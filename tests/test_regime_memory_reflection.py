"""
Unit Test Suite for Milestone 3 (CARE-Agents R3):
Regime-Conditioned Episodic Memory & Counterfactual Credit Assignment

Coverage:
1. Mem0AgentMemory Metadata Normalization:
   - Mandatory keys: market_regime, volatility_quintile, brier_calibration_error
   - Defaults for legacy callers (prevent KeyErrors)
   - Value validation and clamping
2. Regime Circuit-Breaker Memory Retrieval:
   - Filtering contradicting regime memories when regime_confidence >= 0.5
   - Bypassing circuit-breaker when regime_confidence < 0.5
   - Numerical boundary testing (0.500 vs 0.499)
   - Scope limited to target decision agents (bull/bear researcher, manager, trader, risk manager)
   - Mem0AgentMemory.search_memories client-side circuit breaker integration
3. 4-Quadrant Counterfactual Credit Assignment:
   - Q1: Vindicated & Followed (+|R| * conf)
   - Q2: Vindicated & Overridden (+|R| counterfactual alpha)
   - Q3: Faulty & Followed (-|R| * conf)
   - Q4: Faulty & Overridden (-0.2 * |R| mitigated fault)
   - Stance & action parsing (string/numeric) and boundary conditions
4. Reflection Prompt Injection & Reflector Integration:
   - Prompt formatting with quadrant label, attribution score, and directive
   - Reflector component reflection with mock LLM
   - Researcher, trader, and judge reflection methods with counterfactual context
   - Helper function run_reflection and prompt builders
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List

from core.memory.memory_manager import (
    Mem0AgentMemory,
    AgentMemory,
    circuit_breaker_memory_filter,
    _CIRCUIT_BREAKER_AGENTS,
)
from core.agents.reflection_helper import (
    calculate_counterfactual_attribution,
    format_attribution_prompt_block,
    run_reflection,
)
from core.agents.reflection_prompts import (
    build_trade_reflection_user_prompt,
    build_analysis_reflection_user_prompt,
    build_debate_reflection_user_prompt,
)
from tradingagents.graph.reflection import Reflector


# ==============================================================================
# 1. Metadata Normalization Unit Tests
# ==============================================================================

class TestMemoryMetadataNormalization:
    """Verifies that mandatory metadata keys are strictly enforced with safe defaults."""

    def test_store_metadata_defaults_for_empty_dict(self):
        """When empty dict is passed, all 3 mandatory keys are populated with defaults."""
        norm = Mem0AgentMemory._normalize_store_metadata({})
        assert norm["market_regime"] == "sideways"
        assert norm["volatility_quintile"] == 3
        assert norm["brier_calibration_error"] == 0.0
        assert norm["source"] == "legacy_agent_memory_runtime"

    def test_store_metadata_defaults_for_none(self):
        """When None is passed, sensible defaults prevent KeyErrors."""
        norm = Mem0AgentMemory._normalize_store_metadata(None)
        assert norm["market_regime"] == "sideways"
        assert norm["volatility_quintile"] == 3
        assert norm["brier_calibration_error"] == 0.0

    def test_store_metadata_valid_regimes_case_insensitivity(self):
        """Valid regimes ('bull', 'bear', 'sideways') are normalized to lowercase."""
        for reg in ["bull", "BULL", " Bull ", "bear", "BEAR", " Bear ", "sideways", "SIDEWAYS"]:
            norm = Mem0AgentMemory._normalize_store_metadata({"market_regime": reg})
            expected = reg.strip().lower()
            assert norm["market_regime"] == expected

    def test_store_metadata_invalid_regime_fallback(self):
        """Invalid or unknown regime falls back to 'sideways'."""
        for invalid in ["volatile", "neutral", "crash", "unknown", 123, None, ""]:
            norm = Mem0AgentMemory._normalize_store_metadata({"market_regime": invalid})
            assert norm["market_regime"] == "sideways"

    def test_store_metadata_volatility_quintile_clamping(self):
        """volatility_quintile is coerced to int and clamped within [1, 5]."""
        # Lower bound
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": 0})["volatility_quintile"] == 1
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": -10})["volatility_quintile"] == 1
        # Upper bound
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": 6})["volatility_quintile"] == 5
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": 100})["volatility_quintile"] == 5
        # Valid values
        for v in [1, 2, 3, 4, 5]:
            assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": v})["volatility_quintile"] == v
            assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": str(v)})["volatility_quintile"] == v
        # Invalid type falls back to default 3
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": "invalid"})["volatility_quintile"] == 3
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": None})["volatility_quintile"] == 3

    def test_store_metadata_brier_calibration_error_validation(self):
        """brier_calibration_error is coerced to float and clamped to >= 0.0."""
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": 0.42})["brier_calibration_error"] == 0.42
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": "0.15"})["brier_calibration_error"] == 0.15
        # Negative clamped to 0.0
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": -0.5})["brier_calibration_error"] == 0.0
        # Invalid type falls back to 0.0
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": "bad"})["brier_calibration_error"] == 0.0
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": None})["brier_calibration_error"] == 0.0

    def test_store_metadata_preserves_ticker_and_custom_keys(self):
        """Existing ticker/symbol normalization and custom caller keys are preserved."""
        raw = {
            "ticker": "600519",
            "market_regime": "bull",
            "volatility_quintile": 2,
            "brier_calibration_error": 0.03,
            "custom_metric": 99.5,
            "stance": "optimistic",
        }
        norm = Mem0AgentMemory._normalize_store_metadata(raw)
        assert norm["ticker"] == "600519"
        assert norm["symbol"] == "600519"
        assert norm["object_type"] == "stock"
        assert norm["object_key"] == "600519"
        assert norm["custom_metric"] == 99.5
        assert norm["stance"] == "optimistic"

    def test_recall_filters_normalization_defaults(self):
        """_normalize_recall_filters enforces mandatory keys with defaults for legacy callers."""
        norm = Mem0AgentMemory._normalize_recall_filters(None)
        assert norm["market_regime"] == "sideways"
        assert norm["volatility_quintile"] == 3
        assert norm["brier_calibration_error"] == 0.0

        norm_empty = Mem0AgentMemory._normalize_recall_filters({})
        assert norm_empty["market_regime"] == "sideways"
        assert norm_empty["volatility_quintile"] == 3
        assert norm_empty["brier_calibration_error"] == 0.0

    def test_recall_filters_preserves_provided_keys(self):
        """When caller provides specific filters, they are validated and preserved."""
        raw = {"ticker": "000001.SZ", "market_regime": "bear", "volatility_quintile": 4}
        norm = Mem0AgentMemory._normalize_recall_filters(raw)
        assert norm["ticker"] == "000001.SZ"
        assert norm["market_regime"] == "bear"
        assert norm["volatility_quintile"] == 4
        assert norm["brier_calibration_error"] == 0.0


# ==============================================================================
# 2. Regime Circuit-Breaker Unit Tests
# ==============================================================================

class TestRegimeCircuitBreaker:
    """Verifies regime circuit-breaker on memory retrieval."""

    @pytest.fixture
    def sample_memories(self) -> List[Dict[str, Any]]:
        return [
            {"id": "m1", "content": "Bull rally dip buying lesson", "metadata": {"market_regime": "bull", "volatility_quintile": 2}},
            {"id": "m2", "content": "Bull momentum continuation lesson", "metadata": {"market_regime": "bull", "volatility_quintile": 1}},
            {"id": "m3", "content": "Bear crash stop-loss lesson", "metadata": {"market_regime": "bear", "volatility_quintile": 5}},
            {"id": "m4", "content": "Bear shorting breakdown lesson", "metadata": {"market_regime": "bear", "volatility_quintile": 4}},
            {"id": "m5", "content": "Sideways mean reversion range lesson", "metadata": {"market_regime": "sideways", "volatility_quintile": 3}},
        ]

    def test_circuit_active_high_confidence_bear(self, sample_memories):
        """When confidence >= 0.5 in bear regime, only bear memories are retained."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.8,
            agent_id="trader_v2",
        )
        assert len(filtered) == 2
        for m in filtered:
            assert m["metadata"]["market_regime"] == "bear"
        assert {m["id"] for m in filtered} == {"m3", "m4"}

    def test_circuit_active_high_confidence_bull(self, sample_memories):
        """When confidence >= 0.5 in bull regime, only bull memories are retained."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bull",
            regime_confidence=0.75,
            agent_id="bull_researcher_v2",
        )
        assert len(filtered) == 2
        for m in filtered:
            assert m["metadata"]["market_regime"] == "bull"
        assert {m["id"] for m in filtered} == {"m1", "m2"}

    def test_circuit_active_high_confidence_sideways(self, sample_memories):
        """When confidence >= 0.5 in sideways regime, only sideways memories are retained."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="sideways",
            regime_confidence=0.6,
            agent_id="risk_manager_v2",
        )
        assert len(filtered) == 1
        assert filtered[0]["id"] == "m5"
        assert filtered[0]["metadata"]["market_regime"] == "sideways"

    def test_circuit_bypassed_low_confidence(self, sample_memories):
        """When confidence < 0.5, circuit breaker is bypassed to allow cross-regime hedging insights."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.45,
            agent_id="trader_v2",
        )
        # All 5 memories are returned regardless of stored regime
        assert len(filtered) == 5

    def test_circuit_boundary_values(self, sample_memories):
        """Exact boundary tests at 0.500 vs 0.499."""
        # 0.500 -> Circuit ACTIVE
        active = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.500,
            agent_id="trader_v2",
        )
        assert len(active) == 2

        # 0.499 -> Circuit BYPASSED
        bypassed = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.499,
            agent_id="trader_v2",
        )
        assert len(bypassed) == 5

        # 0.0 -> Circuit BYPASSED
        zero_conf = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.0,
            agent_id="trader_v2",
        )
        assert len(zero_conf) == 5

    def test_circuit_agents_whitelist(self, sample_memories):
        """Circuit breaker applies to all 5 target agents and their v1/v2 aliases."""
        target_agents = [
            "bull_researcher", "bull_researcher_v2",
            "bear_researcher", "bear_researcher_v2",
            "research_manager", "research_manager_v2",
            "trader", "trader_v2",
            "risk_manager", "risk_manager_v2",
        ]
        for aid in target_agents:
            res = circuit_breaker_memory_filter(
                sample_memories,
                current_regime="bull",
                regime_confidence=0.9,
                agent_id=aid,
            )
            assert len(res) == 2, f"Failed for target agent {aid}"

    def test_non_circuit_agents_bypassed(self, sample_memories):
        """Agents not in circuit breaker list (e.g. analysts) are never filtered."""
        non_circuit = [
            "index_analyst_v2", "sector_analyst_v2", "market_analyst_v2",
            "fundamentals_analyst_v2", "news_analyst_v2", "social_analyst_v2",
            "chip_distribution_analyst_v2", "custom_analyst",
        ]
        for aid in non_circuit:
            res = circuit_breaker_memory_filter(
                sample_memories,
                current_regime="bear",
                regime_confidence=0.95,
                agent_id=aid,
            )
            assert len(res) == 5, f"Non-circuit agent {aid} should not be filtered"

    def test_mem0_agent_memory_search_with_circuit_breaker(self):
        """Mem0AgentMemory.search_memories integrates circuit-breaker filtering."""
        mem = Mem0AgentMemory("trader_v2")

        # Mock items returned by service
        class MockItem:
            def __init__(self, item_id, content, regime):
                self.id = item_id
                self.memory = content
                self.score = 0.9
                self.metadata = {"market_regime": regime, "legacy_situation": content}

        mock_svc = MagicMock()
        mock_svc.recall.return_value = [
            MockItem("m1", "Bull memory 1", "bull"),
            MockItem("m2", "Bear memory 1", "bear"),
            MockItem("m3", "Bull memory 2", "bull"),
            MockItem("m4", "Bear memory 2", "bear"),
        ]

        with patch("core.memory.service.get_memory_service", return_value=mock_svc):
            # High confidence bear market -> only bear memories returned
            results_high = mem.search_memories(
                query="trade advice",
                n_results=5,
                current_regime="bear",
                regime_confidence=0.85,
            )
            assert len(results_high) == 2
            assert all(r["metadata"]["market_regime"] == "bear" for r in results_high)

            # Low confidence bear market (< 0.5) -> circuit bypassed, cross-regime returned
            results_low = mem.search_memories(
                query="trade advice",
                n_results=5,
                current_regime="bear",
                regime_confidence=0.35,
            )
            assert len(results_low) == 4

            # State dictionary parameter passing
            results_state = mem.search_memories(
                query="trade advice",
                n_results=5,
                state={"market_regime": "bull", "regime_confidence": 0.9},
            )
            assert len(results_state) == 2
            assert all(r["metadata"]["market_regime"] == "bull" for r in results_state)


# ==============================================================================
# 3. 4-Quadrant Counterfactual Credit Assignment Unit Tests
# ==============================================================================

class TestCounterfactualCreditAssignment:
    """Verifies marginal contribution calculation across all 4 quadrants."""

    def test_q1_vindicated_and_followed_bull(self):
        """Q1: Bull recommended buy, manager bought, trade gained +4%.
        Attribution = +|R| * conf.
        """
        attr = calculate_counterfactual_attribution(
            agent_stance=+1.0,
            realized_return=+0.04,
            manager_action="buy",
            agent_confidence=0.9,
        )
        assert attr["quadrant"] == "Q1_Vindicated_Followed"
        assert attr["attribution_score"] == pytest.approx(0.04 * 0.9)
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is True
        assert "positive alpha" in attr["directive"]

    def test_q1_vindicated_and_followed_bear(self):
        """Q1: Bear recommended sell, manager sold, trade gained +3% (or short gained)."""
        attr = calculate_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=-0.03,  # Negative return on stock vindicates short/bear
            manager_action="sell",
            agent_confidence=0.85,
        )
        assert attr["quadrant"] == "Q1_Vindicated_Followed"
        assert attr["attribution_score"] == pytest.approx(0.03 * 0.85)
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is True

    def test_q2_vindicated_and_overridden_counterfactual_alpha(self):
        """Q2: Bear warned sell, manager bought anyway, trade suffered -5% loss.
        Attribution = +|R| (Counterfactual Alpha acknowledged despite portfolio loss).
        """
        attr = calculate_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=-0.05,
            manager_action="buy",
            agent_confidence=0.8,
        )
        assert attr["quadrant"] == "Q2_Vindicated_Overridden"
        assert attr["attribution_score"] == pytest.approx(0.05)
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is False
        assert "overruled" in attr["directive"]

    def test_q2_vindicated_and_overridden_bull(self):
        """Q2: Bull recommended buy, manager sat in hold, stock surged +8%.
        Attribution = +|R| = +0.08.
        """
        attr = calculate_counterfactual_attribution(
            agent_stance=+1.0,
            realized_return=+0.08,
            manager_action="hold",
            agent_confidence=0.75,
        )
        assert attr["quadrant"] == "Q2_Vindicated_Overridden"
        assert attr["attribution_score"] == pytest.approx(0.08)
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is False

    def test_q3_faulty_and_followed(self):
        """Q3: Bull urged buy, manager bought, trade lost -6%.
        Attribution = -|R| * conf.
        """
        attr = calculate_counterfactual_attribution(
            agent_stance=+1.0,
            realized_return=-0.06,
            manager_action="buy",
            agent_confidence=0.9,
        )
        assert attr["quadrant"] == "Q3_Faulty_Followed"
        assert attr["attribution_score"] == pytest.approx(-0.06 * 0.9)
        assert attr["is_vindicated"] is False
        assert attr["is_followed"] is True
        assert "causing the loss" in attr["directive"]

    def test_q4_faulty_and_overridden_mitigated_fault(self):
        """Q4: Bear advocated sell, manager overruled and bought, trade gained +7%.
        Attribution = -0.2 * |R| (Fault was mitigated by manager override).
        """
        attr = calculate_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=+0.07,
            manager_action="buy",
            agent_confidence=0.8,
        )
        assert attr["quadrant"] == "Q4_Faulty_Overridden"
        assert attr["attribution_score"] == pytest.approx(-0.2 * 0.07)
        assert attr["is_vindicated"] is False
        assert attr["is_followed"] is False
        assert "shielded the portfolio" in attr["directive"]

    def test_string_inputs_normalization(self):
        """String stances ('bull', 'bear', 'buy', 'sell') and manager actions are parsed cleanly."""
        attr_bull = calculate_counterfactual_attribution("bull", +0.03, "buy", 0.8)
        assert attr_bull["quadrant"] == "Q1_Vindicated_Followed"

        attr_bear = calculate_counterfactual_attribution("bear", -0.04, "buy", 0.8)
        assert attr_bear["quadrant"] == "Q2_Vindicated_Overridden"

        attr_sell = calculate_counterfactual_attribution("sell", +0.05, "buy", 0.8)
        assert attr_sell["quadrant"] == "Q4_Faulty_Overridden"

    def test_zero_return_boundary(self):
        """Zero realized return produces 0.0 attribution without exception."""
        attr = calculate_counterfactual_attribution(agent_stance=+1.0, realized_return=0.0, manager_action="buy")
        assert attr["attribution_score"] == 0.0

    def test_format_attribution_prompt_block(self):
        """format_attribution_prompt_block outputs correct headers and fields."""
        attr = calculate_counterfactual_attribution(agent_stance=-1.0, realized_return=-0.04, manager_action="buy")
        block = format_attribution_prompt_block(attr)
        assert "=== Counterfactual Credit Assignment ===" in block
        assert "- Status: Q2_Vindicated_Overridden" in block
        assert "- Attribution Score: +0.040" in block
        assert "- Directive:" in block


# ==============================================================================
# 4. Reflection Prompt Injection & Reflector Integration Tests
# ==============================================================================

class TestReflectionPromptInjection:
    """Verifies that counterfactual attribution is correctly formatted and injected."""

    class MockLLM:
        def __init__(self):
            self.last_messages = None

        def invoke(self, messages):
            self.last_messages = messages
            mock_res = MagicMock()
            mock_res.content = '{"reasoning": "mock reasoning", "improvement": "mock improvement", "summary": "mock summary", "query": "mock query"}'
            return mock_res

    def test_reflector_reflect_bull_researcher_injects_counterfactual(self):
        """Reflector.reflect_bull_researcher passes attribution context to prompt."""
        mock_llm = self.MockLLM()
        reflector = Reflector(mock_llm)

        state = {
            "investment_debate_state": {
                "bull_history": "Bull thesis: strong momentum and earnings acceleration.",
                "bear_history": "Bear thesis: macro risks.",
                "judge_decision": "Decision: BUY 100 shares.",
            },
            "final_trade_decision": "Action: BUY",
            "market_report": "Market index up +1.2%",
            "sentiment_report": "Sentiment bullish",
        }
        mock_memory = MagicMock()

        # Trade gained +5%: Bull is Vindicated & Followed
        reflector.reflect_bull_researcher(state, returns_losses=+0.05, bull_memory=mock_memory)

        assert mock_llm.last_messages is not None
        human_msg = mock_llm.last_messages[1][1]
        assert "=== Counterfactual Credit Assignment ===" in human_msg
        assert "Q1_Vindicated_Followed" in human_msg
        assert "+0.040" in human_msg or "+0.050" in human_msg  # depends on conf default (0.8 * 0.05 = 0.040)
        assert "Bull thesis" in human_msg
        assert mock_memory.add_situations.called

    def test_reflector_reflect_bear_researcher_counterfactual_alpha(self):
        """Reflector.reflect_bear_researcher acknowledges counterfactual alpha on loss."""
        mock_llm = self.MockLLM()
        reflector = Reflector(mock_llm)

        state = {
            "investment_debate_state": {
                "bull_history": "Bull arguments.",
                "bear_history": "Bear warning: impending liquidation cascade.",
                "judge_decision": "Decision: BUY",
            },
            "final_trade_decision": "Action: BUY",
            "market_report": "Severe sell-off",
        }
        mock_memory = MagicMock()

        # Trade lost -4%: Bear is Vindicated & Overridden
        reflector.reflect_bear_researcher(state, returns_losses=-0.04, bear_memory=mock_memory)

        assert mock_llm.last_messages is not None
        human_msg = mock_llm.last_messages[1][1]
        assert "=== Counterfactual Credit Assignment ===" in human_msg
        assert "Q2_Vindicated_Overridden" in human_msg
        assert "+0.040" in human_msg  # Counterfactual alpha recognized!
        assert "overruled" in human_msg
        assert mock_memory.add_situations.called

    def test_reflector_fallback_when_no_attribution(self):
        """Reflector._reflect_on_component cleanly falls back when attribution_context is None."""
        mock_llm = self.MockLLM()
        reflector = Reflector(mock_llm)

        res = reflector._reflect_on_component("TEST", "some report", "some situation", returns_losses=0.03)
        assert mock_llm.last_messages is not None
        human_msg = mock_llm.last_messages[1][1]
        assert "Returns: 0.03" in human_msg
        assert "=== Counterfactual Credit Assignment ===" not in human_msg

    def test_prompt_builders_accept_attribution_context(self):
        """build_trade_reflection, build_analysis_reflection, and build_debate_reflection include attribution."""
        attr = calculate_counterfactual_attribution(agent_stance=+1.0, realized_return=+0.03, manager_action="buy")

        # Debate prompt
        debate_prompt = build_debate_reflection_user_prompt(
            ticker="000001.SZ",
            debate_history="History text",
            conclusion="Conclusion text",
            attribution_context=attr,
        )
        assert "=== Counterfactual Credit Assignment ===" in debate_prompt
        assert "Q1_Vindicated_Followed" in debate_prompt

        # Analysis prompt
        analysis_prompt = build_analysis_reflection_user_prompt(
            ticker="000001.SZ",
            report={"content": "Report text", "stance": "bull"},
            attribution_context=attr,
        )
        assert "=== Counterfactual Credit Assignment ===" in analysis_prompt
        assert "Q1_Vindicated_Followed" in analysis_prompt

        # Trade prompt
        trade_prompt = build_trade_reflection_user_prompt(
            trade_info=MagicMock(code="000001", name="PingAn", first_buy_date="2026-05-01"),
            ai_review=MagicMock(summary="Review text", strengths=[], weaknesses=[], suggestions=[], plan_deviation=""),
            attribution_context=attr,
        )
        assert "=== Counterfactual Credit Assignment ===" in trade_prompt
        assert "Q1_Vindicated_Followed" in trade_prompt

    @pytest.mark.asyncio
    async def test_run_reflection_stores_attribution_metadata(self):
        """run_reflection stores attribution_score and attribution_quadrant in mem0 metadata."""
        attr = calculate_counterfactual_attribution(agent_stance=-1.0, realized_return=-0.05, manager_action="buy")

        mock_svc = MagicMock()
        mock_svc.available = True

        stored_calls = []

        async def mock_store(messages, **kwargs):
            stored_calls.append({"messages": messages, "kwargs": kwargs})
            mock_res = MagicMock()
            mock_res.success = True
            return mock_res

        mock_svc.store = mock_store

        with patch("core.agents.reflection_helper.get_memory_service", return_value=mock_svc):
            success = await run_reflection(
                db=MagicMock(),
                user_id="user1",
                agent_id="bear_researcher_v2",
                scope=MagicMock(),
                memory_kind="trade_lesson",
                system_prompt="sys prompt",
                user_prompt="user prompt",
                fallback_content="fallback content",
                fallback_metadata={"ticker": "000001.SZ"},
                llm_client=None,  # triggers fallback content write
                attribution_context=attr,
            )

        assert len(stored_calls) == 1
        meta = stored_calls[0]["kwargs"]["metadata"]
        assert meta["attribution_score"] == 0.05
        assert meta["attribution_quadrant"] == "Q2_Vindicated_Overridden"
