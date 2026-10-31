"""
Unit Test Suite for Milestone M2:
Regime-Adaptive Weight Calculator & Calibrated Signal Processing

Covers:
1. RegimeAdaptiveWeightCalculator (Initialization, Normalization, Multiclass Brier Loss, MWU Update, Regime Isolation)
2. Fallback Weight Calculation (calculate_report_weights backward compatibility)
3. Bayesian Log-Odds Opinion Pooling & Price Target Calibration
4. SignalProcessor Integration (process_signal, _smart_price_estimation, fallbacks)

Execution: 100% offline, deterministic, zero-network, fast.
"""

import math
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from core.agents.utils.weight_calculator import (
    DEFAULT_ANALYST_IDS,
    REGIMES,
    RegimeAdaptiveWeightCalculator,
    calculate_report_weights,
    format_weighted_reports_prompt,
)
from tradingagents.graph.signal_processing import (
    SignalProcessor,
    calculate_bayesian_log_odds_target_price,
    compute_bayesian_log_odds_details,
)


# ==============================================================================
# 1. Tests for RegimeAdaptiveWeightCalculator
# ==============================================================================

class TestRegimeAdaptiveWeightCalculatorInit:
    """Test initialization and weight retrieval properties."""

    def test_default_initialization(self):
        calc = RegimeAdaptiveWeightCalculator()
        assert set(calc.weights.keys()) == {"bull", "bear", "sideways"}
        assert calc.analyst_ids == DEFAULT_ANALYST_IDS
        assert len(calc.analyst_ids) == 7

        for r in REGIMES:
            weights = calc.get_weights(r)
            assert len(weights) == 7
            for aid in DEFAULT_ANALYST_IDS:
                assert pytest.approx(weights[aid], abs=1e-5) == 1.0 / 7.0
            assert pytest.approx(sum(weights.values()), abs=1e-5) == 1.0

    def test_custom_analyst_ids(self):
        custom_ids = ["market_analyst_v2", "fundamentals_analyst_v2"]
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=custom_ids)
        assert calc.analyst_ids == custom_ids

        for r in REGIMES:
            weights = calc.get_weights(r)
            assert len(weights) == 2
            assert pytest.approx(weights["market_analyst_v2"], abs=1e-5) == 0.5
            assert pytest.approx(weights["fundamentals_analyst_v2"], abs=1e-5) == 0.5
            assert pytest.approx(sum(weights.values()), abs=1e-5) == 1.0

    def test_custom_initial_weights(self):
        init_w = {
            "bull": {"market_analyst_v2": 0.6, "news_analyst_v2": 0.4},
            "bear": {"fundamentals_analyst_v2": 0.8, "market_analyst_v2": 0.2},
            "sideways": {"sector_analyst_v2": 0.5, "fundamentals_analyst_v2": 0.5},
        }
        calc = RegimeAdaptiveWeightCalculator(
            analyst_ids=["market_analyst_v2", "news_analyst_v2", "fundamentals_analyst_v2", "sector_analyst_v2"],
            initial_weights=init_w,
        )
        bull_w = calc.get_weights("bull")
        assert pytest.approx(bull_w["market_analyst_v2"], abs=1e-5) == 0.6
        assert pytest.approx(bull_w["news_analyst_v2"], abs=1e-5) == 0.4

        bear_w = calc.get_weights("bear")
        assert pytest.approx(bear_w["fundamentals_analyst_v2"], abs=1e-5) == 0.8
        assert pytest.approx(bear_w["market_analyst_v2"], abs=1e-5) == 0.2

    def test_regime_normalization_and_unknown_fallback(self):
        calc = RegimeAdaptiveWeightCalculator()
        # Case insensitivity and whitespace
        w_upper = calc.get_weights("BULL")
        w_space = calc.get_weights("  bull  ")
        assert w_upper == w_space

        # Unknown regimes default to sideways
        w_unknown = calc.get_weights("hyper_inflation_chaos")
        w_sideways = calc.get_weights("sideways")
        assert w_unknown == w_sideways

        # None or non-string
        w_none = calc.get_weights(None)  # type: ignore
        assert w_none == w_sideways

    def test_active_analysts_subselection(self):
        calc = RegimeAdaptiveWeightCalculator()
        active = ["market_analyst_v2", "news_analyst_v2"]
        sub_weights = calc.get_weights("bull", active_analysts=active)

        assert set(sub_weights.keys()) == set(active)
        assert pytest.approx(sub_weights["market_analyst_v2"], abs=1e-5) == 0.5
        assert pytest.approx(sub_weights["news_analyst_v2"], abs=1e-5) == 0.5
        assert pytest.approx(sum(sub_weights.values()), abs=1e-5) == 1.0


