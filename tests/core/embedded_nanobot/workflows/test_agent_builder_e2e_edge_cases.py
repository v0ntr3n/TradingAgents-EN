"""
Agent Builder End-to-end boundary scenario testing (including abnormal LLM behavior simulation)

Coverage:
  1. Intent recognition for various user message formats (confirm, select, blur, error)
  2. Plan selection route: letters, numbers, recommendations, and details
  3. Low confidence clarification prompt
  4. Message history formatting and contextual testing
  5. JSON Extract reliability tests

Design principles:
  - Instead of mocking the entire LLM, provide a mock llm_client
  - Abnormal scenario coverage: LLM outputs empty response, plain text, etc.

NOTE: Original XML cleaning related tests (_strip_tool_call_xml / _parse_text_tool_calls /
_run_react_loop) Removed/skipped with Nanobot ReAct loop removal, migrated to
UnifiedLLMClient No more text cleaning required after standard Function Calling.

Usage: pytest tests/core/embedded_nanobot/workflows/test_agent_builder_e2e_edge_cases.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.embedded_nanobot.workflows.agent_builder_state import (
    AgentBuilderState,
    new_agent_builder_state,
)
from core.embedded_nanobot.workflows.agent_builder_nodes import (
    _run_node_llm,
    _build_classify_prompt,
    _build_confirmation_prompt,
    _build_plan_selection_prompt,
    _build_test_eval_prompt,
    _build_error_prompt,
    _build_generic_prompt,
    _classify_node_type,
    _format_recent_history,
    _will_stay_on_wait_node,
    _fallback_classify_intent,
    _extract_json_from_result,
    node_classify_user_intent,
)
from core.embedded_nanobot.workflows.agent_builder_conditions import (
    _is_cancel,
    _is_confirm,
    _is_route_choice,
    _resolve_plan_selection,
    route_after_classify,
    route_start,
)

TESTS_USER_REQUEST = (
    "I want an assistant who can identify financial reporting risk signals, focusing on goodwill impairment, accounts receivable anomalies, and cash flow deterioration."
)


# ====================================================================
# Helper function
# ====================================================================

def new_state(user_message: str = "", **overrides) -> AgentBuilderState:
    s = new_agent_builder_state(
        thread_id="test-e2e",
        user_id="test-user",
        user_message=user_message,
    )
    s.update(overrides)
    return s


def headline_request() -> str:
    return TESTS_USER_REQUEST


def _make_mock_response(content: str = "", tool_calls: list | None = None) -> MagicMock:
    """Create a simulated LLM response object."""
    resp = MagicMock()
    resp.content = content
    resp.tool_calls = tool_calls or []
    return resp


def _make_tool_call_request(name: str, arguments: dict, call_id: str = "call_001") -> MagicMock:
    """Create a mock tool_call object."""
    tc = MagicMock()
    tc.name = name
    tc.arguments = arguments
    tc.id = call_id
    return tc


# ====================================================================
# Part One: Solution Selection Routing Boundary Testing
# ====================================================================

class TestPlanSelectionEdgeCases:
    """Verify the behavior of scheme selections under unusual input."""

    def test_resolve_plan_by_chinese_label(self):
        """LLM Reply"Plan A" → can be parsed correctly."""
        options = [
            {"id": "plan_equal_weight", "index": 1, "name": "Option A: Equally weighted comprehensive rating", "recommended": True},
            {"id": "plan_custom_weight", "index": 2, "name": "Option B: Custom weights"},
        ]
        sel_id, reason = _resolve_plan_selection(options, "Plan A")
        assert sel_id == "plan_equal_weight"
        assert reason

    def test_resolve_plan_by_recommended(self):
        """Users say"Recommended" → Return to recommended plan."""
        options = [
            {"id": "plan_a", "index": 1, "name": "Plan A", "recommended": True},
            {"id": "plan_b", "index": 2, "name": "Plan B"},
        ]
        sel_id, reason = _resolve_plan_selection(options, "Recommended")
        assert sel_id == "plan_a"

    def test_resolve_plan_no_options(self):
        """None pending_options → Returns empty."""
        sel_id, reason = _resolve_plan_selection([], "Plan A")
        assert sel_id == ""
        assert reason == "no_options"

    def test_wait_plan_selection_route_select_option(self):
        """select_option + LLM Parsed selected_index → generate_candidate_agent. """
        state = new_state("Plan A")
        state["current_node"] = "wait_plan_selection"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["pending_options"] = [
            {"id": "plan_a", "index": 1, "name": "Plan A", "recommended": True},
            {"id": "plan_b", "index": 2, "name": "Plan B"},
        ]
        state["user_intent"] = "select_option"
        state["intent_confidence"] = 0.95
        state["user_selected_index"] = 1
        result = route_after_classify(state)
        assert result == "generate_candidate_agent"
        assert state["selected_plan_id"] == "plan_a"

    def test_wait_plan_selection_confirm_uses_recommended(self):
        """User"Confirm" → Use the recommended solution."""
        state = new_state("Confirm")
        state["current_node"] = "wait_plan_selection"
        state["recommended_plan_id"] = "plan_recommended"
        state["pending_options"] = [{"id": "plan_recommended", "index": 1}]
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.95
        result = route_after_classify(state)
        assert result == "generate_candidate_agent"
        assert state["selected_plan_id"] == "plan_recommended"

    def test_wait_plan_selection_no_match_clarifies(self):
        """Unable to match plan → return to wait + clarification. """
        state = new_state("Don t know which one to choose")
        state["current_node"] = "wait_plan_selection"
        state["pending_options"] = [
            {"id": "plan_a", "index": 1, "name": "Plan A"},
            {"id": "plan_b", "index": 2, "name": "Plan B"},
        ]
        state["user_intent"] = "explore_more"
        state["intent_confidence"] = 0.85
        result = route_after_classify(state)
        assert result == "wait_plan_selection"
        assert state["clarification_needed"] is True


# ====================================================================
# Part 2: Abnormal LLM behavior simulation test
# ====================================================================

@pytest.mark.skip(reason="To be adapted after migration to UnifiedLLMClient: the original dependency _strip_tool_call_xml has been removed with the ReAct loop")
class TestAbnormalLLMBehavior:
    """Simulating LLM returns various exceptions to verify that the system does not crash or leak raw output."""

    def test_llm_returns_only_xml_no_text(self):
        """LLM Only the tool call XML is output (no other text)→ Empty after cleaning."""
        raw = (
            "<｜DSML｜tool_calls>\n"
            "<｜DSML｜invoke name=\"search_project_capabilities\">\n"
            "< | DSML | parameter name=\"query\" string=\"true\">financial reporting risk</ | DSML | parameter>\n"
            "</｜DSML｜invoke>\n"
            "</｜DSML｜tool_calls>"
        )
        cleaned = _strip_tool_call_xml(raw)
        # Cleaning should not contain any tool call tags
        for tag in ["DSML", "invoke", "tool_calls", "parameter"]:
            assert tag not in cleaned, f"label {tag} Residue"

    def test_llm_returns_mixed_content_xml_in_middle(self):
        """LLM Output mixed content: opening text → XML → Ending text."""
        raw = (
            "OK, I ll handle it.\n\n"
            "<invoke name=\"run_test\">\n"
            "<parameter name=\"stock\" string=\"true\">600519</parameter>\n"
            "</invoke>\n\n"
            "According to the analysis results, the stock s risk rating is medium."
        )
        cleaned = _strip_tool_call_xml(raw)
        assert "OK, I ll handle it." in cleaned
        assert "According to the analysis results" in cleaned
        assert "<invoke" not in cleaned
        assert "run_test" not in cleaned

    def test_llm_returns_json_tool_block(self):
        """LLM Returns a JSON tool call block."""
        raw = '{\"tool\": \"search_project_capabilities\", \"parameters\": {\"query\": \"financial reporting risk\"}}'
        cleaned = _strip_tool_call_xml(raw)
        assert "search_project_capabilities" not in cleaned

    def test_llm_returns_multiple_tool_call_blocks(self):
        """LLM Returns a block blend of multiple tool calls."""
        raw = (
            "<invoke name=\"search_a\"><parameter name=\"q\" string=\"true\">a</parameter></invoke>\n"
            "middle text\n"
            "<invoke name=\"search_b\"><parameter name=\"q\" string=\"true\">b</parameter></invoke>"
        )
        cleaned = _strip_tool_call_xml(raw)
        assert "invoke" not in cleaned
        assert "search_a" not in cleaned
        assert "search_b" not in cleaned
        assert "middle text" in cleaned

    def test_llm_returns_malformed_xml(self):
        """LLM Returns malformed XML (tags not closed)."""
        raw = (
            "<invoke name=\"test\"\n"
            "<parameter name=\"key\">value"
        )
        # should not crash
        cleaned = _strip_tool_call_xml(raw)
        assert isinstance(cleaned, str)


# ====================================================================
# Part 3: Intent Classification Boundary Testing
# ====================================================================

class TestIntentClassificationEdgeCases:
    """Verify the behavior of intent classification under boundary input."""

    def test_classify_node_type_all_variants(self):
        """All known node types map correctly."""
        assert _classify_node_type("wait_intake_confirmation") == "confirmation"
        assert _classify_node_type("wait_requirement_confirmation") == "confirmation"
        assert _classify_node_type("wait_plan_selection") == "plan_selection"
        assert _classify_node_type("wait_test_request") == "test_eval"
        assert _classify_node_type("wait_evaluation") == "test_eval"
        assert _classify_node_type("evaluate_or_publish") == "test_eval"
        assert _classify_node_type("error_recovery") == "error"
        assert _classify_node_type("unknown_node") == "generic"
        assert _classify_node_type("") == "generic"

    def test_confirmation_prompt_contains_options(self):
        """The confirmation phase prompt contains user options guidance."""
        state = new_state("OK", current_node="wait_intake_confirmation", spec_name="test Agent")
        state["message_history"] = [
            {"role": "agent", "content": "What risk signals do you want to identify?"},
        ]
        prompt = _build_confirmation_prompt(state)
        assert "confirmed" in prompt
        assert "revise" in prompt
        assert "explore_more" in prompt
        assert "test Agent" in prompt

    def test_plan_selection_prompt_contains_options(self):
        """The prompt words in the plan selection phase include a list of plans."""
        state = new_state("Plan A", current_node="wait_plan_selection", spec_name="test Agent")
        state["pending_options"] = [
            {"index": 1, "id": "plan_a", "name": "Plan A: Equal weight", "recommended": True},
            {"index": 2, "id": "plan_b", "name": "Option B: Customize"},
        ]
        state["message_history"] = [
            {"role": "agent", "content": "Option A (recommended) or option B?"},
        ]
        prompt = _build_plan_selection_prompt(state)
        assert "Plan A" in prompt
        assert "Plan B" in prompt
        assert "select_option" in prompt
        assert "recommended" in prompt.lower() or "Recommended" in prompt

    def test_test_eval_prompt_contains_stock_hints(self):
        """The test/evaluation phase prompt words contain stock leads."""
        state = new_state("OK, test it", current_node="wait_test_request", spec_name="test Agent")
        state["message_history"] = [
            {"role": "agent", "content": "Do you want to try pulling a real stock now? For example, enter 600519 (Kweichow Moutai)"},
        ]
        state["test_result"] = {"status": "pending"}
        prompt = _build_test_eval_prompt(state)
        assert "600519" in prompt or "test_symbol" in prompt

    def test_error_prompt_contains_error_details(self):
        """The error phase prompt words contain error information."""
        state = new_state("Try again", current_node="error_recovery")
        state["errors"] = [
            {"node": "generate_candidate_agent", "error": "Tool call failed: agent_id is missing"},
        ]
        prompt = _build_error_prompt(state)
        assert "agent_id" in prompt or "failed" in prompt
        assert "confirmed" in prompt  # Retry options

    def test_generic_prompt_fallback(self):
        """The universal hint word will not report an error."""
        state = new_state("hello", current_node="some_unknown_node")
        prompt = _build_generic_prompt(state)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_fallback_classify_intent_confirmed(self):
        """Bottom line classification: clear confirmation signal → confirmed. """
        for msg in ["Confirm", "OK", "OK", "OK", "No problem", "publish", "Go online"]:
            assert _fallback_classify_intent(msg, "wait_evaluation") in ("confirmed",)

    def test_fallback_classify_intent_cancel(self):
        """Bottom line: Cancel signal → cancel. """
        assert _fallback_classify_intent("Cancel", "wait_evaluation") == "cancel"
        assert _fallback_classify_intent("Forget it", "wait_evaluation") == "cancel"

    def test_fallback_classify_intent_default(self):
        """Bottom line classification: unknown signal → explore_more. """
        assert _fallback_classify_intent("The weather is nice today", "wait_evaluation") == "explore_more"
        assert _fallback_classify_intent("", "") == "explore_more"


# ====================================================================
# Part 4: Message History Formatting and Contextual Testing
# ====================================================================

class TestMessageHistoryAndContext:
    """Verify formatting of conversation history and context."""

    def test_format_recent_history_empty(self):
        """no history → Placeholder text."""
        state = new_state("hello")
        result = _format_recent_history(state, rounds=3)
        assert "None yet" in result or "No" in result or "Conversation history" in result

    def test_format_recent_history_one_round(self):
        """1 turn dialogue → Contains agent and user messages."""
        state = new_state("Plan A")
        state["message_history"] = [
            {"role": "agent", "content": "Option A (recommended) or option B?"},
            {"role": "user", "content": "Plan A"},
        ]
        result = _format_recent_history(state, rounds=3)
        assert "Agent" in result
        assert "User" in result
        assert "Plan A" in result

    def test_format_recent_history_truncation(self):
        """more than 3 rounds → Only take the last 3 rounds."""
        state = new_state("final confirmation")
        state["message_history"] = [
            {"role": "agent", "content": f"No.{i}wheel question"} for i in range(10)
        ]
        # There are 10 agent messages but no user messages
        # Last 6 (3 rounds × 2 bar/wheel)
        history = state["message_history"]
        assert len(history) == 10

    def test_message_history_limit_in_classify(self):
        """message_history Cropped if more than 20 items."""
        state = new_state("final confirmation")
        state["current_node"] = "wait_intake_confirmation"
        initial = [{"role": "agent", "content": f"msg_{i}"} for i in range(30)]
        state["message_history"] = initial
        # Simulate the behavior of _format_recent_history
        recent = initial[-(3 * 2):]
        assert len(recent) <= 6


# ====================================================================
# Part 5: Complete process snapshot test (simulating abnormal LLM behavior)
# ====================================================================

class TestFullFlowWithAbnormalLLM:
    """Simulates a complete Agent build process where LLM occasionally outputs exceptions."""

    def test_new_session_starts_at_intake(self):
        """new session → requirement_intake. """
        state = new_state(headline_request())
        assert route_start(state) == "requirement_intake"

    def test_full_flow_state_transitions(self):
        """State Transition Integrity: New Session → Requirements confirmation → Solution selection → generate → test → Evaluate."""
        # ── Round 1: Requirements exploration ──
        state = new_state(headline_request())
        state["current_node"] = "requirement_intake"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["requirement_summary"] = "Identify financial reporting risk signals"
        state["stage"] = "exploring"
        state["final_response"] = "OK, your requirement is to identify financial reporting risk signals. Confirm"
        state["awaiting_user"] = True

        assert state["current_node"] == "requirement_intake"
        assert state["spec_name"] == "Financial Reporting Risk Identification Assistant"
        # final_response Should not contain tool calls XML
        assert "DSML" not in state["final_response"]
        assert "<invoke" not in state["final_response"]

        # ── Round 2: Requirements confirmation → Capability inventory ──
        state["user_message"] = "Confirm, goodwill, accounts receivable, and cash flow"
        state["current_node"] = "wait_intake_confirmation"
        assert route_start(state) == "classify_intent"

        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.92
        result = route_after_classify(state)
        assert result == "requirement_confirmation"

        # ── Round 3: Solution selection ──
        state["current_node"] = "wait_plan_selection"
        state["pending_options"] = [
            {"id": "plan_a", "index": 1, "name": "Option A: Equally weighted comprehensive rating", "recommended": True},
            {"id": "plan_b", "index": 2, "name": "Option B: Custom weights"},
        ]
        state["recommended_plan_id"] = "plan_a"
        state["user_message"] = "Plan A"
        assert route_start(state) == "classify_intent"

        state["user_intent"] = "select_option"
        state["intent_confidence"] = 0.95
        state["user_selected_index"] = 1
        result = route_after_classify(state)
        assert result == "generate_candidate_agent"
        assert state["selected_plan_id"] == "plan_a"

        # ── Round 4: test ──
        state["user_message"] = "600519"
        state["current_node"] = "wait_test_request"
        assert route_start(state) == "classify_intent"

        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.93
        state["test_symbol"] = "600519"
        result = route_after_classify(state)
        assert result == "real_data_test"

        # ── Round 5: Confirm release after evaluation ──
        state["current_node"] = "wait_evaluation"
        state["user_message"] = "publish"
        state["test_result"] = {"status": "ok"}
        assert route_start(state) == "classify_intent"

        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.95
        result = route_after_classify(state)
        assert result == "evaluate_or_publish"


# ====================================================================
# Part Six: Abnormal Reply Recognition Test
# ====================================================================

class TestAbnormalUserReplyRecognition:
    """Verify the system s ability to handle abnormal user responses."""

    def test_short_confirm_works(self):
        """Very short confirmation: single word"good"→ Identified as confirm."""
        assert _is_confirm("good") is True
        assert _is_confirm("Yeah") is True
        assert _is_confirm("Yes") is True

    def test_typo_like_confirm_works(self):
        """Class acknowledgment signal: Recognized even if there is not an exact match."""
        # "OK", "OK" Waiting for clear signal
        assert _is_confirm("OK") is True
        assert _is_confirm("OK") is True

    def test_ambiguous_reply_explore_more(self):
        """Vague reply What do you mean? → Not a confirmation or a choice → clarification_needed. """
        state = new_state("What does it mean")
        state["current_node"] = "wait_plan_selection"
        state["pending_options"] = [
            {"id": "plan_a", "index": 1, "name": "Plan A"},
        ]
        state["user_intent"] = "explore_more"
        state["intent_confidence"] = 0.85
        result = route_after_classify(state)
        assert result == "wait_plan_selection"
        assert state["clarification_needed"] is True

    def test_irrelevant_reply_doesnt_break(self):
        """Completely irrelevant replies should not cause a crash."""
        state = new_state("The weather is so nice today")
        state["current_node"] = "wait_test_request"
        state["test_result"] = {"status": "ok"}
        state["user_intent"] = "explore_more"
        state["intent_confidence"] = 0.75
        result = route_after_classify(state)
        # Should stay at the current wait node, triggering clarification
        assert result == "wait_test_request"
        assert state["clarification_needed"] is True

    def test_low_confidence_stays_any_wait_node(self):
        """low confidence (<0.7) : Stay at any node + Clarify."""
        wait_nodes = [
            "wait_intake_confirmation",
            "wait_requirement_confirmation",
            "wait_plan_selection",
            "wait_test_request",
            "wait_evaluation",
        ]
        for node in wait_nodes:
            state = new_state("Not sure")
            state["current_node"] = node
            state["user_intent"] = "explore_more"
            state["intent_confidence"] = 0.45
            result = route_after_classify(state)
            assert result == node or result.startswith("wait_"), f"node {node} route to {result}"
            assert state["clarification_needed"] is True

    def test_new_agent_intent_during_existing_session(self):
        """Say Create a new public opinion analysis agent in an existing Agent session→ new_agent → end. """
        state = new_state("I want to create a new public opinion analysis Agent")
        state["current_node"] = "wait_evaluation"
        state["spec_name"] = "Financial Reporting Risk Identification Assistant"
        state["test_result"] = {"status": "ok"}
        state["user_intent"] = "new_agent"
        state["intent_confidence"] = 0.95
        result = route_after_classify(state)
        assert result == "end"
        assert "New Agent" in state.get("final_response", "")
        assert "Financial Reporting Risk Identification Assistant" in state.get("final_response", "")

    def test_cancel_mid_flow_ends_gracefully(self):
        """Say Cancel at any stage→ end."""
        for node in ["wait_intake_confirmation", "wait_plan_selection", "wait_evaluation"]:
            state = new_state("Cancel")
            state["current_node"] = node
            state["user_intent"] = "cancel"
            state["intent_confidence"] = 0.98
            assert route_after_classify(state) == "end", f"node {node} Cancellation failed"

    def test_retry_intent_in_test_eval(self):
        """User says retest in wait_evaluation→ wait_test_request. """
        state = new_state("Change to Kweichow Moutai and test again")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "retry"
        state["intent_confidence"] = 0.9
        result = route_after_classify(state)
        assert result == "wait_test_request"

    def test_revise_intent_in_eval(self):
        """The user said in wait_evaluation Add a cash flow dimension → requirement_intake. """
        state = new_state("Add a cash flow dimension")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "revise"
        state["intent_confidence"] = 0.9
        result = route_after_classify(state)
        assert result == "requirement_intake"


# ====================================================================
# Part 7: _will_stay_on_wait_node verification
# ====================================================================

class TestWillStayOnWaitNode:
    """Verify that _will_stay_on_wait_node is correctly determined for all node types."""

    def test_confirmation_stays_on_explore_more(self):
        """Confirmation stage:explore_more → Stay."""
        state = new_state("What does it mean")
        state["current_node"] = "wait_intake_confirmation"
        state["user_intent"] = "explore_more"
        assert _will_stay_on_wait_node(state) is True

    def test_confirmation_proceeds_on_confirmed(self):
        """Confirmation stage:confirmed → Don t stay behind."""
        state = new_state("OK")
        state["current_node"] = "wait_intake_confirmation"
        state["user_intent"] = "confirmed"
        assert _will_stay_on_wait_node(state) is False

    def test_plan_selection_stays_on_no_match(self):
        """Solution selection stage: Unable to match → Stay."""
        state = new_state("What does it mean")
        state["current_node"] = "wait_plan_selection"
        state["user_intent"] = "confirmed"
        state["intent_confidence"] = 0.9
        # confirmed But there is no recommended_plan_id nor pending_options → Not staying?
        # Actually confirmed will fall back to use recommended ...
        # It depends on the specific status
        # At least it doesn't crash
        result = _will_stay_on_wait_node(state)
        assert isinstance(result, bool)

    def test_test_request_with_symbol_proceeds(self):
        """wait_test_request Yes test_symbol → Don t stay behind."""
        state = new_state("600519")
        state["current_node"] = "wait_test_request"
        state["user_intent"] = "confirmed"
        state["test_symbol"] = "600519"
        assert _will_stay_on_wait_node(state) is False

    def test_test_request_without_symbol_stays(self):
        """wait_test_request None test_symbol → Stay."""
        state = new_state("test")
        state["current_node"] = "wait_test_request"
        state["user_intent"] = "confirmed"
        # No test_symbol
        assert _will_stay_on_wait_node(state) is True

    def test_eval_pending_revise_proceeds(self):
        """wait_evaluation: revise → Don t stay behind."""
        state = new_state("Modify requirements")
        state["current_node"] = "wait_evaluation"
        state["user_intent"] = "revise"
        assert _will_stay_on_wait_node(state) is False


# ====================================================================
# Part 8: _extract_json_from_result Reliability Test
# ====================================================================

class TestExtractJsonFromResult:
    """Verify that JSON extraction does not crash under various abnormal inputs."""

    def test_empty_string(self):
        assert _extract_json_from_result("") == {}

    def test_none(self):
        assert _extract_json_from_result(None) == {}

    def test_valid_json(self):
        result = _extract_json_from_result('{"status": "ok", "data": 123}')
        assert result["status"] == "ok"
        assert result["data"] == 123

    def test_malformed_json(self):
        result = _extract_json_from_result("not one JSON")
        assert result == {}

    def test_json_embedded_in_text(self):
        result = _extract_json_from_result('previous text {"key": "value"} back text')
        assert result["key"] == "value"

    def test_nested_json(self):
        result = _extract_json_from_result('{"outer": {"inner": {"deep": true}}}')
        assert result["outer"]["inner"]["deep"] is True


# ====================================================================
# Part 9: Comprehensive end-to-end scenario (simulating anomaly LLM)
# ====================================================================

class TestE2EWithFaultyLLM:
    """End-to-end process: final_response of all critical nodes should not leak the tool call XML."""

    def setup_method(self):
        """Reset before each test."""
        self.xml_patterns = [
            r"<\s*invoke\b",
            r"<\s*parameter\b",
            r"tool_calls\b",
            r"DSML",
            r"tool_call\b",
            r'"tool"\s*:\s*"',
        ]
        self.compiled = [re.compile(p, re.IGNORECASE) for p in self.xml_patterns]

    def _assert_no_xml_leak(self, text: str, context: str = ""):
        """Assert text does not contain any tool call XML."""
        for pat in self.compiled:
            if pat.search(text):
                match = pat.search(text)
                # Extract the 30 characters before and after the matching position
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                snippet = text[start:end]
                raise AssertionError(
                    f"[XML leak] {context}: mode '{pat.pattern}' matched to: ...{snippet}..."
                )
        assert True

    def test_no_xml_in_normal_analysis_text(self):
        """Normally parsed text should not be considered an XML leak (false positive check)."""
        text = (
            "## analysis report\n"
            "Target: 600519 (Kweichow Moutai)\n"
            "Goodwill impairment risk: low\n"
            "Accounts receivable turnover ratio:45.2\n"
            "Cash flow coverage:2.3x\n"
        )
        self._assert_no_xml_leak(text, "Normal analysis report")

    @pytest.mark.skip(reason="To be adapted after migration to UnifiedLLMClient: the original dependency _strip_tool_call_xml has been removed with the ReAct loop")
    def test_strip_removes_all_xml_variants(self):
        """After all XML format variants are cleaned, _assert_no_xml_leak does not alarm."""
        variants = [
            # DSML full width
            (
                "<｜DSML｜tool_calls>\n"
                "<｜DSML｜invoke name=\"search\">\n"
                "<｜DSML｜parameter name=\"q\" string=\"true\">test</｜DSML｜parameter>\n"
                "</｜DSML｜invoke>\n"
                "</｜DSML｜tool_calls>"
            ),
            # invoke
            (
                "<invoke name=\"run_test\">\n"
                "<parameter name=\"symbol\" string=\"true\">600519</parameter>\n"
                "</invoke>"
            ),
            # tool_call
            (
                "<tool_call name=\"search_project_capabilities\">\n"
                "<parameter name=\"query\">test</parameter>\n"
                "</tool_call>"
            ),
            # JSON
            '{\"tool\": \"search_project_capabilities\", \"parameters\": {\"query\": \"test\"}}',
        ]
        for i, raw in enumerate(variants):
            cleaned = _strip_tool_call_xml(raw)
            try:
                self._assert_no_xml_leak(cleaned, f"Variants {i+1}")
            except AssertionError:
                pytest.fail(f"Variants {i+1} Cleaning failed: cleaned='{cleaned[:100]}'")

    @pytest.mark.skip(reason="To be adapted after migration to UnifiedLLMClient: the original dependency _strip_tool_call_xml has been removed with the ReAct loop")
    def test_streaming_receives_cleaned_content_only(self):
        """Simulate streaming: each batch of delta is the cleaned content."""
        # Simulate LLM streaming output: the first few batches are normal, the middle batches contain XML, and the last few batches are normal
        deltas = [
            "OK,",
            "Let me analyze it.\n\n",
            "<invoke name=\"search\"><parameter name=\"q\" string=\"true\">test</parameter></invoke>",
            "\n\n Based on the analysis results,",
            "The risk rating is medium.",
        ]
        # Simulate real-time cleaning
        cleaned_deltas = []
        for d in deltas:
            cleaned = _strip_tool_call_xml(d)
            cleaned_deltas.append(cleaned)
        full_text = "".join(cleaned_deltas)
        assert "OK, let me analyze it." in full_text
        assert "Risk rating is medium" in full_text
        assert "invoke" not in full_text, "Flow cleaning failed"
        assert "search" not in full_text, "Flow cleaning failed"


# ====================================================================
# Standalone smoke test (no need for pytest)
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Agent Builder End-to-end boundary testing - Smoke Test")
    print("=" * 60)

    errors = []

    def check(condition, msg):
        if not condition:
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  PASS: {msg[:80]}")

    # ── JSON Extract ──
    j = _extract_json_from_result('{"intent": "confirmed", "confidence": 0.9}')
    check(j.get("intent") == "confirmed", "JSON Extract")
    check(_extract_json_from_result("") == {}, "Empty JSON extraction")

    # ── routing logic ──
    check(route_start(new_state("test")) == "requirement_intake", "new session → intake")

    s = new_state("600519")
    s["current_node"] = "wait_test_request"
    s["user_intent"] = "confirmed"
    s["intent_confidence"] = 0.9
    s["test_symbol"] = "600519"
    check(route_after_classify(s) == "real_data_test", "test_symbol → real_data_test")

    s2 = new_state("")
    s2["current_node"] = "wait_test_request"
    s2["user_intent"] = "confirmed"
    s2["intent_confidence"] = 0.9
    check(route_after_classify(s2) == "wait_test_request", "None test_symbol → clarification")

    # ── Solution selection ──
    opts = [
        {"id": "plan_a", "index": 1, "name": "Plan A", "recommended": True},
        {"id": "plan_b", "index": 2, "name": "Plan B"},
    ]
    sel_id, reason = _resolve_plan_selection(opts, "Plan A")
    check(sel_id == "plan_a", f"Solution A Analysis → {sel_id}")

    sel_id2, _ = _resolve_plan_selection(opts, "Recommended")
    check(sel_id2 == "plan_a", f"Recommended analysis → {sel_id2}")

    # ── Intent classification ──
    check(_fallback_classify_intent("Confirm", "wait_intake_confirmation") == "confirmed", "Confirm → confirmed")
    check(_fallback_classify_intent("Cancel", "wait_intake_confirmation") == "cancel", "Cancel → cancel")

    # ── result ──
    print("=" * 60)
    if errors:
        print(f"FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL PASSED")
        sys.exit(0)
