# Investigation Report: Milestone M4 Iteration 1 Defects & Fix Strategy

**Agent**: Explorer M4_it2_1 (`teamwork_explorer_m4_it2_1`)  
**Target File**: `core/backtest/result_evaluator.py` (lines 170–265)  
**Associated Test File**: `tests/test_challenger_m4_1_frictions.py`  
**Parent Agent**: `0c1b607b-8443-4c84-97bb-8256a9dd2707`  
**Date**: 2026-10-30  

---

## 1. Observation

### 1.1 Context and Baseline
- In Milestone M4 Iteration 1, Challenger M4_1 issued a **CHALLENGE** verdict (`teamwork_challenger_m4_1/handoff.md`) citing three critical defects in `core/backtest/result_evaluator.py`, despite the core financial formulas (asymmetric China A-share stamp duty, MDD, Sharpe/Sortino/Calmar) being mathematically sound.
- Challenger created `tests/test_challenger_m4_1_frictions.py` containing 42 tests. Tests 1–39 assert expected financial properties, while tests 40–42 (`TestChallengerEmpiricalVulnerabilities`) empirically reproduce and assert the defects via `pytest.raises` and corrupted return thresholds.
- Full test suite baseline: 185 tests pass in the standard CARE-Agents suite (`pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py`).

### 1.2 Direct Observations of the Three Defects

#### Defect 1: Crash on Empty Trades with Positional Returns (`AttributeError`)
- **Location**: `core/backtest/result_evaluator.py:202-206` and line 240:
  ```python
  202: elif trades == [] and isinstance(daily_returns, (list, tuple)) and isinstance(equity_curve, FrictionConfig):
  203:     # Pattern: ([], [], FrictionConfig)
  204:     actual_returns = []
  205:     actual_trades = list(daily_returns)
  206:     actual_friction = equity_curve
  ...
  240:     action = str(t.get("action", t.get("side", t.get("type", "")))).lower().strip()
  ```
- **Observed Behavior**:
  Calling `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())`:
  `trades == []` matches the condition on line 202. Line 205 assigns `actual_trades = list(daily_returns)` (`[0.01, 0.02]`) while erasing `actual_returns` (`actual_returns = []`).
  On line 240, iteration over `actual_trades` calls `.get("action")` on float `0.01`, raising:
  ```text
  AttributeError: 'float' object has no attribute 'get'
  ```

#### Defect 2: Contract Violation & Return Corruption in Positional Pattern 2
- **Contract Defined**:
  `PROJECT.md` line 121:
  ```python
  def calculate_net_performance_metrics(trades: List[Dict[str, Any]], equity_curve: List[float], friction: FrictionConfig) -> Dict[str, float]: ...
  ```
  `core/backtest/result_evaluator.py:185`:
  ```
  2. calculate_net_performance_metrics(trades, equity_curve, friction)
  ```
- **Location**: `core/backtest/result_evaluator.py:171-174` and lines 208–216:
  ```python
  171: def calculate_net_performance_metrics(
  172:     trades: Optional[Any] = None,
  173:     daily_returns: Optional[Any] = None,
  174:     equity_curve: Optional[Any] = None,
  ...
  208: else:
  209:     actual_trades = list(trades) if isinstance(trades, (list, tuple)) else []
  210:     if isinstance(daily_returns, (list, tuple, np.ndarray)):
  211:         if len(daily_returns) == 0 or isinstance(daily_returns[0], (int, float, np.floating, np.integer)):
  212:             actual_returns = [float(x) for x in daily_returns]
  ```
- **Observed Behavior**:
  Calling `calculate_net_performance_metrics([{"action": "buy"}], [100.0, 102.0, 105.0], FrictionConfig())`:
  The 2nd argument (`[100.0, 102.0, 105.0]`) binds to parameter `daily_returns`. Line 212 stores it into `actual_returns`.
  Lines 224–233 (equity derivation) are skipped because `actual_returns is not None`.
  Wealth levels `[100.0, 102.0, 105.0]` are interpreted as daily percentage returns of +10,000%, +10,200%, and +10,500%.
  Computed `gross_return` becomes `1,102,717.0` (1.1 million percent) with runtime warning:
  ```text
  RuntimeWarning: overflow encountered in scalar power
    cagr = float(equity[-1] ** (252.0 / max(1, n)) - 1.0)
  ```
  Keyword invocation `calculate_net_performance_metrics(trades=trades, equity_curve=equity_curve, friction=friction)` correctly yields `+0.05` (+5.0%).

