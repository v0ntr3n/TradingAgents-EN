# Handoff Report: Milestone M4 Test Suite Coverage & Regression Risk Analysis

- **Agent**: Explorer M4_it2_3
- **Working Directory**: `/home/bramy/Documents/TradingAgents-EN/.agents/teamwork/teamwork_explorer_m4_it2_3`
- **Target Files**:
  - `core/backtest/result_evaluator.py`
  - `tests/test_result_evaluator_care.py`
  - `tests/test_care_agents_ablation.py`
  - `tests/test_challenger_m4_1_frictions.py`
  - `tests/test_challenger_m4_2_ablation.py`
- **Reference Contracts**: `ORIGINAL_REQUEST.md` (§R4), `PROJECT.md` (§5, lines 113–124)

---

## 1. Observation

### 1.1 Direct Inspection of Target Implementation (`core/backtest/result_evaluator.py`)
In `core/backtest/result_evaluator.py`:
- Lines 170–177 define signature:
  ```python
  def calculate_net_performance_metrics(
      trades: Optional[Any] = None,
      daily_returns: Optional[Any] = None,
      equity_curve: Optional[Any] = None,
      friction: Optional[FrictionConfig] = None,
      risk_free_rate: float = 0.025,
      **kwargs,
  ) -> Dict[str, float]:
  ```
- Lines 202–206 contain the empty trades dispatch logic:
  ```python
  elif trades == [] and isinstance(daily_returns, (list, tuple)) and isinstance(equity_curve, FrictionConfig):
      # Pattern: ([], [], FrictionConfig)
      actual_returns = []
      actual_trades = list(daily_returns)
      actual_friction = equity_curve
  ```
- Lines 208–217 handle Pattern 1 & 2 dispatch:
  ```python
  actual_trades = list(trades) if isinstance(trades, (list, tuple)) else []
  if isinstance(daily_returns, (list, tuple, np.ndarray)):
      if len(daily_returns) == 0 or isinstance(daily_returns[0], (int, float, np.floating, np.integer)):
          actual_returns = [float(x) for x in daily_returns]
  if isinstance(equity_curve, FrictionConfig):
      actual_friction = equity_curve
  elif isinstance(equity_curve, (list, tuple, np.ndarray)):
      actual_equity = [float(x) for x in equity_curve]
  ```
- Lines 250–254 contain the share quantity checking logic:
  ```python
  shares = t.get("shares", t.get("amount", t.get("qty", 0)))
  if shares > 0:
      total_frictions_bps += actual_friction.commission_bps + actual_friction.slippage_bps
  elif shares < 0:
      total_frictions_bps += (
          actual_friction.sell_stamp_duty_bps
          + actual_friction.commission_bps
          + actual_friction.slippage_bps
      )
  ```

### 1.2 Observed Defects & Verbatim Errors

1. **Defect 1: Crash on Empty Trades with Positional Returns (`AttributeError`)**
   - **Trigger**: `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())`
   - **Observation**:
     - Line 202 evaluates to `True` because `trades == []`, `isinstance(daily_returns, list)` is `True`, and the 3rd positional argument binds to parameter `equity_curve` which is `FrictionConfig`.
     - Line 205 assigns `actual_trades = list(daily_returns)` -> `actual_trades = [0.01, 0.02]`.
     - Line 240 executes `action = str(t.get("action", ...))` on `t = 0.01` (float).
     - **Verbatim Error**:
       ```
       AttributeError: 'float' object has no attribute 'get'
       ```

2. **Defect 2: Contract Violation & Return Corruption in Positional Pattern 2**
   - **Contract**: `PROJECT.md` line 121:
     `def calculate_net_performance_metrics(trades: List[Dict[str, Any]], equity_curve: List[float], friction: FrictionConfig) -> Dict[str, float]:`
   - **Trigger**: `calculate_net_performance_metrics([{"action": "buy"}], [100.0, 102.0, 105.0], FrictionConfig())`
   - **Observation**:
     - The second positional argument binds to `daily_returns`.
     - Line 210 executes `actual_returns = [float(x) for x in daily_returns]`, setting `actual_returns = [100.0, 102.0, 105.0]`.
     - `actual_equity` is never set, so lines 225–230 (deriving returns from equity curve) are skipped.
     - Wealth levels are treated as daily return percentages (+10,000%, +10,200%, +10,500%).
     - **Verbatim Output**:
       Calculated `gross_return` = `1102717.0` (1.1 million percent) vs expected `+0.05` (+5.0%).
       ```
       RuntimeWarning: overflow encountered in scalar power
         cagr = float(equity[-1] ** (252.0 / max(1, n)) - 1.0)
       ```

