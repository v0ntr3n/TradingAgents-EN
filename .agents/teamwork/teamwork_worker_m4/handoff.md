# Handoff Report: Milestone M4 (Evaluator & Ablation Testing)

**Agent**: Worker M4 (`teamwork_worker_m4`)  
**Date**: 2026-10-30  
**Status**: COMPLETE (Hard Handoff)  
**Parent Agent**: `0c1b607b-8443-4c84-97bb-8256a9dd2707`

---

## 1. Observation

1. **`core/backtest/result_evaluator.py`**:
   - Previously contained high-level LLM evaluation wrappers (`evaluate_backtest_result`, `optimize_strategy_based_on_evaluation`), extracting basic summary statistics from coarse dictionaries without programmatic risk-adjusted metric calculations, transaction fee modeling, or market regime breakdowns.
   - Enhanced with:
     * `FrictionConfig` dataclass: `sell_stamp_duty_bps = 5.0` (levied exclusively on SELL trades), `commission_bps = 2.5` (levied on BUY and SELL trades), `slippage_bps = 5.0` (configurable, levied on BUY and SELL trades), with backward-compatible `stamp_duty_bps` alias.
     * `calculate_net_performance_metrics`: computes Net Sharpe, Net Sortino, Net Calmar, and Maximum Drawdown after deducting China A-share frictions (20.0 bps round-trip friction with default 5.0 bps slippage). Annualized assuming 252 trading days. Supports polymorphic parameter signatures: `(trades, daily_returns, equity_curve, friction)` and positional `(gross_returns, trades, friction)`.
     * `calculate_cbs_and_coordination_cost`: computes realized Coordination Breakeven Spread (`CBS_bps`), token cost per decision, latency ms per decision, and fast-path debate bypass rate.
     * `calculate_multi_regime_breakdown`: returns multi-regime breakdown across `"bull"`, `"bear"`, and `"sideways"` windows (computing return, Sharpe, Sortino, Calmar, and Max Drawdown per regime).
     * `_build_evaluation_context`: enhanced to format and integrate `[Net Performance & Cost Analysis (CARE-Agents)]` and `[Multi-Regime Breakdown]` sections into prompt context when present or derivable from trade records.
2. **`tests/test_result_evaluator_care.py`**:
   - Created new dedicated unit test suite with 32 tests covering:
     * `TestFrictionConfig` (defaults, customization, backward-compatibility alias)
     * `TestNetPerformanceMetricsFrictions` (A-share asymmetry: 0 bps stamp duty on BUY, 5 bps stamp duty on SELL, 2.5 bps commission and 5 bps slippage on both)
     * `TestNetPerformanceMetricsRiskRatios` (excess return over daily $R_f = 0.025 / 252$, $\sqrt{252}$ annualization, zero-volatility guards, downside deviation, peak-to-trough drawdown from $W_0=1.0$, Calmar ratio)
     * `TestNetPerformanceMetricsSignatures` (all 3 polymorphic calling patterns, empty inputs, equity curve return derivation)
     * `TestRealizedCBSAndCoordinationCost` (realized CBS, token tracking, latency normalization, bypass rate, empty records fallback)
     * `TestMultiRegimeBreakdown` (Bull, Bear, Sideways slicing, metrics calculation, case-insensitivity, empty inputs)
     * `TestEvaluationContextIntegration` (prompt formatting with net metrics, multi-regime breakdown, auto-computation, legacy backward-compatibility, `should_optimize_strategy`)
3. **`tests/test_care_agents_ablation.py`**:
   - Updated to import `FrictionConfig`, `calculate_net_performance_metrics`, `calculate_multi_regime_breakdown`, and `calculate_cbs_and_coordination_cost` directly from `core.backtest.result_evaluator`.
   - Verified that all 52 tests covering Config A (Linear), Config B (Vanilla TradingAgents), Config C (Self-Debate 1-Shot), and Config D (CARE-Agents) pass seamlessly.
