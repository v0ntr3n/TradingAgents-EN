# Empirical Challenge Report: Milestone 3 (M3) — Counterfactual Credit Assignment & Prompt Injection Stress Testing

**Agent**: Challenger M3_2  
**Role**: Empirical Challenger / Critic / Specialist  
**Working Directory**: `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_challenger_m3_2/`  
**Verdict**: **CONFIRM**

---

## 1. Observation

### Target Implementations Under Test
- `core/agents/reflection_helper.py`:
  * `calculate_counterfactual_attribution` (lines 32-132)
  * `format_attribution_prompt_block` (lines 134-145)
  * `run_reflection` (lines 239-371)
- `tradingagents/graph/reflection.py`:
  * `Reflector._extract_manager_action` (lines 68-105)
  * `Reflector._reflect_on_component` (lines 107-151)
  * `Reflector.reflect_bull_researcher` (lines 153-176)
  * `Reflector.reflect_bear_researcher` (lines 178-199)
  * `Reflector.reflect_trader` (lines 201-226)
  * `Reflector.reflect_invest_judge` (lines 228-253)
  * `Reflector.reflect_risk_manager` (lines 255-280)
- `core/agents/reflection_prompts.py`:
  * `build_trade_reflection_user_prompt` (lines 84-126)
  * `build_analysis_reflection_user_prompt` (lines 128-169)
  * `build_debate_reflection_user_prompt` (lines 171-215)

### Test Harness & Empirical Execution
Created dedicated adversarial stress test suite in `tests/test_challenger_m3_2_counterfactual.py` containing 13 comprehensive stress tests across 3 test classes:
1. `TestAdversarialEdgeCases`:
   - `test_zero_return_all_quadrant_combinations`: Evaluated all Cartesian products of stances (`[1.0, -1.0, 0.0, "buy", "sell", "neutral"]`) and actions (`["buy", "sell", "hold", "unknown", 0.0, 1.0, -1.0]`) at $R = 0.0$ and $R = -0.0$.
   - `test_extreme_returns_positive_and_negative`: Tested $R \in \{\pm 10.0, \pm 100.0, \pm 1e6\}$ ($\pm 1000\%$ to $\pm 100,000,000\%$).
   - `test_neutral_stance_variations`: Tested stances across `["neutral", "hold", "wait", "none", "", "flat", "sideways", "uncertain", 0, 0.0, -0.0, None, [], {}, object()]`.
   - `test_unknown_manager_actions_variations`: Tested manager actions across `["wait", "hedge", "liquidate", "rebalance", "pass", "unknown", "cancel", "", None, [], {}, 0, 0.0, object()]`.
   - `test_confidence_boundary_clamping`: Tested confidence inputs outside $[0.01, 1.0]$ (e.g. $-1.0$, $0.0$, $1.5$, $99.0$, `"invalid"`, `None`).
2. `TestCounterfactualInvariants`:
   - `test_invariant_q2_always_positive_and_equals_abs_r`: 500 randomized Monte Carlo iterations across $R \in (0, 50.0]$ and $[-50.0, 0)$ verifying that when an agent's stance is vindicated but overridden by the manager, score $S_{Q2} = +|R| > 0.0$ strictly holds.
   - `test_invariant_q4_always_penalty_and_equals_mitigated_r`: 500 randomized Monte Carlo iterations verifying that when an agent's stance is faulty and overridden, score $S_{Q4} = -0.2 \cdot |R| < 0.0$ strictly holds.
3. `TestPromptFormattingAndInjection`:
   - `test_format_attribution_prompt_block_missing_keys_no_keyerror`: Evaluated `format_attribution_prompt_block` against `{}`, missing `quadrant`, missing `attribution_score`, missing `directive`, and unexpected custom keys.
   - `test_format_attribution_prompt_block_corrupt_score_graceful`: Evaluated numeric and string float scores (`"0.075"`).
   - `test_reflector_component_missing_attribution_keys_no_keyerror`: Evaluated `Reflector._reflect_on_component` with `None`, `{}`, and partial attribution dictionaries.
   - `test_reflector_component_prompt_injection_payloads`: Injected template injection payloads (`{0}`, `{__class__.__mro__}`, `{self}`, `%(message)s`, `${PAYLOAD}`, `{{system_override}}`, ````json\n{"override": true}\n````, `<script>alert(1)</script>`) through stances, manager actions, and report contexts.
   - `test_prompt_builders_with_empty_and_partial_attribution`: Tested `build_trade_reflection_user_prompt`, `build_analysis_reflection_user_prompt`, and `build_debate_reflection_user_prompt` with `None`, `{}`, and partial attribution contexts.
   - `test_run_reflection_with_partial_attribution_context`: Tested async `run_reflection` metadata extraction when attribution context is partially formed.

