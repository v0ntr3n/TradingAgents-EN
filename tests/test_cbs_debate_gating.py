"""
Canonical Acceptance Test Suite: CBS Debate Gating & Dynamic Coordination
Milestone: M1 / Phase 1
Reference: PROJECT.md (Features 1-10), ORIGINAL_REQUEST.md (Acceptance Criteria 1)

Acceptance Criteria:
- Verifies boundary conditions: D_JS = 0 (identical distributions) and D_JS = 1 (orthogonal distributions)
- Verifies dynamic routing switches between multi-round Bull/Bear debate and single-pass
  fast-path synthesis (RiskSelfDebateV2) based on disagreement (D_JS >= 0.12) and spread thresholds (CBS > s_t)
- Verifies base-2 Shannon entropy calculations and numerical invariants
- Verifies dynamic debate rounds scaling based on divergence intensity
- Verifies state schema concurrency reduction (merge_dict) and posterior normalization
"""

import math
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest
from langchain_core.messages import AIMessage

# Core imports
from core.agents.analyst import AnalystAgent, DEFAULT_UNINFORMATIVE_POSTERIOR
from core.agents.adapters.index_analyst_v2 import IndexAnalystV2
from core.agents.adapters.risk_self_debate_v2 import RiskSelfDebateV2
from core.state.reducers import merge_dict
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_shannon_entropy,
    compute_base2_jsd,
    compute_jensen_shannon_divergence,
    compute_cbs_bps,
    calculate_base2_jsd,
    calculate_cbs_routing,
    should_trigger_multi_round_debate,
    should_gate_debate,
)
from core.agents.analyst import (
    AnalystAgent,
    DEFAULT_UNINFORMATIVE_POSTERIOR,
    extract_structured_posterior,
)


# Dummy analyst subclass for response parsing tests
class MockAnalystAgent(AnalystAgent):
    analyst_type = "mock"
    output_field = "mock_report"

    def _build_system_prompt(self, market_type: str = None, context=None, state=None) -> str:
        return "Mock System Prompt"

    def _build_user_prompt(self, ticker: str, analysis_date: str, tool_data: Dict[str, Any], state: Dict[str, Any]) -> str:
        return "Mock User Prompt"


