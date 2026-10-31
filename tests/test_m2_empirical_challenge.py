"""
Empirical Challenge & Stress-Test Suite for Milestone M2:
Multiplicative Weights Update, Multiclass Brier Loss, and Regime Isolation.

This test suite executes rigorous adversarial tests:
1. 100+ simulated sequential updates with calibrated vs miscalibrated vs noise forecasters.
2. Weight convergence, monotonicity, non-negativity, and strict sum-to-1 normalization (sum(w) == 1.0 +- 1e-6).
3. Extreme edge cases:
   - Learning rates eta in [0.0, 5.0]
   - Extreme returns +-500%, boundary returns +-0.5%
   - Identical predictions across all analysts
   - All-wrong predictions (loss = 2.0) and all-correct predictions (loss = 0.0)
   - Degenerate/malformed posteriors (zeros, unnormalized, string values)
4. Regime isolation: strict non-interference across bull, bear, and sideways weight vectors.
"""

import math
import random
from typing import Any, Dict, List
import pytest

from core.agents.utils.weight_calculator import (
    DEFAULT_ANALYST_IDS,
    REGIMES,
    RegimeAdaptiveWeightCalculator,
)


class TestEmpiricalSimulationMWU:
    """Empirical challenge: 100+ sequential updates, convergence, monotonicity, normalization."""

    def test_100_plus_sequential_updates_calibrated_vs_miscalibrated(self):
        """
        Run 150 simulated sequential updates in bull regime.
        - Forecaster A (Calibrated Bull): p_opt=0.85, p_neu=0.10, p_caut=0.05
        - Forecaster B (Neutral / Guessing): p_opt=0.33, p_neu=0.34, p_caut=0.33
        - Forecaster C (Miscalibrated Bear): p_opt=0.05, p_neu=0.10, p_caut=0.85
        Verify:
        - Weight convergence: Forecaster A weight approaches > 0.99
        - Monotonicity: w_A(t) >= w_A(t-1) at each step where Forecaster A incurs lower loss
        - Non-negativity: w_i >= 0.0 for all forecasters at all steps
        - Strict sum-to-1 normalization: abs(sum(w) - 1.0) <= 1e-6 at every single step
        """
        analyst_ids = ["calibrated_a", "neutral_b", "miscalibrated_c"]
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=analyst_ids, learning_rate=0.2)

        prev_w_a = calc.get_weights("bull")["calibrated_a"]
        prev_w_c = calc.get_weights("bull")["miscalibrated_c"]

        for step in range(1, 151):
            # Market return in bull regime: +1.0% to +3.0%
            realized_return = 0.01 + (step % 20) * 0.001

            posteriors = {
                "calibrated_a": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05},
                "neutral_b": {"p_optimistic": 0.33, "p_neutral": 0.34, "p_cautious": 0.33},
                "miscalibrated_c": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85},
            }

            w = calc.update_weights("bull", posteriors, realized_return)

            # 1. Strict sum-to-1 normalization: sum w_i == 1.0 +- 1e-6
            total_w = sum(w.values())
            assert abs(total_w - 1.0) <= 1e-6, f"Step {step}: sum(w) = {total_w} deviates from 1.0 by > 1e-6"

            # 2. Strict non-negativity
            for aid, weight in w.items():
                assert weight >= 0.0, f"Step {step}: negative weight {weight} for {aid}"
                assert not math.isnan(weight), f"Step {step}: NaN weight for {aid}"
                assert not math.isinf(weight), f"Step {step}: Inf weight for {aid}"

            # 3. Monotonicity: calibrated_a strictly increases, miscalibrated_c strictly decreases
            assert w["calibrated_a"] >= prev_w_a - 1e-9, f"Step {step}: w_a decreased from {prev_w_a} to {w['calibrated_a']}"
            assert w["miscalibrated_c"] <= prev_w_c + 1e-9, f"Step {step}: w_c increased from {prev_w_c} to {w['miscalibrated_c']}"
            assert w["calibrated_a"] > w["neutral_b"] > w["miscalibrated_c"]

            prev_w_a = w["calibrated_a"]
            prev_w_c = w["miscalibrated_c"]

        # 4. Weight convergence after 150 rounds
        final_w = calc.get_weights("bull")
        assert final_w["calibrated_a"] > 0.999, f"Calibrated forecaster failed to converge: {final_w['calibrated_a']}"
        assert final_w["miscalibrated_c"] < 1e-4, f"Miscalibrated forecaster failed to vanish: {final_w['miscalibrated_c']}"

    def test_multi_regime_alternating_150_updates(self):
        """
        Simulate 150 alternating rounds across regimes:
        - Rounds 0..49: Bull regime (+2%), BullForecaster is accurate.
        - Rounds 50..99: Bear regime (-2%), BearForecaster is accurate.
        - Rounds 100..149: Sideways regime (0%), SidewaysForecaster is accurate.
        Verify:
        - Regime weights adapt independently.
        - Each specialist forecaster dominates in its respective regime.
        - Strict normalization holds at every single update.
        """
        analyst_ids = ["bull_forecaster", "bear_forecaster", "sideways_forecaster"]
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=analyst_ids, learning_rate=0.25)

        for step in range(150):
            if step < 50:
                regime = "bull"
                ret = 0.02
            elif step < 100:
                regime = "bear"
                ret = -0.02
            else:
                regime = "sideways"
                ret = 0.0005

            posteriors = {
                "bull_forecaster": {"p_optimistic": 0.80, "p_neutral": 0.15, "p_cautious": 0.05},
                "bear_forecaster": {"p_optimistic": 0.05, "p_neutral": 0.15, "p_cautious": 0.80},
                "sideways_forecaster": {"p_optimistic": 0.10, "p_neutral": 0.80, "p_cautious": 0.10},
            }

            w = calc.update_weights(regime, posteriors, ret)
            assert abs(sum(w.values()) - 1.0) <= 1e-6
            for v in w.values():
                assert v >= 0.0

        # Verify specialization
        bull_w = calc.get_weights("bull")
        bear_w = calc.get_weights("bear")
        sideways_w = calc.get_weights("sideways")

        assert bull_w["bull_forecaster"] > 0.95
        assert bear_w["bear_forecaster"] > 0.95
        assert sideways_w["sideways_forecaster"] > 0.95

    def test_stochastic_noisy_simulation_200_rounds(self):
        """
        Stochastic simulation: 200 rounds with random returns and calibrated vs noisy forecasters.
        Calibrated forecaster has 80% accuracy predicting direction.
        Noisy forecaster outputs uniform random noise.
        Adversarial forecaster has only 20% accuracy.
        Verify:
        - Calibrated forecaster weight > Noisy forecaster weight > Adversarial forecaster weight.
        - Strict sum-to-1 normalization at all 200 steps.
        """
        random.seed(42)
        analyst_ids = ["calibrated", "noisy", "adversarial"]
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=analyst_ids, learning_rate=0.15)

        for step in range(200):
            # Market return sampled with slight positive bias
            ret = random.gauss(0.002, 0.015)

            # Determine true outcome
            if ret > 0.005:
                true_idx = 0  # opt
            elif ret < -0.005:
                true_idx = 2  # caut
            else:
                true_idx = 1  # neu

            # Calibrated forecaster: 80% chance of high probability on true outcome
            if random.random() < 0.80:
                p_cal = [0.1, 0.1, 0.1]
                p_cal[true_idx] = 0.8
            else:
                p_cal = [0.33, 0.33, 0.34]

            # Noisy forecaster: Dirichlet(1, 1, 1) random
            r1, r2, r3 = random.expovariate(1), random.expovariate(1), random.expovariate(1)
            tot_r = r1 + r2 + r3
            p_noisy = [r1 / tot_r, r2 / tot_r, r3 / tot_r]

            # Adversarial forecaster: 80% chance of predicting wrong outcome
            p_adv = [0.1, 0.1, 0.1]
            wrong_idx = (true_idx + 1) % 3
            p_adv[wrong_idx] = 0.8

            posteriors = {
                "calibrated": {"p_optimistic": p_cal[0], "p_neutral": p_cal[1], "p_cautious": p_cal[2]},
                "noisy": {"p_optimistic": p_noisy[0], "p_neutral": p_noisy[1], "p_cautious": p_noisy[2]},
                "adversarial": {"p_optimistic": p_adv[0], "p_neutral": p_adv[1], "p_cautious": p_adv[2]},
            }

            w = calc.update_weights("bull" if ret > 0 else "bear", posteriors, ret)
            assert abs(sum(w.values()) - 1.0) <= 1e-6
            for v in w.values():
                assert v >= 0.0

        # In both bull and bear, calibrated should decisively beat adversarial
        for reg in ["bull", "bear"]:
            w = calc.get_weights(reg)
            assert w["calibrated"] > w["noisy"] > w["adversarial"]
            assert abs(sum(w.values()) - 1.0) <= 1e-6


