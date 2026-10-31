"""
Empirical Challenge & Stress-Test Suite for Milestone M2:
Bayesian Log-Odds Aggregation & Legacy Multiplier Fallbacks.

Author: Challenger M2_2
Execution: Deterministic offline Python / pytest harness.
"""

import math
import pytest
from typing import Any, Dict

from tradingagents.graph.signal_processing import (
    SignalProcessor,
    calculate_bayesian_log_odds_target_price,
    compute_bayesian_log_odds_details,
)
from core.agents.utils.weight_calculator import RegimeAdaptiveWeightCalculator


# ==============================================================================
# Challenge 1: Numerical Stability Under Extreme Posterior Probabilities
# ==============================================================================

class TestExtremePosteriorProbabilities:
    """Stress-test numerical stability under extreme boundary probabilities."""

    @pytest.mark.parametrize(
        "p_opt,p_caut,p_neu",
        [
            (0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 0.0),
            (1e-10, 1.0, 0.0),
            (1.0, 1e-10, 0.0),
            (1e-10, 1e-10, 1.0),
            (0.0, 1e-10, 1.0),
            (1e-10, 0.0, 1.0),
            (1e-30, 1e-30, 1.0),
            (1.0, 1.0, 1.0),  # unnormalized sum > 1
            (0.0, 0.0, 0.0),  # all zero
        ],
    )
    def test_extreme_posteriors_calculate_target_price(self, p_opt, p_caut, p_neu):
        posteriors = {
            "analyst_extreme": {
                "p_optimistic": p_opt,
                "p_cautious": p_caut,
                "p_neutral": p_neu,
                "expected_move_bps": 100.0,
            }
        }
        for action in ["buy", "sell", "hold"]:
            for regime in ["bull", "bear", "sideways"]:
                target = calculate_bayesian_log_odds_target_price(
                    current_price=100.0,
                    action=action,
                    regime=regime,
                    analyst_posteriors=posteriors,
                    is_china=True,
                )
                assert isinstance(target, float), f"Target should be float, got {type(target)}"
                assert not math.isnan(target), f"Target is NaN for p_opt={p_opt}, p_caut={p_caut}"
                assert not math.isinf(target), f"Target is Inf for p_opt={p_opt}, p_caut={p_caut}"
                assert target > 0, f"Target price should be positive, got {target}"

    def test_all_seven_analysts_extreme_cautious(self):
        """All 7 analysts output extreme cautious p_caut=1.0, p_opt=0.0."""
        posteriors = {
            f"analyst_{i}": {
                "p_optimistic": 0.0,
                "p_cautious": 1.0,
                "p_neutral": 0.0,
                "expected_move_bps": -200.0,
            }
            for i in range(7)
        }
        details = compute_bayesian_log_odds_details(
            current_price=100.0,
            action="sell",
            regime="bear",
            analyst_posteriors=posteriors,
        )
        assert details["p_agg"] < 0.001
        # L_0(bear) = ln(0.4/0.6) ~ -0.405465. eps = 1e-4 -> ln(1e-4) ~ -9.21034. l_agg ~ -9.6158
        assert details["l_agg"] <= -9.6
        assert details["target_price"] < 100.0
        assert details["target_price"] > 0.0

    def test_all_seven_analysts_extreme_optimistic(self):
        """All 7 analysts output extreme optimistic p_opt=1.0, p_caut=0.0."""
        posteriors = {
            f"analyst_{i}": {
                "p_optimistic": 1.0,
                "p_cautious": 0.0,
                "p_neutral": 0.0,
                "expected_move_bps": 200.0,
            }
            for i in range(7)
        }
        details = compute_bayesian_log_odds_details(
            current_price=100.0,
            action="buy",
            regime="bull",
            analyst_posteriors=posteriors,
        )
        assert details["p_agg"] > 0.999
        # L_0(bull) = ln(0.6/0.4) ~ +0.405465. eps = 1e-4 -> ln(1/1e-4) ~ +9.21034. l_agg ~ +9.6158
        assert details["l_agg"] >= 9.6
        assert details["target_price"] > 100.0
        assert details["target_price"] < 120.0

    def test_100_analysts_extreme_accumulation_clipped_with_unnormalized_weights(self):
        """100 analysts extreme optimistic with unnormalized weights: check clipping prevents float overflow."""
        posteriors = {
            f"analyst_{i}": {
                "p_optimistic": 1.0,
                "p_cautious": 1e-10,
                "expected_move_bps": 500.0,
            }
            for i in range(100)
        }
        # Unnormalized weights where sum = 100.0
        unnormalized_weights = {f"analyst_{i}": 1.0 for i in range(100)}
        details = compute_bayesian_log_odds_details(
            current_price=100.0,
            action="buy",
            regime="bull",
            analyst_posteriors=posteriors,
            weights=unnormalized_weights,
        )
        # l_agg will be 0.405 + 100 * 9.21 = 921.4, which is clipped to 10.0
        assert details["l_agg"] > 10.0
        assert details["p_agg"] == pytest.approx(1.0 / (1.0 + math.exp(-10.0)), abs=1e-5)
        assert not math.isnan(details["target_price"])
        assert not math.isinf(details["target_price"])


