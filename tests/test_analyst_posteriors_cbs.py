"""
Unit Test Suite for CARE-Agents Milestone M1:
- Analyst Posterior Estimation & Signal Block Parsing
- V2 Analyst Adapters Integration & Schema Compliance
- Pure Python Base-2 Shannon Entropy & JSD Calculation
- Coordination Breakeven Spread (CBS) Gating & Dynamic Debate Rounds
- RiskSelfDebateV2 Fast-Path Synthesis
- State Schema Concurrency with merge_dict Reducer

All tests run 100% offline, deterministically, without requiring network or external databases.
"""

import json
import math
import re
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from core.agents.analyst import AnalystAgent, DEFAULT_UNINFORMATIVE_POSTERIOR
from core.agents.adapters.index_analyst_v2 import IndexAnalystV2
from core.agents.adapters.sector_analyst_v2 import SectorAnalystV2
from core.agents.adapters.market_analyst_v2 import MarketAnalystV2
from core.agents.adapters.fundamentals_analyst_v2 import FundamentalsAnalystAgentV2
from core.agents.adapters.news_analyst_v2 import NewsAnalystV2
from core.agents.adapters.social_analyst_v2 import SocialMediaAnalystV2
from core.agents.adapters.chip_distribution_analyst_v2 import ChipDistributionAnalystV2
from core.agents.adapters.risk_self_debate_v2 import RiskSelfDebateV2
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_shannon_entropy,
    compute_base2_jsd,
    calculate_base2_jsd,
    calculate_cbs_routing,
    should_trigger_multi_round_debate,
)
from tradingagents.agents.utils.agent_states import AgentState
from core.workflow.builder import WorkflowBuilder
from core.state.reducers import merge_dict


# Concrete analyst subclass for base parser testing
class DummyAnalystAgent(AnalystAgent):
    analyst_type = "dummy"
    output_field = "dummy_report"

    def _build_system_prompt(self, market_type: str = None, context=None, state=None) -> str:
        return "Dummy System Prompt"

    def _build_user_prompt(self, ticker: str, analysis_date: str, tool_data: Dict[str, Any], state: Dict[str, Any]) -> str:
        return "Dummy User Prompt"