class TestExtremeEdgeCases:
    """Stress tests on learning rates, returns, boundary conditions, and degenerate inputs."""

    @pytest.mark.parametrize("eta", [0.0, 0.001, 0.05, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0])
    def test_learning_rate_spectrum(self, eta: float):
        """Verify MWU across the full spectrum of learning rates eta in [0.0, 5.0]."""
        analyst_ids = ["a1", "a2"]
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=analyst_ids, learning_rate=eta)

        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.1, "p_neutral": 0.05, "p_cautious": 0.85},
        }
        ret = 0.02  # Bull outcome

        w = calc.update_weights("bull", posteriors, ret)

        # Strict sum-to-1 normalization
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        assert w["a1"] >= 0.0 and w["a2"] >= 0.0

        if eta == 0.0:
            # When eta == 0.0, weights must be strictly unchanged
            assert pytest.approx(w["a1"], abs=1e-6) == 0.5
            assert pytest.approx(w["a2"], abs=1e-6) == 0.5
        else:
            # Accurate analyst a1 must strictly gain weight over inaccurate a2
            assert w["a1"] > w["a2"]

    @pytest.mark.parametrize("extreme_return", [-5.0, -1.0, -0.5, 0.5, 1.0, 5.0, 50.0])
    def test_extreme_returns_pm_500_percent(self, extreme_return: float):
        """Stress-test returns +-500% (and up to +-5000%)."""
        calc = RegimeAdaptiveWeightCalculator()
        posteriors = {
            "index_analyst_v2": {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1},
            "market_analyst_v2": {"p_optimistic": 0.1, "p_neutral": 0.2, "p_cautious": 0.7},
        }

        w = calc.update_weights("bull" if extreme_return > 0 else "bear", posteriors, extreme_return)
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        for weight in w.values():
            assert weight >= 0.0
            assert not math.isnan(weight)
            assert not math.isinf(weight)

    def test_return_threshold_exact_boundaries(self):
        """
        Test exact deadband boundaries:
        return_threshold = 0.005 (50 bps)
        - ret = 0.005 -> Neutral (since > 0.005 is false)
        - ret = 0.0050001 -> Bull (since > 0.005 is true)
        - ret = -0.005 -> Neutral (since < -0.005 is false)
        - ret = -0.0050001 -> Bear (since < -0.005 is true)
        - ret = 0.0 -> Neutral
        """
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)
        post = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}

        # ret = 0.005 -> target is neutral [0, 1, 0]. Loss for [1, 0, 0] = (1-0)^2 + (0-1)^2 + 0 = 2.0
        assert pytest.approx(calc.compute_brier_loss(post, 0.005), abs=1e-5) == 2.0

        # ret = 0.0050001 -> target is bull [1, 0, 0]. Loss for [1, 0, 0] = 0.0
        assert pytest.approx(calc.compute_brier_loss(post, 0.0050001), abs=1e-5) == 0.0

        # ret = -0.005 -> target is neutral [0, 1, 0]. Loss for [1, 0, 0] = 2.0
        assert pytest.approx(calc.compute_brier_loss(post, -0.005), abs=1e-5) == 2.0

        # ret = -0.0050001 -> target is bear [0, 0, 1]. Loss for [1, 0, 0] = 2.0
        assert pytest.approx(calc.compute_brier_loss(post, -0.0050001), abs=1e-5) == 2.0

        # ret = 0.0 -> neutral [0, 1, 0]
        neut_post = {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0}
        assert pytest.approx(calc.compute_brier_loss(neut_post, 0.0), abs=1e-5) == 0.0

    def test_identical_predictions_preserves_uniform_weights(self):
        """When all analysts output identical predictions, weights must remain identical."""
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.5)
        identical_posterior = {"p_optimistic": 0.6, "p_neutral": 0.25, "p_cautious": 0.15}
        posteriors = {aid: dict(identical_posterior) for aid in calc.analyst_ids}

        w = calc.update_weights("bull", posteriors, 0.02)
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        expected_uniform = 1.0 / len(calc.analyst_ids)
        for aid, weight in w.items():
            assert pytest.approx(weight, abs=1e-6) == expected_uniform

    def test_all_wrong_predictions_maximum_loss(self):
        """
        When all analysts predict bull with 100% confidence but market experiences a crash (-10%),
        multiclass Brier loss for all analysts is 2.0.
        All weights are multiplied by exp(-lr * 2.0).
        After normalization, all weights must remain strictly equal and sum to 1.0 +- 1e-6.
        """
        calc = RegimeAdaptiveWeightCalculator(learning_rate=1.0)
        wrong_post = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        posteriors = {aid: dict(wrong_post) for aid in calc.analyst_ids}

        # Check raw loss is exactly 2.0
        assert calc.compute_brier_loss(wrong_post, -0.10) == 2.0

        w = calc.update_weights("bear", posteriors, -0.10)
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        expected_uniform = 1.0 / len(calc.analyst_ids)
        for aid, weight in w.items():
            assert pytest.approx(weight, abs=1e-6) == expected_uniform

    def test_all_correct_predictions_zero_loss(self):
        """When all analysts predict bull with 100% confidence and return is +5%, loss is 0.0."""
        calc = RegimeAdaptiveWeightCalculator(learning_rate=1.0)
        correct_post = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        posteriors = {aid: dict(correct_post) for aid in calc.analyst_ids}

        assert calc.compute_brier_loss(correct_post, 0.05) == 0.0

        w = calc.update_weights("bull", posteriors, 0.05)
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        expected_uniform = 1.0 / len(calc.analyst_ids)
        for aid, weight in w.items():
            assert pytest.approx(weight, abs=1e-6) == expected_uniform

    def test_degenerate_and_malformed_posteriors(self):
        """Stress-test degenerate posteriors: all zeros, unnormalized, negative, and strings."""
        calc = RegimeAdaptiveWeightCalculator()

        # All zeros -> fallback to uniform [1/3, 1/3, 1/3]
        zero_post = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 0.0}
        loss_zero = calc.compute_brier_loss(zero_post, 0.02)
        # target [1,0,0], p=[1/3, 1/3, 1/3] -> (1/3-1)^2 + 1/9 + 1/9 = 4/9 + 2/9 = 6/9 = 0.66667
        assert pytest.approx(loss_zero, abs=1e-4) == 2.0 / 3.0

        # String-typed floats
        str_post = {"p_optimistic": "0.8", "p_neutral": "0.1", "p_cautious": "0.1"}
        loss_str = calc.compute_brier_loss(str_post, 0.02)
        assert pytest.approx(loss_str, abs=1e-4) == (0.8 - 1)**2 + 0.1**2 + 0.1**2

        # Completely empty dict
        empty_post = {}
        loss_empty = calc.compute_brier_loss(empty_post, 0.02)
        assert 0.0 <= loss_empty <= 2.0

        # Update weights with degenerate inputs does not raise exception
        posteriors = {
            "index_analyst_v2": zero_post,
            "sector_analyst_v2": str_post,
            "market_analyst_v2": empty_post,
        }
        w = calc.update_weights("bull", posteriors, 0.02)
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        for weight in w.values():
            assert weight >= 0.0


