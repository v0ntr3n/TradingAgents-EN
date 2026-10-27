"""
Agent Builder Workflow full process integration testing

Coverage:
  1. State management (creation, serialization, whitelisting)
  2. Routing logic (route_start, route_after_classify)
  3. Intent classification prompt words (5 node types)
  4. Complete multi-turn dialogue simulation (mock LLM)
  5. Boundary conditions and abnormal paths

Test topic: I want an assistant that can identify financial reporting risk signals, focusing on goodwill impairment, accounts receivable anomalies, and cash flow deterioration.

Usage: pytest tests/core/embedded_nanobot/workflows/test_agent_builder_full_flow.py -v
       python tests/core/embedded_nanobot/workflows/test_agent_builder_full_flow.py  # independent smoke test
"""

from __future__ import annotations

import copy
import json
import sys
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make sure the project root is in sys.path (compatible with both direct running and pytest methods)
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ──────────────────────────────────────────────────────────────
# Import the module under test
# ──────────────────────────────────────────────────────────────
from core.embedded_nanobot.workflows.agent_builder_state import (
    AgentBuilderState,
    new_agent_builder_state,
)
from core.embedded_nanobot.workflows.agent_builder_store import _KNOWN_KEYS
from core.embedded_nanobot.workflows.agent_builder_conditions import (
    _is_cancel,
    _is_confirm,
    _is_route_choice,
    _resolve_plan_selection,
    route_after_classify,
    route_start,
)
from core.embedded_nanobot.workflows.agent_builder_nodes import (
    _build_classify_prompt,
    _classify_node_type,
    _extract_json_from_result,
    _fallback_classify_intent,
    _format_recent_history,
    _will_stay_on_wait_node,
)

# ──────────────────────────────────────────────────────────────
# test constants
# ──────────────────────────────────────────────────────────────
TEST_USER_REQUEST = "I want an assistant who can identify financial reporting risk signals, focusing on goodwill impairment, accounts receivable anomalies, and cash flow deterioration."


# ====================================================================
# Part One: State Management Testing
# ====================================================================

class TestStateManagement:
    """Test the creation, serialization and whitelisting of AgentBuilderState."""

    def test_create_new_state(self):
        """Create a new state and verify that all key fields are initialized correctly."""
        state = new_agent_builder_state(
            thread_id="test-thread-001",
            user_id="user-001",
            user_message=TEST_USER_REQUEST,
        )
        assert state["thread_id"] == "test-thread-001"
        assert state["user_id"] == "user-001"
        assert state["user_message"] == TEST_USER_REQUEST
        assert state["current_node"] == "START"
        assert state["stage"] == ""
        assert state["awaiting_user"] is False
        assert state["message_history"] == []
        assert state["errors"] == []

    def test_new_state_no_message(self):
        """Create a new state without a message."""
        state = new_agent_builder_state(
            thread_id="test-thread-002",
            user_id="user-002",
        )
        assert state["user_message"] == ""
        assert state["current_node"] == "START"

    def test_known_keys_covers_new_fields(self):
        """Verify that all new fields added in v2 are in the whitelist (to prevent cross-request loss)."""
        required_keys = {
            # Intent classification
            "user_intent", "intent_confidence", "intent_reason",
            "user_selected_index", "user_selected_id",
            # Conversation history
            "message_history",
            # clarification mark
            "clarification_needed",
            # tool progress
            "test_progress",
            # Basic fields
            "thread_id", "user_id", "user_message", "current_node",
            "stage", "awaiting_user", "spec_id", "spec_name",
            "version_id", "test_symbol", "test_result",
            "official_acceptance_decision", "errors", "final_response",
        }
        missing = required_keys - set(_KNOWN_KEYS)
        assert not missing, f"Whitelist missing fields: {missing}"

    def test_state_serialization_roundtrip(self):
        """After the status is stored in a known field, it should be able to be read out completely."""
        state = new_agent_builder_state(
            thread_id="test-serial-001",
            user_id="user-001",
            user_message=headline_request(),
        )
        state["message_history"] = [
            {"role": "agent", "content": "Please confirm your requirements"},
            {"role": "user", "content": "Confirm"},
        ]
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.92
        state["clarification_needed"] = False

        # Simulate the filtering logic of _make_state_serializable
        serialized = {k: v for k, v in state.items() if k in _KNOWN_KEYS}

        assert serialized["message_history"] == state["message_history"]
        assert serialized["user_intent"] == "confirmed"
        assert serialized["intent_confidence"] == 0.92