#### Defect 3: Unhandled `TypeError` on Non-Numeric or None `shares`
- **Location**: `core/backtest/result_evaluator.py:250-254`:
  ```python
  250: shares = t.get("shares", t.get("amount", t.get("qty", 0)))
  251: if shares > 0:
  ```
- **Observed Behavior**:
  If a trade dictionary contains `{"shares": "100"}` or `{"shares": None}`, line 251 raises:
  ```text
  TypeError: '>' not supported between instances of 'str' and 'int'
  ```
  or
  ```text
  TypeError: '>' not supported between instances of 'NoneType' and 'int'
  ```

---

## 2. Logic Chain

1. **Root Cause Analysis of Defect 1 (Crash on Empty Trades)**:
   - Line 202 was written under the assumption that an empty 1st positional argument (`trades == []`) coupled with a `FrictionConfig` in the 3rd argument *only* occurs in Pattern 3: `(gross_returns=[], trades, friction)`.
   - The developer assumed the 2nd argument must be `trades`, assigning `actual_trades = list(daily_returns)`.
   - However, when a caller invokes Pattern 1 (`trades=[], daily_returns=[0.01, 0.02], friction`) or Pattern 2 (`trades=[], equity_curve=[100.0, 102.0], friction`), the 2nd argument contains floating-point returns/wealth levels.
   - Iterating over `actual_trades` and calling `.get()` on floats causes the `AttributeError`.
   - *Inference*: The code must inspect whether elements in the 2nd argument are dictionaries vs floats before assigning them to `actual_trades`.

2. **Root Cause Analysis of Defect 2 (Positional Pattern 2 Return Corruption)**:
   - The function signature in `core/backtest/result_evaluator.py:170-174` defines parameter 2 as `daily_returns` and parameter 3 as `equity_curve`.
   - When calling Pattern 2 positionally `calculate_net_performance_metrics(trades, equity_curve, friction)`, positional binding places `equity_curve` into `daily_returns` and `friction` into `equity_curve`.
   - Line 210 unconditionally assigns `actual_returns = [float(x) for x in daily_returns]`, mistaking wealth levels (e.g. 100.0, 102.0) for daily returns.
   - *Inference*: In China A-shares (daily price limits of ±10%, ±20%, ±30%), daily returns cannot exceed 1.0 (100%). Sequences with `abs(x) > 1.0` or sequences starting at `1.0` without negative numbers represent wealth levels (equity curves), not daily returns. The parser must detect wealth sequences and assign them to `actual_equity`, deriving daily returns via consecutive ratio differences.

3. **Root Cause Analysis of Defect 3 (Unhandled `TypeError` on `shares`)**:
   - In Python dictionary `.get(key, default)`, if `key` exists with value `None` (e.g. `{"shares": None}`), `.get("shares", 0)` returns `None`, not `0`.
   - Furthermore, string inputs (e.g. `{"shares": "100"}` from raw JSON logs) are not coerced to float prior to numerical comparison `shares > 0`.
   - *Inference*: `shares` must be resolved defensively with null-coalescing across aliases (`shares`, `amount`, `qty`), wrapped in a `try...except (ValueError, TypeError)` block defaulting safely to `0.0`, and guarded against non-dict objects in `actual_trades`.

4. **Blast Radius & Inter-Test Dependencies**:
   - `tests/test_challenger_m4_1_frictions.py:424-490` contains 3 empirical tests that currently assert that the bugs occur (`pytest.raises(AttributeError)`, `gross_return > 100000.0`, `pytest.raises(TypeError)`).
   - Once the implementation worker fixes `core/backtest/result_evaluator.py`, those three tests in `tests/test_challenger_m4_1_frictions.py` will fail unless they are updated to assert the correct, healthy behaviors.

---

## 3. Caveats

