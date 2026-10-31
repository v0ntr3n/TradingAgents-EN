"""
Unit and Integration Tests for CARE-Agents Result Evaluator Metrics
Reference: ORIGINAL_REQUEST.md (R4), PROJECT.md, survey_r4_arch.md
Target: core/backtest/result_evaluator.py
"""

import math
from typing import Any, Dict, List
import numpy as np
import pytest

from core.backtest.result_evaluator import (
    FrictionConfig,
    calculate_cbs_and_coordination_cost,
    calculate_multi_regime_breakdown,
    calculate_net_performance_metrics,
    _build_evaluation_context,
    should_optimize_strategy,
)


class TestFrictionConfig:
    """Verifies FrictionConfig defaults, customization, and backward compatibility."""

    def test_default_china_a_share_frictions(self):
        """Default values strictly follow China A-share trading rules."""
        cfg = FrictionConfig()
        assert cfg.sell_stamp_duty_bps == 5.0   # 5 bps on SELL only (0.05%)
        assert cfg.commission_bps == 2.5        # 2.5 bps on BUY and SELL (0.025%)
        assert cfg.slippage_bps == 5.0          # 5 bps configurable slippage

    def test_stamp_duty_property_alias(self):
        """stamp_duty_bps property alias maps to sell_stamp_duty_bps."""
        cfg = FrictionConfig(sell_stamp_duty_bps=8.0)
        assert cfg.stamp_duty_bps == 8.0

    def test_custom_parameters_initialization(self):
        """Custom friction parameters are correctly initialized."""
        cfg = FrictionConfig(sell_stamp_duty_bps=10.0, commission_bps=1.5, slippage_bps=2.0)
        assert cfg.sell_stamp_duty_bps == 10.0
        assert cfg.commission_bps == 1.5
        assert cfg.slippage_bps == 2.0

    def test_backward_compatible_stamp_duty_kwarg(self):
        """Initialization using legacy stamp_duty_bps keyword argument."""
        cfg = FrictionConfig(stamp_duty_bps=6.0, commission_bps=3.0)
        assert cfg.sell_stamp_duty_bps == 6.0
        assert cfg.commission_bps == 3.0


class TestNetPerformanceMetricsFrictions:
    """Verifies that China A-share frictions (stamp duty, commission, slippage) are calculated accurately."""

    def test_buy_trade_incurs_no_stamp_duty(self):
        """
        Crucial A-share rule: BUY orders must NOT incur stamp duty.
        Buy friction = commission (2.5 bps) + slippage (5.0 bps) = 7.5 bps.
        """
        trades = [{"action": "buy", "price": 10.0}]
        returns = [0.01]
        metrics = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=FrictionConfig())
        assert metrics["total_frictions_bps"] == 7.5
        assert metrics["net_return"] < metrics["gross_return"]

    def test_sell_trade_incurs_stamp_duty(self):
        """
        SELL orders incur stamp duty (5.0 bps) + commission (2.5 bps) + slippage (5.0 bps) = 12.5 bps.
        """
        trades = [{"action": "sell", "price": 12.0}]
        returns = [0.01]
        metrics = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=FrictionConfig())
        assert metrics["total_frictions_bps"] == 12.5

    def test_round_trip_friction(self):
        """
        Round-trip trade (1 Buy + 1 Sell):
        Total friction = 7.5 bps (Buy) + 12.5 bps (Sell) = 20.0 bps.
        """
        trades = [
            {"action": "buy", "price": 10.0},
            {"action": "sell", "price": 11.0},
        ]
        returns = [0.01, 0.02]
        metrics = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=FrictionConfig())
        assert metrics["total_frictions_bps"] == 20.0

    def test_zero_slippage_configuration(self):
        """Zero slippage: Buy=2.5 bps, Sell=7.5 bps -> Round-trip=10.0 bps."""
        trades = [
            {"action": "buy", "price": 10.0},
            {"action": "sell", "price": 11.0},
        ]
        metrics = calculate_net_performance_metrics(
            trades=trades, daily_returns=[0.01], friction=FrictionConfig(slippage_bps=0.0)
        )
        assert metrics["total_frictions_bps"] == 10.0

    def test_multiple_trades_linear_accumulation(self):
        """3 Buys + 2 Sells: 3 * 7.5 + 2 * 12.5 = 22.5 + 25.0 = 47.5 bps."""
        trades = [
            {"action": "buy"},
            {"action": "buy"},
            {"action": "buy"},
            {"action": "sell"},
            {"action": "sell"},
        ]
        metrics = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01] * 5, friction=FrictionConfig())
        assert metrics["total_frictions_bps"] == 47.5

    def test_signed_shares_or_roundtrip_fallback(self):
        """Positive shares treated as Buy, negative shares treated as Sell."""
        trades = [
            {"shares": 1000},   # buy -> 7.5 bps
            {"shares": -1000},  # sell -> 12.5 bps
        ]
        metrics = calculate_net_performance_metrics(trades=trades, daily_returns=[0.01, 0.02])
        assert metrics["total_frictions_bps"] == 20.0


