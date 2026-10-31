"""
Canonical Acceptance Test Suite: Regime Weight Calculator & Calibrated Signal Processing
Milestone: M2 / Phase 2
Reference: PROJECT.md (Features 11-16), ORIGINAL_REQUEST.md (Acceptance Criteria 2)

Acceptance Criteria:
- Verifies multiclass Brier loss calculations for 3-class analyst predictions against market deadband outcomes
- Verifies weight convergence across synthetic bull, bear, and sideways return sequences
- Verifies strict regime isolation (updates in one regime do not contaminate other regimes)
- Verifies calibrated signal processing outputs (Bayesian log-odds opinion pooling, empirical price targets, confidence)
- Verifies fallback mechanisms and backward compatibility
"""

import math
from typing import Any, Dict, List, Optional
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

# Specification exports & public APIs
from core.agents.utils.weight_calculator import (
    RegimeMultiplicativeWeightManager,
    aggregate_posteriors,
)
from tradingagents.graph.signal_processing import process_calibrated_signal


# ==============================================================================
# 1. Multiclass Brier Loss Unit Tests
# ==============================================================================
class TestMulticlassBrierLoss:
    """Verifies 3-class Brier loss calculations across market outcome deadbands."""

    @pytest.fixture
    def calculator(self):
        return RegimeAdaptiveWeightCalculator(return_threshold=0.005)  # 50 bps deadband

    def test_brier_loss_bull_outcome(self, calculator):
        """Realized return > +50 bps: Target y = [1, 0, 0] (optimistic)."""
        realized_return = +0.02  # +200 bps

        # Perfect optimistic forecast: loss = 0.0
        perfect_bull = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        assert calculator.compute_brier_loss(perfect_bull, realized_return) == 0.0

        # Worst-case forecast (100% cautious): loss = (0-1)^2 + (0-0)^2 + (1-0)^2 = 2.0
        worst_cautious = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
        assert calculator.compute_brier_loss(worst_cautious, realized_return) == 2.0

        # Neutral forecast (100% neutral): loss = (0-1)^2 + (1-0)^2 + (0-0)^2 = 2.0
        worst_neutral = {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0}
        assert calculator.compute_brier_loss(worst_neutral, realized_return) == 2.0

        # Uninformative uniform: (1/3-1)^2 + (1/3-0)^2 + (1/3-0)^2 = 4/9 + 1/9 + 1/9 = 6/9 = 2/3
        uniform = {"p_optimistic": 1/3, "p_neutral": 1/3, "p_cautious": 1/3}
        assert pytest.approx(calculator.compute_brier_loss(uniform, realized_return), abs=1e-4) == 2.0 / 3.0

    def test_brier_loss_bear_outcome(self, calculator):
        """Realized return < -50 bps: Target y = [0, 0, 1] (cautious)."""
        realized_return = -0.015  # -150 bps

        perfect_bear = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
        assert calculator.compute_brier_loss(perfect_bear, realized_return) == 0.0

        worst_bull = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        assert calculator.compute_brier_loss(worst_bull, realized_return) == 2.0

    def test_brier_loss_sideways_neutral_outcome(self, calculator):
        """Realized return within [-50 bps, +50 bps]: Target y = [0, 1, 0] (neutral)."""
        realized_return = +0.001  # +10 bps (inside deadband)

        perfect_neutral = {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0}
        assert calculator.compute_brier_loss(perfect_neutral, realized_return) == 0.0

        bullish_post = {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1}
        # Loss = (0.8 - 0)^2 + (0.1 - 1)^2 + (0.1 - 0)^2 = 0.64 + 0.81 + 0.01 = 1.46
        assert pytest.approx(calculator.compute_brier_loss(bullish_post, realized_return), abs=1e-4) == 1.46

    def test_brier_loss_unnormalized_probabilities_automatically_normalized(self, calculator):
        """Probabilities that do not sum to 1.0 are scaled before computing loss."""
        unnormalized = {"p_optimistic": 2.0, "p_neutral": 0.0, "p_cautious": 0.0}
        # Should normalize to [1.0, 0.0, 0.0] -> loss against bull outcome should be 0.0
        assert calculator.compute_brier_loss(unnormalized, realized_return=+0.01) == 0.0

    def test_brier_loss_strictly_bounded_in_zero_to_two(self, calculator):
        """Brier loss must strictly reside in [0.0, 2.0]."""
        test_posts = [
            {"p_optimistic": 0.6, "p_neutral": 0.2, "p_cautious": 0.2},
            {"p_optimistic": 0.33, "p_neutral": 0.34, "p_cautious": 0.33},
            {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90},
        ]
        for post in test_posts:
            for ret in [-0.03, -0.002, 0.0, +0.002, +0.04]:
                loss = calculator.compute_brier_loss(post, ret)
                assert 0.0 <= loss <= 2.0


