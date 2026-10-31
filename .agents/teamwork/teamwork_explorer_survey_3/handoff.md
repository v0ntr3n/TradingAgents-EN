# Handoff Report: R4 Architecture, Evaluator Metrics, and Ablation Testing Strategy

## 1. Observation
1. **`core/backtest/result_evaluator.py`**:
   - Total lines: 438 lines.
   - Contains LLM evaluation wrappers (`evaluate_backtest_result` at line 127, `optimize_strategy_based_on_evaluation` at line 287).
   - In `_build_evaluation_context` (lines 207–236), metrics are extracted solely from a summary dictionary:
     `summary.get('total_return', 0)`, `summary.get('win_rate', 0)`, `summary.get('max_drawdown_pct', 0)`, `summary.get('trade_count', 0)`, `summary.get('final_value', 0)`.
   - There are **no mathematical calculations** of Sharpe, Sortino, Calmar, Maximum Drawdown, transaction frictions (stamp duty, commission, slippage), CBS_bps, or multi-regime breakdowns.
2. **Transaction Frictions in China A-Shares**:
   - Stamp duty: 5 bps (0.0005) levied exclusively on SELL orders.
   - Commission: 2.5 bps (0.00025) levied on both BUY and SELL orders.
   - Slippage: Configurable `slippage_bps` (e.g. 5.0 bps) on both BUY and SELL orders.
   - Total round-trip friction is $10.0 + 2 \times \text{slippage\_bps}$ bps (20.0 bps with 5 bps slippage).
3. **Graph Architecture in `tradingagents/graph/`**:
   - `TradingAgentsGraph` (`tradingagents/graph/trading_graph.py` lines 419–1150) initializes LLMs, memory provider, toolkit, tool nodes, `ConditionalLogic`, and `GraphSetup`.
   - `GraphSetup.setup_graph()` (`tradingagents/graph/setup.py` lines 284–365) connects analyst nodes sequentially, then lines 316–317 unconditionally route the last analyst to `Bull Researcher`: `workflow.add_edge(current_clear, "Bull Researcher")`.
   - `ConditionalLogic.should_continue_debate` (`conditional_logic.py` lines 273–290) counts debate turns: `max_count = 2 * self.max_debate_rounds`.
   - `core/agents/adapters/risk_self_debate_v2.py` (lines 92–396) already implements 1-shot risk self-debate (`RiskSelfDebateV2`), outputting `risky_opinion`, `safe_opinion`, `neutral_opinion`, and updating `risk_debate_state`.
   - `core/workflow/builder.py` (lines 1132–1151 and 2718–2743) demonstrates routing conditional edges to `risk_self_debate` when `state["_risk_self_debate"]=True`.
4. **Testing & Mocking Infrastructure**:
   - Running live `TradingAgentsGraph` without mocked LLM credentials or offline network isolation fails or times out.
   - In contrast, `tests/tradingagents/graph/test_trading_graph_memory_provider.py` runs with `_DummyLLM` and monkeypatching, passing 100% in 3.47 seconds (`.venv/bin/pytest tests/tradingagents/graph/test_trading_graph_memory_provider.py`).
   - `tests/core/agents/test_manager_memory.py` executes in-memory with `_DummyLLM` and `_Mem0StyleMemory` in under 0.1s.

## 2. Logic Chain
1. *From Observation 1 and 2*: Since `result_evaluator.py` currently only passes high-level summary fields to an LLM prompt, extending it to satisfy R4 requires adding programmatic calculation functions (`calculate_net_performance_metrics`, `calculate_cbs_and_coordination_cost`, `calculate_multi_regime_breakdown`) and a `FrictionConfig` dataclass without breaking the existing LLM evaluation interface.
2. *From Observation 2*: Applying China A-share frictions requires distinguishing sell orders (where 5 bps stamp duty applies) from buy orders (stamp duty does not apply), while applying 2.5 bps commission and configurable slippage to both legs. Net returns must be deducted prior to computing risk-adjusted ratios (Sharpe, Sortino, Calmar, MDD).
3. *From Observation 3*: The 4 ablation configurations map directly to specific architectural control points:
   - Config A (Linear Pipeline): `max_debate_rounds = 0`, `max_risk_discuss_rounds = 0`, static weights, regime-blind memory.
   - Config B (Vanilla TradingAgents): `max_debate_rounds = 1` or 2, `max_risk_discuss_rounds = 1` or 2, static weights, regime-blind memory.
   - Config C (Self-Debate 1-Shot): `RiskSelfDebateV2` 1-shot node, static weights, regime-blind memory.
   - Config D (CARE-Agents): `should_trigger_multi_round_debate` (CBS/JSD gate) + `RegimeAdaptiveWeightCalculator` (Brier-loss MWU) + `Mem0AgentMemory` (regime circuit-breaker).
4. *From Observation 4*: Live graph execution without mocks is non-deterministic and external network dependent. A dedicated `AblationMockLLM` with calibrated response fixtures and a synthetic 60-day price series spanning Bull, Bear, and Sideways windows ensures `tests/test_care_agents_ablation.py` runs 100% offline, deterministically, and fast (< 10 seconds).

## 3. Caveats
- The external Backtrader service (`core/backtest/engine_client.py`) is deployed on port 8900 and runs independently. The evaluation additions in `core/backtest/result_evaluator.py` must operate as a standalone Python library callable on trade and return series without requiring the external Backtrader HTTP server to be running.
- In `tradingagents/graph/setup.py`, routing conditionally after the last analyst will require adding conditional edges from the last analyst clear node to either `Bull Researcher` or `Research Manager` based on `should_trigger_multi_round_debate(state)`.

## 4. Conclusion
- `core/backtest/result_evaluator.py` is ready to be augmented with clean, vectorized net-of-cost calculation functions supporting China A-share friction rules (5 bps sell stamp duty, 2.5 bps commission, configurable slippage), Realized CBS & Token/Latency tracking, and multi-regime window slicing.
- All 4 ablation configurations (Config A, B, C, D) can be cleanly orchestrated and benchmarked within a dedicated test suite `tests/test_care_agents_ablation.py`.
- Deterministic mock LLM and synthetic 3-regime market fixtures guarantee that all ablation unit and integration tests run fast, completely offline, and pass reliably via `.venv/bin/pytest`.

## 5. Verification Method
1. **Inspect Survey Artifacts**:
   - View `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_3/survey_r4_arch.md`.
2. **Verify Python/Pytest Test Environment**:
   - Run: `.venv/bin/pytest tests/tradingagents/graph/test_trading_graph_memory_provider.py`
   - Expected result: 1 test passed in ~3.5 seconds.
3. **Invalidation Conditions**:
   - In `result_evaluator.py`, stamp duty being deducted on buy orders (stamp duty must ONLY be deducted on sell orders).
   - Any external network calls during `tests/test_care_agents_ablation.py` execution.
   - Any breaking signature changes to `evaluate_backtest_result()` or `optimize_strategy_based_on_evaluation()`.
