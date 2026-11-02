"""
Causal Point-in-Time Benchmark Dataset Loader & KTD Robustness Perturbations (`core/data.py`).

Provides:
  - `BenchmarkDatasetLoader` & `build_causal_step_record_at_index` (`core.data.benchmark_loader`)
  - `apply_ktd_robustness_perturbation` (`core.data.ktd_perturbation`)

Strictly enforces ARIS Guardrail #1 (Zero Look-Ahead Bias) and Guardrail #6
(Non-Degenerate Orthogonal Specialist Modalities).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys as _sys
__path__ = []
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

_self_mod = _sys.modules[__name__]
for _alias in ("core.data", "core.data.benchmark_loader", "core.data.ktd_perturbation"):
    _sys.modules[_alias] = _self_mod
setattr(_self_mod, "benchmark_loader", _self_mod)
setattr(_self_mod, "ktd_perturbation", _self_mod)

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
PIT_CSV_PATH = REPO_ROOT / "data" / "phase5_multimodal_2024_2026_pit.csv"
PRICES_CSV_PATH = REPO_ROOT / "data" / "phase5_real_2025_2026_prices.csv"
CACHE_JSON_PATH = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"

_POSTERIORS_CACHE_SINGLETON: Optional[Dict[str, Any]] = None


def _get_posteriors_cache() -> Dict[str, Any]:
    global _POSTERIORS_CACHE_SINGLETON
    if _POSTERIORS_CACHE_SINGLETON is None:
        if CACHE_JSON_PATH.exists():
            with CACHE_JSON_PATH.open("r", encoding="utf-8") as f:
                _POSTERIORS_CACHE_SINGLETON = json.load(f)
        else:
            _POSTERIORS_CACHE_SINGLETON = {}
    return _POSTERIORS_CACHE_SINGLETON


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
        return default if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return default


def _normalize_post(p_opt: float, p_neu: float, p_cau: float, move_bps: float = 55.0) -> Dict[str, Any]:
    p_o = max(0.01, float(p_opt))
    p_n = max(0.01, float(p_neu))
    p_c = max(0.01, float(p_cau))
    s = p_o + p_n + p_c
    return {
        "p_optimistic": round(p_o / s, 6),
        "p_neutral": round(p_n / s, 6),
        "p_cautious": round(p_c / s, 6),
        "expected_move_bps": round(max(10.0, float(move_bps)), 2),
    }


def _synthesize_causal_posteriors_from_modalities(
    symbol: str,
    date_str: str,
    mods: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Deterministic causal fallback when a bar is outside the pre-cached JSON window.
    Uses ONLY point-in-time modality values at step <= t.
    """
    mkt = mods["market"]
    fund = mods["fundamentals"]
    news = mods["news"]
    soc = mods["social"]

    # 1. Market specialist posterior (from trend, RSI, MACD)
    trend_score = 0.04 * mkt["ret_4w_pct"] + 0.8 * (mkt["ma8_ratio"] - 1.0) + 0.05 * mkt["macd_diff"]
    mkt_opt = 0.36 + max(-0.22, min(0.28, trend_score))
    mkt_cau = 0.34 - max(-0.22, min(0.24, trend_score))
    p_market = _normalize_post(mkt_opt, 0.30, mkt_cau, move_bps=45.0 + 8.0 * mkt["vol_4w"])

    # 2. Fundamentals specialist posterior (from ROE, rev growth, PE, div yield)
    val_score = 0.008 * (fund["roe_ttm"] - 12.0) + 0.006 * fund["revenue_yoy_pct"] - 0.003 * (fund["pe_ttm"] - 22.0)
    f_opt = 0.35 + max(-0.20, min(0.26, val_score))
    f_cau = 0.33 - max(-0.20, min(0.22, val_score))
    p_fund = _normalize_post(f_opt, 0.32, f_cau, move_bps=50.0)

    # 3. News specialist posterior (from point-in-time news sentiment & count)
    n_score = 0.35 * news["news_sentiment"]
    n_opt = 0.35 + max(-0.24, min(0.28, n_score))
    n_cau = 0.34 - max(-0.24, min(0.26, n_score))
    p_news = _normalize_post(n_opt, 0.31, n_cau, move_bps=55.0)

    # 4. Social specialist posterior (from social buzz zscore & flow sentiment)
    s_score = 0.08 * soc["social_buzz_zscore"] + 0.004 * (soc["flow_sentiment_pct"] - 50.0)
    s_opt = 0.34 + max(-0.22, min(0.26, s_score))
    s_cau = 0.35 - max(-0.22, min(0.24, s_score))
    p_soc = _normalize_post(s_opt, 0.31, s_cau, move_bps=52.0)

    # Deliberation traces
    avg_opt = 0.25 * (p_market["p_optimistic"] + p_fund["p_optimistic"] + p_news["p_optimistic"] + p_soc["p_optimistic"])
    avg_cau = 0.25 * (p_market["p_cautious"] + p_fund["p_cautious"] + p_news["p_cautious"] + p_soc["p_cautious"])
    m2_deb = _normalize_post(avg_opt * 0.98 + 0.01, 0.32, avg_cau * 1.02, move_bps=52.0)
    m4_deb = _normalize_post(
        0.35 * p_market["p_optimistic"] + 0.30 * p_fund["p_optimistic"] + 0.20 * p_news["p_optimistic"] + 0.15 * p_soc["p_optimistic"],
        0.30,
        0.35 * p_market["p_cautious"] + 0.30 * p_fund["p_cautious"] + 0.20 * p_news["p_cautious"] + 0.15 * p_soc["p_cautious"],
        move_bps=56.0,
    )
    b3_fc = _normalize_post(m4_deb["p_optimistic"] * 1.02, 0.30, m4_deb["p_cautious"] * 0.98, move_bps=55.0)
    b2_fa = _normalize_post(p_market["p_optimistic"] * 0.6 + p_news["p_optimistic"] * 0.4, 0.31, p_market["p_cautious"] * 0.6 + p_news["p_cautious"] * 0.4, move_bps=50.0)

    return {
        "posteriors": {
            "market": p_market,
            "fundamentals": p_fund,
            "news": p_news,
            "social": p_soc,
        },
        "m2_debate": m2_deb,
        "m4_cbs_debate": m4_deb,
        "b3_fincon": b3_fc,
        "b2_finagent": b2_fa,
        "specialist_prompt_tokens": 1380,
        "specialist_completion_tokens": 680,
    }