class TestNetPerformanceMetricsRiskRatios:
    """Verifies Sharpe, Sortino, Calmar, and Maximum Drawdown quantitative formulas."""

    def test_annualized_net_sharpe_with_risk_free_rate(self):
        """Sharpe ratio is annualized by sqrt(252) with excess return over daily Rf."""
        daily_returns = [0.002, 0.001, 0.003, -0.001, 0.002] * 10  # 50 days
        trades = [{"action": "buy"}, {"action": "sell"}]
        metrics = calculate_net_performance_metrics(
            trades=trades, daily_returns=daily_returns, risk_free_rate=0.025
        )
        assert "net_sharpe" in metrics
        assert metrics["net_sharpe"] > 0.0
        assert not math.isnan(metrics["net_sharpe"])
        assert not math.isinf(metrics["net_sharpe"])

    def test_zero_variance_sharpe_protection(self):
        """Constant returns produce 0 variance -> Net Sharpe should safely return 0.0."""
        daily_returns = [0.001] * 20
        metrics = calculate_net_performance_metrics(daily_returns=daily_returns, trades=[])
        assert metrics["net_sharpe"] == 0.0
        assert not math.isnan(metrics["net_sharpe"])

    def test_annualized_net_sortino_ratio(self):
        """Sortino ratio only penalizes downside deviations below risk-free rate."""
        # Strong upside returns with few small dips
        daily_returns = [0.01, 0.015, -0.002, 0.02, 0.008, -0.001, 0.012] * 5
        metrics = calculate_net_performance_metrics(trades=[], daily_returns=daily_returns)
        assert metrics["net_sortino"] > 0.0
        # Sortino should be higher than Sharpe because upside volatility is not penalized
        assert metrics["net_sortino"] >= metrics["net_sharpe"]

    def test_maximum_drawdown_peak_to_trough(self):
        """Maximum Drawdown accurately tracks the deepest trough from peak equity (W_0 = 1.0)."""
        # Day 1: +10% (1.10), Day 2: -20% (0.88), Day 3: +10% (0.968)
        # Peak = 1.10, Trough = 0.88 -> Drawdown = (0.88 - 1.10) / 1.10 = -0.20 (-20%)
        returns = [0.10, -0.20, 0.10]
        # friction = 0 to verify pure math
        friction = FrictionConfig(sell_stamp_duty_bps=0.0, commission_bps=0.0, slippage_bps=0.0)
        metrics = calculate_net_performance_metrics(trades=[], daily_returns=returns, friction=friction)
        assert abs(metrics["net_max_drawdown"] - (-0.20)) < 1e-4

    def test_monotonic_positive_returns_zero_mdd(self):
        """Monotonically rising equity has maximum drawdown of 0.0."""
        returns = [0.01, 0.02, 0.015, 0.005]
        friction = FrictionConfig(sell_stamp_duty_bps=0.0, commission_bps=0.0, slippage_bps=0.0)
        metrics = calculate_net_performance_metrics(trades=[], daily_returns=returns, friction=friction)
        assert metrics["net_max_drawdown"] == 0.0

    def test_net_calmar_ratio(self):
        """Calmar ratio equals annualized CAGR divided by absolute Maximum Drawdown."""
        returns = [0.005, -0.002, 0.008, -0.004, 0.006] * 20  # 100 days
        metrics = calculate_net_performance_metrics(trades=[], daily_returns=returns)
        assert "net_calmar" in metrics
        if abs(metrics["net_max_drawdown"]) > 1e-6:
            expected_calmar = metrics["annualized_return"] / abs(metrics["net_max_drawdown"])
            assert abs(metrics["net_calmar"] - expected_calmar) < 1e-4

    def test_disastrous_returns_total_loss_handling(self):
        """Catastrophic loss does not raise ValueError or imaginary numbers."""
        returns = [-0.60, -0.60, -0.60]
        metrics = calculate_net_performance_metrics(trades=[], daily_returns=returns)
        assert metrics["net_max_drawdown"] < -0.80
        assert not math.isnan(metrics["net_calmar"])


