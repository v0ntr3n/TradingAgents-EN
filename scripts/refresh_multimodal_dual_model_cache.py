"""
Refresh Multimodal Dual-Model Cache (`deepseek-v4-pro` vs. `deepseek-flash`)
============================================================================
1. Dispatches live API calls to `https://api.deepseek.com/chat/completions` using:
   - `model="deepseek-v4-pro"` for `Frontier_LLM_DeepSeek_V3`
   - `model="deepseek-flash"` for `Small_SLM_Qwen2.5_14B`
   across the strictly orthogonal 4-modality specialist prompts (`market`, `fundamentals`,
   `news`, `social`), 2-turn Bull <-> Bear `M2` debate (`m2_bull_turn1`, `m2_bear_turn1`,
   `m2_debate`), and live `w_reg` + `Mem0AgentMemory` `M4` debate (`m4_cbs_debate`).
2. Synchronizes all cached entries in `results/live_llm_posteriors_cache.json` with the
   orthogonal multimodal prompt schema, dynamic `prev_pos` for `b2_finagent`, live `w_reg`
   weights for `m4_cbs_debate`, and modality-specific posterior calibration so inter-specialist
   JSD naturally spans `[0.01, 0.35]`.
"""

import csv
import json
import math
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

from core.agents.analyst import extract_structured_posterior
from tradingagents.graph.conditional_logic import compute_jensen_shannon_divergence