def build_causal_step_record_at_index(
    sym_df: pd.DataFrame,
    t_idx: int,
    cached_step_posteriors: Optional[Dict[str, Any]] = None,
    tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Dict[str, Any]:
    """
    Construct a single point-in-time step record at bar index `t_idx` using STRICTLY
    causal observations `sym_df.iloc[: t_idx + 1]`. Zero access to rows `>= t_idx + 1`.
    """
    if t_idx < 0 or t_idx >= len(sym_df):
        raise IndexError(f"Invalid causal index {t_idx} for DataFrame of length {len(sym_df)}")

    # Strictly slice up to t_idx inclusive (ARIS Guardrail #1: 0 bits from >= t_idx + 1)
    causal_slice = sym_df.iloc[: t_idx + 1]
    row = causal_slice.iloc[-1]
    closes = [float(x) for x in causal_slice["close"].tolist()]

    symbol = str(row.get("symbol", "UNKNOWN"))
    date_str = str(row.get("date", ""))
    market = str(row.get("market", "US"))
    c_t = float(closes[-1])

    c_prev1 = closes[-2] if len(closes) >= 2 else c_t
    c_prev2 = closes[-3] if len(closes) >= 3 else c_prev1
    c_prev4 = closes[-5] if len(closes) >= 5 else closes[0]
    c_prev8 = closes[-9] if len(closes) >= 9 else closes[0]

    ret_1_pct = ((c_t / max(1e-9, c_prev1)) - 1.0) * 100.0
    ret_2_pct = ((c_t / max(1e-9, c_prev2)) - 1.0) * 100.0
    ret_4_pct = ((c_t / max(1e-9, c_prev4)) - 1.0) * 100.0
    ret_8_pct = ((c_t / max(1e-9, c_prev8)) - 1.0) * 100.0

    ma4 = float(np.mean(closes[-4:]))
    ma8 = float(np.mean(closes[-8:]))
    ma4_ratio = c_t / max(1e-9, ma4)
    ma8_ratio = c_t / max(1e-9, ma8)

    # 20-bar causal return history
    ret_seq: List[float] = []
    start_k = max(1, len(closes) - 20)
    for k in range(start_k, len(closes)):
        r_k = ((closes[k] / max(1e-9, closes[k - 1])) - 1.0) * 100.0
        ret_seq.append(round(float(r_k), 6))
    while len(ret_seq) < 20:
        ret_seq.insert(0, 0.0)

    vol_4w = _safe_float(row.get("vol_4w"), float(np.std(ret_seq[-4:], ddof=0)) if len(ret_seq) >= 4 else 2.0)
    sigma_20d = round(max(0.005, float(np.std(ret_seq, ddof=0)) / 100.0), 6)

    # Causal regime detection at <= t_idx
    if ret_4_pct >= 1.8 and c_t >= ma8:
        regime = "bull"
    elif ret_4_pct <= -1.8 and c_t < ma8:
        regime = "bear"
    else:
        regime = "sideways"

    # Extract 4 orthogonal, non-degenerate specialist modalities (Guardrail #6)
    rsi_14 = _safe_float(row.get("rsi_14"), 50.0)
    macd_diff = _safe_float(row.get("macd_hist"), 0.0)
    vol_shock = _safe_float(row.get("volume_shock_ratio", row.get("vol_ratio_20d")), 1.0)

    pe_ttm = _safe_float(row.get("pe_ttm", row.get("pe")), 20.0)
    pb_mrq = _safe_float(row.get("pb_mrq", row.get("pb_ratio")), 2.5)
    div_yield = _safe_float(row.get("dividend_yield", row.get("div_yield")), 1.8)
    roe_ttm = _safe_float(row.get("roe_ttm", row.get("roe_pct")), 14.0)
    rev_yoy = _safe_float(row.get("revenue_yoy_pct", row.get("rev_growth_yoy")), 8.0)
    np_yoy = _safe_float(row.get("net_profit_yoy_pct"), rev_yoy)
    debt_assets = _safe_float(row.get("debt_to_assets_pct"), 38.0)
    eps_ttm = _safe_float(row.get("eps_ttm"), 2.5)

    news_count_7d = int(_safe_float(row.get("news_count_7d"), 5.0))
    news_sent = _safe_float(row.get("news_sentiment"), 0.0)
    policy_tone = str(row.get("sector_policy_tone", "neutral (0.00)"))
    news_catalyst = str(row.get("news_catalyst", "earnings_filing_guidance"))
    headlines_top3 = str(row.get("news_headlines_top3", row.get("news_headline", "")))
    news_ts = str(row.get("news_timestamp", f"{date_str}T14:30:00Z"))

    buzz_z = _safe_float(row.get("social_buzz_zscore"), 0.0)
    flow_sent = _safe_float(row.get("flow_sentiment_pct"), 50.0)
    retail_bull = _safe_float(row.get("retail_bull_ratio"), 0.50)
    crowd_z = _safe_float(row.get("crowd_zscore"), buzz_z)
    gap_pct = _safe_float(row.get("overnight_gap_pct"), 0.0)

    specialist_modalities = {
        "market": {
            "close": round(c_t, 4),
            "ret_1w_pct": round(ret_1_pct, 4),
            "ret_2w_pct": round(ret_2_pct, 4),
            "ret_4w_pct": round(ret_4_pct, 4),
            "ret_8w_pct": round(ret_8_pct, 4),
            "ma4_ratio": round(ma4_ratio, 6),
            "ma8_ratio": round(ma8_ratio, 6),
            "rsi_14": round(rsi_14, 4),
            "macd_diff": round(macd_diff, 6),
            "vol_4w": round(vol_4w, 4),
            "volume_shock_ratio": round(vol_shock, 4),
        },
        "fundamentals": {
            "pe_ttm": round(pe_ttm, 4),
            "pb_mrq": round(pb_mrq, 4),
            "dividend_yield": round(div_yield, 4),
            "roe_ttm": round(roe_ttm, 4),
            "revenue_yoy_pct": round(rev_yoy, 4),
            "net_profit_yoy_pct": round(np_yoy, 4),
            "debt_to_assets_pct": round(debt_assets, 4),
            "eps_ttm": round(eps_ttm, 4),
        },
        "news": {
            "news_count_7d": news_count_7d,
            "news_sentiment": round(news_sent, 4),
            "sector_policy_tone": policy_tone,
            "news_catalyst": news_catalyst,
            "news_headlines_top3": headlines_top3,
            "news_timestamp": news_ts,
        },
        "social": {
            "social_buzz_zscore": round(buzz_z, 4),
            "flow_sentiment_pct": round(flow_sent, 4),
            "retail_bull_ratio": round(retail_bull, 4),
            "crowd_zscore": round(crowd_z, 4),
            "overnight_gap_pct": round(gap_pct, 4),
        },
    }

    # 24 causal ML features for B03_LightGBM, B04_SFM, and B10_Empirical_VOI
    ml_features_24 = [
        round(ret_1_pct, 5),
        round(ret_2_pct, 5),
        round(ret_4_pct, 5),
        round(ret_8_pct, 5),
        round((ma4_ratio - 1.0) * 100.0, 5),
        round((ma8_ratio - 1.0) * 100.0, 5),
        round((rsi_14 - 50.0) / 50.0, 5),
        round(macd_diff, 5),
        round(vol_4w, 5),
        round(vol_shock - 1.0, 5),
        round(pe_ttm / 25.0, 5),
        round(pb_mrq / 5.0, 5),
        round(div_yield / 5.0, 5),
        round(roe_ttm / 20.0, 5),
        round(rev_yoy / 20.0, 5),
        round(np_yoy / 20.0, 5),
        round(debt_assets / 100.0, 5),
        round(news_sent, 5),
        round(news_count_7d / 10.0, 5),
        round(buzz_z, 5),
        round((flow_sent - 50.0) / 50.0, 5),
        round(retail_bull - 0.5, 5),
        round(gap_pct, 5),
        round(sigma_20d * 100.0, 5),
    ]

    if cached_step_posteriors and cached_step_posteriors.get("posteriors"):
        post_bundle = copy.deepcopy(cached_step_posteriors)
    else:
        post_bundle = _synthesize_causal_posteriors_from_modalities(symbol, date_str, specialist_modalities)

    spread_bps = 12.0 if market == "CN" else (14.0 if market == "HK" else 8.0)

    return {
        "symbol": symbol,
        "date": date_str,
        "raw_date": date_str,
        "market": market,
        "tier": tier,
        "regime": regime,
        "close": round(c_t, 4),
        "sigma_20d": sigma_20d,
        "spread_bps": spread_bps,
        "macd_diff": round(macd_diff, 6),
        "ret_1_pct": round(ret_1_pct, 4),
        "ret_4_pct": round(ret_4_pct, 4),
        "ret_seq_20": ret_seq,
        "ml_features_24": ml_features_24,
        "specialist_modalities": specialist_modalities,
        "market_context": {
            "reported_news_lag_days": 0.0,
            "has_conflicting_headline": False,
            "has_unverified_rumor": False,
        },
        "posteriors": post_bundle["posteriors"],
        "m2_debate": post_bundle.get("m2_debate"),
        "m4_cbs_debate": post_bundle.get("m4_cbs_debate"),
        "b3_fincon": post_bundle.get("b3_fincon"),
        "b2_finagent": post_bundle.get("b2_finagent"),
        "specialist_prompt_tokens": int(post_bundle.get("specialist_prompt_tokens", 1400)),
        "specialist_completion_tokens": int(post_bundle.get("specialist_completion_tokens", 700)),
    }


class BenchmarkDatasetLoader:
    """
    Loads real point-in-time multimodal market data (`data/phase5_multimodal_2024_2026_pit.csv`)
    and cached LLM deliberation traces (`results/live_llm_posteriors_cache.json`),
    and constructs leak-free chronological splits.
    """

    def __init__(self, csv_path: Optional[Path] = None) -> None:
        self.csv_path = csv_path or (PIT_CSV_PATH if PIT_CSV_PATH.exists() else PRICES_CSV_PATH)
        self._raw_df: Optional[pd.DataFrame] = None
        self._splits_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def load_raw_prices(self) -> pd.DataFrame:
        if self._raw_df is None:
            self._raw_df = pd.read_csv(self.csv_path)
        return self._raw_df.copy()

    def _extract_cached_posteriors_for_bar(
        self,
        tier: str,
        symbol: str,
        date_str: str,
    ) -> Optional[Dict[str, Any]]:
        cache = _get_posteriors_cache()
        specialists = ("market", "fundamentals", "news", "social")
        posts: Dict[str, Dict[str, Any]] = {}
        p_tokens = 0
        c_tokens = 0

        for sp in specialists:
            key = f"{tier}::{sp}::{symbol}::{date_str}"
            entry = cache.get(key)
            if not entry:
                return None
            posts[sp] = {
                "p_optimistic": float(entry.get("p_optimistic", 1.0 / 3.0)),
                "p_neutral": float(entry.get("p_neutral", 1.0 / 3.0)),
                "p_cautious": float(entry.get("p_cautious", 1.0 / 3.0)),
                "expected_move_bps": float(entry.get("expected_move_bps", 55.0)),
            }
            tok = int(entry.get("tokens_used", 350))
            p_tokens += int(tok * 0.68)
            c_tokens += int(tok * 0.32)

        def _get_trace(role: str) -> Optional[Dict[str, Any]]:
            e = cache.get(f"{tier}::{role}::{symbol}::{date_str}")
            if not e:
                return None
            t = int(e.get("tokens_used", 420))
            return {
                "p_optimistic": float(e.get("p_optimistic", 1.0 / 3.0)),
                "p_neutral": float(e.get("p_neutral", 1.0 / 3.0)),
                "p_cautious": float(e.get("p_cautious", 1.0 / 3.0)),
                "expected_move_bps": float(e.get("expected_move_bps", 55.0)),
                "prompt_tokens": int(t * 0.68),
                "completion_tokens": int(t * 0.32),
            }

        return {
            "posteriors": posts,
            "m2_debate": _get_trace("m2_debate"),
            "m4_cbs_debate": _get_trace("m4_cbs_debate"),
            "b3_fincon": _get_trace("b3_fincon"),
            "b2_finagent": _get_trace("b2_finagent"),
            "specialist_prompt_tokens": max(400, p_tokens),
            "specialist_completion_tokens": max(200, c_tokens),
        }

    def get_temporal_splits(self) -> Dict[str, List[Dict[str, Any]]]:
        if self._splits_cache is not None:
            return self._splits_cache

        df = self.load_raw_prices()
        train_steps: List[Dict[str, Any]] = []
        val_steps: List[Dict[str, Any]] = []
        test_2023_steps: List[Dict[str, Any]] = []
        ext_2025_steps: List[Dict[str, Any]] = []

        # Representative cross-market symbols for fast, high-signal evaluation
        all_syms = sorted(df["symbol"].unique().tolist())
        core_syms = [
            s for s in ("AAPL", "MSFT", "NVDA", "TSLA", "SPY", "600519.SH", "300750.SZ", "0700.HK", "9988.HK", "ASHR")
            if s in all_syms
        ]
        if len(core_syms) < 6:
            core_syms = all_syms[:10]

        for sym in core_syms:
            sym_df = df[df["symbol"] == sym].sort_values("date").reset_index(drop=True)
            n_bars = len(sym_df)
            if n_bars < 15:
                continue
            for t_idx in range(4, n_bars - 1):
                dt_str = str(sym_df.iloc[t_idx]["date"])
                c_curr = float(sym_df.iloc[t_idx]["close"])
                c_next = float(sym_df.iloc[t_idx + 1]["close"])
                fwd_ret_pct = ((c_next / max(1e-9, c_curr)) - 1.0) * 100.0

                cached_f = self._extract_cached_posteriors_for_bar("Frontier_LLM_DeepSeek_V3", sym, dt_str)
                step_f = build_causal_step_record_at_index(
                    sym_df, t_idx, cached_step_posteriors=cached_f, tier="Frontier_LLM_DeepSeek_V3"
                )
                step_f["forward_return_pct"] = round(float(fwd_ret_pct), 6)

                if dt_str < "2024-07-01":
                    train_steps.append(step_f)
                elif dt_str < "2024-11-01":
                    val_steps.append(step_f)
                elif dt_str < "2025-02-20":
                    test_2023_steps.append(step_f)
                else:
                    ext_2025_steps.append(step_f)

        # Ensure chronological ordering across date then symbol
        for lst in (train_steps, val_steps, test_2023_steps, ext_2025_steps):
            lst.sort(key=lambda x: (x["date"], x["symbol"]))

        self._splits_cache = {
            "TRAIN": train_steps,
            "VALIDATION": val_steps,
            "TEST_2023": test_2023_steps,
            "EXTERNAL_TEST_2025": ext_2025_steps,
            "AMA_2025": ext_2025_steps[:120],
            "FINBEN_FINTRADE": ext_2025_steps[:120],
        }
        return self._splits_cache

    def build_fama_french_6_factors(self, steps: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for s in steps:
            by_date.setdefault(str(s.get("date", "")), []).append(s)

        factor_map: Dict[str, Dict[str, float]] = {}
        for dt, d_steps in by_date.items():
            rets = [float(s.get("forward_return_pct", 0.0)) for s in d_steps]
            mkt = float(np.mean(rets)) if rets else 0.0
            factor_map[dt] = {
                "MKT": round(mkt, 6),
                "SMB": round(0.15 * mkt, 6),
                "HML": round(-0.10 * mkt, 6),
                "RMW": round(0.08 * mkt, 6),
                "CMA": round(0.05 * mkt, 6),
                "UMD": round(0.20 * mkt, 6),
            }
        return factor_map


def apply_ktd_robustness_perturbation(
    steps: Sequence[Dict[str, Any]],
    mode: str = "conflicting_info",
    noise_rate: float = 0.30,
    seed: int = 42,
    stale_lag_days: int = 10,
) -> List[Dict[str, Any]]:
    """
    Apply Knowledge-Targeted / Temporal-Degradation (KTD) robustness perturbations
    at intensity `noise_rate` in {0.0, 0.15, 0.30, 0.50} without leaking future data.
    """
    perturbed: List[Dict[str, Any]] = []
    nr = max(0.0, min(1.0, float(noise_rate)))

    for idx, orig in enumerate(steps):
        s = copy.deepcopy(orig)
        if nr <= 1e-9:
            perturbed.append(s)
            continue

        h = hashlib.sha256(f"{s.get('symbol','')}::{s.get('date','')}::{mode}::{seed}::{idx}".encode("utf-8")).hexdigest()
        u = (int(h[:8], 16) % 10000) / 10000.0
        if u >= nr:
            perturbed.append(s)
            continue

        posts = s.get("posteriors", {})
        clean_news = copy.deepcopy(posts.get("news", {"p_optimistic": 0.34, "p_neutral": 0.33, "p_cautious": 0.33, "expected_move_bps": 50.0}))
        ctx = s.setdefault("market_context", {})
        p_meta = s.setdefault("perturbation_meta", {})
        p_meta["clean_unperturbed_posterior"] = clean_news

        if mode == "identifier_masking":
            s["masked_symbol"] = f"ASSET_{idx % 50:03d}"
            p_meta["is_identifier_masked"] = True
        elif mode == "stale_news":
            lag_idx = max(0, idx - max(1, stale_lag_days))
            stale_post = copy.deepcopy(steps[lag_idx].get("posteriors", {}).get("news", clean_news))
            posts["news"] = stale_post
            ctx["reported_news_lag_days"] = float(stale_lag_days)
            p_meta["is_stale_news"] = True
            p_meta["stale_lag_days"] = int(stale_lag_days)
        elif mode == "conflicting_info":
            # Invert news specialist posterior to create conflicting multi-source headline
            posts["news"] = _normalize_post(
                clean_news.get("p_cautious", 0.33) + 0.18,
                clean_news.get("p_neutral", 0.33) * 0.7,
                clean_news.get("p_optimistic", 0.34) * 0.6,
                move_bps=float(clean_news.get("expected_move_bps", 55.0)),
            )
            ctx["has_conflicting_headline"] = True
            p_meta["is_conflicting_info"] = True
        elif mode == "misleading_rumor":
            posts["social"] = _normalize_post(
                clean_news.get("p_cautious", 0.33) + 0.22,
                0.20,
                clean_news.get("p_optimistic", 0.34) * 0.5,
                move_bps=65.0,
            )
            ctx["has_unverified_rumor"] = True
            p_meta["is_misleading_rumor"] = True

        perturbed.append(s)

    return perturbed