class TestNetPerformanceMetricsSignatures:
    """Verifies polymorphic calling signatures and edge-case handling."""

    def test_signature_pattern_1_explicit_kwargs(self):
        """Pattern 1: trades, daily_returns=..., equity_curve=..., friction=..."""
        trades = [{"action": "buy"}]
        daily_returns = [0.01, 0.02]
        res = calculate_net_performance_metrics(trades=trades, daily_returns=daily_returns, friction=FrictionConfig())
        assert res["trade_count"] == 1
        assert len(daily_returns) == 2

    def test_signature_pattern_2_equity_curve_derivation(self):
        """Pattern 2: trades, equity_curve, friction (daily returns derived from wealth levels)."""
        trades = [{"action": "sell"}]
        equity_curve = [100.0, 102.0, 105.06, 103.0]
        res = calculate_net_performance_metrics(trades=trades, equity_curve=equity_curve, friction=FrictionConfig())
        assert res["trade_count"] == 1
        assert res["gross_return"] > 0.0

    def test_signature_pattern_3_positional_gross_returns(self):
        """Pattern 3: calculate_net_performance_metrics(gross_returns, trades, friction)."""
        gross_returns = [0.01, -0.005, 0.02]
        trades = [{"action": "buy"}, {"action": "sell"}]
        friction = FrictionConfig()
        res = calculate_net_performance_metrics(gross_returns, trades, friction)
        assert res["total_frictions_bps"] == 20.0
        assert res["net_return"] < res["gross_return"]

    def test_empty_returns_and_trades(self):
        """Empty inputs gracefully return dictionary of zeros without exceptions."""
        res = calculate_net_performance_metrics([], [], FrictionConfig())
        assert res["gross_return"] == 0.0
        assert res["net_return"] == 0.0
        assert res["net_sharpe"] == 0.0
        assert res["net_sortino"] == 0.0
        assert res["net_calmar"] == 0.0
        assert res["net_max_drawdown"] == 0.0
        assert res["total_frictions_bps"] == 0.0
        assert res["trade_count"] == 0


