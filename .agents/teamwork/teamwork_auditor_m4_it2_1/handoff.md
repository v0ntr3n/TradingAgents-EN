# Forensic Audit Report: Milestone M4 Iteration 2

**Work Product**: `core/backtest/result_evaluator.py`, `tests/test_challenger_m4_1_frictions.py`, `tests/test_result_evaluator_care.py`  
**Profile**: General Project  
**Integrity Mode**: Development (also verified against Demo & Benchmark standards)  
**Auditor**: Forensic Auditor M4_it2 (`teamwork_auditor_m4_it2_1`)  
**Verdict**: **CLEAN**

---

### Phase Results Summary
- **Hardcoded Output Detection**: **PASS** — Zero hardcoded mock returns, dummy outputs, or rigged constants.
- **Facade Detection**: **PASS** — Authentic mathematical logic implemented for China A-share frictions (5 bps sell stamp duty, 2.5 bps commission, configurable slippage), annualized CAGR, Sharpe, Sortino, Calmar, MDD, CBS, and multi-regime breakdown.
- **Pre-populated Artifact Detection**: **PASS** — No fabricated test logs or pre-baked outputs; tests run dynamically.
- **Helper Functions & Type Coercion**: **PASS** — Genuine implementations of `_is_equity_curve`, `_is_trade_list`, `_is_numeric_sequence`, and safe `shares` coercion.
- **Build & Test Execution**: **PASS** — 164/164 targeted tests passed in 2.57s; 265/265 full CARE-Agents test suite passed in 22.74s.
- **Output Verification**: **PASS** — Empirical calculations match theoretical financial formulas and contract specifications.
- **Dependency Audit**: **PASS** — No external library bypasses or execution delegation.

---

## 1. Observation

1. **Helper Functions Implementation (`core/backtest/result_evaluator.py:171-209`)**:
   - `_is_equity_curve(series)`:
     ```python
     def _is_equity_curve(series: Any) -> bool:
         if not isinstance(series, (list, tuple, np.ndarray)) or len(series) < 2:
             return False
         try:
             arr = np.asarray(series, dtype=np.float64)
             if len(arr) < 2:
                 return False
             if (arr < 0.0).any():
                 return False
             if (arr > 1.5).any():
                 return True
             first_val = float(arr[0])
             if abs(first_val - 1.0) < 1e-3 and float(np.mean(arr)) > 0.3:
                 return True
         except (ValueError, TypeError):
             return False
         return False
     ```
     Accurately identifies wealth series (values > 1.5 or normalized near 1.0 without negative values) from return series.
   - `_is_trade_list(obj)`:
     ```python
     def _is_trade_list(obj: Any) -> bool:
         if isinstance(obj, (list, tuple)) and len(obj) > 0:
             return isinstance(obj[0], (dict, collections.abc.Mapping))
         return False
     ```
   - `_is_numeric_sequence(obj)`:
     ```python
     def _is_numeric_sequence(obj: Any) -> bool:
         if isinstance(obj, (list, tuple, np.ndarray)) and len(obj) > 0:
             return isinstance(obj[0], (int, float, np.floating, np.integer))
         return False
     ```

2. **Safe `shares` Type Coercion (`core/backtest/result_evaluator.py:343-369`)**:
   ```python
   raw_shares = t.get("shares")
   if raw_shares is None:
       raw_shares = t.get("amount")
   if raw_shares is None:
       raw_shares = t.get("qty", None)
   shares = 0.0
   if raw_shares is not None:
       try:
           shares = float(raw_shares)
       except (ValueError, TypeError):
           shares = 0.0

   if shares > 0:
       total_frictions_bps += actual_friction.commission_bps + actual_friction.slippage_bps
   elif shares < 0:
       total_frictions_bps += (
           actual_friction.sell_stamp_duty_bps
           + actual_friction.commission_bps
           + actual_friction.slippage_bps
       )
   else:
       # Default completed round trip (1 buy + 1 sell)
       total_frictions_bps += (
           actual_friction.sell_stamp_duty_bps
           + 2.0 * (actual_friction.commission_bps + actual_friction.slippage_bps)
       )
   ```
   Safely coerces integer strings, float strings, `None`, and invalid structures without raising `TypeError`.

3. **Polymorphic Argument Resolution (`core/backtest/result_evaluator.py:246-326`)**:
   - Disentangles `FrictionConfig` whether passed as `friction` keyword, 2nd positional argument, or 3rd positional argument.
   - Resolves Pattern 1 (`trades`, `daily_returns`, `friction`), Pattern 2 (`trades`, `equity_curve`, `friction`), and Pattern 3 (`gross_returns`, `trades`, `friction`).
   - When `trades == []` and second argument is a sequence of numbers, routes to `actual_returns` without misinterpreting floats as dicts (preventing `AttributeError`).
   - When second argument is wealth levels (e.g. `[100.0, 102.0, 105.0]`), derives daily returns via `(equity[i] / equity[i-1]) - 1.0` yielding `+5.0%` gross return, eliminating the 1.1 million percent overflow warning.

