"""
Tier 5 Adversarial Stress Testing & White-Box Coverage Hardening Suite (Suite 2).

Target Modules:
- tradingagents/graph/conditional_logic.py (CBS Gating & JSD)
- core/agents/utils/weight_calculator.py (MWU & Brier Loss)
- tradingagents/graph/signal_processing.py (Bayesian Log-Odds Target Price)
- core/memory/memory_manager.py (Regime Circuit-Breaker & Metadata)
- core/agents/reflection_helper.py (4-Quadrant Counterfactual Credit Assignment)
- core/backtest/result_evaluator.py (FrictionConfig & Net Performance Metrics)

Author: Challenger Tier 5 (Agent 2)
"""

import math
import random
from typing import Any, Dict, List
import numpy as np
import pytest

from core.agents.utils.weight_calculator import (
    DEFAULT_ANALYST_IDS,
    RegimeAdaptiveWeightCalculator,
)
from core.agents.reflection_helper import (
    calculate_counterfactual_attribution,
    format_attribution_prompt_block,
)
from core.backtest.result_evaluator import (
    FrictionConfig,
    calculate_cbs_and_coordination_cost,
    calculate_multi_regime_breakdown,
    calculate_net_performance_metrics,
)
from core.memory.memory_manager import (
    _CIRCUIT_BREAKER_AGENTS,
    circuit_breaker_memory_filter,
)
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    calculate_base2_jsd,
    calculate_cbs_routing,
    compute_base2_jsd,
    compute_shannon_entropy,
    should_trigger_multi_round_debate,
)
from tradingagents.graph.signal_processing import (
    calculate_bayesian_log_odds_target_price,
    compute_bayesian_log_odds_details,
)


# ==============================================================================
# Focus Area 1: Numerical Stability Under Extreme Inputs
# ==============================================================================

