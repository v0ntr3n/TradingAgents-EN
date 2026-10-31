# CARE-Agents Specification Mining Handoff Report

## 1. Observation

1. **Authoritative Specification Inputs:**
   - `/home/bramy/Downloads/plan.md`: Lines 1–101 detail the 4 core contributions (C1: CBS-gated dynamic coordination, C2: online regime-conditioned multiplicative weights, C3: regime-filtered memory and counterfactual credit assignment, C4: 2026 protocol audit evaluator and factorial ablation), mathematical formulations (eqs 3.1, 3.2, 3.3), and phase-by-phase engineering steps 1.1 to 4.4.
   - `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md`: Lines 1–47 define requirements R1–R4, acceptance criteria for 4 unit test suites (`tests/test_cbs_debate_gating.py`, `tests/test_regime_weight_calculator.py`, `tests/test_regime_memory_attribution.py`, `tests/test_protocol_audit_evaluator.py`), and the benchmark script (`scripts/run_cph_ablation_benchmark.py`).

2. **Existing Codebase State in `TradingAgents-EN`:**
   - `core/agents/analyst.py`: Lines 22–29 define `DEFAULT_UNINFORMATIVE_POSTERIOR`. Lines 549–651 implement `_normalize_posterior`. Lines 700–796 implement `_parse_response` with regex search for `json:signal` blocks. Missing: standalone function `extract_structured_posterior(report_text: str)`.
   - `core/agents/adapters/index_analyst_v2.py`: Lines 261–288 parse cached/existing index reports into posteriors, but line 283 returns only `index_report` and `analyst_posteriors`; does not write `state["market_regime"]`.
   - `tradingagents/graph/conditional_logic.py`: Lines 10–51 implement pure Python `compute_shannon_entropy` and `compute_base2_jsd`. Lines 76–136 implement `calculate_cbs_routing`. Missing: explicit function signatures `compute_jensen_shannon_divergence(posteriors, weights=None)` and `compute_cbs_bps(posteriors, weights=None)`, and alias `should_gate_debate(state)`.
   - `core/agents/utils/weight_calculator.py`: Lines 303–481 implement `RegimeAdaptiveWeightCalculator` with `compute_brier_loss`, `update_weights`, and `get_weights`. Missing: `RegimeMultiplicativeWeightManager` class/alias, weight floor $w_{\min} = 0.03$, $\frac{1}{3}$ factor in Brier loss, and `aggregate_posteriors` (logarithmic opinion pool).
   - `tradingagents/graph/signal_processing.py`: Lines 16–173 implement `calculate_bayesian_log_odds_target_price` and `compute_bayesian_log_odds_details`. Missing: dedicated standalone function `process_calibrated_signal(state, ...)` deriving confidence and risk score directly from calibrated posteriors.
   - `core/memory/memory_manager.py`: Lines 56–96 implement `circuit_breaker_memory_filter`. Lines 144–196 normalize metadata (`market_regime`, `volatility_quintile`, `brier_calibration_error`). Missing: `attribution_role`, 1.5x same-regime re-ranking boost, and `drawdown_circuit_breaker` runtime suspension.
   - `core/agents/reflection_helper.py`: Lines 32–132 implement `calculate_counterfactual_attribution` using quadrant strings `Q1_Vindicated_Followed`, `Q2_Vindicated_Overridden`, `Q3_Faulty_Followed`, `Q4_Faulty_Overridden`. Missing: explicit classification into roles `correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`, and public entry point `compute_counterfactual_attribution(state, realized_return_pct)`.
   - `core/backtest/result_evaluator.py`: Lines 137–169 define `FrictionConfig`. Lines 211–452 implement `calculate_net_performance_metrics`. Lines 454–584 implement `calculate_cbs_and_coordination_cost`. Lines 586–649 implement `calculate_multi_regime_breakdown`. Missing: class `ProtocolAuditEvaluator` and ECE calculation.
   - `tests/`: Existing test files `tests/test_analyst_posteriors_cbs.py`, `tests/test_regime_weights_signal.py`, `tests/test_regime_memory_reflection.py`, `tests/test_regime_circuit_breaker_stress.py`, `tests/test_care_agents_ablation.py`, and `tests/test_challenger_m4_2_ablation.py` cover many underlying algorithms, but the exact test file names requested in `ORIGINAL_REQUEST.md` (`test_cbs_debate_gating.py`, `test_regime_weight_calculator.py`, `test_regime_memory_attribution.py`, `test_protocol_audit_evaluator.py`) and script `scripts/run_cph_ablation_benchmark.py` do not yet exist.