# ====================================================================
# Part 2: Routing logic testing
# ====================================================================

class TestRouteStart:
    """Test the routing logic of the START node."""

    def test_new_session_goes_to_intake(self):
        """empty current_node → requirement_intake. """
        state = new_state(user_message=headline_request())
        assert route_start(state) == "requirement_intake"

    def test_start_node_goes_to_intake(self):
        """current_node == "START" → requirement_intake。"""
        state = new_state(user_message=headline_request())
        state["current_node"] = "START"
        assert route_start(state) == "requirement_intake"

    @pytest.mark.parametrize("wait_node", [
        "wait_intake_confirmation",
        "wait_requirement_confirmation",
        "wait_plan_selection",
        "wait_test_request",
        "evaluate_or_publish",
        "wait_evaluation",
        "error_recovery",
    ])
    def test_wait_nodes_go_to_classify(self, wait_node: str):
        """All wait/evaluate/error nodes → classify_intent. """
        state = new_state(user_message="Change a stock test")
        state["current_node"] = wait_node
        assert route_start(state) == "classify_intent"

    def test_action_node_keeps_current(self):
        """Non-wait nodes maintain the original route."""
        state = new_state(user_message="continue")
        state["current_node"] = "gap_analysis"
        assert route_start(state) == "gap_analysis"


class TestRouteAfterClassify:
    """Test routing after LLM intent classification."""

    # ── Low confidence level ──

    def test_low_confidence_stays_on_wait(self):
        """confidence < 0.7 → Stay at the current wait node + clarification_needed. """
        state = new_state("OK")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "explore_more"
        state["intent_confidence"] = 0.45
        result = route_after_classify(state)
        assert result == "wait_evaluation"
        assert state["clarification_needed"] is True

    # ── cancel overall situation ──

    @pytest.mark.parametrize("node", [
        "wait_intake_confirmation", "wait_evaluation", "error_recovery",
    ])
    def test_cancel_anywhere_ends(self, node: str):
        """cancel End at any stage."""
        state = new_state("Cancel")
        state["current_node"] = node
        state["user_intent"] = "cancel"
        state["intent_confidence"] = 0.9
        assert route_after_classify(state) == "end"

    # ── new_agent ──

    def test_new_agent_intent(self):
        """The user wants to create a new Agent → end + guide."""
        state = new_state("I want to create a new public opinion analysis Agent")
        state["current_node"] = "wait_evaluation"
        state["spec_name"] = "Financial reporting risk identification"
        state["user_intent"] = "new_agent"
        state["intent_confidence"] = 0.95
        result = route_after_classify(state)
        assert result == "end"
        assert "New Agent" in state.get("final_response", "")

    # ── wait_test_request ──

    def test_test_symbol_available_goes_to_test(self):
        """LLM extracted test_symbol → real_data_test. """
        state = new_state("600519")
        state["current_node"] = "wait_test_request"
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.9
        state["test_symbol"] = "600519"
        assert route_after_classify(state) == "real_data_test"

    def test_test_symbol_missing_clarifies(self):
        """None test_symbol → stay + clarification. """
        state = new_state("Test it")
        state["current_node"] = "wait_test_request"
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.9
        result = route_after_classify(state)
        assert result == "wait_test_request"
        assert state["clarification_needed"] is True

    # ── wait_evaluation ──

    def test_eval_confirm_publishes(self):
        """User confirms release → evaluate_or_publish. """
        state = new_state("publish")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.9
        assert route_after_classify(state) == "evaluate_or_publish"

    def test_eval_retry_goes_to_test(self):
        """User requests retest → wait_test_request. """
        state = new_state("Test again in the CATL era")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "retry"
        state["intent_confidence"] = 0.9
        state["test_symbol"] = "300750"
        assert route_after_classify(state) == "wait_test_request"

    def test_eval_revise_goes_to_requirement(self):
        """User wants to modify → requirement_intake. """
        state = new_state("Add a cash flow analysis dimension")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "revise"
        state["intent_confidence"] = 0.9
        assert route_after_classify(state) == "requirement_intake"

    # ── Unknown node security ──

    def test_unknown_node_defaults_to_end(self):
        """unknown current_node → Safe end."""
        state = new_state("test")
        state["current_node"] = "gap_analysis"
        state["user_intent"] = "retry"
        state["intent_confidence"] = 0.8
        assert route_after_classify(state) == "end"