- **Scope Boundary**: As an Explorer, this report provides architectural analysis, exact code remedies, and test updates without directly editing production code (`core/backtest/result_evaluator.py`). The Worker agent will execute the implementation.
- **Signatures and Keywords**: Keyword calls (e.g. `daily_returns=...`, `equity_curve=...`) and positional Pattern 3 (`gross_returns, trades, friction`) were already functional. The fix must strictly preserve all keyword behaviors while restoring positional contract compliance.
- **Extreme Daily Returns vs Wealth Levels**: In the theoretical edge case where an equity curve starts at `0.50` (sub-1.0 initial capital), callers can pass `equity_curve=...` via keyword. Standard backtest equity curves start at 1.0 or currency base (100.0, 10,000.0), which are cleanly disambiguated.

---

## 4. Conclusion & Actionable Fix Strategy for Worker

### Recommended Changes in `core/backtest/result_evaluator.py` (lines 188–265):

Replace lines 188–265 with the following robust, self-contained implementation:

```python
    actual_returns: Optional[List[float]] = None
    actual_trades: List[Dict[str, Any]] = []
    actual_friction: Optional[FrictionConfig] = None
    actual_equity: Optional[List[float]] = None

    # 1. Resolve friction configuration
    if isinstance(equity_curve, FrictionConfig):
        actual_friction = equity_curve
        equity_curve = None
    elif isinstance(friction, FrictionConfig):
        actual_friction = friction
    elif isinstance(kwargs.get("friction"), FrictionConfig):
        actual_friction = kwargs.get("friction")
    else:
        actual_friction = FrictionConfig()

    # Helper: check if a sequence contains numeric values
    def _is_numeric_seq(seq: Any) -> bool:
        return (
            isinstance(seq, (list, tuple, np.ndarray))
            and len(seq) > 0
            and isinstance(seq[0], (int, float, np.floating, np.integer))
        )

    # Helper: determine if a numeric sequence represents wealth levels (equity curve) vs daily returns
    def _is_wealth_curve(seq: List[float]) -> bool:
        if not seq:
            return False
        # Values > 1.0 (e.g. 100.0, 102.0) represent wealth levels, not daily percentage returns
        if any(abs(x) > 1.0 for x in seq):
            return True
        # Normalized wealth curve starting at 1.0 with strictly non-negative wealth
        if len(seq) > 1 and abs(seq[0] - 1.0) < 1e-4 and all(x >= 0 for x in seq):
            return True
        return False

    # 2. Dispatch polymorphic calling patterns
    if _is_numeric_seq(trades):
        # Pattern 3: calculate_net_performance_metrics(gross_returns, trades, friction)
        actual_returns = [float(x) for x in trades]
        actual_trades = [t for t in daily_returns if isinstance(t, dict)] if isinstance(daily_returns, (list, tuple)) else []
    elif trades == [] and isinstance(daily_returns, (list, tuple)) and len(daily_returns) > 0 and isinstance(daily_returns[0], dict):
        # Pattern 3 with empty returns: (gross_returns=[], trades, friction)
        actual_returns = []
        actual_trades = [t for t in daily_returns if isinstance(t, dict)]
    else:
        # Pattern 1 & 2: trades is first argument
        actual_trades = [t for t in trades if isinstance(t, dict)] if isinstance(trades, (list, tuple)) else []

        # Handle daily_returns / equity_curve passed as second positional argument or keyword
        if isinstance(daily_returns, (list, tuple, np.ndarray)):
            seq = [float(x) for x in daily_returns]
            if _is_wealth_curve(seq):
                actual_equity = seq
            else:
                actual_returns = seq

        # If equity_curve was explicitly supplied (e.g. keyword argument or 3rd parameter)
        if isinstance(equity_curve, (list, tuple, np.ndarray)):
            actual_equity = [float(x) for x in equity_curve]

    # 3. Derive daily returns from equity curve if returns not directly provided
    if actual_returns is None and actual_equity is not None and len(actual_equity) > 1:
        actual_returns = [
            (actual_equity[i] / actual_equity[i - 1]) - 1.0
            for i in range(1, len(actual_equity))
            if actual_equity[i - 1] > 0
        ]
    elif actual_returns is None:
        actual_returns = []

    # 4. Calculate frictions across all trades safely
    total_frictions_bps = 0.0
    for t in actual_trades:
        if not isinstance(t, dict):
            continue
        action = str(t.get("action", t.get("side", t.get("type", "")))).lower().strip()
        if action == "buy":
            total_frictions_bps += actual_friction.commission_bps + actual_friction.slippage_bps
        elif action == "sell":
            total_frictions_bps += (
                actual_friction.sell_stamp_duty_bps
                + actual_friction.commission_bps
                + actual_friction.slippage_bps
            )
        else:
            # Defensive extraction and safe type coercion for shares
            raw_shares = t.get("shares")
            if raw_shares is None:
                raw_shares = t.get("amount")
            if raw_shares is None:
                raw_shares = t.get("qty", 0)
            try:
                shares = float(raw_shares) if raw_shares is not None else 0.0
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

### Required Test Suite Updates in `tests/test_challenger_m4_1_frictions.py` (lines 430–490):

Update `TestChallengerEmpiricalVulnerabilities` to assert healthy, verified behavior:

```python
    def test_positional_empty_trades_signature_defect(self):
        """Verifies positional call ([], daily_returns, friction) succeeds cleanly without AttributeError."""
        trades = []
        daily_returns = [0.01, 0.02]
        friction = FrictionConfig()

        res = calculate_net_performance_metrics(trades, daily_returns, friction)
        assert res["trade_count"] == 0
        assert res["total_frictions_bps"] == 0.0
        assert res["gross_return"] == pytest.approx((1.01 * 1.02) - 1.0, abs=1e-6)
        assert res["net_return"] == pytest.approx(res["gross_return"], abs=1e-6)

    def test_positional_equity_curve_misinterpretation_defect(self):
        """Verifies positional call (trades, equity_curve, friction) accurately derives returns from wealth levels."""
        trades = [{"action": "buy"}]
        equity_curve = [100.0, 102.0, 105.0]
        friction = FrictionConfig()

        res_kw = calculate_net_performance_metrics(trades=trades, equity_curve=equity_curve, friction=friction)
        assert res_kw["gross_return"] == pytest.approx(0.05, abs=1e-4)

        res_pos = calculate_net_performance_metrics(trades, equity_curve, friction)
        assert res_pos["gross_return"] == pytest.approx(0.05, abs=1e-4)
        assert res_pos["trade_count"] == 1
        assert res_pos["total_frictions_bps"] == 7.5
        assert res_pos["gross_return"] == pytest.approx(res_kw["gross_return"], abs=1e-6)

    def test_non_numeric_shares_type_error_defect(self):
        """Verifies non-numeric string or None shares in trade dicts are safely coerced without TypeError."""
        trades_str = [{"shares": "100"}]
        res_str = calculate_net_performance_metrics(trades=trades_str, daily_returns=[0.01])
        assert res_str["trade_count"] == 1
        assert res_str["total_frictions_bps"] == 7.5  # parsed as positive shares -> buy (7.5 bps)

        trades_none = [{"shares": None}]
        res_none = calculate_net_performance_metrics(trades=trades_none, daily_returns=[0.01])
        assert res_none["trade_count"] == 1
        assert res_none["total_frictions_bps"] == 20.0  # roundtrip fallback
