# Handoff Report: Milestone 3 (M3) — Regime-Conditioned Memory Circuit Breaker & Counterfactual Credit Assignment

## 1. Observation

### Target 1: `core/memory/memory_manager.py`
- Previously, `Mem0AgentMemory._normalize_store_metadata()` (lines 87-97) and `_normalize_recall_filters()` (lines 99-108) only handled `ticker` and `symbol`, omitting regime context.
- Calling `_normalize_recall_filters` without defaults risked KeyErrors for legacy callers querying mandatory keys.
- `search_memories()` in `Mem0AgentMemory` and `AgentMemory` lacked regime filtering, causing cross-regime memory contamination (e.g. bullish dip-buying lessons retrieved during severe bear crashes).
- Defined `_CIRCUIT_BREAKER_AGENTS = {"bull_researcher", "bull_researcher_v2", "bear_researcher", "bear_researcher_v2", "research_manager", "research_manager_v2", "trader", "trader_v2", "risk_manager", "risk_manager_v2"}`.
- Implemented `circuit_breaker_memory_filter(memories, current_regime, regime_confidence, agent_id)`:
  * When `regime_confidence >= 0.5`: filters out memories whose stored `market_regime` contradicts `current_regime`.
  * When `regime_confidence < 0.5`: bypasses circuit-breaker, enabling cross-regime memory recall under regime ambiguity.
  * For non-circuit agents (e.g. analysts): bypasses filtering.
- Updated `Mem0AgentMemory._normalize_store_metadata()` and `_normalize_recall_filters()` to enforce:
  * `"market_regime"`: `"bull"` | `"bear"` | `"sideways"` (default `"sideways"`, validated and case-normalized)
  * `"volatility_quintile"`: int 1 to 5 (clamped, default 3)
  * `"brier_calibration_error"`: float (clamped >= 0.0, default 0.0)
- Updated `Mem0AgentMemory.search_memories()` and `AgentMemory.search_memories()` to resolve `current_regime` and `regime_confidence` from method parameters, `state`, or `filter_metadata`, and execute client-side circuit breaker filtering while maintaining candidate recall budgets (`max(n_results * 3, 15)`).

### Target 2: `core/agents/reflection_helper.py` & `core/agents/reflection_prompts.py`
- Implemented `calculate_counterfactual_attribution(agent_stance, realized_return, manager_action, agent_confidence)` with 4-quadrant attribution:
  * **Q1 (Vindicated & Followed)**: $+|R| \cdot \text{conf}$
  * **Q2 (Vindicated & Overridden)**: $+|R|$ (Counterfactual Alpha acknowledged despite trade loss)
  * **Q3 (Faulty & Followed)**: $-|R| \cdot \text{conf}$
  * **Q4 (Faulty & Overridden)**: $-0.2 \cdot |R|$ (Mitigated Fault)
- Implemented `format_attribution_prompt_block(attribution)` producing:
  ```
  === Counterfactual Credit Assignment ===
  - Status: {quadrant}
  - Attribution Score: {score:+.3f}
  - Directive: {directive}
  ```
- Extended `run_reflection` in `core/agents/reflection_helper.py` to accept `attribution_context`, inject the attribution block into the user prompt, and store `attribution_score` and `attribution_quadrant` into mem0 metadata.
- Extended prompt builders in `core/agents/reflection_prompts.py`:
  * `build_trade_reflection_user_prompt(trade_info, ai_review, attribution_context=None)`
  * `build_analysis_reflection_user_prompt(ticker, report, analysis_date="", attribution_context=None)`
  * `build_debate_reflection_user_prompt(ticker, debate_history, conclusion, debate_type="", attribution_context=None)`

### Target 3: `tradingagents/graph/reflection.py`
- Added `_extract_manager_action(current_state)` to resolve executed manager decision (`"buy"`, `"sell"`, `"hold"`) from state fields (`final_trade_decision`, `trader_investment_plan`, `risk_debate_state`, `investment_debate_state`).
- Replaced uniform scalar broadcast in `Reflector`:
  * `reflect_bull_researcher()` computes Bull stance ($+1.0$) vs manager action and injects Q1/Q2/Q3/Q4 attribution into prompt.
  * `reflect_bear_researcher()` computes Bear stance ($-1.0$) vs manager action and acknowledges counterfactual alpha ($+|R|$) when ignored warnings coincide with portfolio losses.
  * `reflect_trader()`, `reflect_invest_judge()`, `reflect_risk_manager()` evaluate decision stances ($+1.0$, $-1.0$, $0.0$) against trade outcome.