# ==============================================================================
# 1. Base-2 Shannon Entropy & JSD Boundary Conditions (D_JS = 0, D_JS = 1)
# ==============================================================================
class TestJSDBoundaryConditions:
    """Verifies Base-2 Shannon Entropy and strict JSD boundary conditions [0, 1]."""

    def test_shannon_entropy_deterministic_values(self):
        """H_2(P) = -sum(p * log2(p)). Verify certainty, uniform coin, and ternary distributions."""
        # Certainty: H_2([1, 0, 0]) = 0.0
        assert compute_shannon_entropy([1.0, 0.0, 0.0]) == 0.0
        assert compute_shannon_entropy([0.0, 1.0, 0.0]) == 0.0
        assert compute_shannon_entropy([0.0, 0.0, 1.0]) == 0.0

        # Fair binary coin: H_2([0.5, 0.5]) = 1.0
        assert pytest.approx(compute_shannon_entropy([0.5, 0.5]), abs=1e-6) == 1.0

        # Ternary uniform: H_2([1/3, 1/3, 1/3]) = log2(3) ~ 1.58496
        assert pytest.approx(compute_shannon_entropy([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]), abs=1e-4) == math.log2(3)

    def test_jsd_boundary_d_js_equals_zero_for_identical_distributions(self):
        """Boundary Condition: D_JS = 0 for identical probability distributions across analysts."""
        # 2 identical distributions
        identical_pair = [
            [0.60, 0.30, 0.10],
            [0.60, 0.30, 0.10],
        ]
        jsd_pair = compute_base2_jsd(identical_pair)
        assert pytest.approx(jsd_pair, abs=1e-6) == 0.0
        assert compute_jensen_shannon_divergence(identical_pair) < 1e-6

        # 3 identical distributions
        identical_triplet = [
            [0.25, 0.50, 0.25],
            [0.25, 0.50, 0.25],
            [0.25, 0.50, 0.25],
        ]
        assert compute_base2_jsd(identical_triplet) < 1e-6

        # All 7 specialist analysts in exact consensus
        seven_identical = [[0.70, 0.20, 0.10]] * 7
        assert compute_base2_jsd(seven_identical) < 1e-6

    def test_jsd_boundary_d_js_equals_one_for_orthogonal_distributions(self):
        """Boundary Condition: D_JS = 1 for completely orthogonal (maximally contradictory) distributions."""
        # Two analysts with opposite deterministic opinions: Optimistic vs Cautious
        orthogonal_dists = [
            [1.0, 0.0, 0.0],  # 100% Optimistic
            [0.0, 0.0, 1.0],  # 100% Cautious
        ]
        jsd_ortho = compute_base2_jsd(orthogonal_dists)
        assert pytest.approx(jsd_ortho, abs=1e-4) == 1.0

        # Alternate orthogonal pair: Optimistic vs Neutral
        orthogonal_opt_neu = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        assert pytest.approx(compute_base2_jsd(orthogonal_opt_neu), abs=1e-4) == 1.0

    def test_jsd_bounded_in_unit_interval(self):
        """JSD must strictly reside within [0.0, 1.0] across diverse distribution pairs."""
        test_pairs = [
            ([[0.9, 0.05, 0.05], [0.1, 0.1, 0.8]]),
            ([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]]),
            ([[0.333, 0.334, 0.333], [0.333, 0.334, 0.333]]),
            ([[0.99, 0.01, 0.0], [0.01, 0.99, 0.0]]),
        ]
        for dists in test_pairs:
            jsd = compute_base2_jsd(dists)
            assert 0.0 <= jsd <= 1.0

    def test_jsd_numerical_stability_with_exact_zeros(self):
        """Zeros in distribution vectors must not raise ZeroDivisionError or domain errors."""
        dists_with_zeros = [
            [1.0, 0.0, 0.0],
            [0.0, 0.5, 0.5],
            [0.5, 0.0, 0.5],
        ]
        jsd = compute_base2_jsd(dists_with_zeros)
        assert 0.0 <= jsd <= 1.0
        assert not math.isnan(jsd)

    def test_jsd_empty_or_single_input(self):
        """Empty or single distribution input safely returns 0.0."""
        assert compute_base2_jsd([]) == 0.0
        assert compute_base2_jsd([[0.7, 0.2, 0.1]]) == 0.0

    def test_jsd_inconsistent_dimensions_raises_value_error(self):
        """Mismatched dimension lengths across analysts raises ValueError."""
        with pytest.raises(ValueError, match="Inconsistent distribution dimensions"):
            compute_base2_jsd([[0.5, 0.5], [0.33, 0.33, 0.34]])


