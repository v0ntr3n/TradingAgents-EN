# Explorer Report: Polymorphic Signature Resolution in Result Evaluator

**Agent**: Explorer M4_it2_2  
**Target Code**: `core/backtest/result_evaluator.py` (`calculate_net_performance_metrics`)  
**Context**: Milestone M4 (Iteration 2) — Resolution of Challenger M4_1 findings  
**Status**: Investigation Complete — Design Formulated  

---

## 1. Observation

### Target Under Investigation
- File: `core/backtest/result_evaluator.py`
  - Function: `calculate_net_performance_metrics` (lines 170–338)
  - Class: `FrictionConfig` (lines 135–168)
- Upstream contracts & specifications:
  - `PROJECT.md` §5 (line 121):
    ```python
    def calculate_net_performance_metrics(trades: List[Dict[str, Any]], equity_curve: List[float], friction: FrictionConfig) -> Dict[str, float]: ...
    ```
  - `ORIGINAL_REQUEST.md` §R4 (lines 54–57, 77)
  - Docstring in `core/backtest/result_evaluator.py` (lines 183–187):
    ```
    Supports multiple polymorphic calling conventions:
    1. calculate_net_performance_metrics(trades, daily_returns=..., equity_curve=..., friction=...)
    2. calculate_net_performance_metrics(trades, equity_curve, friction)
    3. calculate_net_performance_metrics(gross_returns, trades, friction)
    ```

### Failure Reproduction from Challenger M4_1
Challenger M4_1 reported 3 reproducible defects in `.agents/teamwork/teamwork_challenger_m4_1/handoff.md`:

1. **Defect 1: Crash on Empty Trades with Positional Returns (`AttributeError`)**
   - Code location: `core/backtest/result_evaluator.py:202-206`
     ```python
     elif trades == [] and isinstance(daily_returns, (list, tuple)) and isinstance(equity_curve, FrictionConfig):
         # Pattern: ([], [], FrictionConfig)
         actual_returns = []
         actual_trades = list(daily_returns)
         actual_friction = equity_curve
     ```
   - Invocation: `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())`
   - Traceback: Line 205 binds `actual_trades = [0.01, 0.02]`. Line 240 executes `t.get("action", ...)`:
     ```
     AttributeError: 'float' object has no attribute 'get'
     ```

2. **Defect 2: Contract Violation & Return Corruption in Positional Pattern 2**
   - Code location: `core/backtest/result_evaluator.py:208-217`
     ```python
     actual_trades = list(trades) if isinstance(trades, (list, tuple)) else []
     if isinstance(daily_returns, (list, tuple, np.ndarray)):
         if len(daily_returns) == 0 or isinstance(daily_returns[0], (int, float, np.floating, np.integer)):
             actual_returns = [float(x) for x in daily_returns]
     ```
   - Invocation: `calculate_net_performance_metrics([{"action": "buy"}], [100.0, 102.0, 105.0], FrictionConfig())`
   - Behavior: The second argument `[100.0, 102.0, 105.0]` binds to parameter `daily_returns`. Line 210 treats wealth levels as daily percentage returns (+10,000% daily gains), producing gross return `1,102,717.0%` with `RuntimeWarning: overflow encountered in scalar power`.
   - Contract expectation: Wealth curve `[100.0, 102.0, 105.0]` represents a +5.0% gross return (`(105 - 100) / 100 = 0.05`).

3. **Defect 3: Unhandled `TypeError` on Non-Numeric or None `shares`**
   - Code location: `core/backtest/result_evaluator.py:250-254`
     ```python
     shares = t.get("shares", t.get("amount", t.get("qty", 0)))
     if shares > 0:
     ```
   - Invocation: `calculate_net_performance_metrics(trades=[{"shares": "100"}], daily_returns=[0.01])` or `{"shares": None}`
   - Traceback:
     ```
     TypeError: '>' not supported between instances of 'str' and 'int'
     TypeError: '>' not supported between instances of 'NoneType' and 'int'
     ```