# ==============================================================================
# Challenge 2: Extreme Expected Moves (0 bps, 50,000 bps, Negative bps)
# ==============================================================================

class TestExtremeExpectedMoves:
    """Stress-test behaviour with zero, extreme positive, and extreme negative moves."""

    def test_zero_expected_move_bps(self):
        """When expected move is 0 bps, deadband +50 bps floor applies."""
        posteriors = {
            "market_analyst_v2": {
                "p_optimistic": 0.80,
                "p_cautious": 0.10,
                "expected_move_bps": 0.0,
            }
        }
        # For buy: calibrated_return will be 0.0, max(0.0, 0.005) = 0.005 (+50 bps floor)
        target_buy = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="buy", regime="bull", analyst_posteriors=posteriors
        )
        assert target_buy == 100.50

        # For sell: calibrated_return will be 0.0, max(0.0, 0.005) = 0.005 (-50 bps floor)
        target_sell = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="sell", regime="bull", analyst_posteriors=posteriors
        )
        assert target_sell == 99.50

    def test_negative_expected_move_bps(self):
        """When analyst gives negative bps (e.g. -250 bps), direction is properly handled."""
        posteriors = {
            "market_analyst_v2": {
                "p_optimistic": 0.10,
                "p_cautious": 0.80,
                "expected_move_bps": -250.0,
            }
        }
        # Sell action in bear regime
        details_sell = compute_bayesian_log_odds_details(
            current_price=100.0, action="sell", regime="bear", analyst_posteriors=posteriors
        )
        # p_agg < 0.5, 2*p_agg - 1.0 < 0
        # calibrated_return is negative, but sell uses max(|calibrated_return|, 0.005)
        assert details_sell["target_price"] < 100.0
        assert details_sell["target_price"] > 90.0

    def test_extreme_positive_expected_move_50000_bps_buy(self):
        """50,000 bps (500% move) on buy action."""
        posteriors = {
            "market_analyst_v2": {
                "p_optimistic": 0.90,
                "p_cautious": 0.05,
                "expected_move_bps": 50000.0,
            }
        }
        target_buy = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="buy", regime="bull", analyst_posteriors=posteriors
        )
        # calibrated_return = (2*p_agg - 1) * 5.0 > 0
        assert target_buy > 100.0
        assert not math.isnan(target_buy)
        assert not math.isinf(target_buy)

    def test_extreme_move_50000_bps_sell_action_boundary(self):
        """
        Critical Challenge: If expected_move_bps is 50,000 (500%),
        calibrated_return = (2*p_agg - 1.0) * 5.0.
        What is the behavior of sell price?
        Empirical finding: Target price becomes negative (-366.10) because
        abs(calibrated_return) = 4.661 > 1.0, so 1.0 - 4.661 < 0.
        Directionally it is < 100.0, but negative in absolute price terms.
        """
        posteriors = {
            "market_analyst_v2": {
                "p_optimistic": 0.05,
                "p_cautious": 0.95,
                "expected_move_bps": -50000.0,
            }
        }
        details = compute_bayesian_log_odds_details(
            current_price=100.0, action="sell", regime="bear", analyst_posteriors=posteriors
        )
        target_sell = details["target_price"]
        assert target_sell < 100.0, f"Sell target price {target_sell} must be < current_price 100.0"
        # Confirm empirical negative price finding
        assert target_sell < 0.0, "Expected negative price under 50,000 bps move due to lack of non-negative price floor"