# ====================================================================
# Part 3: Intent Classification Unit Testing
# ====================================================================

class TestIntentClassification:
    """Helper function for testing intent classification."""

    def test_classify_node_type(self):
        """Node names map correctly to types."""
        assert _classify_node_type("wait_intake_confirmation") == "confirmation"
        assert _classify_node_type("wait_requirement_confirmation") == "confirmation"
        assert _classify_node_type("wait_plan_selection") == "plan_selection"
        assert _classify_node_type("wait_test_request") == "test_eval"
        assert _classify_node_type("wait_evaluation") == "test_eval"
        assert _classify_node_type("evaluate_or_publish") == "test_eval"
        assert _classify_node_type("error_recovery") == "error"
        assert _classify_node_type("gap_analysis") == "generic"

    def test_fallback_classify_intent(self):
        """LLM When unavailable, sort it out."""
        # cancel intention
        assert _fallback_classify_intent("Cancel", "wait_evaluation") == "cancel"
        # Solution selection
        assert _fallback_classify_intent("choose A", "wait_plan_selection") == "select_option"
        assert _fallback_classify_intent("B Plan", "wait_plan_selection") == "select_option"
        # Confirm
        assert _fallback_classify_intent("Confirm", "wait_intake_confirmation") == "confirmed"
        assert _fallback_classify_intent("OK", "wait_requirement_confirmation") == "confirmed"
        # unknown expression → explore_more (Streamline the details and don't over-guess)
        assert _fallback_classify_intent("Exit", "wait_evaluation") == "explore_more"
        assert _fallback_classify_intent("The weather is so nice today", "wait_evaluation") == "explore_more"

    def test_recent_history_formatting(self):
        """message_history Properly formatted for LLM prompt context."""
        state = new_state("new news")
        state["message_history"] = [
            {"role": "agent", "content": "Please confirm whether to continue"},
            {"role": "user", "content": "Confirm to continue"},
            {"role": "agent", "content": "OK, searching for capabilities"},
            {"role": "user", "content": "new news"},
        ]
        formatted = _format_recent_history(state)
        assert "[Agent] Please confirm whether to continue" in formatted
        assert "[User] Confirm to continue" in formatted
        # Verification only takes the latest 3 rounds (6 entries)
        assert formatted.count("[Agent]") >= 1

    def test_recent_history_empty(self):
        """No conversation history → Return placeholder text."""
        state = new_state("new news")
        state["message_history"] = []
        formatted = _format_recent_history(state)
        assert "No conversation history yet" in formatted

    def test_build_classify_prompt_for_test_eval(self):
        """test_eval The node type generates the correct prompt word."""
        state = new_state("Retest in the CATL era")
        state["current_node"] = "wait_evaluation"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["message_history"] = [
            {"role": "agent", "content": "The test is completed and the three indicators of PE/PB/PS are normal."},
            {"role": "user", "content": "Retest in the CATL era"},
        ]
        prompt = _build_classify_prompt(state, "test_eval")
        assert "retry" in prompt.lower() or "retest" in prompt or "Data extraction" in prompt
        assert "Ningde era" in prompt

    def test_build_classify_prompt_for_confirmation(self):
        """confirmation The node type generates the correct prompt word."""
        state = new_state("Confirm")
        state["current_node"] = "wait_intake_confirmation"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        prompt = _build_classify_prompt(state, "confirmation")
        assert "confirmed" in prompt.lower() or "Confirm" in prompt

    def test_extract_json_from_result(self):
        """JSON Extract correctly handles various inputs."""
        # Standard JSON
        assert _extract_json_from_result('{"key": "value"}') == {"key": "value"}
        # empty string
        assert _extract_json_from_result("") == {}
        # Non-JSON text
        assert _extract_json_from_result("hello world") == {}

    def test_will_stay_on_wait_node(self):
        """Anticipate whether to stay."""
        # retry drive process
        state = new_state("retest")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "retry"
        assert _will_stay_on_wait_node(state) is False
        # explore_more stay
        state["user_intent"] = "explore_more"
        assert _will_stay_on_wait_node(state) is True
        # cancel Won't stay (end)
        state["user_intent"] = "cancel"
        assert _will_stay_on_wait_node(state) is False

    def test_test_request_with_test_symbol(self):
        """wait_test_request Yes test_symbol → Does not trigger stay."""
        state = new_state("600519")
        state["current_node"] = "wait_test_request"
        state["user_intent"] = "confirmed"
        state["test_symbol"] = "600519"
        assert _will_stay_on_wait_node(state) is False