---

## 2. Logic Chain

1. From Observation 1, `plan.md` and `ORIGINAL_REQUEST.md` define the authoritative functional and empirical requirements for CARE-Agents across Phases 1 through 4.
2. From Observation 2, substantial core logic (JSD calculation, CBS routing, basic MWU update, Bayesian log-odds price target calculation, basic circuit breaker, and net performance calculation) was previously developed in various modules and verified in test suites such as `test_care_agents_ablation.py`.
3. However, comparing the exact naming, function signatures, constants, and module contracts specified in `plan.md` and `ORIGINAL_REQUEST.md` against Observation 2 reveals several specific interface gaps:
   - Function aliases and entry points (`extract_structured_posterior`, `compute_jensen_shannon_divergence`, `compute_cbs_bps`, `should_gate_debate`, `RegimeMultiplicativeWeightManager`, `aggregate_posteriors`, `process_calibrated_signal`, `compute_counterfactual_attribution`, `ProtocolAuditEvaluator`).
   - Constant and formula calibrations: floor $w_{\min} = 0.03$, $\frac{1}{3}$ Brier loss scaling, 1.5x same-regime re-ranking boost, drawdown circuit-breaker suspension.
   - Metadata key `attribution_role` in `Mem0AgentMemory` and attribution role mapping (`correct_driver`, `overridden_correct`, `false_driver`, `correct_dissent_ignored`).
   - Acceptance test suite naming: tests must reside under or be executable via the four canonical test files (`tests/test_cbs_debate_gating.py`, `tests/test_regime_weight_calculator.py`, `tests/test_regime_memory_attribution.py`, `tests/test_protocol_audit_evaluator.py`).
   - Benchmark script: `scripts/run_cph_ablation_benchmark.py` needs to be created to run the 4-way factorial ablation (M1–M4) and export LaTeX and CSV tables.

---

## 3. Caveats

1. The codebase is actively functioning under development mode; live LLM execution depends on external API keys (OpenAI / DeepSeek / DashScope) and market data tokens (Tushare / AKShare). All unit test verification and benchmarks must retain deterministic offline mock modes.
2. `core/state/reducers.py`'s `merge_dict` is critical for parallel analyst execution in LangGraph; any modifications to `AgentState` annotations must preserve the `merge_dict` reducer on `analyst_posteriors`.

---

## 4. Conclusion

The authoritative specifications, mathematical equations, data schemas, parameters, and 29 discrete features across Phases 1–4 are fully mined, cross-referenced, and documented in `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/spec_report.md`.
The implementation roadmap is completely actionable and scoped:
- **Phase 1:** Add `extract_structured_posterior`, propagate `market_regime` from `index_analyst_v2`, add `compute_jensen_shannon_divergence` & `compute_cbs_bps` & `should_gate_debate` to `conditional_logic.py`, and link `tests/test_cbs_debate_gating.py`.
- **Phase 2:** Add `RegimeMultiplicativeWeightManager`, $w_{\min} = 0.03$, $\frac{1}{3}$ loss scaling, `aggregate_posteriors` in `weight_calculator.py`, add `process_calibrated_signal` in `signal_processing.py`, and link `tests/test_regime_weight_calculator.py`.
- **Phase 3:** Enforce `attribution_role`, 1.5x re-ranking boost, and `drawdown_circuit_breaker` in `memory_manager.py`, add `compute_counterfactual_attribution` role mapping in `reflection_helper.py`, and link `tests/test_regime_memory_attribution.py`.
- **Phase 4:** Add `ProtocolAuditEvaluator` in `result_evaluator.py`, implement `scripts/run_cph_ablation_benchmark.py` with mockable mode and LaTeX/CSV exports, and link `tests/test_protocol_audit_evaluator.py`.

---

## 5. Verification Method

To independently verify this specification survey:
1. Inspect the generated report:
   ```bash
   cat /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/spec_miner_survey/spec_report.md
   ```
2. Verify reference plan and request alignment:
   ```bash
   diff -u /home/bramy/Downloads/plan.md /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md
   ```
3. Run existing tests to verify baseline test harness integrity:
   ```bash
   pytest tests/test_analyst_posteriors_cbs.py tests/test_regime_weights_signal.py tests/test_regime_memory_reflection.py tests/test_care_agents_ablation.py -q
   ```
4. Verify that no codebase files were modified during this specification mining turn:
   ```bash
   git status --short
   ```
