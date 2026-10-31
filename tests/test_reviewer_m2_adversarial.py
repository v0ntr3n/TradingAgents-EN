"""
Adversarial Stress Test Suite for Milestone M2:
Testing edge cases, boundary conditions, numerical stability, and robustness.
"""

import math
import pytest
from core.agents.utils.weight_calculator import (
    DEFAULT_ANALYST_IDS,
    REGIMES,
    RegimeAdaptiveWeightCalculator,
    calculate_report_weights,
)
from tradingagents.graph.signal_processing import (
    SignalProcessor,
    calculate_bayesian_log_odds_target_price,
    compute_bayesian_log_odds_details,
)


class TestAdversarialWeightCalculator:
    """Stress-test RegimeAdaptiveWeightCalculator against hostile/extreme inputs."""

    def test_extreme_numerical_learning_rates(self):
        """Test learning rates from 0.0 to 100.0 without numerical breakdown."""
        for lr in [0.0, 0.001, 1.0, 10.0, 50.0, 100.0]:
            calc = RegimeAdaptiveWeightCalculator(learning_rate=lr)
            posteriors = {
                "market_analyst_v2": {"p_optimistic": 0.99, "p_neutral": 0.01, "p_cautious": 0.0},
                "news_analyst_v2": {"p_optimistic": 0.0, "p_neutral": 0.01, "p_cautious": 0.99},
            }
            w = calc.update_weights("bull", posteriors, 0.02)
            assert pytest.approx(sum(w.values()), abs=1e-5) == 1.0
            assert all(val >= 0.0 for val in w.values())

    def test_massive_iterations_underflow_resilience(self):
        """Simulate 500 consecutive rounds of severe prediction loss."""
        calc = RegimeAdaptiveWeightCalculator(learning_rate=1.0)
        for _ in range(500):
            calc.update_weights("bull", {
                "market_analyst_v2": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
            }, 0.05)
        w = calc.get_weights("bull")
        assert pytest.approx(sum(w.values()), abs=1e-5) == 1.0
        assert w["market_analyst_v2"] >= 0.0

    def test_all_analysts_zero_or_identical_probabilities(self):
        calc = RegimeAdaptiveWeightCalculator()
        posteriors = {
            aid: {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 0.0}
            for aid in DEFAULT_ANALYST_IDS
        }
        w = calc.update_weights("bull", posteriors, 0.02)
        # All equal Brier loss, all weights should remain uniform
        for aid in DEFAULT_ANALYST_IDS:
            assert pytest.approx(w[aid], abs=1e-5) == 1.0 / 7.0

    def test_boundary_realized_returns_around_50bps(self):
        """Test exact deadband boundaries at 0.005 and -0.005."""
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)
        post = {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1}

        # Just at deadband boundary (0.005 is NOT > 0.005, so it classifies as neutral)
        loss_at_boundary = calc.compute_brier_loss(post, 0.005)
        loss_just_above = calc.compute_brier_loss(post, 0.005001)

        # Above threshold targets [1, 0, 0], at threshold targets [0, 1, 0]
        assert loss_at_boundary != loss_just_above
        assert loss_just_above < loss_at_boundary  # Bull prediction rewarded above 50 bps


class TestAdversarialSignalProcessor:
    """Stress-test Bayesian log-odds aggregation and SignalProcessor."""

    def test_extreme_expected_moves_bps(self):
        """Huge expected move (1,000,000 bps = 100x price) should scale deterministically."""
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.99, "p_cautious": 0.01, "expected_move_bps": 1_000_000.0}
        }
        t = calculate_bayesian_log_odds_target_price(100.0, "buy", "bull", posteriors)
        assert t > 100.0
        assert not math.isnan(t)
        assert not math.isinf(t)

    def test_negative_expected_move_with_buy_action(self):
        """If analyst expects negative move but action is BUY, deadband enforces min 0.5% gain."""
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.1, "p_cautious": 0.9, "expected_move_bps": -200.0}
        }
        t = calculate_bayesian_log_odds_target_price(100.0, "buy", "bull", posteriors)
        # Calibrated return will be negative, max(calibrated_return, 0.005) gives 0.005 -> target 100.5
        assert t == 100.50

    def test_positive_expected_move_with_sell_action(self):
        """If analyst expects positive move (+200 bps) but action is SELL, abs(calibrated_return) is subtracted."""
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.9, "p_cautious": 0.1, "expected_move_bps": 200.0}
        }
        t = calculate_bayesian_log_odds_target_price(100.0, "sell", "bear", posteriors)
        # abs(calibrated_return) ~ 0.01428 -> 100 * (1 - 0.01428) = 98.57
        assert t == 98.57
        assert t < 100.0

    def test_log_odds_clipping_bounds(self):
        """Extreme posteriors (1.0 vs 0.0) are safely bounded by clipping to [-10, 10]."""
        extreme_posteriors = {
            f"analyst_{i}": {"p_optimistic": 1.0, "p_cautious": 0.0, "expected_move_bps": 100.0}
            for i in range(20)
        }
        weights = {f"analyst_{i}": 1.0 / 20.0 for i in range(20)}
        details = compute_bayesian_log_odds_details(100.0, "buy", "bull", extreme_posteriors, weights=weights)
        assert details["p_agg"] < 1.0
        assert details["p_agg"] > 0.999
        assert not math.isinf(details["l_agg"])

    def test_signal_processor_robust_to_non_dict_symbol(self):
        """Passing integers or floats as stock_symbol should not crash."""
        sp = SignalProcessor()
        res = sp.process_signal("Buy Ping An at 50.00 yuan", stock_symbol=600000)
        assert res["action"] == "buy"

    def test_signal_processor_disambiguates_current_from_target_price(self):
        """When text contains 'Current price: 80.00' and state has posteriors, target price is not 80.00."""
        sp = SignalProcessor()
        state = {
            "current_price": 80.0,
            "market_regime": "bull",
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.85, "p_cautious": 0.05, "expected_move_bps": 150.0}
            }
        }
        res = sp.process_signal("Current price: 80.00. Recommend buy.", stock_symbol="600519", state=state)
        assert res["action"] == "buy"
        assert res["target_price"] > 80.0
