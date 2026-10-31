# Empirical Challenge Report: Milestone M4 — China A-Share Frictions & Net Metrics

**Agent**: Challenger M4_1 (Empirical Challenger)  
**Target Code**: `core/backtest/result_evaluator.py`  
**Test Suite**: `tests/test_challenger_m4_1_frictions.py`  
**Verdict**: **CHALLENGE**

---

## 1. Observation

### Target Under Test
- File: `core/backtest/result_evaluator.py`
  - Class: `FrictionConfig` (lines 135–168)
  - Function: `calculate_net_performance_metrics` (lines 170–338)
  - Function: `calculate_cbs_and_coordination_cost` (lines 340–432)
  - Function: `calculate_multi_regime_breakdown` (lines 435–498)
  - Contracts: `PROJECT.md` §5 (lines 115–124) and `ORIGINAL_REQUEST.md` §R4 (lines 54–57, 77)

### Executed Empirical Tests
Created and executed an adversarial stress test suite in `tests/test_challenger_m4_1_frictions.py` containing 42 tests across 6 classes:
1. `TestAsymmetricStampDuty` (11 tests): Buy 0 bps vs sell 5.0 bps stamp duty, action casing, whitespace, field aliases, signed shares, fallback defaults, custom parameters.
2. `TestBoundaryTradeConfigurations` (10 tests): Zero trades (0 bps friction), buy-only trades linear scaling, sell-only trades linear scaling, trade count integrity, zero trades with empty returns.
3. `TestExtremeFrictionsAndSlippage` (6 tests): Zero slippage (0.0 bps), extreme slippage (100.0 bps), extreme commission (100.0 bps), monotonic return drag, high-frequency extreme friction, numerical stability.
4. `TestDegenerateEquityCurves` (7 tests): Flat zero returns (zero Sharpe std protection, Sortino finite), zero-variance positive returns, constant negative returns, varying negative returns, flash crash single-day drawdown (-90%), total bankruptcy (-100% loss CAGR clamping), consecutive wipes.
5. `TestPolymorphicCallingSignatures` (6 tests): Keyword Pattern 1, keyword Pattern 2, positional Pattern 3, default friction fallback, risk-free rate sensitivity, CBS and regime breakdown integration.
6. `TestChallengerEmpiricalVulnerabilities` (3 tests): Empirical reproduction and assertion of positional calling bugs and unhandled `TypeError` exceptions.

### Test Execution Commands & Verbatim Outputs
Command 1 (Adversarial Suite):
```bash
.venv/bin/pytest tests/test_challenger_m4_1_frictions.py -v
```
Verbatim Output:
```
======================== 42 passed, 8 warnings in 1.41s ========================
```

Command 2 (Full Milestone M4 Suite):
```bash
.venv/bin/pytest tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py -v
```
Verbatim Output:
```
======================= 126 passed, 8 warnings in 1.87s ========================
```

### Observed Defects & Verbatim Exceptions

#### Defect 1: Crash on Empty Trades with Positional Returns (`AttributeError`)
- **Code Location**: `core/backtest/result_evaluator.py:202-205`
```python
202:    elif trades == [] and isinstance(daily_returns, (list, tuple)) and isinstance(equity_curve, FrictionConfig):
203:        # Pattern: ([], [], FrictionConfig)
204:        actual_returns = []
205:        actual_trades = list(daily_returns)
206:        actual_friction = equity_curve
```
- **Observed Behavior**:
  When calling `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())`:
  Line 205 erroneously assigns `actual_trades = list(daily_returns)` (which is `[0.01, 0.02]`).
  Subsequently, line 240 attempts `action = str(t.get("action", ...))` on each float:
  ```
  AttributeError: 'float' object has no attribute 'get'
  ```

#### Defect 2: Contract Violation & Return Corruption in Positional Pattern 2
- **Contract Specified**:
  `PROJECT.md` line 121:
  ```python
  def calculate_net_performance_metrics(trades: List[Dict[str, Any]], equity_curve: List[float], friction: FrictionConfig) -> Dict[str, float]: ...
  ```
  `core/backtest/result_evaluator.py:185`:
  ```
  2. calculate_net_performance_metrics(trades, equity_curve, friction)
  ```
- **Observed Behavior**:
  Calling `calculate_net_performance_metrics([{"action": "buy"}], [100.0, 102.0, 105.0], FrictionConfig())`:
  The 2nd positional argument binds to parameter `daily_returns`. Line 210 executes:
  ```python
  if isinstance(daily_returns, (list, tuple, np.ndarray)):
      actual_returns = [float(x) for x in daily_returns]
  ```
  `actual_returns` receives `[100.0, 102.0, 105.0]`, interpreting wealth levels as daily returns of 10,000%!
  Calculated Gross Return: `1,102,717.0` (1.1 million percent) with runtime warning:
  ```
  RuntimeWarning: overflow encountered in scalar power
    cagr = float(equity[-1] ** (252.0 / max(1, n)) - 1.0)
  ```
  Expected Gross Return from wealth curve `[100.0, 102.0, 105.0]`: `+0.05` (+5.0%).

#### Defect 3: Unhandled `TypeError` on Non-Numeric or None `shares`
- **Code Location**: `core/backtest/result_evaluator.py:250-254`
```python
250:        shares = t.get("shares", t.get("amount", t.get("qty", 0)))
251:        if shares > 0:
```
- **Observed Behavior**:
  If trade dictionary contains `{"shares": "100"}` or `{"shares": None}`, line 251 raises:
  `TypeError: '>' not supported between instances of 'str' and 'int'` or `'NoneType' and 'int'`.