# ==============================================================================
# Challenge 3: Action Direction Compliance (Buy > Current Price, Sell < Current Price)
# ==============================================================================

class TestActionDirectionCompliance:
    """Verify calibrated target price strictly respects action direction across varied conditions."""

    @pytest.mark.parametrize("regime", ["bull", "bear", "sideways"])
    @pytest.mark.parametrize("price", [10.0, 50.0, 100.0, 1850.50])
    @pytest.mark.parametrize("p_opt,p_caut", [
        (0.9, 0.1),  # strongly optimistic
        (0.1, 0.9),  # strongly cautious
        (0.33, 0.33),  # neutral
    ])
    def test_buy_price_strictly_greater_than_current(self, regime, price, p_opt, p_caut):
        posteriors = {
            "analyst_1": {"p_optimistic": p_opt, "p_cautious": p_caut, "expected_move_bps": 100.0}
        }
        target = calculate_bayesian_log_odds_target_price(
            current_price=price, action="buy", regime=regime, analyst_posteriors=posteriors
        )
        assert target > price, f"Buy target {target} should be > current price {price}"

    @pytest.mark.parametrize("regime", ["bull", "bear", "sideways"])
    @pytest.mark.parametrize("price", [10.0, 50.0, 100.0, 1850.50])
    @pytest.mark.parametrize("p_opt,p_caut", [
        (0.9, 0.1),
        (0.1, 0.9),
        (0.33, 0.33),
    ])
    def test_sell_price_strictly_less_than_current(self, regime, price, p_opt, p_caut):
        posteriors = {
            "analyst_1": {"p_optimistic": p_opt, "p_cautious": p_caut, "expected_move_bps": -100.0}
        }
        target = calculate_bayesian_log_odds_target_price(
            current_price=price, action="sell", regime=regime, analyst_posteriors=posteriors
        )
        assert target < price, f"Sell target {target} should be < current price {price}"

    def test_penny_stock_rounding_quantization_edge_case(self):
        """
        Examine penny stock edge case where rounding to 2 decimals
        causes target == current_price if current_price <= 0.50 and move is 50 bps.
        """
        posteriors = {
            "analyst_1": {"p_optimistic": 0.33, "p_cautious": 0.33, "expected_move_bps": 50.0}
        }
        # Price 0.50 with +0.5% move -> 0.5025 -> round(0.5025, 2) == 0.50
        target = calculate_bayesian_log_odds_target_price(
            current_price=0.50, action="buy", regime="sideways", analyst_posteriors=posteriors
        )
        # At 0.50, tick size 0.01 exceeds 0.5% (0.0025)
        assert target == 0.50

        # For standard stock prices (>= 2.00), verify direction strictly holds:
        target_2 = calculate_bayesian_log_odds_target_price(
            current_price=2.00, action="buy", regime="sideways", analyst_posteriors=posteriors
        )
        assert target_2 > 2.00


# ==============================================================================
# Challenge 4: Fallback Testing (Missing/None States & Legacy Multipliers)
# ==============================================================================

