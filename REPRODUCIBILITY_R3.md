# R3 Reproducibility Audit Manifest & Execution Guide (`REPRODUCIBILITY_R3.md`)

**Paper Title:** *CARE-Agents: Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Episodic Memory for Financial Trading*

**Audit Standard:** Satisfies **Tier R3 (Full Code, Point-in-Time Data, Deterministic Seeds, and Automated Verification)** and all seven Minimum Reporting requirements (**MR-1 to MR-7**) from [Xia et al. (2026, arXiv:2605.19337)](https://arxiv.org/html/2605.19337v1) and the Five-Criteria Credibility Audit from [Nguyen & Pham (2026, arXiv:2603.27539)](https://arxiv.org/html/2603.27539v1).

## 1. Minimum Reporting (MR-1 to MR-7) Compliance Matrix

| Criterion | Standard Requirement ([Xia et al., 2026](https://arxiv.org/html/2605.19337v1)) | CARE-Agents Implementation & Verification Artifact | Status |
| :--- | :--- | :--- | :--- |
| **MR-1** | Post-cutoff out-of-sample evaluation window | `data/phase5_real_2025_2026_prices.csv` (`2025-01-03` to `2026-10-23`, 86 out-of-sample weekly bars post-warmup) | **Verified** |
| **MR-2** | Strict point-in-time causal feature construction (zero look-ahead) | `detect_causal_regime()` in `scripts/run_phase5_real_market_benchmark.py` uses only historical indices $\tau \le t$ | **Verified** |
| **MR-3** | Multi-asset, cross-market evaluation universe (survivorship-free) | 12 equities across China CSI 300 A-Shares (8 assets, including decliners `-45.2%` & `-32.5%`) and US Tech (4 assets) | **Verified** |
| **MR-4** | Explicit market microstructure friction & trading limits | `15.0 bps` one-way cost + weekly price-limit caps for CN A-Shares; `5.0 bps` one-way cost for US Tech | **Verified** |
| **MR-5** | Comprehensive risk-adjusted & calibration metrics | Reports Gross/Net Return, Gross/Net Sharpe, Sortino, Calmar, MaxDD, Turnover, Multiclass Brier Score, and CBS Surplus | **Verified** |
| **MR-6** | Computational overhead & token cost accounting | Tracks Debate Trigger Rate (`%`), Fast-Path Skip Rate (`%`), and Average Tokens per decision step | **Verified** |
| **MR-7** | Non-parametric statistical significance testing | Politis–Romano circular block bootstrap ($B=500$, block size $b=4$) $p$-values via `paired_block_bootstrap_sharpe_test()` | **Verified** |

## 2. One-Click Installation into `TradingAgents-EN`

Apply all Phases 1–6 source upgrades, unit tests, point-in-time datasets, and LaTeX manuscript files to a clean clone of `TradingAgents-EN`:

```bash
python3 apply_care_agents_upgrades.py /path/to/TradingAgents-EN
cd /path/to/TradingAgents-EN
```

## 3. Running the Unit Test Suites (Phases 1–5)

Execute all 5 unit test suites verifying CBS debate gating, online regime-conditioned multiplicative weights, regime-filtered episodic memory, counterfactual credit assignment, protocol audit metrics, and the prompt seed JSON contract:

```bash
for f in \
  tests/test_cbs_debate_gating.py \
  tests/test_regime_weight_calculator.py \
  tests/test_regime_memory_attribution.py \
  tests/test_protocol_audit_evaluator.py \
  tests/test_phase5_prompt_seed_and_real_data.py; do
    PYTHONPATH=. python3 "$f"
done
```

## 4. Reproducing All Manuscript Tables and Figures

### 4.1 Phase 4 Controlled 500-Day Multi-Regime Ablation (Table 2)

```bash
PYTHONPATH=. python3 scripts/run_cph_ablation_benchmark.py
```

* **Outputs:** `reports/cph_ablation_metrics.csv` and `reports/cph_ablation_table.tex` (Deterministic Seed: `42`).

### 4.2 Phase 5 Out-of-Sample 2025–2026 Real-Market 2×4 Factorial Benchmark (Tables 3–5 & Figures 2–3)

* **Mode A — Deterministic Replay with Calibrated Signal-to-Noise Backbone Emulation (Default, Zero API Cost):**

```bash
PYTHONPATH=. python3 scripts/run_phase5_real_market_benchmark.py
```

* **Mode B — Live LLM API Execution (`DeepSeek-V3` & `Qwen2.5-14B` via OpenAI-Compatible Endpoints with R3 Caching):**

```bash
export DEEPSEEK_API_KEY="sk-..."
export DASHSCOPE_API_KEY="sk-..."
PYTHONPATH=. python3 scripts/run_phase5_real_market_benchmark.py --use-live-llm-api
```

* **Outputs:**
  * `results/phase5_real_market_cph_results.csv` (2×4 Factorial Summary Metrics)
  * `results/phase5_per_stock_breakdown.csv` (12-Equity Granular Breakdown)
  * `results/phase5_cph_table.tex` (Booktabs LaTeX Table for Manuscript)
  * `results/regime_weight_trajectories.png` (Figure 2: Online Regime-MWU Specialist Weights)
  * `results/phase5_equity_drawdown_curves.png` (Figure 3: Cumulative Net Equity & Drawdown Curves)

### 4.3 Compiling the LaTeX Manuscript (`care_agents_paper.tex`)

```bash
lualatex -interaction=nonstopmode -halt-on-error care_agents_paper.tex
lualatex -interaction=nonstopmode -halt-on-error care_agents_paper.tex
```