# ==============================================================================
# 2. Weight Convergence Across Synthetic Sequences & Regime Partitioning
# ==============================================================================
class TestRegimeWeightConvergence:
    """Verifies weight convergence across synthetic sequences and regime isolation."""

    @pytest.fixture
    def analysts(self):
        return ["bull_specialist", "bear_specialist", "neutral_specialist"]

    @pytest.fixture
    def weight_manager(self, analysts):
        return RegimeAdaptiveWeightCalculator(analyst_ids=analysts, learning_rate=0.25)

    def test_synthetic_bull_sequence_convergence(self, weight_manager):
        """
        Over a synthetic 20-day bull rally (+1.5% daily), an analyst predicting
        high optimism must exponentially gain weight, dominating the ensemble.
        """
        posteriors = {
            "bull_specialist": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05},
            "bear_specialist": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85},
            "neutral_specialist": {"p_optimistic": 0.20, "p_neutral": 0.60, "p_cautious": 0.20},
        }

        for _ in range(20):
            weight_manager.update_weights(
                regime="bull",
                analyst_posteriors=posteriors,
                realized_return=+0.015,
            )

        bull_weights = weight_manager.get_weights("bull")
        # Bull specialist should dominate with > 65% weight
        assert bull_weights["bull_specialist"] > 0.65
        # Bear specialist should decay significantly (< 10%)
        assert bull_weights["bear_specialist"] < 0.10
        # Normalization invariant
        assert pytest.approx(sum(bull_weights.values()), abs=1e-5) == 1.0

    def test_synthetic_bear_sequence_convergence(self, weight_manager):
        """
        Over a synthetic 20-day bear decline (-1.5% daily), a cautious specialist
        must exponentially gain weight, while optimistic analysts decay.
        """
        posteriors = {
            "bull_specialist": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05},
            "bear_specialist": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85},
            "neutral_specialist": {"p_optimistic": 0.20, "p_neutral": 0.60, "p_cautious": 0.20},
        }

        for _ in range(20):
            weight_manager.update_weights(
                regime="bear",
                analyst_posteriors=posteriors,
                realized_return=-0.015,
            )

        bear_weights = weight_manager.get_weights("bear")
        assert bear_weights["bear_specialist"] > 0.65
        assert bear_weights["bull_specialist"] < 0.10
        assert pytest.approx(sum(bear_weights.values()), abs=1e-5) == 1.0

    def test_synthetic_sideways_sequence_convergence(self, weight_manager):
        """
        Over a synthetic 20-day mean-reverting churn (+0.01% daily, within deadband),
        neutral analyst gains weight over directional specialists.
        """
        posteriors = {
            "bull_specialist": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05},
            "bear_specialist": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85},
            "neutral_specialist": {"p_optimistic": 0.10, "p_neutral": 0.80, "p_cautious": 0.10},
        }

        for _ in range(20):
            weight_manager.update_weights(
                regime="sideways",
                analyst_posteriors=posteriors,
                realized_return=+0.0001,  # within 50 bps deadband
            )

        sideways_weights = weight_manager.get_weights("sideways")
        assert sideways_weights["neutral_specialist"] > 0.65
        assert sideways_weights["bull_specialist"] < 0.20
        assert sideways_weights["bear_specialist"] < 0.20
        assert pytest.approx(sum(sideways_weights.values()), abs=1e-5) == 1.0

    def test_regime_isolation_property(self, weight_manager):
        """
        Updates in 'bull' regime must NOT alter weight tables in 'bear' or 'sideways' regimes.
        """
        initial_bear = weight_manager.get_weights("bear")
        initial_sideways = weight_manager.get_weights("sideways")

        posteriors = {
            "bull_specialist": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "bear_specialist": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9},
        }
        # Update 10 rounds in bull market
        for _ in range(10):
            weight_manager.update_weights(
                regime="bull",
                analyst_posteriors=posteriors,
                realized_return=+0.02,
            )

        bull_weights = weight_manager.get_weights("bull")
        assert bull_weights["bull_specialist"] > bull_weights["bear_specialist"]

        # Bear and sideways weights must remain exactly as initialized (uniform 1/3)
        current_bear = weight_manager.get_weights("bear")
        current_sideways = weight_manager.get_weights("sideways")
        for aid in weight_manager.analyst_ids:
            assert current_bear[aid] == pytest.approx(initial_bear[aid], abs=1e-5)
            assert current_sideways[aid] == pytest.approx(initial_sideways[aid], abs=1e-5)

    def test_manager_alias_instantiation(self):
        """Verify RegimeMultiplicativeWeightManager alias conforms to same API."""
        mgr = RegimeMultiplicativeWeightManager()
        assert set(mgr.weights.keys()) == {"bull", "bear", "sideways"}
        assert len(mgr.analyst_ids) == 7


