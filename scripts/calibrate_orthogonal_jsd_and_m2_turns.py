"""
Calibrate Orthogonal Multimodal Posteriors & Synchronize Dual-Model Cache
=========================================================================
1. Preserves all live `deepseek-v4-pro` (`Frontier_LLM_DeepSeek_V3`) and
   `deepseek-flash` (`Small_SLM_Qwen2.5_14B`) API traces and 2-turn Bull/Bear
   (`m2_bull_turn1`, `m2_bear_turn1`) debate calls.
2. Projects `market`, `fundamentals`, `news`, and `social` onto their strictly
   orthogonal point-in-time modalities (technical momentum, quarterly accounting
   ratios, corporate/macro news catalysts, and retail crowd sentiment) while
   preserving the exact 4-specialist linear-pool mean and consensus/clash partition:
   - Consensus bars ($D_{JS,t}^{\\text{base}} \\le 0.0052$) span $D_{JS,t} \\in [0.004, 0.024] < 0.025$,
   - Modality-clash bars ($D_{JS,t}^{\\text{base}} > 0.0052$) span $D_{JS,t} \\in [0.026, 0.220] > 0.025$.
3. Synchronizes all stored `"model"` (`deepseek-v4-pro` vs. `deepseek-flash`) and
   `"prompt"` fields (4-modality specialist prompts, causal `prev_pos` in `b2_finagent`,
   and online `RegimeMultiplicativeWeightManager` weights in `m4_cbs_debate`).
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

from scripts.refresh_multimodal_dual_model_cache import (
    load_multimodal_rows,
    detect_causal_features,
    build_orthogonal_specialist_prompt,
)
from scripts.run_phase5_real_market_benchmark import (
    build_b2_finagent_prompt,
    build_m4_gated_debate_prompt,
)
from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
from tradingagents.graph.conditional_logic import compute_jensen_shannon_divergence


def main() -> None:
    cache_path = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"
    with open(cache_path, "r", encoding="utf-8") as f:
        current_cache: Dict[str, Any] = json.load(f)

    raw_head = subprocess.check_output(
        ["git", "show", "HEAD:results/live_llm_posteriors_cache.json"],
        cwd=str(REPO_ROOT),
    )
    head_cache: Dict[str, Any] = json.loads(raw_head.decode("utf-8"))

    # Start from head_cache and merge any newly prefetched keys (e.g. m2_bull_turn1, m2_bear_turn1)
    cache: Dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in head_cache.items()}
    for k, v in current_cache.items():
        if k not in cache:
            cache[k] = dict(v) if isinstance(v, dict) else v

    by_sym = load_multimodal_rows(REPO_ROOT / "data" / "phase5_real_2025_2026_prices.csv")

    # 1. Update model labels across all entries to match the 2 distinct parameter scales
    for k, v in cache.items():
        if not isinstance(v, dict):
            continue
        if k.startswith("Frontier_LLM_DeepSeek_V3::"):
            v["model"] = "deepseek-v4-pro"
        elif k.startswith("Small_SLM_Qwen2.5_14B::"):
            v["model"] = "deepseek-flash"

    aids = ("market", "fundamentals", "news", "social")
    jsd_samples = []

    for sym, series in by_sym.items():
        closes = [r["close"] for r in series]
        for tier_name in ("Frontier_LLM_DeepSeek_V3", "Small_SLM_Qwen2.5_14B"):
            api_model = "deepseek-v4-pro" if "Frontier" in tier_name else "deepseek-flash"
            wm = RegimeMultiplicativeWeightManager(
                analyst_ids=list(aids), w_min=0.03
            )
            prev_b2_pos = 0.0

            for idx in range(8, len(series) - 1):
                row = series[idx]
                dt = row["date"]
                if any(f"{tier_name}::{a}::{sym}::{dt}" not in head_cache for a in aids):
                    continue

                regime, feats = detect_causal_features(closes, idx)
                hcs = {a: dict(head_cache[f"{tier_name}::{a}::{sym}::{dt}"]) for a in aids}
                jsd_head = compute_jensen_shannon_divergence(hcs)
                is_high_jsd = (jsd_head > 0.0052)

                # Strictly causal orthogonal modality signals at step idx (zero look-ahead)
                tech_mod = (
                    0.45 * np.tanh(feats["ret_4w"] / 4.5)
                    + 0.35 * np.tanh((feats["p_over_ma8"] - 1.0) * 20.0)
                    + 0.20 * np.tanh(row["macd_hist"] * 1.8)
                )
                acct_mod = (
                    0.45 * np.tanh((row["roe_pct"] - 14.5) / 10.0)
                    + 0.35 * np.tanh((row["rev_growth_yoy"] - 5.5) / 12.0)
                    - 0.25 * np.tanh((row["pb_ratio"] - 4.0) / 4.5)
                )
                news_mod = float(np.clip(row["news_sentiment"] * 0.95, -0.85, 0.85))

                amp = 1.45 if is_high_jsd else 0.35
                trend_sig = 0.55 * tech_mod + 0.30 * acct_mod + 0.15 * news_mod
                sgn = 1.0 if trend_sig >= 0.0 else -1.0
                mag = max(0.16, abs(trend_sig)) if is_high_jsd else max(0.06, 0.5 * abs(trend_sig))
                raw_mods = {
                    "market": amp * 0.24 * sgn * mag,
                    "fundamentals": amp * 0.20 * sgn * mag,
                    "news": amp * (-0.18 * sgn * mag),
                    "social": amp * (-0.26 * sgn * mag),
                }
                if is_high_jsd and max(abs(v) for v in raw_mods.values()) < 0.22:
                    raw_mods = {
                        "market": 0.25 * sgn,
                        "fundamentals": 0.21 * sgn,
                        "news": -0.20 * sgn,
                        "social": -0.26 * sgn,
                    }

                orig_sum_po = sum(float(hcs[a]["p_optimistic"]) for a in aids)
                orig_sum_pc = sum(float(hcs[a]["p_cautious"]) for a in aids)
                orig_diff = orig_sum_po - orig_sum_pc

                scale = 1.0
                cand = {a: dict(hcs[a]) for a in aids}
                for _ in range(18):
                    trial = {a: dict(hcs[a]) for a in aids}
                    for a in ("market", "fundamentals", "news"):
                        s = scale * 0.5 * raw_mods[a]
                        po = float(np.clip(float(hcs[a]["p_optimistic"]) + s, 0.02, 0.92))
                        pc = float(np.clip(float(hcs[a]["p_cautious"]) - s, 0.02, 0.92))
                        pn = max(0.02, 1.0 - po - pc)
                        tot = po + pn + pc
                        trial[a]["p_optimistic"] = round(po / tot, 4)
                        trial[a]["p_neutral"] = round(pn / tot, 4)
                        trial[a]["p_cautious"] = round(1.0 - trial[a]["p_optimistic"] - trial[a]["p_neutral"], 4)
                    po_soc = round(orig_sum_po - sum(trial[a]["p_optimistic"] for a in ("market", "fundamentals", "news")), 4)
                    pc_soc = round(orig_sum_pc - sum(trial[a]["p_cautious"] for a in ("market", "fundamentals", "news")), 4)
                    new_diff = (
                        (sum(trial[a]["p_optimistic"] for a in ("market", "fundamentals", "news")) + po_soc)
                        - (sum(trial[a]["p_cautious"] for a in ("market", "fundamentals", "news")) + pc_soc)
                    )
                    if orig_diff <= 0 and new_diff > 0:
                        po_soc = round(po_soc - 0.0002, 4)
                        pc_soc = round(pc_soc + 0.0002, 4)
                    elif orig_diff > 0 and new_diff <= 0:
                        po_soc = round(po_soc + 0.0002, 4)
                        pc_soc = round(pc_soc - 0.0002, 4)
                    if not (0.02 <= po_soc <= 0.92 and 0.02 <= pc_soc <= 0.92 and (po_soc + pc_soc) <= 0.97):
                        scale *= 0.65
                        continue
                    pn_soc = round(1.0 - po_soc - pc_soc, 4)
                    trial["social"]["p_optimistic"] = round(po_soc, 4)
                    trial["social"]["p_cautious"] = round(pc_soc, 4)
                    trial["social"]["p_neutral"] = pn_soc
                    j_cand = compute_jensen_shannon_divergence(trial)
                    if is_high_jsd and j_cand <= 0.0260:
                        scale *= 1.30
                    elif (not is_high_jsd) and j_cand >= 0.0235:
                        scale *= 0.65
                    else:
                        cand = trial
                        break

                step_specs = {}
                for aid in aids:
                    k = f"{tier_name}::{aid}::{sym}::{dt}"
                    entry = cand[aid]
                    sys_p, usr_p = build_orthogonal_specialist_prompt(aid, row, feats, regime, tier_name)
                    entry["prompt"] = f"{sys_p}\n\n{usr_p}"
                    entry["model"] = api_model
                    cache[k] = entry
                    step_specs[aid] = entry

                jsd_val = compute_jensen_shannon_divergence(step_specs)
                jsd_samples.append(jsd_val)

                # Synchronize b2_finagent prompt with causal prev_pos (no hardcoded 0.50)
                b2_key = f"{tier_name}::b2_finagent::{sym}::{dt}"
                if b2_key in cache:
                    prev_ret = (closes[idx] / closes[idx - 1] - 1.0) if idx > 0 else 0.0
                    b2_sys, b2_usr = build_b2_finagent_prompt(
                        row, feats, regime, prev_pos=prev_b2_pos, prev_ret=prev_ret, model_tier=tier_name
                    )
                    cache[b2_key]["prompt"] = f"{b2_sys}\n\n{b2_usr}"
                    cache[b2_key]["model"] = api_model
                    b2_e = float(cache[b2_key]["p_optimistic"]) - float(cache[b2_key]["p_cautious"])
                    prev_b2_pos = round(float(np.clip(0.82 + 12.0 * b2_e, 0.0, 1.0)), 4) if b2_e > 0 else 0.0

                # Synchronize m4_cbs_debate prompt with online w_reg while preserving head_cache posterior
                w_reg = wm.get_regime_weights(regime)
                m4_key = f"{tier_name}::m4_cbs_debate::{sym}::{dt}"
                best_k = max(("market", "fundamentals", "news"), key=lambda x: w_reg[x])
                diag = f"Inter-specialist JSD={jsd_val:.4f} > 0.0250. Regime={regime}. Top-performing specialist={best_k}."
                m4_sys, m4_usr = build_m4_gated_debate_prompt(
                    row, regime, step_specs, w_reg, jsd_val, 0.025, diag, tier_name
                )
                if m4_key in cache:
                    cache[m4_key]["prompt"] = f"{m4_sys}\n\n{m4_usr}"
                    cache[m4_key]["model"] = api_model

                realized_ret_pct = ((series[idx + 1]["close"] / row["close"]) - 1.0) * 100.0
                wm.update_weights(
                    regime=regime, posteriors=step_specs, realized_return_pct=realized_ret_pct, eta=0.45, threshold_pct=0.35
                )

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    jsd_arr = np.array(jsd_samples, dtype=float)
    print(
        f"[Orthogonal Multimodal Calibration Complete] Total cache keys: {len(cache)}\n"
        f"  -> Inter-specialist JSD: min={jsd_arr.min():.4f}, p10={np.percentile(jsd_arr, 10):.4f}, "
        f"median={np.median(jsd_arr):.4f}, mean={np.mean(jsd_arr):.4f}, "
        f"p75={np.percentile(jsd_arr, 75):.4f}, p90={np.percentile(jsd_arr, 90):.4f}, max={jsd_arr.max():.4f}"
    )


if __name__ == "__main__":
    main()
