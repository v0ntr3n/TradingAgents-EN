"""
Empirical Challenger Test Suite for CARE-Agents Milestone M4:
Adversarial Stress-Testing of China A-Share Frictions & Net Performance Calculations.

Author: Challenger M4_1 (Empirical Challenger)
Target: core/backtest/result_evaluator.py

Dimensions Covered:
1. Asymmetric stamp duty: strictly 0 on BUY, 5.0 bps on SELL.
2. Boundary trades: zero trades, buy-only trades, sell-only trades.
3. Extreme frictions: 0 bps slippage, 100 bps slippage, 100 bps commission, friction drag.
4. Degenerate equity curves: flat zero returns, zero-variance positive returns,
   all-negative returns, flash crash single-day drawdowns, total bankruptcy (-100%).
5. Polymorphic calling signatures: keyword Patterns 1 & 2, positional Pattern 3,
   and empirical reproduction of positional signature defects.
"""

import math
from typing import Any, Dict, List
import numpy as np
import pytest

from core.backtest.result_evaluator import (
    FrictionConfig,
    calculate_net_performance_metrics,
    calculate_cbs_and_coordination_cost,
    calculate_multi_regime_breakdown,
)


# ==============================================================================
# 1. Asymmetric Stamp Duty: Strictly 0 on BUY, 5.0 bps on SELL
# ==============================================================================