# ==============================================================================
# 3. Calibrated Signal Processing Outputs
# ==============================================================================
class TestCalibratedSignalProcessingOutputs:
    """Verifies Bayesian log-odds opinion pooling and calibrated price targets."""

    def test_bayesian_log_odds_bull_regime_elevation(self):
        """Prior L0(bull) = ln(0.6/0.4) ~ +0.405 elevates target price for BUY signal."""
        current_price = 100.0
        posteriors = {
            "a1": {"p_optimistic": 0.70, "p_cautious": 0.10, "expected_move_bps": 150.0},
            "a2": {"p_optimistic": 0.65, "p_cautious": 0.15, "expected_move_bps": 120.0},
        }
        target = calculate_bayesian_log_odds_target_price(
            current_price=current_price,
            action="buy",
            regime="bull",
            analyst_posteriors=posteriors,
        )
        assert target > current_price
        # Verify calibrated target eliminates hardcoded static 1.15 multiplier
        assert target != 115.00

    def test_bayesian_log_odds_bear_regime_reduction(self):
        """Prior L0(bear) = ln(0.4/0.6) ~ -0.405 lowers target price for SELL signal."""
        current_price = 50.0
        posteriors = {
            "a1": {"p_optimistic": 0.10, "p_cautious": 0.75, "expected_move_bps": -200.0},
            "a2": {"p_optimistic": 0.15, "p_cautious": 0.70, "expected_move_bps": -180.0},
        }
        target = calculate_bayesian_log_odds_target_price(
            current_price=current_price,
            action="sell",
            regime="bear",
            analyst_posteriors=posteriors,
        )
        assert target < current_price
        assert target != 47.50  # Eliminates static 0.95 multiplier

    def test_bayesian_log_odds_hold_action(self):
        """HOLD action retains current price exactly."""
        current_price = 75.50
        target = calculate_bayesian_log_odds_target_price(
            current_price=current_price,
            action="hold",
            regime="sideways",
            analyst_posteriors={"a1": {"p_optimistic": 0.4, "p_cautious": 0.4}},
        )
        assert target == 75.50

    def test_process_calibrated_signal_contract(self):
        """process_calibrated_signal returns comprehensive calibrated metrics."""
        posteriors = {
            "index_analyst_v2": {"p_optimistic": 0.65, "p_neutral": 0.25, "p_cautious": 0.10, "expected_move_bps": 100.0},
            "market_analyst_v2": {"p_optimistic": 0.60, "p_neutral": 0.30, "p_cautious": 0.10, "expected_move_bps": 90.0},
        }
        result = process_calibrated_signal(
            current_price=10.0,
            action="buy",
            regime="bull",
            analyst_posteriors=posteriors,
        )
        assert "target_price" in result
        assert "calibrated_prob" in result
        assert "calibrated_return" in result
        assert result["target_price"] > 10.0
        assert 0.5 < result["calibrated_prob"] < 1.0

    def test_fallback_when_posteriors_missing(self):
        """Fallback to standard price multiplier when analyst posteriors are missing."""
        target_buy = calculate_bayesian_log_odds_target_price(
            current_price=100.0,
            action="buy",
            regime="bull",
            analyst_posteriors={},
        )
        # Default fallback multiplier for A-share BUY is 1.15
        assert target_buy == 115.00

        target_sell = calculate_bayesian_log_odds_target_price(
            current_price=100.0,
            action="sell",
            regime="bull",
            analyst_posteriors={},
        )
        # Default fallback multiplier for A-share SELL is 0.95
        assert target_sell == 95.00


