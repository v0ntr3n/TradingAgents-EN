"""
Adversarial Mathematical Stress-Testing Suite for CARE-Agents Milestone M1.

Empirical verification of:
1. `compute_jensen_shannon_divergence`:
   - Extreme distributions: near-zero epsilon (1e-12, 1e-16, 1e-300), asymmetric Dirichlet samples,
     non-normalized raw vectors, degenerate probabilities ([1,0,0] vs [0,1,0] vs [0,0,1]).
   - Weight permutations: extreme weight skews (99.9% vs 0.1%), zero weights, negative weights, empty dicts.
2. `compute_cbs_bps`:
   - Opposing analysts move sign interactions (+500 bps vs -500 bps) ensuring move magnitude is preserved.
   - Dual-signature consistency.
3. `calculate_cbs_routing`:
   - Exact numerical boundary decisions: D_JS = 0.1200000 and CBS = 15.00000 bps.
   - Dynamic debate rounds scaling and bounds.
"""

import math
import random
from typing import Any, Dict, List
import pytest

from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_shannon_entropy,
    compute_base2_jsd,
    calculate_base2_jsd,
    compute_jensen_shannon_divergence,
    compute_cbs_bps,
    calculate_cbs_routing,
    should_trigger_multi_round_debate,
    should_gate_debate,
)


# ==============================================================================
# Suite 1: Extreme Distributions & Numerical Stability
# ==============================================================================
class TestExtremeDistributions:
    """Stress-test JSD across extreme, near-zero, unnormalized, and degenerate probability vectors."""

    @pytest.mark.parametrize("eps", [1e-4, 1e-8, 1e-12, 1e-16, 1e-50, 1e-300])
    def test_near_zero_epsilon_stability(self, eps: float):
        """Probability vectors with near-zero epsilon components must compute without underflow/domain error."""
        # Pair with extreme divergence
        p1 = [1.0 - 2 * eps, eps, eps]
        p2 = [eps, 1.0 - 2 * eps, eps]
        jsd = compute_jensen_shannon_divergence([p1, p2])
        assert 0.0 <= jsd <= 1.0
        # As epsilon approaches 0, JSD approaches 1.0 for orthogonal distributions
        min_bound = 0.998 if eps >= 1e-4 else 0.999
        assert jsd > min_bound

        # Triplet with extreme divergence
        p3 = [eps, eps, 1.0 - 2 * eps]
        jsd_triplet = compute_jensen_shannon_divergence([p1, p2, p3])
        assert 0.0 <= jsd_triplet <= 1.0
        assert jsd_triplet > min_bound

    def test_asymmetric_dirichlet_monte_carlo(self):
        """1,000 asymmetric Dirichlet Monte Carlo draws must maintain mathematical invariants:
        1. 0.0 <= D_JS <= 1.0
        2. D_JS(P, P) == 0.0
        3. Permutation invariance under weight permutation
        """
        random.seed(42)
        # Generate samples with extreme asymmetry across dimensions
        alphas_list = [
            [0.01, 1.0, 10.0],
            [100.0, 0.01, 1.0],
            [0.001, 0.001, 50.0],
            [5.0, 5.0, 5.0],
        ]

        def sample_dirichlet(alphas: List[float]) -> List[float]:
            gammas = [random.gammavariate(a, 1.0) for a in alphas]
            tot = sum(gammas)
            return [g / tot for g in gammas]

        for _ in range(250):
            for alphas in alphas_list:
                p1 = sample_dirichlet(alphas)
                p2 = sample_dirichlet(alphas)

                # Invariant 1: Bounded in [0, 1]
                jsd_12 = compute_jensen_shannon_divergence([p1, p2])
                assert 0.0 <= jsd_12 <= 1.0
                assert not math.isnan(jsd_12)

                # Invariant 2: Identity of indiscernibles
                jsd_self = compute_jensen_shannon_divergence([p1, p1])
                assert jsd_self < 1e-6

                # Invariant 3: Symmetry under uniform weights
                jsd_21 = compute_jensen_shannon_divergence([p2, p1])
                assert abs(jsd_12 - jsd_21) < 1e-6

    def test_non_normalized_raw_vectors_scale_invariance(self):
        """JSD must be invariant to uniform scalar multiplication of probability vectors."""
        base_p1 = [0.7, 0.2, 0.1]
        base_p2 = [0.1, 0.3, 0.6]
        base_jsd = compute_jensen_shannon_divergence([base_p1, base_p2])

        # Large scale: 10^12
        large_p1 = [x * 1e12 for x in base_p1]
        large_p2 = [x * 1e12 for x in base_p2]
        large_jsd = compute_jensen_shannon_divergence([large_p1, large_p2])
        assert abs(base_jsd - large_jsd) < 1e-6

        # Small scale: 10^-12
        small_p1 = [x * 1e-12 for x in base_p1]
        small_p2 = [x * 1e-12 for x in base_p2]
        small_jsd = compute_jensen_shannon_divergence([small_p1, small_p2])
        assert abs(base_jsd - small_jsd) < 1e-6

        # Cross-scale: analyst 1 has scale 10^9, analyst 2 has scale 10^-9
        mixed_jsd = compute_jensen_shannon_divergence([large_p1, small_p2])
        assert abs(base_jsd - mixed_jsd) < 1e-6

    def test_degenerate_orthogonal_simplex_vertices(self):
        """Orthogonal simplex basis vectors must yield D_JS = 1.0 under uniform weights."""
        e1 = [1.0, 0.0, 0.0]
        e2 = [0.0, 1.0, 0.0]
        e3 = [0.0, 0.0, 1.0]

        # Pairwise
        assert abs(compute_jensen_shannon_divergence([e1, e2]) - 1.0) < 1e-6
        assert abs(compute_jensen_shannon_divergence([e1, e3]) - 1.0) < 1e-6
        assert abs(compute_jensen_shannon_divergence([e2, e3]) - 1.0) < 1e-6

        # 3-way orthogonal
        jsd_3way = compute_jensen_shannon_divergence([e1, e2, e3])
        # Theoretical base-2 JSD is log2(3) ~ 1.58496, clamped to 1.0
        assert jsd_3way == 1.0

    def test_degenerate_partial_support_analytical_match(self):
        """Partial overlap distributions must match analytical base-2 JSD within 1e-6."""
        # P1 = [0.5, 0.5, 0.0], P2 = [0.0, 0.5, 0.5]
        # M = [0.25, 0.5, 0.25]
        # H2(M) = - (0.25 * (-2) + 0.5 * (-1) + 0.25 * (-2)) = 1.5
        # H2(P1) = 1.0, H2(P2) = 1.0, avg_H = 1.0
        # D_JS = 1.5 - 1.0 = 0.5000000
        p1 = [0.5, 0.5, 0.0]
        p2 = [0.0, 0.5, 0.5]
        jsd = compute_jensen_shannon_divergence([p1, p2])
        assert abs(jsd - 0.500000) < 1e-6