class TestBrierLossCalculation:
    """Test multiclass Brier loss computation."""

    def test_bull_market_outcomes(self):
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)
        # Realized return > +50 bps -> Target y = [1, 0, 0]
        realized_return = 0.02

        # 1. Perfect optimistic prediction
        perfect_post = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        assert pytest.approx(calc.compute_brier_loss(perfect_post, realized_return), abs=1e-5) == 0.0

        # 2. Worst cautious prediction
        worst_post = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
        # (0-1)^2 + (0-0)^2 + (1-0)^2 = 2.0
        assert pytest.approx(calc.compute_brier_loss(worst_post, realized_return), abs=1e-5) == 2.0

        # 3. Intermediate prediction [0.7, 0.2, 0.1]
        mid_post = {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1}
        # (0.7-1)^2 + 0.2^2 + 0.1^2 = 0.09 + 0.04 + 0.01 = 0.14
        assert pytest.approx(calc.compute_brier_loss(mid_post, realized_return), abs=1e-5) == 0.14

    def test_bear_market_outcomes(self):
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)
        # Realized return < -50 bps -> Target y = [0, 0, 1]
        realized_return = -0.015

        # 1. Perfect cautious prediction
        perfect_post = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
        assert pytest.approx(calc.compute_brier_loss(perfect_post, realized_return), abs=1e-5) == 0.0

        # 2. Worst optimistic prediction
        worst_post = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        assert pytest.approx(calc.compute_brier_loss(worst_post, realized_return), abs=1e-5) == 2.0

    def test_sideways_neutral_market_outcomes(self):
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)
        # Realized return within [-0.005, +0.005] -> Target y = [0, 1, 0]
        realized_return = 0.001

        # 1. Perfect neutral prediction
        perfect_post = {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0}
        assert pytest.approx(calc.compute_brier_loss(perfect_post, realized_return), abs=1e-5) == 0.0

        # 2. Polarized prediction [0.5, 0.0, 0.5]
        polar_post = {"p_optimistic": 0.5, "p_neutral": 0.0, "p_cautious": 0.5}
        # (0.5-0)^2 + (0-1)^2 + (0.5-0)^2 = 0.25 + 1.0 + 0.25 = 1.50
        assert pytest.approx(calc.compute_brier_loss(polar_post, realized_return), abs=1e-5) == 1.50

    def test_unnormalized_probabilities_normalization(self):
        calc = RegimeAdaptiveWeightCalculator()
        # Probabilities summing to 100 instead of 1.0
        pct_post = {"p_optimistic": 80.0, "p_neutral": 10.0, "p_cautious": 10.0}
        loss_pct = calc.compute_brier_loss(pct_post, 0.02)

        # Decimal equivalent: [0.8, 0.1, 0.1] -> (0.8-1)^2 + 0.1^2 + 0.1^2 = 0.04 + 0.01 + 0.01 = 0.06
        assert pytest.approx(loss_pct, abs=1e-5) == 0.06