class TestRealizedCBSAndCoordinationCost:
    """Verifies calculate_cbs_and_coordination_cost."""

    def test_cbs_and_token_cost_calculation(self):
        """Averages realized CBS hurdle, tokens, and latency across decision records."""
        records = [
            {"cbs_bps": 12.0, "route": "fast_path", "tokens": 400, "latency_sec": 0.02},
            {"cbs_bps": 20.0, "route": "multi_round_debate", "tokens": 1000, "latency_sec": 0.08},
            {"cbs_bps": 16.0, "route": "fast_path", "tokens": 400, "latency_sec": 0.02},
            {"cbs_bps": 24.0, "route": "multi_round_debate", "tokens": 1200, "latency_sec": 0.08},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert res["realized_cbs_bps"] == 18.0   # (12+20+16+24)/4
        assert res["token_cost_per_decision"] == 750.0 # (400+1000+400+1200)/4
        assert res["latency_ms_per_decision"] == 50.0  # (20+80+20+80)/4 ms
        assert res["latency_sec_per_decision"] == 0.05
        assert res["fast_path_debate_bypass_rate"] == 0.5 # 2 of 4
        assert res["debate_trigger_rate"] == 0.5
        assert res["total_decisions"] == 4.0

    def test_latency_ms_and_token_fields_variants(self):
        """Supports various field names: latency_ms, tokens_consumed, prompt_tokens+completion_tokens."""
        records = [
            {"cbs_bps": 15.0, "fast_path": True, "tokens_consumed": 500, "latency_ms": 30.0},
            {"cbs_bps": 25.0, "debate_triggered": True, "prompt_tokens": 600, "completion_tokens": 200, "latency": 70.0},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert res["realized_cbs_bps"] == 20.0
        assert res["token_cost_per_decision"] == 650.0  # (500 + 800) / 2
        assert res["latency_ms_per_decision"] == 50.0   # (30 + 70) / 2
        assert res["fast_path_debate_bypass_rate"] == 0.5

    def test_empty_debate_records(self):
        """Empty records return zeroed metrics without crashing."""
        res = calculate_cbs_and_coordination_cost([])
        assert res["realized_cbs_bps"] == 0.0
        assert res["token_cost_per_decision"] == 0.0
        assert res["latency_ms_per_decision"] == 0.0
        assert res["fast_path_debate_bypass_rate"] == 0.0
        assert res["total_decisions"] == 0.0


class TestMultiRegimeBreakdown:
    """Verifies calculate_multi_regime_breakdown across Bull, Bear, and Sideways periods."""

    def test_multi_regime_slicing_and_metrics(self):
        """Returns segmented metrics across Bull, Bear, and Sideways."""
        daily_returns = [
            0.02, 0.015, 0.01, 0.025,      # Bull
            -0.03, -0.02, -0.025, -0.015,  # Bear
            0.001, -0.002, 0.002, -0.001,  # Sideways
        ]
        regimes = [
            "bull", "bull", "bull", "bull",
            "bear", "bear", "bear", "bear",
            "sideways", "sideways", "sideways", "sideways",
        ]

        breakdown = calculate_multi_regime_breakdown(daily_returns, regimes, friction_per_period=0.0)
        assert "bull" in breakdown
        assert "bear" in breakdown
        assert "sideways" in breakdown

        # Bull metrics
        assert breakdown["bull"]["count"] == 4.0
        assert breakdown["bull"]["net_return"] > 0.0
        assert breakdown["bull"]["sharpe"] > 0.0

        # Bear metrics
        assert breakdown["bear"]["count"] == 4.0
        assert breakdown["bear"]["net_return"] < 0.0
        assert breakdown["bear"]["max_drawdown"] < 0.0

        # Sideways metrics
        assert breakdown["sideways"]["count"] == 4.0
        assert abs(breakdown["sideways"]["net_return"]) < 0.01

    def test_case_insensitivity_and_whitespace(self):
        """Regime labels are normalized regardless of case or whitespace."""
        daily_returns = [0.01, -0.01]
        regimes = [" BULL ", "Bear\n"]
        breakdown = calculate_multi_regime_breakdown(daily_returns, regimes)
        assert "bull" in breakdown
        assert "bear" in breakdown
        assert "sideways" not in breakdown  # omitted if not present

    def test_empty_returns_or_regimes(self):
        """Empty input returns empty dictionary."""
        breakdown = calculate_multi_regime_breakdown([], [])
        assert breakdown == {}


class TestEvaluationContextIntegration:
    """Verifies integration of net-of-cost metrics and regime summaries in _build_evaluation_context."""

    def test_context_includes_care_agents_net_metrics_when_provided(self):
        """When summary has net performance metrics, the CARE-Agents net analysis section is rendered."""
        backtest_result = {
            "summary": {
                "total_return": 18.5,
                "win_rate": 62.0,
                "max_drawdown_pct": 8.5,
                "trade_count": 24,
                "final_value": 1185000,
                "net_return": 0.165,
                "net_sharpe": 1.82,
                "net_sortino": 2.45,
                "net_calmar": 1.94,
                "net_max_drawdown": -0.085,
                "total_frictions_bps": 240.0,
                "realized_cbs_bps": 16.5,
                "token_cost_per_decision": 650.0,
                "fast_path_bypass_rate": 0.70,
            }
        }
        context = _build_evaluation_context(
            user_description="Test Strategy",
            strategy={"code": "class Strategy: pass", "config": {}},
            backtest_result=backtest_result,
        )
        assert "[Net Performance & Cost Analysis (CARE-Agents)]" in context
        assert "Net Return: 16.50%" in context
        assert "Net Sharpe: 1.82" in context
        assert "Net Sortino: 2.45" in context
        assert "Net Calmar: 1.94" in context
        assert "Net Max Drawdown: -8.50%" in context
        assert "Total Frictions: 240.0 bps" in context
        assert "Realized CBS: 16.5 bps" in context
        assert "Fast-Path Bypass Rate: 70.0%" in context

    def test_context_includes_multi_regime_breakdown_when_provided(self):
        """When regime breakdown is present, it is formatted into the evaluation context."""
        backtest_result = {
            "summary": {
                "total_return": 10.0,
                "regime_breakdown": {
                    "bull": {"net_return": 0.15, "net_sharpe": 2.1, "net_max_drawdown": -0.03},
                    "bear": {"net_return": -0.05, "net_sharpe": -0.8, "net_max_drawdown": -0.12},
                    "sideways": {"net_return": 0.02, "net_sharpe": 0.5, "net_max_drawdown": -0.02},
                }
            }
        }
        context = _build_evaluation_context(
            user_description="Test Regime Strategy",
            strategy={"code": "pass", "config": {}},
            backtest_result=backtest_result,
        )
        assert "[Multi-Regime Breakdown]" in context
        assert "Bull: Return=15.00%, Sharpe=2.10, Max Drawdown=-3.00%" in context
        assert "Bear: Return=-5.00%, Sharpe=-0.80, Max Drawdown=-12.00%" in context
        assert "Sideways: Return=2.00%, Sharpe=0.50, Max Drawdown=-2.00%" in context

    def test_context_auto_computes_net_metrics_from_trades_and_daily_returns(self):
        """When summary lacks net metrics but trades and returns are present, auto-computation kicks in."""
        backtest_result = {
            "summary": {"total_return": 5.0, "win_rate": 50.0, "trade_count": 2},
            "trades": [{"action": "buy"}, {"action": "sell"}],
            "daily_returns": [0.02, 0.03],
        }
        context = _build_evaluation_context(
            user_description="Auto compute test",
            strategy={"code": "pass", "config": {}},
            backtest_result=backtest_result,
        )
        assert "[Net Performance & Cost Analysis (CARE-Agents)]" in context
        assert "Total Frictions: 20.0 bps" in context

    def test_context_backward_compatible_with_pure_legacy_summary(self):
        """Pure legacy backtest results format cleanly without error."""
        legacy_result = {
            "summary": {
                "total_return": 12.0,
                "win_rate": 55.0,
                "max_drawdown_pct": 5.0,
                "trade_count": 10,
                "final_value": 1120000,
            }
        }
        context = _build_evaluation_context(
            user_description="Legacy backtest",
            strategy={"code": "pass", "config": {}},
            backtest_result=legacy_result,
        )
        assert "[Summary of backtest results]" in context
        assert "total revenue: 12.0%" in context
        # Should not crash and not have empty brackets
        assert "Based on the above information" in context

    def test_should_optimize_strategy_thresholds(self):
        """should_optimize_strategy returns True for low scores or high priority issues."""
        assert should_optimize_strategy({"overall_score": 65, "is_satisfactory": True, "optimization_priority": "low"}) is True
        assert should_optimize_strategy({"overall_score": 85, "is_satisfactory": False, "optimization_priority": "low"}) is True
        assert should_optimize_strategy({"overall_score": 85, "is_satisfactory": True, "optimization_priority": "high"}) is True
        assert should_optimize_strategy({"overall_score": 85, "is_satisfactory": True, "optimization_priority": "none"}) is False


class TestM4DefectRegressionGuards:
    """
    Permanent regression test guards preventing Defect 1, Defect 2, and Defect 3.
    Target: core/backtest/result_evaluator.py
    """

    def test_positional_empty_trades_numeric_returns(self):
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

    def test_positional_empty_trades_default_friction(self):
        """Empty trades with positional returns and default friction fallback."""
        trades = []
        daily_returns = [0.005, -0.002, 0.008]

        res = calculate_net_performance_metrics(trades, daily_returns)
        assert res["trade_count"] == 0
        assert res["total_frictions_bps"] == 0.0
        assert res["gross_return"] == pytest.approx(res["net_return"], abs=1e-6)

    def test_positional_equity_curve_return_derivation(self):
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

        # Also verify normalized equity curve [1.0, 1.02, 1.05]
        res_norm = calculate_net_performance_metrics(trades, [1.0, 1.02, 1.05], friction)
        assert res_norm["gross_return"] == pytest.approx(0.05, abs=1e-4)
        assert res_norm["trade_count"] == 1
        assert res_norm["total_frictions_bps"] == 12.5

    def test_positional_vs_keyword_equity_curve_parity(self):
        """Positional Pattern 2 and Keyword Pattern 2 must return identical metrics."""
        trades = [{"action": "buy"}, {"action": "sell"}]
        equity_curve = [100.0, 101.5, 99.5, 103.0]
        friction = FrictionConfig(sell_stamp_duty_bps=5.0, commission_bps=2.5, slippage_bps=5.0)

        res_kw = calculate_net_performance_metrics(
            trades=trades, equity_curve=equity_curve, friction=friction
        )
        res_pos = calculate_net_performance_metrics(trades, equity_curve, friction)

        for key in ["gross_return", "net_return", "net_sharpe", "net_sortino", "net_calmar", "net_max_drawdown", "total_frictions_bps", "trade_count"]:
            assert res_pos[key] == pytest.approx(res_kw[key], abs=1e-6), f"Mismatch in key {key}"

    def test_shares_type_coercion_string_and_none(self):
        """
        Prevent Defect 3: Non-numeric strings, string floats, and None values in 'shares', 'amount',
        or 'qty' must be coerced safely and must NOT raise TypeError.
        """
        # String integer shares: positive -> buy (7.5 bps), negative -> sell (12.5 bps)
        trades_str = [
            {"shares": "100"},
            {"shares": "-200"},
        ]
        res_str = calculate_net_performance_metrics(trades=trades_str, daily_returns=[0.01, 0.02])
        assert res_str["trade_count"] == 2
        assert res_str["total_frictions_bps"] == 20.0  # 7.5 + 12.5 = 20.0

        # String float shares across aliases
        trades_aliases = [
            {"amount": "500.5"},
            {"qty": "-250.0"},
        ]
        res_aliases = calculate_net_performance_metrics(trades=trades_aliases, daily_returns=[0.01, 0.02])
        assert res_aliases["trade_count"] == 2
        assert res_aliases["total_frictions_bps"] == 20.0

        # None shares fallback to roundtrip default (20.0 bps)
        trades_none = [{"shares": None}, {"amount": None}, {"qty": None}]
        res_none = calculate_net_performance_metrics(trades=trades_none, daily_returns=[0.01])
        assert res_none["trade_count"] == 3
        assert res_none["total_frictions_bps"] == 60.0  # 3 * 20.0

        # Malformed non-numeric values
        trades_malformed = [{"shares": "not_a_number"}, {"shares": []}, {"shares": {}}]
        res_malformed = calculate_net_performance_metrics(trades=trades_malformed, daily_returns=[0.01])
        assert res_malformed["trade_count"] == 3
        assert res_malformed["total_frictions_bps"] == 60.0

    def test_all_three_positional_patterns(self):
        """
        Verifies that all three canonical calling patterns work seamlessly positionally
        and produce consistent, expected financial metrics:
        Pattern 1: calculate_net_performance_metrics(trades, daily_returns, friction)
        Pattern 2: calculate_net_performance_metrics(trades, equity_curve, friction)
        Pattern 3: calculate_net_performance_metrics(gross_returns, trades, friction)
        """
        trades = [{"action": "buy"}, {"action": "sell"}]
        friction = FrictionConfig()

        # Pattern 1: (trades, daily_returns, friction)
        daily_returns = [0.02, 0.03]
        res_p1 = calculate_net_performance_metrics(trades, daily_returns, friction)
        assert res_p1["trade_count"] == 2
        assert res_p1["total_frictions_bps"] == 20.0  # 7.5 + 12.5
        assert res_p1["gross_return"] == pytest.approx((1.02 * 1.03) - 1.0, abs=1e-6)

        # Pattern 2: (trades, equity_curve, friction)
        # Equity curve corresponding to 2% and 3% returns: [100.0, 102.0, 105.06]
        equity_curve = [100.0, 102.0, 105.06]
        res_p2 = calculate_net_performance_metrics(trades, equity_curve, friction)
        assert res_p2["trade_count"] == 2
        assert res_p2["total_frictions_bps"] == 20.0
        assert res_p2["gross_return"] == pytest.approx(res_p1["gross_return"], abs=1e-5)
        assert res_p2["net_return"] == pytest.approx(res_p1["net_return"], abs=1e-5)

        # Pattern 3: (gross_returns, trades, friction)
        res_p3 = calculate_net_performance_metrics(daily_returns, trades, friction)
        assert res_p3["trade_count"] == 2
        assert res_p3["total_frictions_bps"] == 20.0
        assert res_p3["gross_return"] == pytest.approx(res_p1["gross_return"], abs=1e-6)
        assert res_p3["net_return"] == pytest.approx(res_p1["net_return"], abs=1e-6)