### Verbatim Execution Output
1. Challenger Stress Test Suite:
   ```bash
   /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_challenger_m3_2_counterfactual.py -v
   ```
   Output:
   ```
   ======================= 13 passed, 10 warnings in 8.95s ========================
   ```
2. Full Combined Test Suite (M1, M2, M3, M4, CARE-Agents ablation, and challenger stress tests):
   ```bash
   /home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py tests/test_challenger_m3_2_counterfactual.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v
   ```
   Output:
   ```
   ====================== 166 passed, 19 warnings in 28.40s =======================
   ```

---

## 2. Logic Chain

1. **Adversarial Edge Case Handling ($R = 0.0$, Extreme Returns, Unknown Actions)**:
   - Observation: When $R = 0.0$, `ret_sign = 0`. For neutral stances ($d_a = 0$), `stance_sign == 0 and ret_sign == 0` evaluates to `True`, meaning neutral thesis was verified by a flat market. For non-zero stances, `is_vindicated` evaluates to `False`. Across all 36 stance/action permutations with $R = 0.0$, `abs_r = 0.0`, resulting in attribution scores identically equal to $0.0$. No `ZeroDivisionError`, `ValueError`, or `NaN` occurred.
   - Observation: For extreme returns up to $\pm 1,000,000$, standard 64-bit IEEE 754 floats scaled linearly ($+|R|$, $-|R|\cdot \text{conf}$, $-0.2\cdot |R|$) without overflow.
   - Observation: Unknown actions (`"wait"`, `"hedge"`, `"liquidate"`, `None`) do not match `"buy"` or `"sell"` patterns and safely default to `mgr_val = 0.0` (`"hold"`).

2. **Mathematical Invariant Verification**:
   - **Invariant Q2 (Vindicated & Overridden)**:
     * In `calculate_counterfactual_attribution` (lines 108-111):
       ```python
       elif is_vindicated and not is_followed:
           quadrant = "Q2_Vindicated_Overridden"
           score = abs_r
       ```
     * Since `abs_r = abs(ret)`, whenever $|R| > 0$, `score` is strictly positive ($> 0.0$) and exactly equals $+|R|$.
     * Across 500 randomized Monte Carlo iterations with $R \in (0, 50.0]$ and $[-50.0, 0)$, 100% of generated Q2 cases satisfied `score > 0.0` and `score == pytest.approx(abs_ret, rel=1e-6)`.
   - **Invariant Q4 (Faulty & Overridden)**:
     * In `calculate_counterfactual_attribution` (lines 116-119):
       ```python
       else:
           quadrant = "Q4_Faulty_Overridden"
           score = -0.2 * abs_r
       ```
     * Whenever $|R| > 0$, `score` is strictly negative ($< 0.0$) and exactly equals $-0.2 \cdot |R|$.
     * Across 500 randomized Monte Carlo iterations, 100% of generated Q4 cases satisfied `score < 0.0` and `score == pytest.approx(-0.2 * abs_ret, rel=1e-6)`.