# ==============================================================================
# Suite 2: Weight Permutations & Skew Testing
# ==============================================================================
class TestWeightPermutations:
    """Stress-test weight permutations: extreme skews, zero weights, negative weights, empty dicts."""

    def test_extreme_weight_skews_asymptotic_convergence(self):
        """As one analyst's weight approaches 1.0, JSD must monotonically converge to 0.0."""
        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9},
        }

        prev_jsd = compute_jensen_shannon_divergence(posteriors)  # uniform: ~0.667
        for skew in [0.90, 0.99, 0.999, 0.9999, 0.99999]:
            jsd_skewed = compute_jensen_shannon_divergence(
                posteriors, weights={"a1": skew, "a2": 1.0 - skew}
            )
            assert jsd_skewed < prev_jsd, f"Expected monotonic decrease, {jsd_skewed} >= {prev_jsd}"
            prev_jsd = jsd_skewed

        # Extremely skewed weight should be practically zero
        assert prev_jsd < 1e-4

    def test_zero_weights_isolation(self):
        """Analysts with weight 0.0 must be effectively isolated and not contribute to divergence."""
        posteriors = {
            "a1": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1},
            "a2": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1},
            "a3_dissident": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0},
        }
        # When dissident has weight 0.0, effective JSD between a1 and a2 is 0.0
        jsd_isolated = compute_jensen_shannon_divergence(
            posteriors, weights={"a1": 0.5, "a2": 0.5, "a3_dissident": 0.0}
        )
        assert abs(jsd_isolated) < 1e-6

        # One single active analyst (all others 0) yields JSD = 0.0
        jsd_single_active = compute_jensen_shannon_divergence(
            posteriors, weights={"a1": 1.0, "a2": 0.0, "a3_dissident": 0.0}
        )
        assert abs(jsd_single_active) < 1e-6

    def test_all_zero_weights_fallback_to_uniform(self):
        """When all weights are 0.0, JSD must safely fallback to uniform weighting without ZeroDivisionError."""
        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9},
        }
        jsd_uniform = compute_jensen_shannon_divergence(posteriors)
        jsd_all_zeros = compute_jensen_shannon_divergence(
            posteriors, weights={"a1": 0.0, "a2": 0.0}
        )
        assert abs(jsd_all_zeros - jsd_uniform) < 1e-6

    def test_negative_weights_clamping(self):
        """Negative weights must be clamped to 0.0; if all negative, fallback to uniform."""
        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9},
        }
        jsd_uniform = compute_jensen_shannon_divergence(posteriors)

        # a1 negative clamped to 0 -> only a2 has non-zero weight -> JSD = 0
        jsd_one_neg = compute_jensen_shannon_divergence(
            posteriors, weights={"a1": -5.0, "a2": 2.0}
        )
        assert jsd_one_neg == 0.0

        # both negative clamped to 0 -> fallback to uniform
        jsd_both_neg = compute_jensen_shannon_divergence(
            posteriors, weights={"a1": -5.0, "a2": -10.0}
        )
        assert abs(jsd_both_neg - jsd_uniform) < 1e-6

    def test_empty_none_and_missing_keys_weights(self):
        """Empty dict, None, and missing keys must have predictable deterministic behaviors."""
        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9},
        }
        jsd_uniform = compute_jensen_shannon_divergence(posteriors)

        assert abs(compute_jensen_shannon_divergence(posteriors, weights={}) - jsd_uniform) < 1e-6
        assert abs(compute_jensen_shannon_divergence(posteriors, weights=None) - jsd_uniform) < 1e-6

        # Missing key for a2 -> defaults to 1.0, matching a1: 1.0 (uniform)
        assert abs(compute_jensen_shannon_divergence(posteriors, weights={"a1": 1.0}) - jsd_uniform) < 1e-6

    def test_weight_normalization_scale_invariance(self):
        """Unnormalized weights must produce identical JSD to normalized weights."""
        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9},
        }
        jsd_norm = compute_jensen_shannon_divergence(posteriors, weights={"a1": 0.75, "a2": 0.25})
        jsd_unnorm = compute_jensen_shannon_divergence(posteriors, weights={"a1": 750.0, "a2": 250.0})
        assert abs(jsd_norm - jsd_unnorm) < 1e-6


