# Forensic Integrity Audit Report: Milestone M4 (Evaluator & Cost/Friction Accounting)

**Work Product**:
- `core/backtest/result_evaluator.py`
- `tests/test_result_evaluator_care.py`
- `tests/test_care_agents_ablation.py`

**Profile**: General Project
**Integrity Mode**: Development (from `ORIGINAL_REQUEST.md`)
**Verdict**: **CLEAN**

---

## 1. Observation

### 1.1 Source Code Inspection (`core/backtest/result_evaluator.py`)
- **Friction Modeling** (lines 135–168):
  `FrictionConfig` specifies `sell_stamp_duty_bps = 5.0` (levied exclusively on SELL trades), `commission_bps = 2.5` (levied on BUY and SELL trades), and `slippage_bps = 5.0` (configurable), with property alias `stamp_duty_bps` for backward compatibility.
- **Net Performance Calculation** (lines 170–337):
  `calculate_net_performance_metrics` computes:
  - Frictions accumulated across all trades: BUY incurs commission + slippage (7.5 bps default); SELL incurs stamp duty + commission + slippage (12.5 bps default); round-trip incurs 20.0 bps default.
  - Periodic friction deduction: `friction_per_period = (total_frictions_bps / 10000.0) / max(1, n)`.
  - Net return series: `net_returns = gross_arr - friction_per_period`.
  - Compounded net total return: `equity = np.cumprod(1.0 + net_returns)`.
  - Annualized CAGR: `equity[-1] ** (252.0 / max(1, n)) - 1.0` (with boundary check for zero/negative equity).
  - Maximum Drawdown: Peak-to-trough calculation starting from initial capital peak $W_0 = 1.0$ via `np.maximum.accumulate`.
  - Net Sharpe: Annualized by $\sqrt{252}$ over daily risk-free rate $R_f / 252$, guarded against zero variance (`std_excess > 1e-12`).
  - Net Sortino: Downside semivariance deviation below daily risk-free rate annualized by $\sqrt{252}$, guarded against zero downside deviation (`downside_dev > 1e-12`).
  - Net Calmar: CAGR divided by $|MDD|$, guarded against zero drawdown (`abs(net_mdd) > 1e-6`).
- **Realized CBS & Latency Metrics** (lines 340–433):
  `calculate_cbs_and_coordination_cost` calculates average realized CBS hurdle, average token consumption per decision (parsing polymorphic token keys `tokens`, `tokens_consumed`, `prompt_tokens` + `completion_tokens`), average latency per decision in milliseconds and seconds, fast-path bypass rate, and debate trigger rate.
- **Multi-Regime Partitioning** (lines 435–499):
  `calculate_multi_regime_breakdown` subsets daily returns and regimes into `"bull"`, `"bear"`, and `"sideways"`, deducting period frictions and generating separate return, Sharpe, Sortino, Calmar, and MDD statistics per regime.
- **Evaluation Context Integration** (lines 611–664):
  `_build_evaluation_context` dynamically incorporates net performance metrics and multi-regime breakdowns into the LLM prompt context, auto-deriving net metrics from trade and return history if not pre-computed.

### 1.2 Static Analysis & Prohibited Pattern Searches
- Search for hardcoded return/ratio constants: Zero instances of hardcoded return strings or constant Sharpe/Sortino ratios returned. All metric calculations utilize dynamic numpy arrays and mathematical operations.
- Search for dummy facade stubs: Zero occurrences of `pass`, `return <constant>`, `NotImplementedError`, or mock delegators in `core/backtest/result_evaluator.py`.
- Search for pre-populated or fabricated test artifacts: No pre-populated result files or fake evaluation logs exist.

### 1.3 Test Suite Verification (`tests/test_result_evaluator_care.py` & `tests/test_care_agents_ablation.py`)
- `test_result_evaluator_care.py` contains 32 unit and integration tests verifying China A-share friction accounting, risk ratios, polymorphic signatures, realized CBS, multi-regime partitioning, and evaluation prompt formatting.
- `test_care_agents_ablation.py` contains 52 tests covering all 4 tiers of the CARE-Agents opaque-box architecture:
  - Tier 1: Features 1–20 across R1, R2, R3, R4.
  - Tier 2: Boundary value analysis & numerical extremes (JSD boundaries at 0.12, CBS boundaries at 15.0 bps, extreme Brier losses, zero volume/zero variance).
  - Tier 3: Pairwise cross-feature interactions.
  - Tier 4: Real-world market scenarios comparing all 4 ablation configurations (Config A: Linear, Config B: Vanilla TradingAgents, Config C: Self-Debate 1-Shot, Config D: CARE-Agents).