# ====================================================================
# Part 4: User Intent Judgment Auxiliary Function Test
# ====================================================================

class TestUserIntentHelpers:
    """test _is_confirm, _is_cancel, _is_route_choice Auxiliary functions."""

    @pytest.mark.parametrize("text,expected", [
        ("OK", True), ("Confirm", True), ("OK", True), ("OK", True),
        ("publish", True), ("Go online", True), ("generate", True), ("Start generating", True),
        ("Confirm release", True), ("No problem", True), ("That s it", True), ("yes", True),
        ("Agree", True), ("click this", True), ("correct", True), ("Default scheme", True),
    ])
    def test_is_confirm_positive(self, text: str, expected: bool):
        assert _is_confirm(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("Don t", False), ("Wrong", False), ("Cancel", False),
        ("Test again", False), ("Change stocks", False),
        ("The weather is nice today", False), ("", False),
    ])
    def test_is_confirm_negative(self, text: str, expected: bool):
        assert _is_confirm(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("Cancel", True), ("Forget it", True), ("No more", True),
        ("Start over", True), ("All over again", True),
    ])
    def test_is_cancel_positive(self, text: str, expected: bool):
        assert _is_cancel(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("OK", False), ("publish", False), ("continue", False),
    ])
    def test_is_cancel_negative(self, text: str, expected: bool):
        assert _is_cancel(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("B", True), ("Plan A", True), ("choose C", True),
        ("Advance according to plan B", True), ("B Plan", True),
    ])
    def test_is_route_choice_positive(self, text: str, expected: bool):
        assert _is_route_choice(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("OK", False), ("Confirm", False), ("publish", False),
    ])
    def test_is_route_choice_negative(self, text: str, expected: bool):
        assert _is_route_choice(text) == expected

    def test_resolve_plan_selection_by_letter(self):
        """Select from user reply parsing scheme."""
        options = [
            {"id": "plan_a", "index": 1, "title": "Quick solution"},
            {"id": "plan_b", "index": 2, "title": "Standard solution"},
        ]
        sel_id, reason = _resolve_plan_selection(options, "choose B")
        assert sel_id == "plan_b"
        assert reason

        sel_id, _ = _resolve_plan_selection(options, "B Plan")
        assert sel_id == "plan_b"

    def test_resolve_plan_selection_no_match(self):
        """Unable to match scheme."""
        options = [{"id": "plan_a", "index": 1}]
        sel_id, reason = _resolve_plan_selection(options, "choose Z")
        assert sel_id == ""
        assert reason


# ====================================================================
# Part 5: Complete multi-round dialogue process test
# ====================================================================

