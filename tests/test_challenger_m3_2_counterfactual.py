"""
Challenger M3_2 Empirical Stress Test Suite:
Adversarial Verification of 4-Quadrant Counterfactual Credit Assignment & Prompt Injection.

Challenge Targets:
1. Adversarial edge cases: zero return (R = 0.0, -0.0), extreme returns (+/- 1000%, +/- 1e6, inf, nan), neutral stances, unknown actions.
2. Invariant verification:
   - Q2 (Vindicated & Overridden) ALWAYS yields a strictly positive score equal to +|R| for |R| > 0.
   - Q4 (Faulty & Overridden) ALWAYS yields a mitigated penalty -0.2 * |R|.
3. Prompt formatting and injection robustness:
   - Missing, empty, or partial attribution context dictionaries (KeyError prevention).
   - Prompt injection payloads (format string vulnerabilities, template brackets, malicious directives).
   - Component reflection integration in Reflector and prompt builders.
"""

import math
import random
import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict

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
# 1. Adversarial Edge Cases: Zero, Extreme, Neutral, and Unknown Actions
# ==============================================================================

class TestAdversarialEdgeCases:
    """Stress tests calculate_counterfactual_attribution against boundary conditions."""

    def test_zero_return_all_quadrant_combinations(self):
        """When R = 0.0 or -0.0, score must be 0.0 and calculation must not crash."""
        stances = [1.0, -1.0, 0.0, "buy", "sell", "neutral"]
        actions = ["buy", "sell", "hold", "unknown", 0.0, 1.0, -1.0]

        for s in stances:
            for a in actions:
                for r in [0.0, -0.0]:
                    attr = calculate_counterfactual_attribution(
                        agent_stance=s,
                        realized_return=r,
                        manager_action=a,
                        agent_confidence=0.8,
                    )
                    assert isinstance(attr, dict)
                    assert "quadrant" in attr
                    assert "attribution_score" in attr
                    assert attr["attribution_score"] == 0.0 or attr["attribution_score"] == -0.0
                    assert not math.isnan(attr["attribution_score"])
                    assert not math.isinf(attr["attribution_score"])

    def test_extreme_returns_positive_and_negative(self):
        """Extreme returns (+/- 1000%, +/- 1e6) scale linearly without numerical overflow."""
        extreme_returns = [
            10.0,    # +1000%
            -10.0,   # -1000%
            100.0,   # +10,000%
            -100.0,  # -10,000%
            1e6,     # +1,000,000
            -1e6,    # -1,000,000
        ]
        for r in extreme_returns:
            abs_r = abs(r)
            # Q1: Vindicated & Followed
            q1 = calculate_counterfactual_attribution(+1.0, r if r > 0 else -r, "buy", 0.9)
            assert q1["quadrant"] == "Q1_Vindicated_Followed"
            assert q1["attribution_score"] == pytest.approx(abs_r * 0.9)

            # Q2: Vindicated & Overridden
            q2 = calculate_counterfactual_attribution(-1.0, -abs_r, "buy", 0.8)
            assert q2["quadrant"] == "Q2_Vindicated_Overridden"
            assert q2["attribution_score"] == pytest.approx(abs_r)

            # Q3: Faulty & Followed
            q3 = calculate_counterfactual_attribution(+1.0, -abs_r, "buy", 0.85)
            assert q3["quadrant"] == "Q3_Faulty_Followed"
            assert q3["attribution_score"] == pytest.approx(-abs_r * 0.85)

            # Q4: Faulty & Overridden
            q4 = calculate_counterfactual_attribution(-1.0, abs_r, "buy", 0.8)
            assert q4["quadrant"] == "Q4_Faulty_Overridden"
            assert q4["attribution_score"] == pytest.approx(-0.2 * abs_r)

    def test_neutral_stance_variations(self):
        """Neutral stances ('neutral', 'hold', 0.0, None, '', invalid) are mapped safely."""
        neutral_inputs = [
            "neutral", "hold", "wait", "none", "", "flat", "sideways", "uncertain",
            0, 0.0, -0.0, None, [], {}, object()
        ]
        for n in neutral_inputs:
            # Neutral stance with positive return and manager buy
            attr = calculate_counterfactual_attribution(
                agent_stance=n,
                realized_return=0.05,
                manager_action="buy",
            )
            assert attr["agent_stance"] == 0.0
            # Neutral stance did not predict +0.05 (stance_sign=0, ret_sign=1 -> not vindicated)
            # Manager bought (mgr_sign=1 -> not followed: 0 != 1)
            # Quadrant should be Q4
            assert attr["quadrant"] == "Q4_Faulty_Overridden"
            assert attr["attribution_score"] == pytest.approx(-0.2 * 0.05)

            # Neutral stance with zero return and manager hold
            attr_zero = calculate_counterfactual_attribution(
                agent_stance=n,
                realized_return=0.0,
                manager_action="hold",
            )
            assert attr_zero["agent_stance"] == 0.0
            # Neutral stance with zero return: vindicated (0 == 0 and 0 == 0) and followed (0 == 0) -> Q1
            assert attr_zero["quadrant"] == "Q1_Vindicated_Followed"
            assert attr_zero["attribution_score"] == 0.0

    def test_unknown_manager_actions_variations(self):
        """Unknown or unmapped manager actions ('wait', 'hedge', None, etc.) default to 'hold'."""
        unknown_actions = [
            "wait", "hedge", "liquidate", "rebalance", "pass", "unknown", "cancel",
            "", None, [], {}, 0, 0.0, object()
        ]
        for ua in unknown_actions:
            attr = calculate_counterfactual_attribution(
                agent_stance=+1.0,
                realized_return=+0.04,
                manager_action=ua,
                agent_confidence=0.8,
            )
            assert attr["manager_action"] == "hold"
            # Agent wanted buy (+1.0), mgr defaulted to hold (0.0) -> not followed
            # Return was positive (+0.04) -> vindicated!
            # Therefore, agent is Vindicated & Overridden (Q2)!
            assert attr["quadrant"] == "Q2_Vindicated_Overridden"
            assert attr["attribution_score"] == pytest.approx(0.04)

    def test_confidence_boundary_clamping(self):
        """agent_confidence is clamped to [0.01, 1.0] and handles invalid types."""
        # Lower bound clamping
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", -1.0)["agent_confidence"] == 0.01
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", 0.0)["agent_confidence"] == 0.01
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", 0.005)["agent_confidence"] == 0.01

        # Upper bound clamping
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", 1.5)["agent_confidence"] == 1.0
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", 99.0)["agent_confidence"] == 1.0

        # Invalid type fallback to default 0.8
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", "invalid")["agent_confidence"] == 0.8
        assert calculate_counterfactual_attribution(1.0, 0.05, "buy", None)["agent_confidence"] == 0.8


