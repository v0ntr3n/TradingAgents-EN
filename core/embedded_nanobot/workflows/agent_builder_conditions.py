"""
Agent Builder Workflow conditional edge function

each wait_* The conditional judgment logic of the node.
The conditional function does not call LLM, but only makes rule judgment.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from core.embedded_nanobot.workflows.agent_builder_state import AgentBuilderState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Universal confirmation analysis
# ──────────────────────────────────────────────────────────────

def _is_confirm(text: str) -> bool:
    """Whether the user confirms/ok/ok."""
    t = (text or "").strip().lower()
    if not t:
        return False
    confirm_words = (
        "Confirm", "OK", "OK", "OK", "No problem", "No problem anymore",
        "That s it", "click this", "That s right", "Right", "Correct", "ok", "yes",
        "generate", "Start generating", "Generate directly", "Come out", "Let s get started", "continue",
        "yes", "Yes", "Yeah", "good", "By default", "default", "Default scheme",
        "Agree", "Agree", "advance",
        "publish", "Go online", "Confirm release",
    )
    return any(t == w or t.startswith(w) for w in confirm_words)


def _is_route_choice(text: str) -> bool:
    """Whether the user is selecting a route/plan (such as B, press B, plan B, plan B, press plan B to advance).

    LLM In the demand exploration/confirmation stage, A/B routes may be proposed for users to choose.
    The user s response (e.g. "B", "Advance according to plan B", "choose B") Should be considered confirmed to advance.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    normalized = re.sub(r"\s+", "", t)
    # single letter A/B/C/D
    if normalized in {"a", "b", "c", "d"}:
        return True
    # letters+Plan/Plan+Letter / Press letter / Select letter
    for letter in ("a", "b", "c", "d"):
        if (
            f"{letter}Plan" in normalized
            or f"Plan{letter}" in normalized
            or f"press{letter}" in normalized
            or f"choose{letter}" in normalized
            or f"Choose{letter}" in normalized
            or f"route{letter}" in normalized
            or f"{letter}route" in normalized
        ):
            return True
    return False


def _is_revise(text: str) -> bool:
    """Whether the user indicates modification/adjustment/addition."""
    t = (text or "").strip().lower()
    if not t:
        return False
    revise_keywords = (
        "plus", "Change", "Change to", "Don t", "Forget it", "Start over", "Change another one",
        "supplement", "Add dimension", "Also add", "Add more", "Also includes", "Modify",
        "adjust", "add one", "remove", "change direction", "No need", "Don t want to",
        "Change it", "can it", "Can you add", "add one more", "More",
    )
    return any(kw in t for kw in revise_keywords)


def _is_cancel(text: str) -> bool:
    """Whether the user indicated to cancel/restart."""
    t = (text or "").strip().lower()
    if not t:
        return False
    cancel_words = ("Cancel", "Forget it", "No more", "Start over", "All over again")
    return any(t == w or t.startswith(w) for w in cancel_words)


# ──────────────────────────────────────────────────────────────
# Solution selection analysis
# ──────────────────────────────────────────────────────────────

def _resolve_plan_selection(
    pending_options: list, text: str
) -> tuple[str, str]:
    """Parse plan choices from user responses.

    Return (selected_plan_id, reason). 
    """
    t = (text or "").strip().lower()
    normalized = re.sub(r"\s+", "", t)
    if not pending_options:
        return "", "no_options"

    # Match alphabetically/numericly
    index_map = {"a": 1, "b": 2, "c": 3, "d": 4}
    selected_index = 0
    for letter, idx in index_map.items():
        if (
            f"Plan{letter}" in normalized      # Plan b
            or f"{letter}Plan" in normalized    # b Plan
            or f"choose{letter}" in normalized      # choose b
            or f"Choose{letter}" in normalized    # Choose b
            or f"press{letter}" in normalized      # press b
            or f"route{letter}" in normalized    # route b
            or f"{letter}route" in normalized    # b route
            or normalized == letter             # b
        ):
            selected_index = idx
            break

    if not selected_index:
        if "first one" in normalized or "1st" in normalized or normalized in {"1", "Plan 1", "Option 1"}:
            selected_index = 1
        elif "second" in normalized or "2nd" in normalized or normalized in {"2", "Plan 2", "Option 2"}:
            selected_index = 2
        elif "third" in normalized or "3rd" in normalized or normalized in {"3", "Plan 3", "Option three"}:
            selected_index = 3

    if selected_index:
        for opt in pending_options:
            if int(opt.get("index") or 0) == selected_index:
                return str(opt.get("id") or "").strip(), f"matched_index_{selected_index}"

    # Recommended solution/Default
    recommend_keywords = ("Recommended", "click this", "OK", "Confirm", "OK", "OK", "Start generating", "That s it")
    if any(kw in normalized for kw in recommend_keywords):
        for opt in pending_options:
            if opt.get("recommended"):
                return str(opt.get("id") or "").strip(), "recommended"
        if pending_options:
            return str(pending_options[0].get("id") or "").strip(), "default_first"

    return "", "no_match"