class TestTier5NumericalStabilityExtremes:
    """Stress tests numerical stability on extreme inputs, boundary simplexes, and extreme losses."""

    def test_dirichlet_simplex_vertices_jsd_strictly_bounded(self):
        """Pure simplex vertices [1, 0, 0], [0, 1, 0], [0, 0, 1] and near-vertex perturbations.

        Verifies JSD is strictly bounded in [0.0, 1.0] without NaN or floating-point errors.
        """
        vertices = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        jsd_orth = compute_base2_jsd(vertices)
        assert not math.isnan(jsd_orth)
        assert not math.isinf(jsd_orth)
        assert 0.0 <= jsd_orth <= 1.0
        # In base-2 with clamp, max JSD is 1.0
        assert jsd_orth == 1.0

        # Perturbed vertices near 0/1 simplex boundaries
        epsilons = [1e-9, 1e-15, 1e-30, 1e-300]
        for eps in epsilons:
            perturbed = [
                [1.0 - 2 * eps, eps, eps],
                [eps, 1.0 - 2 * eps, eps],
                [eps, eps, 1.0 - 2 * eps],
            ]
            jsd_pert = compute_base2_jsd(perturbed)
            assert 0.0 <= jsd_pert <= 1.0
            assert not math.isnan(jsd_pert)

    def test_dirichlet_low_concentration_random_sampling(self):
        """Random Dirichlet samples with low concentration parameter (alpha = 0.01).

        Samples are strongly concentrated at simplex vertices; verify JSD remains stable across 50 trials.
        """
        np.random.seed(42)
        alpha = [0.01, 0.01, 0.01]
        for _ in range(50):
            sample_dists = np.random.dirichlet(alpha, size=4).tolist()
            jsd = compute_base2_jsd(sample_dists)
            assert 0.0 <= jsd <= 1.0
            assert not math.isnan(jsd)

    def test_jsd_zero_boundaries_identical_and_single(self):
        """Identical distributions across N analysts, single analyst, or empty list must return 0.0."""
        # Single distribution
        assert compute_base2_jsd([[0.7, 0.2, 0.1]]) == 0.0
        assert compute_base2_jsd([]) == 0.0

        # Multiple identical distributions (arbitrary simplex locations)
        for vec in [[1.0, 0.0, 0.0], [0.3333, 0.3334, 0.3333], [0.8, 0.1, 0.1], [0.01, 0.98, 0.01]]:
            dists = [list(vec) for _ in range(7)]
            assert compute_base2_jsd(dists) == pytest.approx(0.0, abs=1e-12)

        # Analyst posteriors dictionary with identical posteriors
        ident_posteriors = {
            f"analyst_{i}": {
                "p_optimistic": 0.60,
                "p_neutral": 0.20,
                "p_cautious": 0.20,
                "expected_move_bps": 75.0,
                "confidence": 0.8,
            }
            for i in range(5)
        }
        assert calculate_base2_jsd(ident_posteriors) == pytest.approx(0.0, abs=1e-12)

    def test_brier_loss_extremes_and_mwu_weight_preservation(self):
        """Brier loss extremes (0.0 vs 2.0) and MWU weight normalization under extreme learning rates."""
        calc = RegimeAdaptiveWeightCalculator()
        analysts = ["analyst_opt", "analyst_caut"]
        calc.analyst_ids = list(analysts)
        calc.reset()

        # Perfect prediction (p_opt = 1.0 when return is +100 bps)
        post_perfect = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        loss_perfect = calc.compute_brier_loss(post_perfect, realized_return=0.01)
        assert loss_perfect == 0.0

        # Worst possible prediction (p_opt = 1.0 when return is -100 bps, target is cautious)
        loss_worst = calc.compute_brier_loss(post_perfect, realized_return=-0.01)
        assert loss_worst == 2.0

        # MWU update across extreme learning rates
        for lr in [0.0, 0.2, 1.0, 10.0, 100.0]:
            calc.reset()
            posteriors = {
                "analyst_opt": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0},
                "analyst_caut": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0},
            }
            # Market goes down: cautious is right (loss=0), optimistic is wrong (loss=2)
            updated = calc.update_weights("bear", posteriors, realized_return=-0.02, learning_rate=lr)
            assert sum(updated.values()) == pytest.approx(1.0, abs=1e-9)
            if lr > 0:
                assert updated["analyst_caut"] >= updated["analyst_opt"]
            else:
                assert updated["analyst_caut"] == pytest.approx(updated["analyst_opt"], abs=1e-9)

    def test_log_odds_extreme_probabilities_and_clipping(self):
        """Bayesian log-odds opinion pooling under extreme probability vectors."""
        current_price = 100.0
        # Extreme optimistic analyst (p_opt = 1.0, p_caut = 0.0 -> clamped by eps=1e-4)
        ext_posteriors = {
            "a1": {
                "p_optimistic": 1.0,
                "p_neutral": 0.0,
                "p_cautious": 0.0,
                "expected_move_bps": 500.0,
            }
        }
        details_buy = compute_bayesian_log_odds_details(
            current_price=current_price,
            action="buy",
            regime="bull",
            analyst_posteriors=ext_posteriors,
        )
        assert details_buy["target_price"] > current_price
        assert details_buy["p_agg"] > 0.99
        assert -10.0 <= details_buy["l_agg"] <= 10.0  # Clipped

        # Extreme cautious analyst (p_opt = 0.0, p_caut = 1.0)
        ext_caut_posteriors = {
            "a2": {
                "p_optimistic": 0.0,
                "p_neutral": 0.0,
                "p_cautious": 1.0,
                "expected_move_bps": -500.0,
            }
        }
        details_sell = compute_bayesian_log_odds_details(
            current_price=current_price,
            action="sell",
            regime="bear",
            analyst_posteriors=ext_caut_posteriors,
        )
        assert details_sell["target_price"] < current_price
        assert details_sell["p_agg"] < 0.01
        assert not math.isnan(details_sell["target_price"])


# ==============================================================================
# Focus Area 2: Dynamic Debate Gating with Missing / None State Fields
# ==============================================================================

