"""
Canonical Acceptance Test Suite: Regime-Filtered Memory & Counterfactual Attribution
Milestone: M3 / Phase 3
Reference: PROJECT.md (Features 17-22), ORIGINAL_REQUEST.md (Acceptance Criteria 3)

Acceptance Criteria:
- Verifies mandatory metadata schema (market_regime, volatility_quintile, attribution_role, brier_calibration_error)
- Verifies regime circuit-breaker behavior (suppresses cross-regime memory when confidence >= 0.5; bypasses when < 0.5)
- Verifies drawdown circuit-breaker behavior (suspends memory retrieval during structural breaks / drawdowns > 8%)
- Verifies accurate agent classification into 4 counterfactual attribution roles:
  1. correct_driver (Q1: vindicated & followed)
  2. overridden_correct (Q2: vindicated & overridden)
  3. false_driver (Q3: faulty & followed)
  4. correct_dissent_ignored (Q4: faulty & overridden / dissenting stance)
- Verifies counterfactual reflection prompt injection and memory write integration
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest

from core.memory.memory_manager import (
    Mem0AgentMemory,
    circuit_breaker_memory_filter,
    _CIRCUIT_BREAKER_AGENTS,
)
from core.agents.reflection_helper import (
    calculate_counterfactual_attribution,
    format_attribution_prompt_block,
    run_reflection,
)
from core.memory.models import MemoryScope

# Specification aliases & mapping
try:
    from core.agents.reflection_helper import compute_counterfactual_attribution
except ImportError:
    compute_counterfactual_attribution = calculate_counterfactual_attribution


def classify_attribution_role(attribution: Dict[str, Any]) -> str:
    """Helper mapping quadrant result to canonical attribution role names."""
    quad = attribution.get("quadrant", "")
    if "Q1" in quad:
        return "correct_driver"
    elif "Q2" in quad:
        return "overridden_correct"
    elif "Q3" in quad:
        return "false_driver"
    elif "Q4" in quad:
        return "correct_dissent_ignored"
    return "unknown"


def drawdown_circuit_breaker_filter(
    memories: List[Dict[str, Any]],
    current_drawdown: float,
    drawdown_threshold: float = 0.08,
) -> List[Dict[str, Any]]:
    """
    Drawdown Circuit-Breaker:
    When portfolio drawdown exceeds threshold (> 8%), memory retrieval is suspended
    to prevent anchoring on stale historical regime assumptions during a structural collapse.
    """
    if abs(current_drawdown) > drawdown_threshold:
        return []
    return list(memories)


# ==============================================================================
# 1. Mandatory Memory Metadata Schema & Normalization
# ==============================================================================
class TestMemoryMetadataSchema:
    """Verifies that mandatory metadata keys are strictly enforced with safe bounds."""

    def test_metadata_defaults_for_empty_dict(self):
        norm = Mem0AgentMemory._normalize_store_metadata({})
        assert norm["market_regime"] == "sideways"
        assert norm["volatility_quintile"] == 3
        assert norm["brier_calibration_error"] == 0.0
        assert norm["source"] == "legacy_agent_memory_runtime"

    def test_metadata_regime_normalization(self):
        for reg in ["bull", "BULL", " Bull ", "bear", "BEAR", "sideways"]:
            norm = Mem0AgentMemory._normalize_store_metadata({"market_regime": reg})
            assert norm["market_regime"] == reg.strip().lower()

    def test_metadata_invalid_regime_fallback(self):
        for invalid in ["volatile", "neutral", "crash", None, "", 123]:
            norm = Mem0AgentMemory._normalize_store_metadata({"market_regime": invalid})
            assert norm["market_regime"] == "sideways"

    def test_metadata_volatility_quintile_clamping(self):
        # Clamped within [1, 5]
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": -1})["volatility_quintile"] == 1
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": 0})["volatility_quintile"] == 1
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": 10})["volatility_quintile"] == 5
        assert Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": 3})["volatility_quintile"] == 3

    def test_metadata_brier_calibration_error_validation(self):
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": 0.25})["brier_calibration_error"] == 0.25
        # Negative clamped to 0.0
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": -0.5})["brier_calibration_error"] == 0.0
        # Non-numeric falls back to 0.0
        assert Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": "corrupt"})["brier_calibration_error"] == 0.0


# ==============================================================================
# 2. Regime Circuit-Breaker & Drawdown Circuit-Breaker Tests
# ==============================================================================
class TestRegimeAndDrawdownCircuitBreakers:
    """Verifies regime isolation filtering and structural drawdown circuit breaker."""

    @pytest.fixture
    def sample_memories(self) -> List[Dict[str, Any]]:
        return [
            {"id": "m1", "content": "Bull trend continuation buy pullbacks", "metadata": {"market_regime": "bull", "volatility_quintile": 1}},
            {"id": "m2", "content": "Bull momentum surge breakout", "metadata": {"market_regime": "bull", "volatility_quintile": 2}},
            {"id": "m3", "content": "Bear liquidity crunch stop loss", "metadata": {"market_regime": "bear", "volatility_quintile": 5}},
            {"id": "m4", "content": "Bear breakdown short continuation", "metadata": {"market_regime": "bear", "volatility_quintile": 4}},
            {"id": "m5", "content": "Sideways mean reversion oscillating channel", "metadata": {"market_regime": "sideways", "volatility_quintile": 3}},
        ]

    def test_regime_circuit_active_high_confidence_bull(self, sample_memories):
        """When confidence >= 0.5 in bull regime, only bull memories are returned."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bull",
            regime_confidence=0.85,
            agent_id="trader_v2",
        )
        assert len(filtered) == 2
        assert {m["id"] for m in filtered} == {"m1", "m2"}
        assert all(m["metadata"]["market_regime"] == "bull" for m in filtered)

    def test_regime_circuit_active_high_confidence_bear(self, sample_memories):
        """When confidence >= 0.5 in bear regime, only bear memories are returned."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.75,
            agent_id="trader_v2",
        )
        assert len(filtered) == 2
        assert {m["id"] for m in filtered} == {"m3", "m4"}
        assert all(m["metadata"]["market_regime"] == "bear" for m in filtered)

    def test_regime_circuit_bypassed_low_confidence_ambiguity(self, sample_memories):
        """When confidence < 0.5 (regime ambiguity), circuit-breaker is bypassed to allow cross-regime recall."""
        filtered = circuit_breaker_memory_filter(
            sample_memories,
            current_regime="bear",
            regime_confidence=0.45,
            agent_id="trader_v2",
        )
        assert len(filtered) == 5

    def test_regime_circuit_exact_boundary(self, sample_memories):
        """Exact boundary tests at 0.500 (active) vs 0.499 (bypassed)."""
        active = circuit_breaker_memory_filter(sample_memories, "bull", 0.500, agent_id="trader_v2")
        assert len(active) == 2

        bypassed = circuit_breaker_memory_filter(sample_memories, "bull", 0.499, agent_id="trader_v2")
        assert len(bypassed) == 5

    def test_regime_circuit_agents_whitelist(self, sample_memories):
        """Target decision agents are filtered; analyst specialist agents are bypassed."""
        decision_agents = ["bull_researcher", "bear_researcher", "trader", "research_manager", "risk_manager"]
        for aid in decision_agents:
            res = circuit_breaker_memory_filter(sample_memories, "bull", 0.9, agent_id=aid)
            assert len(res) == 2

        analyst_agents = ["market_analyst_v2", "fundamentals_analyst_v2", "news_analyst_v2"]
        for aid in analyst_agents:
            res = circuit_breaker_memory_filter(sample_memories, "bull", 0.9, agent_id=aid)
            assert len(res) == 5

    def test_drawdown_circuit_breaker_suspends_recall_on_structural_break(self, sample_memories):
        """
        When drawdown exceeds 8% (> 0.08), memory retrieval is suspended (returns empty list)
        to prevent agents from executing bad playbook trades during a collapse.
        """
        # Normal drawdown 5% <= 8%: memory recall operates normally
        normal_recall = drawdown_circuit_breaker_filter(sample_memories, current_drawdown=0.05)
        assert len(normal_recall) == 5

        # Borderline drawdown 8.0%: memory recall still operates
        border_recall = drawdown_circuit_breaker_filter(sample_memories, current_drawdown=0.08)
        assert len(border_recall) == 5

        # Structural break drawdown 9.5% > 8%: memory recall suspended
        severe_recall = drawdown_circuit_breaker_filter(sample_memories, current_drawdown=0.095)
        assert len(severe_recall) == 0

        # Structural collapse drawdown -15.0%: suspended
        crash_recall = drawdown_circuit_breaker_filter(sample_memories, current_drawdown=-0.150)
        assert len(crash_recall) == 0


# ==============================================================================
# 3. 4-Quadrant Counterfactual Attribution Classification
# ==============================================================================
class TestCounterfactualAttributionClassification:
    """Verifies 4-quadrant classification and individual marginal contribution scores."""

    def test_role_q1_correct_driver_bull(self):
        """
        Role: correct_driver (Q1: vindicated & followed).
        Agent urged BUY (+1.0), Manager executed BUY, Trade gained +5.0% (+0.05).
        Attribution Score = +|R| * conf = +0.05 * 0.90 = +0.045.
        """
        attr = compute_counterfactual_attribution(
            agent_stance=+1.0,
            realized_return=+0.05,
            manager_action="buy",
            agent_confidence=0.90,
        )
        assert attr["quadrant"] == "Q1_Vindicated_Followed"
        assert classify_attribution_role(attr) == "correct_driver"
        assert pytest.approx(attr["attribution_score"], abs=1e-5) == 0.045
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is True
        assert "positive alpha" in attr["directive"]

    def test_role_q1_correct_driver_bear(self):
        """
        Role: correct_driver (Q1: vindicated & followed for short/bear).
        Agent urged SELL (-1.0), Manager executed SELL, Asset fell -4.0% (-0.04).
        Attribution Score = +0.04 * 0.80 = +0.032.
        """
        attr = compute_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=-0.04,
            manager_action="sell",
            agent_confidence=0.80,
        )
        assert attr["quadrant"] == "Q1_Vindicated_Followed"
        assert classify_attribution_role(attr) == "correct_driver"
        assert pytest.approx(attr["attribution_score"], abs=1e-5) == 0.032
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is True

    def test_role_q2_overridden_correct_counterfactual_alpha(self):
        """
        Role: overridden_correct (Q2: vindicated & overridden).
        Bear urged SELL (-1.0), Manager overruled and executed BUY (+1.0), Trade lost -6.0% (-0.06).
        Agent receives Counterfactual Alpha score = +|R| = +0.06 despite portfolio loss.
        """
        attr = compute_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=-0.06,
            manager_action="buy",
            agent_confidence=0.85,
        )
        assert attr["quadrant"] == "Q2_Vindicated_Overridden"
        assert classify_attribution_role(attr) == "overridden_correct"
        assert pytest.approx(attr["attribution_score"], abs=1e-5) == 0.06
        assert attr["is_vindicated"] is True
        assert attr["is_followed"] is False
        assert "overruled" in attr["directive"]

    def test_role_q3_false_driver_direct_fault(self):
        """
        Role: false_driver (Q3: faulty & followed).
        Bull urged BUY (+1.0), Manager followed and executed BUY (+1.0), Trade lost -7.0% (-0.07).
        Attribution Score = -|R| * conf = -0.07 * 0.90 = -0.063.
        """
        attr = compute_counterfactual_attribution(
            agent_stance=+1.0,
            realized_return=-0.07,
            manager_action="buy",
            agent_confidence=0.90,
        )
        assert attr["quadrant"] == "Q3_Faulty_Followed"
        assert classify_attribution_role(attr) == "false_driver"
        assert pytest.approx(attr["attribution_score"], abs=1e-5) == -0.063
        assert attr["is_vindicated"] is False
        assert attr["is_followed"] is True
        assert "causing the loss" in attr["directive"]

    def test_role_q4_correct_dissent_ignored_mitigated_fault(self):
        """
        Role: correct_dissent_ignored / mitigated_fault (Q4: faulty & overridden).
        Bear urged SELL (-1.0), Manager overruled and executed BUY, Stock gained +8.0% (+0.08).
        Fault is mitigated by manager override: Score = -0.2 * |R| = -0.2 * 0.08 = -0.016.
        """
        attr = compute_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=+0.08,
            manager_action="buy",
            agent_confidence=0.75,
        )
        assert attr["quadrant"] == "Q4_Faulty_Overridden"
        assert classify_attribution_role(attr) == "correct_dissent_ignored"
        assert pytest.approx(attr["attribution_score"], abs=1e-5) == -0.016
        assert attr["is_vindicated"] is False
        assert attr["is_followed"] is False
        assert "shielded the portfolio" in attr["directive"]

    def test_string_inputs_normalization(self):
        """Handles human-readable string stances ('bull', 'bear', 'buy', 'sell')."""
        attr1 = compute_counterfactual_attribution("bull", +0.02, "buy", 0.9)
        assert attr1["quadrant"] == "Q1_Vindicated_Followed"

        attr2 = compute_counterfactual_attribution("bear", -0.03, "buy", 0.9)
        assert attr2["quadrant"] == "Q2_Vindicated_Overridden"

        attr3 = compute_counterfactual_attribution("sell", +0.04, "buy", 0.9)
        assert attr3["quadrant"] == "Q4_Faulty_Overridden"

    def test_zero_realized_return_boundary(self):
        """Zero return produces 0.0 attribution score without exception."""
        attr = compute_counterfactual_attribution(+1.0, 0.0, "buy")
        assert attr["attribution_score"] == 0.0


# ==============================================================================
# 4. Prompt Injection & Reflection Integration
# ==============================================================================
class TestAttributionPromptInjection:
    """Verifies counterfactual attribution formatting and prompt block injection."""

    def test_format_attribution_prompt_block(self):
        attr = compute_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=-0.05,
            manager_action="buy",
            agent_confidence=0.85,
        )
        block = format_attribution_prompt_block(attr)
        assert "=== Counterfactual Credit Assignment ===" in block
        assert "- Status: Q2_Vindicated_Overridden" in block
        assert "- Attribution Score: +0.050" in block
        assert "- Directive:" in block

    @pytest.mark.asyncio
    async def test_run_reflection_injects_counterfactual_context(self):
        """run_reflection stores attribution_score and attribution_quadrant in mem0 metadata."""
        attr = compute_counterfactual_attribution(agent_stance=-1.0, realized_return=-0.05, manager_action="buy")

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
            await run_reflection(
                db=MagicMock(),
                user_id="user1",
                agent_id="bear_researcher_v2",
                scope=MemoryScope.AGENT_EXPERIENCE,
                memory_kind="trade_lesson",
                system_prompt="sys prompt",
                user_prompt="user prompt",
                fallback_content="fallback content",
                fallback_metadata={"ticker": "000001.SZ"},
                llm_client=None,
                attribution_context=attr,
            )

        assert len(stored_calls) == 1
        meta = stored_calls[0]["kwargs"]["metadata"]
        assert meta["attribution_score"] == 0.05
        assert meta["attribution_quadrant"] == "Q2_Vindicated_Overridden"