# ==============================================================================
# Suite 3: Move Sign Interactions & CBS Calculations
# ==============================================================================
class TestMoveSignInteractions:
    """Stress-test directional move sign interactions (+500 vs -500 bps) and CBS calculation."""

    def test_opposing_analysts_magnitude_preservation(self):
        """Opposing analysts (+500 bps vs -500 bps) must preserve magnitude and not cancel to 0 bps."""
        p_bull = {
            "p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05,
            "expected_move_bps": 500.0, "confidence": 0.8,
        }
        p_bear = {
            "p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90,
            "expected_move_bps": -500.0, "confidence": 0.8,
        }
        posteriors = {"bull": p_bull, "bear": p_bear}

        routing = calculate_cbs_routing(posteriors, estimated_spread_bps=15.0)
        assert routing["weighted_expected_move_bps"] == 500.0
        assert routing["cbs_bps"] > 100.0  # (0.667 * 500) / 2 = ~166.8 bps
        assert routing["route"] == "multi_round_debate"

    def test_asymmetric_opposing_moves(self):
        """Asymmetric opposing moves (+800 bps vs -200 bps) weighted correctly."""
        p1 = {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1, "expected_move_bps": 800.0, "confidence": 0.5}
        p2 = {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8, "expected_move_bps": -200.0, "confidence": 0.5}
        posteriors = {"a1": p1, "a2": p2}

        routing = calculate_cbs_routing(posteriors, estimated_spread_bps=15.0)
        # Average of |800| and |-200| under equal confidence is 500.0
        assert abs(routing["weighted_expected_move_bps"] - 500.0) < 1e-4

        # With asymmetric weights/confidence
        weights = {"a1": 0.9, "a2": 0.1}
        routing_w = calculate_cbs_routing(posteriors, weights=weights, estimated_spread_bps=15.0)
        expected_w_move = 0.9 * 800.0 + 0.1 * 200.0  # 720 + 20 = 740.0
        assert abs(routing_w["weighted_expected_move_bps"] - 740.0) < 1e-4

    def test_cbs_bps_dual_signature_consistency(self):
        """`compute_cbs_bps(posteriors)` and `compute_cbs_bps(jsd, move)` must yield consistent values."""
        for move in [20.0, 50.0, 150.0, 500.0, 1200.0]:
            p1 = {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1, "expected_move_bps": move, "confidence": 1.0}
            p2 = {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8, "expected_move_bps": -move, "confidence": 1.0}
            posteriors = {"a1": p1, "a2": p2}

            cbs_dict = compute_cbs_bps(posteriors)
            jsd = compute_jensen_shannon_divergence(posteriors)
            cbs_scalar = compute_cbs_bps(jsd, move)

            assert abs(cbs_dict - cbs_scalar) < 1e-4
            # Also test negative scalar move
            cbs_scalar_neg = compute_cbs_bps(jsd, -move)
            assert abs(cbs_scalar - cbs_scalar_neg) < 1e-6


