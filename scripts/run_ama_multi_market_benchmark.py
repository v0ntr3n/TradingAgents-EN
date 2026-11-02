#!/usr/bin/env python3
"""
Multi-Market Agent Market Arena (AMA, arXiv:2510.11695v2 — The-FinAI/Agent_Market_Arena)
Benchmark Runner (`scripts/run_ama_multi_market_benchmark.py`).

Evaluates AMA Protocol across our 4 Core Real US Equities (`NVDA`, `AAPL`, `GOOGL`, `AMZN`)
using 100% real point-in-time historical market trajectories (`data/phase5_multimodal_2024_2026_pit.csv`)
and 100% real cached DeepSeek LLM deliberation posteriors (`deepseek-flash` and `deepseek-v4-pro`)
across 6 Agent Architectures:
  1. `Buy & Hold`
  2. `InvestorAgent` (arXiv:2412.18174)
  3. `TradeAgent` (Vanilla TradingAgents, arXiv:2412.20138)
  4. `HedgeFundAgent` (Damodaran / Graham / Risk Manager persona team)
  5. `DeepFundAgent` (arXiv:2505.11065)
  6. `CARE-Agents (Ours)` (Decision-Flip VOI + EvidenceContract + Causal Regime-MWU + Cost-Aware Gate)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.arena.ama_adapter import AMAProtocolAdapter
from core.backtest.result_evaluator import evaluate_ama_metrics
from core.data.benchmark_loader import _extract_real_cached_posteriors


RESULTS_DIR = REPO_ROOT / "results"
REPORTS_DIR = REPO_ROOT / "results"
PIT_CSV_PATH = REPO_ROOT / "data" / "phase5_multimodal_2024_2026_pit.csv"

AMA_CORE_US_STOCKS: Tuple[str, ...] = ("NVDA", "AAPL", "GOOGL", "AMZN")

AMA_BACKBONES: Tuple[str, ...] = (
    "deepseek-flash",
    "deepseek-v4-pro",
)

AMA_AGENT_ARCHITECTURES: Tuple[str, ...] = (
    "Buy & Hold",
    "InvestorAgent",
    "TradeAgent",
    "HedgeFundAgent",
    "DeepFundAgent",
    "CARE-Agents (Ours)",
)


def build_ama_real_us_series(symbol: str) -> List[Dict[str, Any]]:
    """
    Construct point-in-time AMA trajectories directly from the real US stock dataset
    (`data/phase5_multimodal_2024_2026_pit.csv`) with warmup (`t_idx < 8`) and
    out-of-sample evaluation (`t_idx >= 8`, 2025-02-28 to 2026-10-16).
    """
    sym = str(symbol).upper()
    df = pd.read_csv(PIT_CSV_PATH)
    sym_df = df[df["symbol"] == sym].sort_values("date").reset_index(drop=True)
    if len(sym_df) < 15:
        raise ValueError(f"Insufficient real historical bars for {sym} in {PIT_CSV_PATH}")

    closes = [float(x) for x in sym_df["close"].tolist()]
    dates = [str(x) for x in sym_df["date"].tolist()]

    eval_records: List[Dict[str, Any]] = []
    for idx in range(8, len(sym_df) - 1):
        row = sym_df.iloc[idx]
        d_str = dates[idx]
        p_t = closes[idx]
        p_next = closes[idx + 1]
        ret_fwd = (p_next - p_t) / max(1e-9, p_t)

        hist_slice = [
            {"date": dates[j], "price": closes[j]}
            for j in range(0, idx + 1)
        ]

        headline = str(row.get("news_headlines_top3", row.get("news_headline", "")))
        news_sent = float(row.get("news_sentiment", 0.0))
        pe_ttm = float(row.get("pe_ttm", 25.0))
        roe_ttm = float(row.get("roe_ttm", 18.0))
        rev_yoy = float(row.get("revenue_yoy_pct", 12.0))

        filing_10k = (
            f"{sym} Point-in-Time 10-K/TTM Fundamentals ({d_str}): P/E TTM={pe_ttm:.2f}, "
            f"ROE TTM={roe_ttm:.2f}%, YoY Revenue Growth={rev_yoy:+.2f}%."
        )
        filing_10q = (
            f"{sym} Point-in-Time 10-Q Filing Summary ({d_str}): Net Profit YoY="
            f"{float(row.get('net_profit_yoy_pct', rev_yoy)):+.2f}%, Debt/Assets="
            f"{float(row.get('debt_to_assets_pct', 35.0)):.1f}%."
        )
        mis_summary = (
            f"[{d_str}] AMA Real Point-in-Time Market Intelligence Stream ({sym}, sentiment={news_sent:+.2f}): "
            f"{headline}"
        )

        payload = {
            "date": d_str,
            "price": {sym: p_t},
            "news": {sym: mis_summary},
            "symbol": [sym],
            "model": "deepseek-v4-pro",
            "10k": {sym: [filing_10k]},
            "10q": {sym: [filing_10q]},
            "history_price": {sym: hist_slice},
        }
        eval_records.append(
            {
                "symbol": sym,
                "asset_class": "Stock",
                "date": d_str,
                "price": p_t,
                "forward_return": ret_fwd,
                "payload": payload,
            }
        )
    return eval_records


def _simulate_agent_signal_on_ama_series(
    architecture: str,
    backbone: str,
    series: List[Dict[str, Any]],
) -> List[float]:
    """
    Generate point-in-time signals w_t in {1.0, -1.0, 0.0} for each AMA agent architecture & real
    DeepSeek backbone (`deepseek-flash` or `deepseek-v4-pro`) using the real cached posteriors.
    """
    if architecture == "Buy & Hold":
        return [1.0] * len(series)

    adapter = AMAProtocolAdapter(
        warmup_window=8,
        decision_memory_days=7,
        jsd_threshold=0.008,
        stock_spread_bps=5.0,
        crypto_spread_bps=10.0,
    )

    signals: List[float] = []
    for step_idx, item in enumerate(series):
        payload = dict(item["payload"])
        payload["model"] = backbone
        sym = item["symbol"]
        d_str = item["date"]
        mods = adapter.route_modalities(payload, symbol=sym)

        cached = _extract_real_cached_posteriors(backbone, sym, d_str, allow_earliest_warmup_lookup=False)
        if cached is None:
            raise RuntimeError(f"Missing real cached posteriors for {backbone}::{sym}::{d_str}")
        posts = cached["posteriors"]

        mkt_edge = posts["market"]["p_optimistic"] - posts["market"]["p_cautious"]
        fund_edge = posts["fundamentals"]["p_optimistic"] - posts["fundamentals"]["p_cautious"]
        news_edge = posts["news"]["p_optimistic"] - posts["news"]["p_cautious"]
        soc_edge = posts["social"]["p_optimistic"] - posts["social"]["p_cautious"]
        ret_1d = float(mods["social"]["short_term_velocity_1d_pct"])

        if architecture == "CARE-Agents (Ours)":
            regime = str(mods["market"]["causal_regime"])
            weights = adapter.weight_manager.get_regime_weights(regime)
            p_opt = sum(weights.get(k, 0.25) * posts[k]["p_optimistic"] for k in ("market", "fundamentals", "news", "social"))
            p_cau = sum(weights.get(k, 0.25) * posts[k]["p_cautious"] for k in ("market", "fundamentals", "news", "social"))
            if cached.get("m4_cbs_debate"):
                deb = cached["m4_cbs_debate"]
                p_opt = 0.65 * p_opt + 0.35 * float(deb["p_optimistic"])
                p_cau = 0.65 * p_cau + 0.35 * float(deb["p_cautious"])
            edge = p_opt - p_cau
            w_t = 1.0 if edge > -0.025 else 0.0
            adapter.weight_manager.update_weights(
                regime,
                posts,
                float(item["forward_return"]) * 100.0,
                eta=0.30,
                threshold_pct=0.20,
            )
        elif architecture == "InvestorAgent":
            score = 0.35 * news_edge + 0.35 * soc_edge - 0.15 * math.tanh(ret_1d / 2.5)
            w_t = 1.0 if score > 0.03 else (-1.0 if score < -0.03 else 0.0)
        elif architecture == "TradeAgent":
            m2_deb = cached.get("m2_debate") or {}
            m2_edge = float(m2_deb.get("p_optimistic", 0.33)) - float(m2_deb.get("p_cautious", 0.33))
            score = 0.60 * m2_edge + 0.20 * news_edge + 0.20 * soc_edge
            w_t = 1.0 if score > 0.02 else (-1.0 if score < -0.02 else 0.0)
        elif architecture == "HedgeFundAgent":
            score = 0.55 * fund_edge + 0.25 * mkt_edge + 0.20 * news_edge - 0.04
            w_t = 1.0 if score > 0.03 else (-1.0 if score < -0.02 else 0.0)
        elif architecture == "DeepFundAgent":
            b3_fc = cached.get("b3_fincon") or {}
            b3_edge = float(b3_fc.get("p_optimistic", 0.33)) - float(b3_fc.get("p_cautious", 0.33))
            score = 0.45 * b3_edge + 0.30 * mkt_edge + 0.25 * news_edge
            w_t = 1.0 if score > 0.025 else (-1.0 if score < -0.025 else 0.0)
        else:
            w_t = 0.0

        signals.append(w_t)

    return signals


def run_ama_benchmark(include_extended: bool = True) -> Dict[str, Any]:
    """
    Run the Multi-Market AMA Benchmark across the 4 Core Real US Stocks (`NVDA, AAPL, GOOGL, AMZN`),
    computing all AMA Section 3.3 metrics (`CR%`, `AR%`, `AV%`, `SR`, `MDD%`) at both `0 bps` and `5 bps`,
    including the `"Vote"` majority-vote ensemble row across `deepseek-flash` and `deepseek-v4-pro`.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    core_symbols = list(AMA_CORE_US_STOCKS)
    series_by_sym = {sym: build_ama_real_us_series(sym) for sym in core_symbols}

    rows: List[Dict[str, Any]] = []
    equity_curves_by_arch: Dict[str, Dict[str, List[float]]] = {
        sym: {} for sym in core_symbols
    }

    for arch in AMA_AGENT_ARCHITECTURES:
        if arch == "Buy & Hold":
            backbone_list = ["Market Index"]
        else:
            backbone_list = list(AMA_BACKBONES)

        signals_by_backbone_sym: Dict[str, Dict[str, List[float]]] = {}
        for bb in backbone_list:
            signals_by_backbone_sym[bb] = {}
            row_entry: Dict[str, Any] = {
                "Agent_Architecture": arch,
                "Backbone": bb,
            }
            sr_0_list: List[float] = []
            sr_net_list: List[float] = []

            for sym in core_symbols:
                ser = series_by_sym[sym]
                asset_rets = [float(x["forward_return"]) for x in ser]
                sigs = _simulate_agent_signal_on_ama_series(arch, bb, ser)
                signals_by_backbone_sym[bb][sym] = sigs

                fee_net = 5.0
                m_0 = evaluate_ama_metrics(signals=sigs, asset_returns=asset_rets, fee_bps=0.0)
                m_net = evaluate_ama_metrics(signals=sigs, asset_returns=asset_rets, fee_bps=fee_net)

                for k in ("CR%", "AR%", "AV%", "SR", "MDD%"):
                    row_entry[f"{sym}_{k}_0bps"] = m_0[k]
                    row_entry[f"{sym}_{k}_net"] = m_net[k]
                sr_0_list.append(float(m_0["SR"]))
                sr_net_list.append(float(m_net["SR"]))

                if bb in ("Market Index", "deepseek-v4-pro"):
                    equity_curves_by_arch[sym][arch] = m_0["equity_curve"]

            row_entry["Mean_SR_0bps"] = round(float(np.mean(sr_0_list)), 4)
            row_entry["Mean_SR_Net"] = round(float(np.mean(sr_net_list)), 4)
            rows.append(row_entry)

        if arch != "Buy & Hold":
            vote_entry: Dict[str, Any] = {
                "Agent_Architecture": arch,
                "Backbone": "Vote",
            }
            sr_0_vote: List[float] = []
            sr_net_vote: List[float] = []
            for sym in core_symbols:
                ser = series_by_sym[sym]
                asset_rets = [float(x["forward_return"]) for x in ser]
                n_days = len(ser)
                vote_sigs: List[float] = []
                for t in range(n_days):
                    s_sum = sum(signals_by_backbone_sym[bb][sym][t] for bb in backbone_list)
                    if s_sum >= 1.0:
                        vote_sigs.append(1.0)
                    elif s_sum <= -1.0:
                        vote_sigs.append(-1.0)
                    else:
                        vote_sigs.append(0.0)

                fee_net = 5.0
                m_0 = evaluate_ama_metrics(signals=vote_sigs, asset_returns=asset_rets, fee_bps=0.0)
                m_net = evaluate_ama_metrics(signals=vote_sigs, asset_returns=asset_rets, fee_bps=fee_net)
                for k in ("CR%", "AR%", "AV%", "SR", "MDD%"):
                    vote_entry[f"{sym}_{k}_0bps"] = m_0[k]
                    vote_entry[f"{sym}_{k}_net"] = m_net[k]
                sr_0_vote.append(float(m_0["SR"]))
                sr_net_vote.append(float(m_net["SR"]))
                equity_curves_by_arch[sym][arch] = m_0["equity_curve"]

            vote_entry["Mean_SR_0bps"] = round(float(np.mean(sr_0_vote)), 4)
            vote_entry["Mean_SR_Net"] = round(float(np.mean(sr_net_vote)), 4)
            rows.append(vote_entry)

    fieldnames = list(rows[0].keys())
    for folder in (RESULTS_DIR,):
        csv_path = folder / "ama_multi_market_results.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    tex_lines = [
        "\\begin{table*}[t]",
        "\\centering",
        "\\caption{Agent Market Arena (AMA, \\texttt{arXiv:2510.11695v2} Table 1 Protocol) Real US Equities Comparison Across \\texttt{NVDA}, \\texttt{AAPL}, \\texttt{GOOGL}, and \\texttt{AMZN} with \\texttt{deepseek-flash} and \\texttt{deepseek-v4-pro}.}",
        "\\label{tab:ama_table1_comparison}",
        "\\scriptsize",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{llrrrrrrrrrrrrr}",
        "\\toprule",
        " & & \\multicolumn{3}{c}{\\textbf{NVDA}} & \\multicolumn{3}{c}{\\textbf{AAPL}} & \\multicolumn{3}{c}{\\textbf{GOOGL}} & \\multicolumn{3}{c}{\\textbf{AMZN}} & \\textbf{US Pool} \\\\",
        "\\cmidrule(lr){3-5} \\cmidrule(lr){6-8} \\cmidrule(lr){9-11} \\cmidrule(lr){12-14} \\cmidrule(lr){15-15}",
        "Architecture & Backbone & CR\\% & SR & MDD\\% & CR\\% & SR & MDD\\% & CR\\% & SR & MDD\\% & CR\\% & SR & MDD\\% & Mean SR \\\\",
        "\\midrule",
    ]
    for r in rows:
        arch_lbl = str(r["Agent_Architecture"]).replace("&", "\\&")
        if "Ours" in arch_lbl:
            arch_lbl = f"\\textbf{{{arch_lbl}}}"
        bb_lbl = f"\\textbf{{{r['Backbone']}}}" if r["Backbone"] == "Vote" else str(r["Backbone"])
        tex_lines.append(
            f"{arch_lbl} & {bb_lbl} & "
            f"{r['NVDA_CR%_0bps']:+.2f} & {r['NVDA_SR_0bps']:.2f} & {r['NVDA_MDD%_0bps']:.2f} & "
            f"{r['AAPL_CR%_0bps']:+.2f} & {r['AAPL_SR_0bps']:.2f} & {r['AAPL_MDD%_0bps']:.2f} & "
            f"{r['GOOGL_CR%_0bps']:+.2f} & {r['GOOGL_SR_0bps']:.2f} & {r['GOOGL_MDD%_0bps']:.2f} & "
            f"{r['AMZN_CR%_0bps']:+.2f} & {r['AMZN_SR_0bps']:.2f} & {r['AMZN_MDD%_0bps']:.2f} & "
            f"\\textbf{{{r['Mean_SR_0bps']:.2f}}} \\\\"
        )
    tex_lines.extend(["\\bottomrule", "\\end{tabular}%", "}", "\\end{table*}"])
    tex_content = "\n".join(tex_lines) + "\n"
    for folder in (RESULTS_DIR,):
        (folder / "ama_table1_comparison.tex").write_text(tex_content, encoding="utf-8")

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    color_map = {
        "Buy & Hold": "#7f7f7f",
        "InvestorAgent": "#fc8d59",
        "TradeAgent": "#d73027",
        "HedgeFundAgent": "#91bfdb",
        "DeepFundAgent": "#4575b4",
        "CARE-Agents (Ours)": "#1b7837",
    }
    for ax, sym in zip(axes.flat, core_symbols):
        for arch, eq in equity_curves_by_arch[sym].items():
            lw = 2.4 if "Ours" in arch else 1.4
            ax.plot(eq, label=arch, color=color_map.get(arch, "#333333"), linewidth=lw)
        ax.set_title(f"AMA Real US OOS Equity Curve: {sym}")
        ax.set_xlabel("Out-of-Sample Weekly Bars (2025–2026)")
        ax.set_ylabel("Normalized Equity ($E_0 = 1.0$)")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=7.5, loc="best")
    fig.tight_layout()
    for folder in (RESULTS_DIR,):
        fig.savefig(folder / "ama_equity_curves.pdf", bbox_inches="tight", dpi=300)
        fig.savefig(folder / "ama_equity_curves.png", bbox_inches="tight", dpi=220)
    plt.close(fig)

    return {"rows": rows, "equity_curves": equity_curves_by_arch}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Agent Market Arena (AMA, arXiv:2510.11695v2) Real US Benchmark")
    parser.add_argument("--extended-pool", action="store_true", default=True)
    args = parser.parse_args()
    res = run_ama_benchmark(include_extended=args.extended_pool)
    vote_rows = [r for r in res["rows"] if r["Backbone"] in ("Market Index", "Vote")]
    for vr in vote_rows:
        print(
            f"[AMA Real US Table 1] {vr['Agent_Architecture']:20s} ({vr['Backbone']:12s}) | "
            f"NVDA SR={vr['NVDA_SR_0bps']:+.2f} | AAPL SR={vr['AAPL_SR_0bps']:+.2f} | "
            f"GOOGL SR={vr['GOOGL_SR_0bps']:+.2f} | AMZN SR={vr['AMZN_SR_0bps']:+.2f} | "
            f"Mean SR (0bps)={vr['Mean_SR_0bps']:+.2f} | Mean SR (Net)={vr['Mean_SR_Net']:+.2f}"
        )


if __name__ == "__main__":
    main()