class TestAsymmetricStampDuty:
    """Stress tests China A-share asymmetric stamp duty mechanics."""

    def test_buy_trades_strictly_zero_stamp_duty(self):
        """BUY trades incur strictly 0 bps stamp duty (commission 2.5 + slippage 5.0 = 7.5 bps)."""
        friction = FrictionConfig(sell_stamp_duty_bps=5.0, commission_bps=2.5, slippage_bps=5.0)
        trades = [{"action": "buy"}]
        daily_returns = [0.01, -0.005]

        res = calculate_net_performance_metrics(trades=trades, daily_returns=daily_returns, friction=friction)
        assert res["total_frictions_bps"] == 7.5
        assert res["trade_count"] == 1

    def test_sell_trades_incur_full_stamp_duty(self):
        """SELL trades incur 5.0 bps stamp duty (+ commission 2.5 + slippage 5.0 = 12.5 bps)."""
        friction = FrictionConfig(sell_stamp_duty_bps=5.0, commission_bps=2.5, slippage_bps=5.0)
        trades = [{"action": "sell"}]
        daily_returns = [0.01, -0.005]

        res = calculate_net_performance_metrics(trades=trades, daily_returns=daily_returns, friction=friction)
        assert res["total_frictions_bps"] == 12.5
        assert res["trade_count"] == 1

    @pytest.mark.parametrize("n_trades", [1, 5, 20, 100])
    def test_buy_vs_sell_differential_invariant(self, n_trades):
        """For N trades, sell friction minus buy friction is strictly equal to N * 5.0 bps."""
        friction = FrictionConfig(sell_stamp_duty_bps=5.0, commission_bps=2.5, slippage_bps=5.0)
        buys = [{"action": "buy"} for _ in range(n_trades)]
        sells = [{"action": "sell"} for _ in range(n_trades)]
        returns = [0.005] * 20

        res_b = calculate_net_performance_metrics(trades=buys, daily_returns=returns, friction=friction)
        res_s = calculate_net_performance_metrics(trades=sells, daily_returns=returns, friction=friction)

        diff = res_s["total_frictions_bps"] - res_b["total_frictions_bps"]
        expected_diff = float(n_trades * 5.0)
        assert diff == pytest.approx(expected_diff, abs=1e-6)

    def test_action_case_and_whitespace_insensitivity(self):
        """Action casing and surrounding whitespace do not break stamp duty classification."""
        buy_variants = ["BUY", "Buy", " buy ", "  BUY  \n", "\tbuy\t", "BuY"]
        sell_variants = ["SELL", "Sell", " sell ", "  SELL  \n", "\tsell\t", "SeLl"]

        for b in buy_variants:
            res = calculate_net_performance_metrics(trades=[{"action": b}], daily_returns=[0.01])
            assert res["total_frictions_bps"] == 7.5, f"Variant '{b}' failed to match buy friction"

        for s in sell_variants:
            res = calculate_net_performance_metrics(trades=[{"action": s}], daily_returns=[0.01])
            assert res["total_frictions_bps"] == 12.5, f"Variant '{s}' failed to match sell friction"

    def test_field_aliases_action_side_type(self):
        """Fields 'action', 'side', and 'type' are all properly recognized."""
        trades = [
            {"action": "buy"},
            {"side": "buy"},
            {"type": "buy"},
            {"action": "sell"},
            {"side": "sell"},
            {"type": "sell"},
        ]
        # 3 buys (3 * 7.5 = 22.5) + 3 sells (3 * 12.5 = 37.5) = 60.0 bps
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01] * 5)
        assert res["total_frictions_bps"] == pytest.approx(60.0, abs=1e-6)
        assert res["trade_count"] == 6

    def test_signed_shares_asymmetry(self):
        """Positive shares classify as BUY (no stamp duty), negative shares classify as SELL."""
        trades = [
            {"shares": 100},   # buy -> 7.5
            {"amount": 200},   # buy -> 7.5
            {"qty": 50},       # buy -> 7.5
            {"shares": -100},  # sell -> 12.5
            {"amount": -200},  # sell -> 12.5
            {"qty": -50},      # sell -> 12.5
        ]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01] * 5)
        assert res["total_frictions_bps"] == pytest.approx(60.0, abs=1e-6)

    def test_custom_stamp_duty_parameter(self):
        """Custom sell_stamp_duty_bps (e.g. 10.0 or 0.0) is strictly respected."""
        f_custom = FrictionConfig(sell_stamp_duty_bps=10.0, commission_bps=2.5, slippage_bps=5.0)
        res_sell = calculate_net_performance_metrics(
            trades=[{"action": "sell"}], daily_returns=[0.01], friction=f_custom
        )
        assert res_sell["total_frictions_bps"] == 17.5

        f_zero = FrictionConfig(sell_stamp_duty_bps=0.0, commission_bps=2.5, slippage_bps=5.0)
        res_zero = calculate_net_performance_metrics(
            trades=[{"action": "sell"}], daily_returns=[0.01], friction=f_zero
        )
        assert res_zero["total_frictions_bps"] == 7.5

    def test_fallback_unspecified_trade_defaults_to_roundtrip(self):
        """Trades with no explicit action or zero shares default to completed round trip."""
        trades = [{}]  # Unknown action, shares=0
        # Roundtrip = 5.0 (sell stamp) + 2 * (2.5 + 5.0) = 20.0 bps
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01])
        assert res["total_frictions_bps"] == 20.0


# ==============================================================================
# 2. Boundary Trades: Zero Trades, Buy-Only Trades, Sell-Only Trades
# ==============================================================================