def _detect_intent_change(text: str) -> bool:
    """Whether the user indicates that he or she wants to change needs/directions at any stage."""
    t = (text or "").strip().lower()
    if not t:
        return False
    keywords = (
        "plus", "Change", "Change to", "Don t", "Forget it", "Start over", "Change another one",
        "supplement", "Add dimension", "Also add", "Add more", "Also includes",
    )
    return any(kw in t for kw in keywords)


# ──────────────────────────────────────────────────────────────
# conditional edge routing function
# ──────────────────────────────────────────────────────────────

def _log_route(func_name: str, state: "AgentBuilderState", result: str):
    """Unified routing log."""
    logger.info(
        "[Route] %s → %s (node=%s stage=%s pending=%d msg=%.60s)",
        func_name,
        result,
        state.get("current_node", "?"),
        state.get("stage", "?"),
        len(state.get("pending_options", [])),
        (state.get("user_message", "") or "")[:60],
    )


def route_start(state: "AgentBuilderState") -> str:
    """START Routing: Determine whether a new session or recovery from the wait node is based on current_node.

    When recovering from the wait node, first route to the classify_intent node,
    Let LLM determine the user s intention before routing to the next step.
    """
    node = state.get("current_node", "")

    if not node or node == "START":
        result = "requirement_intake"
        _log_route("route_start", state, result)
        return result

    # Version conflicts are waiting for user decision-making: the user will directly return to build_or_ready to rebuild after replying.
    if state.get("build_status") == "pending_user_decision":
        logger.info(
            "[RouteStart][Debug] pending_user_decision detected | current_node=%s | decision_ctx_keys=%s | build_status=%s",
            node,
            list(state.get("decision_context", {}).keys()) if state.get("decision_context") else [],
            state.get("build_status"),
        )
        result = "build_or_ready"
        _log_route("route_start", state, result)
        return result

    # The published version is waiting for the user's decision: after the user replies, classify_intent determines whether to create a new version or cancel it.
    if state.get("build_status") == "pending_iteration_decision":
        logger.info(
            "[RouteStart][Debug] pending_iteration_decision detected | current_node=%s | user_message=%s",
            node,
            (state.get("user_message", "") or "")[:100],
        )
        result = "classify_intent"
        _log_route("route_start", state, result)
        return result

    # Resume from wait / evaluate / error node → Go first LLM intent classification
    # build_or_ready Not in the list: When in the pending_user_decision state, the user replies directly back to build_or_ready to rebuild
    if node in (
        "wait_intake_confirmation",
        "wait_requirement_confirmation",
        "wait_plan_selection",
        "wait_test_request",
        "evaluate_or_publish",
        "wait_evaluation",
        "error_recovery",
    ):
        result = "classify_intent"
        _log_route("route_start", state, result)
        return result

    # Other nodes: continue directly
    result = node
    _log_route("route_start", state, result)
    return result