# ==============================================================================
# 2. CBS Debate Gating & Dynamic Routing Switches
# ==============================================================================
class TestCBSDebateGatingRouting:
    """Verifies CBS routing switches between multi-round debate and fast-path synthesis."""

    def test_consensus_triggers_fast_path(self):
        """When analysts are in high consensus (D_JS < 0.12), route to fast_path with 0 debate rounds."""
        consensus_posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.72, "p_neutral": 0.20, "p_cautious": 0.08, "expected_move_bps": 120.0, "confidence": 0.9},
            "news_analyst_v2": {"p_optimistic": 0.70, "p_neutral": 0.22, "p_cautious": 0.08, "expected_move_bps": 115.0, "confidence": 0.85},
            "fundamentals_analyst_v2": {"p_optimistic": 0.75, "p_neutral": 0.18, "p_cautious": 0.07, "expected_move_bps": 130.0, "confidence": 0.95},
        }
        res = calculate_cbs_routing(consensus_posteriors, estimated_spread_bps=15.0)
        assert res["route"] == "fast_path"
        assert res["jsd"] < 0.12
        assert res["dynamic_debate_rounds"] == 0

    def test_high_jsd_but_cbs_below_spread_triggers_fast_path(self):
        """
        Disagreement exists (D_JS >= 0.12), but expected price move is too small (CBS <= s_t).
        The expected gain does not justify transaction friction, bypassing debate.
        """
        disagreement_small_move = {
            "bull_analyst": {"p_optimistic": 0.75, "p_neutral": 0.15, "p_cautious": 0.10, "expected_move_bps": 10.0, "confidence": 0.9},
            "bear_analyst": {"p_optimistic": 0.10, "p_neutral": 0.15, "p_cautious": 0.75, "expected_move_bps": 10.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(disagreement_small_move, estimated_spread_bps=15.0)
        assert res["jsd"] >= 0.12
        assert res["cbs_bps"] <= 15.0
        assert res["route"] == "fast_path"
        assert res["dynamic_debate_rounds"] == 0

    def test_high_jsd_and_high_cbs_triggers_multi_round_debate(self):
        """
        Substantial disagreement (D_JS >= 0.12) AND high stakes (CBS > s_t).
        Triggers multi-round debate with dynamic rounds scaled from divergence intensity.
        """
        contested_high_stakes = {
            "bull_analyst": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 160.0, "confidence": 0.9},
            "bear_analyst": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85, "expected_move_bps": 160.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(contested_high_stakes, estimated_spread_bps=15.0, max_debate_rounds=3)
        assert res["jsd"] >= 0.12
        assert res["cbs_bps"] > 15.0
        assert res["route"] == "multi_round_debate"
        assert res["dynamic_debate_rounds"] in [2, 3]

    def test_opposing_directional_moves_preserve_magnitude(self):
        """
        When Bull expects +150 bps and Bear expects -150 bps, the absolute magnitude
        must be preserved as 150 bps, rather than cancelling out to 0 bps.
        """
        opposing = {
            "bull_specialist": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": +150.0, "confidence": 0.9},
            "bear_specialist": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": -150.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(opposing, estimated_spread_bps=15.0)
        assert pytest.approx(res["weighted_expected_move_bps"], abs=1e-4) == 150.0
        assert res["cbs_bps"] > 15.0
        assert res["route"] == "multi_round_debate"

    def test_spread_threshold_sensitivity(self):
        """Testing sensitivity across different market spread hurdles (5 bps vs 25 bps)."""
        moderate_posteriors = {
            "a1": {"p_optimistic": 0.65, "p_neutral": 0.20, "p_cautious": 0.15, "expected_move_bps": 60.0, "confidence": 0.8},
            "a2": {"p_optimistic": 0.15, "p_neutral": 0.20, "p_cautious": 0.65, "expected_move_bps": 60.0, "confidence": 0.8},
        }
        # Low spread hurdle (5 bps) -> debate triggered
        res_low_spread = calculate_cbs_routing(moderate_posteriors, estimated_spread_bps=5.0)
        assert res_low_spread["route"] == "multi_round_debate"

        # High spread hurdle (30 bps) -> fast path chosen due to friction
        res_high_spread = calculate_cbs_routing(moderate_posteriors, estimated_spread_bps=30.0)
        assert res_high_spread["route"] == "fast_path"

    def test_dynamic_debate_rounds_scaling(self):
        """Dynamic debate rounds scale from 1 to max_debate_rounds based on divergence intensity."""
        # Moderate divergence above 0.12 -> 1 round
        mild = {
            "a1": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 120.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.15, "p_neutral": 0.35, "p_cautious": 0.50, "expected_move_bps": 120.0, "confidence": 0.9},
        }
        res_mild = calculate_cbs_routing(mild, estimated_spread_bps=10.0, max_debate_rounds=3)
        assert res_mild["route"] == "multi_round_debate"
        assert res_mild["dynamic_debate_rounds"] in [1, 2]

        # Extreme divergence near 1.0 -> 3 rounds
        extreme = {
            "a1": {"p_optimistic": 0.99, "p_neutral": 0.005, "p_cautious": 0.005, "expected_move_bps": 200.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.005, "p_neutral": 0.005, "p_cautious": 0.99, "expected_move_bps": 200.0, "confidence": 0.9},
        }
        res_extreme = calculate_cbs_routing(extreme, estimated_spread_bps=10.0, max_debate_rounds=3)
        assert res_extreme["route"] == "multi_round_debate"
        assert res_extreme["dynamic_debate_rounds"] == 3


# ==============================================================================
# 3. ConditionalLogic Class & AgentState Integration
# ==============================================================================
class TestConditionalLogicStateIntegration:
    """Verifies runtime state mutation and graph edge routing."""

    def test_should_trigger_multi_round_debate_state_injection(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        state: Dict[str, Any] = {
            "analyst_posteriors": {
                "bull": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 150.0, "confidence": 0.9},
                "bear": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85, "expected_move_bps": 150.0, "confidence": 0.9},
            },
            "estimated_spread_bps": 15.0,
            "investment_debate_state": {"count": 0, "current_response": "Bull Researcher"},
        }

        decision = cl.should_trigger_multi_round_debate(state)
        assert decision == "multi_round_debate"
        assert state["debate_jsd"] >= 0.12
        assert state["cbs_bps"] > 15.0
        assert state["dynamic_debate_rounds"] in [2, 3]
        assert state["_max_debate_rounds"] == state["dynamic_debate_rounds"]

    def test_fast_path_sets_risk_self_debate_flag(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        state: Dict[str, Any] = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 80.0, "confidence": 0.85},
                "a2": {"p_optimistic": 0.68, "p_neutral": 0.22, "p_cautious": 0.10, "expected_move_bps": 80.0, "confidence": 0.85},
            },
            "estimated_spread_bps": 15.0,
        }
        decision = cl.should_trigger_multi_round_debate(state)
        assert decision == "fast_path"
        assert state["_risk_self_debate"] is True
        assert state["dynamic_debate_rounds"] == 0

    def test_should_continue_debate_honors_dynamic_rounds(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        state: Dict[str, Any] = {
            "investment_debate_state": {"count": 2, "current_response": "Bull Researcher"},
            "dynamic_debate_rounds": 1,  # Max count = 2 * 1 = 2
        }
        next_step = cl.should_continue_debate(state)
        assert next_step == "Research Manager"

    def test_module_gateway_convenience_alias(self):
        state: Dict[str, Any] = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 80.0, "confidence": 0.85},
                "a2": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 80.0, "confidence": 0.85},
            },
            "estimated_spread_bps": 15.0,
        }
        res = should_gate_debate(state)
        assert res == "fast_path"