### Analysis of Existing Invocations Across Codebase
Across test files (`tests/test_result_evaluator_care.py`, `tests/test_care_agents_ablation.py`, `tests/test_challenger_m4_1_frictions.py`, `tests/test_challenger_m4_2_ablation.py`), invocations span all of the following patterns:
1. `calculate_net_performance_metrics(trades=buys, daily_returns=returns, friction=friction)` (Keyword Pattern 1)
2. `calculate_net_performance_metrics(trades=buys, equity_curve=[100.0, 102.0], friction=friction)` (Keyword Pattern 2)
3. `calculate_net_performance_metrics(gross_returns, trades, friction)` (Positional Pattern 3)
4. `calculate_net_performance_metrics(gross_returns, [], friction)` (Positional Pattern 3 with zero trades)
5. `calculate_net_performance_metrics([], [], FrictionConfig())` (Empty returns & empty trades)
6. `calculate_net_performance_metrics(trades=trades, daily_returns=[0.01])` (Omitted friction fallback)
7. `calculate_net_performance_metrics(trades=[], daily_returns=returns)` (Empty trades with keyword returns)
8. `calculate_net_performance_metrics(daily_returns=returns, trades=[])` (Keyword order invariance)

---

## 2. Logic Chain

1. **Parameter Binding Ambiguity in Python**:
   - The Python function signature is declared as:
     `def calculate_net_performance_metrics(trades=None, daily_returns=None, equity_curve=None, friction=None, risk_free_rate=0.025, **kwargs)`
   - When a caller invokes a 3-argument positional call `calculate_net_performance_metrics(arg1, arg2, arg3)`:
     - `arg1` binds to `trades`
     - `arg2` binds to `daily_returns`
     - `arg3` binds to `equity_curve`
     - `friction` parameter receives `None`
   - Therefore, in **ALL** 3-argument calls where `arg3` is `FrictionConfig`:
     - `equity_curve` contains the `FrictionConfig` instance!
     - `friction` is `None`!
   - This directly explains why previous ad-hoc pattern checks failed: any check that assumes `equity_curve` is an equity curve when 3 positional args are passed is flawed. `equity_curve` must first be inspected for `isinstance(equity_curve, FrictionConfig)`.

2. **Differentiating Container Types (`trades` vs `numeric series`)**:
   - Every object passed to `arg1` or `arg2` belongs to one of three mutually exclusive categories:
     - **Trade List**: Sequence whose elements are mappings/dicts (`isinstance(obj[0], dict)`).
     - **Numeric Series**: Sequence/ndarray whose elements are numbers (`isinstance(obj[0], (int, float, np.floating, np.integer))`).
     - **Empty Sequence**: `len(obj) == 0`.
   - Because dicts and floats are fundamentally distinct types in Python, there is **zero ambiguity** between a non-empty trade list and a numeric series.
   - When one argument is an empty sequence `[]` and the other is a numeric series:
     - The numeric series **cannot** be trades (floats do not have trade fields like `.get("action")`).
     - Therefore, the numeric series is unconditionally returns or equity curve, and the empty sequence is unconditionally trades.
     - This directly resolves Defect 1.

