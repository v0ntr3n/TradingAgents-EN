## 2026-10-30T05:08:01Z
You are Worker M3.
Your working directory is: /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_worker_m3/

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You must read:
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/bramy/Documents/TradingAgents-EN/PROJECT.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/survey_r2_r3.md
- /home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_survey_2/handoff.md

You exclusively own:
- `core/memory/memory_manager.py`
- `core/agents/reflection_helper.py`
- `core/agents/reflection_prompts.py`
- `tradingagents/graph/reflection.py`
- `tests/test_regime_memory_reflection.py` (new unit test file for M3)

Tasks:
1. In `core/memory/memory_manager.py`:
   - In `Mem0AgentMemory._normalize_store_metadata` and `_normalize_recall_filters`:
     Enforce three mandatory metadata keys:
     * `"market_regime"`: `"bull"` | `"bear"` | `"sideways"` (default `"sideways"`)
     * `"volatility_quintile"`: int 1 to 5 (default 3)
     * `"brier_calibration_error"`: float (default 0.0)
     Provide sensible defaults so existing/legacy callers never raise KeyErrors.
   - Add a regime circuit-breaker on memory retrieval:
     When querying memories for `bull_researcher_v2`, `bear_researcher_v2`, `research_manager_v2`, `trader_v2`, or `risk_manager_v2` (and their aliases):
     Filter out memories whose stored `"market_regime"` contradicts the current `state["market_regime"]` UNLESS current regime confidence is below 0.5.
     If regime confidence < 0.5, bypass the circuit-breaker (allowing cross-regime memory recall under regime ambiguity).
2. In `tradingagents/graph/reflection.py`, `core/agents/reflection_helper.py`, and `core/agents/reflection_prompts.py`:
   - Replace uniform `returns_losses` scalar broadcast across all agents with counterfactual credit assignment:
     Compute each agent's marginal contribution:
     * Check whether agent's directional probability agreed with realized return sign ($y_{\text{sign}}$).
     * Check whether manager overrode or followed the agent.
     * 4-quadrant attribution model:
       - Vindicated & Followed: $+|R| \cdot \text{conf}$
       - Vindicated & Overridden: $+|R|$ (counterfactual alpha)
       - Faulty & Followed: $-|R| \cdot \text{conf}$
       - Faulty & Overridden: $-0.2 \cdot |R|$
     * Inject agent-specific attribution score, quadrant label, and rationale into the reflection prompt.
3. In `tests/test_regime_memory_reflection.py`:
   - Write comprehensive unit tests for metadata normalization, regime circuit-breaker (confidence >= 0.5 vs < 0.5), counterfactual credit assignment across all 4 quadrants, and prompt injection.
4. Run tests:
   - `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v`
   - Document commands and results in `handoff.md`.
Notify orchestrator via send_message when done.