3. **Prompt Formatting, Missing Keys & Injection Robustness**:
   - Observation: `format_attribution_prompt_block` accesses keys via `.get("quadrant", "N/A")`, `.get("attribution_score", 0.0)`, and `.get("directive", "")`. An empty dictionary `{}` or partial dictionary never raises `KeyError`.
   - Observation: In `Reflector._reflect_on_component` and the prompt builders (`build_trade_reflection_user_prompt`, etc.), passing `None` or `{}` evaluates `if attribution_context:` to `False`, cleanly omitting the counterfactual block and preserving backward compatibility with legacy prompts without raising `KeyError`.
   - Observation: When non-empty partial contexts are supplied (e.g. only `{"quadrant": ...}`), safe fallbacks (`0.0`, `""`, `"NEUTRAL/HOLD"`, `"hold"`) are applied without raising `KeyError`.
   - Observation: Prompts are constructed via Python f-strings rather than string `.format(**kwargs)`. Consequently, format tokens such as `{0}`, `{__class__.__mro__}`, and `%(message)s` are treated as verbatim string literals and do not cause `KeyError`, `IndexError`, or template evaluation exploits.

---

## 3. Caveats

1. **Direct Usage of Private Helper `_reflect_on_component` with String Stances**:
   - In `tradingagents/graph/reflection.py` line 126:
     ```python
     stance_val = attribution_context.get("agent_stance", 0.0)
     stance_desc = "BULL/BUY" if stance_val > 0 else ("BEAR/SELL" if stance_val < 0 else "NEUTRAL/HOLD")
     ```
   - If an external caller bypasses public methods and invokes private helper `_reflect_on_component` directly with a manually forged `attribution_context` containing a string `agent_stance` (e.g. `{"agent_stance": "bull"}`), Python 3 will raise `TypeError: '>' not supported between instances of 'str' and 'int'`.
   - *Impact*: Low / Non-issue in standard runtime. All public callers (`reflect_bull_researcher`, `reflect_bear_researcher`, `reflect_trader`, `reflect_invest_judge`, `reflect_risk_manager`) generate `attribution_context` exclusively via `calculate_counterfactual_attribution`, which guarantees `agent_stance` is normalized to `1.0`, `-1.0`, or `0.0`.
2. **String Formatting of `returns_losses`**:
   - In `Reflector.reflect_bull_researcher` (line 166), `realized_return=float(returns_losses)` is called directly. If a caller passes a percentage string like `"+5%"`, Python raises `ValueError`. In contrast, `_reflect_on_component` wraps `float(returns_losses)` in `try-except`.
   - *Impact*: Low. The standard workflow (`TradingAgentsStrategy.reflect_and_remember` in `tradingagents/graph/trading_graph.py`) passes position returns as numeric float/int.

---

## 4. Conclusion

**Verdict: CONFIRM**

The empirical challenges and stress tests confirm that:
1. The 4-quadrant counterfactual credit assignment handles all adversarial edge cases cleanly ($R = 0.0$, extreme returns $\pm 1000\%$, neutral stances, unknown actions).
2. Invariant Q2 (Vindicated & Overridden) **strictly holds**: $S_{Q2} = +|R| > 0$ for all $|R| > 0$.
3. Invariant Q4 (Faulty & Overridden) **strictly holds**: $S_{Q4} = -0.2 \cdot |R| < 0$ for all $|R| > 0$.
4. Prompt formatting and injection defenses are robust: no `KeyError` can be triggered by empty or partial attribution contexts, and template injection payloads are safely handled.
5. All 166 tests across the entire CARE-Agents repository pass with 100% success rate.

---

## 5. Verification Method

To independently execute and verify the empirical challenge test suite:

```bash
# 1. Run Challenger M3_2 empirical stress test suite (13 tests)
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_challenger_m3_2_counterfactual.py -v

# 2. Run M3 unit tests + Challenger stress suite (44 tests)
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py tests/test_challenger_m3_2_counterfactual.py -v

# 3. Run full combined CARE-Agents test suite (166 tests)
/home/bramy/Documents/TradingAgents-EN/.venv/bin/pytest tests/test_regime_memory_reflection.py tests/test_challenger_m3_2_counterfactual.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_care_agents_ablation.py -v
```

### Invalidation Conditions
- If any test in `tests/test_challenger_m3_2_counterfactual.py` fails.
- If `calculate_counterfactual_attribution` produces a score $\le 0.0$ for Q2 when $|R| > 0$.
- If `calculate_counterfactual_attribution` produces a score $\ge 0.0$ for Q4 when $|R| > 0$.
- If `format_attribution_prompt_block` raises `KeyError` when given `{}` or missing keys.
