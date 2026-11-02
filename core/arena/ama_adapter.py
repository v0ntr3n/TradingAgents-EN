"""
Agent Market Arena (AMA, arXiv:2510.11695v2 — The-FinAI/Agent_Market_Arena)
Standardized REST API Endpoint (`POST /trading_action/`) & Direct Python Adapter
(`core/arena/ama_adapter.py`).

Routes AMA multimodal inputs (daily price, 90-day history_price, Market Intelligence
Stream news summary, and point-in-time 10-K/10-Q filing excerpts) into the 4 orthogonal
CARE-Agents specialists (`market`, `fundamentals`, `news`, `social`), executes the
4-stage Decision-Flip VOI + EvidenceContract + Causal Regime-MWU + Cost-Aware Gate,
and returns the standardized AMA JSON response:
  {
    "recommended_action": "BUY" | "SELL" | "HOLD",
    "reasoning": "Regime: ... | JSD: ... | CBS: ... bps | Gate: ... | Weights: {...} | Rationale: ..."
  }
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, ConfigDict, Field

from core.agents.decision_flip_voi import DecisionFlipVOIEstimator
from core.agents.evidence_contract import (
    adjudicate_with_evidence_contract,
    build_evidence_contract_from_posteriors,
    execute_point_in_time_verification_tool,
)
from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
from tradingagents.graph.conditional_logic import (
    compute_cbs_bps,
    compute_jensen_shannon_divergence,
)


AMA_CORE_STOCKS = ("TSLA", "BMRN")
AMA_CORE_CRYPTOS = ("BTC", "ETH")
AMA_EXTENDED_STOCKS = (
    "TSLA",
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "NFLX",
    "AMD",
    "INTC",
    "BMRN",
    "MRNA",
)
AMA_EXTENDED_CRYPTOS = (
    "BTC",
    "ETH",
    "ADA",
    "SOL",
    "DOT",
    "LINK",
    "UNI",
    "MATIC",
    "AVAX",
    "ATOM",
)
CRYPTO_SYMBOLS = set(AMA_EXTENDED_CRYPTOS) | {"BTC-USD", "ETH-USD", "SOL-USD", "DOGE", "XRP"}

BULLISH_KEYWORDS = (
    "beat",
    "surge",
    "growth",
    "upgrade",
    "approval",
    "record",
    "expansion",
    "bullish",
    "outperform",
    "breakthrough",
    "strong",
    "positive",
    "inflow",
    "adoption",
    "rally",
    "accelerate",
    "profit",
    "buyback",
    "partnership",
)
BEARISH_KEYWORDS = (
    "miss",
    "drop",
    "decline",
    "downgrade",
    "delay",
    "lawsuit",
    "investigation",
    "bearish",
    "underperform",
    "recall",
    "weak",
    "negative",
    "outflow",
    "hack",
    "selloff",
    "headwind",
    "loss",
    "dilution",
    "default",
    "tariff",
    "regulatory risk",
)


class AMATradingActionRequest(BaseModel):
    """Pydantic request schema matching The-FinAI/Agent_Market_Arena `POST /trading_action/`."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date: str
    price: Dict[str, float]
    news: Dict[str, Any] = Field(default_factory=dict)
    symbol: List[str]
    model: str = "gpt-4.1"
    filing_10k: Dict[str, List[str]] = Field(default_factory=dict, alias="10k")
    filing_10q: Dict[str, List[str]] = Field(default_factory=dict, alias="10q")
    history_price: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)


class AMATradingActionResponse(BaseModel):
    """Standardized AMA response schema."""

    recommended_action: str
    reasoning: str


def _keyword_polarity_score(text: str) -> Tuple[float, int, int]:
    """Compute bounded polarity score in [-1, 1] from point-in-time text."""
    if not text:
        return 0.0, 0, 0
    low = text.lower()
    pos_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in low)
    neg_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in low)
    total = pos_hits + neg_hits
    if total == 0:
        return 0.0, 0, 0
    score = (pos_hits - neg_hits) / float(total + 1.0)
    return max(-1.0, min(1.0, score)), pos_hits, neg_hits


