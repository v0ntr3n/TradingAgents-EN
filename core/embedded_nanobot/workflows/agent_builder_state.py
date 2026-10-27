"""
Agent Builder Workflow state model

Defines the state structure of the LangGraph Agent Builder graph.
The state is the only source of truth for the graph and structured fields cannot be determined directly by LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, TypedDict


class AgentBuilderState(TypedDict, total=False):
    """Agent Builder Workflow status.

    Agreement:
    - stage / current_node is the only stage fact source
    - pending_options Can only be written by plan_generation nodes
    - selected_plan_id Can only be written by the wait_plan_selection conditional function
    - gap_report Can only be written by gap_analysis
    - generated_agent Can only be written by generate_candidate_agent
    """

    # ── session id ──
    thread_id: str
    user_id: str
    user_message: str
    channel: str
    chat_id: str

    # ── graph status ──
    current_node: str
    stage: str
    awaiting_user: bool
    pending_question: str
    clarification_needed: bool  # When the intent cannot be recognized, let the wait node output a clarifying prompt instead of repeating the previous round of content.
    skill_creation_requested: bool  # Set when the user requests to complete the missing skill and let the wait node output the skill creation prompt.

    # ── LLM Intent classification (written by classify_intent node) ──
    user_intent: str  # confirmed / revise / select_option / explore_more / cancel / new_agent / retry
    user_selected_index: int  # LLM The parsed selected solution serial number
    user_selected_id: str  # LLM Analyzed options ID
    intent_confidence: float  # LLM Intent classification confidence (0.0-1.0)
    intent_reason: str  # LLM Intention classification reasoning explanation

    # ── demand stage ──
    spec_id: str
    spec_name: str
    requirement_summary: str
    confirmation_brief: dict
    original_user_request: str
    proposed_plan: dict

    # ── Capability inventory ──
    capability_inventory: dict
    gap_report: dict

    # ── planning stage ──
    candidate_plans: list
    pending_options: list
    recommended_plan_id: str
    selected_plan_id: str
    acknowledged_gaps: list

    # ── generation phase ──
    generated_agent: dict
    workshop_session_id: str
    version_id: str
    build_status: str
    decision_context: dict  # Version conflict/iteration decision context (pending_user_decision/pending_iteration_decision)

    # ── testing phase ──
    test_symbol: str
    test_result: dict
    official_acceptance_decision: str

    # ── error recovery ──
    errors: list

    # ── dialogue memory ──
    conversation_summary: str
    tool_events: list
    final_response: str
    message_history: list  # [{role, content}] Recent N rounds of conversations for LLM intent classification

    # ── Runtime injection (not persistent) ──
    _tool_registry: Any
    _llm_client: Any  # UnifiedLLMClient instance (replacing the old _provider + _model) 
    _event_callback: Any
    _on_stream: Any


def new_agent_builder_state(
    thread_id: str = "",
    user_id: str = "",
    user_message: str = "",
    channel: str = "",
    chat_id: str = "",
) -> AgentBuilderState:
    """Create initial state."""
    return AgentBuilderState(
        thread_id=thread_id,
        user_id=user_id,
        user_message=user_message,
        channel=channel,
        chat_id=chat_id,
        current_node="START",
        stage="",
        awaiting_user=False,
        pending_question="",
        clarification_needed=False,
        skill_creation_requested=False,
        spec_id="",
        spec_name="",
        requirement_summary="",
        confirmation_brief={},
        capability_inventory={},
        gap_report={},
        candidate_plans=[],
        pending_options=[],
        recommended_plan_id="",
        selected_plan_id="",
        acknowledged_gaps=[],
        generated_agent={},
        workshop_session_id="",
        version_id="",
        build_status="",
        decision_context={},
        test_symbol="",
        test_result={},
        official_acceptance_decision="",
        errors=[],
        conversation_summary="",
        tool_events=[],
        final_response="",
        message_history=[],
    )