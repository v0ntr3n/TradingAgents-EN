"""
Agent Builder LangGraph Workflow definition

A directed graph that defines the Agent Builder creation process.

Principle:
- The node is the construction phase (requirements exploration, confirmation, capability inventory, solution, generation, testing)
- The edges are conditional branches (user confirms, modifies, cancels, chooses plan A/B/C)
- State is persisted by MongoDB checkpoints
- LLM Only responsible for communication and tool invocation within the node
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from langgraph.graph import StateGraph, START, END

from core.embedded_nanobot.workflows.agent_builder_state import AgentBuilderState
from core.embedded_nanobot.workflows import (
    agent_builder_nodes as nodes,
    agent_builder_conditions as conditions,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Graph construction
# ──────────────────────────────────────────────────────────────

def build_agent_builder_graph() -> StateGraph:
    """Build an Agent Builder workflow diagram.

    Returns a compiled StateGraph, which can be called directly ainvoke(). 
    """
    graph = StateGraph(AgentBuilderState)

    # ── Register node ──
    # LLM Intent classification (run this first when recovering from the wait node)
    graph.add_node("classify_intent", _make_node_wrapper(nodes.node_classify_user_intent))

    # demand stage
    graph.add_node("requirement_intake", _make_node_wrapper(nodes.node_requirement_intake))
    graph.add_node("wait_intake_confirmation", _make_node_wrapper(nodes.node_wait_intake_confirmation))
    graph.add_node("requirement_confirmation", _make_node_wrapper(nodes.node_requirement_confirmation))
    graph.add_node("wait_requirement_confirmation", _make_node_wrapper(nodes.node_wait_requirement_confirmation))

    # gap analysis stage
    graph.add_node("gap_analysis", _make_node_wrapper(nodes.node_gap_analysis))

    # planning stage
    graph.add_node("plan_generation", _make_node_wrapper(nodes.node_plan_generation))
    graph.add_node("wait_plan_selection", _make_node_wrapper(nodes.node_wait_plan_selection))

    # generation phase
    graph.add_node("generate_candidate_agent", _make_node_wrapper(nodes.node_generate_candidate_agent))
    graph.add_node("build_or_ready", _make_node_wrapper(nodes.node_build_or_ready))

    # testing phase
    graph.add_node("wait_test_request", _make_node_wrapper(nodes.node_wait_test_request))
    graph.add_node("real_data_test", _make_node_wrapper(nodes.node_real_data_test))

    # Evaluate/Release (wait for user decision after testing)
    graph.add_node("wait_evaluation", _make_node_wrapper(nodes.node_wait_evaluation))
    graph.add_node("evaluate_or_publish", _make_node_wrapper(nodes.node_evaluate_or_publish))
    graph.add_node("iterate_agent_version", _make_node_wrapper(nodes.node_iterate_agent_version))

    # error recovery
    graph.add_node("error_recovery", _make_node_wrapper(nodes.node_error_recovery))

    # ── Register side ──

    # START → Determine whether it is a new session or recovery based on current_node
    graph.add_conditional_edges(
        START,
        conditions.route_start,
        {
            "classify_intent": "classify_intent",
            "requirement_intake": "requirement_intake",
            "requirement_confirmation": "requirement_confirmation",
            "wait_intake_confirmation": "wait_intake_confirmation",
            "wait_requirement_confirmation": "wait_requirement_confirmation",
            "gap_analysis": "gap_analysis",
            "plan_generation": "plan_generation",
            "wait_plan_selection": "wait_plan_selection",
            "generate_candidate_agent": "generate_candidate_agent",
            "build_or_ready": "build_or_ready",
            "wait_test_request": "wait_test_request",
            "real_data_test": "real_data_test",
            "evaluate_or_publish": "evaluate_or_publish",
            "iterate_agent_version": "iterate_agent_version",
            "wait_evaluation": "wait_evaluation",
            "error_recovery": "error_recovery",
            "end": END,
        },
    )

    # classify_intent → Routing results based on LLM intent classification
    graph.add_conditional_edges(
        "classify_intent",
        conditions.route_after_classify,
        {
            "requirement_intake": "requirement_intake",
            "requirement_confirmation": "requirement_confirmation",
            "wait_intake_confirmation": "wait_intake_confirmation",
            "wait_requirement_confirmation": "wait_requirement_confirmation",
            "gap_analysis": "gap_analysis",
            "plan_generation": "plan_generation",
            "generate_candidate_agent": "generate_candidate_agent",
            "wait_plan_selection": "wait_plan_selection",
            "real_data_test": "real_data_test",
            "wait_test_request": "wait_test_request",
            "evaluate_or_publish": "evaluate_or_publish",
            "iterate_agent_version": "iterate_agent_version",
            "wait_evaluation": "wait_evaluation",
            "error_recovery": "error_recovery",
            "build_or_ready": "build_or_ready",
            "end": END,
        },
    )

    # After requirement exploration
    graph.add_conditional_edges(
        "requirement_intake",
        conditions.route_after_intake,
        {
            "requirement_confirmation": "requirement_confirmation",
            "wait_intake_confirmation": "wait_intake_confirmation",
            "end": END,
        },
    )

    # Waiting for confirmation of demand → terminal
    graph.add_edge("wait_intake_confirmation", END)

    # After confirmation of demand
    graph.add_edge("requirement_confirmation", "wait_requirement_confirmation")

    # Waiting for confirmation of demand boundaries → terminal
    graph.add_edge("wait_requirement_confirmation", END)

    # gap analysis → Solution generation
    graph.add_edge("gap_analysis", "plan_generation")

    # Solution generation → Waiting for selection
    graph.add_edge("plan_generation", "wait_plan_selection")

    # Waiting for plan selection → terminal
    graph.add_edge("wait_plan_selection", END)

    # After generating Agent
    graph.add_conditional_edges(
        "generate_candidate_agent",
        conditions.route_after_generate,
        {
            "wait_test_request": "wait_test_request",
            "build_or_ready": "build_or_ready",
            "error_recovery": "error_recovery",
        },
    )

    # After building
    graph.add_conditional_edges(
        "build_or_ready",
        conditions.route_after_build,
        {
            "wait_test_request": "wait_test_request",
            "error_recovery": "error_recovery",
        },
    )

    # Waiting for test request → terminal
    graph.add_edge("wait_test_request", END)

    # After test → Wait for user decision (no longer publish automatically)
    graph.add_conditional_edges(
        "real_data_test",
        conditions.route_after_test,
        {
            "wait_evaluation": "wait_evaluation",
            "error_recovery": "error_recovery",
        },
    )

    # Waiting for evaluation decision → terminal
    graph.add_edge("wait_evaluation", END)

    # After version iteration is created → Terminal, waiting for the user to continue to supplement/confirm the upgrade requirements
    graph.add_edge("iterate_agent_version", END)

    # After evaluation/release → terminal
    graph.add_edge("evaluate_or_publish", END)

    # error recovery → terminal
    graph.add_edge("error_recovery", END)

    return graph.compile()


# ──────────────────────────────────────────────────────────────
# node wrapper
# ──────────────────────────────────────────────────────────────

def _make_node_wrapper(node_func):
    """Wrap node functions as LangGraph nodes.

    Dynamically inject parameters based on node function signature.
    - action node:inject tool_registry, llm_client, event_callback, on_stream
    - wait node:inject only event_callback, on_stream
    """
    import inspect
    sig = inspect.signature(node_func)
    param_names = set(sig.parameters.keys())
    node_name = node_func.__name__

    async def wrapper(state: AgentBuilderState) -> AgentBuilderState:
        logger.info("[Node][Enter] %s stage=%s spec=%s", node_name, state.get("stage", ""), state.get("spec_id", ""))

        kwargs = {"state": state}

        if "event_callback" in param_names:
            kwargs["event_callback"] = state.get("_event_callback")
        if "on_stream" in param_names:
            kwargs["on_stream"] = state.get("_on_stream")
        if "tool_registry" in param_names:
            kwargs["tool_registry"] = state.get("_tool_registry")
        if "llm_client" in param_names:
            kwargs["llm_client"] = state.get("_llm_client")

        result = await node_func(**kwargs)

        logger.info(
            "[Node][Exit] %s → stage=%s awaiting=%s pending=%s",
            node_name,
            result.get("stage", ""),
            result.get("awaiting_user", False),
            result.get("pending_question", "")[:80],
        )
        return result

    return wrapper


# ──────────────────────────────────────────────────────────────
# graph executor
# ──────────────────────────────────────────────────────────────

async def execute_graph(
    graph: StateGraph,
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
    max_steps: int = 10,
) -> AgentBuilderState:
    """Execute the Agent Builder graph.

    Inject runtime dependencies into state and then execute the graph.
    encounter wait_* Pause when the node is running and save the checkpoint.

    Return the final state.
    """
    # Inject runtime dependencies
    state["_tool_registry"] = tool_registry
    state["_llm_client"] = llm_client
    state["_event_callback"] = event_callback
    state["_on_stream"] = on_stream

    logger.info(
        "[Graph][Invoke] node=%s stage=%s awaiting=%s",
        state.get("current_node", "START"),
        state.get("stage", "?"),
        state.get("awaiting_user", False),
    )

    # Figure execution:START → route_start → ... → wait_* → END
    # No need to loop, the graph is completed in one go
    result = await graph.ainvoke(
        state,
        config={"recursion_limit": 50},
    )

    logger.info(
        "[Graph][Done] node=%s stage=%s awaiting=%s",
        result.get("current_node", "?"),
        result.get("stage", "?"),
        result.get("awaiting_user", False),
    )

    return result