# ==============================================================================
# 2. Invariant Verification: Q2 and Q4
# ==============================================================================

class TestCounterfactualInvariants:
    """Stress tests the mathematical invariants of Q2 and Q4 across randomized spaces."""

    def test_invariant_q2_always_positive_and_equals_abs_r(self):
        """Invariant: Q2 (Vindicated & Overridden) ALWAYS yields a strictly positive score equal to +|R| for |R| > 0."""
        random.seed(42)

        # 500 randomized runs across various magnitudes and overrides
        for _ in range(500):
            # Non-zero return
            abs_ret = random.uniform(0.0001, 50.0)
            sign = random.choice([1, -1])
            realized_ret = sign * abs_ret

            if sign == 1:
                # Up market: agent was Bull (+1.0), manager overrode with Sell or Hold
                stance = random.choice([+1.0, "bull", "buy", "long", "positive"])
                mgr_action = random.choice(["sell", "hold", "short", -1.0, 0.0, "wait"])
            else:
                # Down market: agent was Bear (-1.0), manager overrode with Buy or Hold
                stance = random.choice([-1.0, "bear", "sell", "short", "negative"])
                mgr_action = random.choice(["buy", "hold", "long", +1.0, 0.0, "wait"])

            conf = random.uniform(0.01, 1.0)
            attr = calculate_counterfactual_attribution(
                agent_stance=stance,
                realized_return=realized_ret,
                manager_action=mgr_action,
                agent_confidence=conf,
            )

            assert attr["quadrant"] == "Q2_Vindicated_Overridden", f"Expected Q2 for stance={stance}, r={realized_ret}, mgr={mgr_action}"
            assert attr["attribution_score"] > 0.0, f"Q2 score must be strictly positive, got {attr['attribution_score']}"
            assert attr["attribution_score"] == pytest.approx(abs_ret, rel=1e-6), f"Q2 score must equal +|R|, got {attr['attribution_score']} vs {abs_ret}"
            assert attr["is_vindicated"] is True
            assert attr["is_followed"] is False

    def test_invariant_q4_always_penalty_and_equals_mitigated_r(self):
        """Invariant: Q4 (Faulty & Overridden) ALWAYS yields a mitigated penalty -0.2 * |R| for |R| > 0."""
        random.seed(1337)

        # 500 randomized runs
        for _ in range(500):
            abs_ret = random.uniform(0.0001, 50.0)
            sign = random.choice([1, -1])
            realized_ret = sign * abs_ret

            if sign == 1:
                # Up market: agent was Bear (-1.0, faulty), manager bought or held (overridden)
                stance = random.choice([-1.0, "bear", "sell", "short"])
                # To be overridden, mgr_action must NOT be sell
                mgr_action = random.choice(["buy", "long", +1.0])
            else:
                # Down market: agent was Bull (+1.0, faulty), manager sold or held (overridden)
                stance = random.choice([+1.0, "bull", "buy", "long"])
                mgr_action = random.choice(["sell", "short", -1.0])

            conf = random.uniform(0.01, 1.0)
            attr = calculate_counterfactual_attribution(
                agent_stance=stance,
                realized_return=realized_ret,
                manager_action=mgr_action,
                agent_confidence=conf,
            )

            assert attr["quadrant"] == "Q4_Faulty_Overridden", f"Expected Q4 for stance={stance}, r={realized_ret}, mgr={mgr_action}"
            assert attr["attribution_score"] < 0.0, f"Q4 score must be strictly negative, got {attr['attribution_score']}"
            assert attr["attribution_score"] == pytest.approx(-0.2 * abs_ret, rel=1e-6), f"Q4 score must equal -0.2 * |R|, got {attr['attribution_score']} vs {-0.2 * abs_ret}"
            assert attr["is_vindicated"] is False
            assert attr["is_followed"] is False