# ==============================================================================
# 1. Test Suite: Analyst Response Parsing & Probability Normalization
# ==============================================================================
class TestAnalystResponseParsing:
    """Test AnalystAgent._parse_response and normalization logic."""

    @pytest.fixture
    def analyst(self):
        return DummyAnalystAgent(config=None)

    def test_clean_markdown_and_signal_block_extraction(self, analyst):
        raw_text = (
            "## Technical Report\n"
            "The asset has formed a bull flag with expanding breakout volume.\n"
            "```json:signal\n"
            "{\n"
            '  "p_optimistic": 0.70,\n'
            '  "p_neutral": 0.20,\n'
            '  "p_cautious": 0.10,\n'
            '  "expected_move_bps": 120.0,\n'
            '  "confidence": 0.85,\n'
            '  "market_regime": "bull"\n'
            "}\n"
            "```\n"
            "Action recommendation: Accumulate on pullbacks."
        )
        parsed = analyst._parse_response(raw_text)

        assert parsed["success"] is True
        assert "```json:signal" not in parsed["content"]
        assert "p_optimistic" not in parsed["content"]
        assert "The asset has formed a bull flag" in parsed["content"]
        assert "Action recommendation: Accumulate on pullbacks." in parsed["content"]

        post = parsed["posterior"]
        assert post["p_optimistic"] == 0.70
        assert post["p_neutral"] == 0.20
        assert post["p_cautious"] == 0.10
        assert abs((post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]) - 1.0) < 1e-4
        assert post["expected_move_bps"] == 120.0
        assert post["confidence"] == 0.85
        assert post["market_regime"] == "bull"

    def test_unnormalized_probabilities_scaling(self, analyst):
        raw = {
            "p_optimistic": 0.6,
            "p_neutral": 0.4,
            "p_cautious": 0.6,
            "expected_move_bps": 50.0,
            "confidence": 0.8,
            "market_regime": "bull",
        }
        post = analyst._normalize_posterior(raw)
        total = post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]
        assert abs(total - 1.0) < 1e-4
        assert post["p_optimistic"] == 0.375
        assert post["p_neutral"] == 0.25
        assert post["p_cautious"] == 0.375

    def test_percentage_probabilities_converted(self, analyst):
        raw = {
            "p_optimistic": 70,
            "p_neutral": 20,
            "p_cautious": 10,
            "expected_move_bps": 100,
            "confidence": 90,
            "market_regime": "bull",
        }
        post = analyst._normalize_posterior(raw)
        total = post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]
        assert abs(total - 1.0) < 1e-4
        assert post["p_optimistic"] == 0.7
        assert post["p_neutral"] == 0.2
        assert post["p_cautious"] == 0.1
        assert post["confidence"] == 0.9

    def test_negative_and_out_of_bound_probabilities(self, analyst):
        raw = {
            "p_optimistic": -0.5,
            "p_neutral": 0.5,
            "p_cautious": 0.5,
            "expected_move_bps": 0.0,
            "confidence": 1.5,
            "market_regime": "sideways",
        }
        post = analyst._normalize_posterior(raw)
        assert post["p_optimistic"] == 0.0
        assert post["p_neutral"] == 0.5
        assert post["p_cautious"] == 0.5
        assert abs((post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]) - 1.0) < 1e-4
        assert post["confidence"] == 1.0

    def test_all_zero_probabilities_fallback(self, analyst):
        raw = {
            "p_optimistic": 0.0,
            "p_neutral": 0.0,
            "p_cautious": 0.0,
            "expected_move_bps": 0.0,
            "confidence": 0.0,
            "market_regime": "sideways",
        }
        post = analyst._normalize_posterior(raw)
        total = post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]
        assert abs(total - 1.0) < 1e-4
        assert post["p_optimistic"] == 0.3333
        assert post["p_neutral"] == 0.3334
        assert post["p_cautious"] == 0.3333

    def test_pure_text_unstructured_fallback(self, analyst):
        raw_text = "Standard analysis report without any structured JSON block."
        parsed = analyst._parse_response(raw_text)

        assert parsed["success"] is True
        assert parsed["content"] == raw_text
        post = parsed["posterior"]
        assert post["p_optimistic"] == 0.3333
        assert post["p_neutral"] == 0.3334
        assert post["p_cautious"] == 0.3333
        assert post["expected_move_bps"] == 0.0
        assert post["confidence"] == 0.0
        assert post["market_regime"] == "sideways"

    def test_malformed_json_repair(self, analyst):
        # Malformed: single quotes, trailing commas, Python None/True
        raw_text = (
            "Analysis text\n"
            "```json\n"
            "{\n"
            "  'p_optimistic': 0.65,\n"
            "  'p_neutral': 0.25,\n"
            "  'p_cautious': 0.10,\n"
            "  'expected_move_bps': 80.0,\n"
            "  'confidence': 0.75,\n"
            "  'market_regime': 'bull',\n"
            "}\n"
            "```\n"
        )
        parsed = analyst._parse_response(raw_text)
        assert parsed["success"] is True
        post = parsed["posterior"]
        assert post["p_optimistic"] == 0.65
        assert post["p_neutral"] == 0.25
        assert post["p_cautious"] == 0.10
        assert post["market_regime"] == "bull"

    def test_truncated_json_fallback(self, analyst):
        raw_text = "Analysis text\n```json\n{'p_optimistic': 0.65, 'p_neutral': "
        parsed = analyst._parse_response(raw_text)
        assert parsed["success"] is True
        assert abs(sum([parsed["p_optimistic"], parsed["p_neutral"], parsed["p_cautious"]]) - 1.0) < 1e-4

    def test_expected_move_bps_string_variants(self, analyst):
        variants = [
            ("+150 bps", 150.0),
            ("-50bp", -50.0),
            ("2.5%", 250.0),
            ("-1.0%", -100.0),
            ("80.5", 80.5),
        ]
        for s_val, expected in variants:
            raw = {
                "p_optimistic": 0.5,
                "p_neutral": 0.3,
                "p_cautious": 0.2,
                "expected_move_bps": s_val,
                "confidence": 0.8,
                "market_regime": "bull",
            }
            post = analyst._normalize_posterior(raw)
            assert post["expected_move_bps"] == expected

    def test_market_regime_synonym_normalization(self, analyst):
        test_cases = [
            ("BULL", "bull"),
            ("bullish", "bull"),
            ("uptrend", "bull"),
            ("BEAR", "bear"),
            ("bearish", "bear"),
            ("downtrend", "bear"),
            ("sideways", "sideways"),
            ("range-bound", "sideways"),
            ("flat", "sideways"),
            ("consolidation", "sideways"),
        ]
        for raw_regime, expected in test_cases:
            post = analyst._normalize_posterior({
                "p_optimistic": 0.4,
                "p_neutral": 0.3,
                "p_cautious": 0.3,
                "market_regime": raw_regime,
            })
            assert post["market_regime"] == expected

    def test_various_signal_block_delimiters(self, analyst):
        delimiters = [
            ("<signal_block>\n{{\"p_optimistic\": 0.6, \"p_neutral\": 0.3, \"p_cautious\": 0.1, \"expected_move_bps\": 50, \"confidence\": 0.8, \"market_regime\": \"bull\"}}\n</signal_block>", "bull"),
            ("<!-- SIGNAL_BLOCK: {{\"p_optimistic\": 0.2, \"p_neutral\": 0.2, \"p_cautious\": 0.6, \"expected_move_bps\": -50, \"confidence\": 0.8, \"market_regime\": \"bear\"}} -->", "bear"),
            ("```signal\n{{\"p_optimistic\": 0.3, \"p_neutral\": 0.5, \"p_cautious\": 0.2, \"expected_move_bps\": 0, \"confidence\": 0.8, \"market_regime\": \"sideways\"}}\n```", "sideways"),
        ]
        for block, expected_regime in delimiters:
            text = f"Report body\n{block}\nConclusion"
            parsed = analyst._parse_response(text)
            assert parsed["posterior"]["market_regime"] == expected_regime
            assert "Report body" in parsed["content"]
            assert "Conclusion" in parsed["content"]


