# R3 Reproducibility Audit Manifest & Execution Guide (`REPRODUCIBILITY_R3.md`)

**Paper Title:** *CARE-Agents: Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Episodic Memory for Financial Trading*

**Audit Standard:** Satisfies **Tier R3 (Full Code, Point-in-Time Data, Deterministic Seeds, and Automated Verification)** and all seven Minimum Reporting requirements (**MR-1 to MR-7**) from [Xia et al. (2026, arXiv:2605.19337)](https://arxiv.org/abs/2605.19337) and the Five-Criteria Credibility Audit from [Nguyen & Pham (2026, arXiv:2603.27539)](https://arxiv.org/abs/2603.27539).

## 1. Minimum Reporting (MR-1 to MR-7) Compliance Matrix

| Criterion | Standard Requirement ([Xia et al., 2026](https://arxiv.org/abs/2605.19337)) | CARE-Agents Implementation & Verification Artifact | Status |
| :--- | :--- | :--- | :--- |
| **MR-1** | Post-cutoff out-of-sample evaluation window | `data/phase5_real_2025_2026_prices.csv` (`2025-01-03` to `2026-10-23`, 86 out-of-sample weekly decision bars post-warmup) | **Verified** |
| **MR-2** | Strict point-in-time causal feature construction (zero look-ahead) | `detect_causal_regime()` in `scripts/run_phase5_real_market_benchmark.py` uses only historical indices $\tau \le t$ (`MA8_weekly`) | **Verified** |
| **MR-3** | Multi-asset, cross-market evaluation universe (survivorship-free) | 12 equities across China CSI 300 A-Shares (8 assets, including decliners `-45.2%` & `-32.5%`) and US Tech (4 assets) | **Verified** |
| **MR-4** | Explicit market microstructure friction & trading limits | `15.0 bps` one-way cost + weekly price-limit caps for CN A-Shares; `5.0 bps` one-way cost for US Tech | **Verified** |
| **MR-5** | Comprehensive risk-adjusted & calibration metrics | Reports Gross/Net Return (`15/5 bps` and `10 bps`), Gross/Net Sharpe, Sortino, Calmar, MaxDD, Turnover, Multiclass Brier Score, MAE, ECE, and CBS Surplus | **Verified** |
| **MR-6** | Computational overhead & token cost accounting | Tracks Debate Trigger Rate (`%`), Fast-Path Skip Rate (`%`), and Average Tokens per decision step from `15,974` cached live DeepSeek API traces | **Verified** |
| **MR-7** | Non-parametric statistical significance testing | Politis–Romano circular block bootstrap ($B=1000$, block size $b=4$) $p$-values (`p_boot`), Diebold–Mariano (`p_DM`), and paired Brier $z$-tests (`p_Brier`) | **Verified** |

## 2. Running the Unit Test Suites (Phases 1–5)

Execute all 6 unit test suites verifying CBS debate gating, online regime-conditioned multiplicative weights, regime-filtered episodic memory, counterfactual credit assignment, protocol audit metrics, causal ablation integrity, and the prompt seed JSON contract:

```bash
PYTHONPATH=. ./.venv/bin/pytest \
  tests/test_cbs_debate_gating.py \
  tests/test_regime_weight_calculator.py \
  tests/test_regime_memory_attribution.py \
  tests/test_protocol_audit_evaluator.py \
  tests/test_phase5_prompt_seed_and_real_data.py \
  tests/test_adversarial_challenger_1.py -v
```

## 3. Reproducing All Manuscript Tables and Figures

### 3.1 Phase 4 Controlled 500-Bar Multi-Regime Ablation (Table 2 & Figure 2)

```bash
PYTHONPATH=. ./.venv/bin/python scripts/run_cph_ablation_benchmark.py
```

* **Outputs:** `results/cph_ablation_metrics.csv`, `reports/cph_ablation_metrics.csv`, `reports/cph_ablation_table.tex`, and `reports/cph_ablation_brier_mae.pdf` (Deterministic Seed: `42`).

### 3.2 Phase 5 Out-of-Sample 2025–2026 Real-Market 2×4 Factorial Benchmark (Tables 3–8 & Figures 3–4)

* **Mode A — Deterministic Replay with Pre-Cached Live LLM Posteriors (`results/live_llm_posteriors_cache.json`, Default, Zero API Cost):**

```bash
PYTHONPATH=. ./.venv/bin/python scripts/run_phase5_real_market_benchmark.py
```

* **Mode B — Live LLM API Execution (`DeepSeek-Flash` at `T=0.35` & `T=0.10` via OpenAI-Compatible Endpoints with R3 Caching):**

```bash
export DEEPSEEK_API_KEY="sk-..."
PYTHONPATH=. ./.venv/bin/python scripts/run_phase5_real_market_benchmark.py --use-live-llm-api
```

* **Outputs:**
  * `results/phase5_real_market_cph_results.csv` (2×4 Factorial Summary Metrics — Cohort B Full Universe)
  * `results/phase5_real_market_subset_results.csv` (Cohort A Subset Metrics)
  * `results/phase5_component_ablation.csv` (Stepwise Component Ablation C1–C3 + Fair Control `M2 + C3`)
  * `results/phase5_sota_pnl_comparison.csv` (\$100,000 Portfolio SOTA Baseline Comparison)
  * `results/phase5_sensitivity_sweep.csv` (Hyperparameter Sensitivity Sweep across $\eta \times \tau_{JS}$)
  * `results/phase5_per_stock_breakdown.csv` (12-Equity Granular Breakdown)
  * `results/phase5_cph_table.tex` (Booktabs LaTeX Table for Manuscript)
  * `results/regime_weight_trajectories.pdf` (Figure 3: Online Regime-MWU Specialist Weights)
  * `results/phase5_equity_drawdown_curves.pdf` (Figure 4: Cumulative Net Equity & Drawdown Curves)

### 3.3 Compiling the LaTeX Manuscript (`care_agents_paper.tex`)

```bash
pdflatex -interaction=nonstopmode -halt-on-error care_agents_paper.tex
pdflatex -interaction=nonstopmode -halt-on-error care_agents_paper.tex
```