- Zero instances of trivial assertions (`assert True`, tautologies) were found in either test file.

### 1.4 Test Execution Results
- Command: `.venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py -v`
  - Output: `84 passed, 7 warnings in 2.10s`
- Full regression suite across M1–M4:
  - Command: `.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_regime_weights_signal.py tests/test_regime_memory_reflection.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py`
  - Output: `185 passed, 19 warnings in 23.84s`

### 1.5 Independent Mathematical Verification
An independent forensic script was run in the environment to compare the output of `calculate_net_performance_metrics` against manual hand calculations:
- Frictions: 2 Buys + 1 Sell = $7.5 + 7.5 + 12.5 = 27.5\text{ bps}$. Match confirmed.
- Net Equity Compounding: Exact match with hand-calculated cumulative product ($< 10^{-9}$ difference).
- Sharpe Ratio: Exact match with excess return / sample standard deviation annualized by $\sqrt{252}$ ($< 10^{-9}$ difference).
- Sortino Ratio: Exact match with excess return / downside semivariance annualized by $\sqrt{252}$ ($< 10^{-9}$ difference).
- Maximum Drawdown: Exact match with peak-to-trough formula ($< 10^{-9}$ difference).

---

## 2. Logic Chain

1. **Premise**: Milestone M4 requires implementing net-of-cost performance metrics (China A-share 5 bps sell stamp duty, 2.5 bps commission, configurable slippage), realized CBS accounting, multi-regime breakdowns, and a 4-configuration ablation benchmark suite running deterministically offline.
2. **Observation**: `core/backtest/result_evaluator.py` implements `FrictionConfig`, `calculate_net_performance_metrics`, `calculate_cbs_and_coordination_cost`, and `calculate_multi_regime_breakdown` using genuine numeric calculations with standard numpy/math routines.
3. **Observation**: BUY trades incur commission + slippage without stamp duty, SELL trades incur stamp duty + commission + slippage, exactly reflecting China A-share market mechanics.
4. **Observation**: Numerical edge cases (zero variance, constant returns, $n=1$, portfolio total wipeout) are guarded with zero-division protections and boundary clamping.
5. **Observation**: `tests/test_result_evaluator_care.py` and `tests/test_care_agents_ablation.py` execute 84 authentic tests with non-trivial assertions that run deterministically offline in 2.10 seconds.
6. **Observation**: The full test suite across M1, M2, M3, and M4 passes 100% (185/185 tests) without regressions.
7. **Deduction**: The work product satisfies all functional and non-functional requirements of Milestone M4 without any integrity violations or deceptive patterns.

---

## 3. Caveats

- In `calculate_net_performance_metrics`, when trades are provided without specific trade sizes or equity values, the total accumulated friction basis points are distributed uniformly across the return periods (`friction_per_period = total_frictions_bps / 10000.0 / n`). This is a standard and expected convention for backtest summary evaluation when per-bar trade execution fills are not mapped to exact intraday cash balances.
- No caveats regarding code authenticity or integrity.

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone M4 fulfills all requirements in `ORIGINAL_REQUEST.md` (R4) and interface contracts in `PROJECT.md`:
1. Accurate net-of-cost metrics accounting for China A-share trading frictions (5 bps stamp duty on sells, 2.5 bps commission on buys and sells, configurable slippage).
2. Annualized Net Sharpe, Sortino, Calmar, and Maximum Drawdown formulas are mathematically authentic.
3. Realized CBS hurdle, token consumption, and latency metrics are correctly calculated.
4. Multi-regime partitioning across bull, bear, and sideways windows is fully operational.
5. All 4 ablation configurations (Config A, B, C, D) run deterministically offline in `tests/test_care_agents_ablation.py`.
6. Zero facades, zero hardcoded dummy results, zero pre-populated verification artifacts.

---

## 5. Verification Method

To independently verify this audit:
```bash
# 1. Run M4 test suite (evaluator and 4-way ablation suite):
.venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py -v

# 2. Run full cross-milestone test suite (M1-M4):
.venv/bin/pytest tests/test_analyst_posteriors_cbs.py tests/test_regime_weights_signal.py tests/test_regime_memory_reflection.py tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py

# 3. Verify static authenticity and absence of hardcoded dummy stubs:
grep -rn "NotImplemented" core/backtest/result_evaluator.py
grep -rn "assert True" tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py
```
Invalidation conditions:
- Any test failure in `tests/test_result_evaluator_care.py` or `tests/test_care_agents_ablation.py`.
- Discovery of hardcoded Sharpe/Sortino values or mock test bypassing in `core/backtest/result_evaluator.py`.