# ==============================================================================
# 2. Test Suite: All 7 V2 Analyst Adapters
# ==============================================================================
class TestV2AnalystAdapters:
    """Verify all 7 V2 analyst adapters inherit from AnalystAgent and return posteriors."""

    def test_all_seven_inherit_from_analyst_agent(self):
        classes = [
            IndexAnalystV2,
            SectorAnalystV2,
            MarketAnalystV2,
            FundamentalsAnalystAgentV2,
            NewsAnalystV2,
            SocialMediaAnalystV2,
            ChipDistributionAnalystV2,
        ]
        for cls in classes:
            assert issubclass(cls, AnalystAgent), f"{cls.__name__} does not inherit from AnalystAgent"

    @pytest.mark.parametrize(
        "adapter_cls, expected_output_field, agent_id",
        [
            (MarketAnalystV2, "market_report", "market_analyst_v2"),
            (FundamentalsAnalystAgentV2, "fundamentals_report", "fundamentals_analyst_v2"),
            (NewsAnalystV2, "news_report", "news_analyst_v2"),
            (SocialMediaAnalystV2, "sentiment_report", "social_analyst_v2"),
            (ChipDistributionAnalystV2, "chip_report", "chip_distribution_analyst_v2"),
        ],
    )
    def test_adapter_execute_returns_clean_report_and_posterior(
        self, adapter_cls, expected_output_field, agent_id
    ):
        mock_llm = MagicMock()
        mock_response = AIMessage(
            content=(
                f"## Report for {agent_id}\nDetailed analysis content.\n"
                "```json:signal\n"
                "{\n"
                '  "p_optimistic": 0.60,\n'
                '  "p_neutral": 0.30,\n'
                '  "p_cautious": 0.10,\n'
                '  "expected_move_bps": 75.0,\n'
                '  "confidence": 0.80,\n'
                '  "market_regime": "bull"\n'
                "}\n"
                "```\n"
            )
        )
        mock_llm.invoke.return_value = mock_response

        agent = adapter_cls(llm=mock_llm, tool_ids=[])
        agent._invoke_llm_with_trace = MagicMock(return_value=mock_response)
        agent.invoke_with_tools = MagicMock(return_value=mock_response.content)
        agent._get_prompt_from_template = MagicMock(return_value="Mock prompt")

        state = {
            "ticker": "000001.SZ",
            "trade_date": "2026-03-31",
            "analysis_date": "2026-03-31",
            "prompt_overrides": {
                "system": "System instructions",
                "user": "User instructions",
                "analysis": "Analysis prompt",
            },
        }
        result = agent.execute(state)

        assert expected_output_field in result
        assert isinstance(result[expected_output_field], str)
        assert "```json:signal" not in result[expected_output_field]
        assert "Detailed analysis content" in result[expected_output_field]

        assert "analyst_posteriors" in result
        posteriors = result["analyst_posteriors"]
        assert agent_id in posteriors

        post = posteriors[agent_id]
        assert post["p_optimistic"] == 0.60
        assert post["p_neutral"] == 0.30
        assert post["p_cautious"] == 0.10
        assert abs((post["p_optimistic"] + post["p_neutral"] + post["p_cautious"]) - 1.0) < 1e-4

    def test_index_analyst_v2_cache_hit_returns_posteriors(self):
        cached_content = (
            "Cached index report content\n"
            "```json:signal\n"
            "{\n"
            '  "p_optimistic": 0.55,\n'
            '  "p_neutral": 0.35,\n'
            '  "p_cautious": 0.10,\n'
            '  "expected_move_bps": 40.0,\n'
            '  "confidence": 0.70,\n'
            '  "market_regime": "bull"\n'
            "}\n"
            "```\n"
        )
        with patch("core.agents.adapters.index_analyst_v2._get_cached_index_report", return_value=cached_content):
            agent = IndexAnalystV2(llm=None)
            agent._prepare_analysis_mode = MagicMock(return_value="tushare")
            state = {"ticker": "000001.SZ", "analysis_date": "2026-03-31"}
            result = agent.execute(state)

            assert "index_report" in result
            assert "Cached index report content" in result["index_report"]
            assert "```json:signal" not in result["index_report"]
            assert "analyst_posteriors" in result
            assert "index_analyst_v2" in result["analyst_posteriors"]
            assert result["analyst_posteriors"]["index_analyst_v2"]["p_optimistic"] == 0.55

    def test_index_analyst_v2_existing_report_in_state(self):
        existing_report = (
            "Existing index report in state\n"
            "```json:signal\n"
            "{\n"
            '  "p_optimistic": 0.65,\n'
            '  "p_neutral": 0.25,\n'
            '  "p_cautious": 0.10,\n'
            '  "expected_move_bps": 60.0,\n'
            '  "confidence": 0.75,\n'
            '  "market_regime": "bull"\n'
            "}\n"
            "```\n"
        ) + " " * 100
        agent = IndexAnalystV2(llm=None)
        agent._prepare_analysis_mode = MagicMock(return_value="tushare")
        # When posteriors already present, skip
        state_with_post = {
            "index_report": existing_report,
            "analyst_posteriors": {"index_analyst_v2": {"p_optimistic": 0.65}},
        }
        assert agent.execute(state_with_post) == {}

        # When posteriors missing, parse existing report
        state_without_post = {"index_report": existing_report}
        res = agent.execute(state_without_post)
        assert "analyst_posteriors" in res
        assert "index_analyst_v2" in res["analyst_posteriors"]
        assert res["analyst_posteriors"]["index_analyst_v2"]["p_optimistic"] == 0.65

    def test_sector_analyst_v2_existing_report_in_state(self):
        existing_report = (
            "Existing sector report\n"
            "```json:signal\n"
            "{\n"
            '  "p_optimistic": 0.40,\n'
            '  "p_neutral": 0.40,\n'
            '  "p_cautious": 0.20,\n'
            '  "expected_move_bps": 20.0,\n'
            '  "confidence": 0.60,\n'
            '  "market_regime": "sideways"\n'
            "}\n"
            "```\n"
        ) + " " * 100
        agent = SectorAnalystV2(llm=None)
        agent._prepare_analysis_mode = MagicMock(return_value="tushare")
        state_without_post = {"sector_report": existing_report}
        res = agent.execute(state_without_post)
        assert "analyst_posteriors" in res
        assert "sector_analyst_v2" in res["analyst_posteriors"]
        assert res["analyst_posteriors"]["sector_analyst_v2"]["market_regime"] == "sideways"


