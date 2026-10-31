## 2026-10-30T12:35:16Z

Implement the CARE-Agents (Cost-Aware, Regime-Adaptive Multi-Agent Coordination and Calibrated Memory for Financial Trading) research extensions across TradingAgents-EN covering Phases 1 to 4, with full unit test coverage and mockable ablation benchmark scripts.

Working directory: /home/bramy/Documents/TradingAgents-EN
Integrity mode: development

Reference material: /home/bramy/Downloads/plan.md

## Requirements

### R1. Structured Analyst Posteriors & CBS-Gated Dynamic Coordination (Phase 1)
- Extract structured directional probability distributions (`p_optimistic`, `p_neutral`, `p_cautious`), `expected_move_bps`, and `market_regime` from all v2 analysts in `core/agents/analyst.py`, storing them in `state["analyst_posteriors"]`.
- In `tradingagents/graph/conditional_logic.py`, compute inter-analyst Jensen-Shannon Divergence ($D_{JS}$) and Coordination Breakeven Spread ($\text{CBS}$).
- Dynamically route between multi-round Bull/Bear debate and single-pass fast-path synthesis (`RiskSelfDebateV2`) based on the CBS gating condition ($D_{JS} \ge \tau_{JS}$ and $\text{CBS} > s_t$), bypassing debate when expected signal improvement does not exceed friction.

### R2. Online Regime-Conditioned Multiplicative Weights & Calibrated Signal Processing (Phase 2)
- In `core/agents/utils/weight_calculator.py`, implement regime-partitioned analyst weights updated via an online Exponentially Weighted Forecaster using multiclass Brier loss per market regime (bull, bear, sideways).
- In `tradingagents/graph/signal_processing.py`, derive ensemble confidence, risk score, and target prices from calibrated weighted posteriors, eliminating hardcoded heuristic price multipliers and static analyst weights.

### R3. Regime-Filtered Episodic Memory & Counterfactual Reflection Attribution (Phase 3)
- In `core/memory/memory_manager.py`, tag episodic memories with `market_regime`, `volatility_quintile`, and `attribution_role`, enforcing regime-consistent retrieval filtering and a drawdown circuit-breaker during structural breaks.
- In `tradingagents/graph/reflection.py` and `core/agents/reflection_helper.py`, implement counterfactual credit assignment to attribute reflection rewards individually to agents based on marginal contribution rather than broadcasting uniform portfolio returns.

### R4. 2026 Protocol Audit Evaluator & Factorial Ablation Suite (Phase 4)
- In `core/backtest/result_evaluator.py`, implement `ProtocolAuditEvaluator` calculating net-of-cost financial metrics (Sharpe, Sortino, Calmar, Max Drawdown, A-share transaction costs including commission, stamp duty, slippage), CBS surplus, Brier score, ECE, and token/latency costs.
- In `scripts/run_cph_ablation_benchmark.py`, implement a 4-way factorial ablation runner comparing Linear Pipeline, Vanilla TradingAgents, Self-Debate V2, and CARE-Agents.
- Support both live execution with real LLM API keys and market data feeds (Tushare/AKShare) and mockable deterministic execution for automated verification.

## Acceptance Criteria

### CBS Debate Gating Verification
- [ ] Unit tests in `tests/test_cbs_debate_gating.py` pass, verifying boundary conditions ($D_{JS} = 0$, $D_{JS} = 1$) and dynamic routing switches between multi-round debate and fast-path synthesis based on spread thresholds.

### Regime Weight Calibration Verification
- [ ] Unit tests in `tests/test_regime_weight_calculator.py` pass, verifying multiclass Brier loss calculations, weight convergence across synthetic bull/bear/sideways return sequences, and calibrated signal processing outputs.

### Regime Memory & Counterfactual Attribution Verification
- [ ] Unit tests in `tests/test_regime_memory_attribution.py` pass, verifying regime filtering, drawdown circuit-breaker behavior, and accurate agent classification into counterfactual attribution roles (`correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`).

### Protocol Audit Evaluator & Ablation Suite Verification
- [ ] Unit tests in `tests/test_protocol_audit_evaluator.py` pass, validating net-of-cost financial metrics, A-share friction deductions, calibration metrics, and latency/token tracking.
- [ ] The factorial ablation benchmark script (`scripts/run_cph_ablation_benchmark.py`) runs successfully across all 4 configurations with mockable fixtures and exports performance metric tables.
- [ ] Live execution mode connects to configured LLM API keys and financial market data feeds when credentials are provided in the environment.