class TestMultiplicativeWeightsUpdate:
    """Test Multiplicative Weights Update (MWU) adaptation and normalization."""

    def test_mwu_rewards_accurate_analyst(self):
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.5)
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05},  # Accurately predicted bull
            "social_analyst_v2": {"p_optimistic": 0.10, "p_neutral": 0.10, "p_cautious": 0.80},  # Inaccurately predicted bear
        }
        realized_return = 0.03  # Bull market (+3%)

        new_weights = calc.update_weights("bull", posteriors, realized_return)

        # Market analyst weight must strictly increase relative to social analyst
        assert new_weights["market_analyst_v2"] > new_weights["social_analyst_v2"]
        assert pytest.approx(sum(new_weights.values()), abs=1e-5) == 1.0

    def test_regime_isolation(self):
        """Updating weights in 'bull' regime must NOT affect 'bear' or 'sideways'."""
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.5)
        bear_before = dict(calc.get_weights("bear"))
        sideways_before = dict(calc.get_weights("sideways"))

        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.95, "p_neutral": 0.03, "p_cautious": 0.02},
        }
        calc.update_weights("bull", posteriors, 0.02)

        bear_after = calc.get_weights("bear")
        sideways_after = calc.get_weights("sideways")

        assert bear_before == bear_after
        assert sideways_before == sideways_after

    def test_zero_learning_rate_invariance(self):
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.0)
        before = dict(calc.get_weights("bull"))

        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.99, "p_neutral": 0.01, "p_cautious": 0.0},
            "news_analyst_v2": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0},
        }
        after = calc.update_weights("bull", posteriors, 0.02)

        for aid in calc.analyst_ids:
            assert pytest.approx(before[aid], abs=1e-5) == after[aid]

    def test_sequential_multi_step_compounding(self):
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.3)
        # Consistent bull streak: market_analyst_v2 is always right, news_analyst_v2 is always wrong
        for _ in range(5):
            posteriors = {
                "market_analyst_v2": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05},
                "news_analyst_v2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90},
            }
            calc.update_weights("bull", posteriors, 0.015)

        w = calc.get_weights("bull")
        assert w["market_analyst_v2"] > w["news_analyst_v2"] * 5.0
        assert pytest.approx(sum(w.values()), abs=1e-5) == 1.0

    def test_dynamic_analyst_addition(self):
        calc = RegimeAdaptiveWeightCalculator()
        posteriors = {
            "special_quant_analyst": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1},
        }
        updated = calc.update_weights("bull", posteriors, 0.02)
        assert "special_quant_analyst" in updated
        assert "special_quant_analyst" in calc.analyst_ids
        assert pytest.approx(sum(updated.values()), abs=1e-5) == 1.0

    def test_reset_weights(self):
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.5)
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05},
            "news_analyst_v2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90},
        }
        calc.update_weights("bull", posteriors, 0.03)
        assert calc.get_weights("bull")["market_analyst_v2"] != 1.0 / len(calc.analyst_ids)

        calc.reset()
        for r in REGIMES:
            w = calc.get_weights(r)
            for aid in calc.analyst_ids:
                assert pytest.approx(w[aid], abs=1e-5) == 1.0 / len(calc.analyst_ids)


# ==============================================================================
# 2. Tests for Fallback Weight Calculation (calculate_report_weights)
# ==============================================================================

class TestLegacyReportWeightsFallback:
    """Ensure 100% backward compatibility for calculate_report_weights."""

    def test_short_term_style_inference(self):
        reports = {
            "market_report": "Technical analysis showing oversold bounce",
            "news_report": "Earnings beat expectations",
            "sentiment_report": "Retail sentiment positive",
        }
        weights = calculate_report_weights(reports)
        assert "market_report" in weights
        assert "news_report" in weights
        assert "sentiment_report" in weights
        assert weights["market_report"] >= weights["news_report"]
        assert pytest.approx(sum(weights.values()), abs=1e-4) == 1.0

    def test_long_term_style_inference(self):
        reports = {
            "fundamentals_report": "Strong balance sheet with net cash position",
            "sector_report": "Semiconductor sector uptrend",
        }
        weights = calculate_report_weights(reports)
        assert "fundamentals_report" in weights
        assert "sector_report" in weights
        assert weights["fundamentals_report"] > weights["sector_report"]
        assert pytest.approx(sum(weights.values()), abs=1e-4) == 1.0

    def test_empty_or_whitespace_reports(self):
        assert calculate_report_weights({}) == {}
        assert calculate_report_weights({"market_report": "   ", "news_report": None}) == {}

    def test_format_weighted_reports_prompt(self):
        reports = {
            "market_report": "Technical analysis bullish",
            "news_report": "Neutral news catalysts",
        }
        weights = {"market_report": 0.75, "news_report": 0.25}
        formatted = format_weighted_reports_prompt(reports, weights)
        assert "[Important report]" in formatted
        assert "Technical analysis bullish" in formatted