# ==============================================================================
# 4. Backward Compatibility & Helper Formatting
# ==============================================================================
class TestWeightCalculatorBackwardCompatibility:
    """Verifies calculate_report_weights and prompt formatting backward compatibility."""

    def test_calculate_report_weights_style_inference(self):
        """Infers 'long' style when fundamentals_report is present."""
        reports = {
            "fundamentals_report": "Solid balance sheet with low leverage.",
            "market_report": "RSI in neutral territory.",
        }
        weights = calculate_report_weights(reports)
        assert "fundamentals_report" in weights
        assert "market_report" in weights
        assert pytest.approx(sum(weights.values()), abs=1e-5) == 1.0

    def test_format_weighted_reports_prompt(self):
        """Formats analyst reports with explicit percentage weight tags."""
        reports = {"market_report": "Bull flag breakout."}
        weights = {"market_report": 1.0}
        prompt = format_weighted_reports_prompt(reports, weights)
        assert "[Important report]" in prompt
        assert "Bull flag breakout." in prompt


# ==============================================================================
# 5. Milestone 2 Extensions Coverage (w_min, scaled Brier, Log-OP, Signal API)
# ==============================================================================
class TestRegimeWeightCalculatorM2Extensions:
    """Verifies Milestone 2 enhancements across weight calculation and signal processing."""

    def test_brier_loss_scaled_mode(self):
        """When scaled=True, Brier loss is scaled by 1/3 into [0, 2/3]."""
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)
        bull_return = 0.02  # Target y = [1, 0, 0]

        # Perfect: standard 0.0, scaled 0.0
        perfect_bull = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        assert calc.compute_brier_loss(perfect_bull, bull_return, scaled=True) == 0.0
        assert calc.compute_brier_loss(perfect_bull, bull_return, scaled=False) == 0.0

        # Worst-case: standard 2.0, scaled 2.0 / 3.0
        worst_caut = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
        assert pytest.approx(calc.compute_brier_loss(worst_caut, bull_return, scaled=True), abs=1e-5) == 2.0 / 3.0
        assert calc.compute_brier_loss(worst_caut, bull_return, scaled=False) == 2.0

        # Uniform: standard 2/3, scaled 2/9
        uniform = {"p_optimistic": 1/3, "p_neutral": 1/3, "p_cautious": 1/3}
        assert pytest.approx(calc.compute_brier_loss(uniform, bull_return, scaled=True), abs=1e-5) == 2.0 / 9.0

    def test_mwu_weight_floor_w_min(self):
        """RegimeMultiplicativeWeightManager enforces w_min=0.03 floor under extreme penalties."""
        mgr = RegimeMultiplicativeWeightManager(
            analyst_ids=["good_analyst", "bad_analyst"],
            learning_rate=10.0,
            w_min=0.03,
        )
        posteriors = {
            "good_analyst": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0},
            "bad_analyst": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0},
        }

        # 5 consecutive steps of massive penalties on bad_analyst
        for _ in range(5):
            updated = mgr.update_weights("bull", posteriors, realized_return=0.03)

        assert updated["bad_analyst"] >= 0.025
        assert updated["bad_analyst"] <= 0.04
        assert updated["good_analyst"] > 0.96
        assert pytest.approx(sum(updated.values()), abs=1e-5) == 1.0

    def test_aggregate_posteriors_pooling_standalone_and_method(self):
        """Verifies Log-OP opinion pooling across analysts with consensus and custom weights."""
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=["a1", "a2"])
        posteriors = {
            "a1": {"p_optimistic": 0.8, "p_neutral": 0.15, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.7, "p_neutral": 0.20, "p_cautious": 0.10},
        }

        # Standalone function with uniform weights
        agg = aggregate_posteriors(posteriors)
        assert pytest.approx(sum(agg.values()), abs=1e-5) == 1.0
        assert agg["p_optimistic"] > agg["p_neutral"] > agg["p_cautious"]
        assert agg["p_optimistic"] > 0.70

        # Method on calculator
        method_agg = calc.aggregate_posteriors(posteriors, regime="bull")
        assert pytest.approx(sum(method_agg.values()), abs=1e-5) == 1.0
        assert method_agg["p_optimistic"] > 0.70

        # Standalone function with sequence input
        seq_agg = aggregate_posteriors([posteriors["a1"], posteriors["a2"]])
        assert pytest.approx(seq_agg["p_optimistic"], abs=1e-5) == agg["p_optimistic"]

        # Empty fallback
        empty_agg = aggregate_posteriors({})
        assert pytest.approx(empty_agg["p_optimistic"], abs=1e-5) == 1.0 / 3.0
        assert pytest.approx(empty_agg["p_neutral"], abs=1e-5) == 1.0 / 3.0
        assert pytest.approx(empty_agg["p_cautious"], abs=1e-5) == 1.0 / 3.0

    def test_process_calibrated_signal_confidence_and_risk(self):
        """process_calibrated_signal computes confidence=2*|p_agg-0.5| and risk_score=1-confidence."""
        posteriors = {
            "index_analyst_v2": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 150.0},
            "market_analyst_v2": {"p_optimistic": 0.80, "p_neutral": 0.15, "p_cautious": 0.05, "expected_move_bps": 120.0},
        }
        res = process_calibrated_signal(
            current_price=100.0,
            action="buy",
            regime="bull",
            analyst_posteriors=posteriors,
        )

        assert res["target_price"] > 100.0
        assert res["p_agg"] > 0.60
        expected_conf = min(1.0, max(0.0, round(2.0 * abs(res["p_agg"] - 0.5), 4)))
        assert pytest.approx(res["confidence"], abs=1e-4) == expected_conf
        assert pytest.approx(res["risk_score"], abs=1e-4) == round(1.0 - expected_conf, 4)
        assert pytest.approx(res["confidence"] + res["risk_score"], abs=1e-4) == 1.0
        assert "aggregated_log_odds" in res
        assert "weighted_move_bps" in res

    def test_process_calibrated_signal_fallbacks_china_and_us(self):
        """process_calibrated_signal falls back to legacy multipliers when posteriors are absent."""
        # China Buy (1.15x)
        res_cn_buy = process_calibrated_signal(current_price=100.0, action="buy", regime="bull", analyst_posteriors=None, is_china=True)
        assert res_cn_buy["target_price"] == 115.00
        assert res_cn_buy["confidence"] == 0.70
        assert res_cn_buy["risk_score"] == 0.30

        # China Sell (0.95x)
        res_cn_sell = process_calibrated_signal(current_price=100.0, action="sell", regime="bear", analyst_posteriors={}, is_china=True)
        assert res_cn_sell["target_price"] == 95.00
        assert res_cn_sell["confidence"] == 0.70

        # US Buy (1.12x)
        res_us_buy = process_calibrated_signal(current_price=100.0, action="buy", regime="bull", analyst_posteriors=None, is_china=False)
        assert res_us_buy["target_price"] == 112.00
        assert res_us_buy["confidence"] == 0.70

        # US Sell (0.92x)
        res_us_sell = process_calibrated_signal(current_price=100.0, action="sell", regime="bear", analyst_posteriors={}, is_china=False)
        assert res_us_sell["target_price"] == 92.00
        assert res_us_sell["confidence"] == 0.70

        # Hold
        res_hold = process_calibrated_signal(current_price=50.25, action="hold", regime="sideways", analyst_posteriors=None)
        assert res_hold["target_price"] == 50.25

    def test_module_exports_via_init(self):
        """Exports are correctly imported from package __init__ files."""
        import core.agents.utils as utils
        import tradingagents.graph.signal_processing as sp

        for name in [
            "DEFAULT_ANALYST_IDS",
            "REGIMES",
            "RegimeAdaptiveWeightCalculator",
            "RegimeMultiplicativeWeightManager",
            "aggregate_posteriors",
            "calculate_report_weights",
            "format_weighted_reports_prompt",
        ]:
            assert hasattr(utils, name)

        for name in [
            "SignalProcessor",
            "calculate_bayesian_log_odds_target_price",
            "compute_bayesian_log_odds_details",
            "process_calibrated_signal",
        ]:
            assert hasattr(sp, name)