class TestFullWorkflowSimulation:
    """Simulate complete Agent creation → test → publish → Retest process."""

    REQUEST = "I want an assistant who can identify financial reporting risk signals, focusing on goodwill impairment, accounts receivable anomalies, and cash flow deterioration."

    def _make_agent_builder_state(self, turn: int = 1, **overrides) -> AgentBuilderState:
        """Create a mocked AgentBuilderState."""
        state = new_agent_builder_state(
            thread_id=f"test-full-flow-{turn}",
            user_id="test-user",
            user_message=overrides.pop("user_message", self.REQUEST),
        )
        state.update(overrides)
        return state

    # ── Round 1: New session → Requirements exploration ──

    def test_round1_new_session(self):
        """Round 1: User speaks for the first time → requirement_intake. """
        state = self._make_agent_builder_state(turn=1)
        target = route_start(state)
        assert target == "requirement_intake"
        # Simulate node_requirement_intake after execution
        state["current_node"] = "wait_intake_confirmation"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["stage"] = "exploring"
        state["awaiting_user"] = True
        state["final_response"] = "What specific financial reporting risk signals would you like to identify?"
        assert state["current_node"] == "wait_intake_confirmation"
        assert state["awaiting_user"] is True

    # ── Round 2: Requirements Validation → Ability search ──

    def test_round2_confirm_intake(self):
        """Round 2: User Confirmation → requirement_confirmation. """
        state = self._make_agent_builder_state(
            turn=2,
            user_message="To confirm, focus on goodwill, accounts receivable and cash flow.",
            current_node="wait_intake_confirmation",
            spec_name="Financial Reporting Risk Identification Assistant",
            stage="exploring",
            message_history=[
                {"role": "agent", "content": "What specific financial reporting risk signals would you like to identify?"},
            ],
        )
        # route_start: wait node → classify_intent
        assert route_start(state) == "classify_intent"
        # Simulate LLM classification results
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.95
        result = route_after_classify(state)
        assert result == "requirement_confirmation"

    # ── Round 3: Test Requests → code extraction → real test ──

    def test_round3_test_with_explicit_symbol(self):
        """Round 3: User explicitly enters stock symbol."""
        state = self._make_agent_builder_state(
            turn=3,
            user_message="600519",
            current_node="wait_test_request",
            spec_name="Financial Reporting Risk Identification Assistant",
            version_id="spec_financial_risk_v1_v1",
            stage="testing",
            message_history=[
                {"role": "agent", "content": "Do you want to test now? For example, enter 600519 (Kweichow Moutai)"},
            ],
        )
        assert route_start(state) == "classify_intent"
        # LLM Category:confirmed + test_symbol Extract
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.92
        state["test_symbol"] = "600519"
        result = route_after_classify(state)
        assert result == "real_data_test"

    def test_round3_test_confirm_agent_suggestion(self):
        """Round 3: User confirms Agent s suggested code ("OK, test it") . """
        state = self._make_agent_builder_state(
            turn=3,
            user_message="OK, let s test it",
            current_node="wait_test_request",
            spec_name="Financial Reporting Risk Identification Assistant",
            version_id="spec_financial_risk_v1_v1",
            stage="testing",
            message_history=[
                {"role": "agent", "content": "Do you want to try pulling a real stock now? For example, enter 600519 (Kweichow Moutai)"},
            ],
        )
        assert route_start(state) == "classify_intent"
        # LLM infer from context test_symbol
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.90
        state["test_symbol"] = "600519"
        assert route_after_classify(state) == "real_data_test"

    def test_round3_test_no_symbol_clarifies(self):
        """Round 3: User did not provide code → Clarification examples."""
        state = self._make_agent_builder_state(
            turn=3,
            user_message="Test it",
            current_node="wait_test_request",
            spec_name="Financial Reporting Risk Identification Assistant",
            version_id="spec_financial_risk_v1_v1",
            stage="testing",
            message_history=[
                {"role": "agent", "content": "Want to test? Provide a ticker symbol"},
            ],
        )
        assert route_start(state) == "classify_intent"
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.85
        state["test_symbol"] = ""
        result = route_after_classify(state)
        assert result == "wait_test_request"
        assert state["clarification_needed"] is True

    # ── Round 4: Assessment then retest ──

    def test_round4_retry_different_symbol(self):
        """Round 4: Request for stock exchange and retest after release."""
        state = self._make_agent_builder_state(
            turn=4,
            user_message="Test again in the CATL era",
            current_node="wait_evaluation",
            spec_name="Financial Reporting Risk Identification Assistant",
            version_id="spec_financial_risk_v1_v1",
            official_acceptance_decision="published",
            stage="completed",
            message_history=[
                {"role": "agent", "content": "The test is completed, Moutai s financial report risk score is 75, and it has been released."},
            ],
        )
        assert route_start(state) == "classify_intent"
        state["user_intent"] = "retry"
        state["intent_confidence"] = 0.92
        state["test_symbol"] = "300750"
        result = route_after_classify(state)
        assert result == "wait_test_request"

    def test_round4_revise_add_dimension(self):
        """Round 4: Add dimensions of analysis after assessment."""
        state = self._make_agent_builder_state(
            turn=4,
            user_message="Add another dimension of profit quality analysis",
            current_node="wait_evaluation",
            spec_name="Financial Reporting Risk Identification Assistant",
            stage="completed",
            message_history=[
                {"role": "agent", "content": "The three-dimensional risk analysis of goodwill, receivables and cash flow is ready."},
            ],
        )
        assert route_start(state) == "classify_intent"
        state["user_intent"] = "revise"
        state["intent_confidence"] = 0.93
        result = route_after_classify(state)
        assert result == "requirement_intake"

    # ── Round 5: Low Confidence Clarification ──

    def test_round5_ambiguous_reply(self):
        """Round 5: User responses are vague → LLM low confidence → Return to current node + Clarify."""
        state = self._make_agent_builder_state(
            turn=5,
            user_message="take a look",
            current_node="wait_evaluation",
            spec_name="Financial Reporting Risk Identification Assistant",
            stage="completed",
            message_history=[
                {"role": "agent", "content": "Testing is complete, do you want to publish or retest?"},
            ],
        )
        assert route_start(state) == "classify_intent"
        state["user_intent"] = "explore_more"
        state["intent_confidence"] = 0.35
        result = route_after_classify(state)
        assert result == "wait_evaluation"
        assert state["clarification_needed"] is True

    # ── Round 6: new_agent intent ──

    def test_round6_new_agent_intent(self):
        """Round 6: Released Agents are asked to do new functions → Identified as new_agent."""
        state = self._make_agent_builder_state(
            turn=6,
            user_message="I want to create a new public opinion monitoring agent instead of changing the current one.",
            current_node="wait_evaluation",
            spec_name="Financial Reporting Risk Identification Assistant",
            official_acceptance_decision="published",
            stage="completed",
            message_history=[
                {"role": "agent", "content": "The Financial Reporting Risk Identification Assistant has been released and you can continue to test other targets."},
            ],
        )
        assert route_start(state) == "classify_intent"
        state["user_intent"] = "new_agent"
        state["intent_confidence"] = 0.96
        result = route_after_classify(state)
        assert result == "end"
        assert "New Agent" in state.get("final_response", "") or "Create" in state.get("final_response", "")

    # ── Round 7: Abnormal Recovery ──

    def test_round7_error_recovery_retry(self):
        """Round 7: Error recovery phase confirms retries."""
        state = self._make_agent_builder_state(
            turn=7,
            user_message="Try again",
            current_node="error_recovery",
            spec_name="Financial Reporting Risk Identification Assistant",
            errors=[
                {"node": "gap_analysis", "error": "analyze_agent_workshop_gaps timeout"},
            ],
            stage="error",
            message_history=[
                {"role": "agent", "content": "Capability search timed out, do you want to retry or modify the requirements?"},
            ],
        )
        assert route_start(state) == "classify_intent"
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.88
        # route_after_classify → error_recovery the confirmed branch
        # Should return to the previous retryable node
        result = route_after_classify(state)
        # At least it can't be end
        assert result != "end"