# ==============================================================================
# 3. Test Suite: Pure Python Shannon Entropy & JSD Calculation
# ==============================================================================
class TestJSDAndEntropyPurePython:
    """Verify information theory calculations without external dependencies."""

    def test_compute_shannon_entropy_properties(self):
        # H2([1, 0, 0]) = 0.0 (certainty)
        assert compute_shannon_entropy([1.0, 0.0, 0.0]) == 0.0

        # H2([0.5, 0.5]) = 1.0 (fair coin)
        assert abs(compute_shannon_entropy([0.5, 0.5]) - 1.0) < 1e-6

        # H2([1/3, 1/3, 1/3]) = log2(3) ~ 1.58496
        assert abs(compute_shannon_entropy([1/3, 1/3, 1/3]) - math.log2(3)) < 1e-4

    def test_compute_base2_jsd_identical_is_zero(self):
        identical = [
            [0.6, 0.2, 0.2],
            [0.6, 0.2, 0.2],
            [0.6, 0.2, 0.2],
        ]
        assert compute_base2_jsd(identical) < 1e-6

    def test_compute_base2_jsd_orthogonal_is_one(self):
        orthogonal = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        assert abs(compute_base2_jsd(orthogonal) - 1.0) < 1e-4

    def test_compute_base2_jsd_zero_entries_stability(self):
        # Ensure exact 0.0 probabilities do not trigger ZeroDivisionError or math domain errors
        dists = [
            [1.0, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 0.5, 0.5],
        ]
        jsd = compute_base2_jsd(dists)
        assert 0.0 <= jsd <= 1.0

    def test_compute_base2_jsd_empty_or_single(self):
        assert compute_base2_jsd([]) == 0.0
        assert compute_base2_jsd([[0.5, 0.5]]) == 0.0

    def test_calculate_base2_jsd_dict_api_all_seven(self):
        posts = {
            "index_analyst_v2": {"p_optimistic": 0.6, "p_neutral": 0.3, "p_cautious": 0.1},
            "sector_analyst_v2": {"p_optimistic": 0.65, "p_neutral": 0.25, "p_cautious": 0.1},
            "market_analyst_v2": {"p_optimistic": 0.55, "p_neutral": 0.35, "p_cautious": 0.1},
            "fundamentals_analyst_v2": {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1},
            "news_analyst_v2": {"p_optimistic": 0.6, "p_neutral": 0.3, "p_cautious": 0.1},
            "social_analyst_v2": {"p_optimistic": 0.5, "p_neutral": 0.4, "p_cautious": 0.1},
            "chip_distribution_analyst_v2": {"p_optimistic": 0.58, "p_neutral": 0.32, "p_cautious": 0.1},
        }
        jsd = calculate_base2_jsd(posts)
        # All 7 in strong consensus -> JSD is very low (< 0.02)
        assert jsd < 0.02