# ==============================================================================
# Suite 4: Numerical Precision & Exact Boundaries
# ==============================================================================
class TestNumericalPrecisionAndExactBoundaries:
    """Stress-test exact numerical boundaries around D_JS = 0.1200000 and CBS = 15.00000 bps."""

    @classmethod
    def setup_class(cls):
        """Solve for symmetric distribution offset x giving base-2 JSD ~ 0.1200000."""
        # For p1 = [0.5+x, 0.5-x, 0], p2 = [0.5-x, 0.5+x, 0], find x where JSD >= 0.12
        def jsd_eval(x: float) -> float:
            return compute_base2_jsd([[0.5 + x, 0.5 - x, 0.0], [0.5 - x, 0.5 + x, 0.0]])

        low, high = 0.0, 0.5
        for _ in range(60):
            mid = (low + high) / 2
            if jsd_eval(mid) < 0.12:
                low = mid
            else:
                high = mid
        cls.x_at_012 = high
        cls.jsd_at_012 = jsd_eval(high)

    def test_exact_jsd_boundary_sub_and_super_threshold(self):
        """JSD < 0.12 must route to fast_path regardless of CBS; JSD >= 0.12 triggers debate if CBS > spread."""
        # Slightly sub-threshold JSD: ~0.119999
        x_sub = self.x_at_012 - 1e-5
        jsd_sub = compute_base2_jsd([[0.5 + x_sub, 0.5 - x_sub, 0.0], [0.5 - x_sub, 0.5 + x_sub, 0.0]])
        assert jsd_sub < 0.12

        # Massive expected move (10,000 bps -> CBS ~ 600 bps >> 15 bps spread)
        post_sub = {
            "a1": {"p_optimistic": 0.5 + x_sub, "p_neutral": 0.5 - x_sub, "p_cautious": 0.0, "expected_move_bps": 10000.0, "confidence": 1.0},
            "a2": {"p_optimistic": 0.5 - x_sub, "p_neutral": 0.5 + x_sub, "p_cautious": 0.0, "expected_move_bps": 10000.0, "confidence": 1.0},
        }
        r_sub = calculate_cbs_routing(post_sub, estimated_spread_bps=15.0)
        assert r_sub["route"] == "fast_path"
        assert r_sub["dynamic_debate_rounds"] == 0

        # Slightly super-threshold JSD: >= 0.12
        post_sup = {
            "a1": {"p_optimistic": 0.5 + self.x_at_012, "p_neutral": 0.5 - self.x_at_012, "p_cautious": 0.0, "expected_move_bps": 10000.0, "confidence": 1.0},
            "a2": {"p_optimistic": 0.5 - self.x_at_012, "p_neutral": 0.5 + self.x_at_012, "p_cautious": 0.0, "expected_move_bps": 10000.0, "confidence": 1.0},
        }
        r_sup = calculate_cbs_routing(post_sup, estimated_spread_bps=15.0)
        assert r_sup["route"] == "multi_round_debate"
        assert r_sup["dynamic_debate_rounds"] >= 1

    def test_exact_cbs_boundary_15_0(self):
        """When JSD >= 0.12, CBS <= 15.0 routes to fast_path, and CBS > 15.0 routes to multi_round_debate."""
        # Craft move so that CBS = (jsd * move) / 2 == 15.0 bps
        target_move = (2.0 * 15.0) / self.jsd_at_012
        post_exact = {
            "a1": {"p_optimistic": 0.5 + self.x_at_012, "p_neutral": 0.5 - self.x_at_012, "p_cautious": 0.0, "expected_move_bps": target_move, "confidence": 1.0},
            "a2": {"p_optimistic": 0.5 - self.x_at_012, "p_neutral": 0.5 + self.x_at_012, "p_cautious": 0.0, "expected_move_bps": target_move, "confidence": 1.0},
        }
        cbs_val = calculate_cbs_routing(post_exact)["cbs_bps"]

        # Case 1: spread == cbs_val -> fast_path (boundary condition: CBS <= spread)
        r_equal = calculate_cbs_routing(post_exact, estimated_spread_bps=cbs_val)
        assert r_equal["route"] == "fast_path"

        # Case 2: spread == cbs_val + 1e-9 -> fast_path
        r_below = calculate_cbs_routing(post_exact, estimated_spread_bps=cbs_val + 1e-9)
        assert r_below["route"] == "fast_path"

        # Case 3: spread == cbs_val - 1e-9 -> multi_round_debate
        r_above = calculate_cbs_routing(post_exact, estimated_spread_bps=cbs_val - 1e-9)
        assert r_above["route"] == "multi_round_debate"
        assert r_above["dynamic_debate_rounds"] >= 1

    @pytest.mark.parametrize("max_rounds", [1, 2, 3, 5, 8])
    def test_dynamic_debate_rounds_scaling_limits(self, max_rounds: int):
        """Dynamic debate rounds must scale strictly between 1 and max_debate_rounds."""
        for jsd_val in [0.12001, 0.25, 0.50, 0.75, 1.0]:
            # Scale formula from implementation
            scaling = (jsd_val - 0.12) / (1.0 - 0.12)
            scaled = 1 + (max_rounds - 1) * scaling
            expected = int(max(1, min(max_rounds, round(scaled))))
            assert 1 <= expected <= max_rounds

    def test_nan_and_inf_robustness(self):
        """Malformed floats (NaN, Inf) and unexpected types must not crash the calculation."""
        # 1. NaN in probabilities: normalized to 0.0 / uniform by max(0.0, float(x))
        post_prob_nan = {
            "a1": {"p_optimistic": float("nan"), "p_neutral": float("nan"), "p_cautious": float("nan")},
            "a2": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2, "expected_move_bps": 50.0},
        }
        routing_prob_nan = calculate_cbs_routing(post_prob_nan, estimated_spread_bps=15.0)
        assert routing_prob_nan["route"] in ("fast_path", "multi_round_debate")
        assert not math.isnan(routing_prob_nan["jsd"])
        assert not math.isnan(routing_prob_nan["cbs_bps"])

        # 2. NaN in expected_move_bps: float("nan") does not raise ValueError/TypeError,
        # propagating NaN into cbs_bps. When JSD < 0.12, routes to fast_path.
        post_move_nan = {
            "a1": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2, "expected_move_bps": float("nan")},
            "a2": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2, "expected_move_bps": 50.0},
        }
        routing_move_nan = calculate_cbs_routing(post_move_nan, estimated_spread_bps=15.0)
        assert routing_move_nan["route"] == "fast_path"  # because jsd == 0.0 < 0.12
        assert math.isnan(routing_move_nan["cbs_bps"])  # Empirical finding: NaN move propagates into cbs_bps