3. **Defect 3: Unhandled `TypeError` on Non-Numeric or None `shares`**
   - **Trigger**: `calculate_net_performance_metrics(trades=[{"shares": "100"}], daily_returns=[0.01])` or `trades=[{"shares": None}]`
   - **Observation**:
     - Line 250 retrieves `shares = "100"` or `shares = None`.
     - Line 251 executes `if shares > 0:`.
     - **Verbatim Error**:
       ```
       TypeError: '>' not supported between instances of 'str' and 'int'
       TypeError: '>' not supported between instances of 'NoneType' and 'int'
       ```

### 1.3 Complete Inventory of Tests Exercising `calculate_net_performance_metrics`
Across all 4 test files, a total of **68 test functions (74 test executions)** exercise `calculate_net_performance_metrics` (55 direct calls, 13 indirect calls):

#### A. `tests/test_result_evaluator_care.py` (17 Direct + 1 Indirect = 18 Tests)
| Class | Test Method | Line # | Invocation Convention | Description |
|---|---|---|---|---|
| `TestNetPerformanceMetricsFrictions` | `test_buy_trade_incurs_no_stamp_duty` | 54–64 | Keyword: `trades=..., daily_returns=..., friction=...` | 7.5 bps buy friction |
| `TestNetPerformanceMetricsFrictions` | `test_sell_trade_incurs_stamp_duty` | 65–73 | Keyword: `trades=..., daily_returns=..., friction=...` | 12.5 bps sell friction |
| `TestNetPerformanceMetricsFrictions` | `test_round_trip_friction` | 74–86 | Keyword: `trades=..., daily_returns=..., friction=...` | 20.0 bps round-trip friction |
| `TestNetPerformanceMetricsFrictions` | `test_zero_slippage_configuration` | 87–97 | Keyword: `trades=..., daily_returns=..., friction=...` | 10.0 bps zero slippage |
| `TestNetPerformanceMetricsFrictions` | `test_multiple_trades_linear_accumulation` | 98–109 | Keyword: `trades=..., daily_returns=..., friction=...` | 47.5 bps 5 trades |
| `TestNetPerformanceMetricsFrictions` | `test_signed_shares_or_roundtrip_fallback` | 110–118 | Keyword: `trades=..., daily_returns=...` | Signed int shares |
| `TestNetPerformanceMetricsRiskRatios` | `test_annualized_net_sharpe_with_risk_free_rate` | 123–134 | Keyword: `trades=..., daily_returns=..., risk_free_rate=...` | Annualized Sharpe ratio |
| `TestNetPerformanceMetricsRiskRatios` | `test_zero_variance_sharpe_protection` | 135–141 | Keyword: `daily_returns=..., trades=...` | Zero variance Sharpe protection |
| `TestNetPerformanceMetricsRiskRatios` | `test_annualized_net_sortino_ratio` | 142–150 | Keyword: `trades=..., daily_returns=...` | Downside deviation Sortino |
| `TestNetPerformanceMetricsRiskRatios` | `test_maximum_drawdown_peak_to_trough` | 151–160 | Keyword: `trades=..., daily_returns=..., friction=...` | Peak to trough MDD (-20%) |
| `TestNetPerformanceMetricsRiskRatios` | `test_monotonic_positive_returns_zero_mdd` | 161–167 | Keyword: `trades=..., daily_returns=..., friction=...` | Monotonic returns zero MDD |
| `TestNetPerformanceMetricsRiskRatios` | `test_net_calmar_ratio` | 168–176 | Keyword: `trades=..., daily_returns=...` | Calmar = CAGR / \|MDD\| |
| `TestNetPerformanceMetricsRiskRatios` | `test_disastrous_returns_total_loss_handling` | 177–183 | Keyword: `trades=..., daily_returns=...` | Catastrophic loss handling |
| `TestNetPerformanceMetricsSignatures` | `test_signature_pattern_1_explicit_kwargs` | 188–195 | Keyword: `trades=..., daily_returns=..., friction=...` | Pattern 1 explicit kwargs |
| `TestNetPerformanceMetricsSignatures` | `test_signature_pattern_2_equity_curve_derivation` | 196–203 | Keyword: `trades=..., equity_curve=..., friction=...` | Pattern 2 via **keywords only** |
| `TestNetPerformanceMetricsSignatures` | `test_signature_pattern_3_positional_gross_returns` | 204–212 | Positional: `(gross_returns, trades, friction)` | Pattern 3 positional gross returns |
| `TestNetPerformanceMetricsSignatures` | `test_empty_returns_and_trades` | 213–224 | Positional: `([], [], FrictionConfig())` | Pattern 3 empty inputs |
| `TestEvaluationContextIntegration` | `test_context_auto_computes_net_metrics_from_trades_and_daily_returns` | 378–392 | Indirect call via `_build_evaluation_context` | Automatic backtest summary injection |