class TestTier5DynamicDebateGatingFields:
    """Stress tests debate gating under missing, None, and hostile state dictionary fields."""

    def test_debate_gating_missing_estimated_spread_bps_defaults(self):
        """When estimated_spread_bps is absent from state, it safely defaults to 15.0 bps."""
        state = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1, "expected_move_bps": 10.0},
                "a2": {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8, "expected_move_bps": 10.0},
            }
        }
        # estimated_spread_bps key is completely absent
        route = should_trigger_multi_round_debate(state)
        assert route in ["fast_path", "multi_round_debate"]
        assert state.get("estimated_spread_bps") is None  # was not set originally
        # verify internal metric recorded
        assert "cbs_bps" in state

    def test_debate_gating_none_estimated_spread_bps_vulnerability(self):
        """Hardened: When state['estimated_spread_bps'] is explicitly None,

        it safely falls back to default 15.0 bps without raising TypeError.
        """
        state = {
            "analyst_posteriors": {},
            "estimated_spread_bps": None,  # Key present, but explicitly None
        }
        route = should_trigger_multi_round_debate(state)
        assert route in ["fast_path", "multi_round_debate"]
        assert route == "fast_path"
        assert state["cbs_bps"] == 0.0

    def test_debate_gating_non_numeric_and_negative_spread(self):
        """When estimated_spread_bps is <= 0 or 0.0, routing handles hurdle comparison safely."""
        high_conflict = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 200.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.9, "expected_move_bps": 200.0, "confidence": 0.9},
        }
        state_zero = {"analyst_posteriors": high_conflict, "estimated_spread_bps": 0.0}
        route_zero = should_trigger_multi_round_debate(state_zero)
        assert route_zero == "multi_round_debate"

        state_neg = {"analyst_posteriors": high_conflict, "estimated_spread_bps": -10.0}
        route_neg = should_trigger_multi_round_debate(state_neg)
        assert route_neg == "multi_round_debate"

    def test_debate_gating_missing_and_none_analyst_posteriors(self):
        """When analyst_posteriors is missing, None, or empty dict, gating safely routes to fast_path."""
        empty_states = [
            {},
            {"analyst_posteriors": None},
            {"analyst_posteriors": {}},
            {"analyst_posteriors": "not_a_dict"},
            {"analyst_posteriors": []},
        ]
        for st in empty_states:
            route = should_trigger_multi_round_debate(st)
            assert route == "fast_path"
            if isinstance(st, dict) and "dynamic_debate_rounds" in st:
                assert st["dynamic_debate_rounds"] == 0
                assert st["debate_jsd"] == 0.0

    def test_debate_gating_malformed_posterior_elements(self):
        """Hardened: When posterior values are non-numeric strings,

        calculate_base2_jsd safely falls back to uniform probabilities without raising ValueError.
        """
        malformed_state = {
            "analyst_posteriors": {
                "analyst_bad": {"p_optimistic": "corrupted_non_float"},
            }
        }
        route = should_trigger_multi_round_debate(malformed_state)
        assert route in ["fast_path", "multi_round_debate"]
        assert route == "fast_path"


# ==============================================================================
# Focus Area 3: Memory Circuit-Breaker Boundary Conditions
# ==============================================================================