def route_after_classify(state: "AgentBuilderState") -> str:
    """LLM Routing after intent classification.

    read state["user_intent"], state["intent_confidence"], state["current_node"], 
    Decide which node to go to next.

    Rules:
      1. confidence < 0.7 → Return to the current wait node and trigger clarification_needed
      2. intent = "new_agent" → Stay in the current wait node (prompts the user to create it manually)
      3. Other by intention + Node combination routing
    """
    current_node = state.get("current_node", "")
    intent = state.get("user_intent", "explore_more")
    confidence = state.get("intent_confidence", 0.0)
    msg = state.get("user_message", "")

    # Clear clarification mark by default
    state["clarification_needed"] = False

    logger.info(
        "[Route][AfterClassify] current_node=%s intent=%s confidence=%.2f msg=%.60s",
        current_node, intent, confidence, msg,
    )

    # ── cancel end at any stage ──
    if intent == "cancel":
        result = "end"
        _log_route("route_after_classify", state, result)
        return result

    # ── new_agent: Prompts the user to create manually and stay in the current wait node ──
    if intent == "new_agent":
        result = current_node if current_node.startswith("wait_") or current_node in ("evaluate_or_publish", "error_recovery") else "wait_evaluation"
        _log_route("route_after_classify", state, result)
        return result

    # ── rerun_gap: Users request to rerun the current Agent Workshop capability gap analysis ──
    if intent == "rerun_gap":
        state["stage"] = "capability_check"
        state["gap_report"] = {}
        state["candidate_plans"] = []
        state["pending_options"] = []
        state["selected_plan_id"] = ""
        result = "gap_analysis"
        _log_route("route_after_classify", state, result)
        return result

    # ── regenerate_plan: User requests to regenerate candidate solutions based on current gap ──
    if intent == "regenerate_plan":
        state["stage"] = "plan_selection_pending"
        state["candidate_plans"] = []
        state["pending_options"] = []
        state["selected_plan_id"] = ""
        result = "plan_generation"
        _log_route("route_after_classify", state, result)
        return result

    # ── Low confidence: LLM is unclear about the user's meaning and returns to the current wait node to trigger clarification ──
    if confidence < 0.7:
        wait_node = current_node
        # Make sure you are returning to a valid wait node
        if not (wait_node.startswith("wait_") or wait_node in ("evaluate_or_publish", "error_recovery")):
            wait_node = "wait_evaluation"  # Keep everything in mind
        state["clarification_needed"] = True
        logger.info(
            "[Route][LowConfidence] confidence=%.2f → stay_on=%s clarify=1",
            confidence, wait_node,
        )
        _log_route("route_after_classify", state, wait_node)
        return wait_node

    # ── wait_intake_confirmation: Requirements exploration stage ──
    if current_node == "wait_intake_confirmation":
        if intent in ("confirmed", "select_option"):
            # confirmed / select_option All are regarded as confirmation and advancement
            result = "requirement_confirmation"
        elif intent == "revise":
            result = "requirement_intake"
        else:  # explore_more
            result = "wait_intake_confirmation"
            state["clarification_needed"] = True

    # ── wait_requirement_confirmation: Requirements confirmation stage ──
    elif current_node == "wait_requirement_confirmation":
        if intent in ("confirmed", "select_option"):
            result = "gap_analysis"
        elif intent == "revise":
            result = "requirement_confirmation"
        else:  # explore_more
            result = "wait_requirement_confirmation"
            state["clarification_needed"] = True

    # ── wait_plan_selection: Solution selection stage ──
    elif current_node == "wait_plan_selection":
        if intent == "select_option" or intent == "create_skill":
            # create_skill: If users want to complete missing skills, they should give priority to solutions that include the development of new skills.
            # Priority is given to LLM analysis selected_index / selected_id
            selected_id = _resolve_selected_from_llm(state)
            if selected_id:
                state["selected_plan_id"] = selected_id
                result = "generate_candidate_agent"
            else:
                # LLM I haven't analyzed it yet, so I'll use the rules to find out.
                selected_id, reason = _resolve_plan_selection(
                    state.get("pending_options", []), msg
                )
                if selected_id:
                    state["selected_plan_id"] = selected_id
                    result = "generate_candidate_agent"
                elif intent == "create_skill":
                    # 🔑 create_skill The bottom line: find what's included"complete"/"develop"/"skill"keyword plan
                    selected_id = _find_skill_creation_plan(state.get("pending_options", []))
                    if selected_id:
                        state["selected_plan_id"] = selected_id
                        result = "generate_candidate_agent"
                    else:
                        # If there is no plan that includes skill development, use the recommended plan.
                        state["selected_plan_id"] = state.get("recommended_plan_id", "")
                        if not state["selected_plan_id"] and state.get("pending_options"):
                            state["selected_plan_id"] = state["pending_options"][0].get("id", "")
                        result = "generate_candidate_agent" if state.get("selected_plan_id") else "wait_plan_selection"
                        if not state.get("selected_plan_id"):
                            state["clarification_needed"] = True
                else:
                    result = "wait_plan_selection"
                    state["clarification_needed"] = True
        elif intent == "confirmed":
            # Users say"Confirm"/"Recommended"→ Use recommended solutions
            state["selected_plan_id"] = state.get("recommended_plan_id", "")
            if not state["selected_plan_id"] and state.get("pending_options"):
                state["selected_plan_id"] = state["pending_options"][0].get("id", "")
            if state["selected_plan_id"]:
                result = "generate_candidate_agent"
            else:
                result = "wait_plan_selection"
                state["clarification_needed"] = True
        elif intent == "revise":
            result = "requirement_intake"
        else:  # explore_more
            result = "wait_plan_selection"
            state["clarification_needed"] = True

    # ── wait_test_request: Waiting for test target ──
    elif current_node == "wait_test_request":
        if state.get("build_status") == "pending_iteration_decision":
            # Published version decision point: User confirms creation of new version → return to generate_candidate_agent
            #  (The node entrance will automatically iterate to create a new session, and then continue to generate using the previously selected solution)
            if intent in ("confirmed", "select_option"):
                result = "generate_candidate_agent"
            elif intent == "cancel":
                result = "end"
                state["stage"] = "cancelled"
            else:
                result = "wait_test_request"
                state["clarification_needed"] = True
        elif state.get("test_symbol"):
            result = "real_data_test"
        elif intent == "create_skill":
            # If the user wants to create the missing skill, stop at the current node and the node will output a prompt.
            result = "wait_test_request"
            state["skill_creation_requested"] = True
        elif intent == "cancel":
            result = "end"
        else:
            result = "wait_test_request"
            state["clarification_needed"] = True

    # ── Evaluation phase (waiting for user decision-making) ──
    elif current_node == "wait_evaluation":
        if intent in ("cancel",):
            result = "end"
            state["stage"] = "cancelled"
        elif intent in ("confirmed", "select_option"):
            # User confirms release → Enter the publishing process
            result = "evaluate_or_publish"
        elif intent == "create_skill":
            # The user wants to create the missing skill
            result = "wait_evaluation"
            state["skill_creation_requested"] = True
        elif intent in ("revise",):
            result = "iterate_agent_version" if state.get("version_id") else "requirement_intake"
        elif intent == "retry":
            # User requests retest: If the test target has been parsed in this round, enter the real data test directly; otherwise, wait for the target first.
            result = "real_data_test" if state.get("test_symbol") else "wait_test_request"
        else:
            result = "wait_evaluation"
            state["clarification_needed"] = True

    # ── Evaluation phase (under release) ──
    elif current_node == "evaluate_or_publish":
        if intent in ("confirmed", "select_option"):
            # User confirms release/continues evaluation → Enter the release evaluation node.
            result = "evaluate_or_publish"
        elif intent == "retry":
            # The user wants to retest; if there is a target, test it directly, otherwise wait for the target first.
            result = "real_data_test" if state.get("test_symbol") else "wait_test_request"
        elif intent == "revise":
            # User wants to upgrade/modify the evaluated version → Create a draft for the next iteration
            result = "iterate_agent_version" if state.get("version_id") else "requirement_intake"
        elif intent == "cancel":
            result = "end"
        else:
            # explore_more: Users ask questions, still in the evaluation stage
            result = "evaluate_or_publish"
            state["clarification_needed"] = True

    # ── error_recovery: error recovery phase ──
    elif current_node == "error_recovery":
        if intent in ("confirmed", "retry", "select_option"):
            # The user wants to try again (e.g."Try again""do it again""retry") 
            result = _resolve_error_retry_target(state)
        elif intent == "revise":
            # User wants to modify → Back to demand exploration
            result = "requirement_intake"
        elif intent == "cancel":
            result = "end"
        else:
            # explore_more: Users are still asking questions
            result = "error_recovery"
            state["clarification_needed"] = True

    else:
        # Unknown nodes: Safely reach END to avoid incorrect routing to action nodes
        logger.warning(
            "[Route][AfterClassify] unexpected current_node=%s, intent=%s → Get to the bottom of everything end",
            current_node, intent,
        )
        result = "end"

    _log_route("route_after_classify", state, result)
    return result