#### B. `tests/test_care_agents_ablation.py` (7 Direct + 7 Indirect = 14 Tests)
| Class | Test Method | Line # | Invocation Convention | Description |
|---|---|---|---|---|
| `TestTier1FeatureCoverage` | `test_f16_net_of_cost_metrics_deduction` | 950–967 | Positional: `(gross_returns, trades, friction)` | Feature 16 net metric calculation |
| `TestTier2BoundaryExtremes` | `test_t2_zero_trades_empty_equity` | 1172–1178 | Positional: `([], [], FrictionConfig())` | Empty returns zero division protection |
| `TestTier2BoundaryExtremes` | `test_t2_zero_volatility_sharpe_protection` | 1179–1185 | Positional: `(constant_returns, [], FrictionConfig())` | Constant returns Sharpe protection |
| `TestTier2BoundaryExtremes` | `test_t2_pure_sell_turnover_stamp_duty` | 1186–1191 | Positional: `([0.01], trades, FrictionConfig())` | Sell order 12.5 bps friction |
| `TestTier2BoundaryExtremes` | `test_t2_pure_buy_turnover_no_stamp_duty` | 1192–1197 | Positional: `([0.01], trades, FrictionConfig())` | Buy order 7.5 bps friction |
| `TestTier2BoundaryExtremes` | `test_t2_zero_slippage_friction` | 1198–1206 | Positional: `([0.01], trades, FrictionConfig(...))` | Zero slippage round-trip 10.0 bps |
| `TestTier2BoundaryExtremes` | `test_t2_total_drawdown_mdd_clamping` | 1207–1212 | Positional: `(disastrous_returns, [], FrictionConfig())` | Bankruptcy drawdown clamping |
| `TestTier1FeatureCoverage` | `test_f19_four_ablation_configurations_execution` | 996 | Indirect via `AblationEngine.run_simulation` (L661) | Runs Config A, B, C, D simulations |
| `TestTier1FeatureCoverage` | `test_f20_offline_deterministic_execution` | 1004 | Indirect via `AblationEngine.run_simulation` (L661) | Two identical Config D runs match |
| `TestTier3Interactions` | `test_interaction_6_ablation_simulation_full_pipeline` | 1279 | Indirect via `AblationEngine.run_simulation` (L661) | Full ablation pipeline execution |
| `TestTier4RealWorldScenarios` | `test_scenario_1_bull_to_bear_regime_shift` | 1317 | Indirect via `AblationEngine.run_simulation` (L661) | Config D vs A on regime transition |
| `TestTier4RealWorldScenarios` | `test_scenario_2_high_volatility_bull_rally` | 1333 | Indirect via `AblationEngine.run_simulation` (L661) | Config D vs B on bull rally |
| `TestTier4RealWorldScenarios` | `test_scenario_3_low_volatility_sideways_churn` | 1352 | Indirect via `AblationEngine.run_simulation` (L661) | Config D fast-path bypass on sideways |
| `TestTier4RealWorldScenarios` | `test_scenario_4_comprehensive_ablation_ranking` | 1389 | Indirect via `AblationEngine.run_simulation` (L661) | Ranking D > C >= B >= A |

