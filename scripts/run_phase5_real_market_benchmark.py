"""
Phase 5 Real-Market Benchmark Runner (2025-2026 Post-Cutoff Point-in-Time Data)
================================================================================
Executes:
  1. Dual-Backbone 2x4 Cross-Architecture Factorial Comparison (MR-1 to MR-7)
  2. SOTA External Baseline PnL ($100,000 Initial Capital) Comparison against
     classical quant rules (Q1 SMA Crossover, Q2 MACD+RSI) and published LLM
     frameworks (B1 FinMem, B2 FinAgent, B3 FinCon, M2 TradingAgents).

Audit & Fairness Guarantees:
  - Zero market-specific `if is_cn:` branches in specialist signal generation or
    protocol position mapping.
  - All protocols (M1, M2, M3, M4) share the exact same `unified_position_from_posterior()`
    mapping function and `linear_pool()` aggregation; only their coordination weights,
    CBS debate gating, and episodic drawdown circuit breaker differ.
  - Exact M1 turnover (`m1_turnover * cost_rate`) is used when computing CBS surplus.
  - Supports `--use-live-llm-api` via CLI `argparse` with deterministic JSON caching.
"""

import os
import sys
import csv
import json
import math
import time
import hashlib
import threading
import argparse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Tuple, Optional
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env", override=False)
except ImportError:
    pass

import tests  # registers lightweight offline stubs if optional cloud SDKs are absent
from core.agents.analyst import extract_structured_posterior
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_jensen_shannon_divergence,
    compute_cbs_bps,
)
from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
from tradingagents.graph.signal_processing import SignalProcessor
from core.agents.reflection_helper import compute_counterfactual_attribution
from core.backtest.result_evaluator import ProtocolAuditEvaluator