class TestRegimeIsolationEmpirical:
    """Rigorous empirical validation of regime isolation."""

    def test_updating_bull_strictly_leaves_bear_and_sideways_untouched(self):
        """
        Run 100 sequential updates in bull regime.
        Verify bear and sideways weights remain bit-for-bit identical to their pre-update state.
        """
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.4)
        bear_initial = {k: float(v) for k, v in calc.get_weights("bear").items()}
        sideways_initial = {k: float(v) for k, v in calc.get_weights("sideways").items()}

        for step in range(100):
            posteriors = {
                "market_analyst_v2": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
                "news_analyst_v2": {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8},
            }
            calc.update_weights("bull", posteriors, 0.03)

            # Check after EVERY single step
            bear_current = calc.get_weights("bear")
            sideways_current = calc.get_weights("sideways")

            assert bear_current == bear_initial, f"Step {step}: bear weights corrupted during bull update!"
            assert sideways_current == sideways_initial, f"Step {step}: sideways weights corrupted during bull update!"

    def test_updating_bear_strictly_leaves_bull_and_sideways_untouched(self):
        """
        Run 100 sequential updates in bear regime.
        Verify bull and sideways weights remain strictly untouched.
        """
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.4)
        bull_initial = {k: float(v) for k, v in calc.get_weights("bull").items()}
        sideways_initial = {k: float(v) for k, v in calc.get_weights("sideways").items()}

        for step in range(100):
            posteriors = {
                "market_analyst_v2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90},
                "news_analyst_v2": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1},
            }
            calc.update_weights("bear", posteriors, -0.03)

            assert calc.get_weights("bull") == bull_initial, f"Step {step}: bull weights corrupted during bear update!"
            assert calc.get_weights("sideways") == sideways_initial, f"Step {step}: sideways weights corrupted during bear update!"

    def test_updating_sideways_strictly_leaves_bull_and_bear_untouched(self):
        """
        Run 100 sequential updates in sideways regime.
        Verify bull and bear weights remain strictly untouched.
        """
        calc = RegimeAdaptiveWeightCalculator(learning_rate=0.4)
        bull_initial = {k: float(v) for k, v in calc.get_weights("bull").items()}
        bear_initial = {k: float(v) for k, v in calc.get_weights("bear").items()}

        for step in range(100):
            posteriors = {
                "sector_analyst_v2": {"p_optimistic": 0.1, "p_neutral": 0.8, "p_cautious": 0.1},
            }
            calc.update_weights("sideways", posteriors, 0.001)

            assert calc.get_weights("bull") == bull_initial, f"Step {step}: bull weights corrupted during sideways update!"
            assert calc.get_weights("bear") == bear_initial, f"Step {step}: bear weights corrupted during sideways update!"

    def test_case_variant_regime_names_isolation(self):
        """
        Verify case insensitivity and whitespace handling:
        'BULL', '  bull  ' update 'bull' without contaminating bear or sideways.
        """
        calc = RegimeAdaptiveWeightCalculator()
        bear_initial = dict(calc.get_weights("bear"))
        sideways_initial = dict(calc.get_weights("sideways"))

        calc.update_weights(
            "  BULL  ",
            {
                "market_analyst_v2": {"p_optimistic": 0.9, "p_neutral": 0.1, "p_cautious": 0.0},
                "news_analyst_v2": {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8},
            },
            0.02,
        )
        assert calc.get_weights("bear") == bear_initial
        assert calc.get_weights("sideways") == sideways_initial
        assert calc.get_weights("bull")["market_analyst_v2"] > calc.get_weights("bull")["news_analyst_v2"]

    def test_partial_analyst_update_sleeping_expert_dynamics(self):
        """
        Adversarial test on sleeping / absent analysts:
        When only a subset of analysts report in posteriors, non-reporting analysts
        retain their unweighted raw mass (effective multiplier 1.0, loss=0.0).
        Verify:
        - Participating accurate analyst beats participating inaccurate analyst.
        - Non-participating analysts maintain strict non-negativity.
        - Sum strictly normalizes to 1.0 +- 1e-6.
        - Active analyst sub-selection via get_weights(regime, active_analysts) correctly
          normalizes active weights only.
        """
        calc = RegimeAdaptiveWeightCalculator()
        posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},  # loss = 0.015
            "news_analyst_v2": {"p_optimistic": 0.1, "p_neutral": 0.10, "p_cautious": 0.80},    # loss = 1.46
        }
        w = calc.update_weights("bull", posteriors, 0.02)

        # 1. Normalization
        assert abs(sum(w.values()) - 1.0) <= 1e-6
        # 2. Ranking among participating analysts: accurate > inaccurate
        assert w["market_analyst_v2"] > w["news_analyst_v2"]
        # 3. Sub-selection across active analysts only
        active_w = calc.get_weights("bull", active_analysts=["market_analyst_v2", "news_analyst_v2"])
        assert abs(sum(active_w.values()) - 1.0) <= 1e-6
        assert active_w["market_analyst_v2"] > active_w["news_analyst_v2"]
        assert active_w["market_analyst_v2"] > 0.55