# ==============================================================================
# 4. Test Suite: CBS Gating & Dynamic Debate Rounds
# ==============================================================================
class TestCBSDebateGating:
    """Verify CBS routing, fast-path bypass, and dynamic debate rounds."""

    def test_cbs_routing_low_jsd_triggers_fast_path(self):
        # Consensus: JSD ~ 0.001 < 0.12
        consensus_posteriors = {
            "a1": {"p_optimistic": 0.75, "p_neutral": 0.20, "p_cautious": 0.05, "expected_move_bps": 120.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.72, "p_neutral": 0.22, "p_cautious": 0.06, "expected_move_bps": 115.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(consensus_posteriors, estimated_spread_bps=15.0)
        assert res["route"] == "fast_path"
        assert res["jsd"] < 0.12
        assert res["dynamic_debate_rounds"] == 0

    def test_cbs_routing_high_jsd_low_cbs_triggers_fast_path(self):
        # Disagreement (JSD ~ 0.38 >= 0.12) but tiny move (10 bps) -> CBS = 1.9 <= 15.0
        disagreement_low_stake = {
            "a1": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 10.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.10, "p_neutral": 0.20, "p_cautious": 0.70, "expected_move_bps": 10.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(disagreement_low_stake, estimated_spread_bps=15.0)
        assert res["route"] == "fast_path"
        assert res["jsd"] >= 0.12
        assert res["cbs_bps"] <= 15.0

    def test_cbs_routing_high_jsd_high_cbs_triggers_debate(self):
        # High disagreement (JSD ~ 0.62) and large move (150 bps) -> CBS = 46.5 > 15.0
        contested = {
            "a1": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 150.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85, "expected_move_bps": 150.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(contested, estimated_spread_bps=15.0, max_debate_rounds=3)
        assert res["route"] == "multi_round_debate"
        assert res["jsd"] >= 0.12
        assert res["cbs_bps"] > 15.0
        assert res["dynamic_debate_rounds"] in [2, 3]

    def test_cbs_routing_opposing_analysts_magnitude_not_canceling(self):
        # Bull expects +150 bps, Bear expects -150 bps. Magnitude must be 150 bps, not 0!
        opposing = {
            "bull_analyst": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 150.0, "confidence": 0.9},
            "bear_analyst": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": -150.0, "confidence": 0.9},
        }
        res = calculate_cbs_routing(opposing, estimated_spread_bps=15.0)
        assert res["weighted_expected_move_bps"] == 150.0
        assert res["cbs_bps"] > 15.0
        assert res["route"] == "multi_round_debate"

    def test_conditional_logic_method_and_state_injection(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        contested = {
            "a1": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 200.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": 200.0, "confidence": 0.9},
        }
        state: Dict[str, Any] = {
            "analyst_posteriors": contested,
            "estimated_spread_bps": 15.0,
            "investment_debate_state": {"count": 0, "current_response": "Bull Researcher"},
        }
        route = cl.should_trigger_multi_round_debate(state)
        assert route == "multi_round_debate"
        assert state["dynamic_debate_rounds"] in [2, 3]
        assert state["cbs_bps"] > 15.0

        # Now test should_continue_debate with dynamic rounds
        state["investment_debate_state"]["count"] = 2 * state["dynamic_debate_rounds"]
        next_speaker = cl.should_continue_debate(state)
        assert next_speaker == "Research Manager"

    def test_module_level_gateway(self):
        state = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1, "expected_move_bps": 50, "confidence": 0.8},
                "a2": {"p_optimistic": 0.7, "p_neutral": 0.2, "p_cautious": 0.1, "expected_move_bps": 50, "confidence": 0.8},
            },
            "estimated_spread_bps": 15.0,
        }
        assert should_trigger_multi_round_debate(state) == "fast_path"
        assert state.get("_risk_self_debate") is True


# ==============================================================================
# 5. Test Suite: RiskSelfDebateV2 Fast-Path Synthesis
# ==============================================================================
class TestRiskSelfDebateV2FastPath:
    """Verify RiskSelfDebateV2 supports fast-path inputs and fallback synthesis."""

    def test_metadata_contains_posteriors_and_investment_plan(self):
        inputs = {inp.name: inp for inp in RiskSelfDebateV2.metadata.inputs}
        outputs = {out.name: out for out in RiskSelfDebateV2.metadata.outputs}

        assert "analyst_posteriors" in inputs
        assert inputs["analyst_posteriors"].state_field == "analyst_posteriors"
        assert "investment_plan" in outputs

    def test_user_prompt_summarizes_analyst_posteriors(self):
        agent = RiskSelfDebateV2(llm=None)
        agent._get_prompt_from_template = MagicMock(return_value=None)
        state = {
            "ticker": "000001.SZ",
            "analysis_date": "2026-03-31",
            "investment_plan": "",  # Empty investment plan -> should synthesize from posteriors
            "analyst_posteriors": {
                "market_analyst_v2": {
                    "p_optimistic": 0.70,
                    "p_neutral": 0.20,
                    "p_cautious": 0.10,
                    "expected_move_bps": 80.0,
                    "market_regime": "bull",
                }
            },
        }
        prompt = agent._build_user_prompt("000001.SZ", "2026-03-31", state)
        assert "Fast-Path Consensus Synthesis" in prompt
        assert "market_analyst_v2: Bull=0.70" in prompt

    def test_execute_populates_investment_plan_and_debate_state_on_fast_path(self):
        mock_llm = MagicMock()
        mock_response = AIMessage(
            content=(
                "[Highly resilient scenario perspective]\nHigh elasticity upside.\n\n"
                "[defensive situational view]\nDefensive downside.\n\n"
                "[base case view]\nBase case balanced scenario.\n"
            )
        )
        mock_llm.invoke.return_value = mock_response

        agent = RiskSelfDebateV2(llm=mock_llm)
        agent._get_prompt_from_template = MagicMock(return_value="Mock Prompt")
        agent._invoke_llm_with_trace = MagicMock(return_value=mock_response)

        state = {
            "ticker": "000001.SZ",
            "analysis_date": "2026-03-31",
            "investment_plan": "",  # Missing investment_plan
            "investment_debate_state": {},  # Missing investment_debate_state
        }
        result = agent.execute(state)

        assert "investment_plan" in result
        assert "Fast-Path Tripartite Synthesis" in result["investment_plan"]
        assert "investment_debate_state" in result
        assert result["investment_debate_state"]["history"].startswith("Fast-Path")


# ==============================================================================
# 6. Test Suite: State Schema Registration & Concurrency Reducer
# ==============================================================================
class TestStateSchemaAndConcurrency:
    """Verify analyst_posteriors schema registration and concurrent merge_dict behavior."""

    def test_agent_state_annotations_registration(self):
        annotations = AgentState.__annotations__
        assert "analyst_posteriors" in annotations
        assert "estimated_spread_bps" in annotations
        assert "debate_jsd" in annotations
        assert "cbs_bps" in annotations
        assert "dynamic_debate_rounds" in annotations

    def test_workflow_state_annotations_registration(self):
        builder = WorkflowBuilder()
        schema = builder._get_default_state_schema()
        annotations = schema.__annotations__
        assert "analyst_posteriors" in annotations
        assert "estimated_spread_bps" in annotations
        assert "debate_jsd" in annotations
        assert "cbs_bps" in annotations
        assert "dynamic_debate_rounds" in annotations

    def test_merge_dict_concurrency_all_seven_analysts(self):
        # Simulate LangGraph concurrent parallel node execution
        accumulated: Dict[str, Any] = {}

        analyst_outputs = [
            {"index_analyst_v2": {"p_optimistic": 0.60, "market_regime": "bull"}},
            {"sector_analyst_v2": {"p_optimistic": 0.65, "market_regime": "bull"}},
            {"market_analyst_v2": {"p_optimistic": 0.55, "market_regime": "bull"}},
            {"fundamentals_analyst_v2": {"p_optimistic": 0.70, "market_regime": "bull"}},
            {"news_analyst_v2": {"p_optimistic": 0.58, "market_regime": "bull"}},
            {"social_analyst_v2": {"p_optimistic": 0.52, "market_regime": "bull"}},
            {"chip_distribution_analyst_v2": {"p_optimistic": 0.62, "market_regime": "bull"}},
        ]

        for out in analyst_outputs:
            accumulated = merge_dict(accumulated, out)

        assert len(accumulated) == 7
        for out in analyst_outputs:
            aid = list(out.keys())[0]
            assert aid in accumulated
            assert accumulated[aid]["p_optimistic"] == out[aid]["p_optimistic"]