class TestTier5MemoryCircuitBreakerBoundaries:
    """Stress tests regime circuit-breaker filter across exact 0.500000 boundary and agent types."""

    def test_circuit_breaker_exact_threshold_boundary_0_5(self):
        """Tests exact confidence boundary: 0.500000 triggers filter, 0.499999 bypasses filter.

        Specification (§R3): 'filter out memories whose stored market_regime contradicts current state['market_regime']
        unless current regime confidence is below 0.5'.
        """
        memories = [
            {"id": "m1", "metadata": {"market_regime": "bull"}},
            {"id": "m2", "metadata": {"market_regime": "bear"}},
            {"id": "m3", "metadata": {"market_regime": "sideways"}},
        ]
        # At exactly 0.500000: NOT below 0.5 -> circuit-breaker ACTIVE -> filters out 'bear' and 'sideways'
        f_active = circuit_breaker_memory_filter(
            memories=memories,
            current_regime="bull",
            regime_confidence=0.500000,
            agent_id="bull_researcher_v2",
        )
        assert len(f_active) == 1
        assert f_active[0]["id"] == "m1"

        # At 0.499999: strictly below 0.5 -> circuit-breaker BYPASSED -> returns all 3 memories
        f_bypassed = circuit_breaker_memory_filter(
            memories=memories,
            current_regime="bull",
            regime_confidence=0.499999,
            agent_id="bull_researcher_v2",
        )
        assert len(f_bypassed) == 3

        # At 0.500001: strictly above 0.5 -> circuit-breaker ACTIVE -> filters
        f_above = circuit_breaker_memory_filter(
            memories=memories,
            current_regime="bull",
            regime_confidence=0.500001,
            agent_id="bull_researcher_v2",
        )
        assert len(f_above) == 1
        assert f_above[0]["id"] == "m1"

    def test_circuit_breaker_microscopic_float_precision(self):
        """Evaluates boundary behavior at IEEE 754 precision limit around 0.5."""
        memories = [
            {"id": "m_bull", "metadata": {"market_regime": "bull"}},
            {"id": "m_bear", "metadata": {"market_regime": "bear"}},
        ]
        # 0.5 - 1e-12 -> bypass
        res_low = circuit_breaker_memory_filter(memories, "bull", 0.5 - 1e-12, "trader_v2")
        assert len(res_low) == 2

        # 0.5 + 1e-12 -> filter
        res_high = circuit_breaker_memory_filter(memories, "bull", 0.5 + 1e-12, "trader_v2")
        assert len(res_high) == 1
        assert res_high[0]["id"] == "m_bull"

    def test_circuit_breaker_hostile_confidence_inputs(self):
        """Hostile confidence inputs (None, negative, string, 0.0)."""
        memories = [
            {"id": "m_bull", "metadata": {"market_regime": "bull"}},
            {"id": "m_bear", "metadata": {"market_regime": "bear"}},
        ]
        # None confidence defaults to 1.0 -> filters
        res_none = circuit_breaker_memory_filter(memories, "bull", None, "risk_manager_v2")
        assert len(res_none) == 1

        # 0.0 confidence < 0.5 -> bypasses
        res_zero = circuit_breaker_memory_filter(memories, "bull", 0.0, "risk_manager_v2")
        assert len(res_zero) == 2

        # Negative confidence < 0.5 -> bypasses
        res_neg = circuit_breaker_memory_filter(memories, "bull", -0.5, "risk_manager_v2")
        assert len(res_neg) == 2

        # String '0.5' parsed as float -> filters
        res_str = circuit_breaker_memory_filter(memories, "bull", "0.5", "risk_manager_v2")
        assert len(res_str) == 1

    def test_circuit_breaker_non_target_agents_always_bypass(self):
        """Non-circuit-breaker agents (e.g. analyst_v2) NEVER filter memories regardless of confidence."""
        memories = [
            {"id": "m_bull", "metadata": {"market_regime": "bull"}},
            {"id": "m_bear", "metadata": {"market_regime": "bear"}},
        ]
        non_cb_agents = [
            "index_analyst_v2",
            "sector_analyst_v2",
            "market_analyst_v2",
            "fundamentals_analyst_v2",
            "news_analyst_v2",
            "social_analyst_v2",
            "chip_distribution_analyst_v2",
            "random_custom_agent",
        ]
        for aid in non_cb_agents:
            res = circuit_breaker_memory_filter(
                memories=memories,
                current_regime="bull",
                regime_confidence=1.0,  # Max confidence
                agent_id=aid,
            )
            assert len(res) == 2, f"Agent {aid} was incorrectly filtered by circuit breaker"


# ==============================================================================
# Focus Area 4: Counterfactual Attribution Under Extreme Market Moves
# ==============================================================================