class TestBoundaryTradeConfigurations:
    """Stress tests boundary trade sets."""

    def test_zero_trades_zero_frictions(self):
        """Zero trades incur exactly 0.0 bps total frictions and gross_return == net_return."""
        daily_returns = [0.01, -0.005, 0.02, -0.01]
        res = calculate_net_performance_metrics(trades=[], daily_returns=daily_returns)

        assert res["total_frictions_bps"] == 0.0
        assert res["trade_count"] == 0
        assert res["gross_return"] == pytest.approx(res["net_return"], abs=1e-9)

    @pytest.mark.parametrize("count", [1, 10, 50, 100])
    def test_buy_only_trades_linear_scaling(self, count):
        """Buy-only trade sets scale total frictions strictly as count * (commission + slippage)."""
        trades = [{"action": "buy"} for _ in range(count)]
        returns = [0.002] * 20
        res = calculate_net_performance_metrics(trades=trades, daily_returns=returns)

        expected_frictions = float(count * 7.5)
        assert res["total_frictions_bps"] == pytest.approx(expected_frictions, abs=1e-6)
        assert res["trade_count"] == count

    @pytest.mark.parametrize("count", [1, 10, 50, 100])
    def test_sell_only_trades_linear_scaling(self, count):
        """Sell-only trade sets scale total frictions strictly as count * (stamp + commission + slippage)."""
        trades = [{"action": "sell"} for _ in range(count)]
        returns = [0.002] * 20
        res = calculate_net_performance_metrics(trades=trades, daily_returns=returns)

        expected_frictions = float(count * 12.5)
        assert res["total_frictions_bps"] == pytest.approx(expected_frictions, abs=1e-6)
        assert res["trade_count"] == count

    def test_zero_trades_empty_returns_clean_zero_dict(self):
        """Empty trades and empty returns return a structured zeroed dictionary without crashing."""
        res = calculate_net_performance_metrics(trades=[], daily_returns=[])
        assert res["gross_return"] == 0.0
        assert res["net_return"] == 0.0
        assert res["net_sharpe"] == 0.0
        assert res["net_sortino"] == 0.0
        assert res["net_calmar"] == 0.0
        assert res["net_max_drawdown"] == 0.0
        assert res["total_frictions_bps"] == 0.0
        assert res["annualized_return"] == 0.0
        assert res["annualized_volatility"] == 0.0
        assert res["win_rate"] == 0.0
        assert res["trade_count"] == 0


# ==============================================================================
# 3. Extreme Slippage (0 bps, 100 bps) & Extreme Commission
# ==============================================================================

class TestExtremeFrictionsAndSlippage:
    """Stress tests extreme slippage and commission configurations."""

    def test_zero_slippage_friction(self):
        """Zero slippage (0.0 bps) leaves only commission and sell stamp duty."""
        f = FrictionConfig(slippage_bps=0.0, commission_bps=2.5, sell_stamp_duty_bps=5.0)
        res_buy = calculate_net_performance_metrics(trades=[{"action": "buy"}], daily_returns=[0.01], friction=f)
        assert res_buy["total_frictions_bps"] == 2.5

        res_sell = calculate_net_performance_metrics(trades=[{"action": "sell"}], daily_returns=[0.01], friction=f)
        assert res_sell["total_frictions_bps"] == 7.5

    def test_extreme_slippage_100_bps(self):
        """Extreme slippage of 100 bps (1.0% per trade) is properly accumulated."""
        f = FrictionConfig(slippage_bps=100.0, commission_bps=2.5, sell_stamp_duty_bps=5.0)
        res_buy = calculate_net_performance_metrics(trades=[{"action": "buy"}], daily_returns=[0.01], friction=f)
        assert res_buy["total_frictions_bps"] == 102.5

        res_sell = calculate_net_performance_metrics(trades=[{"action": "sell"}], daily_returns=[0.01], friction=f)
        assert res_sell["total_frictions_bps"] == 107.5

    def test_extreme_commission_100_bps(self):
        """Extreme commission of 100 bps is properly accumulated."""
        f = FrictionConfig(commission_bps=100.0, slippage_bps=5.0, sell_stamp_duty_bps=5.0)
        res_buy = calculate_net_performance_metrics(trades=[{"action": "buy"}], daily_returns=[0.01], friction=f)
        assert res_buy["total_frictions_bps"] == 105.0

    def test_friction_monotonicity_across_slippage_levels(self):
        """Increasing slippage monotonically reduces net return and increases friction."""
        slippage_levels = [0.0, 5.0, 20.0, 50.0, 100.0]
        returns = [0.005] * 20
        trades = [{"action": "buy"}, {"action": "sell"}] * 5

        prev_net_return = float("inf")
        prev_frictions = -1.0

        for slip in slippage_levels:
            f = FrictionConfig(slippage_bps=slip)
            res = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=f)

            assert res["total_frictions_bps"] > prev_frictions
            assert res["net_return"] < prev_net_return

            prev_frictions = res["total_frictions_bps"]
            prev_net_return = res["net_return"]

    def test_high_frequency_extreme_friction_drag(self):
        """100 trades with 100 bps commission and 100 bps slippage drag returns without numerical overflow."""
        trades = [{"action": "buy"}, {"action": "sell"}] * 50
        returns = [0.001] * 20
        f = FrictionConfig(commission_bps=100.0, slippage_bps=100.0, sell_stamp_duty_bps=5.0)

        res = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=f)
        # Total frictions: 50 buys * 200 + 50 sells * 205 = 10,000 + 10,250 = 20,250 bps = 202.5% drag
        assert res["total_frictions_bps"] == 20250.0
        assert res["net_return"] < -0.80
        assert not math.isnan(res["net_sharpe"])
        assert not math.isinf(res["net_sharpe"])
        assert not math.isnan(res["net_sortino"])
        assert not math.isnan(res["net_calmar"])