class TestFallbackToLegacyMultipliers:
    """Stress-test process_signal and _smart_price_estimation fallback behavior."""

    @pytest.mark.parametrize("state_val", [
        None,
        {},
        {"analyst_posteriors": None},
        {"analyst_posteriors": {}},
        {"some_irrelevant_key": 123},
    ])
    def test_smart_price_estimation_legacy_multiplier_fallbacks(self, state_val):
        processor = SignalProcessor()
        text_buy = "Stock price is 100.00 yuan. High conviction BUY."
        text_sell = "Stock price is 100.00 yuan. High conviction SELL."

        # China A-shares (1.15 buy / 0.95 sell)
        res_buy_china = processor._smart_price_estimation(text_buy, action="buy", is_china=True, state=state_val)
        res_sell_china = processor._smart_price_estimation(text_sell, action="sell", is_china=True, state=state_val)
        assert res_buy_china == 115.00, f"Expected 115.00 for state={state_val}, got {res_buy_china}"
        assert res_sell_china == 95.00, f"Expected 95.00 for state={state_val}, got {res_sell_china}"

        # US Stocks (1.12 buy / 0.92 sell)
        res_buy_us = processor._smart_price_estimation(text_buy, action="buy", is_china=False, state=state_val)
        res_sell_us = processor._smart_price_estimation(text_sell, action="sell", is_china=False, state=state_val)
        assert res_buy_us == 112.00, f"Expected 112.00 for state={state_val}, got {res_buy_us}"
        assert res_sell_us == 92.00, f"Expected 92.00 for state={state_val}, got {res_sell_us}"

    @pytest.mark.parametrize("state_val", [
        None,
        {},
        {"analyst_posteriors": None},
        {"analyst_posteriors": {}},
    ])
    def test_process_signal_offline_legacy_multiplier_fallbacks(self, state_val):
        """When LLM is None and state has no posteriors, process_signal matches legacy multipliers."""
        processor = SignalProcessor(quick_thinking_llm=None)
        signal_buy = "Comprehensive analysis suggests: BUY Ping An. Current price: 100.00"
        signal_sell = "Comprehensive analysis suggests: SELL Ping An. Current price: 100.00"

        # Buy China
        res_buy = processor.process_signal(signal_buy, stock_symbol="600519", state=state_val)
        assert res_buy["action"] == "buy"
        assert res_buy["target_price"] == 115.00
        assert "bayesian_target_price" not in res_buy

        # Sell China
        res_sell = processor.process_signal(signal_sell, stock_symbol="600519", state=state_val)
        assert res_sell["action"] == "sell"
        assert res_sell["target_price"] == 95.00
        assert "bayesian_target_price" not in res_sell

        # Buy US
        res_buy_us = processor.process_signal(signal_buy, stock_symbol="AAPL", state=state_val)
        assert res_buy_us["action"] == "buy"
        assert res_buy_us["target_price"] == 112.00

        # Sell US
        res_sell_us = processor.process_signal(signal_sell, stock_symbol="AAPL", state=state_val)
        assert res_sell_us["action"] == "sell"
        assert res_sell_us["target_price"] == 92.00

    def test_calculate_bayesian_log_odds_direct_fallback(self):
        """Direct call to calculate_bayesian_log_odds_target_price with empty posteriors."""
        for is_china, buy_mult, sell_mult in [(True, 1.15, 0.95), (False, 1.12, 0.92)]:
            for empty_post in [{}, None]:  # type: ignore
                buy_target = calculate_bayesian_log_odds_target_price(
                    current_price=100.0, action="buy", regime="bull", analyst_posteriors=empty_post, is_china=is_china
                )
                sell_target = calculate_bayesian_log_odds_target_price(
                    current_price=100.0, action="sell", regime="bear", analyst_posteriors=empty_post, is_china=is_china
                )
                hold_target = calculate_bayesian_log_odds_target_price(
                    current_price=100.0, action="hold", regime="sideways", analyst_posteriors=empty_post, is_china=is_china
                )
                assert buy_target == round(100.0 * buy_mult, 2)
                assert sell_target == round(100.0 * sell_mult, 2)
                assert hold_target == 100.00