3. **Distinguishing `daily_returns` from `equity_curve`**:
   - Consider a sequence of floats $S = [s_0, s_1, \dots, s_{k-1}]$:
     - **Mathematical Property 1 (Sign)**: Equity curves represent cumulative portfolio wealth $W_t \ge 0$. They never contain negative values. Daily returns $r_t = (P_t - P_{t-1})/P_{t-1}$ routinely contain negative values on down days. If $\exists x \in S: x < 0.0$, $S$ is strictly `daily_returns`.
     - **Mathematical Property 2 (Scale)**: In equity markets (and especially China A-shares with 10% or 20% daily price limits), single-day returns $r_t \le 0.20$. Equity curves commonly start at $100.0$ or $1000.0$, or compound past $1.5$. If $\exists x \in S: x > 1.5$, $S$ is strictly an `equity_curve`.
     - **Mathematical Property 3 (Base 1.0 Wealth vs +100% Day-1 Return)**: If an equity curve is normalized to $1.0$, $S[0] \approx 1.0$, all values $s_i \ge 0$, and the mean $\bar{S} \approx 1.0$ (typically $> 0.3$). If this were interpreted as daily returns, it would represent a strategy gaining $+100\%$ on day 1 and $> +50\%$ on every subsequent day, which is impossible in realistic trading.
     - **Mathematical Property 4 (Minimum Length)**: An equity curve requires at least 2 points to compute a return ($r_1 = W_1/W_0 - 1$). If $\text{len}(S) < 2$, it cannot be an equity curve.
   - Formulation of the heuristic function `_is_equity_curve(series)`:
     ```python
     def _is_equity_curve(series: Sequence[float]) -> bool:
         if not isinstance(series, (list, tuple, np.ndarray)) or len(series) < 2:
             return False
         if any(x < 0.0 for x in series):
             return False
         if any(x > 1.5 for x in series):
             return True
         if abs(float(series[0]) - 1.0) < 1e-3 and (sum(series) / len(series)) > 0.3:
             return True
         return False
     ```
   - This cleanly differentiates:
     - `[100.0, 102.0, 105.0]` -> True (Equity curve)
     - `[1.0, 1.02, 1.05]` -> True (Equity curve)
     - `[0.01, 0.02, 0.015]` -> False (Daily returns)
     - `[0.01, -0.005, 0.02]` -> False (Daily returns)
     - `[0.001] * 20` -> False (Daily returns)
     - `[-0.5, -0.5]` -> False (Daily returns)
   - This directly resolves Defect 2.

4. **Safe Coercion for Trade Records**:
   - Defect 3 occurs because `raw_shares = t.get("shares", ...)` can be `"100"` or `None`.
   - Wrapping extraction with `float(raw_shares)` within `try ... except (ValueError, TypeError)` safely defaults invalid or `None` values to `0.0`, triggering the default round-trip friction without throwing `TypeError`.
   - This directly resolves Defect 3.

---

## 3. Caveats

1. **Adversarial Assertion in `test_challenger_m4_1_frictions.py`**:
   - Challenger M4_1 created `tests/test_challenger_m4_1_frictions.py` containing class `TestChallengerEmpiricalVulnerabilities`.
   - Those 3 tests currently assert the *presence* of the defects (e.g. `with pytest.raises(AttributeError): calculate_net_performance_metrics([], [0.01, 0.02], friction)` and `assert res_pos["gross_return"] > 100000.0`).
   - When `calculate_net_performance_metrics` is remediated, these tests will fail because the bugs are fixed.
   - **Remedy**: The test suite in `tests/test_challenger_m4_1_frictions.py` must have `TestChallengerEmpiricalVulnerabilities` updated to assert the *corrected* behavior (or the class replaced with positive regression tests).
2. **Ambiguity on Length-1 Wealth Levels**:
   - An equity curve with only 1 point (e.g. `[100.0]`) cannot derive returns because $n=1$. The evaluator safely handles this by returning 0-metrics (`len(actual_returns) == 0`).
3. **Keyword Argument Aliases**:
   - Callers sometimes pass `gross_returns` or `returns` instead of `daily_returns`, or `equity` instead of `equity_curve`. Supporting these aliases via `kwargs` ensures total backward compatibility.

---

## 4. Conclusion

The polymorphic signature parser in `calculate_net_performance_metrics` can be made completely robust and deterministic using a 5-step resolution pipeline:
1. Keyword reconciliation & alias unpacking
2. Friction extraction (disentangling `FrictionConfig` from `equity_curve` parameter)
3. Container type classification & `_is_equity_curve` heuristic
4. Equity-to-returns derivation
5. Safe trade friction calculation with `shares` type coercion

### Proposed Implementation Code

Here is the complete proposed design for `core/backtest/result_evaluator.py` lines 170–267:

```python
def _is_equity_curve(series: Any) -> bool:
    """
    Heuristic to distinguish whether a numeric sequence represents an equity curve
    (cumulative wealth levels) or a series of daily returns.
    """
    if not isinstance(series, (list, tuple, np.ndarray)) or len(series) < 2:
        return False
    # If any negative value exists, it cannot be an equity curve
    if any(x < 0.0 for x in series):
        return False
    # If any value exceeds 1.5, it is an equity curve (daily returns > 150% do not occur in equities)
    if any(x > 1.5 for x in series):
        return True
    # For normalized equity curves starting near 1.0 (e.g. [1.0, 1.02, 0.98]):
    first_val = float(series[0])
    if abs(first_val - 1.0) < 1e-3 and (sum(series) / len(series)) > 0.3:
        return True
    return False


def _is_trade_list(obj: Any) -> bool:
    """Returns True if obj is a non-empty sequence of trade dicts."""
    if isinstance(obj, (list, tuple)) and len(obj) > 0:
        return isinstance(obj[0], (dict, collections.abc.Mapping))
    return False


def _is_numeric_sequence(obj: Any) -> bool:
    """Returns True if obj is a non-empty sequence of numbers."""
    if isinstance(obj, (list, tuple, np.ndarray)) and len(obj) > 0:
        return isinstance(obj[0], (int, float, np.floating, np.integer))
    return False


def calculate_net_performance_metrics(
    trades: Optional[Any] = None,
    daily_returns: Optional[Any] = None,
    equity_curve: Optional[Any] = None,
    friction: Optional[FrictionConfig] = None,
    risk_free_rate: float = 0.025,
    **kwargs,
) -> Dict[str, float]:
    """
    Computes Net Sharpe, Net Sortino, Net Calmar, and Maximum Drawdown after deducting
    China A-share frictions (5 bps sell stamp duty, 2.5 bps commission, configurable slippage).
    Provides annualized metrics assuming 252 trading days.

    Supports multiple polymorphic calling conventions:
    1. calculate_net_performance_metrics(trades, daily_returns=..., equity_curve=..., friction=...)
    2. calculate_net_performance_metrics(trades, equity_curve, friction)
    3. calculate_net_performance_metrics(gross_returns, trades, friction)
    """
    # Step 1: Reconcile keyword arguments & aliases
    if "risk_free_rate" in kwargs:
        risk_free_rate = float(kwargs["risk_free_rate"])

    if daily_returns is None:
        if "gross_returns" in kwargs:
            daily_returns = kwargs["gross_returns"]
        elif "returns" in kwargs:
            daily_returns = kwargs["returns"]

    if equity_curve is None and "equity" in kwargs:
        equity_curve = kwargs["equity"]

    if trades is None and "trades" in kwargs:
        trades = kwargs["trades"]

    # Step 2: Friction extraction (disentangle FrictionConfig from equity_curve parameter)
    actual_friction: Optional[FrictionConfig] = None
    if isinstance(equity_curve, FrictionConfig):
        actual_friction = equity_curve
        equity_curve = None
    elif isinstance(friction, FrictionConfig):
        actual_friction = friction
    elif "friction" in kwargs and isinstance(kwargs["friction"], FrictionConfig):
        actual_friction = kwargs["friction"]
    elif friction is not None:
        actual_friction = friction
    elif "friction" in kwargs:
        actual_friction = kwargs["friction"]

    if actual_friction is None:
        actual_friction = FrictionConfig()

    # Step 3: Polymorphic parsing of trades, returns, equity_curve
    actual_returns: Optional[List[float]] = None
    actual_trades: List[Dict[str, Any]] = []
    actual_equity: Optional[List[float]] = None

    if equity_curve is not None and _is_numeric_sequence(equity_curve):
        actual_equity = [float(x) for x in equity_curve]
        if _is_numeric_sequence(trades):
            actual_returns = [float(x) for x in trades]
            actual_trades = []
        else:
            actual_trades = list(trades) if isinstance(trades, (list, tuple)) else []
            if _is_numeric_sequence(daily_returns):
                actual_returns = [float(x) for x in daily_returns]
    else:
        # equity_curve is None (or was FrictionConfig and has been extracted)
        if _is_numeric_sequence(trades):
            # Pattern 3: (gross_returns, trades, friction)
            if _is_equity_curve(trades):
                actual_equity = [float(x) for x in trades]
            else:
                actual_returns = [float(x) for x in trades]

            if _is_trade_list(daily_returns) or (isinstance(daily_returns, (list, tuple)) and len(daily_returns) == 0):
                actual_trades = list(daily_returns)
            else:
                actual_trades = []
        elif _is_trade_list(trades):
            # Pattern 1 & 2: trades is first argument
            actual_trades = list(trades)
            if _is_numeric_sequence(daily_returns):
                if _is_equity_curve(daily_returns):
                    # Pattern 2: (trades, equity_curve, friction)
                    actual_equity = [float(x) for x in daily_returns]
                else:
                    # Pattern 1: (trades, daily_returns, friction)
                    actual_returns = [float(x) for x in daily_returns]
            elif isinstance(daily_returns, (list, tuple, np.ndarray)) and len(daily_returns) == 0:
                actual_returns = []
        else:
            # trades is empty [] or None
            if _is_trade_list(daily_returns):
                # Pattern 3 with empty returns: ([], trades, friction)
                actual_trades = list(daily_returns)
                actual_returns = []
            elif _is_numeric_sequence(daily_returns):
                # Pattern 1/2 with empty trades: ([], returns/equity, friction)
                actual_trades = []
                if _is_equity_curve(daily_returns):
                    actual_equity = [float(x) for x in daily_returns]
                else:
                    actual_returns = [float(x) for x in daily_returns]
            else:
                actual_trades = []
                actual_returns = []

    # Step 4: Derive daily returns from equity curve if needed
    if actual_returns is None and actual_equity is not None and len(actual_equity) > 1:
        actual_returns = [
            (actual_equity[i] / actual_equity[i - 1]) - 1.0
            for i in range(1, len(actual_equity))
            if actual_equity[i - 1] > 0
        ]
    elif actual_returns is None:
        actual_returns = []

    # Step 5: Safe trade friction calculation with type coercion for shares
    total_frictions_bps = 0.0
    for t in actual_trades:
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
            raw_shares = t.get("shares", t.get("amount", t.get("qty", None)))
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

---

## 5. Verification Method

### Concrete Verification Steps for Implementation Worker:
1. Apply the proposed signature parsing and friction calculation logic to `core/backtest/result_evaluator.py`.
2. Update the adversarial tests in `tests/test_challenger_m4_1_frictions.py` (`TestChallengerEmpiricalVulnerabilities`) to assert the **expected successful behavior**:
   ```python
   def test_positional_empty_trades_signature_resolved(self):
       trades = []
       daily_returns = [0.01, 0.02]
       res = calculate_net_performance_metrics(trades, daily_returns, FrictionConfig())
       assert res["trade_count"] == 0
       assert res["total_frictions_bps"] == 0.0
       assert len(daily_returns) == 2

   def test_positional_equity_curve_resolved(self):
       trades = [{"action": "buy"}]
       equity_curve = [100.0, 102.0, 105.0]
       res = calculate_net_performance_metrics(trades, equity_curve, FrictionConfig())
       assert res["gross_return"] == pytest.approx(0.05, abs=1e-4)
       assert res["trade_count"] == 1

   def test_non_numeric_shares_type_coercion_resolved(self):
       res_str = calculate_net_performance_metrics(trades=[{"shares": "100"}], daily_returns=[0.01])
       assert res_str["total_frictions_bps"] == 7.5
       res_none = calculate_net_performance_metrics(trades=[{"shares": None}], daily_returns=[0.01])
       assert res_none["total_frictions_bps"] == 20.0
   ```
3. Run test suites:
   ```bash
   # Run friction test suite
   .venv/bin/pytest tests/test_challenger_m4_1_frictions.py -v

   # Run result evaluator tests
   .venv/bin/pytest tests/test_result_evaluator_care.py -v

   # Run complete CARE-Agents ablation suite
   .venv/bin/pytest tests/test_care_agents_ablation.py tests/test_challenger_m4_2_ablation.py -v

   # Run all evaluator & ablation tests together
   .venv/bin/pytest tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_challenger_m4_2_ablation.py -v
   ```
4. Verify that 100% of tests pass without any warnings or regressions.