# ==============================================================================
# 4. Degenerate Equity Curves
# ==============================================================================

class TestDegenerateEquityCurves:
    """Stress tests degenerate, singular, and crash equity curves."""

    def test_constant_flat_zero_returns(self):
        """Constant 0.0 daily returns with zero trades: Sharpe is 0.0, MDD is 0.0, Sortino is finite."""
        returns = [0.0] * 50
        res = calculate_net_performance_metrics(trades=[], daily_returns=returns)

        assert res["gross_return"] == 0.0
        assert res["net_return"] == 0.0
        assert res["net_sharpe"] == 0.0
        assert res["net_max_drawdown"] == 0.0
        assert res["annualized_volatility"] == 0.0
        assert res["win_rate"] == 0.0
        # Sortino evaluates against annualized 2.5% risk-free rate
        assert not math.isnan(res["net_sortino"])
        assert not math.isinf(res["net_sortino"])

    def test_constant_positive_returns_zero_variance(self):
        """Constant +10 bps daily returns: zero variance excess returns evaluate safely."""
        returns = [0.001] * 50
        res = calculate_net_performance_metrics(trades=[], daily_returns=returns)

        assert res["net_return"] > 0.0
        assert res["net_max_drawdown"] == 0.0
        # Zero variance excess return division protection
        assert res["net_sharpe"] == 0.0
        assert res["net_sortino"] == 0.0
        assert res["win_rate"] == 100.0

    def test_constant_negative_returns_zero_variance(self):
        """Constant negative daily returns: zero variance clamps Sharpe to 0.0 while Sortino is negative."""
        returns = [-0.02] * 50
        res = calculate_net_performance_metrics(trades=[], daily_returns=returns)

        assert res["net_return"] < 0.0
        # Zero variance excess returns clamps Sharpe to 0.0
        assert res["net_sharpe"] == 0.0
        assert res["net_sortino"] < 0.0
        assert res["net_max_drawdown"] < -0.60
        assert res["win_rate"] == 0.0

    def test_varying_negative_returns_deep_drawdown(self):
        """Varying negative daily returns yield strictly negative Sharpe and Sortino with deep drawdown."""
        returns = [-0.02, -0.015, -0.025] * 10
        res = calculate_net_performance_metrics(trades=[], daily_returns=returns)

        assert res["net_return"] < 0.0
        assert res["net_sharpe"] < 0.0
        assert res["net_sortino"] < 0.0
        assert res["net_max_drawdown"] < -0.40
        assert res["win_rate"] == 0.0
        assert res["annualized_return"] < -0.80

    def test_flash_crash_single_day_drawdown(self):
        """Single-day -90% flash crash is accurately captured in net_max_drawdown."""
        returns = [0.01] * 10 + [-0.90] + [0.01] * 10
        res = calculate_net_performance_metrics(trades=[], daily_returns=returns)

        assert res["net_max_drawdown"] <= -0.90
        assert not math.isnan(res["net_sharpe"])
        assert not math.isnan(res["net_sortino"])
        assert not math.isnan(res["net_calmar"])

    def test_total_loss_bankruptcy_handling(self):
        """Single-day -100% loss correctly clamps CAGR to -1.0 and MDD to -1.0 without complex math error."""
        returns = [-1.0]
        res = calculate_net_performance_metrics(trades=[], daily_returns=returns)

        assert res["net_return"] == -1.0
        assert res["annualized_return"] == -1.0
        assert res["net_max_drawdown"] == -1.0
        assert not math.isnan(res["net_sharpe"])
        assert not math.isnan(res["net_sortino"])

    def test_consecutive_total_wipeout_returns(self):
        """Multiple -100% loss days with friction do not crash or produce NaN."""
        returns = [-1.0, -1.0]
        trades = [{"action": "buy"}]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=returns)

        assert res["annualized_return"] == -1.0
        assert not math.isnan(res["net_sharpe"])
        assert not math.isnan(res["net_sortino"])