4. **Test Suite Execution**:
   - Running: `.venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py -v`
   - Output: **185 passed, 19 warnings in 21.67s** (Exit code 0).

---

## 2. Logic Chain

1. *From Requirement R4 and Observation 1*: In China A-shares, stamp duty is legally levied only on seller exits (0.05% / 5 bps), while broker commissions (0.025% / 2.5 bps) and market slippage apply to both entry and exit. Therefore, an asymmetrical deduction must be applied on each trade leg:
   $$\text{Friction}_{\text{buy}} = \text{commission\_bps} + \text{slippage\_bps} = 7.5 \text{ bps}$$
   $$\text{Friction}_{\text{sell}} = \text{sell\_stamp\_duty\_bps} + \text{commission\_bps} + \text{slippage\_bps} = 12.5 \text{ bps}$$
   $$\text{Total Round-Trip Friction} = 7.5 + 12.5 = 20.0 \text{ bps}$$
   By calculating the total trade friction and deducting it across the return series, net returns faithfully reflect institutional A-share execution costs.
2. *From Observation 1 and 2*: Risk-adjusted metrics (Sharpe, Sortino, Calmar, MDD) computed on net returns provide true economic performance. Annualization assuming 252 trading days ($\sqrt{252}$ for Sharpe/Sortino, $(252/N)$ power for CAGR) conforms to quantitative standards, while zero-division guards ensure robustness on flat or negative return profiles.
3. *From Observation 1 and 3*: Connecting `tests/test_care_agents_ablation.py` to `core.backtest.result_evaluator` establishes direct validation of production code across all 4 ablation configurations:
   - Config A (Linear Pipeline: 0 debate rounds, static weights, regime-blind memory)
   - Config B (Vanilla TradingAgents: 2 fixed debate rounds, static weights, regime-blind memory)
   - Config C (Self-Debate 1-Shot: `RiskSelfDebateV2`, static weights, regime-blind memory)
   - Config D (CARE-Agents: CBS-gated dynamic debate, regime-adaptive MWU weights, regime-filtered memory)
4. *From Observation 4*: All 185 tests across M1, M2, M3, M4, and the full ablation test suite pass deterministically and fully offline in under 22 seconds without external network dependencies.

---

## 3. Caveats

- `calculate_net_performance_metrics` deducts aggregate trade friction uniformly across the return periods when exact timestamp mapping between trades and return bars is not provided. If a future simulation requires bar-by-bar discrete friction deductions, per-bar trade execution timestamps can be passed.
- Existing LLM prompt functions `evaluate_backtest_result()` and `optimize_strategy_based_on_evaluation()` remain fully backward-compatible and mock-friendly; they do not invoke external APIs during tests.

---

## 4. Conclusion

- Requirement R4 is 100% fulfilled:
  * `FrictionConfig` accurately models China A-share asymmetric transaction costs.
  * `calculate_net_performance_metrics` computes annualized Net Sharpe, Net Sortino, Net Calmar, and Maximum Drawdown.
  * `calculate_cbs_and_coordination_cost` tracks realized CBS hurdles, token costs, latency, and fast-path bypass rates.
  * `calculate_multi_regime_breakdown` segments performance across Bull, Bear, and Sideways regimes.
  * `_build_evaluation_context` integrates net-of-cost metrics and regime summaries into prompt context.
  * `tests/test_result_evaluator_care.py` (32 tests) and `tests/test_care_agents_ablation.py` (52 tests) pass 100%.

---

## 5. Verification Method

Execute the full CARE-Agents test suite via pytest:
```bash
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py -v
```

Expected result:
```text
====================== 185 passed, 19 warnings in ~22s =======================
```
Exit code: 0.

Invalidation conditions:
- Any failure in the 185 tests.
- Deducting stamp duty on BUY trades (stamp duty must strictly be 0 bps on BUY).
- Any breaking signature change to `evaluate_backtest_result()` or `_build_evaluation_context()`.