- Updated `_reflect_on_component()` to inject the formatted counterfactual credit assignment block into the human prompt when `attribution_context` is present, while preserving backward-compatible fallback when absent.

### Target 4: Unit Test Suite `tests/test_regime_memory_reflection.py`
- Created 31 unit tests across 4 test classes:
  1. `TestMemoryMetadataNormalization` (9 tests)
  2. `TestRegimeCircuitBreaker` (8 tests)
  3. `TestCounterfactualCreditAssignment` (9 tests)
  4. `TestReflectionPromptInjection` (5 tests)

### Verification Commands & Results
- Command:
  `/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v`
- Result: **153 passed, 19 warnings in 23.43s** (100% pass rate across M1, M2, M3, M4 test suites).

---

## 2. Logic Chain

1. **Memory Isolation vs Ambiguity**:
   - In high-confidence trending regimes ($\text{conf} \ge 0.5$), retrieving contradicting regime memories (e.g., bull dip-buying in a bear market) severely harms decision quality.
   - However, when regime classification is uncertain ($\text{conf} < 0.5$), enforcing strict regime filtering prematurely excludes valuable hedging insights.
   - Therefore, `circuit_breaker_memory_filter` activates when $\text{conf} \ge 0.5$ and bypasses when $\text{conf} < 0.5$.

2. **Resolving Multi-Agent Credit Assignment**:
   - Broadcasting a uniform scalar return $R$ conflates portfolio return with individual agent forecast accuracy.
   - For instance, if an ignored Bear researcher accurately foresees a $-4\%$ crash, uniform broadcast penalizes the Bear researcher for the manager's error.
   - The 4-quadrant attribution model addresses this by evaluating $d_a \cdot y_{\text{sign}}$ (forecast correctness) and $\text{followed}_a$ (manager adoption).
   - In Q2 (Vindicated & Overridden), $+|R|$ rewards counterfactual alpha. In Q4 (Faulty & Overridden), $-0.2 \cdot |R|$ mitigates penalty because the manager shielded the portfolio.

3. **Backward Compatibility**:
   - Adding sensible defaults to `_normalize_store_metadata` and `_normalize_recall_filters` ensures legacy callers that do not supply regime metadata never raise `KeyError`.
   - `Reflector._reflect_on_component` falls back to `Returns: {returns_losses}` when `attribution_context` is `None`.

---

## 3. Caveats

- In test environments without an active MongoDB instance, `MemoryService` defaults to unavailable or memory fallback. `Mem0AgentMemory.search_memories` uses client-side circuit-breaker filtering, which was tested and verified with synthetic mocks and unit fixtures.
- No caveats regarding regressions: all 122 existing CARE-Agents tests plus 31 new M3 tests pass completely.

---

## 4. Conclusion

Milestone 3 (M3) is complete, robust, and verified:
1. `core/memory/memory_manager.py` enforces mandatory metadata keys (`market_regime`, `volatility_quintile`, `brier_calibration_error`) and implements regime circuit-breaker memory retrieval with confidence-based bypass.
2. `core/agents/reflection_helper.py`, `core/agents/reflection_prompts.py`, and `tradingagents/graph/reflection.py` implement the 4-quadrant counterfactual credit assignment model and inject structured attribution into agent reflection prompts.
3. `tests/test_regime_memory_reflection.py` contains 31 exhaustive unit tests covering all functional requirements and boundary conditions.
4. The full suite of 153 tests passes 100% via pytest.

---

## 5. Verification Method

To independently verify M3 changes:
```bash
# Run M3 unit tests
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py -v

# Run full combined CARE-Agents test suite
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v
```

Files to inspect:
- `core/memory/memory_manager.py`
- `core/agents/reflection_helper.py`
- `core/agents/reflection_prompts.py`
- `tradingagents/graph/reflection.py`
- `tests/test_regime_memory_reflection.py`

Invalidation conditions:
- If `Mem0AgentMemory._normalize_store_metadata` or `_normalize_recall_filters` raises `KeyError` when called with `{}` or `None`.
- If `circuit_breaker_memory_filter` filters out contradicting memories when `regime_confidence < 0.5`.
- If `calculate_counterfactual_attribution` produces negative score for Q2 (Vindicated & Overridden).
- If any test in `tests/test_regime_memory_reflection.py` fails.