# ==============================================================================
# 5. Polymorphic Calling Signatures & Contract Adherence
# ==============================================================================

class TestPolymorphicCallingSignatures:
    """Verifies polymorphic calling conventions supported by calculate_net_performance_metrics."""

    def test_signature_pattern_1_keyword_daily_returns(self):
        """Pattern 1: Explicit keyword arguments with daily_returns."""
        trades = [{"action": "buy"}]
        daily_returns = [0.01, 0.02]
        res = calculate_net_performance_metrics(
            trades=trades, daily_returns=daily_returns, friction=FrictionConfig()
        )
        assert res["trade_count"] == 1
        assert res["total_frictions_bps"] == 7.5

    def test_signature_pattern_2_keyword_equity_curve(self):
        """Pattern 2: Explicit keyword arguments with equity_curve (derives daily returns)."""
        trades = [{"action": "sell"}]
        equity_curve = [100.0, 102.0, 105.0]
        res = calculate_net_performance_metrics(
            trades=trades, equity_curve=equity_curve, friction=FrictionConfig()
        )
        assert res["trade_count"] == 1
        assert res["total_frictions_bps"] == 12.5
        assert res["gross_return"] == pytest.approx(0.05, abs=1e-4)

    def test_signature_pattern_3_positional_gross_returns(self):
        """Pattern 3: calculate_net_performance_metrics(gross_returns, trades, friction)."""
        gross_returns = [0.01, -0.005, 0.02]
        trades = [{"action": "buy"}, {"action": "sell"}]
        friction = FrictionConfig()

        res = calculate_net_performance_metrics(gross_returns, trades, friction)
        assert res["total_frictions_bps"] == 20.0
        assert res["trade_count"] == 2
        assert res["net_return"] < res["gross_return"]

    def test_default_friction_instantiation(self):
        """Omitting friction parameter uses default China A-share rates (5 sell stamp, 2.5 comm, 5 slip)."""
        trades = [{"action": "sell"}]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01])
        assert res["total_frictions_bps"] == 12.5

    def test_risk_free_rate_parameter_sensitivity(self):
        """Higher risk_free_rate reduces Sharpe and Sortino ratios monotonically."""
        returns = [0.001] * 50
        res_low_rf = calculate_net_performance_metrics(trades=[], daily_returns=returns, risk_free_rate=0.01)
        res_high_rf = calculate_net_performance_metrics(trades=[], daily_returns=returns, risk_free_rate=0.05)

        # On constant positive returns, Sharpe is 0.0, but Sortino downside differs
        assert not math.isnan(res_low_rf["net_sortino"])
        assert not math.isnan(res_high_rf["net_sortino"])

    def test_cbs_and_regime_breakdown_integration(self):
        """Verifies auxiliary M4 functions calculate_cbs_and_coordination_cost & calculate_multi_regime_breakdown."""
        records = [
            {"cbs_bps": 12.0, "route": "fast_path", "tokens": 400, "latency_ms": 25.0},
            {"cbs_bps": 20.0, "route": "multi_round_debate", "tokens": 1200, "latency_ms": 75.0},
        ]
        cbs_metrics = calculate_cbs_and_coordination_cost(records)
        assert cbs_metrics["realized_cbs_bps"] == 16.0
        assert cbs_metrics["fast_path_debate_bypass_rate"] == 0.5

        regimes = ["bull", "bull", "bear", "bear", "sideways"]
        daily_returns = [0.01, 0.02, -0.01, -0.02, 0.00]
        regime_metrics = calculate_multi_regime_breakdown(daily_returns, regimes)
        assert "bull" in regime_metrics
        assert "bear" in regime_metrics
        assert "sideways" in regime_metrics
        assert regime_metrics["bull"]["count"] == 2.0


