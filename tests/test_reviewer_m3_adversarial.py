"""
Adversarial Stress Test Suite for Milestone M3:
Regime-Conditioned Episodic Memory & Counterfactual Credit Assignment

Stress-testing edge cases, boundary conditions, malformed structures,
clamping guarantees, and mathematical invariance.
"""

import math
import pytest
from unittest.mock import MagicMock

from core.memory.memory_manager import (
    Mem0AgentMemory,
    circuit_breaker_memory_filter,
    _CIRCUIT_BREAKER_AGENTS,
)
from core.agents.reflection_helper import (
    calculate_counterfactual_attribution,
    format_attribution_prompt_block,
)
from core.agents.reflection_prompts import (
    build_trade_reflection_user_prompt,
    build_analysis_reflection_user_prompt,
    build_debate_reflection_user_prompt,
)
from tradingagents.graph.reflection import Reflector


class TestAdversarialMemoryMetadata:
    """Stress-test metadata normalization against hostile, extreme, and malformed inputs."""

    def test_idempotent_normalization(self):
        """Applying normalization multiple times must yield identical metadata."""
        raw = {"market_regime": "bull", "volatility_quintile": 4, "brier_calibration_error": 0.12}
        norm1 = Mem0AgentMemory._normalize_store_metadata(raw)
        norm2 = Mem0AgentMemory._normalize_store_metadata(norm1)
        assert norm1 == norm2

        recall1 = Mem0AgentMemory._normalize_recall_filters(raw)
        recall2 = Mem0AgentMemory._normalize_recall_filters(recall1)
        assert recall1 == recall2

    def test_hostile_volatility_quintiles(self):
        """Ensure inputs for volatility_quintile clamp to [1, 5] without crashing on non-infinite inputs."""
        for val in [-999, 999, 0, 6, "1", "5", "100", "-50", None, {}, []]:
            res = Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": val})
            assert isinstance(res["volatility_quintile"], int)
            assert 1 <= res["volatility_quintile"] <= 5

        # Note: float('inf') raises OverflowError in int() which is caught as a finding
        with pytest.raises(OverflowError):
            Mem0AgentMemory._normalize_store_metadata({"volatility_quintile": float("inf")})

    def test_hostile_brier_calibration_errors(self):
        """Ensure brier_calibration_error never goes below 0.0 and survives hostile types."""
        for val in [-100.0, -1e-6, 0.0, 1.5, "0.33", "not_a_number", None, {}, []]:
            res = Mem0AgentMemory._normalize_store_metadata({"brier_calibration_error": val})
            assert isinstance(res["brier_calibration_error"], float)
            assert res["brier_calibration_error"] >= 0.0

    def test_unicode_and_unusual_regime_strings(self):
        """Ensure non-standard strings gracefully resolve to 'sideways'."""
        for reg in [" 牛市 ", "bearish", "bullish", "BULL\n", "\tsideways\t", "⚡crash⚡", "", "   "]:
            res = Mem0AgentMemory._normalize_store_metadata({"market_regime": reg})
            expected = reg.strip().lower() if reg.strip().lower() in {"bull", "bear", "sideways"} else "sideways"
            assert res["market_regime"] == expected


class TestAdversarialRegimeCircuitBreaker:
    """Stress-test circuit breaker filtering on memory objects."""

    def test_circuit_exact_epsilon_boundary(self):
        """Verify strict behavior around confidence 0.5 boundary."""
        memories = [
            {"id": "m1", "metadata": {"market_regime": "bull"}},
            {"id": "m2", "metadata": {"market_regime": "bear"}},
        ]
        # Active: >= 0.5
        active = circuit_breaker_memory_filter(memories, "bull", regime_confidence=0.5, agent_id="trader_v2")
        assert len(active) == 1 and active[0]["id"] == "m1"

        active_eps = circuit_breaker_memory_filter(memories, "bull", regime_confidence=0.5 + 1e-9, agent_id="trader_v2")
        assert len(active_eps) == 1 and active_eps[0]["id"] == "m1"

        # Bypassed: < 0.5
        bypassed_eps = circuit_breaker_memory_filter(memories, "bull", regime_confidence=0.5 - 1e-9, agent_id="trader_v2")
        assert len(bypassed_eps) == 2

    def test_malformed_and_missing_metadata(self):
        """Memories with missing or corrupted metadata must not cause exceptions."""
        malformed_memories = [
            {"id": "none_meta", "metadata": None},
            {"id": "string_meta", "metadata": "corrupted"},
            {"id": "list_meta", "metadata": ["invalid"]},
            {"id": "missing_regime", "metadata": {"ticker": "AAPL"}},
            {"id": "valid_bull", "metadata": {"market_regime": "bull"}},
            {"id": "valid_sideways", "metadata": {"market_regime": "sideways"}},
        ]
        # When querying bull with high confidence
        res = circuit_breaker_memory_filter(malformed_memories, "bull", regime_confidence=0.8, agent_id="bull_researcher_v2")
        # Only valid_bull should match; missing/none defaults to sideways and gets filtered
        assert len(res) == 1
        assert res[0]["id"] == "valid_bull"

        # When querying sideways
        res_sideways = circuit_breaker_memory_filter(malformed_memories, "sideways", regime_confidence=0.8, agent_id="research_manager_v2")
        # missing_regime, none_meta, string_meta, list_meta all fall back to sideways and thus match!
        assert "valid_sideways" in [m["id"] for m in res_sideways]
        assert "valid_bull" not in [m["id"] for m in res_sideways]

    def test_large_scale_memory_throughput(self):
        """Filter 10,000 memories in < 50ms."""
        import time
        large_memories = [
            {"id": f"m_{i}", "metadata": {"market_regime": "bull" if i % 2 == 0 else "bear"}}
            for i in range(10000)
        ]
        t0 = time.perf_counter()
        filtered = circuit_breaker_memory_filter(large_memories, "bull", regime_confidence=0.9, agent_id="trader_v2")
        t1 = time.perf_counter()
        assert len(filtered) == 5000
        assert (t1 - t0) < 0.05  # Must execute in under 50ms


