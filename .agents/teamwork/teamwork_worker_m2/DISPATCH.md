## 2026-10-30T04:38:37Z
You are Worker M2.
Your working directory is: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_m2/

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You must read:
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/bramy/Documents/TradingAgents-EN/PROJECT.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/survey_r2_r3.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/handoff.md

You exclusively own:
- `core/agents/utils/weight_calculator.py`
- `tradingagents/graph/signal_processing.py`
- `tests/test_regime_weights_signal.py` (new unit test file for M2)

Tasks:
1. In `core/agents/utils/weight_calculator.py`:
   - Keep `calculate_report_weights()` exactly intact as a fallback for backward compatibility.
   - Implement `RegimeAdaptiveWeightCalculator`:
     * Maintains weight vectors `w[regime][analyst_id]` across three regimes: "bull", "bear", and "sideways".
     * Provide `get_weights(regime: str) -> Dict[str, float]`.
     * Implement `update_weights(regime: str, analyst_posteriors: dict, realized_return: float, learning_rate: float = 0.2)`:
       - Multiplicative Weights Update (Exponentially Weighted Forecaster) rule based on multiclass Brier loss:
         Target $y$: optimistic $[1, 0, 0]$ if `realized_return > 0.005`, cautious $[0, 0, 1]$ if `realized_return < -0.005`, else neutral $[0, 1, 0]$.
         For each analyst $i$: $BrierLoss_i = \sum_{k=1}^3 (p_{i, k} - y_k)^2 \in [0, 2]$.
         $w_{\text{new}}[i] = w_{\text{old}}[i] \cdot \exp(-\text{learning\_rate} \cdot BrierLoss_i)$.
         Normalize so $\sum_i w_{\text{new}}[i] == 1.0$.
       - Update internal weights for the regime and return normalized weights.
2. In `tradingagents/graph/signal_processing.py`:
   - In `SignalProcessor._smart_price_estimation()` and `process_signal()`:
     * When `state` and `state["analyst_posteriors"]` are present:
       Perform regime-calibrated Bayesian log-odds aggregation weighted by `RegimeAdaptiveWeightCalculator`.
       Calculate aggregated log-odds $L_{\text{agg}}$, calibrated directional probability $P_{\text{agg}}$, and weighted expected move to produce empirical price target.
     * When `state` or `analyst_posteriors` is absent:
       Preserve original fallback multipliers (1.15 for buy, 0.95 for sell) for 100% backward compatibility.
3. In `tests/test_regime_weights_signal.py`:
   - Write comprehensive unit tests for all M2 functionality.
4. Execute tests:
   - `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v`
   - Document commands and results in `handoff.md`.
Notify orchestrator via send_message when done.