class TestTier5CounterfactualAttributionExtremes:
    """Stress tests 4-quadrant counterfactual attribution on extreme market moves and boundary inputs."""

    def test_attribution_extreme_positive_returns(self):
        """Extreme positive returns (+1000%, +10,000%, +1e6%) scale linearly without overflow."""
        extreme_returns = [10.0, 100.0, 1e6]
        for r in extreme_returns:
            # Q1: Vindicated & Followed: +|R| * conf
            q1 = calculate_counterfactual_attribution("buy", r, "buy", agent_confidence=0.9)
            assert q1["quadrant"] == "Q1_Vindicated_Followed"
            assert q1["attribution_score"] == pytest.approx(r * 0.9, rel=1e-6)

            # Q2: Vindicated & Overridden: +|R|
            q2 = calculate_counterfactual_attribution("buy", r, "sell", agent_confidence=0.5)
            assert q2["quadrant"] == "Q2_Vindicated_Overridden"
            assert q2["attribution_score"] == pytest.approx(r, rel=1e-6)

    def test_attribution_extreme_negative_returns(self):
        """Extreme negative returns (-99.9%, -100%, -500%) scale linearly without overflow."""
        extreme_losses = [-0.999, -1.0, -5.0, -1e6]
        for r in extreme_losses:
            abs_r = abs(r)
            # Q3: Faulty & Followed: -|R| * conf
            q3 = calculate_counterfactual_attribution("buy", r, "buy", agent_confidence=0.85)
            assert q3["quadrant"] == "Q3_Faulty_Followed"
            assert q3["attribution_score"] == pytest.approx(-abs_r * 0.85, rel=1e-6)

            # Q4: Faulty & Overridden: -0.2 * |R|
            q4 = calculate_counterfactual_attribution("buy", r, "sell", agent_confidence=0.85)
            assert q4["quadrant"] == "Q4_Faulty_Overridden"
            assert q4["attribution_score"] == pytest.approx(-0.2 * abs_r, rel=1e-6)

    def test_attribution_zero_and_microscopic_returns(self):
        """Zero return (0.0, -0.0) and sub-basis point returns (1e-6) must evaluate without NaN."""
        for r in [0.0, -0.0, 1e-9, -1e-9]:
            attr = calculate_counterfactual_attribution("buy", r, "buy", 0.8)
            assert not math.isnan(attr["attribution_score"])
            assert not math.isinf(attr["attribution_score"])
            if abs(r) == 0.0:
                assert abs(attr["attribution_score"]) == 0.0

    def test_attribution_confidence_clamping_and_prompt_formatting(self):
        """Confidence clamped to [0.01, 1.0] and prompt formatting under extreme numbers."""
        # Confidence <= 0 clamped to 0.01
        attr_low = calculate_counterfactual_attribution("buy", 1.0, "buy", agent_confidence=-5.0)
        assert attr_low["agent_confidence"] == 0.01
        assert attr_low["attribution_score"] == pytest.approx(0.01)

        # Confidence > 1 clamped to 1.0
        attr_high = calculate_counterfactual_attribution("buy", 1.0, "buy", agent_confidence=50.0)
        assert attr_high["agent_confidence"] == 1.0
        assert attr_high["attribution_score"] == pytest.approx(1.0)

        # Prompt formatting survival under extreme scores
        prompt_block = format_attribution_prompt_block(attr_high)
        assert "=== Counterfactual Credit Assignment ===" in prompt_block
        assert "Attribution Score: +1.000" in prompt_block


# ==============================================================================
# Focus Area 5: Result Evaluator with Heterogeneous Trade Records
# ==============================================================================