# ====================================================================
# Part 6: JSON Extraction Boundary Testing
# ====================================================================

class TestJsonExtraction:
    """Test JSON extraction of LLM return content."""

    def test_extract_valid_json(self):
        result = _extract_json_from_result('{"intent": "confirmed", "confidence": 0.9}')
        assert result.get("intent") == "confirmed"

    def test_extract_json_with_markdown_codeblock(self):
        result = _extract_json_from_result(
            '```json\n{"intent": "retry", "confidence": 0.85}\n```'
        )
        assert result.get("intent") == "retry"

    def test_extract_nested_json_string(self):
        result = _extract_json_from_result(
            '{"intent": "retry", "confidence": 0.92, "test_symbol": "300750"}'
        )
        assert result["intent"] == "retry"
        assert result["test_symbol"] == "300750"

    def test_extract_json_with_surrounding_text(self):
        result = _extract_json_from_result(
            'Users should retest.\n{"intent": "retry", "confidence": 0.9}\n Got it.'
        )
        assert result.get("intent") == "retry"

    def test_extract_empty_or_invalid(self):
        assert _extract_json_from_result("") == {}
        assert _extract_json_from_result("hello world") == {}
        assert _extract_json_from_result(None) == {}


# ====================================================================
# Part Seven: Complete Process Snapshot Test
# ====================================================================

