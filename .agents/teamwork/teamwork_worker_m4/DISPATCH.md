## 2026-10-30T05:33:51Z
You are Worker M4.
Your working directory is: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_m4/

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You must read:
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/bramy/Documents/TradingAgents-EN/PROJECT.md
- /home/bramy/Documents/TradingAgents-EN/TEST_INFRA.md
- /home/bramy/Documents/TradingAgents-EN/TEST_READY.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_3/survey_r4_arch.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_3/handoff.md

You exclusively own:
- `core/backtest/result_evaluator.py`
- `tests/test_result_evaluator_care.py` (new unit test file for M4 evaluator metrics)
- `tests/test_care_agents_ablation.py`

Tasks:
1. In `core/backtest/result_evaluator.py`:
   - Keep existing `evaluate_backtest_result()` and `optimize_strategy_based_on_evaluation()` backward-compatible.
   - Implement `FrictionConfig` dataclass:
     * `sell_stamp_duty_bps: float = 5.0` (levied exclusively on SELL trades)
     * `commission_bps: float = 2.5` (levied on both BUY and SELL trades)
     * `slippage_bps: float = 5.0` (configurable, levied on both BUY and SELL trades)
   - Implement `calculate_net_performance_metrics(trades: List[Dict[str, Any]], daily_returns: Optional[List[float]] = None, equity_curve: Optional[List[float]] = None, friction: Optional[FrictionConfig] = None) -> Dict[str, float]`:
     * Computes Net Sharpe, Net Sortino, Net Calmar, and Maximum Drawdown after deducting China A-share frictions (5 bps sell stamp duty, 2.5 bps commission, configurable slippage).
     * Provide annualized metrics assuming 252 trading days.
   - Implement `calculate_cbs_and_coordination_cost(debate_records: List[Dict[str, Any]]) -> Dict[str, float]`:
     * Computes realized Coordination Breakeven Spread (`CBS_bps`), token cost per decision, latency ms per decision, and fast-path debate bypass rate.
   - Implement `calculate_multi_regime_breakdown(daily_returns: List[float], regimes: List[str]) -> Dict[str, Dict[str, float]]`:
     * Returns a multi-regime breakdown across `"bull"`, `"bear"`, and `"sideways"` windows (computing return, Sharpe, Sortino, Calmar, Max Drawdown per regime).
   - Integrate net-of-cost metrics and regime summaries into `_build_evaluation_context()` if provided in summary.
2. In `tests/test_result_evaluator_care.py`:
   - Write comprehensive unit tests for `FrictionConfig`, net Sharpe/Sortino/Calmar/MDD calculations (ensuring sell stamp duty is NOT applied to buy orders), realized CBS, token/latency tracking, and multi-regime slicing.
3. In `tests/test_care_agents_ablation.py`:
   - Verify that all 4 ablation configurations (Config A: Linear, Config B: Vanilla TradingAgents, Config C: Self-Debate 1-Shot, Config D: CARE-Agents) pass seamlessly and report net metrics.
4. Execute tests:
   - `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py -v`
   - Document commands and results in `handoff.md`.
Notify orchestrator via send_message when done.