# ==============================================================================
# 3. Tests for Bayesian Log-Odds Aggregation
# ==============================================================================

class TestBayesianLogOddsAggregation:
    """Test Bayesian log-odds opinion pooling and calibrated price target calculation."""

    def test_bull_regime_prior_effect(self):
        """Even with neutral analyst posteriors, a bull prior produces p_agg > 0.5."""
        balanced_posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.3333, "p_cautious": 0.3333, "expected_move_bps": 50.0},
        }
        weights = {"market_analyst_v2": 1.0}

        bull_details = compute_bayesian_log_odds_details(
            current_price=100.0, action="buy", regime="bull", analyst_posteriors=balanced_posteriors, weights=weights
        )
        sideways_details = compute_bayesian_log_odds_details(
            current_price=100.0, action="buy", regime="sideways", analyst_posteriors=balanced_posteriors, weights=weights
        )
        bear_details = compute_bayesian_log_odds_details(
            current_price=100.0, action="buy", regime="bear", analyst_posteriors=balanced_posteriors, weights=weights
        )

        assert bull_details["p_agg"] > 0.50
        assert pytest.approx(sideways_details["p_agg"], abs=1e-3) == 0.50
        assert bear_details["p_agg"] < 0.50

    def test_strong_bull_consensus_price_projection(self):
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.85, "p_cautious": 0.05, "expected_move_bps": 120.0},
            "news_analyst_v2": {"p_optimistic": 0.80, "p_cautious": 0.10, "expected_move_bps": 100.0},
        }
        weights = {"market_analyst_v2": 0.5, "news_analyst_v2": 0.5}

        target = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="buy", regime="bull", analyst_posteriors=posteriors, weights=weights
        )
        # Should project upward move between 0.5% and 2.0%
        assert target > 100.0
        assert target < 120.0

    def test_strong_bear_consensus_price_projection(self):
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.05, "p_cautious": 0.85, "expected_move_bps": -150.0},
            "fundamentals_analyst_v2": {"p_optimistic": 0.08, "p_cautious": 0.80, "expected_move_bps": -100.0},
        }
        weights = {"market_analyst_v2": 0.5, "fundamentals_analyst_v2": 0.5}

        target = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="sell", regime="bear", analyst_posteriors=posteriors, weights=weights
        )
        # Should project downward move below 100.0
        assert target < 100.0
        assert target > 80.0

    def test_hold_action_preserves_current_price(self):
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.70, "p_cautious": 0.20, "expected_move_bps": 80.0},
        }
        target = calculate_bayesian_log_odds_target_price(
            current_price=52.50, action="hold", regime="bull", analyst_posteriors=posteriors
        )
        assert target == 52.50

    def test_empty_posteriors_fallback_to_legacy_multipliers(self):
        # China A-share fallback
        china_buy = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="buy", regime="bull", analyst_posteriors={}, is_china=True
        )
        assert china_buy == 115.0  # 1.15 multiplier

        china_sell = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="sell", regime="bear", analyst_posteriors={}, is_china=True
        )
        assert china_sell == 95.0  # 0.95 multiplier

        # US stock fallback
        us_buy = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="buy", regime="bull", analyst_posteriors={}, is_china=False
        )
        assert us_buy == 112.0  # 1.12 multiplier

        us_sell = calculate_bayesian_log_odds_target_price(
            current_price=100.0, action="sell", regime="bear", analyst_posteriors={}, is_china=False
        )
        assert us_sell == 92.0  # 0.92 multiplier


# ==============================================================================
# 4. Tests for SignalProcessor Integration & Fallbacks
# ==============================================================================