#### C. `tests/test_challenger_m4_1_frictions.py` (29 Direct Tests, 35 Executions)
| Class | Test Method | Line # | Invocation Convention | Description |
|---|---|---|---|---|
| `TestAsymmetricStampDuty` | `test_buy_trades_strictly_zero_stamp_duty` | 38–47 | Keyword: `trades=..., daily_returns=..., friction=...` | Buy trade 7.5 bps |
| `TestAsymmetricStampDuty` | `test_sell_trades_incur_full_stamp_duty` | 48–57 | Keyword: `trades=..., daily_returns=..., friction=...` | Sell trade 12.5 bps |
| `TestAsymmetricStampDuty` | `test_buy_vs_sell_differential_invariant` | 58–72 | Keyword (Parameterized 4x: n=1, 5, 20, 100) | Differential = N * 5 bps invariant |
| `TestAsymmetricStampDuty` | `test_action_case_and_whitespace_insensitivity` | 73–85 | Keyword: `trades=..., daily_returns=...` | Action case & whitespace insensitivity |
| `TestAsymmetricStampDuty` | `test_field_aliases_action_side_type` | 86–100 | Keyword: `trades=..., daily_returns=...` | Field aliases (action, side, type) |
| `TestAsymmetricStampDuty` | `test_signed_shares_asymmetry` | 101–113 | Keyword: `trades=..., daily_returns=...` | Signed int shares (shares, amount, qty) |
| `TestAsymmetricStampDuty` | `test_custom_stamp_duty_parameter` | 114–127 | Keyword: `trades=..., daily_returns=..., friction=...` | Custom stamp duty parameter |
| `TestAsymmetricStampDuty` | `test_fallback_unspecified_trade_defaults_to_roundtrip` | 128–135 | Keyword: `trades=..., daily_returns=...` | Empty trade dict round-trip fallback |
| `TestBoundaryTradeConfigurations` | `test_zero_trades_zero_frictions` | 143–151 | Keyword: `trades=[], daily_returns=...` | Zero trades = 0 bps friction |
| `TestBoundaryTradeConfigurations` | `test_buy_only_trades_linear_scaling` | 152–162 | Keyword (Parameterized 4x: count=1, 10, 50, 100) | Buy-only linear scaling |
| `TestBoundaryTradeConfigurations` | `test_sell_only_trades_linear_scaling` | 163–173 | Keyword (Parameterized 4x: count=1, 10, 50, 100) | Sell-only linear scaling |
| `TestBoundaryTradeConfigurations` | `test_zero_trades_empty_returns_clean_zero_dict` | 174–189 | Keyword: `trades=[], daily_returns=[]` | Clean zero dictionary on empty |
| `TestExtremeFrictionsAndSlippage` | `test_zero_slippage_friction` | 197–205 | Keyword: `trades=..., daily_returns=..., friction=...` | Zero slippage verification |
| `TestExtremeFrictionsAndSlippage` | `test_extreme_slippage_100_bps` | 206–214 | Keyword: `trades=..., daily_returns=..., friction=...` | Extreme 100 bps slippage |
| `TestExtremeFrictionsAndSlippage` | `test_extreme_commission_100_bps` | 215–220 | Keyword: `trades=..., daily_returns=..., friction=...` | Extreme 100 bps commission |
| `TestExtremeFrictionsAndSlippage` | `test_friction_monotonicity_across_slippage_levels` | 221–239 | Keyword: `trades=..., daily_returns=..., friction=...` | Monotonic return drag |
| `TestExtremeFrictionsAndSlippage` | `test_high_frequency_extreme_friction_drag` | 240–255 | Keyword: `trades=..., daily_returns=..., friction=...` | 100 high-frequency trades |
| `TestDegenerateEquityCurves` | `test_constant_flat_zero_returns` | 263–277 | Keyword: `trades=[], daily_returns=...` | Flat 0.0 returns |
| `TestDegenerateEquityCurves` | `test_constant_positive_returns_zero_variance` | 278–289 | Keyword: `trades=[], daily_returns=...` | Zero variance positive returns |
| `TestDegenerateEquityCurves` | `test_constant_negative_returns_zero_variance` | 290–301 | Keyword: `trades=[], daily_returns=...` | Zero variance negative returns |
| `TestDegenerateEquityCurves` | `test_varying_negative_returns_deep_drawdown` | 302–313 | Keyword: `trades=[], daily_returns=...` | Deep drawdown Sortino & Sharpe |
| `TestDegenerateEquityCurves` | `test_flash_crash_single_day_drawdown` | 314–323 | Keyword: `trades=[], daily_returns=...` | Single day -90% crash |
| `TestDegenerateEquityCurves` | `test_total_loss_bankruptcy_handling` | 324–334 | Keyword: `trades=[], daily_returns=...` | Single day -100% loss CAGR clamp |
| `TestDegenerateEquityCurves` | `test_consecutive_total_wipeout_returns` | 335–345 | Keyword: `trades=..., daily_returns=...` | Consecutive total loss days |
| `TestPolymorphicCallingSignatures` | `test_signature_pattern_1_keyword_daily_returns` | 353–362 | Keyword: `trades=..., daily_returns=..., friction=...` | Pattern 1 keyword daily returns |
| `TestPolymorphicCallingSignatures` | `test_signature_pattern_2_keyword_equity_curve` | 363–373 | Keyword: `trades=..., equity_curve=..., friction=...` | Pattern 2 keyword equity curve |
| `TestPolymorphicCallingSignatures` | `test_signature_pattern_3_positional_gross_returns` | 374–384 | Positional: `(gross_returns, trades, friction)` | Pattern 3 positional gross returns |
| `TestPolymorphicCallingSignatures` | `test_default_friction_instantiation` | 385–390 | Keyword: `trades=..., daily_returns=...` | Default friction config |
| `TestPolymorphicCallingSignatures` | `test_risk_free_rate_parameter_sensitivity` | 391–400 | Keyword: `trades=[], daily_returns=..., risk_free_rate=...` | Risk-free rate sensitivity |
| `TestChallengerEmpiricalVulnerabilities` | `test_positional_empty_trades_signature_defect` | 430–451 | Positional: `([], [0.01, 0.02], FrictionConfig())` | **Asserts Defect 1 AttributeError** |
| `TestChallengerEmpiricalVulnerabilities` | `test_positional_equity_curve_misinterpretation_defect` | 452–477 | Positional: `(trades, [100.0, ...], FrictionConfig())` | **Asserts Defect 2 Return Corruption** |
| `TestChallengerEmpiricalVulnerabilities` | `test_non_numeric_shares_type_error_defect` | 478–490 | Keyword: `trades=[{"shares": "100"}], daily_returns=...` | **Asserts Defect 3 TypeError** |