# ==============================================================================
# 4. Fast-Path Synthesis & Signal Block Parsing
# ==============================================================================
class TestFastPathSynthesisAndParsing:
    """Verifies RiskSelfDebateV2 fast-path and posterior signal block extraction."""

    def test_signal_block_extraction_and_cleaning(self):
        analyst = MockAnalystAgent(config=None)
        raw_text = (
            "## Market Overview\n"
            "The market is forming a consolidated base with bullish divergence.\n"
            "```json:signal\n"
            "{\n"
            '  "p_optimistic": 0.65,\n'
            '  "p_neutral": 0.25,\n'
            '  "p_cautious": 0.10,\n'
            '  "expected_move_bps": 95.0,\n'
            '  "confidence": 0.88,\n'
            '  "market_regime": "bull"\n'
            "}\n"
            "```\n"
            "Recommendation: Accumulate gradually."
        )
        parsed = analyst._parse_response(raw_text)
        assert parsed["success"] is True
        assert "```json:signal" not in parsed["content"]
        assert "Recommendation: Accumulate gradually." in parsed["content"]

        post = parsed["posterior"]
        assert post["p_optimistic"] == 0.65
        assert post["p_neutral"] == 0.25
        assert post["p_cautious"] == 0.10
        assert abs((post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]) - 1.0) < 1e-4
        assert post["expected_move_bps"] == 95.0
        assert post["market_regime"] == "bull"

    def test_posterior_simplex_normalization_for_unnormalized_probabilities(self):
        analyst = MockAnalystAgent(config=None)
        raw_text = (
            "```json:signal\n"
            '{"p_optimistic": 3.0, "p_neutral": 1.0, "p_cautious": 1.0, "expected_move_bps": 50}\n'
            "```"
        )
        parsed = analyst._parse_response(raw_text)
        post = parsed["posterior"]
        assert pytest.approx(post["p_optimistic"], abs=1e-4) == 0.60
        assert pytest.approx(post["p_neutral"], abs=1e-4) == 0.20
        assert pytest.approx(post["p_cautious"], abs=1e-4) == 0.20
        assert pytest.approx(post["p_optimistic"] + post["p_neutral"] + post["p_cautious"], abs=1e-4) == 1.0

    def test_state_concurrency_merge_dict_reducer(self):
        """merge_dict handles parallel writes to analyst_posteriors dictionary."""
        existing = {
            "index_analyst_v2": {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1},
        }
        update = {
            "market_analyst_v2": {"p_optimistic": 0.6, "p_neutral": 0.3, "p_cautious": 0.1},
        }
        merged = merge_dict(existing, update)
        assert "index_analyst_v2" in merged
        assert "market_analyst_v2" in merged
        assert len(merged) == 2

    def test_risk_self_debate_v2_tripartite_fast_path(self):
        """RiskSelfDebateV2 executes single-pass synthesis generating 3 perspectives."""
        mock_llm = MagicMock()
        mock_response = AIMessage(
            content=(
                "[Highly resilient scenario perspective]\nUpside potential remains viable.\n\n"
                "[defensive situational view]\nKey downside support at 3000.\n\n"
                "[base case view]\nBalanced accumulation recommendation.\n"
            )
        )
        mock_llm.invoke.return_value = mock_response

        agent = RiskSelfDebateV2(llm=mock_llm)
        agent._get_prompt_from_template = MagicMock(return_value="Mock Prompt")
        agent._invoke_llm_with_trace = MagicMock(return_value=mock_response)

        state = {
            "ticker": "000001.SZ",
            "analysis_date": "2026-03-31",
            "investment_plan": "",
            "investment_debate_state": {},
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1},
            },
        }
        result = agent.execute(state)
        assert "investment_plan" in result
        assert "Fast-Path Tripartite Synthesis" in result["investment_plan"]
        assert "investment_debate_state" in result
        assert result["investment_debate_state"]["history"].startswith("Fast-Path")