def _resolve_selected_from_llm(state: "AgentBuilderState") -> str:
    """Parse the selected scenario ID from the LLM classification results."""
    pending = state.get("pending_options", []) or []
    # priority selected_index
    sel_idx = state.get("user_selected_index")
    if sel_idx:
        for opt in pending:
            if int(opt.get("index") or 0) == int(sel_idx):
                return str(opt.get("id") or "").strip()
    # Secondly use selected_id
    sel_id = state.get("user_selected_id", "")
    if sel_id:
        for opt in pending:
            if str(opt.get("id") or "") == str(sel_id):
                return str(opt.get("id") or "").strip()
    return ""


def _find_skill_creation_plan(options: list) -> str:
    """Find the project ID containing skill/tool development from the list of projects."""
    skill_keywords = ["complete", "develop", "skill", "Create.*Tools", "New.*Tools", "Quantitative scoring"]
    for opt in options:
        name = str(opt.get("name", opt.get("id", ""))).lower()
        desc = str(opt.get("description", opt.get("summary", ""))).lower()
        text = f"{name} {desc}"
        for kw in skill_keywords:
            if re.search(kw, text, re.IGNORECASE):
                return str(opt.get("id") or "").strip()
    # Not found, return to recommended plan
    for opt in options:
        if opt.get("recommended"):
            return str(opt.get("id") or "").strip()
    return ""