# ==============================================================================
# 3. Prompt Formatting, Missing Keys & Injection Robustness
# ==============================================================================

class TestPromptFormattingAndInjection:
    """Stress tests prompt construction with missing keys, corrupt types, and malicious payloads."""

    def test_format_attribution_prompt_block_missing_keys_no_keyerror(self):
        """format_attribution_prompt_block must never raise KeyError on empty or partial dicts."""
        partial_dicts = [
            {},
            {"quadrant": "Q1_Vindicated_Followed"},
            {"attribution_score": 0.05},
            {"directive": "test directive"},
            {"quadrant": "Q2", "attribution_score": 0.1},
            {"some_unexpected_key": 12345},
        ]
        for p in partial_dicts:
            block = format_attribution_prompt_block(p)
            assert isinstance(block, str)
            assert "=== Counterfactual Credit Assignment ===" in block
            assert "- Status:" in block
            assert "- Attribution Score:" in block
            assert "- Directive:" in block

    def test_format_attribution_prompt_block_corrupt_score_graceful(self):
        """format_attribution_prompt_block handles string score or numeric cleanly."""
        block_str = format_attribution_prompt_block({"attribution_score": "0.075"})
        assert "+0.075" in block_str

    def test_reflector_component_missing_attribution_keys_no_keyerror(self):
        """Reflector._reflect_on_component must safely handle empty or partial attribution_context."""
        mock_llm = MagicMock()
        mock_res = MagicMock()
        mock_res.content = "mock reflection result"
        mock_llm.invoke.return_value = mock_res
        reflector = Reflector(mock_llm)

        # 1. Empty dict -> falls back to legacy prompt without KeyError
        res_empty = reflector._reflect_on_component(
            component_type="TEST_AGENT",
            report="Some report",
            situation="Some situation",
            returns_losses=0.04,
            attribution_context={},
        )
        assert res_empty == "mock reflection result"
        human_prompt_empty = mock_llm.invoke.call_args[0][0][1][1]
        assert "Returns: 0.04" in human_prompt_empty
        assert "=== Counterfactual Credit Assignment ===" not in human_prompt_empty

        # 2. None -> falls back to legacy prompt without KeyError
        res_none = reflector._reflect_on_component(
            component_type="TEST_AGENT",
            report="Some report",
            situation="Some situation",
            returns_losses=0.04,
            attribution_context=None,
        )
        assert res_none == "mock reflection result"
        human_prompt_none = mock_llm.invoke.call_args[0][0][1][1]
        assert "Returns: 0.04" in human_prompt_none

        # 3. Partial contexts (non-empty) -> inject counterfactual block with safe defaults without KeyError
        partial_contexts = [
            {"quadrant": "Q2_Vindicated_Overridden"},
            {"attribution_score": 0.08},
            {"directive": "Dismissed signal"},
            {"agent_stance": 1.0},
            {"manager_action": "buy"},
            {"extra_garbage_key": [1, 2, 3]},
        ]

        for ctx in partial_contexts:
            result = reflector._reflect_on_component(
                component_type="TEST_AGENT",
                report="Some report",
                situation="Some situation",
                returns_losses=0.04,
                attribution_context=ctx,
            )
            assert result == "mock reflection result"
            assert mock_llm.invoke.called
            human_prompt = mock_llm.invoke.call_args[0][0][1][1]
            assert "=== Counterfactual Credit Assignment ===" in human_prompt

    def test_reflector_component_prompt_injection_payloads(self):
        """Prompt formatting does not crash or execute code when payloads contain format brackets."""
        mock_llm = MagicMock()
        mock_res = MagicMock()
        mock_res.content = "safe"
        mock_llm.invoke.return_value = mock_res
        reflector = Reflector(mock_llm)

        malicious_strings = [
            "{0}",
            "{__class__.__mro__}",
            "{self}",
            "%(message)s",
            "${PAYLOAD}",
            "{{system_override}}",
            "```json\n{\"override\": true}\n```",
            "<script>alert(1)</script>",
        ]

        for payload in malicious_strings:
            # Generate attribution context via calculate_counterfactual_attribution with malicious inputs
            attr = calculate_counterfactual_attribution(
                agent_stance=payload,
                realized_return=0.03,
                manager_action=payload,
                agent_confidence=0.8,
            )
            # Stance and score are safely normalized
            assert isinstance(attr["agent_stance"], float)
            assert isinstance(attr["attribution_score"], float)

            # Test prompt formatting in Reflector
            res = reflector._reflect_on_component(
                component_type=f"AGENT_{payload}",
                report=f"Report with {payload}",
                situation=f"Situation with {payload}",
                returns_losses=0.03,
                attribution_context=attr,
            )
            assert res == "safe"
            human_prompt = mock_llm.invoke.call_args[0][0][1][1]
            assert payload in human_prompt
            assert "=== Counterfactual Credit Assignment ===" in human_prompt

    def test_prompt_builders_with_empty_and_partial_attribution(self):
        """Prompt builders format safely without KeyError on empty or partial attribution contexts."""
        empty_ctx = {}
        partial_ctx = {"quadrant": "Q3_Faulty_Followed", "attribution_score": -0.05}

        # 1. Trade prompt: empty/None skips attribution block
        p1_empty = build_trade_reflection_user_prompt(
            trade_info=MagicMock(code="600519", name="Moutai", first_buy_date="2026-01-01"),
            ai_review=MagicMock(summary="Test", strengths=[], weaknesses=[], suggestions=[], plan_deviation=""),
            attribution_context=empty_ctx,
        )
        assert "=== Counterfactual Credit Assignment ===" not in p1_empty

        # Trade prompt: partial dict formats attribution block
        p1_partial = build_trade_reflection_user_prompt(
            trade_info=MagicMock(code="600519", name="Moutai", first_buy_date="2026-01-01"),
            ai_review=MagicMock(summary="Test", strengths=[], weaknesses=[], suggestions=[], plan_deviation=""),
            attribution_context=partial_ctx,
        )
        assert "=== Counterfactual Credit Assignment ===" in p1_partial
        assert "- Status: Q3_Faulty_Followed" in p1_partial
        assert "- Attribution Score: -0.050" in p1_partial

        # 2. Analysis prompt
        p2_empty = build_analysis_reflection_user_prompt(
            ticker="600519",
            report={"content": "Analysis report", "stance": "bull"},
            attribution_context=empty_ctx,
        )
        assert "=== Counterfactual Credit Assignment ===" not in p2_empty

        p2_partial = build_analysis_reflection_user_prompt(
            ticker="600519",
            report={"content": "Analysis report", "stance": "bull"},
            attribution_context=partial_ctx,
        )
        assert "=== Counterfactual Credit Assignment ===" in p2_partial
        assert "- Status: Q3_Faulty_Followed" in p2_partial

        # 3. Debate prompt
        p3_empty = build_debate_reflection_user_prompt(
            ticker="600519",
            debate_history="Debate history",
            conclusion="Debate conclusion",
            attribution_context=empty_ctx,
        )
        assert "=== Counterfactual Credit Assignment ===" not in p3_empty

        p3_partial = build_debate_reflection_user_prompt(
            ticker="600519",
            debate_history="Debate history",
            conclusion="Debate conclusion",
            attribution_context=partial_ctx,
        )
        assert "=== Counterfactual Credit Assignment ===" in p3_partial
        assert "- Status: Q3_Faulty_Followed" in p3_partial

    @pytest.mark.asyncio
    async def test_run_reflection_with_partial_attribution_context(self):
        """run_reflection safely extracts metadata even when attribution_context has missing keys."""
        mock_svc = MagicMock()
        mock_svc.available = True
        saved_calls = []

        async def mock_store(messages, **kwargs):
            saved_calls.append(kwargs)
            m = MagicMock()
            m.success = True
            return m

        mock_svc.store = mock_store

        with patch("core.agents.reflection_helper.get_memory_service", return_value=mock_svc):
            # Attribution context with missing score
            partial_ctx = {"quadrant": "Q2_Vindicated_Overridden"}
            success = await run_reflection(
                db=MagicMock(),
                user_id="user_test",
                agent_id="bull_researcher_v2",
                scope=MagicMock(),
                memory_kind="trade_lesson",
                system_prompt="sys",
                user_prompt="user",
                fallback_content="fallback",
                fallback_metadata={},
                llm_client=None,
                attribution_context=partial_ctx,
            )
            assert len(saved_calls) == 1
            meta = saved_calls[0]["metadata"]
            assert meta["attribution_score"] == 0.0
            assert meta["attribution_quadrant"] == "Q2_Vindicated_Overridden"