class TestAdversarialCounterfactualAttribution:
    """Stress-test mathematical properties and quadrant invariants."""

    def test_quadrant_sign_invariants(self):
        """Mathematical invariants:
        Q1 score >= 0.0
        Q2 score >= 0.0 (counterfactual alpha)
        Q3 score <= 0.0
        Q4 score <= 0.0
        """
        for stance in [+1.0, -1.0, 0.0, "buy", "sell", "hold"]:
            for action in ["buy", "sell", "hold", +1.0, -1.0, 0.0]:
                for ret in [-0.10, -0.01, 0.0, 0.01, 0.10]:
                    for conf in [0.1, 0.5, 0.8, 1.0]:
                        attr = calculate_counterfactual_attribution(stance, ret, action, conf)
                        q = attr["quadrant"]
                        score = attr["attribution_score"]

                        if q.startswith("Q1"):
                            assert score >= -1e-9, f"Q1 must be >= 0: {attr}"
                        elif q.startswith("Q2"):
                            assert score >= -1e-9, f"Q2 must be >= 0: {attr}"
                        elif q.startswith("Q3"):
                            assert score <= 1e-9, f"Q3 must be <= 0: {attr}"
                        elif q.startswith("Q4"):
                            assert score <= 1e-9, f"Q4 must be <= 0: {attr}"

    def test_extreme_confidence_values(self):
        """Confidence must be clamped to [0.01, 1.0]."""
        # Negative confidence
        attr_neg = calculate_counterfactual_attribution(+1.0, 0.05, "buy", -5.0)
        assert attr_neg["agent_confidence"] == 0.01
        assert attr_neg["attribution_score"] == pytest.approx(0.05 * 0.01)

        # > 1.0 confidence
        attr_high = calculate_counterfactual_attribution(+1.0, 0.05, "buy", 10.0)
        assert attr_high["agent_confidence"] == 1.0
        assert attr_high["attribution_score"] == pytest.approx(0.05 * 1.0)

    def test_unconventional_action_strings(self):
        """Strings like 'bullish', 'bearish', 'positive', 'negative' are normalized."""
        attr_bullish = calculate_counterfactual_attribution("bullish stance", 0.05, "buy")
        assert attr_bullish["agent_stance"] == 1.0
        assert attr_bullish["quadrant"] == "Q1_Vindicated_Followed"

        attr_short = calculate_counterfactual_attribution("short recommendation", -0.05, "sell")
        assert attr_short["agent_stance"] == -1.0
        assert attr_short["quadrant"] == "Q1_Vindicated_Followed"

        attr_neutral = calculate_counterfactual_attribution("neutral / waiting", 0.05, "buy")
        assert attr_neutral["agent_stance"] == 0.0


class TestAdversarialReflectorAndPrompts:
    """Stress-test Reflector prompt injection and prompt builders."""

    def test_massive_prompt_content_truncation(self):
        """Prompt builders must truncate 50,000 char inputs without choking."""
        huge_text = "A" * 50000
        attr = calculate_counterfactual_attribution(+1.0, 0.04, "buy")

        p_analysis = build_analysis_reflection_user_prompt("000001.SZ", huge_text, attribution_context=attr)
        assert len(p_analysis) < 5000
        assert "truncated" in p_analysis

        p_debate = build_debate_reflection_user_prompt("000001.SZ", huge_text, huge_text, attribution_context=attr)
        assert len(p_debate) < 10000
        assert "truncated" in p_debate

    def test_reflector_handles_missing_state_keys(self):
        """Reflector._extract_manager_action must safely handle empty state."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Mock response")
        reflector = Reflector(mock_llm)

        # Empty state
        mgr_action = reflector._extract_manager_action({})
        assert mgr_action == "hold"

        # State with None values
        mgr_action_none = reflector._extract_manager_action({
            "final_trade_decision": None,
            "trader_investment_plan": None,
            "risk_debate_state": None,
        })
        assert mgr_action_none == "hold"

    def test_reflector_reflect_trader_and_judges(self):
        """Reflect on trader, invest judge, risk judge with various outcomes."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Reflect response")
        reflector = Reflector(mock_llm)

        state = {
            "trader_investment_plan": "Action: SELL 500 shares",
            "investment_debate_state": {"judge_decision": "Decision: BUY"},
            "risk_debate_state": {"judge_decision": "Decision: HOLD"},
            "final_trade_decision": "SELL",
        }
        mock_mem = MagicMock()

        # Trader: SELL, trade return -0.03 (stock dropped), manager sold -> Q1 (Vindicated & Followed)
        res_trader = reflector.reflect_trader(state, returns_losses=-0.03, trader_memory=mock_mem)
        assert res_trader == "Reflect response"
        assert mock_mem.add_situations.called

        # Invest Judge: BUY, trade return -0.03, manager sold -> Q4 (Faulty & Overridden)
        res_invest = reflector.reflect_invest_judge(state, returns_losses=-0.03, invest_judge_memory=mock_mem)
        assert res_invest == "Reflect response"

        # Risk Judge: HOLD, trade return -0.03, manager sold -> Q4 (Faulty & Overridden)
        res_risk = reflector.reflect_risk_manager(state, returns_losses=-0.03, risk_manager_memory=mock_mem)
        assert res_risk == "Reflect response"