class TestSignalProcessorIntegration:
    """Test SignalProcessor with Bayesian calibration and fallback mechanisms."""

    def test_smart_price_estimation_with_state_posteriors(self):
        processor = SignalProcessor()
        state = {
            "market_regime": "bull",
            "current_price": 50.0,
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.85, "p_cautious": 0.05, "expected_move_bps": 150.0},
                "news_analyst_v2": {"p_optimistic": 0.75, "p_cautious": 0.10, "expected_move_bps": 80.0},
            },
        }
        target = processor._smart_price_estimation(
            text="Recommended to buy the dip",
            action="buy",
            is_china=True,
            state=state,
        )
        assert target is not None
        assert target > 50.0
        assert target < 60.0

    def test_smart_price_estimation_without_state_fallback(self):
        processor = SignalProcessor()
        # Without state: China A-share 1.15 fallback
        target_buy = processor._smart_price_estimation(
            text="The current price is 100.00 yuan. Highly recommend buying.",
            action="buy",
            is_china=True,
            state=None,
        )
        assert target_buy == 115.0

        target_sell = processor._smart_price_estimation(
            text="The current price is 100.00 yuan. Strongly recommend selling.",
            action="sell",
            is_china=True,
            state=None,
        )
        assert target_sell == 95.0

    def test_smart_price_estimation_percentage_in_text(self):
        processor = SignalProcessor()
        target = processor._smart_price_estimation(
            text="Current price 100.00, expected to rise 20%",
            action="buy",
            is_china=True,
            state=None,
        )
        assert target == 120.0

    def test_process_signal_offline_fallback_with_state(self):
        """When LLM is None, process_signal runs offline fallback and incorporates Bayesian state."""
        processor = SignalProcessor(quick_thinking_llm=None)
        state = {
            "market_regime": "bear",
            "current_price": 80.0,
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.05, "p_cautious": 0.85, "expected_move_bps": -200.0},
            },
        }
        signal_text = "Market shows severe breakdown. Recommend to SELL immediately. Current price: 80.00"

        decision = processor.process_signal(signal_text, stock_symbol="600519", state=state)
        assert decision["action"] == "sell"
        assert decision["target_price"] is not None
        assert decision["target_price"] < 80.0
        assert "bayesian_target_price" in decision
        assert decision["p_agg"] < 0.5

    def test_process_signal_with_mock_llm(self):
        """When LLM returns JSON with missing target price, Bayesian calibrated price fills it."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"action": "buy", "target_price": null, "confidence": 0.85, "risk_score": 0.25, "reasoning": "Strong breakout"}'
        mock_llm.invoke.return_value = mock_response

        processor = SignalProcessor(quick_thinking_llm=mock_llm)
        state = {
            "market_regime": "bull",
            "current_price": 100.0,
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.85, "p_cautious": 0.05, "expected_move_bps": 120.0},
            },
        }
        signal_text = "Current price: 100.00. Strong momentum rally."

        decision = processor.process_signal(signal_text, stock_symbol="000001", state=state)
        assert decision["action"] == "buy"
        assert decision["target_price"] > 100.0
        assert decision["target_price"] < 120.0
        assert decision["confidence"] == 0.85
        assert "bayesian_target_price" in decision

    def test_process_signal_state_passed_as_dict_symbol(self):
        """If caller passes state dict as the second argument, process_signal adapts gracefully."""
        processor = SignalProcessor(quick_thinking_llm=None)
        state = {
            "stock_symbol": "000001",
            "market_regime": "bull",
            "current_price": 25.0,
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.80, "p_cautious": 0.10, "expected_move_bps": 100.0},
            },
        }
        signal_text = "Recommend buy. Current price: 25.00"

        # Passing state as second positional argument
        decision = processor.process_signal(signal_text, state)
        assert decision["action"] == "buy"
        assert decision["target_price"] > 25.0

    def test_invalid_signal_returns_default_decision(self):
        processor = SignalProcessor(quick_thinking_llm=None)
        decision_empty = processor.process_signal("")
        assert decision_empty["action"] == "hold"
        assert decision_empty["target_price"] is None

        decision_none = processor.process_signal(None)  # type: ignore
        assert decision_none["action"] == "hold"

    def test_extract_target_price_helper(self):
        processor = SignalProcessor()
        text = "Current valuation suggests a target price: 48.50 yuan for Ping An."
        price = processor._extract_target_price(text)
        assert price == 48.50