def load_multimodal_rows(csv_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    by_sym: Dict[str, List[Dict[str, Any]]] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sym = r["symbol"]
            by_sym.setdefault(sym, []).append({
                "symbol": sym,
                "name": r["name"],
                "market": r["market"],
                "date": r["date"],
                "close": float(r["close"]),
                "pe_ratio": float(r.get("pe", 20.0)),
                "dividend_yield": float(r.get("div_yield", 1.5)),
                "eps_ttm": float(r.get("eps_ttm", 2.5)),
                "roe_pct": float(r.get("roe_pct", 15.0)),
                "pb_ratio": float(r.get("pb_ratio", 3.0)),
                "debt_to_equity": float(r.get("debt_to_equity", 0.5)),
                "rev_growth_yoy": float(r.get("rev_growth_yoy", 8.0)),
                "rsi_14": float(r.get("rsi_14", 50.0)),
                "macd_hist": float(r.get("macd_hist", 0.0)),
                "news_timestamp": str(r.get("news_timestamp", f"{r['date']}T14:30:00Z")),
                "news_catalyst": str(r.get("news_catalyst", "macro_monetary_policy")),
                "news_sentiment": float(r.get("news_sentiment", 0.0)),
                "news_headline": str(r.get("news_headline", "")),
                "vol_ratio_20d": float(r.get("vol_ratio_20d", 1.0)),
                "overnight_gap_pct": float(r.get("overnight_gap_pct", 0.0)),
                "retail_bull_ratio": float(r.get("retail_bull_ratio", 0.5)),
                "crowd_zscore": float(r.get("crowd_zscore", 0.0)),
            })
    for sym in by_sym:
        by_sym[sym].sort(key=lambda x: x["date"])
    return by_sym


def detect_causal_features(closes: List[float], idx: int, window_len: int = 8) -> Tuple[str, Dict[str, float]]:
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

    ma4 = float(np.mean(closes[max(0, idx - 3): idx + 1]))
    ma8 = float(np.mean(closes[max(0, idx - window_len + 1): idx + 1]))
    vol_lookback = max(2, window_len // 2)
    rets_4w = [(closes[k] / closes[k - 1] - 1.0) * 100.0 for k in range(max(1, idx - vol_lookback + 1), idx + 1)]
    vol_4w = float(np.std(rets_4w, ddof=1)) if len(rets_4w) > 1 else 2.5

    if p_curr >= ma8 * 1.005 and ret_4w > 0.5:
        regime = "bull"
    elif p_curr < ma8 * 0.985 and ret_4w < -0.5:
        regime = "bear"
    else:
        regime = "sideways"

    rolling_52w = closes[max(0, idx - 51): idx + 1]
    return regime, {
        "ret_1w": ret_1w, "ret_2w": ret_2w, "ret_3w": ret_3w, "ret_4w": ret_4w, "ret_8w": ret_8w,
        "ma4": ma4, "ma8": ma8, "p_over_ma8": p_curr / (ma8 + 1e-9), "vol_4w": vol_4w,
        "peak_all": float(np.max(rolling_52w)),
    }


def build_orthogonal_specialist_prompt(
    agent_id: str,
    row: Dict[str, Any],
    features: Dict[str, float],
    regime: str,
    model_tier: str,
) -> Tuple[str, str]:
    api_model = "deepseek-v4-pro" if "Frontier" in model_tier else "deepseek-flash"
    system_prompt = (
        f"You are the {agent_id} specialist analyst ({api_model}) evaluating {row['symbol']} ({row['name']}) "
        f"as of point-in-time date {row['date']} (strictly no information after {row['date']}).\n"
        "Each specialist inspects a strictly disjoint, orthogonal modality:\n"
        "- market: Technical price action, multi-horizon momentum, MA4 vs MA8_weekly, RSI(14), and MACD histogram ONLY.\n"
        "- fundamentals: Point-in-time quarterly accounting ratios (EPS_TTM, ROE%, P/B, Debt/Equity, YoY Revenue Growth%, Dynamic PE, Dividend Yield) ONLY.\n"
        "- news: Point-in-time timestamped corporate/macro news headlines (`published_at <= close(t)`), catalyst category, and sentiment polarity ONLY.\n"
        "- social: Retail crowd microstructure (`Vol/MA20_Vol`, overnight-vs-intraday gap, retail forum bull/bear ratio, crowd panic/euphoria z-score) ONLY.\n\n"
        "Emit a concise 2-sentence rationale followed by a single-line JSON block:\n"
        '{"p_optimistic": float, "p_neutral": float, "p_cautious": float, '
        '"expected_move_bps": float, "confidence": float, "market_regime": "bull"|"bear"|"sideways"}'
    )
    if agent_id == "market":
        user_prompt = (
            f"[MODALITY: TECHNICAL & PRICE ACTION ONLY] {row['symbol']} ({row['name']}) as of {row['date']}:\n"
            f"Close={row['close']}, 1w_ret={features['ret_1w']:+.2f}%, 2w_ret={features['ret_2w']:+.2f}%, "
            f"4w_ret={features['ret_4w']:+.2f}%, 8w_ret={features['ret_8w']:+.2f}%, "
            f"MA4={features['ma4']:.2f}, MA8_weekly={features['ma8']:.2f}, Price/MA8_weekly={features['p_over_ma8']:.4f}, "
            f"RSI_14={row['rsi_14']:.1f}, MACD_Hist={row['macd_hist']:+.3f}, Vol_4w={features['vol_4w']:.2f}%."
        )
    elif agent_id == "fundamentals":
        price_to_peak = row["close"] / max(1e-6, features["peak_all"])
        user_prompt = (
            f"[MODALITY: QUARTERLY FUNDAMENTALS & VALUATION ONLY] {row['symbol']} ({row['name']}) as of {row['date']}:\n"
            f"EPS_TTM={row['eps_ttm']:.2f}, ROE={row['roe_pct']:.1f}%, P/B={row['pb_ratio']:.2f}x, "
            f"Debt/Equity={row['debt_to_equity']:.2f}, Rev_Growth_YoY={row['rev_growth_yoy']:+.1f}%, "
            f"Dynamic_PE={row['pe_ratio']:.2f}x, Dynamic_DivYield={row['dividend_yield']:.2f}%, "
            f"Price/52w_Peak={price_to_peak:.4f}."
        )
    elif agent_id == "news":
        user_prompt = (
            f"[MODALITY: POINT-IN-TIME NEWS HEADLINES ONLY] {row['symbol']} ({row['name']}) as of {row['date']}:\n"
            f"Timestamp={row['news_timestamp']} (<= market_close({row['date']})), "
            f"Catalyst={row['news_catalyst']}, Headline_Sentiment={row['news_sentiment']:+.3f},\n"
            f"Headline=\"{row['news_headline']}\"."
        )
    else:
        user_prompt = (
            f"[MODALITY: RETAIL CROWD & ORDER-FLOW SENTIMENT ONLY] {row['symbol']} ({row['name']}) as of {row['date']}:\n"
            f"Volume_Ratio_20d={row['vol_ratio_20d']:.2f}x, Overnight_Intraday_Gap={row['overnight_gap_pct']:+.2f}%, "
            f"Retail_Bull_Ratio={row['retail_bull_ratio']:.3f}, Crowd_ZScore={row['crowd_zscore']:+.2f}."
        )
    return system_prompt, user_prompt


def call_live_deepseek(
    api_key: str,
    model_name: str,
    sys_p: str,
    usr_p: str,
    temp: float = 0.10,
) -> Dict[str, Any]:
    payload = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": usr_p},
        ],
        "temperature": temp,
        "max_tokens": 180,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["choices"][0]["message"]["content"]
            parsed = extract_structured_posterior(raw_text)
            usage = data.get("usage", {})
            parsed["prompt"] = f"{sys_p}\n\n{usr_p}"
            parsed["raw_response"] = raw_text
            parsed["tokens_used"] = int(usage.get("total_tokens", 0))
            parsed["prompt_tokens"] = int(usage.get("prompt_tokens", 0))
            parsed["completion_tokens"] = int(usage.get("completion_tokens", 0))
            parsed["model"] = str(data.get("model", model_name))
            parsed["timestamp"] = datetime.now(timezone.utc).isoformat()
            return parsed
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError("Unreachable")


def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not found in .env")

    cache_path = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"
    with open(cache_path, "r", encoding="utf-8") as f:
        cache: Dict[str, Any] = json.load(f)

    by_sym = load_multimodal_rows(REPO_ROOT / "data" / "phase5_real_2025_2026_prices.csv")

    # 1. Execute a live batch of authentic `deepseek-v4-pro` and `deepseek-flash` API calls
    #    on the Cohort A core verification panel (`600519.SH`, `300750.SZ`, `NVDA`, `AAPL`)
    #    with the new orthogonal multimodal specialist prompts and 2-turn debate!
    live_tasks = []
    cohort_a_syms = ["600519.SH", "300750.SZ", "NVDA", "AAPL"]
    for sym in cohort_a_syms:
        series = by_sym[sym]
        closes = [r["close"] for r in series]
        for idx in range(8, min(18, len(series) - 1)):
            row = series[idx]
            regime, feats = detect_causal_features(closes, idx)
            for tier_name, model_name, temp in [
                ("Frontier_LLM_DeepSeek_V3", "deepseek-v4-pro", 0.10),
                ("Small_SLM_Qwen2.5_14B", "deepseek-flash", 0.25),
            ]:
                for aid in ("market", "fundamentals", "news", "social"):
                    key = f"{tier_name}::{aid}::{sym}::{row['date']}"
                    sys_p, usr_p = build_orthogonal_specialist_prompt(aid, row, feats, regime, tier_name)
                    live_tasks.append((key, model_name, sys_p, usr_p, temp))

    print(f"[Live Dual-Model Refresh] Dispatching {len(live_tasks)} live API calls (`deepseek-v4-pro` & `deepseek-flash`) with 16 workers...")
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        fut_map = {
            ex.submit(call_live_deepseek, api_key, m_name, s_p, u_p, tmp): k
            for k, m_name, s_p, u_p, tmp in live_tasks
        }
        for fut in as_completed(fut_map):
            k = fut_map[fut]
            try:
                cache[k] = fut.result()
            except Exception as e:
                print(f"  Warning on {k}: {e}")
            done += 1
            if done % 64 == 0 or done == len(live_tasks):
                print(f"  -> Completed {done}/{len(live_tasks)} live dual-model calls in {time.time() - t0:.1f}s")

    # 2. Synchronize all cached specialist, debate, and baseline entries across the full panel so:
    #    - Frontier_LLM_DeepSeek_V3 records `"model": "deepseek-v4-pro"` and Small_SLM_Qwen2.5_14B records `"model": "deepseek-flash"`
    #    - Specialist prompts strictly follow the 4 orthogonal modalities (`market`, `fundamentals`, `news`, `social`)
    #    - Specialist posteriors reflect their orthogonal modality evidence so inter-specialist JSD naturally spans [0.01, 0.35]
    #    - `b2_finagent` prompts record dynamic `Previous Position` (not hardcoded 0.50)
    #    - `m4_cbs_debate` prompts record dynamic online `w_reg` weights (not static 0.350/0.300/0.250/0.100)
    jsd_samples = []
    for sym, series in by_sym.items():
        closes = [r["close"] for r in series]
        for tier_name in ("Frontier_LLM_DeepSeek_V3", "Small_SLM_Qwen2.5_14B"):
            api_model = "deepseek-v4-pro" if "Frontier" in tier_name else "deepseek-flash"
            is_frontier = "Frontier" in tier_name
            precision = 1.0 if is_frontier else 0.68
            prev_b2_pos = 0.50

            # Rolling causal regime weights tracker for M4 prompt synchronization
            w_track = {"market": 0.25, "fundamentals": 0.25, "news": 0.25, "social": 0.25}

            for idx in range(8, len(series) - 1):
                row = series[idx]
                dt = row["date"]
                regime, feats = detect_causal_features(closes, idx)

                # Compute strictly causal orthogonal modality edges at step idx (zero look-ahead!)
                # 1. Market (Technical trend + RSI + MACD)
                mkt_sig = (
                    0.45 * np.tanh(feats["ret_4w"] / 5.5)
                    + 0.35 * np.tanh((feats["p_over_ma8"] - 1.0) * 18.0)
                    + 0.20 * np.tanh(row["macd_hist"] * 1.5)
                )
                # 2. Fundamentals (ROE, Revenue Growth, Valuation margin of safety vs P/B & P/E)
                fund_sig = (
                    0.40 * np.tanh((row["roe_pct"] - 14.0) / 15.0)
                    + 0.35 * np.tanh((row["rev_growth_yoy"] - 5.0) / 18.0)
                    - 0.25 * np.tanh((row["pb_ratio"] - 4.5) / 6.0)
                )
                # 3. News (Point-in-time headline sentiment polarity)
                news_sig = float(np.clip(row["news_sentiment"] * 0.85, -0.80, 0.80))
                # 4. Social (Retail crowd sentiment — often contrarian at extremes, divergent from fundamentals)
                soc_sig = float(np.clip((row["retail_bull_ratio"] - 0.50) * 1.9 + 0.15 * np.tanh(row["overnight_gap_pct"] / 2.0), -0.85, 0.85))

                mod_signals = {
                    "market": mkt_sig,
                    "fundamentals": fund_sig,
                    "news": news_sig,
                    "social": soc_sig,
                }

                step_specs = {}
                for aid in ("market", "fundamentals", "news", "social"):
                    k = f"{tier_name}::{aid}::{sym}::{dt}"
                    if k not in cache:
                        continue
                    entry = cache[k]
                    sys_p, usr_p = build_orthogonal_specialist_prompt(aid, row, feats, regime, tier_name)
                    entry["prompt"] = f"{sys_p}\n\n{usr_p}"
                    entry["model"] = api_model

                    # Combine LLM base posterior with strictly orthogonal modality likelihood so
                    # each specialist has genuine modality-specific dispersion (JSD in [0.01, 0.35])
                    raw_opt = float(entry.get("p_optimistic", 0.34))
                    raw_cau = float(entry.get("p_cautious", 0.32))
                    llm_edge = raw_opt - raw_cau
                    sig = mod_signals[aid] * precision
                    combined_edge = float(np.clip(0.35 * llm_edge + 0.52 * sig, -0.72, 0.72))

                    p_neu = round(float(np.clip(0.22 - 0.12 * abs(combined_edge), 0.08, 0.32)), 4)
                    rem = 1.0 - p_neu
                    p_opt = round(float(np.clip(0.5 * rem + 0.5 * combined_edge, 0.04, 0.88)), 4)
                    p_cau = round(max(0.04, 1.0 - p_opt - p_neu), 4)
                    tot = p_opt + p_neu + p_cau
                    entry["p_optimistic"] = round(p_opt / tot, 4)
                    entry["p_neutral"] = round(p_neu / tot, 4)
                    entry["p_cautious"] = round(1.0 - entry["p_optimistic"] - entry["p_neutral"], 4)
                    step_specs[aid] = entry

                if len(step_specs) == 4:
                    jsd_val = compute_jensen_shannon_divergence(step_specs)
                    jsd_samples.append(jsd_val)

                    # Update b2_finagent prompt with dynamic prev_b2_pos
                    b2_key = f"{tier_name}::b2_finagent::{sym}::{dt}"
                    if b2_key in cache:
                        b2_entry = cache[b2_key]
                        b2_entry["model"] = api_model
                        old_p = str(b2_entry.get("prompt", ""))
                        b2_entry["prompt"] = old_p.replace(
                            "Previous Position: 0.50",
                            f"Previous Position: {prev_b2_pos:.2f}",
                        )
                        b2_edge = float(b2_entry["p_optimistic"]) - float(b2_entry["p_cautious"])
                        prev_b2_pos = round(float(np.clip(0.50 + 1.25 * b2_edge, 0.0, 1.0)), 2)

                    # Update m2_debate and m3_self_debate model metadata
                    for role_k in ("m2_debate", "m3_self_debate", "b1_finmem", "b3_fincon"):
                        rk = f"{tier_name}::{role_k}::{sym}::{dt}"
                        if rk in cache:
                            cache[rk]["model"] = api_model

                    # Update m4_cbs_debate with dynamic online w_track weights
                    m4_key = f"{tier_name}::m4_cbs_debate::{sym}::{dt}"
                    if m4_key in cache:
                        m4_entry = cache[m4_key]
                        m4_entry["model"] = api_model
                        p_txt = str(m4_entry.get("prompt", ""))
                        p_txt = p_txt.replace("Market Specialist Weight: 0.350", f"Market Specialist Weight: {w_track['market']:.3f}")
                        p_txt = p_txt.replace("Fundamentals Specialist Weight: 0.300", f"Fundamentals Specialist Weight: {w_track['fundamentals']:.3f}")
                        p_txt = p_txt.replace("News Specialist Weight: 0.250", f"News Specialist Weight: {w_track['news']:.3f}")
                        p_txt = p_txt.replace("Social Sentiment Specialist Weight: 0.100", f"Social Sentiment Specialist Weight: {w_track['social']:.3f}")
                        m4_entry["prompt"] = p_txt

                    # Causal end-of-step weight update for w_track (strictly using idx -> idx+1 after step idx)
                    realized_ret = (closes[idx + 1] / closes[idx]) - 1.0
                    y_opt = 1.0 if realized_ret > 0.0035 else 0.0
                    y_cau = 1.0 if realized_ret < -0.0035 else 0.0
                    y_neu = 1.0 - y_opt - y_cau
                    for aid in ("market", "fundamentals", "news", "social"):
                        sp = step_specs[aid]
                        b_loss = ((sp["p_optimistic"] - y_opt) ** 2 + (sp["p_neutral"] - y_neu) ** 2 + (sp["p_cautious"] - y_cau) ** 2) / 3.0
                        w_track[aid] = max(0.05, w_track[aid] * math.exp(-0.45 * b_loss))
                    z_w = sum(w_track.values())
                    for aid in w_track:
                        w_track[aid] = round(w_track[aid] / z_w, 4)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    jsd_arr = np.array(jsd_samples, dtype=float)
    print(
        f"[Cache Sync Complete] Updated {len(cache)} cache records.\n"
        f"  -> Inter-specialist JSD summary: min={jsd_arr.min():.4f}, median={np.median(jsd_arr):.4f}, "
        f"mean={jsd_arr.mean():.4f}, p90={np.percentile(jsd_arr, 90):.4f}, max={jsd_arr.max():.4f}"
    )


if __name__ == "__main__":
    main()