class TestCompleteFlowSnapshot:
    """
    Snapshot of node flow simulating a complete 8-round dialogue of Financial Reporting Risk Identification Assistant .

    Expected process:
      1. Users raise demands → requirement_intake → wait_intake_confirmation
      2. User confirmation requirements → requirement_confirmation → wait_requirement_confirmation
      3. User confirmation specifications → gap_analysis → plan_generation
      4. User options → generate_candidate_agent → build_or_ready → wait_test_request
      5. User gives code → real_data_test → wait_evaluation
      6. User confirms release → evaluate_or_publish → wait_evaluation (Published)
      7. User requests to retest another stock → classify_intent (retry) → wait_test_request
      8. User gives new code → real_data_test → wait_evaluation
    """

    def _simulate_turn(self, state: AgentBuilderState, user_msg: str,
                       intent: str, confidence: float = 0.9, **extra) -> Tuple[str, AgentBuilderState]:
        """Simulate a complete interaction:route_start → classify_intent → route_after_classify. """
        state["user_message"] = user_msg
        # Append to conversation history
        history = state.setdefault("message_history", [])
        if state.get("final_response"):
            history.append({"role": "agent", "content": state["final_response"]})
        history.append({"role": "user", "content": user_msg})
        if len(history) > 20:
            state["message_history"] = history[-20:]

        # routing
        start_target = route_start(state)
        assert start_target == "classify_intent", \
            f"Expected classify_intent, got {start_target} (current_node={state.get('current_node')})"

        # LLM Classification
        state["user_intent"] = intent
        state["intent_confidence"] = confidence
        for k, v in extra.items():
            state[k] = v

        result = route_after_classify(state)
        return result, state

    def test_full_flow_8_turns(self):
        """Full 8-round dialogue snapshot test."""
        # ── Round 1: New ──
        state = new_agent_builder_state("snapshot-001", "user-001",
                                         user_message=TEST_USER_REQUEST)
        target = route_start(state)
        assert target == "requirement_intake"
        state["current_node"] = "wait_intake_confirmation"
        state["stage"] = "exploring"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["awaiting_user"] = True
        state["final_response"] = "Your need is to identify financial reporting risks and focus on goodwill impairment, accounts receivable and cash flow. You need to confirm the following points:[...]\n\n Do you agree to these settings?"

        # ── Round 2: Identify needs ──
        target, state = self._simulate_turn(
            state, "Confirm, no problem", "confirmed", 0.95,
        )
        assert target == "requirement_confirmation"
        state["current_node"] = "wait_requirement_confirmation"
        state["stage"] = "confirming"
        state["awaiting_user"] = True
        state["final_response"] = "[Requirement confirmation completed]"

        # ── Round 3: Confirm Specs ──
        target, state = self._simulate_turn(
            state, "Okay, according to this specification", "confirmed", 0.95,
        )
        assert target == "gap_analysis"
        # Simulate automatic flow (no more user input required, complete gap analysis → Plan generation)
        state["current_node"] = "wait_plan_selection"
        state["stage"] = "selecting"
        state["awaiting_user"] = True
        state["pending_options"] = [
            {"id": "plan_standard", "label": "A", "title": "Standard solution"},
            {"id": "plan_advanced", "label": "B", "title": "Advanced plan"},
        ]
        state["final_response"] = "I generated two plans for you:[...]\n Please select A or B."

        # ── Round 4: Choices ──
        target, state = self._simulate_turn(
            state, "Choose B, advanced plan", "select_option", 0.95,
            user_selected_id="plan_advanced",
        )
        assert target == "generate_candidate_agent"
        state["current_node"] = "wait_test_request"
        state["stage"] = "testing"
        state["awaiting_user"] = True
        state["version_id"] = "spec_financial_risk_v1"
        state["build_status"] = "built"
        state["final_response"] = "Agent Generated! Version v1, do you want to test it with real stocks? For example, 600519 (Kweichow Moutai)."

        # ── Round 5: Put the code to the test ──
        target, state = self._simulate_turn(
            state, "600519", "confirmed", 0.92,
            test_symbol="600519",
        )
        assert target == "real_data_test"
        state["current_node"] = "wait_evaluation"
        state["stage"] = "evaluating"
        state["awaiting_user"] = True
        state["test_result"] = {"status": "pass", "score": 78}
        state["final_response"] = "Moutai 600519 financial report risk score is 78, goodwill risk: low, receivable risk: medium, cash flow risk: low. Want to publish?"

        # ── Round 6: Release ──
        target, state = self._simulate_turn(
            state, "publish", "confirmed", 0.95,
        )
        assert target == "evaluate_or_publish"
        state["current_node"] = "wait_evaluation"
        state["official_acceptance_decision"] = "published"
        state["stage"] = "completed"
        state["awaiting_user"] = True
        state["final_response"] = "Published successfully! You can continue to test other targets or modify requirements."

        # ── Round 7: Retest another stock ──
        target, state = self._simulate_turn(
            state, "Test again in the CATL era", "retry", 0.92,
            test_symbol="300750",
        )
        assert target == "wait_test_request"
        # retry Routed to wait_test_request, but simulate_turn will not actually execute the node,
        # So you need to manually change current_node to wait_test_request
        state["current_node"] = "wait_test_request"
        state["stage"] = "testing"
        state["awaiting_user"] = True
        state["final_response"] = "Received! Should we conduct a financial reporting risk test on CATL (300750)? Please confirm."

        # ── Round 8: Give new code ──
        target, state = self._simulate_turn(
            state, "300750", "confirmed", 0.95,
            test_symbol="300750",
        )
        assert target == "real_data_test"

    def test_single_turn_cancel_mid_flow(self):
        """Cancel midway → end. """
        state = new_agent_builder_state("cancel-001", "user-001")
        state["current_node"] = "wait_evaluation"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["final_response"] = "Want to publish?"

        target, state = self._simulate_turn(
            state, "Forget it", "cancel", 0.95,
        )
        assert target == "end"

    def test_round8_after_publish_user_asks_question(self):
        """Users chatted and asked questions after publishing → explore_more → stay wait_evaluation + Clarify."""
        state = new_agent_builder_state("question-001", "user-001")
        state["current_node"] = "wait_evaluation"
        state["official_acceptance_decision"] = "published"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["final_response"] = "Published."

        target, state = self._simulate_turn(
            state, "What data sources do you support?", "explore_more", 0.55,
        )
        # low confidence → stay
        assert target == "wait_evaluation"
        assert state["clarification_needed"] is True