def route_after_intake(state: "AgentBuilderState") -> str:
    """Routing after demand exploration."""
    if _is_cancel(state.get("user_message", "")):
        result = "end"
    elif state.get("spec_id") and (
        _is_confirm(state.get("user_message", "")) or _is_route_choice(state.get("user_message", ""))
    ):
        result = "requirement_confirmation"
    else:
        result = "wait_intake_confirmation"
    _log_route("route_after_intake", state, result)
    return result


def route_after_gap_analysis(state: "AgentBuilderState") -> str:
    """gap Analyzed routing."""
    result = "plan_generation"
    _log_route("route_after_gap_analysis", state, result)
    return result


def route_after_plan_generation(state: "AgentBuilderState") -> str:
    """Routing after plan generation."""
    result = "wait_plan_selection"
    _log_route("route_after_plan_generation", state, result)
    return result


def route_wait_plan_selection(state: "AgentBuilderState") -> str:
    """Wait for the user to select a plan."""
    msg = state.get("user_message", "")
    if _is_cancel(msg):
        result = "end"
    elif _detect_intent_change(msg):
        result = "requirement_intake"
    else:
        selected_id, reason = _resolve_plan_selection(
            state.get("pending_options", []), msg
        )
        logger.info(
            "[PlanSelection][Condition] result=%s, reason=%s, pending_options=%d",
            selected_id, reason, len(state.get("pending_options", [])),
        )
        if selected_id:
            state["selected_plan_id"] = selected_id
            result = "generate_candidate_agent"
        elif _is_confirm(msg):
            state["selected_plan_id"] = state.get("recommended_plan_id", "")
            if not state["selected_plan_id"] and state.get("pending_options"):
                state["selected_plan_id"] = state["pending_options"][0].get("id", "")
            result = "generate_candidate_agent" if state["selected_plan_id"] else "wait_plan_selection"
        else:
            result = "wait_plan_selection"
    _log_route("route_wait_plan_selection", state, result)
    return result


def route_after_generate(state: "AgentBuilderState") -> str:
    """Route after generating Agent."""
    if state.get("build_status") == "pending_iteration_decision":
        # Released version is intercepted by phase_guard → Present decision options to users
        result = "wait_test_request"
    elif state.get("errors"):
        result = "error_recovery"
    elif state.get("selected_plan_id") == "quick":
        result = "wait_test_request"
    elif state.get("build_status") == "built":
        result = "wait_test_request"
    elif state.get("generated_agent"):
        result = "build_or_ready"
    else:
        result = "error_recovery"
    _log_route("route_after_generate", state, result)
    return result


def route_after_build(state: "AgentBuilderState") -> str:
    """The route after construction."""
    build_status = state.get("build_status", "")
    if build_status in ("built", "skipped", "pending_user_decision"):
        result = "wait_test_request"
    elif build_status == "skipped_no_session":
        # Unable to build version without workshop_session_id → Enter error recovery
        result = "error_recovery"
    elif state.get("errors"):
        result = "error_recovery"
    else:
        result = "wait_test_request" if build_status == "built" else "error_recovery"
    _log_route("route_after_build", state, result)
    return result


def route_after_test(state: "AgentBuilderState") -> str:
    """Route after test: test completed → Waiting for user decision (publish/retest/modify/cancel).

    No more automatic entry into the publishing process, giving users a clear opportunity to view test results
    and decide what to do next.
    """
    result = "wait_evaluation" if not state.get("errors") else "error_recovery"
    _log_route("route_after_test", state, result)
    return result


def _resolve_error_retry_target(state: "AgentBuilderState") -> str:
    """Extract the error node from errors and return the retry target.

    Note: here is the state["errors"] Modifications will not be persisted to the node
     (LangGraph The state modification of the conditional function is not persisted).
    The actual error cleaning is done within the classify_intent node.
    """
    errors = state.get("errors", []) or []
    failed_node = ""
    for e in reversed(errors):
        if isinstance(e, dict):
            failed_node = str(e.get("node") or "").strip()
            if failed_node:
                break

    if failed_node:
        # Clear errors for this node
        state["errors"] = [
            e for e in errors
            if not (isinstance(e, dict) and e.get("node") == failed_node)
        ]
        return failed_node

    return "wait_test_request"