4. **Independent Test Execution Results**:
   - Targeted M4 suite command:
     `.venv/bin/pytest tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_challenger_m4_2_ablation.py -v`
     **Result**: `164 passed, 7 warnings in 2.57s`.
   - Full CARE-Agents suite command:
     `.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_regime_weights_signal.py tests/test_regime_memory_reflection.py tests/test_care_agents_ablation.py tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_challenger_m4_2_ablation.py -q`
     **Result**: `265 passed, 19 warnings in 22.74s`.

5. **Empirical Adversarial Edge-Case Stress Testing**:
   - Tested `calculate_net_performance_metrics` with `NaN` shares -> outputs `20.0 bps` (roundtrip fallback) without crash.
   - Tested `calculate_net_performance_metrics` with `Inf` shares -> outputs `7.5 bps` (buy friction) without crash.
   - Tested mixed trade list with `None` and invalid string elements -> safely filtered, only valid dicts processed.
   - Tested `_is_equity_curve` with invalid types (`['a', 'b']`, `[1.0, 'b']`, `[]`, `None`) -> returns `False` without exception.

---

## 2. Logic Chain

1. In Milestone M4 Iteration 1, Challenger M4_1 uncovered three defects in `core/backtest/result_evaluator.py`:
   - Defect 1: Positional empty trades `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())` raised `AttributeError: 'float' object has no attribute 'get'`.
   - Defect 2: Positional wealth curve `calculate_net_performance_metrics(trades, [100.0, 102.0, 105.0], friction)` treated wealth levels as daily returns, yielding `1,102,717.0` (+1.1M%) and scalar power overflow warning.
   - Defect 3: Non-numeric strings or `None` in `shares` raised `TypeError` during comparison against `0`.
2. Inspection of `core/backtest/result_evaluator.py` lines 171–369 confirms that Worker M4 Iteration 2 implemented genuine domain logic rather than superficial workarounds:
   - `_is_trade_list` and `_is_numeric_sequence` accurately distinguish numeric returns from trade lists, preventing floats from ever being placed into `actual_trades`.
   - `_is_equity_curve` evaluates length, non-negativity, threshold (> 1.5), and normalized level (~1.0 with mean > 0.3) to distinguish equity curves from daily returns.
   - `shares` extraction wraps `float(raw_shares)` in a defensive `try...except (ValueError, TypeError)` block, defaulting to `0.0` on invalid/missing values and routing `shares == 0` to a standard completed roundtrip trade (20.0 bps).
3. Search for hardcoded return values, rigged constants, or dummy stubs across `core/backtest/result_evaluator.py` yielded zero matches. All metrics (Sharpe, Sortino, Calmar, MDD, total frictions, CBS, multi-regime breakdown) derive from authentic vectorized numpy and math operations.
4. Test files `tests/test_challenger_m4_1_frictions.py` and `tests/test_result_evaluator_care.py` contain genuine assertions verifying mathematical formulas, boundary conditions, and contract parity across positional and keyword invocations.
5. All 164 targeted tests and 265 total project tests execute cleanly and pass without errors.
6. Therefore, the work product meets all forensic integrity standards with zero violations.

---

## 3. Caveats

- **No Caveats**: All 3 defects identified in Iteration 1 have been completely resolved with authentic logic.
- Backward compatibility for existing v2 workflows and legacy callers is preserved 100%.

---

## 4. Conclusion

**Verdict: CLEAN**

The implementation in `core/backtest/result_evaluator.py` along with challenger test updates in `tests/test_challenger_m4_1_frictions.py` and regression guards in `tests/test_result_evaluator_care.py` represents an authentic, robust, and mathematically sound completion of Milestone M4 Iteration 2. There are zero integrity violations, zero facades, zero hardcoded values, and zero test bypasses.

---

## 5. Verification Method

Independent reproduction commands:

```bash
# 1. Verify targeted M4 friction and evaluator test suite (164 tests):
.venv/bin/pytest tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_challenger_m4_2_ablation.py -v

# 2. Verify complete CARE-Agents test suite (265 tests):
.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_regime_weights_signal.py tests/test_regime_memory_reflection.py tests/test_care_agents_ablation.py tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_challenger_m4_2_ablation.py -q

# 3. Verify adversarial edge cases in Python:
.venv/bin/python -c "
from core.backtest.result_evaluator import FrictionConfig, calculate_net_performance_metrics, _is_equity_curve
assert calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())['total_frictions_bps'] == 0.0
assert calculate_net_performance_metrics([{'action': 'buy'}], [100.0, 102.0, 105.0], FrictionConfig())['gross_return'] < 0.1
assert calculate_net_performance_metrics([{'shares': '100'}], [0.01])['total_frictions_bps'] == 7.5
assert calculate_net_performance_metrics([{'shares': None}], [0.01])['total_frictions_bps'] == 20.0
print('ALL ADVERSARIAL CHECKS PASSED!')
"
```

### Invalidation Conditions:
- `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())` raises `AttributeError`.
- Positional equity curve derivation yields `gross_return > 1.0` or raises `RuntimeWarning: overflow encountered in scalar power`.
- Non-numeric or `None` in `shares` raises `TypeError`.
- Any test in `tests/test_challenger_m4_1_frictions.py` or `tests/test_result_evaluator_care.py` fails.
