## 2026-10-30T04:01:05Z
You are Worker M1.
Your working directory is: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_m1/

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You must read:
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/bramy/Documents/TradingAgents-EN/PROJECT.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_m1_1/m1_1_design.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_m1_2/m1_2_design.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_m1_3/m1_3_design.md

You exclusively own these files for Milestone M1:
- `core/agents/analyst.py`
- `core/agents/adapters/index_analyst_v2.py`
- `core/agents/adapters/sector_analyst_v2.py`
- `core/agents/adapters/market_analyst_v2.py`
- `core/agents/adapters/fundamentals_analyst_v2.py`
- `core/agents/adapters/news_analyst_v2.py`
- `core/agents/adapters/social_analyst_v2.py`
- `core/agents/adapters/chip_distribution_analyst_v2.py`
- `tradingagents/graph/conditional_logic.py`
- `core/agents/adapters/risk_self_debate_v2.py`
- `tradingagents/agents/utils/agent_states.py`
- `core/workflow/builder.py`
- `tests/test_analyst_posteriors_cbs.py` (new unit test file for M1)

Implementation Tasks:
1. `core/agents/analyst.py`:
   - Extend `AnalystAgent._parse_response()` to extract structured signal block:
     `{"p_optimistic": float, "p_neutral": float, "p_cautious": float, "expected_move_bps": float, "confidence": float, "market_regime": "bull" | "bear" | "sideways"}`
   - Enforce `p_optimistic + p_neutral + p_cautious == 1.0` (within 1e-4 tolerance).
   - Strip the signal block from the response to keep `{output_field}` as a clean string report.
   - Return `{output_field: clean_report, "analyst_posteriors": {self.agent_id: posterior}}` in `execute()`.
   - Include robust fallback parsing (uninformative prior `p_opt=0.3333, p_neu=0.3334, p_cau=0.3333, confidence=0.0, sideways`).
2. Update all 7 v2 analyst adapters:
   - `index_analyst_v2.py`, `sector_analyst_v2.py`, `market_analyst_v2.py`, `fundamentals_analyst_v2.py`, `news_analyst_v2.py`, `social_analyst_v2.py`, `chip_distribution_analyst_v2.py`.
   - Ensure `FundamentalsAnalystAgentV2` inherits from `AnalystAgent`.
   - Ensure all 7 adapters return `{self.output_field: clean_report, "analyst_posteriors": {self.agent_id: posterior}}` while preserving `tool_call_summaries` and `quality_flags`.
3. `tradingagents/graph/conditional_logic.py`:
   - Implement pure Python base-2 JSD calculation (`compute_base2_jsd`, `compute_shannon_entropy`), without scipy dependency.
   - Implement `should_trigger_multi_round_debate(self, state: AgentState) -> str`:
     * Compute JSD across active analyst probability vectors in `state["analyst_posteriors"]`.
     * Compute `expected_debate_gain_bps = JSD * weighted_expected_move_bps`.
     * Compute `CBS_bps = expected_debate_gain_bps / 2.0`.
     * Compare `CBS_bps` against `state.get("estimated_spread_bps", 15.0)`.
     * If `JSD < 0.12` OR `CBS_bps <= estimated_spread_bps`: return `"fast_path"`.
     * If `JSD >= 0.12` AND `CBS_bps > estimated_spread_bps`: return `"multi_round_debate"` and scale dynamic rounds 1 to `max_debate_rounds`.
   - Update `should_continue_debate` to respect `state.get("dynamic_debate_rounds")`.
4. `core/agents/adapters/risk_self_debate_v2.py`:
   - Support fast-path single-pass risk review and ensure investment plan fallback synthesis.
5. State schemas (`tradingagents/agents/utils/agent_states.py` & `core/workflow/builder.py`):
   - Register `analyst_posteriors` with `merge_dict` reducer.
6. Write unit tests in `tests/test_analyst_posteriors_cbs.py` verifying all M1 capabilities and edge cases.
7. Run tests using `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py` and verify all tests pass.

Write your report to `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_m1/handoff.md`.
Notify the orchestrator with send_message when done.