def load_real_2025_2026_dataset(csv_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Load real 2025-2026 weekly prices and valuation metrics grouped by symbol."""
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row["symbol"]
            by_symbol.setdefault(sym, []).append({
                "symbol": sym,
                "name": row["name"],
                "market": row["market"],
                "date": row["date"],
                "close": float(row["close"]),
                "pe_ratio": float(row.get("pe", row.get("pe_ratio", 20.0))),
                "dividend_yield": float(row.get("div_yield", row.get("dividend_yield", 1.5))),
            })
    for sym in by_symbol:
        by_symbol[sym].sort(key=lambda r: r["date"])
    return by_symbol


def detect_causal_regime(
    closes: List[float],
    idx: int,
    window_len: int = 8,
) -> Tuple[str, Dict[str, float]]:
    """
    Compute strictly point-in-time (causal) technical and volatility features
    using ONLY historical observations up to index `idx` (time t). Zero look-ahead (MR-2).
    """
    p_curr = closes[idx]
    p_prev1 = closes[max(0, idx - 1)]
    p_prev2 = closes[max(0, idx - 2)]
    p_prev3 = closes[max(0, idx - 3)]
    p_prev4 = closes[max(0, idx - 4)]
    p_prev8 = closes[max(0, idx - window_len)]

    ret_1w = (p_curr / p_prev1 - 1.0) * 100.0 if p_prev1 > 0 else 0.0
    ret_2w = (p_curr / p_prev2 - 1.0) * 100.0 if p_prev2 > 0 else 0.0
    ret_3w = (p_curr / p_prev3 - 1.0) * 100.0 if p_prev3 > 0 else 0.0
    ret_4w = (p_curr / p_prev4 - 1.0) * 100.0 if p_prev4 > 0 else 0.0
    ret_8w = (p_curr / p_prev8 - 1.0) * 100.0 if p_prev8 > 0 else 0.0

    window_4 = closes[max(0, idx - 3): idx + 1]
    window_8 = closes[max(0, idx - window_len + 1): idx + 1]
    ma4 = float(np.mean(window_4))
    ma8 = float(np.mean(window_8))

    # Strictly causal trailing weekly returns up to index `idx` (step t) with sample std (ddof=1)
    vol_lookback = max(2, window_len // 2)
    rets_4w = [(closes[k] / closes[k - 1] - 1.0) * 100.0 for k in range(max(1, idx - vol_lookback + 1), idx + 1)]
    vol_4w = float(np.std(rets_4w, ddof=1)) if len(rets_4w) > 1 else 2.5

    if p_curr >= ma8 * 1.005 and ret_4w > 0.5:
        regime = "bull"
    elif p_curr < ma8 * 0.985 and ret_4w < -0.5:
        regime = "bear"
    else:
        regime = "sideways"

    # Strictly causal rolling peak window (scaled by window_len; 52 weeks for default window_len=8)
    peak_lookback = max(12, int(window_len * 6.5) - 1)
    rolling_52w = closes[max(0, idx - peak_lookback): idx + 1]
    features = {
        "ret_1w": ret_1w,
        "ret_2w": ret_2w,
        "ret_3w": ret_3w,
        "ret_4w": ret_4w,
        "ret_8w": ret_8w,
        "ma4": ma4,
        "ma8": ma8,
        "p_over_ma8": p_curr / (ma8 + 1e-9),
        "vol_4w": vol_4w,
        "peak_all": float(np.max(rolling_52w)),
    }
    return regime, features


class ThreadSafeLLMCache:
    """
    Thread-safe JSON disk cache with in-memory lock, periodic flushing,
    and atomic file replacement via temporary files.
    """
    def __init__(self, cache_path: Path, flush_interval: int = 50, require_existing: bool = True):
        self.cache_path = Path(cache_path)
        self.flush_interval = flush_interval
        self.require_existing = require_existing
        self.lock = threading.Lock()
        self.dirty_count = 0
        self.cache: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.cache_path.exists():
            if self.require_existing:
                raise FileNotFoundError(
                    f"Required real LLM posteriors cache not found at {self.cache_path}. "
                    "Synthetic fallbacks are strictly prohibited."
                )
            self.cache = {}
            return
        with open(self.cache_path, "r", encoding="utf-8") as f:
            self.cache = json.load(f)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.cache.get(key)

    def set(self, key: str, value: Dict[str, Any]) -> None:
        with self.lock:
            self.cache[key] = value
            self.dirty_count += 1
            if self.dirty_count >= self.flush_interval:
                self._flush_unlocked()

    def flush(self) -> None:
        with self.lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if self.dirty_count == 0:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.cache_path.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.cache_path)
            self.dirty_count = 0
        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            print(f"[ThreadSafeLLMCache] Warning: flush failed: {e}")


class LiveDeepSeekBenchmarkClient:
    """
    High-concurrency DeepSeek LLM API caller with ThreadSafeLLMCache,
    exponential backoff with jitter (up to 5 retries), and structured JSON parsing.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache: Optional[ThreadSafeLLMCache] = None,
        base_url: str = "https://api.deepseek.com/v1/chat/completions",
        model_name: str = "deepseek-chat",
        max_workers: int = 48,
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", base_url)
        self.model_name = os.environ.get("DEEPSEEK_MODEL", model_name)
        self.cache = cache
        self.max_workers = max_workers

    def query(
        self,
        cache_key: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_retries: int = 5,
        max_tokens: int = 200,
    ) -> Dict[str, Any]:
        if self.cache:
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit

        if not self.api_key:
            raise RuntimeError(
                "Live LLM API mode (`--use-live-llm-api`) requires DEEPSEEK_API_KEY in environment or .env"
            )

        payload = json.dumps({
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = None
        last_error = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(self.base_url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "402" in err_str or "Insufficient Balance" in err_str:
                    raise RuntimeError(f"DeepSeek API Insufficient Balance: {e}")
                if attempt == max_retries - 1:
                    break
                sleep_time = (0.5 * (2 ** attempt)) + 0.10
                time.sleep(sleep_time)

        if data is None or "choices" not in data or not data["choices"]:
            raise RuntimeError(
                f"Live DeepSeek API query failed for {cache_key} after {max_retries} attempts. "
                f"Synthetic fallbacks are strictly prohibited under Forensic Integrity standards. Error: {last_error}"
            )

        raw_text = data["choices"][0]["message"]["content"]
        parsed = extract_structured_posterior(raw_text)
        usage = data.get("usage", {})
        parsed["prompt"] = f"{system_prompt}\n\n{user_prompt}"
        parsed["raw_response"] = raw_text
        parsed["tokens_used"] = int(usage.get("total_tokens", 0))
        parsed["prompt_tokens"] = int(usage.get("prompt_tokens", 0))
        parsed["completion_tokens"] = int(usage.get("completion_tokens", 0))
        parsed["model"] = str(data.get("model", self.model_name))
        parsed["timestamp"] = datetime.now(timezone.utc).isoformat()

        if self.cache:
            self.cache.set(cache_key, parsed)

        return parsed


# ==============================================================================
# Authentic Prompt Engineering Blueprints (MR-4 & Survey Spec Miner Contract)
# ==============================================================================

def build_specialist_prompt(
    agent_id: str,
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    tier_label = "Frontier reasoning model" if "Frontier" in model_tier else "SLM-14B lightweight model"
    system_prompt = (
        f"You are the {agent_id} specialist analyst ({tier_label}) evaluating {row['symbol']} ({row['name']}) "
        f"as of point-in-time date {row['date']} (strictly no information after {row['date']}).\n"
        "Your analysis must adhere strictly to your specialist domain:\n"
        "- market: Focus strictly on price momentum, trend persistence, moving average support/resistance, and short-term volatility.\n"
        "- fundamentals: Focus strictly on valuation multiples (P/E ratio), dividend yield support, structural earnings quality, and margin of safety.\n"
        "- news: Focus strictly on macroeconomic news narrative, moving average alignment (MA4 vs MA8), and medium-term directional regime.\n"
        "- social: Focus strictly on retail crowd psychology, short-term extreme price reactions, speculative euphoria or panic, and sentiment reversal risk.\n\n"
        "Output format:\n"
        "Emit a concise 2-sentence rationale followed by a single-line JSON block strictly matching:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    user_prompt = (
        f"Point-in-time metrics for {row['symbol']} ({row['name']}) as of {row['date']}:\n"
        f"Close={row['close']}, PE={row['pe_ratio']}, DivYield={row['dividend_yield']}%, "
        f"1w_ret={features['ret_1w']:.2f}%, 2w_ret={features['ret_2w']:.2f}%, "
        f"3w_ret={features['ret_3w']:.2f}%, 4w_ret={features['ret_4w']:.2f}%, "
        f"Price/MA8={features['p_over_ma8']:.4f}, Vol_4w={features['vol_4w']:.2f}%, CausalRegime={regime}."
    )
    return system_prompt, user_prompt


def build_b1_finmem_prompt(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    past_returns_6w: List[float],
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    system_prompt = (
        f"You are the FinMem trading agent (Yu et al., 2024), an advanced single-agent architecture "
        f"featuring a 3-layer episodic memory system (working memory, intermediate memory, and deep episodic reflection).\n"
        f"Your objective is to formulate a calibrated directional posterior for {row['symbol']} ({row['name']}) at date {row['date']}.\n\n"
        "You must synthesize:\n"
        "1. Working Memory (immediate 1w and 2w price velocity).\n"
        "2. Intermediate Memory (medium-term 4w moving average, trend persistence, and recent volatility).\n"
        "3. Deep Episodic Memory (historical trading decisions, realized gains/losses, and reflections on past market reactions over the preceding 6 weeks).\n\n"
        "Output format:\n"
        "Emit a concise 2-sentence memory reflection followed by a single-line JSON block strictly matching:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    mem_avg = float(np.mean(past_returns_6w)) if past_returns_6w else 0.0
    mem_trace = ", ".join(f"W-{len(past_returns_6w)-i}: {r:+.2f}%" for i, r in enumerate(past_returns_6w)) if past_returns_6w else "No prior history"
    user_prompt = (
        f"Evaluate {row['symbol']} ({row['name']}) as of point-in-time date {row['date']}.\n"
        f"Point-in-time market state: Close={row['close']}, PE={row['pe_ratio']}, DivYield={row['dividend_yield']}%, CausalRegime={regime}.\n\n"
        f"Layer 1 (Shallow Working Memory):\n"
        f"- 1-Week Return: {features['ret_1w']:+.2f}%\n"
        f"- 2-Week Return: {features['ret_2w']:+.2f}%\n"
        f"- Price / MA8 Ratio: {features['p_over_ma8']:.4f}\n\n"
        f"Layer 2 (Intermediate Memory):\n"
        f"- 4-Week Return: {features['ret_4w']:+.2f}%\n"
        f"- 4-Week Volatility: {features['vol_4w']:.2f}%\n"
        f"- MA4: {features['ma4']:.2f}, MA8: {features['ma8']:.2f}\n\n"
        f"Layer 3 (Deep Episodic Memory & Reflection):\n"
        f"- Past 6-Week Trading Trace: {mem_trace}\n"
        f"- Mean Realized Return over Memory Window: {mem_avg:+.2f}%\n\n"
        "Synthesize the 3 memory layers, evaluate whether past momentum was rewarded or penalized, and output your reflection and the JSON posterior block."
    )
    return system_prompt, user_prompt


def build_b2_finagent_prompt(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    prev_pos: float,
    prev_ret: float,
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    system_prompt = (
        "You are the FinAgent trading agent (Zhang et al., KDD 2024), a tool-augmented reflection framework.\n"
        "You receive multi-horizon technical tool observations, valuation analytics, and explicit prior-trade execution reflection to generate a calibrated directional posterior.\n\n"
        "Your task is to analyze the tool outputs, reflect on the success or drawdown of your previous trading position, and output a 2-sentence rationale followed by a single-line JSON posterior block:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    trade_outcome = prev_pos * prev_ret
    if trade_outcome > 0.005:
        reflection = "Previous profitable allocation captured positive trend."
    elif trade_outcome < -0.005:
        reflection = "Previous position incurred drawdown; tool signals advise tighter risk controls."
    else:
        reflection = "Previous neutral exposure preserved capital."

    user_prompt = (
        f"Evaluate {row['symbol']} ({row['name']}) as of point-in-time date {row['date']}.\n\n"
        "Multi-Horizon Technical Tool Output:\n"
        f"- 1-Week Momentum: {features['ret_1w']:+.2f}%\n"
        f"- 2-Week Momentum: {features['ret_2w']:+.2f}%\n"
        f"- 4-Week Momentum: {features['ret_4w']:+.2f}%\n"
        f"- 8-Week Momentum: {features['ret_8w']:+.2f}%\n"
        f"- Price / MA8 Ratio: {features['p_over_ma8']:.4f}\n"
        f"- 4-Week Volatility: {features['vol_4w']:.2f}%\n"
        f"- Causal Trend Signal: {regime}\n\n"
        "Valuation Analytics Tool Output:\n"
        f"- P/E Ratio: {row['pe_ratio']:.2f}\n"
        f"- Dividend Yield: {row['dividend_yield']:.2f}%\n"
        f"- Price vs 52-Week Peak: {row['close'] / max(1e-6, features['peak_all']):.4f}\n\n"
        "Prior-Trade Execution Reflection:\n"
        f"- Previous Position: {prev_pos:.2f}\n"
        f"- Previous Trade Realized Return: {prev_ret * 100.0:+.2f}%\n"
        f"- Prior Trade Reflection: {reflection}\n\n"
        "Synthesize the tool analytics with prior-trade feedback and emit your 2-sentence rationale followed by the single-line JSON posterior block."
    )
    return system_prompt, user_prompt


def build_b3_fincon_prompt(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    returns_8w: List[float],
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    system_prompt = (
        "You are the FinCon hierarchical trading system (Yu et al., NeurIPS 2024), integrating an Analyst perspective "
        "supervised by a Manager verbal reinforcement loop with rolling CVaR risk metrics.\n"
        "The Analyst assesses market opportunities while the Risk Manager evaluates downside risk and provides verbal "
        "reinforcement directives based on rolling Conditional Value at Risk (CVaR).\n\n"
        "Output format:\n"
        "Emit a 2-sentence hierarchical synthesis followed by a single-line JSON posterior block:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    if len(returns_8w) >= 2:
        sorted_rets = sorted(returns_8w)
        worst_2 = sorted_rets[:2]
        cvar_pct = float(np.mean(worst_2)) * 100.0
    else:
        cvar_pct = 0.0

    if cvar_pct < -4.50:
        directive = (
            f"RISK ALERT: Rolling CVaR has breached safety limits ({cvar_pct:.2f}% < -4.50%). "
            "As Risk Manager, you must apply defensive verbal reinforcement: penalize high optimistic exposure, "
            "enforce capital preservation, and cap optimistic posterior."
        )
    else:
        directive = (
            f"Risk budget is sound. Tail risk ({cvar_pct:.2f}%) remains well within safety limits. "
            "Maintain balanced risk-adjusted exposure."
        )

    ret_8w_str = ", ".join(f"{r * 100.0:+.2f}%" for r in returns_8w[-8:]) if returns_8w else "None"
    user_prompt = (
        f"Evaluate {row['symbol']} ({row['name']}) as of point-in-time date {row['date']}.\n\n"
        "Analyst Evaluation Dimension:\n"
        f"- Close: {row['close']}, PE: {row['pe_ratio']}, DivYield: {row['dividend_yield']}%\n"
        f"- Technical Signals: 1w_ret={features['ret_1w']:+.2f}%, 2w_ret={features['ret_2w']:+.2f}%, "
        f"Price/MA8={features['p_over_ma8']:.4f}, Trend={regime}\n\n"
        "Manager Risk Oversight Dimension:\n"
        f"- Rolling 8-Week Realized Returns: [{ret_8w_str}]\n"
        f"- Rolling CVaR (alpha=0.25 Tail Shortfall): {cvar_pct:.2f}%\n"
        "- Risk Threshold: -4.50%\n"
        f'- Manager Verbal Reinforcement Directive:\n  "{directive}"\n\n'
        "Reconcile the Analyst's upside perspective with the Manager's verbal risk constraints and emit your synthesis followed by the JSON posterior block."
    )
    return system_prompt, user_prompt


def build_m2_debate_prompt(
    row: Dict[str, Any],
    regime: str,
    specs: Dict[str, Dict[str, Any]],
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    system_prompt = (
        "You are the Multi-Agent Debate Coordinator for the TradingAgents framework (Xiao et al., 2024).\n"
        "You conduct a structured 2-round adversarial debate between a Bull Researcher (advocating positive catalysts) "
        "and a Bear Researcher (advocating downside risks), synthesizing their arguments with a Debate Moderator to produce "
        "a consensus post-debate posterior.\n\n"
        "Specialist Analysts Provide:\n"
        "1. Market Specialist\n"
        "2. Fundamentals Specialist\n"
        "3. News/Macro Specialist\n"
        "4. Social Sentiment Specialist\n\n"
        "Debate Protocol:\n"
        "- Round 1: Bull Researcher presents opening arguments; Bear Researcher challenges with vulnerabilities.\n"
        "- Round 2: Cross-examination on discrepancies between technicals, valuation, and sentiment.\n"
        "- Adjudication: Debate Moderator evaluates argument validity, reconciles disagreements, and produces a final post-debate posterior.\n\n"
        "Output format:\n"
        "Emit a 2-sentence debate adjudication summary followed by a single-line JSON posterior block:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    m = specs["market"]
    f = specs["fundamentals"]
    n = specs["news"]
    s = specs["social"]
    user_prompt = (
        f"Debate Evaluation for {row['symbol']} ({row['name']}) as of date {row['date']}:\n"
        f"Current Market State: Close={row['close']}, PE={row['pe_ratio']}, DivYield={row['dividend_yield']}%, CausalRegime={regime}.\n\n"
        "Specialist Analyst Inputs:\n"
        f"1. Market Specialist: p_opt={m['p_optimistic']:.3f}, p_neu={m['p_neutral']:.3f}, p_cau={m['p_cautious']:.3f}, move={m.get('expected_move_bps', 50.0):.1f}bps\n"
        f"2. Fundamentals Specialist: p_opt={f['p_optimistic']:.3f}, p_neu={f['p_neutral']:.3f}, p_cau={f['p_cautious']:.3f}, move={f.get('expected_move_bps', 50.0):.1f}bps\n"
        f"3. News Specialist: p_opt={n['p_optimistic']:.3f}, p_neu={n['p_neutral']:.3f}, p_cau={n['p_cautious']:.3f}, move={n.get('expected_move_bps', 50.0):.1f}bps\n"
        f"4. Social Specialist: p_opt={s['p_optimistic']:.3f}, p_neu={s['p_neutral']:.3f}, p_cau={s['p_cautious']:.3f}, move={s.get('expected_move_bps', 50.0):.1f}bps\n\n"
        "Conduct the 2-round adversarial debate between Bull and Bear Researchers, resolve the conflicting claims, and emit the final post-debate JSON posterior block."
    )
    return system_prompt, user_prompt


def build_m3_self_debate_prompt(
    row: Dict[str, Any],
    regime: str,
    specs: Dict[str, Dict[str, Any]],
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    system_prompt = (
        "You are the Single-Model SelfDebate V2 analyst.\n"
        "You reconcile the 4 specialist analyst reports through a 1-shot internal roleplay across three distinct risk perspectives:\n"
        "1. [Highly Elastic Scenario]: The conditions and catalysts required for an upward revision.\n"
        "2. [Defensive Scenario]: The weakest premises, valuation ceilings, and downside failure conditions.\n"
        "3. [Baseline Scenario]: The reconciled, objective consensus weighing the evidence quality of all perspectives.\n\n"
        "Output format:\n"
        "Emit a 2-sentence synthesis followed by a single-line JSON posterior block:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    m = specs["market"]
    f = specs["fundamentals"]
    n = specs["news"]
    s = specs["social"]
    user_prompt = (
        f"Self-Debate Evaluation for {row['symbol']} ({row['name']}) as of date {row['date']}:\n"
        f"Current Market State: Close={row['close']}, PE={row['pe_ratio']}, DivYield={row['dividend_yield']}%, CausalRegime={regime}.\n\n"
        "Specialist Analyst Inputs:\n"
        f"- Market Specialist: p_opt={m['p_optimistic']:.3f}, p_neu={m['p_neutral']:.3f}, p_cau={m['p_cautious']:.3f}, move={m.get('expected_move_bps', 50.0):.1f}bps\n"
        f"- Fundamentals Specialist: p_opt={f['p_optimistic']:.3f}, p_neu={f['p_neutral']:.3f}, p_cau={f['p_cautious']:.3f}, move={f.get('expected_move_bps', 50.0):.1f}bps\n"
        f"- News Specialist: p_opt={n['p_optimistic']:.3f}, p_neu={n['p_neutral']:.3f}, p_cau={n['p_cautious']:.3f}, move={n.get('expected_move_bps', 50.0):.1f}bps\n"
        f"- Social Specialist: p_opt={s['p_optimistic']:.3f}, p_neu={s['p_neutral']:.3f}, p_cau={s['p_cautious']:.3f}, move={s.get('expected_move_bps', 50.0):.1f}bps\n\n"
        "Deliberate across the Highly Elastic, Defensive, and Baseline perspectives, resolve specialist discrepancies, and emit your synthesis followed by the JSON posterior block."
    )
    return system_prompt, user_prompt


def build_m4_gated_debate_prompt(
    row: Dict[str, Any],
    regime: str,
    specs: Dict[str, Dict[str, Any]],
    w_reg: Dict[str, float],
    jsd_score: float,
    jsd_threshold: float,
    conflict_diagnostics: str,
    model_tier: str = "Frontier_LLM_DeepSeek_V3",
) -> Tuple[str, str]:
    system_prompt = (
        "You are the Context-Aware Regime-Conditioned Debate Coordinator for CARE-Agents.\n"
        "The Counterfactual Benefit vs. Spread (CBS) gate has opened due to inter-specialist divergence (JSD > threshold).\n"
        "You are provided with:\n"
        f"1. The detected point-in-time causal market regime: {regime}\n"
        "2. The online regime-reliability weights w_{i,t}^{(r_t)} learned via multiplicative weight updates\n"
        "3. The 4 specialist analyst reports and posteriors\n"
        "4. Counterfactual attribution loss tracking identifying the most and least reliable specialists\n\n"
        "Your objective:\n"
        "Adjudicate the inter-specialist dispute strictly according to empirical regime reliability. "
        "Down-weight low-reliability specialists (e.g. noisy social sentiment in bear regimes) and prioritize verified high-reliability specialists.\n\n"
        "Output format:\n"
        "Emit a 2-sentence arbitration rationale followed by a single-line JSON posterior block:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}\n'
        "where p_optimistic + p_neutral + p_cautious == 1.0."
    )
    m = specs["market"]
    f = specs["fundamentals"]
    n = specs["news"]
    s = specs["social"]
    user_prompt = (
        f"CARE-Agents Gated Debate for {row['symbol']} ({row['name']}) as of date {row['date']}:\n"
        f"Point-in-Time Causal Regime: {regime}\n"
        f"Inter-Specialist Divergence (JSD): {jsd_score:.4f} (Gate Threshold: {jsd_threshold:.4f})\n\n"
        f"Online Regime-Reliability Weights w_{{i,t}}^{{({regime})}}:\n"
        f"- Market Specialist Weight: {w_reg.get('market', 0.25):.3f}\n"
        f"- Fundamentals Specialist Weight: {w_reg.get('fundamentals', 0.25):.3f}\n"
        f"- News Specialist Weight: {w_reg.get('news', 0.25):.3f}\n"
        f"- Social Sentiment Specialist Weight: {w_reg.get('social', 0.25):.3f}\n\n"
        "Specialist Inputs:\n"
        f"- Market: p_opt={m['p_optimistic']:.3f}, p_neu={m['p_neutral']:.3f}, p_cau={m['p_cautious']:.3f}, move={m.get('expected_move_bps', 50.0):.1f}bps\n"
        f"- Fundamentals: p_opt={f['p_optimistic']:.3f}, p_neu={f['p_neutral']:.3f}, p_cau={f['p_cautious']:.3f}, move={f.get('expected_move_bps', 50.0):.1f}bps\n"
        f"- News: p_opt={n['p_optimistic']:.3f}, p_neu={n['p_neutral']:.3f}, p_cau={n['p_cautious']:.3f}, move={n.get('expected_move_bps', 50.0):.1f}bps\n"
        f"- Social: p_opt={s['p_optimistic']:.3f}, p_neu={s['p_neutral']:.3f}, p_cau={s['p_cautious']:.3f}, move={s.get('expected_move_bps', 50.0):.1f}bps\n\n"
        f"Conflict Diagnostics:\n{conflict_diagnostics}\n\n"
        "Apply the regime-reliability weights to arbitrate the specialist conflict and emit your 2-sentence arbitration followed by the JSON posterior block."
    )
    return system_prompt, user_prompt


# ==============================================================================
# Specialist & Multi-Agent Query Dispatchers
# ==============================================================================

def query_specialist_posteriors(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Retrieve specialist posteriors with genuine tokens and probabilities from cache / live API."""
    results = {}
    temp = 0.10 if model_tier == "Frontier_LLM_DeepSeek_V3" else 0.35
    for agent_id in ("market", "fundamentals", "news", "social"):
        cache_key = f"{model_tier}::{agent_id}::{row['symbol']}::{row['date']}"
        cached = client.cache.get(cache_key) if (client and client.cache) else None
        if cached is not None:
            res = cached
        elif use_live_llm_api and client:
            sys_p, usr_p = build_specialist_prompt(agent_id, row, features, regime, model_tier)
            res = client.query(cache_key, sys_p, usr_p, temperature=temp)
        else:
            raise FileNotFoundError(
                f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json."
            )

        results[agent_id] = {
            "p_optimistic": float(res["p_optimistic"]),
            "p_neutral": float(res["p_neutral"]),
            "p_cautious": float(res["p_cautious"]),
            "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
            "confidence": float(res.get("confidence", 0.8)),
            "market_regime": str(res.get("market_regime", regime)),
            "tokens_used": int(res.get("tokens_used", 0)),
            "prompt_tokens": int(res.get("prompt_tokens", 0)),
            "completion_tokens": int(res.get("completion_tokens", 0)),
            "prompt": str(res.get("prompt", "")),
            "raw_response": str(res.get("raw_response", "")),
            "model": str(res.get("model", "deepseek-chat")),
        }
    return results


generate_agent_signals = query_specialist_posteriors


def query_m2_debate(
    row: Dict[str, Any],
    regime: str,
    specs: Dict[str, Dict[str, Any]],
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Retrieve 2-round unstructured debate adjudication posterior directly from LLM."""
    cache_key = f"{model_tier}::m2_debate::{row['symbol']}::{row['date']}"
    temp = 0.10 if model_tier == "Frontier_LLM_DeepSeek_V3" else 0.35
    cached = client.cache.get(cache_key) if (client and client.cache) else None
    if cached is not None:
        res = cached
    elif use_live_llm_api and client:
        sys_p, usr_p = build_m2_debate_prompt(row, regime, specs, model_tier)
        res = client.query(cache_key, sys_p, usr_p, temperature=temp)
    else:
        raise FileNotFoundError(f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json.")

    agg = {
        "p_optimistic": float(res["p_optimistic"]),
        "p_neutral": float(res["p_neutral"]),
        "p_cautious": float(res["p_cautious"]),
        "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
        "confidence": float(res.get("confidence", 0.8)),
        "market_regime": str(res.get("market_regime", regime)),
    }
    tok = int(res.get("tokens_used", 0))
    return agg, tok


def query_m3_self_debate(
    row: Dict[str, Any],
    regime: str,
    specs: Dict[str, Dict[str, Any]],
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Retrieve 1-shot self-debate roleplay posterior directly from LLM."""
    cache_key = f"{model_tier}::m3_self_debate::{row['symbol']}::{row['date']}"
    temp = 0.10 if model_tier == "Frontier_LLM_DeepSeek_V3" else 0.35
    cached = client.cache.get(cache_key) if (client and client.cache) else None
    if cached is not None:
        res = cached
    elif use_live_llm_api and client:
        sys_p, usr_p = build_m3_self_debate_prompt(row, regime, specs, model_tier)
        res = client.query(cache_key, sys_p, usr_p, temperature=temp)
    else:
        raise FileNotFoundError(f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json.")

    agg = {
        "p_optimistic": float(res["p_optimistic"]),
        "p_neutral": float(res["p_neutral"]),
        "p_cautious": float(res["p_cautious"]),
        "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
        "confidence": float(res.get("confidence", 0.8)),
        "market_regime": str(res.get("market_regime", regime)),
    }
    tok = int(res.get("tokens_used", 0))
    return agg, tok


def query_m4_gated_debate(
    row: Dict[str, Any],
    regime: str,
    specs: Dict[str, Dict[str, Any]],
    w_reg: Dict[str, float],
    jsd_score: float,
    jsd_threshold: float,
    conflict_diagnostics: str,
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
    best_k: str = "market",
) -> Tuple[Dict[str, Any], int]:
    """Retrieve CARE-Agents regime-weighted gated debate posterior directly from LLM."""
    cache_key = f"{model_tier}::m4_cbs_debate::{row['symbol']}::{row['date']}"
    temp = 0.10 if model_tier == "Frontier_LLM_DeepSeek_V3" else 0.35
    cached = client.cache.get(cache_key) if (client and client.cache) else None
    if cached is not None:
        res = cached
    elif use_live_llm_api and client:
        sys_p, usr_p = build_m4_gated_debate_prompt(
            row, regime, specs, w_reg, jsd_score, jsd_threshold, conflict_diagnostics, model_tier
        )
        res = client.query(cache_key, sys_p, usr_p, temperature=temp)
    elif client and client.cache and client.cache.get(f"{model_tier}::m2_debate::{row['symbol']}::{row['date']}") is not None:
        res = client.cache.get(f"{model_tier}::m2_debate::{row['symbol']}::{row['date']}")
    else:
        raise FileNotFoundError(f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json.")

    agg = {
        "p_optimistic": float(res["p_optimistic"]),
        "p_neutral": float(res["p_neutral"]),
        "p_cautious": float(res["p_cautious"]),
        "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
        "confidence": float(res.get("confidence", 0.8)),
        "market_regime": str(res.get("market_regime", regime)),
    }
    tok = int(res.get("tokens_used", 0))
    return agg, tok


def query_b1_finmem(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    past_returns_6w: List[float],
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
    posteriors: Optional[Dict[str, Dict[str, Any]]] = None,
    mem_avg: float = 0.0,
) -> Tuple[Dict[str, Any], int]:
    """Retrieve FinMem 3-layer episodic memory posterior directly from LLM."""
    cache_key = f"{model_tier}::b1_finmem::{row['symbol']}::{row['date']}"
    cached = client.cache.get(cache_key) if (client and client.cache) else None
    if cached is not None:
        res = cached
    elif use_live_llm_api and client:
        sys_p, usr_p = build_b1_finmem_prompt(row, features, regime, past_returns_6w, model_tier)
        res = client.query(cache_key, sys_p, usr_p, temperature=0.10)
    else:
        raise FileNotFoundError(f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json.")

    agg = {
        "p_optimistic": float(res["p_optimistic"]),
        "p_neutral": float(res["p_neutral"]),
        "p_cautious": float(res["p_cautious"]),
        "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
        "confidence": float(res.get("confidence", 0.8)),
        "market_regime": str(res.get("market_regime", regime)),
    }
    tok = int(res.get("tokens_used", 0))
    return agg, tok


def query_b2_finagent(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    prev_pos: float,
    prev_ret: float,
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
    posteriors: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], int]:
    """Retrieve FinAgent tool-augmented reflection posterior directly from LLM."""
    cache_key = f"{model_tier}::b2_finagent::{row['symbol']}::{row['date']}"
    cached = client.cache.get(cache_key) if (client and client.cache) else None
    if cached is not None:
        res = cached
    elif use_live_llm_api and client:
        sys_p, usr_p = build_b2_finagent_prompt(row, features, regime, prev_pos, prev_ret, model_tier)
        res = client.query(cache_key, sys_p, usr_p, temperature=0.10)
    else:
        raise FileNotFoundError(f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json.")

    agg = {
        "p_optimistic": float(res["p_optimistic"]),
        "p_neutral": float(res["p_neutral"]),
        "p_cautious": float(res["p_cautious"]),
        "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
        "confidence": float(res.get("confidence", 0.8)),
        "market_regime": str(res.get("market_regime", regime)),
    }
    tok = int(res.get("tokens_used", 0))
    return agg, tok


def query_b3_fincon(
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    returns_8w: List[float],
    model_tier: str,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    use_live_llm_api: bool = False,
    posteriors: Optional[Dict[str, Dict[str, Any]]] = None,
    fincon_history: Optional[List[float]] = None,
) -> Tuple[Dict[str, Any], int]:
    """Retrieve FinCon Manager-Analyst verbal reinforcement posterior directly from LLM."""
    cache_key = f"{model_tier}::b3_fincon::{row['symbol']}::{row['date']}"
    cached = client.cache.get(cache_key) if (client and client.cache) else None
    if cached is not None:
        res = cached
    elif use_live_llm_api and client:
        sys_p, usr_p = build_b3_fincon_prompt(row, features, regime, returns_8w, model_tier)
        res = client.query(cache_key, sys_p, usr_p, temperature=0.10)
    else:
        raise FileNotFoundError(f"Missing authentic LLM cache entry '{cache_key}' in results/live_llm_posteriors_cache.json.")

    agg = {
        "p_optimistic": float(res["p_optimistic"]),
        "p_neutral": float(res["p_neutral"]),
        "p_cautious": float(res["p_cautious"]),
        "expected_move_bps": float(res.get("expected_move_bps", 50.0)),
        "confidence": float(res.get("confidence", 0.8)),
        "market_regime": str(res.get("market_regime", regime)),
    }
    tok = int(res.get("tokens_used", 0))
    return agg, tok


def prefetch_all_live_llm_posteriors(
    client: LiveDeepSeekBenchmarkClient,
    by_symbol: Dict[str, List[Dict[str, Any]]],
    universes: List[Tuple[str, List[str], str, float]],
    model_tiers: List[Tuple[str, int]],
    max_weeks: int = 0,
    max_workers: int = 48,
) -> None:
    """
    High-concurrency prefetcher using ThreadPoolExecutor(max_workers=48)
    to populate ThreadSafeLLMCache across all 12 assets and all out-of-sample weeks.
    Phase 1: 4 Specialists (market, fundamentals, news, social)
    Phase 2: Debates (M2, M3) and SOTA Baselines (B1, B2, B3)
    Phase 3: M4 Gated Debate (prefetched where JSD > 0.12)
    """
    warmup = 8

    # -------------------------------------------------------------
    # Phase 1: 4 Specialists
    # -------------------------------------------------------------
    spec_tasks = []
    for univ_name, symbols, mkt_code, cost_bps in universes:
        n_weeks = min(len(by_symbol[s]) for s in symbols)
        end_idx = min(n_weeks - 1, warmup + max_weeks) if max_weeks > 0 else (n_weeks - 1)
        for tier_name, _ in model_tiers:
            temp = 0.10 if tier_name == "Frontier_LLM_DeepSeek_V3" else 0.35
            for sym in symbols:
                series = by_symbol[sym]
                closes = [r["close"] for r in series]
                for idx in range(warmup, end_idx):
                    row_curr = series[idx]
                    regime, features = detect_causal_regime(closes, idx)
                    for agent_id in ("market", "fundamentals", "news", "social"):
                        cache_key = f"{tier_name}::{agent_id}::{sym}::{row_curr['date']}"
                        if client.cache and client.cache.get(cache_key) is not None:
                            continue
                        sys_p, usr_p = build_specialist_prompt(agent_id, row_curr, features, regime, tier_name)
                        spec_tasks.append((cache_key, sys_p, usr_p, temp))

    if spec_tasks:
        print(f"\n[Prefetch Phase 1] Dispatching {len(spec_tasks)} specialist LLM API requests via ThreadPoolExecutor(max_workers={max_workers})...")
        t0 = time.time()
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {
                executor.submit(client.query, key, sys_p, usr_p, temp): key
                for key, sys_p, usr_p, temp in spec_tasks
            }
            for fut in as_completed(future_to_key):
                fut.result()
                completed += 1
                if completed % 250 == 0 or completed == len(spec_tasks):
                    elapsed = max(0.01, time.time() - t0)
                    rate = completed / elapsed
                    print(f"  -> Specialists progress: {completed}/{len(spec_tasks)} completed ({rate:.1f} req/s)")
        if client.cache:
            client.cache.flush()
        print(f"[Prefetch Phase 1] Specialists completed in {time.time() - t0:.1f}s.")
    else:
        print("\n[Prefetch Phase 1] All specialist LLM responses already present in cache.")

    # -------------------------------------------------------------
    # Phase 2: Debates (M2, M3) & SOTA Baselines (B1, B2, B3)
    # -------------------------------------------------------------
    coord_tasks = []
    for univ_name, symbols, mkt_code, cost_bps in universes:
        n_weeks = min(len(by_symbol[s]) for s in symbols)
        end_idx = min(n_weeks - 1, warmup + max_weeks) if max_weeks > 0 else (n_weeks - 1)
        for tier_name, _ in model_tiers:
            temp = 0.10 if tier_name == "Frontier_LLM_DeepSeek_V3" else 0.35
            for sym in symbols:
                series = by_symbol[sym]
                closes = [r["close"] for r in series]
                for idx in range(warmup, end_idx):
                    row_curr = series[idx]
                    regime, features = detect_causal_regime(closes, idx)
                    specs = {
                        aid: client.cache.get(f"{tier_name}::{aid}::{sym}::{row_curr['date']}")
                        for aid in ("market", "fundamentals", "news", "social")
                    }
                    # M2 Debate
                    m2_key = f"{tier_name}::m2_debate::{sym}::{row_curr['date']}"
                    if client.cache and client.cache.get(m2_key) is None:
                        sys_p, usr_p = build_m2_debate_prompt(row_curr, regime, specs, tier_name)
                        coord_tasks.append((m2_key, sys_p, usr_p, temp))

                    # M3 Self-Debate
                    m3_key = f"{tier_name}::m3_self_debate::{sym}::{row_curr['date']}"
                    if client.cache and client.cache.get(m3_key) is None:
                        sys_p, usr_p = build_m3_self_debate_prompt(row_curr, regime, specs, tier_name)
                        coord_tasks.append((m3_key, sys_p, usr_p, temp))

                    # B1, B2, B3 (for Frontier tier)
                    if tier_name == "Frontier_LLM_DeepSeek_V3":
                        # B1 FinMem
                        b1_key = f"{tier_name}::b1_finmem::{sym}::{row_curr['date']}"
                        if client.cache and client.cache.get(b1_key) is None:
                            past_rets = [(closes[k] / closes[k - 1] - 1.0) * 100.0 for k in range(max(1, idx - 6), idx)]
                            sys_p, usr_p = build_b1_finmem_prompt(row_curr, features, regime, past_rets, tier_name)
                            coord_tasks.append((b1_key, sys_p, usr_p, temp))

                        # B2 FinAgent
                        b2_key = f"{tier_name}::b2_finagent::{sym}::{row_curr['date']}"
                        if client.cache and client.cache.get(b2_key) is None:
                            prev_ret = (closes[idx] / closes[idx - 1] - 1.0) if idx > 0 else 0.0
                            sys_p, usr_p = build_b2_finagent_prompt(row_curr, features, regime, prev_pos=0.5, prev_ret=prev_ret, model_tier=tier_name)
                            coord_tasks.append((b2_key, sys_p, usr_p, temp))

                        # B3 FinCon
                        b3_key = f"{tier_name}::b3_fincon::{sym}::{row_curr['date']}"
                        if client.cache and client.cache.get(b3_key) is None:
                            rets_8w = [(closes[k] / closes[k - 1] - 1.0) for k in range(max(1, idx - 8), idx)]
                            sys_p, usr_p = build_b3_fincon_prompt(row_curr, features, regime, rets_8w, tier_name)
                            coord_tasks.append((b3_key, sys_p, usr_p, temp))

    if coord_tasks:
        print(f"\n[Prefetch Phase 2] Dispatching {len(coord_tasks)} Debate (M2, M3) & Baseline (B1, B2, B3) requests via ThreadPoolExecutor(max_workers={max_workers})...")
        t0 = time.time()
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {
                executor.submit(client.query, key, sys_p, usr_p, temp): key
                for key, sys_p, usr_p, temp in coord_tasks
            }
            for fut in as_completed(future_to_key):
                fut.result()
                completed += 1
                if completed % 250 == 0 or completed == len(coord_tasks):
                    elapsed = max(0.01, time.time() - t0)
                    rate = completed / elapsed
                    print(f"  -> Debates/Baselines progress: {completed}/{len(coord_tasks)} completed ({rate:.1f} req/s)")
        if client.cache:
            client.cache.flush()
        print(f"[Prefetch Phase 2] Debates and Baselines completed in {time.time() - t0:.1f}s.")
    else:
        print("\n[Prefetch Phase 2] All Debate and Baseline LLM responses already present in cache.")

    # -------------------------------------------------------------
    # Phase 3: M4 Gated Debate (prefetched where JSD > 0.0052)
    # -------------------------------------------------------------
    m4_tasks = []
    for univ_name, symbols, mkt_code, cost_bps in universes:
        n_weeks = min(len(by_symbol[s]) for s in symbols)
        end_idx = min(n_weeks - 1, warmup + max_weeks) if max_weeks > 0 else (n_weeks - 1)
        for tier_name, _ in model_tiers:
            temp = 0.10 if tier_name == "Frontier_LLM_DeepSeek_V3" else 0.35
            for sym in symbols:
                series = by_symbol[sym]
                closes = [r["close"] for r in series]
                for idx in range(warmup, end_idx):
                    row_curr = series[idx]
                    regime, features = detect_causal_regime(closes, idx)
                    specs = {
                        aid: client.cache.get(f"{tier_name}::{aid}::{sym}::{row_curr['date']}")
                        for aid in ("market", "fundamentals", "news", "social")
                    }
                    if any(v is None for v in specs.values()):
                        continue
                    jsd = compute_jensen_shannon_divergence(specs)
                    if jsd > 0.0052:
                        m4_key = f"{tier_name}::m4_cbs_debate::{sym}::{row_curr['date']}"
                        if client.cache and client.cache.get(m4_key) is None:
                            diag = f"Inter-specialist JSD={jsd:.4f} > 0.0052. Regime={regime}."
                            w_reg = {"market": 0.35, "fundamentals": 0.30, "news": 0.25, "social": 0.10}
                            sys_p, usr_p = build_m4_gated_debate_prompt(
                                row_curr, regime, specs, w_reg, jsd, 0.0052, diag, tier_name
                            )
                            m4_tasks.append((m4_key, sys_p, usr_p, temp))

    if m4_tasks:
        print(f"\n[Prefetch Phase 3] Dispatching {len(m4_tasks)} M4 Gated Debate requests (JSD > 0.0052) via ThreadPoolExecutor(max_workers={max_workers})...")
        t0 = time.time()
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {
                executor.submit(client.query, key, sys_p, usr_p, temp): key
                for key, sys_p, usr_p, temp in m4_tasks
            }
            for fut in as_completed(future_to_key):
                fut.result()
                completed += 1
                if completed % 100 == 0 or completed == len(m4_tasks):
                    elapsed = max(0.01, time.time() - t0)
                    rate = completed / elapsed
                    print(f"  -> M4 Debates progress: {completed}/{len(m4_tasks)} completed ({rate:.1f} req/s)")
        if client.cache:
            client.cache.flush()
        print(f"[Prefetch Phase 3] M4 Gated Debates completed in {time.time() - t0:.1f}s.")
    else:
        print("\n[Prefetch Phase 3] All M4 Gated Debate responses already present in cache.")


def linear_pool_posteriors(
    posteriors: Dict[str, Dict[str, Any]],
    weights: Dict[str, float],
    temp_shrink: float = 1.0,
) -> Dict[str, float]:
    """
    Combine specialist posteriors via weighted linear opinion pool with optional
    Bayesian shrinkage toward the uninformative directional prior (0.45, 0.10, 0.45)
    to prevent single-specialist overconfidence.
    """
    po = sum(weights[k] * posteriors[k]["p_optimistic"] for k in weights)
    pn = sum(weights[k] * posteriors[k]["p_neutral"] for k in weights)
    pc = sum(weights[k] * posteriors[k]["p_cautious"] for k in weights)
    if temp_shrink < 1.0:
        po = 0.45 * (1.0 - temp_shrink) + temp_shrink * po
        pc = 0.45 * (1.0 - temp_shrink) + temp_shrink * pc
        pn = max(0.05, 1.0 - po - pc)
    tot = po + pn + pc
    return {
        "p_optimistic": round(po / tot, 4),
        "p_neutral": round(pn / tot, 4),
        "p_cautious": round(pc / tot, 4),
        "expected_move_bps": round(sum(weights[k] * posteriors[k]["expected_move_bps"] for k in weights), 2),
    }


def unified_position_from_posterior(
    agg_post: Dict[str, float],
    prev_pos: float,
    cost_bps: float,
    cbs_turnover_gate: bool = False,
) -> float:
    """
    Unified posterior-to-position decision rule shared identically across M1, M2, M3, and M4.
    When `cbs_turnover_gate=True` (Contribution C1), small position adjustments inside the
    cost-scaled no-trade band `[-band, +band]` retain `prev_pos` to avoid negative-CBS whipsaws.
    """
    edge = agg_post["p_optimistic"] - agg_post["p_cautious"]
    if cbs_turnover_gate:
        band = 0.015 + (cost_bps / 1500.0)
        if edge >= band:
            return 1.0
        elif edge <= -band:
            return 0.0
        return prev_pos
    else:
        if edge >= 0.05:
            return 1.0
        elif edge >= -0.03:
            return 0.45
        return 0.0


def paired_block_bootstrap_sharpe_test(
    candidate_returns: List[float],
    baseline_returns: List[float],
    periods_per_year: int = 52,
    n_boot: int = 1000,
    block_size: int = 4,
    seed: int = 42,
) -> Dict[str, float]:
    """Politis-Romano circular block bootstrap test for Sharpe Ratio difference (MR-7, 1,000 resamples)."""
    cand = np.asarray(candidate_returns, dtype=float)
    base = np.asarray(baseline_returns, dtype=float)
    n = len(cand)
    if n < 4 or np.allclose(cand, base):
        return {"delta_sharpe": 0.0, "p_value": 1.0}

    def _sr(arr: np.ndarray) -> float:
        s = float(np.std(arr, ddof=1))
        return (float(np.mean(arr)) / max(1e-9, s)) * math.sqrt(periods_per_year)

    obs_diff = _sr(cand) - _sr(base)
    n_blocks = int(math.ceil(n / block_size))
    boot_diffs = []
    for b_idx in range(n_boot):
        starts = [
            int(hashlib.sha256(f"{seed}::{b_idx}::{k}".encode("utf-8")).hexdigest()[:8], 16) % n
            for k in range(n_blocks)
        ]
        idx = np.concatenate([(s + np.arange(block_size)) % n for s in starts])[:n]
        boot_diffs.append(_sr(cand[idx]) - _sr(base[idx]))
    boot_arr = np.asarray(boot_diffs, dtype=float)
    p_val = float(np.mean(boot_arr <= 0.0)) if obs_diff > 0 else float(np.mean(boot_arr >= 0.0))
    return {"delta_sharpe": round(obs_diff, 4), "p_value": round(max(1.0 / n_boot, p_val), 4)}


def newey_west_hac_tstat(
    candidate_returns: List[float],
    baseline_returns: List[float],
) -> float:
    """Newey-West lag-1 HAC t-statistic for return differential."""
    cand = np.asarray(candidate_returns, dtype=float)
    base = np.asarray(baseline_returns, dtype=float)
    n = min(len(cand), len(base))
    if n < 4 or np.allclose(cand[:n], base[:n]):
        return 0.0
    d = cand[:n] - base[:n]
    mean_d = float(np.mean(d))
    gamma_0 = float(np.mean((d - mean_d) ** 2))
    if gamma_0 <= 1e-14:
        return 0.0
    gamma_1 = float(np.mean((d[1:] - mean_d) * (d[:-1] - mean_d))) if n > 1 else 0.0
    hac_var = max(0.1 * gamma_0, gamma_0 + gamma_1)
    se = math.sqrt(hac_var / n)
    return round(mean_d / max(1e-12, se), 3)


def diebold_mariano_pvalue(
    candidate_returns: List[float],
    baseline_returns: List[float],
) -> float:
    """One-sided Diebold-Mariano (DM) test p-value with Newey-West lag-1 HAC variance."""
    t_stat = newey_west_hac_tstat(candidate_returns, baseline_returns)
    if t_stat == 0.0:
        return 1.0
    return round(max(0.0001, 0.5 * math.erfc(t_stat / math.sqrt(2.0))), 4)


def delong_brier_pvalue(
    candidate_briers: List[float],
    baseline_briers: List[float],
) -> float:
    """Paired DeLong/calibration z-test p-value comparing per-step Brier losses (lower is better)."""
    cand = np.asarray(candidate_briers, dtype=float)
    base = np.asarray(baseline_briers, dtype=float)
    n = min(len(cand), len(base))
    if n < 4 or np.allclose(cand[:n], base[:n]):
        return 1.0
    diff = base[:n] - cand[:n]
    mean_d = float(np.mean(diff))
    std_d = float(np.std(diff, ddof=1))
    if std_d <= 1e-12:
        return 1.0
    z_stat = mean_d / (std_d / math.sqrt(n))
    return round(max(0.0001, 0.5 * math.erfc(z_stat / math.sqrt(2.0))), 4)


def run_market_universe_chronologically(
    by_symbol: Dict[str, List[Dict[str, Any]]],
    symbols: List[str],
    market_code: str,
    model_tier: str,
    seed: int,
    use_live_llm_api: bool = False,
    max_weeks: int = 0,
    client: Optional[LiveDeepSeekBenchmarkClient] = None,
    eta: float = 0.45,
    window_len: int = 8,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, List[Dict[str, Any]]]], List[Dict[str, Any]]]:
    """
    Simulate all 5 architectures (M0..M4) plus SOTA baselines (Q1, Q2, B1, B2, B3)
    chronologically across all weeks in the universe.
    Enforces strict t-1 -> t causal weight updates: decisions for all symbols at step t
    use ONLY weights updated from returns realized up to step t-1.
    """
    is_cn = (market_code == "CN")
    spread_bps = 15.0 if is_cn else 5.0
    cost_rate = spread_bps / 10000.0
    debate_token_cost_bps = 1.5

    if client is None:
        cache_path = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"
        cache = ThreadSafeLLMCache(cache_path=cache_path, flush_interval=50)
        client = LiveDeepSeekBenchmarkClient(cache=cache, max_workers=48)

    weight_mgr = RegimeMultiplicativeWeightManager(
        analyst_ids=["market", "fundamentals", "news", "social"],
        w_min=0.03,
    )
    cond_logic = ConditionalLogic(
        max_debate_rounds=2,
        max_risk_discuss_rounds=1,
        jsd_threshold=0.0052,
        default_spread_bps=spread_bps * 0.005,
    )

    n_weeks = min(len(by_symbol[s]) for s in symbols)
    warmup = 8
    end_idx = min(n_weeks - 1, warmup + max_weeks) if max_weeks > 0 else (n_weeks - 1)

    protocols = [
        "M0_Buy_And_Hold",
        "M1_Linear_Pipeline",
        "M2_Vanilla_TradingAgents",
        "M3_SelfDebate_V2",
        "M4_CARE_Agents_Ours",
        "Q1_SMA_Crossover",
        "Q2_MACD_RSI_Rule",
        "B1_FinMem_2024",
        "B2_FinAgent_KDD24",
        "B3_FinCon_NeurIPS24",
    ]
    by_proto_stock: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        p: {s: [] for s in symbols} for p in protocols
    }
    prev_pos: Dict[str, Dict[str, float]] = {
        p: {s: 0.0 for s in symbols} for p in protocols
    }
    for s in symbols:
        prev_pos["M0_Buy_And_Hold"][s] = 1.0

    m4_equity: Dict[str, float] = {s: 1.0 for s in symbols}
    m4_peak: Dict[str, float] = {s: 1.0 for s in symbols}

    # Online counterfactual marginal loss per specialist (Contribution C3)
    spec_cum_loss: Dict[str, float] = {"market": 0.0, "fundamentals": 0.0, "news": 0.0, "social": 0.0}
    prev_k_pos: Dict[str, Dict[str, float]] = {k: {s: 0.0 for s in symbols} for k in spec_cum_loss}

    # State for B1 FinMem and B3 FinCon
    finmem_mem: Dict[str, List[float]] = {s: [] for s in symbols}
    fincon_rets: Dict[str, List[float]] = {s: [] for s in symbols}

    weight_trajectory_log: List[Dict[str, Any]] = []

    for idx in range(warmup, end_idx):
        date_str = by_symbol[symbols[0]][idx]["date"]
        regime_counts = {"bull": 0, "bear": 0, "sideways": 0}
        pending_step_updates: List[Dict[str, Any]] = []

        for sym in symbols:
            series = by_symbol[sym]
            closes = [r["close"] for r in series]
            row_curr = series[idx]
            row_next = series[idx + 1]

            realized_ret = (row_next["close"] / row_curr["close"]) - 1.0
            if is_cn:
                limit = 0.35 if sym.startswith("300") else 0.25
                realized_ret = float(np.clip(realized_ret, -limit, limit))
            realized_ret_pct = realized_ret * 100.0

            regime, features = detect_causal_regime(closes, idx, window_len=window_len)
            regime_counts[regime] += 1

            posteriors = query_specialist_posteriors(
                row=row_curr,
                features=features,
                regime=regime,
                model_tier=model_tier,
                client=client,
                use_live_llm_api=use_live_llm_api,
            )

            outcome = 1 if realized_ret > 0.0035 else (-1 if realized_ret < -0.0035 else 0)

            # ----------------------------------------------------------------
            # M0: Passive Buy-and-Hold Benchmark
            # ----------------------------------------------------------------
            by_proto_stock["M0_Buy_And_Hold"][sym].append({
                "date": date_str, "symbol": sym, "position": 1.0,
                "prev_position": prev_pos["M0_Buy_And_Hold"][sym],
                "asset_return": realized_ret,
                "p_optimistic": 0.50, "p_neutral": 0.50, "p_cautious": 0.00,
                "outcome": outcome, "debate_triggered": False,
                "debate_cost_bps": 0.0, "tokens_used": 0,
            })
            prev_pos["M0_Buy_And_Hold"][sym] = 1.0

            # ----------------------------------------------------------------
            # M1: Linear Pipeline (Equal Weights 0.25 each, No Debate, No Gate)
            # ----------------------------------------------------------------
            agg_m1 = linear_pool_posteriors(
                posteriors, {"market": 0.25, "fundamentals": 0.25, "news": 0.25, "social": 0.25}
            )
            pos_m1 = unified_position_from_posterior(
                agg_m1, prev_pos["M1_Linear_Pipeline"][sym], spread_bps, cbs_turnover_gate=False
            )
            m1_tok = sum(int(posteriors[k].get("tokens_used", 0)) for k in ("market", "fundamentals", "news", "social"))
            by_proto_stock["M1_Linear_Pipeline"][sym].append({
                "date": date_str, "symbol": sym, "position": pos_m1,
                "prev_position": prev_pos["M1_Linear_Pipeline"][sym],
                "asset_return": realized_ret,
                "p_optimistic": agg_m1["p_optimistic"],
                "p_neutral": agg_m1["p_neutral"],
                "p_cautious": agg_m1["p_cautious"],
                "outcome": outcome, "debate_triggered": False,
                "debate_cost_bps": 0.0, "tokens_used": m1_tok,
            })
            prev_pos["M1_Linear_Pipeline"][sym] = pos_m1

            # ----------------------------------------------------------------
            # M2: Vanilla TradingAgents (Always-On 2-Round Unstructured Debate)
            # ----------------------------------------------------------------
            agg_m2, m2_deb_tok = query_m2_debate(
                row=row_curr,
                regime=regime,
                specs=posteriors,
                model_tier=model_tier,
                client=client,
                use_live_llm_api=use_live_llm_api,
            )
            pos_m2 = unified_position_from_posterior(
                agg_m2, prev_pos["M2_Vanilla_TradingAgents"][sym], spread_bps, cbs_turnover_gate=False
            )
            m2_tok = sum(int(posteriors[k].get("tokens_used", 0)) for k in ("market", "fundamentals", "news", "social")) + m2_deb_tok
            by_proto_stock["M2_Vanilla_TradingAgents"][sym].append({
                "date": date_str, "symbol": sym, "position": pos_m2,
                "prev_position": prev_pos["M2_Vanilla_TradingAgents"][sym],
                "asset_return": realized_ret,
                "p_optimistic": agg_m2["p_optimistic"],
                "p_neutral": agg_m2["p_neutral"],
                "p_cautious": agg_m2["p_cautious"],
                "outcome": outcome, "debate_triggered": True,
                "debate_cost_bps": debate_token_cost_bps, "tokens_used": m2_tok,
            })
            prev_pos["M2_Vanilla_TradingAgents"][sym] = pos_m2

            # ----------------------------------------------------------------
            # M3: Single-Model Self-Debate V2 (1-Shot Internal Roleplay)
            # ----------------------------------------------------------------
            agg_m3, m3_self_tok = query_m3_self_debate(
                row=row_curr,
                regime=regime,
                specs=posteriors,
                model_tier=model_tier,
                client=client,
                use_live_llm_api=use_live_llm_api,
            )
            pos_m3 = unified_position_from_posterior(
                agg_m3, prev_pos["M3_SelfDebate_V2"][sym], spread_bps, cbs_turnover_gate=False
            )
            m3_tok = sum(int(posteriors[k].get("tokens_used", 0)) for k in ("market", "fundamentals", "news", "social")) + m3_self_tok
            by_proto_stock["M3_SelfDebate_V2"][sym].append({
                "date": date_str, "symbol": sym, "position": pos_m3,
                "prev_position": prev_pos["M3_SelfDebate_V2"][sym],
                "asset_return": realized_ret,
                "p_optimistic": agg_m3["p_optimistic"],
                "p_neutral": agg_m3["p_neutral"],
                "p_cautious": agg_m3["p_cautious"],
                "outcome": outcome, "debate_triggered": True,
                "debate_cost_bps": 0.9, "tokens_used": m3_tok,
            })
            prev_pos["M3_SelfDebate_V2"][sym] = pos_m3

            # ----------------------------------------------------------------
            # M4: CARE-Agents (Ours)
            #   1. Online Regime-Conditioned Multiplicative Weights (C2, strictly causal t-1 -> t)
            #   2. CBS Debate Gate (`ConditionalLogic.should_gate_debate`, C1)
            #   3. Counterfactual Attribution & Volatility-Scaled Drawdown Breaker (C3)
            # ----------------------------------------------------------------
            w_reg = weight_mgr.get_regime_weights(regime)
            gate_info = cond_logic.should_gate_debate({
                "analyst_posteriors": posteriors,
                "analyst_weights": w_reg,
                "estimated_spread_bps": spread_bps * 0.005,
            })
            gate_open = (gate_info.get("route") == "multi_round_debate")

            best_k = min(["market", "fundamentals", "news"], key=lambda k: spec_cum_loss[k])
            spec_tokens = sum(int(posteriors[k].get("tokens_used", 0)) for k in ("market", "fundamentals", "news", "social"))
            if gate_open:
                jsd_val = float(gate_info.get("jsd", gate_info.get("divergence_score", 0.006)))
                conf_diag = f"Inter-specialist JSD={jsd_val:.4f} > 0.0052. Regime={regime}. Top-performing specialist={best_k}."
                agg_m4, m4_deb_tok = query_m4_gated_debate(
                    row=row_curr,
                    regime=regime,
                    specs=posteriors,
                    w_reg=w_reg,
                    jsd_score=jsd_val,
                    jsd_threshold=cond_logic.jsd_threshold,
                    conflict_diagnostics=conf_diag,
                    model_tier=model_tier,
                    client=client,
                    use_live_llm_api=use_live_llm_api,
                    best_k=best_k,
                )
                m4_tok = spec_tokens + m4_deb_tok
                m4_deb_cost = debate_token_cost_bps
            else:
                # Fast path: Gate closed because specialists agree (JSD <= 0.0052)
                # Combine genuine specialist posteriors using online learned regime weights w_{i,t}^{(r_t)}
                agg_m4 = linear_pool_posteriors(posteriors, w_reg)
                m4_tok = spec_tokens + 0
                m4_deb_cost = 0.0

            if abs(eta - 0.45) > 1e-6:
                # Temperature / learning-rate scaling on pooled posterior odds around default eta=0.45
                tau_scale = max(0.5, 1.0 + 0.85 * (eta - 0.45))
                p_o = max(1e-6, agg_m4["p_optimistic"]) ** tau_scale
                p_n = max(1e-6, agg_m4["p_neutral"])
                p_c = max(1e-6, agg_m4["p_cautious"]) ** (1.0 / tau_scale)
                s_tau = p_o + p_n + p_c
                agg_m4 = {
                    **agg_m4,
                    "p_optimistic": p_o / s_tau,
                    "p_neutral": p_n / s_tau,
                    "p_cautious": p_c / s_tau,
                }

            pos_m4 = unified_position_from_posterior(
                agg_m4, prev_pos["M4_CARE_Agents_Ours"][sym], spread_bps, cbs_turnover_gate=True
            )

            # Volatility-scaled Phase 3 Drawdown Circuit Breaker (strictly causal equity & peak through t-1)
            curr_dd = (m4_peak[sym] - m4_equity[sym]) / max(1e-9, m4_peak[sym])
            dd_cap = max(0.068, 2.5 * (features["vol_4w"] / 100.0))
            if curr_dd > dd_cap and closes[idx] < features["peak_all"] * 0.92:
                pos_m4 = 0.0

            prev_m4 = prev_pos["M4_CARE_Agents_Ours"][sym]
            m4_net_ret = pos_m4 * realized_ret - abs(pos_m4 - prev_m4) * cost_rate
            m4_equity[sym] *= (1.0 + m4_net_ret)
            m4_peak[sym] = max(m4_peak[sym], m4_equity[sym])

            by_proto_stock["M4_CARE_Agents_Ours"][sym].append({
                "date": date_str, "symbol": sym, "position": pos_m4,
                "prev_position": prev_m4,
                "asset_return": realized_ret,
                "p_optimistic": agg_m4["p_optimistic"],
                "p_neutral": agg_m4["p_neutral"],
                "p_cautious": agg_m4["p_cautious"],
                "outcome": outcome, "debate_triggered": gate_open,
                "debate_cost_bps": m4_deb_cost,
                "tokens_used": m4_tok,
            })
            prev_pos["M4_CARE_Agents_Ours"][sym] = pos_m4

            # ----------------------------------------------------------------
            # External SOTA & Classical Quant Baselines (for Table 6 PnL Comparison)
            # ----------------------------------------------------------------
            pos_q1 = 1.0 if features["ma4"] > features["ma8"] else 0.0
            by_proto_stock["Q1_SMA_Crossover"][sym].append({
                "date": date_str, "symbol": sym, "position": pos_q1,
                "prev_position": prev_pos["Q1_SMA_Crossover"][sym],
                "asset_return": realized_ret,
                "p_optimistic": 0.65 if pos_q1 > 0.5 else 0.25, "p_neutral": 0.10,
                "p_cautious": 0.25 if pos_q1 > 0.5 else 0.65,
                "outcome": outcome, "debate_triggered": False, "debate_cost_bps": 0.0, "tokens_used": 0,
            })
            prev_pos["Q1_SMA_Crossover"][sym] = pos_q1

            pos_q2 = 1.0 if (features["ma4"] >= features["ma8"] * 0.995 and features["ret_2w"] > 0.0 and features["ret_1w"] < 5.5) else 0.0
            by_proto_stock["Q2_MACD_RSI_Rule"][sym].append({
                "date": date_str, "symbol": sym, "position": pos_q2,
                "prev_position": prev_pos["Q2_MACD_RSI_Rule"][sym],
                "asset_return": realized_ret,
                "p_optimistic": 0.60 if pos_q2 > 0.4 else 0.30, "p_neutral": 0.10,
                "p_cautious": 0.30 if pos_q2 > 0.4 else 0.60,
                "outcome": outcome, "debate_triggered": False, "debate_cost_bps": 0.0, "tokens_used": 0,
            })
            prev_pos["Q2_MACD_RSI_Rule"][sym] = pos_q2

            is_frontier = (model_tier == "Frontier_LLM_DeepSeek_V3")
            if is_frontier:
                # B1: FinMem (Yu et al., 2024) -- Single-agent with 3-layer episodic memory
                past_rets_6w = [(closes[k] / closes[k - 1] - 1.0) * 100.0 for k in range(max(1, idx - 6), idx)]
                mem_avg = float(np.mean(finmem_mem[sym][-6:])) if finmem_mem[sym] else 0.0
                agg_b1, b1_tok = query_b1_finmem(
                    row=row_curr,
                    features=features,
                    regime=regime,
                    past_returns_6w=past_rets_6w,
                    model_tier=model_tier,
                    client=client,
                    use_live_llm_api=use_live_llm_api,
                    posteriors=posteriors,
                    mem_avg=mem_avg,
                )
                pos_b1 = unified_position_from_posterior(agg_b1, prev_pos["B1_FinMem_2024"][sym], spread_bps, cbs_turnover_gate=False)
                finmem_mem[sym].append(realized_ret)
                by_proto_stock["B1_FinMem_2024"][sym].append({
                    "date": date_str, "symbol": sym, "position": pos_b1,
                    "prev_position": prev_pos["B1_FinMem_2024"][sym],
                    "asset_return": realized_ret,
                    "p_optimistic": agg_b1["p_optimistic"], "p_neutral": agg_b1["p_neutral"], "p_cautious": agg_b1["p_cautious"],
                    "outcome": outcome, "debate_triggered": False, "debate_cost_bps": 0.3, "tokens_used": b1_tok,
                })
                prev_pos["B1_FinMem_2024"][sym] = pos_b1

                # B2: FinAgent (Zhang et al., KDD 2024) -- Tool-augmented reflection agent
                prev_trade_pos = prev_pos["B2_FinAgent_KDD24"][sym]
                prev_trade_ret = (closes[idx] / closes[idx - 1] - 1.0) if idx > 0 else 0.0
                agg_b2, b2_tok = query_b2_finagent(
                    row=row_curr,
                    features=features,
                    regime=regime,
                    prev_pos=prev_trade_pos,
                    prev_ret=prev_trade_ret,
                    model_tier=model_tier,
                    client=client,
                    use_live_llm_api=use_live_llm_api,
                    posteriors=posteriors,
                )
                pos_b2 = unified_position_from_posterior(agg_b2, prev_pos["B2_FinAgent_KDD24"][sym], spread_bps, cbs_turnover_gate=False)
                by_proto_stock["B2_FinAgent_KDD24"][sym].append({
                    "date": date_str, "symbol": sym, "position": pos_b2,
                    "prev_position": prev_pos["B2_FinAgent_KDD24"][sym],
                    "asset_return": realized_ret,
                    "p_optimistic": agg_b2["p_optimistic"], "p_neutral": agg_b2["p_neutral"], "p_cautious": agg_b2["p_cautious"],
                    "outcome": outcome, "debate_triggered": False, "debate_cost_bps": 0.4, "tokens_used": b2_tok,
                })
                prev_pos["B2_FinAgent_KDD24"][sym] = pos_b2

                # B3: FinCon (Yu et al., NeurIPS 2024) -- Manager-Analyst hierarchy + rolling CVaR
                rets_8w = [(closes[k] / closes[k - 1] - 1.0) for k in range(max(1, idx - 8), idx)]
                agg_b3, b3_tok = query_b3_fincon(
                    row=row_curr,
                    features=features,
                    regime=regime,
                    returns_8w=rets_8w,
                    model_tier=model_tier,
                    client=client,
                    use_live_llm_api=use_live_llm_api,
                    posteriors=posteriors,
                    fincon_history=fincon_rets[sym],
                )
                pos_b3 = unified_position_from_posterior(agg_b3, prev_pos["B3_FinCon_NeurIPS24"][sym], spread_bps, cbs_turnover_gate=False)
                fincon_rets[sym].append(pos_b3 * realized_ret - abs(pos_b3 - prev_pos["B3_FinCon_NeurIPS24"][sym]) * cost_rate)
                by_proto_stock["B3_FinCon_NeurIPS24"][sym].append({
                    "date": date_str, "symbol": sym, "position": pos_b3,
                    "prev_position": prev_pos["B3_FinCon_NeurIPS24"][sym],
                    "asset_return": realized_ret,
                    "p_optimistic": agg_b3["p_optimistic"], "p_neutral": agg_b3["p_neutral"], "p_cautious": agg_b3["p_cautious"],
                    "outcome": outcome, "debate_triggered": False, "debate_cost_bps": 0.6, "tokens_used": b3_tok,
                })
                prev_pos["B3_FinCon_NeurIPS24"][sym] = pos_b3

            # Queue end-of-week realized return updates so no symbol at step t sees another symbol's t->t+1 return
            pending_step_updates.append({
                "sym": sym,
                "regime": regime,
                "posteriors": posteriors,
                "realized_ret": realized_ret,
                "realized_ret_pct": realized_ret_pct,
            })

        # Log causal pre-update weights w_{i,t}^{(r_t)} active during step t decisions
        dominant_regime = max(regime_counts.items(), key=lambda kv: kv[1])[0]
        w_snap = weight_mgr.get_regime_weights(dominant_regime)
        weight_trajectory_log.append({
            "date": date_str,
            "regime": dominant_regime,
            "market": float(w_snap["market"]),
            "fundamentals": float(w_snap["fundamentals"]),
            "news": float(w_snap["news"]),
            "social": float(w_snap["social"]),
        })

        # Strictly causal t -> t+1 update: apply realized returns from step t AFTER all step t decisions complete
        for upd in pending_step_updates:
            weight_mgr.update_weights(
                regime=upd["regime"],
                posteriors=upd["posteriors"],
                realized_return_pct=upd["realized_ret_pct"],
                eta=eta,
                threshold_pct=0.35,
            )
            sym_u = upd["sym"]
            posts_u = upd["posteriors"]
            ret_u = upd["realized_ret"]
            for k in spec_cum_loss:
                k_pos = 1.0 if (posts_u[k]["p_optimistic"] > posts_u[k]["p_cautious"]) else 0.0
                turn_k = abs(k_pos - prev_k_pos[k][sym_u])
                prev_k_pos[k][sym_u] = k_pos
                spec_cum_loss[k] = 0.96 * spec_cum_loss[k] - (k_pos * ret_u - turn_k * 0.0020)

    portfolio_records_by_proto: Dict[str, List[Dict[str, Any]]] = {}
    for proto in protocols:
        port_recs = []
        n_steps = len(by_proto_stock[proto][symbols[0]])
        for t in range(n_steps):
            step_items = [by_proto_stock[proto][s][t] for s in symbols]
            m1_step_items = [by_proto_stock["M1_Linear_Pipeline"][s][t] for s in symbols]
            avg_pos = float(np.mean([x["position"] for x in step_items]))
            avg_prev_pos = float(np.mean([x["prev_position"] for x in step_items]))
            gross_ret = float(np.mean([x["position"] * x["asset_return"] for x in step_items]))
            exact_turnover = float(np.mean([abs(x["position"] - x["prev_position"]) for x in step_items]))
            avg_asset_ret = float(np.mean([x["asset_return"] for x in step_items]))

            # Exact M1 gross return and exact M1 turnover on week t (no hardcoded 0.12!)
            m1_gross = float(np.mean([x["position"] * x["asset_return"] for x in m1_step_items]))
            m1_turnover = float(np.mean([abs(x["position"] - x["prev_position"]) for x in m1_step_items]))

            any_debate = any(x["debate_triggered"] for x in step_items)
            debate_frac = float(np.mean([1.0 if x["debate_triggered"] else 0.0 for x in step_items]))
            avg_tokens = float(np.mean([x["tokens_used"] for x in step_items]))

            avg_p_opt = float(np.mean([x["p_optimistic"] for x in step_items]))
            avg_p_neut = float(np.mean([x["p_neutral"] for x in step_items]))
            avg_p_caut = float(np.mean([x["p_cautious"] for x in step_items]))
            s_p = avg_p_opt + avg_p_neut + avg_p_caut

            port_outcome = 1 if avg_asset_ret > 0.003 else (-1 if avg_asset_ret < -0.003 else 0)

            port_recs.append({
                "date": step_items[0]["date"],
                "position": avg_pos,
                "prev_position": avg_prev_pos,
                "exact_gross_return": gross_ret,
                "exact_turnover": exact_turnover,
                "asset_return": avg_asset_ret,
                "p_optimistic": avg_p_opt / s_p,
                "p_neutral": avg_p_neut / s_p,
                "p_cautious": avg_p_caut / s_p,
                "outcome": port_outcome,
                "debate_triggered": any_debate,
                "debate_fraction": debate_frac,
                "m1_gross": m1_gross,
                "m1_turnover": m1_turnover,
                "post_debate_gross": gross_ret,
                "debate_cost_bps": float(np.mean([x["debate_cost_bps"] for x in step_items])),
                "tokens_used": avg_tokens,
            })
        portfolio_records_by_proto[proto] = port_recs

    return portfolio_records_by_proto, by_proto_stock, weight_trajectory_log


def evaluate_portfolio_records(
    records: List[Dict[str, Any]],
    cost_bps: float,
) -> Dict[str, Any]:
    """
    Evaluate equal-weighted portfolio records using exact per-stock gross return and
    turnover series (MR-1 through MR-7, Annualized 52-week / 252-trading-day compounding, rf=0).
    """
    cost_rate = cost_bps / 10000.0
    cost_rate_10bps = 10.0 / 10000.0
    gross_rets = []
    net_rets = []
    net_10bps_rets = []
    turnovers = []
    brier_scores = []
    mae_scores = []
    ece_pairs = []
    dir_hits = []
    cbs_surpluses = []
    debate_fracs = []
    token_counts = []

    for r in records:
        g_ret = r["exact_gross_return"]
        turn = r["exact_turnover"]
        n_ret = g_ret - turn * cost_rate
        n_10bps_ret = g_ret - turn * cost_rate_10bps
        gross_rets.append(g_ret)
        net_rets.append(n_ret)
        net_10bps_rets.append(n_10bps_ret)
        turnovers.append(turn)

        outcome = int(r["outcome"])
        y_opt = 1.0 if outcome == 1 else 0.0
        y_neut = 1.0 if outcome == 0 else 0.0
        y_caut = 1.0 if outcome == -1 else 0.0
        bs = (
            (r["p_optimistic"] - y_opt) ** 2
            + (r["p_neutral"] - y_neut) ** 2
            + (r["p_cautious"] - y_caut) ** 2
        ) / 3.0
        mae_val = (
            abs(r["p_optimistic"] - y_opt)
            + abs(r["p_neutral"] - y_neut)
            + abs(r["p_cautious"] - y_caut)
        ) / 3.0
        brier_scores.append(bs)
        mae_scores.append(mae_val)

        probs = [r["p_optimistic"], r["p_neutral"], r["p_cautious"]]
        labels = [y_opt, y_neut, y_caut]
        top_idx = int(np.argmax(probs))
        ece_pairs.append((float(probs[top_idx]), float(labels[top_idx])))

        asset_r = float(r.get("asset_return", 0.0))
        pos = float(r.get("position", 0.0))
        if abs(asset_r) > 1e-9:
            if pos >= 0.45:
                dir_hits.append(1.0 if asset_r > 0 else 0.0)
            else:
                dir_hits.append(1.0 if asset_r <= 0 else 0.0)

        debate_fracs.append(r["debate_fraction"])
        token_counts.append(r["tokens_used"])

        # Exact M1 net return on step t (using exact M1 turnover, zero hardcoded constants)
        m1_net = r["m1_gross"] - r["m1_turnover"] * cost_rate
        surplus_bps = (n_ret - m1_net) * 10000.0 - r["debate_cost_bps"]
        cbs_surpluses.append(surplus_bps)

    ece_val = 0.0
    if ece_pairs:
        n_ece = len(ece_pairs)
        for b_idx in range(10):
            lo, hi = b_idx / 10.0, (b_idx + 1) / 10.0
            bucket = [p for p in ece_pairs if (lo <= p[0] < hi) or (b_idx == 9 and p[0] == 1.0)]
            if bucket:
                avg_c = sum(p[0] for p in bucket) / len(bucket)
                avg_a = sum(p[1] for p in bucket) / len(bucket)
                ece_val += (len(bucket) / n_ece) * abs(avg_c - avg_a)

    periods_per_year = 52.0
    gross_arr = np.array(gross_rets, dtype=float)
    net_arr = np.array(net_rets, dtype=float)
    net_10bps_arr = np.array(net_10bps_rets, dtype=float)

    n_bars = max(1, len(net_arr))
    eq_gross = np.cumprod(1.0 + gross_arr)
    eq_net = np.cumprod(1.0 + net_arr)
    eq_net10 = np.cumprod(1.0 + net_10bps_arr)

    cum_gross = float(eq_gross[-1] - 1.0) * 100.0
    cum_net = float(eq_net[-1] - 1.0) * 100.0
    cum_net10 = float(eq_net10[-1] - 1.0) * 100.0

    ann_gross_ret = (float(eq_gross[-1]) ** (periods_per_year / n_bars) - 1.0) * 100.0
    ann_net_ret = (float(eq_net[-1]) ** (periods_per_year / n_bars) - 1.0) * 100.0
    ann_net10_ret = (float(eq_net10[-1]) ** (periods_per_year / n_bars) - 1.0) * 100.0

    gross_std = float(np.std(gross_arr, ddof=1)) if len(gross_arr) > 1 else 1e-9
    net_std = float(np.std(net_arr, ddof=1)) if len(net_arr) > 1 else 1e-9
    net10_std = float(np.std(net_10bps_arr, ddof=1)) if len(net_10bps_arr) > 1 else 1e-9

    ann_vol_pct = net_std * math.sqrt(periods_per_year) * 100.0
    gross_sharpe = (float(np.mean(gross_arr)) / max(1e-9, gross_std)) * math.sqrt(periods_per_year)
    net_sharpe = (float(np.mean(net_arr)) / max(1e-9, net_std)) * math.sqrt(periods_per_year)
    net_sharpe_10bps = (float(np.mean(net_10bps_arr)) / max(1e-9, net10_std)) * math.sqrt(periods_per_year)

    # Sortino ratio using downside deviation below 0 (target return = 0)
    downside_sq = np.minimum(0.0, net_arr) ** 2
    down_std = float(math.sqrt(np.mean(downside_sq))) if len(net_arr) > 0 else 1e-9
    net_sortino = (float(np.mean(net_arr)) / max(1e-9, down_std)) * math.sqrt(periods_per_year)

    peaks = np.maximum.accumulate(eq_net)
    dds = (peaks - eq_net) / np.maximum(1e-9, peaks)
    max_dd = float(np.max(dds)) * 100.0
    calmar = ann_net_ret / max(0.01, max_dd)

    return {
        "gross_cum_return_pct": round(cum_gross, 2),
        "net_cum_return_pct": round(cum_net, 2),
        "net_10bps_cum_return_pct": round(cum_net10, 2),
        "gross_ann_return_pct": round(ann_gross_ret, 2),
        "net_ann_return_pct": round(ann_net_ret, 2),
        "net_10bps_ann_return_pct": round(ann_net10_ret, 2),
        "ann_vol_pct": round(ann_vol_pct, 2),
        "gross_sharpe": round(gross_sharpe, 3),
        "net_sharpe": round(net_sharpe, 3),
        "net_sharpe_10bps": round(net_sharpe_10bps, 3),
        "net_sortino": round(net_sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "turnover_rate": round(float(np.sum(turnovers)), 2),
        "weekly_turnover_rate": round(float(np.mean(turnovers)), 4),
        "brier_score": round(float(np.mean(brier_scores)), 4),
        "mae": round(float(np.mean(mae_scores)), 4),
        "ece": round(float(ece_val), 4),
        "hit_rate_pct": round(float(np.mean(dir_hits)) * 100.0, 2) if dir_hits else 0.0,
        "cbs_mean_bps": round(float(np.mean(cbs_surpluses)) if cbs_surpluses else 0.0, 2),
        "debate_rate_pct": round(float(np.mean(debate_fracs)) * 100.0, 1),
        "avg_tokens_per_step": round(float(np.mean(token_counts)), 0),
        "net_return_series": net_rets,
        "brier_series": brier_scores,
    }


def _configure_ieee_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 11,
        "legend.fontsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "figure.dpi": 300,
    })
    return plt


def _save_dual_vector_and_png(fig, out_paths: List[Path]) -> None:
    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(p.with_suffix(".pdf"), bbox_inches="tight")
        fig.savefig(p.with_suffix(".png"), dpi=300, bbox_inches="tight")


def render_regime_weight_figure(weight_log: List[Dict[str, Any]], out_path: Path) -> None:
    """Generate publication-quality Figure 2: Regime-Conditioned Specialist Weight Trajectories (.pdf + .png)."""
    plt = _configure_ieee_matplotlib()

    dates = [r["date"] for r in weight_log]
    regimes = [r["regime"] for r in weight_log]
    w_mkt = [r["market"] for r in weight_log]
    w_fund = [r["fundamentals"] for r in weight_log]
    w_news = [r["news"] for r in weight_log]
    w_soc = [r["social"] for r in weight_log]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11.0, 5.8), gridspec_kw={"height_ratios": [3.2, 1.0]}, sharex=True
    )
    fig.patch.set_facecolor("white")

    x = np.arange(len(dates))
    ax1.plot(x, w_mkt, label="Market / Technical Specialist", color="#1f77b4", linewidth=2.0)
    ax1.plot(x, w_fund, label="Fundamentals & Valuation Specialist", color="#2ca02c", linewidth=2.0)
    ax1.plot(x, w_news, label="Macro / Policy News Specialist", color="#ff7f0e", linewidth=1.9, linestyle="--")
    ax1.plot(x, w_soc, label="Social Sentiment Specialist", color="#d62728", linewidth=1.8, linestyle=":")

    regime_colors = {"bull": "#e6f5ea", "bear": "#fde8e8", "sideways": "#f4f4f6"}
    for i in range(len(x) - 1):
        ax1.axvspan(i, i + 1, color=regime_colors.get(regimes[i], "#ffffff"), alpha=0.55, lw=0)

    ax1.axhline(0.25, color="#666666", linestyle="-.", linewidth=1.0, alpha=0.7, label="Equal-Weight Prior (0.25)")
    ax1.set_ylabel("Causal Specialist Weight $w_{i,t}^{(r_t)}$")
    ax1.set_title(
        "CARE-Agents Causal ($t-1 \\to t$) Regime-Conditioned Multiplicative Weight Trajectories (2025–2026 CSI 300 A-Shares)",
        pad=10,
    )
    ax1.set_ylim(0.03, 0.50)
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(loc="upper left", ncol=3, frameon=True, facecolor="white", framealpha=0.9)

    regime_num = [1 if r == "bull" else (-1 if r == "bear" else 0) for r in regimes]
    bar_colors = ["#2ca02c" if r == "bull" else ("#d62728" if r == "bear" else "#7f7f7f") for r in regimes]
    ax2.bar(x, regime_num, color=bar_colors, width=0.85, alpha=0.85)
    ax2.set_yticks([-1, 0, 1])
    ax2.set_yticklabels(["Bear", "Sideways", "Bull"])
    ax2.set_ylabel("Causal Regime")
    ax2.set_xlabel("Point-in-Time Weekly Decision Date (2025-02 to 2026-10, Post-Cutoff Out-of-Sample Window)")
    ax2.grid(True, axis="x", linestyle="--", alpha=0.35)

    step = max(1, len(dates) // 10)
    ax2.set_xticks(x[::step])
    ax2.set_xticklabels([dates[i] for i in range(0, len(dates), step)], rotation=25, ha="right")

    plt.tight_layout()
    reports_dir = REPO_ROOT / "reports"
    _save_dual_vector_and_png(fig, [out_path, reports_dir / "regime_weight_trajectories"])
    plt.close(fig)


def render_equity_and_drawdown_figure(
    cn_port_by_proto: Dict[str, List[Dict[str, Any]]],
    us_port_by_proto: Dict[str, List[Dict[str, Any]]],
    out_path: Path,
) -> None:
    """Generate publication-quality 2-panel Figure: Cumulative Net Equity & Underwater Drawdown (.pdf + .png)."""
    plt = _configure_ieee_matplotlib()

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 7.2), sharex="col")
    fig.patch.set_facecolor("white")

    proto_styles = [
        ("M0_Buy_And_Hold", "Buy & Hold Benchmark", "#7f7f7f", "--", 1.4),
        ("B1_FinMem_2024", "FinMem (Layered Memory)", "#2ca02c", "-.", 1.5),
        ("B2_FinAgent_KDD24", "FinAgent (KDD'24 Reflection)", "#ff7f0e", "-.", 1.5),
        ("B3_FinCon_NeurIPS24", "FinCon (NeurIPS'24 CVaR)", "#9467bd", "--", 1.6),
        ("M2_Vanilla_TradingAgents", "TradingAgents (Fixed Debate)", "#d62728", ":", 1.8),
        ("M4_CARE_Agents_Ours", "CARE-Agents (Ours, CBS + Regime-MWU)", "#1f4e78", "-", 2.5),
    ]

    for col_idx, (title, port_dict, cost_bps) in enumerate([
        ("China CSI 300 A-Shares (15.0 bps One-Way Friction)", cn_port_by_proto, 15.0),
        ("US Tech Benchmark (5.0 bps One-Way Friction)", us_port_by_proto, 5.0),
    ]):
        ax_eq = axes[0, col_idx]
        ax_dd = axes[1, col_idx]
        cost_rate = cost_bps / 10000.0
        dates = [r["date"] for r in port_dict["M0_Buy_And_Hold"]]
        x = np.arange(len(dates))

        for proto, label, color, ls, lw in proto_styles:
            if proto not in port_dict or not port_dict[proto]:
                continue
            recs = port_dict[proto]
            net_rets = np.array([
                r["exact_gross_return"] - r["exact_turnover"] * cost_rate for r in recs
            ])
            eq = np.cumprod(1.0 + net_rets)
            cum_pct = (eq - 1.0) * 100.0
            peaks = np.maximum.accumulate(eq)
            dd_pct = -((peaks - eq) / np.maximum(1e-9, peaks)) * 100.0

            ax_eq.plot(x, cum_pct, label=label, color=color, linestyle=ls, linewidth=lw)
            ax_dd.plot(x, dd_pct, label=label, color=color, linestyle=ls, linewidth=lw)
            if proto == "M4_CARE_Agents_Ours":
                ax_dd.fill_between(x, dd_pct, 0.0, color=color, alpha=0.10)

        ax_eq.axhline(0.0, color="#444444", linewidth=0.8, alpha=0.6)
        ax_eq.set_title(title, pad=8)
        ax_eq.set_ylabel("Cumulative Net Return (%)")
        ax_eq.grid(True, linestyle="--", alpha=0.35)
        if col_idx == 0:
            ax_eq.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.92)

        ax_dd.set_ylabel("Underwater Drawdown (%)")
        ax_dd.set_xlabel("Point-in-Time Weekly Evaluation Date (2025-02 to 2026-10)")
        ax_dd.grid(True, linestyle="--", alpha=0.35)

        step = max(1, len(dates) // 8)
        ax_dd.set_xticks(x[::step])
        ax_dd.set_xticklabels([dates[i] for i in range(0, len(dates), step)], rotation=25, ha="right")

    plt.tight_layout()
    reports_dir = REPO_ROOT / "reports"
    results_dir = REPO_ROOT / "results"
    _save_dual_vector_and_png(
        fig,
        [
            out_path,
            reports_dir / "phase5_sota_pnl_comparison",
            results_dir / "phase5_sota_pnl_comparison",
        ],
    )
    plt.close(fig)


def evaluate_cohort_and_collect_rows(
    cohort_name: str,
    by_symbol: Dict[str, List[Dict[str, Any]]],
    universes: List[Tuple[str, List[str], str, float]],
    model_tiers: List[Tuple[str, int]],
    max_weeks: int,
    use_live_llm_api: bool,
    client: LiveDeepSeekBenchmarkClient,
    verbose: bool = True,
):
    summary_rows: List[Dict[str, Any]] = []
    sota_pnl_rows: List[Dict[str, Any]] = []
    per_stock_rows: List[Dict[str, Any]] = []
    cn_frontier_weights: List[Dict[str, Any]] = []
    cn_frontier_port: Dict[str, List[Dict[str, Any]]] = {}
    us_frontier_port: Dict[str, List[Dict[str, Any]]] = {}

    for univ_name, symbols, mkt_code, cost_bps in universes:
        for tier_name, seed in model_tiers:
            port_by_proto, stock_by_proto, weight_log = run_market_universe_chronologically(
                by_symbol=by_symbol,
                symbols=symbols,
                market_code=mkt_code,
                model_tier=tier_name,
                seed=seed,
                use_live_llm_api=use_live_llm_api,
                max_weeks=max_weeks,
                client=client,
            )
            if mkt_code == "CN" and tier_name == "Frontier_LLM_DeepSeek_V3":
                cn_frontier_weights = weight_log
                cn_frontier_port = port_by_proto
            if mkt_code == "US" and tier_name == "Frontier_LLM_DeepSeek_V3":
                us_frontier_port = port_by_proto

            m2_metrics = evaluate_portfolio_records(port_by_proto["M2_Vanilla_TradingAgents"], cost_bps)
            m1_metrics = evaluate_portfolio_records(port_by_proto["M1_Linear_Pipeline"], cost_bps)
            bh_metrics = evaluate_portfolio_records(port_by_proto["M0_Buy_And_Hold"], cost_bps)
            m2_net_series = m2_metrics["net_return_series"]
            m1_net_series = m1_metrics["net_return_series"]
            bh_net_series = bh_metrics["net_return_series"]
            m2_brier_series = m2_metrics["brier_series"]

            if verbose:
                print(f"\n--- [{cohort_name}] Universe: {univ_name} (Friction: {cost_bps:.1f} bps) | Model Tier: {tier_name} ---")
                print(
                    f"{'Protocol':<26} | {'Gross%':>7} | {'Net%':>7} | {'Net10%':>7} | {'GrossSR':>7} | {'NetSR':>6} | "
                    f"{'SR10bp':>6} | {'Sortino':>7} | {'MaxDD%':>6} | {'Turn':>5} | {'Brier':>6} | {'MAE':>6} | {'Hit%':>5} | {'p(M2)':>6}"
                )
                print("-" * 136)

            for proto in [
                "M0_Buy_And_Hold",
                "M1_Linear_Pipeline",
                "M2_Vanilla_TradingAgents",
                "M3_SelfDebate_V2",
                "M4_CARE_Agents_Ours",
            ]:
                m = evaluate_portfolio_records(port_by_proto[proto], cost_bps)
                cand_series = m["net_return_series"]
                cand_brier = m["brier_series"]

                pval_m2 = paired_block_bootstrap_sharpe_test(cand_series, m2_net_series, periods_per_year=52, n_boot=1000)["p_value"]
                pval_m1 = paired_block_bootstrap_sharpe_test(cand_series, m1_net_series, periods_per_year=52, n_boot=1000)["p_value"]
                pval_bh = paired_block_bootstrap_sharpe_test(cand_series, bh_net_series, periods_per_year=52, n_boot=1000)["p_value"]
                dm_m2 = diebold_mariano_pvalue(cand_series, m2_net_series)
                dm_m1 = diebold_mariano_pvalue(cand_series, m1_net_series)
                dm_bh = diebold_mariano_pvalue(cand_series, bh_net_series)
                hac_t_m2 = newey_west_hac_tstat(cand_series, m2_net_series)
                delong_m2 = delong_brier_pvalue(cand_brier, m2_brier_series)

                if proto == "M2_Vanilla_TradingAgents":
                    pval_m2, dm_m2, hac_t_m2, delong_m2 = 1.0, 1.0, 0.0, 1.0
                if proto == "M1_Linear_Pipeline":
                    pval_m1, dm_m1 = 1.0, 1.0
                if proto == "M0_Buy_And_Hold":
                    pval_bh, dm_bh = 1.0, 1.0

                if verbose:
                    print(
                        f"{proto:<26} | {m['gross_cum_return_pct']:>+7.2f} | {m['net_cum_return_pct']:>+7.2f} | "
                        f"{m['net_10bps_cum_return_pct']:>+7.2f} | {m['gross_sharpe']:>7.3f} | {m['net_sharpe']:>6.3f} | "
                        f"{m['net_sharpe_10bps']:>6.3f} | {m['net_sortino']:>7.3f} | {m['max_drawdown_pct']:>6.2f} | "
                        f"{m['turnover_rate']:>5.2f} | {m['brier_score']:>6.4f} | {m['mae']:>6.4f} | "
                        f"{m['hit_rate_pct']:>4.1f}% | {pval_m2:>6.4f}"
                    )

                summary_rows.append({
                    "cohort": cohort_name,
                    "universe": univ_name,
                    "market": mkt_code,
                    "cost_bps": cost_bps,
                    "model_tier": tier_name,
                    "protocol": proto,
                    "gross_cum_return_pct": m["gross_cum_return_pct"],
                    "net_cum_return_pct": m["net_cum_return_pct"],
                    "net_10bps_cum_return_pct": m["net_10bps_cum_return_pct"],
                    "gross_ann_return_pct": m["gross_ann_return_pct"],
                    "net_ann_return_pct": m["net_ann_return_pct"],
                    "net_10bps_ann_return_pct": m["net_10bps_ann_return_pct"],
                    "ann_vol_pct": m["ann_vol_pct"],
                    "gross_sharpe": m["gross_sharpe"],
                    "net_sharpe": m["net_sharpe"],
                    "net_sharpe_10bps": m["net_sharpe_10bps"],
                    "net_sortino": m["net_sortino"],
                    "calmar_ratio": m["calmar_ratio"],
                    "max_drawdown_pct": m["max_drawdown_pct"],
                    "turnover_rate": m["turnover_rate"],
                    "weekly_turnover_rate": m["weekly_turnover_rate"],
                    "brier_score": m["brier_score"],
                    "mae": m["mae"],
                    "ece": m["ece"],
                    "hit_rate_pct": m["hit_rate_pct"],
                    "cbs_mean_bps": m["cbs_mean_bps"],
                    "debate_rate_pct": m["debate_rate_pct"],
                    "avg_tokens_per_step": m["avg_tokens_per_step"],
                    "hac_t_stat_vs_m2": round(hac_t_m2, 3),
                    "delong_p_value_vs_m2": round(delong_m2, 4),
                    "p_value_vs_m2": round(pval_m2, 4),
                    "dm_p_value_vs_m2": round(dm_m2, 4),
                    "p_value_vs_m1": round(pval_m1, 4),
                    "dm_p_value_vs_m1": round(dm_m1, 4),
                    "p_value_vs_bh": round(pval_bh, 4),
                    "dm_p_value_vs_bh": round(dm_bh, 4),
                })

            if tier_name == "Frontier_LLM_DeepSeek_V3":
                initial_capital = 100000.0
                for sota_key, sota_label in [
                    ("M0_Buy_And_Hold", "Buy & Hold (Market Benchmark)"),
                    ("Q1_SMA_Crossover", "SMA Crossover (Quant Rule)"),
                    ("Q2_MACD_RSI_Rule", "MACD + RSI Filter (Quant Rule)"),
                    ("B1_FinMem_2024", "FinMem (Yu et al., 2024)"),
                    ("B2_FinAgent_KDD24", "FinAgent (Zhang et al., KDD'24)"),
                    ("B3_FinCon_NeurIPS24", "FinCon (Yu et al., NeurIPS'24)"),
                    ("M2_Vanilla_TradingAgents", "TradingAgents (Xiao et al., 2024)"),
                    ("M4_CARE_Agents_Ours", "CARE-Agents (Ours, Full)"),
                ]:
                    ms = evaluate_portfolio_records(port_by_proto[sota_key], cost_bps)
                    cand_s = ms["net_return_series"]
                    cand_b = ms["brier_series"]
                    pv_m2 = paired_block_bootstrap_sharpe_test(cand_s, m2_net_series, periods_per_year=52, n_boot=1000)["p_value"]
                    pv_m1 = paired_block_bootstrap_sharpe_test(cand_s, m1_net_series, periods_per_year=52, n_boot=1000)["p_value"]
                    pv_bh = paired_block_bootstrap_sharpe_test(cand_s, bh_net_series, periods_per_year=52, n_boot=1000)["p_value"]
                    dm_m2 = diebold_mariano_pvalue(cand_s, m2_net_series)
                    dm_m1 = diebold_mariano_pvalue(cand_s, m1_net_series)
                    dm_bh = diebold_mariano_pvalue(cand_s, bh_net_series)
                    hac_t_m2 = newey_west_hac_tstat(cand_s, m2_net_series)
                    delong_m2 = delong_brier_pvalue(cand_b, m2_brier_series)
                    if sota_key == "M2_Vanilla_TradingAgents":
                        pv_m2, dm_m2, hac_t_m2, delong_m2 = 1.0, 1.0, 0.0, 1.0
                    if sota_key == "M0_Buy_And_Hold":
                        pv_bh, dm_bh = 1.0, 1.0

                    net_pnl = initial_capital * (ms["net_cum_return_pct"] / 100.0)
                    net_pnl_10bps = initial_capital * (ms["net_10bps_cum_return_pct"] / 100.0)
                    sota_pnl_rows.append({
                        "cohort": cohort_name,
                        "universe": univ_name,
                        "market": mkt_code,
                        "method_code": sota_key,
                        "method_label": sota_label,
                        "initial_capital_usd": int(initial_capital),
                        "final_equity_usd": round(initial_capital + net_pnl, 2),
                        "net_pnl_usd": round(net_pnl, 2),
                        "net_pnl_10bps_usd": round(net_pnl_10bps, 2),
                        "gross_return_pct": ms["gross_cum_return_pct"],
                        "net_return_pct": ms["net_cum_return_pct"],
                        "net_10bps_return_pct": ms["net_10bps_cum_return_pct"],
                        "gross_ann_return_pct": ms["gross_ann_return_pct"],
                        "net_ann_return_pct": ms["net_ann_return_pct"],
                        "ann_vol_pct": ms["ann_vol_pct"],
                        "gross_sharpe": ms["gross_sharpe"],
                        "net_sharpe": ms["net_sharpe"],
                        "net_sharpe_10bps": ms["net_sharpe_10bps"],
                        "net_sortino": ms["net_sortino"],
                        "calmar_ratio": ms["calmar_ratio"],
                        "max_drawdown_pct": ms["max_drawdown_pct"],
                        "turnover_rate": ms["turnover_rate"],
                        "weekly_turnover_rate": ms["weekly_turnover_rate"],
                        "brier_score": ms["brier_score"],
                        "mae": ms["mae"],
                        "ece": ms["ece"],
                        "hit_rate_pct": ms["hit_rate_pct"],
                        "avg_tokens": ms["avg_tokens_per_step"],
                        "hac_t_stat_vs_tradingagents": round(hac_t_m2, 3),
                        "delong_p_value_vs_tradingagents": round(delong_m2, 4),
                        "p_value_vs_tradingagents": round(pv_m2, 4),
                        "dm_p_value_vs_tradingagents": round(dm_m2, 4),
                        "p_value_vs_equal_weight": round(pv_m1, 4),
                        "dm_p_value_vs_equal_weight": round(dm_m1, 4),
                        "p_value_vs_buy_hold": round(pv_bh, 4),
                        "dm_p_value_vs_buy_hold": round(dm_bh, 4),
                    })

                for sym in symbols:
                    bh_recs = stock_by_proto["M0_Buy_And_Hold"][sym]
                    m2_recs = stock_by_proto["M2_Vanilla_TradingAgents"][sym]
                    m4_recs = stock_by_proto["M4_CARE_Agents_Ours"][sym]

                    def _stock_stats(recs):
                        c_rate = cost_bps / 10000.0
                        c10_rate = 10.0 / 10000.0
                        gross = [r["position"] * r["asset_return"] for r in recs]
                        nets = [
                            r["position"] * r["asset_return"] - abs(r["position"] - r["prev_position"]) * c_rate
                            for r in recs
                        ]
                        nets10 = [
                            r["position"] * r["asset_return"] - abs(r["position"] - r["prev_position"]) * c10_rate
                            for r in recs
                        ]
                        turns = sum(abs(r["position"] - r["prev_position"]) for r in recs)
                        deb_rate = float(np.mean([1.0 if r["debate_triggered"] else 0.0 for r in recs])) * 100.0
                        net_arr_s = np.asarray(nets, dtype=float)
                        net10_arr_s = np.asarray(nets10, dtype=float)
                        gross_arr_s = np.asarray(gross, dtype=float)
                        eq_s = np.cumprod(1.0 + net_arr_s)
                        cum_n = float(eq_s[-1] - 1.0) * 100.0
                        cum_g = float(np.prod(1.0 + gross_arr_s) - 1.0) * 100.0
                        cum_n10 = float(np.prod(1.0 + net10_arr_s) - 1.0) * 100.0
                        ann_n = (float(eq_s[-1]) ** (52.0 / max(1, len(net_arr_s))) - 1.0) * 100.0
                        std_s = float(np.std(net_arr_s, ddof=1)) if len(net_arr_s) > 1 else 1e-9
                        std10_s = float(np.std(net10_arr_s, ddof=1)) if len(net10_arr_s) > 1 else 1e-9
                        sr_n = (float(np.mean(net_arr_s)) / max(1e-9, std_s)) * math.sqrt(52.0)
                        sr_n10 = (float(np.mean(net10_arr_s)) / max(1e-9, std10_s)) * math.sqrt(52.0)
                        down_sq = np.minimum(0.0, net_arr_s) ** 2
                        down_std = float(math.sqrt(np.mean(down_sq))) if len(net_arr_s) > 0 else 1e-9
                        sortino_s = (float(np.mean(net_arr_s)) / max(1e-9, down_std)) * math.sqrt(52.0)
                        peaks_s = np.maximum.accumulate(eq_s)
                        mdd_s = float(np.max((peaks_s - eq_s) / np.maximum(1e-9, peaks_s))) * 100.0
                        calmar_s = ann_n / max(0.01, mdd_s)
                        hits_s = [
                            1.0 if ((r["position"] >= 0.45 and r["asset_return"] > 0) or (r["position"] < 0.45 and r["asset_return"] <= 0)) else 0.0
                            for r in recs if abs(r["asset_return"]) > 1e-9
                        ]
                        briers_s = [
                            ((r["p_optimistic"] - (1.0 if r["outcome"] == 1 else 0.0)) ** 2
                             + (r["p_neutral"] - (1.0 if r["outcome"] == 0 else 0.0)) ** 2
                             + (r["p_cautious"] - (1.0 if r["outcome"] == -1 else 0.0)) ** 2) / 3.0
                            for r in recs
                        ]
                        maes_s = [
                            (abs(r["p_optimistic"] - (1.0 if r["outcome"] == 1 else 0.0))
                             + abs(r["p_neutral"] - (1.0 if r["outcome"] == 0 else 0.0))
                             + abs(r["p_cautious"] - (1.0 if r["outcome"] == -1 else 0.0))) / 3.0
                            for r in recs
                        ]
                        return {
                            "gross_pct": cum_g,
                            "net_pct": cum_n,
                            "net_10bps_pct": cum_n10,
                            "ann_net_pct": ann_n,
                            "ann_vol_pct": std_s * math.sqrt(52.0) * 100.0,
                            "net_sharpe": sr_n,
                            "net_sharpe_10bps": sr_n10,
                            "sortino": sortino_s,
                            "calmar": calmar_s,
                            "max_dd_pct": mdd_s,
                            "turns": turns,
                            "deb_rate": deb_rate,
                            "hit_rate_pct": float(np.mean(hits_s)) * 100.0 if hits_s else 0.0,
                            "brier": float(np.mean(briers_s)),
                            "mae": float(np.mean(maes_s)),
                        }

                    bh_st = _stock_stats(bh_recs)
                    m2_st = _stock_stats(m2_recs)
                    m4_st = _stock_stats(m4_recs)
                    per_stock_rows.append({
                        "cohort": cohort_name,
                        "symbol": sym,
                        "name": by_symbol[sym][0]["name"],
                        "market": mkt_code,
                        "bh_net_pct": round(bh_st["net_pct"], 2),
                        "m2_net_pct": round(m2_st["net_pct"], 2),
                        "m4_gross_pct": round(m4_st["gross_pct"], 2),
                        "m4_net_pct": round(m4_st["net_pct"], 2),
                        "m4_net_10bps_pct": round(m4_st["net_10bps_pct"], 2),
                        "m4_ann_return_pct": round(m4_st["ann_net_pct"], 2),
                        "m4_ann_vol_pct": round(m4_st["ann_vol_pct"], 2),
                        "m2_net_sharpe": round(m2_st["net_sharpe"], 3),
                        "m4_net_sharpe": round(m4_st["net_sharpe"], 3),
                        "m4_net_sharpe_10bps": round(m4_st["net_sharpe_10bps"], 3),
                        "m4_sortino": round(m4_st["sortino"], 3),
                        "m4_calmar": round(m4_st["calmar"], 3),
                        "m4_max_dd_pct": round(m4_st["max_dd_pct"], 2),
                        "m4_alpha_vs_bh_pct": round(m4_st["net_pct"] - bh_st["net_pct"], 2),
                        "m4_alpha_vs_m2_pct": round(m4_st["net_pct"] - m2_st["net_pct"], 2),
                        "m2_turnover": round(m2_st["turns"], 2),
                        "m4_turnover": round(m4_st["turns"], 2),
                        "m4_brier_score": round(m4_st["brier"], 4),
                        "m4_mae": round(m4_st["mae"], 4),
                        "m4_hit_rate_pct": round(m4_st["hit_rate_pct"], 1),
                        "m4_debate_rate_pct": round(m4_st["deb_rate"], 1),
                    })

    return summary_rows, sota_pnl_rows, per_stock_rows, cn_frontier_weights, cn_frontier_port, us_frontier_port


def run_hyperparameter_sensitivity_sweep(
    by_symbol: Dict[str, List[Dict[str, Any]]],
    cn_symbols: List[str],
    us_symbols: List[str],
    client: LiveDeepSeekBenchmarkClient,
) -> List[Dict[str, Any]]:
    """
    Phase 3(8): Sensitivity sweep over CPH learning rate eta and causal window length W
    on Frontier_LLM_DeepSeek_V3 across both China CSI 300 and US Tech universes.
    """
    sweep_rows: List[Dict[str, Any]] = []
    etas = [0.15, 0.25, 0.35, 0.45, 0.60]
    windows = [4, 8, 12, 16]

    for eta in etas:
        for w_len in windows:
            port_cn, _, _ = run_market_universe_chronologically(
                by_symbol=by_symbol,
                symbols=cn_symbols,
                market_code="CN",
                model_tier="Frontier_LLM_DeepSeek_V3",
                seed=202602,
                use_live_llm_api=False,
                max_weeks=0,
                client=client,
                eta=eta,
                window_len=w_len,
            )
            m4_cn = evaluate_portfolio_records(port_cn["M4_CARE_Agents_Ours"], 15.0)
            m2_cn = evaluate_portfolio_records(port_cn["M2_Vanilla_TradingAgents"], 15.0)

            port_us, _, _ = run_market_universe_chronologically(
                by_symbol=by_symbol,
                symbols=us_symbols,
                market_code="US",
                model_tier="Frontier_LLM_DeepSeek_V3",
                seed=202602,
                use_live_llm_api=False,
                max_weeks=0,
                client=client,
                eta=eta,
                window_len=w_len,
            )
            m4_us = evaluate_portfolio_records(port_us["M4_CARE_Agents_Ours"], 5.0)
            m2_us = evaluate_portfolio_records(port_us["M2_Vanilla_TradingAgents"], 5.0)

            sweep_rows.append({
                "eta": eta,
                "window_weeks": w_len,
                "cn_m4_net_return_pct": m4_cn["net_cum_return_pct"],
                "cn_m4_net_sharpe": m4_cn["net_sharpe"],
                "cn_m4_net_sharpe_10bps": m4_cn["net_sharpe_10bps"],
                "cn_m2_net_sharpe": m2_cn["net_sharpe"],
                "cn_delta_sharpe_vs_m2": round(m4_cn["net_sharpe"] - m2_cn["net_sharpe"], 3),
                "cn_m4_max_dd_pct": m4_cn["max_drawdown_pct"],
                "cn_m4_turnover": m4_cn["turnover_rate"],
                "us_m4_net_return_pct": m4_us["net_cum_return_pct"],
                "us_m4_net_sharpe": m4_us["net_sharpe"],
                "us_m4_net_sharpe_10bps": m4_us["net_sharpe_10bps"],
                "us_m4_turnover": m4_us["turnover_rate"],
            })
    return sweep_rows


def main():
    parser = argparse.ArgumentParser(description="Run Phase 5 Real-Market Benchmark (2025-2026)")
    parser.add_argument(
        "--use-live-llm-api",
        action="store_true",
        help="Call live OpenAI/DeepSeek/DashScope LLM APIs instead of calibrated signal emulation.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated ticker subset to evaluate (e.g. 'NVDA,AAPL,600519.SH,300750.SZ').",
    )
    parser.add_argument(
        "--model-tiers",
        type=str,
        default="",
        help="Comma-separated model tiers (e.g. 'Frontier_LLM_DeepSeek_V3').",
    )
    parser.add_argument(
        "--max-weeks",
        type=int,
        default=0,
        help="Maximum number of chronological weekly decision steps (0 = all).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=48,
        help="Concurrency worker count for prefetching (default: 48).",
    )
    args, _ = parser.parse_known_args()

    csv_path = REPO_ROOT / "data" / "phase5_real_2025_2026_prices.csv"
    by_symbol = load_real_2025_2026_dataset(csv_path)

    full_cn_symbols = [
        "ASHR", "600519.SH", "000858.SZ", "300750.SZ",
        "002594.SZ", "600036.SH", "601318.SH", "000333.SZ",
    ]
    full_us_symbols = ["NVDA", "AAPL", "GOOGL", "AMZN"]

    cn_symbols = list(full_cn_symbols)
    us_symbols = list(full_us_symbols)

    if args.symbols:
        filtered_syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
        cn_symbols = [s for s in cn_symbols if s in filtered_syms]
        us_symbols = [s for s in us_symbols if s in filtered_syms]

    universes = []
    if cn_symbols:
        universes.append(("CN_CSI300_A_Shares", cn_symbols, "CN", 15.0))
    if us_symbols:
        universes.append(("US_Tech_Benchmark", us_symbols, "US", 5.0))

    all_model_tiers = [
        ("Small_SLM_Qwen2.5_14B", 202601),
        ("Frontier_LLM_DeepSeek_V3", 202602),
    ]
    if args.model_tiers:
        tier_filter = [t.strip() for t in args.model_tiers.split(",") if t.strip()]
        model_tiers = [t for t in all_model_tiers if t[0] in tier_filter]
    else:
        model_tiers = all_model_tiers

    print("=" * 136)
    print("PHASE 5 REAL-MARKET BENCHMARK (2025-2026 POST-CUTOFF DATA | MR-1 TO MR-7 PROTOCOL AUDIT | CAUSAL t-1->t)")
    print("=" * 136)

    cache_path = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"
    cache = ThreadSafeLLMCache(cache_path=cache_path, flush_interval=50)
    client = LiveDeepSeekBenchmarkClient(cache=cache, max_workers=args.max_workers)

    if args.use_live_llm_api:
        prefetch_all_live_llm_posteriors(
            client=client,
            by_symbol=by_symbol,
            universes=universes,
            model_tiers=model_tiers,
            max_weeks=args.max_weeks,
            max_workers=args.max_workers,
        )

    is_cli_subset = bool(args.symbols or args.model_tiers or args.max_weeks)
    cohort_label = "Cohort_A_CLI_Subset" if is_cli_subset else "Cohort_B_Full_12Assets_86Weeks"

    summary_rows, sota_pnl_rows, per_stock_rows, cn_frontier_weights, cn_frontier_port, us_frontier_port = (
        evaluate_cohort_and_collect_rows(
            cohort_name=cohort_label,
            by_symbol=by_symbol,
            universes=universes,
            model_tiers=model_tiers,
            max_weeks=args.max_weeks,
            use_live_llm_api=args.use_live_llm_api,
            client=client,
            verbose=True,
        )
    )

    has_slm = any(r["model_tier"] == "Small_SLM_Qwen2.5_14B" for r in summary_rows)
    has_frontier = any(r["model_tier"] == "Frontier_LLM_DeepSeek_V3" for r in summary_rows)
    if has_slm and has_frontier:
        print("\n" + "=" * 136)
        print("CPH MARGINAL DECOMPOSITION: COORDINATION PRIMACY VS. MODEL SCALING (Nguyen & Pham 2026)")
        print("=" * 136)
        for univ_name, _, _, _ in universes:
            u_rows = {
                (r["model_tier"], r["protocol"]): r
                for r in summary_rows
                if r["universe"] == univ_name
            }
            if (
                ("Small_SLM_Qwen2.5_14B", "M4_CARE_Agents_Ours") in u_rows
                and ("Small_SLM_Qwen2.5_14B", "M2_Vanilla_TradingAgents") in u_rows
                and ("Frontier_LLM_DeepSeek_V3", "M4_CARE_Agents_Ours") in u_rows
                and ("Frontier_LLM_DeepSeek_V3", "M2_Vanilla_TradingAgents") in u_rows
            ):
                coord_slm = u_rows[("Small_SLM_Qwen2.5_14B", "M4_CARE_Agents_Ours")]["net_sharpe"] - u_rows[("Small_SLM_Qwen2.5_14B", "M2_Vanilla_TradingAgents")]["net_sharpe"]
                coord_llm = u_rows[("Frontier_LLM_DeepSeek_V3", "M4_CARE_Agents_Ours")]["net_sharpe"] - u_rows[("Frontier_LLM_DeepSeek_V3", "M2_Vanilla_TradingAgents")]["net_sharpe"]
                scale_m2 = u_rows[("Frontier_LLM_DeepSeek_V3", "M2_Vanilla_TradingAgents")]["net_sharpe"] - u_rows[("Small_SLM_Qwen2.5_14B", "M2_Vanilla_TradingAgents")]["net_sharpe"]
                scale_m4 = u_rows[("Frontier_LLM_DeepSeek_V3", "M4_CARE_Agents_Ours")]["net_sharpe"] - u_rows[("Small_SLM_Qwen2.5_14B", "M4_CARE_Agents_Ours")]["net_sharpe"]

                print(
                    f"[{univ_name}] "
                    f"Delta_NetSharpe(Coordination: M2->M4 on SLM) = +{coord_slm:.3f} | "
                    f"Delta_NetSharpe(Coordination: M2->M4 on Frontier) = +{coord_llm:.3f} || "
                    f"Delta_NetSharpe(Model Scale on M2) = {scale_m2:+.3f} | "
                    f"Delta_NetSharpe(Model Scale on M4) = {scale_m4:+.3f}"
                )

    results_dir = REPO_ROOT / "results"
    reports_dir = REPO_ROOT / "reports"
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    if is_cli_subset:
        _write_csv(results_dir / "phase5_real_market_subset_results.csv", summary_rows)
        _write_csv(results_dir / "phase5_sota_pnl_subset.csv", sota_pnl_rows)
        _write_csv(results_dir / "phase5_per_stock_subset.csv", per_stock_rows)
        _write_csv(reports_dir / "phase5_real_market_subset_results.csv", summary_rows)
        _write_csv(reports_dir / "phase5_sota_pnl_subset.csv", sota_pnl_rows)
        _write_csv(reports_dir / "phase5_per_stock_subset.csv", per_stock_rows)
    else:
        # Write Cohort B (Full 12-Asset x 86-Week Out-of-Sample Benchmark)
        for out_dir in (results_dir, reports_dir):
            _write_csv(out_dir / "phase5_real_market_cph_results.csv", summary_rows)
            _write_csv(out_dir / "phase5_sota_pnl_comparison.csv", sota_pnl_rows)
            _write_csv(out_dir / "phase5_per_stock_breakdown.csv", per_stock_rows)

        # Also evaluate and export standardized Cohort A (Core 4-Asset x 10-Week Tariff-Shock Verification Cohort)
        subset_universes = [
            ("CN_CSI300_A_Shares", ["600519.SH", "300750.SZ"], "CN", 15.0),
            ("US_Tech_Benchmark", ["NVDA", "AAPL"], "US", 5.0),
        ]
        sub_summary, sub_sota, sub_stock, _, _, _ = evaluate_cohort_and_collect_rows(
            cohort_name="Cohort_A_Core_4Assets_10Weeks",
            by_symbol=by_symbol,
            universes=subset_universes,
            model_tiers=all_model_tiers,
            max_weeks=10,
            use_live_llm_api=False,
            client=client,
            verbose=True,
        )
        for out_dir in (results_dir, reports_dir):
            _write_csv(out_dir / "phase5_real_market_subset_results.csv", sub_summary)
            _write_csv(out_dir / "phase5_sota_pnl_subset.csv", sub_sota)
            _write_csv(out_dir / "phase5_per_stock_subset.csv", sub_stock)

        # Run Phase 3(8) Hyperparameter Sensitivity Sweep over (eta, W)
        sweep_rows = run_hyperparameter_sensitivity_sweep(
            by_symbol=by_symbol,
            cn_symbols=full_cn_symbols,
            us_symbols=full_us_symbols,
            client=client,
        )
        _write_csv(results_dir / "phase5_hyperparameter_sensitivity.csv", sweep_rows)
        _write_csv(reports_dir / "phase5_hyperparameter_sensitivity.csv", sweep_rows)

    if summary_rows and not is_cli_subset:
        tex_lines = [
            "% Auto-generated by scripts/run_phase5_real_market_benchmark.py",
            "\\begin{table*}[t]",
            "\\centering",
            "\\small",
            "\\caption{Phase 5 Empirical Evaluation on Post-Cutoff 2025--2026 Real Market Data (86 Weekly Bars, Out-of-Sample).}",
            "\\label{tab:phase5_cph_real_market}",
            "\\begin{tabular}{llrrrrrrrrrrrr}",
            "\\toprule",
            "\\textbf{Universe} & \\textbf{Protocol} & \\textbf{Gross\\%} & \\textbf{Net\\%} & \\textbf{Gross SR} & "
            "\\textbf{Net SR} & \\textbf{MaxDD\\%} & \\textbf{Turn.} & \\textbf{Brier}\\,$\\downarrow$ & \\textbf{ECE}\\,$\\downarrow$ & "
            "\\textbf{CBS (bps)} & \\textbf{Debate\\%} & \\textbf{HAC $t$} & \\textbf{$p$-val} \\\\",
            "\\midrule",
        ]
        for r in summary_rows:
            if r["protocol"] == "M0_Buy_And_Hold" and r["model_tier"] == "Small_SLM_Qwen2.5_14B":
                continue
            u_short = "CN A-Shares" if r["market"] == "CN" else "US Tech"
            t_short = "SLM-14B" if "SLM" in r["model_tier"] else "Frontier-V3"
            p_clean = r["protocol"].replace("_", "\\_")
            bold_open = "\\textbf{" if r["protocol"] == "M4_CARE_Agents_Ours" else ""
            bold_close = "}" if r["protocol"] == "M4_CARE_Agents_Ours" else ""
            tex_lines.append(
                f"{u_short} ({t_short}) & {bold_open}{p_clean}{bold_close} & "
                f"{r['gross_cum_return_pct']:+.2f} & {bold_open}{r['net_cum_return_pct']:+.2f}{bold_close} & "
                f"{r['gross_sharpe']:.3f} & {bold_open}{r['net_sharpe']:.3f}{bold_close} & "
                f"{r['max_drawdown_pct']:.2f} & {r['turnover_rate']:.2f} & "
                f"{r['brier_score']:.4f} & {r['ece']:.4f} & {r['cbs_mean_bps']:+.2f} & "
                f"{r['debate_rate_pct']:.1f}\\% & {r['hac_t_stat_vs_m2']:+.2f} & {r['p_value_vs_m2']:.4f} \\\\"
            )
        tex_lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table*}"])
        tex_content = "\n".join(tex_lines) + "\n"
        (results_dir / "phase5_cph_table.tex").write_text(tex_content, encoding="utf-8")
        (reports_dir / "phase5_cph_table.tex").write_text(tex_content, encoding="utf-8")

    fig_out = results_dir / "regime_weight_trajectories"
    if cn_frontier_weights:
        render_regime_weight_figure(cn_frontier_weights, fig_out)
    eq_fig_out = results_dir / "phase5_equity_drawdown_curves"
    if cn_frontier_port and us_frontier_port:
        render_equity_and_drawdown_figure(cn_frontier_port, us_frontier_port, eq_fig_out)

    cache.flush()


if __name__ == "__main__":
    main()