```

---

## 5. Verification Method

Once Worker implements the remediations:

1. **Verify Adversarial Friction Tests**:
   ```bash
   .venv/bin/pytest tests/test_challenger_m4_1_frictions.py -v
   ```
   *Expected*: All 42 tests pass with 0 failures and 0 errors.

2. **Verify M4 Ablation & Multi-Regime Tests**:
   ```bash
   .venv/bin/pytest tests/test_challenger_m4_2_ablation.py tests/test_care_agents_ablation.py tests/test_result_evaluator_care.py -v
   ```
   *Expected*: All 116 tests pass with 0 failures.

3. **Verify Full Regression Suite (Milestones M1–M4)**:
   ```bash
   .venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_regime_memory_reflection.py tests/test_regime_weights_signal.py tests/test_analyst_posteriors_cbs.py tests/test_challenger_m4_1_frictions.py tests/test_challenger_m4_2_ablation.py -v
   ```
   *Expected*: All 259 tests pass cleanly.

4. **Invalidation Conditions**:
   - Calling `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())` raises `AttributeError`.
   - Calling `calculate_net_performance_metrics(trades, [100.0, 102.0, 105.0], friction)` produces `gross_return > 1.0` or throws power overflow warning.
   - Calling `calculate_net_performance_metrics([{"shares": "100"}], [0.01])` raises `TypeError`.