# ====================================================================
# Helper function
# ====================================================================

def new_state(user_message: str = "", **overrides) -> AgentBuilderState:
    """Quickly create states for testing."""
    state = new_agent_builder_state(
        thread_id="test-thread",
        user_id="test-user",
        user_message=user_message,
    )
    state.update(overrides)
    return state


def headline_request() -> str:
    return TEST_USER_REQUEST


# ====================================================================
# Can be run independently smoke test
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Agent Builder Full process verification (smoke)")
    print("=" * 60)

    failed: List[str] = []
    passed: List[str] = []

    def check(name: str, cond: bool, detail: str = ""):
        if cond:
            passed.append(name)
            print(f"  ✅ {name}")
        else:
            failed.append(f"{name} -- {detail}")
            print(f"  ❌ {name}  -- {detail}")

    # ── Status ──
    s = new_agent_builder_state("t1", "u1", user_message=headline_request())
    check("Create status", s["current_node"] == "START" and s["thread_id"] == "t1")
    check("The whitelist contains message_history", "message_history" in _KNOWN_KEYS)
    check("The whitelist contains user_intent", "user_intent" in _KNOWN_KEYS)

    # ── routing ──
    check("new session → requirement_intake", route_start(s) == "requirement_intake")
    s["current_node"] = "wait_evaluation"
    check("wait node → classify_intent", route_start(s) == "classify_intent")

    s["user_intent"] = "cancel"
    s["intent_confidence"] = 0.9
    check("cancel → end", route_after_classify(s) == "end")

    # ── Intent classification ──
    check("Node type mapping", _classify_node_type("wait_evaluation") == "test_eval")
    check("Bottom line classification", _fallback_classify_intent("Cancel", "wait_evaluation") == "cancel")
    check("Stay prediction", _will_stay_on_wait_node(
        new_state("What does it mean", current_node="wait_intake_confirmation", user_intent="explore_more")
    ) is True)

    # ── prompt word ──
    prompt = _build_classify_prompt(s, "test_eval")
    check("Prompt word generation", len(prompt) > 100, f"length: {len(prompt)}")

    # ── JSON ──
    j = _extract_json_from_result('{"a": 1}')
    check("JSON Extract", j == {"a": 1})

    print(f"\n{'=' * 60}")
    print(f"result: {len(passed)} Pass, {len(failed)} failed")
    print(f"{'=' * 60}")
    if failed:
        sys.exit(1)