#### D. `tests/test_challenger_m4_2_ablation.py` (2 Direct + 5 Indirect = 7 Tests)
| Class | Test Method | Line # | Invocation Convention | Description |
|---|---|---|---|---|
| `TestChallengerMultiRegimeStress` | `test_empty_trades_net_performance_metrics` | 149–156 | Keyword: `trades=[], daily_returns=..., friction=...` | Empty trades zero friction |
| `TestHostileAdversarialCases` | `test_adversarial_zero_friction_stability` | 551–560 | Positional: `([0.01, -0.005], trades, friction_zero)` | Zero friction gross == net |
| `TestAblationConfigurationInvariants` | `test_config_a_linear_invariants` | 284 | Indirect via `AblationEngine.run_simulation` (L661) | Config A linear invariants |
| `TestAblationConfigurationInvariants` | `test_config_b_vanilla_debate_invariants` | 302 | Indirect via `AblationEngine.run_simulation` (L661) | Config B debate invariants |
| `TestAblationConfigurationInvariants` | `test_config_c_self_debate_invariants` | 324 | Indirect via `AblationEngine.run_simulation` (L661) | Config C self-debate invariants |
| `TestAblationConfigurationInvariants` | `test_ranking_invariants_across_all_configs` | 464 | Indirect via `AblationEngine.run_simulation` (L661) | 4-ablation ranking invariants |
| `TestHostileAdversarialCases` | `test_adversarial_rapid_regime_whipsaw` | 514 | Indirect via `AblationEngine.run_simulation` (L661) | Rapid whipsaw simulation |