# ==============================================================================
# 5. Milestone 1 Public APIs & Interface Contracts
# ==============================================================================
class TestMilestone1PublicAPIs:
    """Verifies standalone extract_structured_posterior, static method, compute_cbs_bps, and regime propagation."""

    def test_extract_structured_posterior_standalone_and_static(self):
        sample_report = (
            "Market analysis shows strong momentum.\n"
            "```json:signal\n"
            '{\n'
            '  "p_optimistic": 0.70,\n'
            '  "p_neutral": 0.20,\n'
            '  "p_cautious": 0.10,\n'
            '  "expected_move_bps": 120.0,\n'
            '  "confidence": 0.85,\n'
            '  "market_regime": "bull"\n'
            '}\n'
            "```"
        )
        post_func = extract_structured_posterior(sample_report)
        post_static = AnalystAgent.extract_structured_posterior(sample_report)

        assert post_func == post_static
        assert post_func["p_optimistic"] == 0.70
        assert post_func["p_neutral"] == 0.20
        assert post_func["p_cautious"] == 0.10
        assert post_func["expected_move_bps"] == 120.0
        assert post_func["confidence"] == 0.85
        assert post_func["market_regime"] == "bull"

    def test_extract_structured_posterior_unstructured_fallback(self):
        plain_text = "General market comments without structured signals."
        post = extract_structured_posterior(plain_text)
        assert post["market_regime"] == "sideways"
        assert post["expected_move_bps"] == 0.0
        assert abs(post["p_optimistic"] + post["p_neutral"] + post["p_cautious"] - 1.0) < 1e-4

    def test_compute_jensen_shannon_divergence_with_weights(self):
        posteriors = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 100.0},
            "a2": {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8, "expected_move_bps": 100.0},
        }
        # Uniform
        jsd_uniform = compute_jensen_shannon_divergence(posteriors)
        # Heavily skewed weights towards a1
        jsd_skewed = compute_jensen_shannon_divergence(posteriors, weights={"a1": 0.99, "a2": 0.01})
        assert 0.0 <= jsd_uniform <= 1.0
        assert 0.0 <= jsd_skewed <= 1.0
        assert jsd_skewed < jsd_uniform

    def test_compute_cbs_bps_both_signatures(self):
        # Signature 1: float jsd, float move
        cbs1 = compute_cbs_bps(0.6, 120.0)
        assert pytest.approx(cbs1, abs=1e-4) == (0.6 * 120.0) / 2.0

        # Signature 2: dict posteriors
        posteriors = {
            "a1": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1, "expected_move_bps": 100.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.1, "p_neutral": 0.1, "p_cautious": 0.8, "expected_move_bps": 100.0, "confidence": 0.9},
        }
        cbs2 = compute_cbs_bps(posteriors)
        jsd = compute_jensen_shannon_divergence(posteriors)
        expected = (jsd * 100.0) / 2.0
        assert pytest.approx(cbs2, abs=1e-2) == expected

    def test_should_gate_debate_sets_flags_accurately(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        # Fast path state
        fast_state = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.6, "p_neutral": 0.3, "p_cautious": 0.1, "expected_move_bps": 20.0},
                "a2": {"p_optimistic": 0.6, "p_neutral": 0.3, "p_cautious": 0.1, "expected_move_bps": 20.0},
            },
            "estimated_spread_bps": 15.0,
        }
        dec_fast = cl.should_gate_debate(fast_state)
        assert dec_fast == "fast_path"
        assert fast_state["_risk_self_debate"] is True

        # Debate state
        debate_state = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.95, "p_neutral": 0.02, "p_cautious": 0.03, "expected_move_bps": 180.0},
                "a2": {"p_optimistic": 0.03, "p_neutral": 0.02, "p_cautious": 0.95, "expected_move_bps": 180.0},
            },
            "estimated_spread_bps": 15.0,
        }
        dec_debate = cl.should_gate_debate(debate_state)
        assert dec_debate == "multi_round_debate"
        assert debate_state["_risk_self_debate"] is False

    def test_index_analyst_v2_market_regime_propagation(self):
        agent = IndexAnalystV2(llm=None)
        agent._prepare_analysis_mode = MagicMock(return_value="tushare")
        report_text = (
            "Broad macro index analysis with clear bull market characteristics." + ("." * 100) + "\n"
            "```json:signal\n"
            '{\n'
            '  "p_optimistic": 0.80,\n'
            '  "p_neutral": 0.15,\n'
            '  "p_cautious": 0.05,\n'
            '  "expected_move_bps": 150.0,\n'
            '  "confidence": 0.90,\n'
            '  "market_regime": "bull"\n'
            '}\n'
            "```"
        )

        # 1. Existing report branch (agent not yet in posteriors)
        state_existing = {
            "index_report": report_text,
            "analyst_posteriors": {},
        }
        res_existing = agent.execute(state_existing)
        assert "market_regime" in res_existing
        assert res_existing["market_regime"] == "bull"
        assert agent.agent_id in res_existing["analyst_posteriors"]

        # 2. Existing report branch (agent already in posteriors) -> must return {}
        state_already_done = {
            "index_report": report_text,
            "analyst_posteriors": {agent.agent_id: {"p_optimistic": 0.8}},
        }
        res_done = agent.execute(state_already_done)
        assert res_done == {}

        # 3. Cache hit branch
        with patch("core.agents.adapters.index_analyst_v2._get_cached_index_report", return_value=report_text):
            state_cache = {"ticker": "000300.SH", "analysis_date": "2026-03-31"}
            res_cache = agent.execute(state_cache)
            assert "market_regime" in res_cache
            assert res_cache["market_regime"] == "bull"
            assert agent.agent_id in res_cache["analyst_posteriors"]
            assert "index_report" in res_cache