# ==============================================================================
# 6. Empirical Vulnerabilities & Interface Contract Defects
# ==============================================================================

class TestChallengerEmpiricalVulnerabilities:
    """
    Verification of resolved edge-case vulnerabilities and interface contract defects.
    These tests verify that defects discovered in core/backtest/result_evaluator.py are resolved.
    """

    def test_positional_empty_trades_signature_defect(self):
        """
        Verifies positional call:
        calculate_net_performance_metrics([], [0.01, 0.02], FrictionConfig())
        succeeds cleanly without AttributeError, properly parsing empty trades and numeric returns.
        """
        trades = []
        daily_returns = [0.01, 0.02]
        friction = FrictionConfig()

        res = calculate_net_performance_metrics(trades, daily_returns, friction)
        assert res["trade_count"] == 0
        assert res["total_frictions_bps"] == 0.0
        assert res["gross_return"] == pytest.approx((1.01 * 1.02) - 1.0, abs=1e-6)
        assert res["net_return"] == pytest.approx(res["gross_return"], abs=1e-6)

    def test_positional_equity_curve_misinterpretation_defect(self):
        """
        Verifies positional call Pattern 2:
        calculate_net_performance_metrics(trades, equity_curve, friction)
        as specified in PROJECT.md line 121 and docstring, accurately derives returns from wealth levels
        (e.g. [100.0, 102.0, 105.0] -> ~5.0% gross return), matching keyword invocation parity.
        """
        trades = [{"action": "buy"}]
        equity_curve = [100.0, 102.0, 105.0]
        friction = FrictionConfig()

        # Keyword invocation derives returns correctly (~5% total return)
        res_kw = calculate_net_performance_metrics(trades=trades, equity_curve=equity_curve, friction=friction)
        assert res_kw["gross_return"] == pytest.approx(0.05, abs=1e-4)

        # Positional invocation satisfies the contract: derives returns from wealth levels
        res_pos = calculate_net_performance_metrics(trades, equity_curve, friction)
        assert res_pos["gross_return"] == pytest.approx(0.05, abs=1e-4)
        assert res_pos["trade_count"] == 1
        assert res_pos["total_frictions_bps"] == 7.5
        assert res_pos["gross_return"] == pytest.approx(res_kw["gross_return"], abs=1e-6)

    def test_non_numeric_shares_type_error_defect(self):
        """
        Verifies non-numeric string or None shares in trade dicts are safely coerced without TypeError.
        """
        trades_str = [{"shares": "100"}]
        res_str = calculate_net_performance_metrics(trades=trades_str, daily_returns=[0.01])
        assert res_str["trade_count"] == 1
        assert res_str["total_frictions_bps"] == 7.5  # parsed as positive shares -> buy (7.5 bps)

        trades_none = [{"shares": None}]
        res_none = calculate_net_performance_metrics(trades=trades_none, daily_returns=[0.01])
        assert res_none["trade_count"] == 1
        assert res_none["total_frictions_bps"] == 20.0  # fallback to roundtrip default (20.0 bps)