---

## 2. Logic Chain

1. **Root Cause Analysis of How the Defects Evaded Baseline Tests**:
   - In `tests/test_result_evaluator_care.py:196–203`, Pattern 2 was tested **only with keyword arguments**: `calculate_net_performance_metrics(trades=trades, equity_curve=equity_curve, friction=FrictionConfig())`. Keyword dispatch explicitly bypasses positional binding, binding `equity_curve` to its named parameter and leaving `daily_returns` as `None`.
   - In `tests/test_result_evaluator_care.py:215`, empty inputs were tested as `calculate_net_performance_metrics([], [], FrictionConfig())`. When `daily_returns` is `[]`, `actual_trades = list(daily_returns)` produces `[]`. The `for t in actual_trades:` loop was empty, preventing the float attribute lookup crash from executing.
   - In `tests/test_result_evaluator_care.py:110–118`, share tests used integer literals (`1000`, `-1000`). No tests exercised string inputs (`"100"`), float strings (`"100.5"`), or `None`.

2. **Root Cause Analysis of Challenger Suite Behavior**:
   - Challenger M4_1 successfully exposed all 3 defects in `tests/test_challenger_m4_1_frictions.py:424–490` by writing tests that assert the *defective* state (`with pytest.raises(AttributeError)`, `assert res_pos["gross_return"] > 100000.0`, `with pytest.raises(TypeError)`).
   - Because these tests assert the existence of the defects, they currently pass (`42 passed`).
   - When the implementation worker fixes the defects, these 3 challenger tests will fail unless updated to assert the fixed behavior.

3. **Regression Prevention Requirements**:
   - The primary regression safety net must reside permanently in `tests/test_result_evaluator_care.py`.
   - The test suite must test both:
     a) Positive contract adherence: Positional Pattern 2 with wealth curves producing identical outputs to keyword Pattern 2.
     b) Defect boundary guards: Positional empty trades with daily returns executing without error, string/None shares coerced gracefully, and Pattern 3 with empty returns executing cleanly.

---

## 3. Caveats

1. **Challenger Test Inversion Risk**:
   - The implementation worker **must update** lines 430–490 of `tests/test_challenger_m4_1_frictions.py` in tandem with fixing `core/backtest/result_evaluator.py`. Failing to update them will cause `pytest tests/test_challenger_m4_1_frictions.py` to fail.
2. **Equity Curve vs. Daily Returns Heuristic in Positional Calling**:
   - When calling positionally as `calculate_net_performance_metrics(trades, arg2, friction)` where `arg2` is a list of floats:
     - If `arg2` contains values $> 1.0$ (or wealth levels $> 1.5$, or starting around 100), it is unambiguously an equity curve.
     - If `arg2` contains values in standard daily return range (e.g. $[-0.20, +0.20]$), it is `daily_returns`.
     - In both cases, if `trades` is a list of dicts (or `[]`) and the 3rd arg is `FrictionConfig`, `actual_trades` MUST be derived from `trades`, NEVER from `arg2` (unless `arg1` contains floats, which is Pattern 3).

---

## 4. Conclusion & Actionable Test Formulations

### Proposed New Regression Test Class for `tests/test_result_evaluator_care.py`
The following new test class `TestM4DefectRegressionGuards` contains **11 comprehensive regression test cases** that should be appended to `tests/test_result_evaluator_care.py`:

```python
class TestM4DefectRegressionGuards:
    """
    Permanent regression test guards preventing Defect 1, Defect 2, and Defect 3.
    Target: core/backtest/result_evaluator.py
    """

    # --------------------------------------------------------------------------
    # Defect 1: Positional Empty Trades with Returns (No AttributeError)
    # --------------------------------------------------------------------------

    def test_regression_defect1_positional_empty_trades_with_returns(self):
        """
        Prevent Defect 1: calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())
        must NOT crash with AttributeError: 'float' object has no attribute 'get'.
        Must compute gross and net returns accurately with 0 trades and 0.0 bps frictions.
        """
        trades = []
        daily_returns = [0.01, 0.02]
        friction = FrictionConfig()

        res = calculate_net_performance_metrics(trades, daily_returns, friction)

        assert res["trade_count"] == 0
        assert res["total_frictions_bps"] == 0.0
        expected_gross = (1.0 + 0.01) * (1.0 + 0.02) - 1.0
        assert res["gross_return"] == pytest.approx(expected_gross, abs=1e-6)
        assert res["net_return"] == pytest.approx(expected_gross, abs=1e-6)
        assert not math.isnan(res["net_sharpe"])
        assert not math.isinf(res["net_sharpe"])

    def test_regression_defect1_positional_empty_trades_default_friction(self):
        """Empty trades with positional returns and default friction fallback."""
        trades = []
        daily_returns = [0.005, -0.002, 0.008]

        res = calculate_net_performance_metrics(trades, daily_returns)
        assert res["trade_count"] == 0
        assert res["total_frictions_bps"] == 0.0
        assert res["gross_return"] == pytest.approx(res["net_return"], abs=1e-6)

    def test_regression_defect1_pattern3_empty_returns_with_trades(self):
        """
        Pattern 3 boundary: calculate_net_performance_metrics([], trades, friction).
        When gross_returns is empty but trades are present:
        trade_count is preserved, frictions are computed, returns remain 0.0.
        """
        gross_returns = []
        trades = [{"action": "buy"}, {"action": "sell"}]
        friction = FrictionConfig()

        res = calculate_net_performance_metrics(gross_returns, trades, friction)
        assert res["trade_count"] == 2
        assert res["total_frictions_bps"] == 20.0
        assert res["gross_return"] == 0.0
        assert res["net_return"] == 0.0

    # --------------------------------------------------------------------------
    # Defect 2: Positional Pattern 2 Wealth Curve Derivation (No Return Corruption)
    # --------------------------------------------------------------------------

    def test_regression_defect2_positional_equity_curve_derivation(self):
        """
        Prevent Defect 2: calculate_net_performance_metrics(trades, equity_curve, friction)
        must treat wealth levels [100.0, 102.0, 105.0] as an equity curve, NOT daily returns!
        Gross return must be +5.0% (~0.05), NOT > 100,000%.
        """
        trades = [{"action": "sell"}]
        equity_curve = [100.0, 102.0, 105.0]
        friction = FrictionConfig()

        res = calculate_net_performance_metrics(trades, equity_curve, friction)

        assert res["trade_count"] == 1
        assert res["total_frictions_bps"] == 12.5  # sell stamp 5 + comm 2.5 + slip 5.0
        assert res["gross_return"] == pytest.approx(0.05, abs=1e-4)
        assert res["gross_return"] < 1.0  # Guard against 1,000,000% overflow
        assert res["net_return"] < res["gross_return"]

    def test_regression_defect2_positional_vs_keyword_equity_curve_parity(self):
        """
        Positional Pattern 2 and Keyword Pattern 2 must return identical metrics.
        """
        trades = [{"action": "buy"}, {"action": "sell"}]
        equity_curve = [100.0, 101.5, 99.5, 103.0]
        friction = FrictionConfig(sell_stamp_duty_bps=5.0, commission_bps=2.5, slippage_bps=5.0)

        res_kw = calculate_net_performance_metrics(
            trades=trades, equity_curve=equity_curve, friction=friction
        )
        res_pos = calculate_net_performance_metrics(trades, equity_curve, friction)

        for key in ["gross_return", "net_return", "net_sharpe", "net_sortino", "net_calmar", "net_max_drawdown", "total_frictions_bps", "trade_count"]:
            assert res_pos[key] == pytest.approx(res_kw[key], abs=1e-6), f"Mismatch in key {key}"

    def test_regression_defect2_positional_equity_curve_zero_trades(self):
        """Positional equity curve with empty trades yields exact wealth ratio return."""
        equity_curve = [1000.0, 1020.0, 1010.0]
        res = calculate_net_performance_metrics([], equity_curve, FrictionConfig())

        assert res["trade_count"] == 0
        assert res["total_frictions_bps"] == 0.0
        expected_ret = (1010.0 / 1000.0) - 1.0
        assert res["gross_return"] == pytest.approx(expected_ret, abs=1e-6)
        assert res["net_return"] == pytest.approx(expected_ret, abs=1e-6)

    def test_regression_defect2_positional_normalized_wealth_curve(self):
        """Positional equity curve starting at 1.0 (e.g. [1.0, 1.02, 1.05])."""
        trades = [{"action": "buy"}]
        equity_curve = [1.0, 1.02, 1.05]
        res = calculate_net_performance_metrics(trades, equity_curve, FrictionConfig())

        assert res["gross_return"] == pytest.approx(0.05, abs=1e-4)
        assert res["trade_count"] == 1
        assert res["total_frictions_bps"] == 7.5

    # --------------------------------------------------------------------------
    # Defect 3: Non-Numeric, String, and None Shares Coercion (No TypeError)
    # --------------------------------------------------------------------------

    def test_regression_defect3_string_numeric_shares_coercion(self):
        """
        Prevent Defect 3: Numeric strings in 'shares' ('100', '-200') must be cleanly coerced.
        Must NOT raise TypeError: '>' not supported between instances of 'str' and 'int'.
        """
        trades = [
            {"shares": "100"},   # buy -> 7.5 bps
            {"shares": "-200"},  # sell -> 12.5 bps
        ]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01, 0.02])
        assert res["trade_count"] == 2
        assert res["total_frictions_bps"] == 20.0

    def test_regression_defect3_string_floats_and_field_aliases(self):
        """String floats across 'amount' and 'qty' aliases coerced cleanly."""
        trades = [
            {"amount": "500.5"},  # buy -> 7.5 bps
            {"qty": "-250.0"},    # sell -> 12.5 bps
        ]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01, 0.02])
        assert res["trade_count"] == 2
        assert res["total_frictions_bps"] == 20.0

    def test_regression_defect3_none_shares_fallback(self):
        """
        Trades with explicit None in 'shares', 'amount', or 'qty' must NOT raise TypeError.
        Must fall back safely to round-trip default (20.0 bps).
        """
        trades = [{"shares": None}, {"amount": None}, {"qty": None}]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01])
        assert res["trade_count"] == 3
        assert res["total_frictions_bps"] == 60.0  # 3 * 20.0 bps

    def test_regression_defect3_malformed_shares_type_resilience(self):
        """Malformed strings or non-numeric types in shares handled gracefully."""
        trades = [
            {"shares": "invalid_str"},
            {"shares": []},
            {"shares": {}},
        ]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01])
        assert res["trade_count"] == 3
        assert res["total_frictions_bps"] == 60.0  # 3 * 20.0 bps fallback
```