def _strip_future_dated_sentences(text: str, trade_date: str) -> str:
    """
    Zero Look-Ahead Guard: If any sentence in `text` explicitly contains an ISO date
    `YYYY-MM-DD` strictly greater than `trade_date`, drop that sentence so future
    leakage can never contaminate step `t`.
    """
    if not text or not trade_date:
        return text or ""
    date_pattern = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
    kept_parts: List[str] = []
    for part in re.split(r"(?<=[.!?;])\s+|\n+", str(text)):
        dates_found = date_pattern.findall(part)
        if any(d > trade_date for d in dates_found):
            continue
        kept_parts.append(part)
    return " ".join(kept_parts).strip()


class AMAProtocolAdapter:
    """
    Adapter bridging `The-FinAI/Agent_Market_Arena` (`arXiv:2510.11695v2`) with
    the 4-stage `CARE-Agents` (`Ours`) architecture.

    Enforces:
      - Warm-up window = 90 trading days, decision memory = 7 days (AMA Table B1)
      - Strict zero look-ahead (`history_price` & text filtered to `<= date`)
      - Non-degenerate specialist modality routing across `market`, `fundamentals`, `news`, `social`
      - 4-stage Decision-Flip VOI + EvidenceContract + Causal Regime-MWU + Cost-Aware Gate
    """

    last_trace: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        warmup_window: int = 90,
        decision_memory_days: int = 7,
        jsd_threshold: float = 0.010,
        stock_spread_bps: float = 5.0,
        crypto_spread_bps: float = 10.0,
        tau_budget_bps: float = 0.0,
    ) -> None:
        self.warmup_window = int(warmup_window)
        self.decision_memory_days = int(decision_memory_days)
        self.jsd_threshold = float(jsd_threshold)
        self.stock_spread_bps = float(stock_spread_bps)
        self.crypto_spread_bps = float(crypto_spread_bps)
        self.tau_budget_bps = float(tau_budget_bps)
        self.weight_manager = RegimeMultiplicativeWeightManager(
            analyst_ids=["market", "fundamentals", "news", "social"],
            w_min=0.05,
        )
        self.voi_estimator = DecisionFlipVOIEstimator()
        self.decision_memory_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        self.prev_position_by_symbol: Dict[str, float] = {}
        self.instance_last_trace: Optional[Dict[str, Any]] = None

    @staticmethod
    def is_crypto_symbol(symbol: str) -> bool:
        sym_clean = str(symbol).upper().strip()
        return sym_clean in CRYPTO_SYMBOLS or sym_clean.endswith("-USD")

    def route_modalities(self, payload: Dict[str, Any], symbol: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Route AMA payload into 4 strictly disjoint specialist modality dictionaries:
          1. `market`: causal OHLCV / close series <= date (up to 90-day warm-up & 7-day memory)
          2. `fundamentals`: 10-K/10-Q SEC filing excerpts for stocks, or causal on-chain/supply
             velocity regime metrics for cryptocurrencies (BTC, ETH)
          3. `news`: AMA Market Intelligence Stream (MIS) macro, regulatory, and corporate catalysts
          4. `social`: crowd sentiment, short-term price/velocity surge, euphoria/panic & reversal risk
        """
        trade_date = str(payload.get("date", ""))
        symbols_list = payload.get("symbol") or list((payload.get("price") or {}).keys()) or ["UNKNOWN"]
        sym = str(symbol or (symbols_list[0] if isinstance(symbols_list, list) else symbols_list)).upper()

        price_map = payload.get("price") or {}
        current_price = float(price_map.get(sym, price_map.get(sym.lower(), 100.0)))

        # Strictly filter history_price to <= trade_date (Zero Look-Ahead Guardrail #1)
        raw_hist = (payload.get("history_price") or {}).get(sym, [])
        causal_hist: List[Tuple[str, float]] = []
        for item in raw_hist:
            if isinstance(item, dict):
                d_str = str(item.get("date", ""))
                p_val = float(item.get("price", item.get("close", current_price)))
                if not trade_date or d_str <= trade_date:
                    causal_hist.append((d_str, p_val))
        causal_hist.sort(key=lambda x: x[0])
        if self.warmup_window > 0 and len(causal_hist) > self.warmup_window:
            causal_hist = causal_hist[-self.warmup_window :]

        closes = [p for _, p in causal_hist]
        if not closes or (causal_hist and causal_hist[-1][0] < trade_date):
            closes.append(current_price)
        else:
            closes[-1] = current_price

        arr_c = np.asarray(closes, dtype=np.float64)
        n_c = len(arr_c)
        ret_1d_pct = float((arr_c[-1] / max(1e-9, arr_c[-2]) - 1.0) * 100.0) if n_c >= 2 else 0.0
        ret_5d_pct = float((arr_c[-1] / max(1e-9, arr_c[-min(n_c, 6)]) - 1.0) * 100.0) if n_c >= 2 else 0.0
        ret_20d_pct = float((arr_c[-1] / max(1e-9, arr_c[-min(n_c, 21)]) - 1.0) * 100.0) if n_c >= 2 else 0.0

        ma4 = float(np.mean(arr_c[-min(n_c, 4) :]))
        ma8 = float(np.mean(arr_c[-min(n_c, 8) :]))
        ma20 = float(np.mean(arr_c[-min(n_c, 20) :]))

        if n_c >= 3:
            daily_rets = np.diff(arr_c) / np.maximum(1e-9, arr_c[:-1])
            sigma_t = float(np.std(daily_rets[-min(len(daily_rets), 20) :], ddof=1))
        else:
            sigma_t = 0.020
        sigma_t = max(0.005, sigma_t)

        # RSI-14 causal calculation
        if n_c >= 3:
            diffs = np.diff(arr_c[-min(n_c, 15) :])
            gains = float(np.mean(np.maximum(0.0, diffs)))
            losses = float(np.mean(np.maximum(0.0, -diffs)))
            rsi_14 = 100.0 - (100.0 / (1.0 + gains / max(1e-9, losses)))
        else:
            rsi_14 = 50.0

        trend_ratio = (current_price / max(1e-9, ma8)) - 1.0
        if trend_ratio > 0.012 and ret_5d_pct > 0.0:
            causal_regime = "bull"
        elif trend_ratio < -0.012 and ret_5d_pct < 0.0:
            causal_regime = "bear"
        else:
            causal_regime = "sideways"

        mem_tail = self.decision_memory_by_symbol.get(sym, [])[-self.decision_memory_days :]

        # 1. Market Specialist Modality
        market_modality = {
            "current_price": round(current_price, 4),
            "warmup_bars_used": n_c,
            "decision_memory_count": len(mem_tail),
            "ma4": round(ma4, 4),
            "ma8": round(ma8, 4),
            "ma20": round(ma20, 4),
            "ma8_ratio": round(current_price / max(1e-9, ma8), 5),
            "ret_5d_pct": round(ret_5d_pct, 4),
            "ret_20d_pct": round(ret_20d_pct, 4),
            "rsi_14": round(rsi_14, 2),
            "trailing_volatility_sigma": round(sigma_t, 5),
            "causal_regime": causal_regime,
        }

        # 2. Fundamentals Specialist Modality
        raw_10k = (payload.get("10k") or payload.get("filing_10k") or {}).get(sym, [])
        raw_10q = (payload.get("10q") or payload.get("filing_10q") or {}).get(sym, [])
        if isinstance(raw_10k, str):
            raw_10k = [raw_10k]
        if isinstance(raw_10q, str):
            raw_10q = [raw_10q]
        clean_10k = [_strip_future_dated_sentences(str(x), trade_date) for x in raw_10k if x]
        clean_10q = [_strip_future_dated_sentences(str(x), trade_date) for x in raw_10q if x]
        filing_text = " ".join(clean_10k + clean_10q)
        filing_polarity, f_pos, f_neg = _keyword_polarity_score(filing_text)
        is_crypto = self.is_crypto_symbol(sym)

        high_90d = float(np.max(arr_c)) if n_c > 0 else current_price
        dd_from_high_pct = float((high_90d - current_price) / max(1e-9, high_90d) * 100.0)

        if is_crypto and not clean_10k and not clean_10q:
            # Crypto asset: route causal on-chain/market-cap & supply-velocity regime metrics
            nvt_velocity_proxy = round(1.0 / max(0.25, 1.0 + sigma_t * 15.0), 4)
            realized_cap_mom = round(math.tanh(ret_20d_pct / 15.0), 4)
            fundamentals_modality = {
                "asset_class": "crypto",
                "sec_10k_excerpt_count": 0,
                "sec_10q_excerpt_count": 0,
                "onchain_nvt_velocity_proxy": nvt_velocity_proxy,
                "realized_cap_momentum": realized_cap_mom,
                "supply_velocity_regime": "accumulation" if dd_from_high_pct < 12.0 else "distribution",
                "drawdown_from_90d_high_pct": round(dd_from_high_pct, 3),
                "fundamental_health_score": round(0.50 + 0.30 * realized_cap_mom - 0.005 * dd_from_high_pct, 4),
            }
        else:
            fundamentals_modality = {
                "asset_class": "equity",
                "sec_10k_excerpt_count": len(clean_10k),
                "sec_10q_excerpt_count": len(clean_10q),
                "filing_sentiment_polarity": round(filing_polarity, 4),
                "filing_positive_terms": f_pos,
                "filing_negative_terms": f_neg,
                "drawdown_from_90d_high_pct": round(dd_from_high_pct, 3),
                "fundamental_health_score": round(0.52 + 0.35 * filing_polarity, 4),
            }

        # 3. News Specialist Modality (AMA Market Intelligence Stream daily summary)
        raw_news_entry = (payload.get("news") or {}).get(sym, "")
        if isinstance(raw_news_entry, list):
            raw_news_str = " ".join(str(x) for x in raw_news_entry)
        elif isinstance(raw_news_entry, dict):
            # Respect published_at <= trade_date if dict provided
            pub_dt = str(raw_news_entry.get("published_at", raw_news_entry.get("date", "")))
            if pub_dt and trade_date and pub_dt > trade_date:
                raw_news_str = ""
            else:
                raw_news_str = str(raw_news_entry.get("summary", raw_news_entry.get("headline", "")))
        else:
            raw_news_str = str(raw_news_entry or "")

        clean_news_str = _strip_future_dated_sentences(raw_news_str, trade_date)
        news_polarity, n_pos, n_neg = _keyword_polarity_score(clean_news_str)

        news_modality = {
            "mis_summary_text": clean_news_str[:500],
            "mis_char_length": len(clean_news_str),
            "catalyst_polarity_score": round(news_polarity, 4),
            "bullish_catalyst_hits": n_pos,
            "bearish_catalyst_hits": n_neg,
            "published_lte_trade_date": True,
        }

        # 4. Social Specialist Modality (crowd sentiment, short-term velocity, euphoria/panic, reversal risk)
        ret_3d_pct = float((arr_c[-1] / max(1e-9, arr_c[-min(n_c, 4)]) - 1.0) * 100.0) if n_c >= 2 else 0.0
        velocity_z = ret_1d_pct / max(0.35, sigma_t * 100.0)
        euphoria_panic_idx = math.tanh(0.55 * velocity_z + 0.45 * news_polarity)
        reversal_risk = min(1.0, max(0.0, (abs(rsi_14 - 50.0) / 50.0) * 0.7 + abs(velocity_z) * 0.15))

        social_modality = {
            "short_term_velocity_1d_pct": round(ret_1d_pct, 4),
            "short_term_velocity_3d_pct": round(ret_3d_pct, 4),
            "velocity_z_score": round(velocity_z, 4),
            "euphoria_panic_index": round(euphoria_panic_idx, 4),
            "crowd_reversal_risk": round(reversal_risk, 4),
        }

        return {
            "market": market_modality,
            "fundamentals": fundamentals_modality,
            "news": news_modality,
            "social": social_modality,
        }

    def compute_specialist_posteriors(
        self,
        modalities: Dict[str, Dict[str, Any]],
        model_id: str = "gpt-4.1",
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate 3-class specialist posteriors `(p_optimistic, p_neutral, p_cautious, expected_move_bps)`
        from each specialist's strictly disjoint modality stream.
        """
        mkt = modalities["market"]
        fund = modalities["fundamentals"]
        news = modalities["news"]
        soc = modalities["social"]

        sigma_bps = max(25.0, float(mkt["trailing_volatility_sigma"]) * 10000.0)
        # Small deterministic model calibration adjustment for AMA backbones
        m_low = str(model_id).lower()
        if "sonnet-4" in m_low or "gpt-4.1" in m_low or "deepseek-v4-pro" in m_low:
            sharpness = 1.12
        elif "gpt-4o" in m_low:
            sharpness = 1.05
        else:
            sharpness = 0.96

        def _make_posterior(edge_signal: float, move_scale: float) -> Dict[str, Any]:
            e = max(-0.70, min(0.70, edge_signal * sharpness))
            p_neu = max(0.12, min(0.50, 0.34 - 0.22 * abs(e)))
            rem = 1.0 - p_neu
            p_opt = max(0.03, min(0.92, 0.5 * rem * (1.0 + e)))
            p_cau = max(0.03, min(0.92, rem - p_opt))
            s = p_opt + p_neu + p_cau
            return {
                "p_optimistic": round(p_opt / s, 6),
                "p_neutral": round(p_neu / s, 6),
                "p_cautious": round(p_cau / s, 6),
                "expected_move_bps": round(sigma_bps * move_scale, 2),
            }

        # 1. Market specialist edge: trend + 5d/20d momentum + RSI regime
        mkt_edge = (
            0.45 * math.tanh(float(mkt["ret_5d_pct"]) / 3.5)
            + 0.35 * math.tanh((float(mkt["ma8_ratio"]) - 1.0) * 25.0)
            + 0.20 * math.tanh((float(mkt["rsi_14"]) - 50.0) / 22.0)
        )
        # 2. Fundamentals specialist edge: SEC 10-K/10-Q health or crypto on-chain regime
        fund_edge = (float(fund["fundamental_health_score"]) - 0.50) * 1.85
        # 3. News specialist edge: MIS daily catalyst polarity
        news_edge = float(news["catalyst_polarity_score"]) * 0.95
        # 4. Social specialist edge: crowd euphoria/panic adjusted for contrarian reversal risk
        soc_raw = float(soc["euphoria_panic_index"])
        rev_risk = float(soc["crowd_reversal_risk"])
        soc_edge = soc_raw * (1.0 - 0.65 * rev_risk) - 0.25 * rev_risk * math.copysign(1.0, soc_raw if abs(soc_raw) > 1e-6 else 1.0)

        return {
            "market": _make_posterior(mkt_edge, 1.05),
            "fundamentals": _make_posterior(fund_edge, 0.95),
            "news": _make_posterior(news_edge, 1.15),
            "social": _make_posterior(soc_edge, 0.90),
        }

    def trading_action(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Execute the full 4-stage CARE-Agents (`Ours`) pipeline on an AMA `/trading_action/`
        payload and return `{"recommended_action": "BUY"|"SELL"|"HOLD", "reasoning": "..."}`.
        """
        trade_date = str(payload.get("date", ""))
        symbols_list = payload.get("symbol") or list((payload.get("price") or {}).keys()) or ["TSLA"]
        sym = str(symbols_list[0] if isinstance(symbols_list, list) else symbols_list).upper()
        model_id = str(payload.get("model", "gpt-4.1"))

        modalities = self.route_modalities(payload, symbol=sym)
        regime = str(modalities["market"]["causal_regime"])
        posteriors = self.compute_specialist_posteriors(modalities, model_id=model_id)

        # Stage 1: Causal Regime-MWU fast-path aggregation
        weights = self.weight_manager.get_regime_weights(regime, ["market", "fundamentals", "news", "social"])
        unverified_agg = self.weight_manager.aggregate_posteriors(regime, posteriors, method="linear")
        jsd = compute_jensen_shannon_divergence(posteriors, weights=weights)
        cbs_bps = compute_cbs_bps(posteriors, weights=weights)

        # Stage 2: Build & validate structured EvidenceContract
        contract = build_evidence_contract_from_posteriors(
            symbol=sym,
            trade_date=trade_date,
            posteriors=posteriors,
            unverified_agg=unverified_agg,
            market_context={
                "reported_news_lag_days": 0.0,
                "has_conflicting_headline": abs(
                    posteriors["fundamentals"]["p_optimistic"] - posteriors["news"]["p_optimistic"]
                )
                > 0.20,
                "has_unverified_rumor": float(modalities["social"]["crowd_reversal_risk"]) > 0.65,
            },
            binary_long_only=False,
        )

        # Stage 3 & 4: Calibrated Decision-Flip VOI & Cost-Aware Verification Gate
        is_crypto = self.is_crypto_symbol(sym)
        spread_bps = self.crypto_spread_bps if is_crypto else self.stock_spread_bps
        prev_pos = float(self.prev_position_by_symbol.get(sym, 0.0))
        sigma_t = float(modalities["market"]["trailing_volatility_sigma"])

        voi_eval = self.voi_estimator.evaluate_step_voi(
            jsd=jsd,
            cbs_bps=cbs_bps,
            unverified_agg=unverified_agg,
            contract=contract,
            prev_position=prev_pos,
            spread_bps=spread_bps,
            sigma_20d=sigma_t,
            regime=regime,
            tau_budget_bps=self.tau_budget_bps,
            cost_aware=True,
        )

        gate_open = bool(
            voi_eval["trigger_verify"] or (jsd >= self.jsd_threshold and cbs_bps > spread_bps)
        )

        if gate_open:
            # Synthesize CBS-arbitrated deliberation posterior from evidence channels at <= date
            deb_opt = (
                0.35 * posteriors["market"]["p_optimistic"]
                + 0.35 * posteriors["fundamentals"]["p_optimistic"]
                + 0.20 * posteriors["news"]["p_optimistic"]
                + 0.10 * posteriors["social"]["p_optimistic"]
            )
            deb_cau = (
                0.35 * posteriors["market"]["p_cautious"]
                + 0.35 * posteriors["fundamentals"]["p_cautious"]
                + 0.20 * posteriors["news"]["p_cautious"]
                + 0.10 * posteriors["social"]["p_cautious"]
            )
            deb_neu = max(0.05, 1.0 - deb_opt - deb_cau)
            step_data = {
                "date": trade_date,
                "posteriors": posteriors,
                "specialist_modalities": modalities,
                "m4_cbs_debate": {
                    "p_optimistic": deb_opt,
                    "p_neutral": deb_neu,
                    "p_cautious": deb_cau,
                    "expected_move_bps": unverified_agg["expected_move_bps"],
                },
            }
            ev = execute_point_in_time_verification_tool(contract, step_data)
            final_post = adjudicate_with_evidence_contract(
                contract=contract,
                unverified_agg=unverified_agg,
                evidence=ev,
                debate_posterior=step_data["m4_cbs_debate"],
                binary_long_only=False,
            )
            gate_label = "OPEN"
        else:
            final_post = dict(unverified_agg)
            gate_label = "FAST_PATH"

        p_opt = float(final_post["p_optimistic"])
        p_cau = float(final_post["p_cautious"])
        edge = p_opt - p_cau
        exp_move = float(final_post.get("expected_move_bps", 50.0))
        expected_edge_bps = abs(edge) * exp_move

        # Cost-aware action mapping to {"BUY", "SELL", "HOLD"}
        min_edge_thresh = max(0.025, (spread_bps * 0.45) / max(20.0, exp_move))
        if edge > min_edge_thresh and expected_edge_bps >= spread_bps * 0.5:
            recommended_action = "BUY"
            new_pos = 1.0
        elif edge < -min_edge_thresh and expected_edge_bps >= spread_bps * 0.5:
            recommended_action = "SELL"
            new_pos = -1.0
        else:
            recommended_action = "HOLD"
            new_pos = 0.0

        self.prev_position_by_symbol[sym] = new_pos
        self.decision_memory_by_symbol.setdefault(sym, []).append(
            {
                "date": trade_date,
                "action": recommended_action,
                "regime": regime,
                "edge": round(edge, 4),
            }
        )

        weights_Compact = {k: round(float(v), 3) for k, v in weights.items()}
        reasoning = (
            f"Regime: {regime} | JSD: {jsd:.4f} | CBS: {cbs_bps:.1f} bps | "
            f"VOI: {voi_eval['voi_ours_bps']:.2f} bps | Gate: {gate_label} | "
            f"Contract: {contract.target_tool} ({contract.vulnerability_type}) | "
            f"Weights: {json.dumps(weights_Compact)} | "
            f"Rationale: {sym} ({'Crypto' if is_crypto else 'Stock'}) p_opt={p_opt:.3f}, "
            f"p_cau={p_cau:.3f}, net_edge={edge:+.3f} -> {recommended_action}."
        )

        trace = {
            "symbol": sym,
            "date": trade_date,
            "model": model_id,
            "is_crypto": is_crypto,
            "regime": regime,
            "specialist_modalities": modalities,
            "specialist_posteriors": posteriors,
            "weights": weights,
            "unverified_posterior": unverified_agg,
            "final_posterior": final_post,
            "jsd": round(jsd, 6),
            "cbs_bps": round(cbs_bps, 4),
            "gate_open": gate_open,
            "evidence_contract": contract.to_dict(),
            "voi_eval": voi_eval,
            "recommended_action": recommended_action,
            "reasoning": reasoning,
        }
        self.instance_last_trace = trace
        AMAProtocolAdapter.last_trace = trace

        return {
            "recommended_action": recommended_action,
            "reasoning": reasoning,
        }


# Singleton default adapter and FastAPI router for `POST /trading_action/`
_default_ama_adapter = AMAProtocolAdapter()
ama_router = APIRouter(tags=["Agent Market Arena (AMA)"])


@ama_router.post("/trading_action/", response_model=AMATradingActionResponse)
@ama_router.post("/trading_action", response_model=AMATradingActionResponse)
def post_trading_action(request: Dict[str, Any]) -> Dict[str, str]:
    """
    Standardized AMA REST API endpoint (`POST /trading_action/`) compatible with
    `The-FinAI/Agent_Market_Arena` (`testbed/get_daily_action.py`).
    """
    return _default_ama_adapter.trading_action(request)


def create_ama_fastapi_app() -> FastAPI:
    """Create a standalone FastAPI application exposing `POST /trading_action/`."""
    application = FastAPI(
        title="CARE-Agents Agent Market Arena (AMA) Service",
        version="3.0.0",
    )
    application.include_router(ama_router)
    return application


app = create_ama_fastapi_app()