---

## 2. Logic Chain

1. **Mathematical Soundness of Confirmed Dimensions**:
   - *Asymmetric Stamp Duty*: In BUY trades, stamp duty is strictly 0.0 bps; in SELL trades, stamp duty is strictly 5.0 bps. Invariant $Frictions(Sell) - Frictions(Buy) = N \times 5.0\text{ bps}$ was verified across $N \in \{1, 5, 20, 100\}$.
   - *Boundary Trade Accumulation*: Frictions scale strictly linearly ($N \times 7.5\text{ bps}$ for buys, $N \times 12.5\text{ bps}$ for sells). Zero trades incur strictly 0.0 bps, and gross return equals net return.
   - *Extreme Slippage & Commissions*: Varying slippage from 0 to 100 bps (1.0% per trade) and commissions to 100 bps induces strictly monotonic return drag without NaN or infinity across Sharpe, Sortino, Calmar, and MDD.
   - *Degenerate Equity Curves*: Constant zero returns, monotonic positive returns, monotonic negative returns, flash crashes (-90%), and total bankruptcy (-100%) all handle division-by-zero safely (Sharpe clamped to 0.0 on zero variance, CAGR clamped to -1.0 when equity drops to $\le 0$).

2. **Root Cause of Defect 1 (Positional Empty Trades Crash)**:
   - Line 202 tests `trades == [] and isinstance(daily_returns, (list, tuple)) and isinstance(equity_curve, FrictionConfig)`.
   - The developer assumed this pattern ONLY occurs when calling Pattern 3 with empty returns: `(gross_returns=[], trades, friction)`.
   - However, when a caller passes `([], float_returns, friction)` (i.e. zero trades and a list of daily returns or equity curve), line 205 assigns `actual_trades = list(daily_returns)`.
   - Line 240 then iterates over floats and calls `.get()`, causing an immediate crash.

3. **Root Cause of Defect 2 (Positional Pattern 2 Contract Violation)**:
   - Interface Contract 5 in `PROJECT.md` line 121 and docstring line 185 state that `(trades, equity_curve, friction)` is a valid calling convention.
   - But in the python definition, parameter 2 is named `daily_returns`.
   - Because `[100.0, 102.0, 105.0]` is a list of floats, line 210 accepts it as daily returns, bypassing the equity derivation logic on line 225.
   - Wealth levels are compounded as daily percentages, corrupting backtest metrics by a factor of 22,000,000x.

4. **Blast Radius Assessment**:
   - Any external workflow, automated evaluation script, or user relying on positional arguments as specified in `PROJECT.md` line 121 will either crash (`AttributeError`) or receive completely corrupted performance statistics (> 1,000,000% returns).
   - This directly breaks interface contract compliance.

---

## 3. Caveats

- Keyword argument calls (`trades=..., daily_returns=...` and `trades=..., equity_curve=...`) and positional Pattern 3 (`gross_returns, trades, friction`) work correctly and pass all unit tests.
- When `shares` is an integer or float, trade classification works as expected. The `TypeError` only arises if raw trade records contain string numbers (e.g. from JSON payloads without type casting) or explicit `None`.

---

## 4. Conclusion

**Verdict**: **CHALLENGE**

While the core quantitative formulas (stamp duty asymmetry, linear friction scaling, downside deviation, drawdown tracking, and CAGR protection) are mathematically robust, `core/backtest/result_evaluator.py` fails to satisfy its positional calling contract and contains reproducible crash paths under boundary arguments.

### Actionable Remediations for Implementation Worker:
1. **Fix Signature Dispatch (lines 193–220)**:
   Inspect the elements of the 2nd positional argument:
   - If the 2nd argument contains dicts, it represents `trades` (Pattern 3: `gross_returns, trades, friction`).
   - If the 2nd argument contains floats:
     - Check if values exceed normal daily return bounds (e.g. `any(abs(x) > 1.0 for x in arg2)` or wealth levels $> 1.5$): treat as `equity_curve` and derive daily returns.
     - Alternatively, if `trades` is a list of dicts (or `[]` where 2nd arg is floats) and 3rd arg is `FrictionConfig`, check whether 2nd arg represents daily returns or equity curve.
     - Specifically, remove `actual_trades = list(daily_returns)` when `daily_returns` contains floats.
2. **Safe Coercion for `shares` (lines 250–254)**:
   ```python
   raw_shares = t.get("shares", t.get("amount", t.get("qty", 0)))
   try:
       shares = float(raw_shares) if raw_shares is not None else 0.0
   except (ValueError, TypeError):
       shares = 0.0
   ```

---

## 5. Verification Method

To independently verify all findings and reproduction tests:
```bash
# Run Challenger M4_1 test suite (42 tests, 100% passing reproduction of invariants and defects)
.venv/bin/pytest tests/test_challenger_m4_1_frictions.py -v

# Run full M4 evaluation and ablation suite (126 tests)
.venv/bin/pytest tests/test_challenger_m4_1_frictions.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py -v
```

Inspect tests in `tests/test_challenger_m4_1_frictions.py`:
- `test_positional_empty_trades_signature_defect`
- `test_positional_equity_curve_misinterpretation_defect`
- `test_non_numeric_shares_type_error_defect`