---

## 5. Verification Method

To independently verify all findings and test suite behavior:

```bash
# 1. Run baseline result evaluator tests (32 tests currently passing)
.venv/bin/pytest tests/test_result_evaluator_care.py -v

# 2. Run existing challenger friction suite (42 tests currently passing by asserting defective state)
.venv/bin/pytest tests/test_challenger_m4_1_frictions.py -v

# 3. Run full ablation benchmark test suite (52 tests currently passing)
.venv/bin/pytest tests/test_care_agents_ablation.py -v

# 4. Run multi-regime and CBS stress test suite (32 tests currently passing)
.venv/bin/pytest tests/test_challenger_m4_2_ablation.py -v

# 5. Combined verification across all 4 files (158 total test executions across suite)
.venv/bin/pytest tests/test_result_evaluator_care.py tests/test_care_agents_ablation.py tests/test_challenger_m4_1_frictions.py tests/test_challenger_m4_2_ablation.py -v
```

### Invalidation Conditions
- If `calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())` raises `AttributeError`, Defect 1 is unresolved.
- If `calculate_net_performance_metrics([{"action": "sell"}], [100.0, 102.0, 105.0], FrictionConfig())` returns `gross_return > 1.0`, Defect 2 is unresolved.
- If `calculate_net_performance_metrics([{"shares": "100"}], [0.01])` raises `TypeError`, Defect 3 is unresolved.
- If `tests/test_challenger_m4_1_frictions.py` is not updated after fixing `result_evaluator.py`, lines 430–490 will fail due to expecting old exceptions.