class TestTier5ResultEvaluatorHeterogeneousRecords:
    """Stress tests result evaluator on empty trades, dictionary friction configs, and extreme drawdowns."""

    def test_evaluator_empty_trades_and_empty_returns_zero_division_guard(self):
        """Empty trades list and empty returns list return valid dictionary with all 0.0 metrics."""
        res = calculate_net_performance_metrics(trades=[], daily_returns=[])
        assert res["gross_return"] == 0.0
        assert res["net_return"] == 0.0
        assert res["net_sharpe"] == 0.0
        assert res["net_sortino"] == 0.0
        assert res["net_calmar"] == 0.0
        assert res["net_max_drawdown"] == 0.0
        assert res["trade_count"] == 0

    def test_evaluator_dict_friction_configuration_vulnerability(self):
        """Hardened: Passing friction as a dict instead of FrictionConfig

        is safely converted to FrictionConfig without raising AttributeError.
        """
        dict_friction = {
            "sell_stamp_duty_bps": 5.0,
            "commission_bps": 2.5,
            "slippage_bps": 5.0,
        }
        trades = [{"action": "buy", "shares": 100}]
        returns = [0.01, 0.02]

        res = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=dict_friction)
        assert isinstance(res, dict)
        assert "total_frictions_bps" in res
        assert res["total_frictions_bps"] == pytest.approx(7.5, abs=1e-6)
        assert res["trade_count"] == 1

    def test_evaluator_heterogeneous_trade_records(self):
        """Heterogeneous trade records with missing action, string shares, None shares, and non-dicts."""
        trades = [
            {"side": "BUY", "shares": "100"},          # string shares -> buy 7.5 bps
            {"type": "sell", "shares": -50},            # negative shares -> sell 12.5 bps
            {"shares": 100},                            # missing action -> shares > 0 -> buy 7.5 bps
            {"action": "sell"},                         # missing shares -> sell 12.5 bps
            {"action": None, "shares": None},           # both None -> roundtrip 20.0 bps
            "invalid_non_dict_trade",                   # skipped
            None,                                       # skipped
        ]
        # Expected frictions: 7.5 + 12.5 + 7.5 + 12.5 + 20.0 = 60.0 bps
        returns = [0.005] * 10
        friction = FrictionConfig()
        res = calculate_net_performance_metrics(trades=trades, daily_returns=returns, friction=friction)
        assert res["total_frictions_bps"] == pytest.approx(60.0, abs=1e-6)
        assert res["trade_count"] == 5

    def test_evaluator_extreme_drawdowns_and_bankruptcy(self):
        """Extreme drawdowns: 100% loss (MDD=-1.0, Calmar=-1.0), leveraged loss (-150%), and zero drawdown."""
        friction = FrictionConfig(sell_stamp_duty_bps=0, commission_bps=0, slippage_bps=0)

        # Single-day 100% total loss
        res_loss_100 = calculate_net_performance_metrics(trades=[], daily_returns=[-1.0], friction=friction)
        assert res_loss_100["net_return"] == -1.0
        assert res_loss_100["net_max_drawdown"] == -1.0
        assert res_loss_100["net_calmar"] == -1.0

        # Leveraged / extreme negative return
        res_loss_150 = calculate_net_performance_metrics(trades=[], daily_returns=[-1.5], friction=friction)
        assert res_loss_150["net_max_drawdown"] == -1.5
        assert res_loss_150["annualized_return"] == -1.0

        # Zero drawdown (strictly positive returns)
        res_pos = calculate_net_performance_metrics(trades=[], daily_returns=[0.01, 0.02, 0.01], friction=friction)
        assert res_pos["net_max_drawdown"] == 0.0
        assert res_pos["net_calmar"] == 0.0  # Division by zero avoided

        # Flat zero returns: with rf=0.025, excess returns are constantly negative (-rf/252),
        # downside deviation is rf/252, resulting in net_sortino = -sqrt(252) = -15.8745
        res_flat = calculate_net_performance_metrics(trades=[], daily_returns=[0.0, 0.0, 0.0], friction=friction)
        assert res_flat["net_sharpe"] == 0.0
        assert res_flat["net_sortino"] == pytest.approx(-math.sqrt(252.0), abs=1e-4)
        assert res_flat["net_calmar"] == 0.0

        # With risk_free_rate=0.0, downside deviation is 0.0, guarded to 0.0
        res_flat_rf0 = calculate_net_performance_metrics(
            trades=[], daily_returns=[0.0, 0.0, 0.0], friction=friction, risk_free_rate=0.0
        )
        assert res_flat_rf0["net_sharpe"] == 0.0
        assert res_flat_rf0["net_sortino"] == 0.0
        assert res_flat_rf0["net_calmar"] == 0.0

    def test_cbs_coordination_cost_malformed_records_vulnerability(self):
        """Hardened: When debate record contains 'latency_ms': None,

        calculate_cbs_and_coordination_cost safely handles None without raising TypeError.
        """
        records = [
            {"cbs_bps": 10.0, "tokens": 500, "latency_ms": None},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert isinstance(res, dict)
        assert res["mean_cbs_bps"] == 10.0
        assert res["mean_tokens_per_decision"] == 500.0
        assert res["mean_latency_ms_per_decision"] == 0.0
