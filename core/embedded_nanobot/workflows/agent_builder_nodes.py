"""
Agent Builder Workflow node implementation

Each node is responsible for:
  1. Communicate with users via LLM
  2. Call the specified required tools
  3. Write tool results to state
  4. update current_node / stage

Note:
  - Nodes do not decide where to go next (determined by conditional edges)
  - The node does not determine which tools are available (it is determined by the graph definition)
  - LLM Only responsible for communication and calling tools according to node requirements
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.embedded_nanobot.workflows.agent_builder_state import AgentBuilderState

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# In-node LLM call assistance (based on UnifiedLLMClient, standard Function Calling)
# ──────────────────────────────────────────────────────────────

def _convert_messages(messages: List[Dict[str, Any]]) -> List[Any]:
    """Convert a message in dict form to the Message Pydantic object expected by UnifiedLLMClient.

    Extracted from TradingAgentsLLMProvider._convert_messages, retaining tool_calls conversion.
    """
    from core.llm.models import Message, MessageRole, ToolCall as CoreToolCall

    converted: List[Message] = []
    for msg in messages:
        role = MessageRole(msg.get("role", "user"))
        tool_calls = None
        raw_tool_calls = msg.get("tool_calls") or []
        if raw_tool_calls:
            tool_calls = []
            for item in raw_tool_calls:
                if isinstance(item, dict):
                    function = item.get("function") or {}
                    arguments = function.get("arguments") or {}
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except Exception:
                            arguments = {}
                    tool_calls.append(CoreToolCall(
                        id=str(item.get("id") or ""),
                        name=str(function.get("name") or ""),
                        arguments=arguments if isinstance(arguments, dict) else {},
                    ))
        converted.append(Message(
            role=role,
            content=msg.get("content") if isinstance(msg.get("content"), str) else None,
            name=msg.get("name"),
            tool_call_id=msg.get("tool_call_id"),
            tool_calls=tool_calls,
        ))
    return converted


def _to_openai_tool_schema(tool: Any) -> Optional[Dict[str, Any]]:
    """Convert Nanobot Tool to OpenAI Function Calling format.

    Nanobot Tool.to_schema() Return: {"name": ..., "description": ..., "parameters": ...}
    OpenAI Expectation: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    if tool is None:
        return None
    try:
        schema = tool.to_schema()
    except Exception:
        return None
    if not isinstance(schema, dict) or not schema.get("name"):
        return None
    return {
        "type": "function",
        "function": {
            "name": schema.get("name", ""),
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
        },
    }


def _collect_tool_schemas(
    tool_registry: Any,
    required_tool_name: Any,
    include_inspect_tools: bool = False,
) -> List[Dict[str, Any]]:
    """Collect the tool schema (OpenAI format) to be passed to LLM."""
    schemas: List[Dict[str, Any]] = []
    if not tool_registry:
        return schemas

    names: List[str] = []
    if isinstance(required_tool_name, list):
        names = [n for n in required_tool_name if n]
    elif required_tool_name:
        names = [required_tool_name]

    for name in names:
        tool = tool_registry.get(name)
        schema = _to_openai_tool_schema(tool)
        if schema:
            schemas.append(schema)

    if include_inspect_tools:
        for inspect_name in ("inspect_agent_workshop_assets", "search_project_capabilities"):
            if inspect_name in names:
                continue
            tool = tool_registry.get(inspect_name)
            schema = _to_openai_tool_schema(tool)
            if schema:
                schemas.append(schema)

    return schemas


async def _stream_chunked(text: str, on_stream: Optional[Callable], chunk_size: int = 40, delay: float = 0.012) -> None:
    """Stream the complete text in chunks (simulating streaming effect)."""
    if not text or not on_stream:
        return
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        try:
            await on_stream(chunk)
        except Exception:
            pass
        if delay > 0:
            await asyncio.sleep(delay)


async def _run_node_tool_first(
    state: AgentBuilderState,
    system_prompt: str,
    tool_registry: Any,
    llm_client: Any,
    required_tool_name: str,
    include_inspect_tools: bool = False,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Tool first mode (string mode): code directly adjusts the tool → LLM Summary → Chunked streaming.

    By not letting LLM decide which tool to tune, XML leaks are essentially eliminated.
    Suitable for scenarios where a node knows that a specific tool must be called (7 nodes use this mode).
    """
    # 1. Build tool parameters (inherit the complete logic of _build_force_call_params)
    tool_params = _build_force_call_params(required_tool_name, state)

    # 2. Execution tool
    tool_events: List[Dict[str, Any]] = []
    tool_results: Dict[str, Any] = {}

    await _emit_event(event_callback, "tool", f"Execution:{required_tool_name}")
    try:
        result = await tool_registry.execute(required_tool_name, tool_params)
        result_str = str(result) if not isinstance(result, str) else result
        tool_results[required_tool_name] = result_str
        tool_events.append({"name": required_tool_name, "params": tool_params, "status": "ok"})
        await _emit_event(event_callback, "tool_done", f"Complete:{required_tool_name}")
        logger.info("[NodeToolFirst][Ok] %s len=%d", required_tool_name, len(result_str))
    except Exception as e:
        logger.error("[NodeToolFirst][Error] %s: %s", required_tool_name, e, exc_info=True)
        result_str = f"Error: {e}"
        tool_results[required_tool_name] = result_str
        tool_events.append({"name": required_tool_name, "params": tool_params, "status": "error", "error": str(e)})
        await _emit_event(event_callback, "tool_error", f"Failure:{required_tool_name}")

    # 3. LLM Summary (non-streaming achat → Push in chunks)
    await _emit_event(event_callback, "progress", "Analyzing results...")

    user_msg_content = state.get("user_message", "") or ""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg_content},
        {
            "role": "user",
            "content": (
                f"Tools {required_tool_name} The execution has been completed. The following is the result returned by the tool:\n\n"
                f"{result_str[:6000]}\n\n"
                "Please give a natural language reply based on the above tool results and the user s needs."
                "Don t output any tool call XML or JSON, just what is said to the user."
            ),
        },
    ]

    try:
        response = await llm_client.achat(
            _convert_messages(messages),
            temperature=0.3,
            auto_execute_tools=False,
        )
        final_text = getattr(response, "content", "") or ""
    except Exception as e:
        logger.error("[NodeToolFirst][LLMError] %s", e, exc_info=True)
        final_text = f"Sorry, there was a problem during processing:{e}"

    # 4. Chunked streaming
    await _stream_chunked(final_text, on_stream)

    return final_text, tool_events, tool_results


async def _run_node_llm_fc(
    state: AgentBuilderState,
    system_prompt: str,
    tool_registry: Any,
    llm_client: Any,
    required_tool_name: List[str],
    include_inspect_tools: bool = False,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """LLM Function Calling Mode (list mode): The standard FC protocol lets LLM decide which tool to call.

    Using OpenAI standard Function Calling, tool calls are returned via the API (not text),
    No XML leaks occur. Suitable for scenarios where nodes need to be selected from multiple tools (use this mode for 1 node).

    NOTE: The UnifiedLLMClient internal _tools dictionary needs to contain tool functions that LLM may call.
    """
    # 1. Collection tool schema (OpenAI format)
    tool_schemas = _collect_tool_schemas(tool_registry, required_tool_name, include_inspect_tools)
    if not tool_schemas:
        # No tools available, reduced to pure LLM calls
        return await _run_node_plain(state, system_prompt, llm_client, event_callback, on_stream)

    # 2. Inject tool functions into llm_client (UnifiedLLMClient executes tools through the _tools dictionary)
    tools_to_inject: Dict[str, Callable] = {}
    for name in required_tool_name:
        tool = tool_registry.get(name) if tool_registry else None
        if tool is None:
            continue
        # Prefer tool.func / tool.execute / tool.run (depends on Nanobot Tool implementation)
        func = None
        for attr in ("func", "execute", "run", "_func", "handler"):
            candidate = getattr(tool, attr, None)
            if callable(candidate):
                func = candidate
                break
        if func is None:
            # The next best thing: wrap one with tool_registry.execute callable
            async def _wrapped(_name=name, _registry=tool_registry):
                # Note: There is no way to receive parameters here, it is just a placeholder; the actual parameters are passed in by aexecute_tool_call
                raise RuntimeError(f"Tools {_name} Missing callable function handle, please check Tool implementation")
            func = _wrapped
        tools_to_inject[name] = func

    # Temporarily inject tools into llm_client (does not affect other requests because _tools is an instance-level dict)
    # Note:auto_execute_tools=True UnifiedLLMClient will use self._tools to execute the tool
    try:
        llm_client.inject_tools(tools_to_inject)
    except Exception as e:
        logger.warning("[NodeLLMFC][InjectTools] %s", e)

    # 3. LLM Deciding which tool to use (auto_execute_tools=True, Standard FC protocol)
    user_msg_content = state.get("user_message", "") or ""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg_content},
    ]

    tools_used: List[str] = []
    tool_events: List[Dict[str, Any]] = []
    tool_results: Dict[str, Any] = {}

    async def _progress(payload: Dict[str, Any]) -> None:
        event = payload.get("event", "")
        tool_name = payload.get("tool", "")
        if event == "tool_started" and tool_name:
            await _emit_event(event_callback, "tool", f"Execution:{tool_name}")
        elif event == "tool_completed" and tool_name:
            preview = payload.get("preview", "")
            tool_results[tool_name] = preview  # Just for the record, we will use registry.execute to re-obtain the complete results below.
            is_error = payload.get("is_error", False)
            status = "error" if is_error else "ok"
            tool_events.append({"name": tool_name, "params": payload.get("arguments", {}), "status": status})
            tools_used.append(tool_name)
            if is_error:
                await _emit_event(event_callback, "tool_error", f"Failure:{tool_name}")
            else:
                await _emit_event(event_callback, "tool_done", f"Complete:{tool_name}")

    await _emit_event(event_callback, "progress", "Analyzing requirements...")

    try:
        response = await llm_client.achat(
            _convert_messages(messages),
            tools=tool_schemas,
            auto_execute_tools=True,
            max_tool_rounds=3,
            tools_used=tools_used,
            dry_run=False,
            progress_callback=_progress,
            temperature=0.3,
        )
        final_text = getattr(response, "content", "") or ""
    except Exception as e:
        logger.error("[NodeLLMFC][LLMError] %s", e, exc_info=True)
        final_text = f"Sorry, there was a problem during processing:{e}"

    # 4. Chunked streaming
    await _stream_chunked(final_text, on_stream)

    return final_text, tool_events, tool_results


async def _run_node_plain(
    state: AgentBuilderState,
    system_prompt: str,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Pure LLM calling mode: no tools are passed and LLM responds directly.

    Used for nodes that do not require tool calls (such as pure wait/clarification).
    """
    user_msg_content = state.get("user_message", "") or ""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg_content},
    ]

    try:
        response = await llm_client.achat(
            _convert_messages(messages),
            temperature=0.3,
            auto_execute_tools=False,
        )
        final_text = getattr(response, "content", "") or ""
    except Exception as e:
        logger.error("[NodePlain][LLMError] %s", e, exc_info=True)
        final_text = f"Sorry, there was a problem during processing:{e}"

    await _stream_chunked(final_text, on_stream)
    return final_text, [], {}


async def _run_node_llm(
    state: AgentBuilderState,
    system_prompt: str,
    tool_registry: Any,
    llm_client: Any,
    required_tool_name: Any = "",
    include_inspect_tools: bool = False,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Node LLM calls the unified entrance (based on UnifiedLLMClient, no XML leakage).

    Route to different modes based on required_tool_name type:
    - String (non-empty): tool first mode (_run_node_tool_first)
    - List: LLM Function Calling mode (_run_node_llm_fc)
    - Empty string: pure LLM calling mode (_run_node_plain)
    """
    if isinstance(required_tool_name, list) and required_tool_name:
        return await _run_node_llm_fc(
            state, system_prompt, tool_registry, llm_client,
            required_tool_name, include_inspect_tools,
            event_callback, on_stream,
        )
    if required_tool_name and isinstance(required_tool_name, str):
        return await _run_node_tool_first(
            state, system_prompt, tool_registry, llm_client,
            required_tool_name, include_inspect_tools,
            event_callback, on_stream,
        )
    return await _run_node_plain(state, system_prompt, llm_client, event_callback, on_stream)



async def _invoke_stream(callback: Optional[Callable], text: str):
    """Safely call stream callback."""
    if callback and text:
        try:
            await callback(text)
        except Exception:
            pass


async def _clarify_with_llm(
    state: AgentBuilderState,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> str:
    """When the intention is unclear, use the term financial product expert  + Agent The Build Assistant persona guides users through LLM natural dialogue.

    It is not a static template prompt, but a combination of conversation history, current Agent status, and user messages.
    Let LLM analyze possible user needs from a product expert perspective, ask questions or suggest next steps.

    Returns:
        LLM Generated lead reply text
    """
    user_msg = state.get("user_message", "") or ""
    spec_name = state.get("spec_name", "") or "Unnamed"
    current_node = state.get("current_node", "")
    published = state.get("official_acceptance_decision") == "published"
    test_status = state.get("test_result", {}).get("status", "")
    version_id = state.get("version_id", "")
    build_status = state.get("build_status", "")

    # Build a summary of the current state
    state_summary_parts = []
    state_summary_parts.append(f"current node: {current_node}")
    if spec_name and spec_name != "Unnamed":
        state_summary_parts.append(f"current Agent: {spec_name}")
    if version_id:
        state_summary_parts.append(f"version: {version_id}")
    if build_status:
        state_summary_parts.append(f"Build status: {build_status}")
    if test_status:
        state_summary_parts.append(f"test status: {test_status}")
    if published:
        state_summary_parts.append("Release status: Published")
    state_summary = " | ".join(state_summary_parts)

    # Collect recent conversation history
    history = state.get("message_history", []) or []
    recent_history = ""
    if history:
        recent_entries = history[-6:]  # Last 3 rounds
        lines = []
        for entry in recent_entries:
            role = entry.get("role", "")
            content = str(entry.get("content", ""))[:200]
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "agent":
                lines.append(f"Assistant: {content}")
        recent_history = "\n".join(lines)

    system_prompt = f"""You are the Agent building assistant of the TradingAgentsCN platform, and you are also a senior financial product expert.

Your job is to help users:
1. Create new trading/analysis agents (such as financial report demining assistant, valuation analysis assistant, moat analysis assistant, etc.)
2. Modify/upgrade the design and capabilities of existing Agents
3. Test and release Agent
4. Answer questions about Agent capabilities and platform functionality

Current status:{state_summary}

Recent conversations:
{recent_history}

Latest news from users: {user_msg}] 

Your task:
1. Analyze user messages from the perspective of financial product experts to determine what users may want
2. If the intention can be determined (such as creating a new Agent, modifying an existing Agent, testing, releasing, etc.), confirm and guide it with natural language
3. If the intention is unclear, ask questions to guide the user to clarify their needs.——You can chat for a few rounds and gradually converge.
4. If the user describes the needs of a new Agent (even if it is just a preliminary idea), actively guide the refinement: target users, core functions, input and output, data sources, etc.
5. Replies should be natural, professional, and concise, just like a product manager talking to users about their needs.

Important rules:
- Do not output tool call XML or JSON
- Do not repeat the previous round of responses
- Don t just list options for users to choose, but provide targeted guidance based on user messages.
- If the user says he wants to create a new Agent, start chatting directly about the requirements (such as"Okay, what kind of moat analysis agent do you want to create? Can you tell me specifically what aspects you want it to help you analyze?") 
- If the user wants to modify an existing Agent, ask clearly what they want to change
- Chinese reply"""

    try:
        messages = [{"role": "system", "content": system_prompt}]
        response = await llm_client.achat(
            _convert_messages(messages),
            temperature=0.4,
            auto_execute_tools=False,
        )
        reply = getattr(response, "content", "") or ""
        if not reply.strip():
            reply = _static_clarify_fallback(state)
    except Exception as e:
        logger.warning("[ClarifyWithLLM] LLM The call fails, use static cover: %s", e)
        reply = _static_clarify_fallback(state)

    # 🔑 Append optional options at the end of the LLM reply to let the user know what actions are available
    options = _build_contextual_options(state)
    if options and options not in reply:
        reply = reply.rstrip() + "\n\n" + options

    return reply.strip()


def _build_contextual_options(state: AgentBuilderState) -> str:
    """Generate a list of options based on the current status (placed at the end of the LLM reply)."""
    published = state.get("official_acceptance_decision") == "published"
    current_node = state.get("current_node", "")
    has_version = bool(state.get("version_id"))

    lines = ["---", "You can:"]

    if current_node == "error_recovery":
        lines.append("- Reply Retry and re-execute the previous step.")
        lines.append("- Reply Skip to skip the current step")
        lines.append("- Reply Modify to return to demand adjustment")
        lines.append("- Directly describe the new Agent")
        lines.append("- Reply Cancel to end the process")
    elif published:
        lines.append("- Reply Retest [Stock name]] Retest with other targets (such as Retest iFlytek )")
        if has_version:
            lines.append("- Reply to Upgrade Requirements or Modify Requirements to create a new version")
        lines.append("- Reply Re-do gap analysis to refresh capability gap analysis")
        lines.append("- Reply Regenerate Solution to regenerate candidate solutions based on the current gap.")
        lines.append("- Directly describe the new Agent you want to create (such as I want to create a moat analysis agent )")
        lines.append("- Reply Cancel to end the current session")
    else:
        lines.append("- Reply Publish to confirm publishing this version")
        lines.append("- Reply Retest [Stock name]] Run a new test (such as Retest Kweichow Moutai )")
        if has_version:
            lines.append("- Reply Upgrade Requirements or Modify Requirements to return to demand adjustment.")
        lines.append("- Reply Re-do gap analysis to refresh capability gap analysis")
        lines.append("- Reply Regenerate Solution to regenerate candidate solutions based on the current gap.")
        lines.append("- Directly describe the new Agent you want to create (such as I want to create a moat analysis agent )")
        lines.append("- Reply Cancel to end the process")

    return "\n".join(lines)


def _static_clarify_fallback(state: AgentBuilderState) -> str:
    """LLM Static clarification prompt when unavailable."""
    user_msg = state.get("user_message", "") or ""
    spec_name = state.get("spec_name", "") or "current"
    published = state.get("official_acceptance_decision") == "published"
    msg_hint = f" (What you said is {user_msg[:60]}] ) " if user_msg else ""

    if published:
        return (
            f"Sorry, I don t quite understand what you mean{msg_hint}. \n\n"
            f" [{spec_name}] Published. You can:\n"
            "- Directly describe the new Agent you want to create (such as I want to create a moat analysis agent )\n"
            "- Reply to Upgrade Requirements to modify the current Agent\n"
            "- Reply Retest [Stock name]] Retest\n"
            "- Reply Cancel to end"
        )
    return (
        f"Sorry, I don t quite understand what you mean{msg_hint}. \n\n"
        f" [{spec_name}] Currently in testing/evaluation phase. You can:\n"
        "- Reply Publish to put the current version online\n"
        "- Directly describe the new Agent\n"
        "- Reply to Upgrade Requirements to modify the current Agent\n"
        "- Reply Retest [Stock name]] Retest\n"
        "- Reply Cancel to end"
    )


def _build_force_call_params(tool_name: str, state: AgentBuilderState) -> dict:
    """Constructs minimum parameters for the tool that is forced to be called."""
    user_msg = state.get("user_message", "")
    spec_id = state.get("spec_id", "")
    # 🔑 Spec_id is no longer set prematurely in node_requirement_intake if spec_id is empty.
    # Avoid 404 caused by GET spec immediately after the front end gets the spec_id from thread_context),
    # Prioritize the slug generated by LLM (existing in proposed_plan) until generate_confirmed_candidate_agent
    # The tool sets state.spec_id in node_generate_candidate_agent only after successfully writing the library.
    if not spec_id:
        proposed_plan = state.get("proposed_plan", {}) or {}
        spec_id = str(proposed_plan.get("proposed_agent_slug") or "").strip()

    if tool_name == "prepare_agent_requirement_intake":
        return {"user_request": user_msg}
    if tool_name == "prepare_agent_generation_confirmation":
        # need agent_id, agent_name, target_responsibility, tool_ids
        spec_name = state.get("spec_name", "") or "candidate Agent"
        responsibility = state.get("requirement_summary", "") or spec_name
        proposed_plan = state.get("proposed_plan", {}) or {}
        preferred_tools = proposed_plan.get("preferred_tools", "")
        if isinstance(preferred_tools, list):
            tool_ids = ",".join(str(t) for t in preferred_tools if t)
        elif isinstance(preferred_tools, str) and preferred_tools and "（" not in preferred_tools:
            tool_ids = preferred_tools
        else:
            tool_ids = ""
        # Priority is given to using the spec_id (English slug) in state. If not, the one generated by LLM is taken from proposed_plan. slug
        agent_id = state.get("spec_id", "")
        if not agent_id:
            agent_id = str(proposed_plan.get("proposed_agent_slug") or "").strip()
        if not agent_id:
            from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import _fallback_slug_from_name
            agent_id = _fallback_slug_from_name(spec_name, state.get("original_user_request", ""), responsibility)
        return {
            "agent_id": agent_id,
            "agent_name": spec_name,
            "target_responsibility": responsibility,
            "tool_ids": tool_ids,
        }
    if tool_name == "analyze_agent_workshop_gaps":
        # analyze_agent_workshop_gaps Prioritize reusing the current workshop session to ensure that the ability gap analysis of the current Agent is re-run.
        session_id = str(state.get("workshop_session_id") or "").strip()
        if session_id:
            return {"session_id": session_id}
        spec_name = state.get("spec_name", "") or "candidate Agent"
        responsibility = state.get("requirement_summary", "") or spec_name
        agent_id = state.get("spec_id", "")
        if not agent_id:
            proposed_plan = state.get("proposed_plan", {}) or {}
            agent_id = str(proposed_plan.get("proposed_agent_slug") or "").strip()
        if not agent_id:
            from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import _fallback_slug_from_name
            agent_id = _fallback_slug_from_name(spec_name, state.get("original_user_request", ""), responsibility)
        return {
            "agent_id": agent_id,
            "agent_name": spec_name,
            "target_responsibility": responsibility,
        }
    if tool_name == "propose_agent_build_plans":
        # propose_agent_build_plans only accept gap_report_json / agent_responsibility / agent_output_shape
        gap_report = state.get("gap_report", {}) or {}
        # If gap_report is an error response, treat it as empty and let the tool go. fallback
        if isinstance(gap_report, dict) and gap_report.get("status") == "error":
            gap_report = {}
        responsibility = state.get("requirement_summary", "") or state.get("spec_name", "")
        return {
            "gap_report_json": json.dumps(gap_report, ensure_ascii=False) if gap_report else "{}",
            "agent_responsibility": responsibility,
        }
    if tool_name == "generate_confirmed_candidate_agent":
        # Rebuild required parameters from state
        original_request = state.get("original_user_request", "") or user_msg
        spec_name = state.get("spec_name", "") or original_request[:30]
        responsibility = state.get("requirement_summary", "") or spec_name
        candidate_plans = state.get("candidate_plans", []) or []
        selected_plan_id = state.get("selected_plan_id", "direct")
        gap_report = state.get("gap_report", {}) or {}
        if not isinstance(gap_report, dict):
            gap_report = {}

        # Note: required_new_skills is"Need to create new capability descriptions", Not registered tool_id
        # Cannot be passed directly as tool_ids bind_agent_tools_and_validate_candidate
        # The true should be extracted from gap_report.existing_tools / suggested_tools tool_id

        # Preferably extract from gap_report.existing_tools (these are the registered available tools)
        tool_ids = ""
        existing_tools = gap_report.get("existing_tools", []) or []
        if isinstance(existing_tools, list) and existing_tools:
            # existing_tools The format may be "tool_id | Description" or pure "tool_id"
            ids: list[str] = []
            for item in existing_tools:
                text = str(item or "").strip()
                if not text:
                    continue
                # Extract | The previous tool_id part
                if "|" in text:
                    tid = text.split("|", 1)[0].strip()
                else:
                    tid = text
                if tid:
                    ids.append(tid)
            if ids:
                tool_ids = ",".join(ids[:8])  # up to 8

        # If existing_tools is empty, try to extract from suggested_tools tool_id
        if not tool_ids:
            suggested_tools = gap_report.get("suggested_tools", []) or []
            if isinstance(suggested_tools, list):
                ids = []
                for item in suggested_tools:
                    if isinstance(item, dict):
                        tid = str(item.get("tool_id") or "").strip()
                        if tid:
                            ids.append(tid)
                    elif isinstance(item, str):
                        if item.strip():
                            ids.append(item.strip())
                if ids:
                    tool_ids = ",".join(ids[:5])

        # Get the bottom of things: use search_project_capabilities (always available, so that the Agent can at least check capabilities)
        if not tool_ids:
            tool_ids = "search_project_capabilities"
            logger.warning("[GenAgent][ForceParams] No tools available, use it with caution search_project_capabilities")

        # Generate agent_id: Prioritize using spec_id in state (set by generate_confirmed_candidate_agent after writing the library),
        # Next, use the slug generated by LLM (existing in proposed_plan), and finally use keyword mapping.
        agent_id = spec_id
        if not agent_id:
            proposed_plan = state.get("proposed_plan", {}) or {}
            agent_id = str(proposed_plan.get("proposed_agent_slug") or "").strip()
        if not agent_id:
            from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import _fallback_slug_from_name
            agent_id = _fallback_slug_from_name(spec_name, original_request, responsibility)

        system_prompt = (
            f"Are you a person who focuses on {responsibility} financial analysis assistant."
            f"Based on the original needs of users{original_request}] , Use the tools provided by the platform to obtain real data,"
            f"Output a structured analysis report, including core judgments, key basis and risk tips."
        )

        # Serialize gap_report for use by direct/complete/quick scenarios
        gap_report_json = json.dumps(gap_report, ensure_ascii=False) if gap_report else "{}"

        # Extract blocking_gaps as acknowledged_gaps
        # Semantics: The user's selection of the plan indicates knowledge and acceptance of these gaps (there is no independent confirmation step in the force-call scenario)
        blocking_gaps_list = gap_report.get("blocking_gaps", []) or []
        if isinstance(blocking_gaps_list, list):
            ack_gaps = [str(g or "").strip() for g in blocking_gaps_list if str(g or "").strip()]
        else:
            ack_gaps = []
        acknowledged_gaps_json = json.dumps(ack_gaps, ensure_ascii=False) if ack_gaps else ""

        logger.info(
            "[GenAgent][ForceParams] plan=%s tool_ids=%s gap_report_keys=%s ack_gaps=%d",
            selected_plan_id, tool_ids, list(gap_report.keys()) if gap_report else [], len(ack_gaps),
        )

        return {
            "agent_id": agent_id,
            "agent_name": spec_name,
            "target_responsibility": responsibility,
            "tool_ids": tool_ids,
            "system_prompt": system_prompt,
            "selected_plan_id": selected_plan_id,
            "confirmed": True,
            "allow_overwrite": True,  # force-call Overwriting is allowed in scenarios (to avoid blocking historical dirty data)
            "gap_report_json": gap_report_json,
            "acknowledged_gaps": acknowledged_gaps_json,
        }
    if tool_name == "build_agent_workshop_version":
        # Requires session_id, obtained from state
        # If the user has confirmed that they want to overwrite the old version, pass overwrite_existing=True
        params: dict = {"session_id": state.get("workshop_session_id", "")}
        if state.get("build_status") == "pending_user_decision":
            params["overwrite_existing"] = True
        return params
    if tool_name == "run_agent_workshop_real_data_test":
        # Requires version_id and stock_symbol
        version_id = _sanitize_version_id(state.get("version_id", ""))
        test_symbol = state.get("test_symbol", "")
        # Try to extract the stock code from the user's message (hidden)
        if not test_symbol:
            msg = state.get("user_message", "")
            m = re.search(r"\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b", msg)
            if m:
                test_symbol = m.group(1)
                state["test_symbol"] = test_symbol
        return {
            "version_id": version_id,
            "stock_symbol": test_symbol,
            "market_type": "A shares",
            "skip_evaluation": True,
        }
    if tool_name == "publish_agent_workshop_version":
        # need version_id
        return {"version_id": _sanitize_version_id(state.get("version_id", ""))}
    if tool_name == "evaluate_agent_workshop_version":
        # Version_id is required; if there is a runtime_result in the test phase, pass it in as well.
        params = {"version_id": _sanitize_version_id(state.get("version_id", ""))}
        runtime_result_json = str(state.get("_test_runtime_result_json", "") or "").strip()
        if runtime_result_json:
            params["runtime_result_json"] = runtime_result_json
        user_feedback = str(state.get("_test_user_feedback", "") or "").strip()
        if user_feedback:
            params["user_feedback"] = user_feedback
        return params
    if tool_name == "iterate_agent_workshop_version":
        return {
            "version_id": _sanitize_version_id(state.get("version_id", "")),
            "feedback": state.get("user_message", "") or "Upgrade requirements",
        }
    return {}


async def _emit_event(callback: Optional[Callable], event_type: str, label: str, payload: Any = None):
    """Send events to SSE streams."""
    if callback:
        try:
            await callback(event_type, label, payload)
        except Exception:
            pass


def _is_confirm_like(msg: str) -> bool:
    """Determine if the message looks like confirmation/acknowledgment."""
    t = (msg or "").strip().lower()
    if not t:
        return False
    confirm_keywords = ("Confirm", "OK", "OK", "OK", "No problem", "ok", "yes", "Confirmed", "Agree")
    return any(kw in t for kw in confirm_keywords)


def _extract_json_from_result(result_str: str) -> dict:
    """Extract JSON from tool result string."""
    if not result_str:
        return {}
    try:
        return json.loads(result_str)
    except json.JSONDecodeError:
        # Try to extract JSON chunks
        m = re.search(r'\{[\s\S]*\}', result_str)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {}


def _sanitize_version_id(value: Any) -> str:
    """Clean version_id to ensure a clean version_id string is returned.

    Defensive handling: When the build_agent_workshop_version tool is not fixed in time,
    version_id may be json.dumps(default=str) str repr converted to Pydantic object,
    shaped like "id=ObjectId('...') version_id='agent_xxx_v1' spec_id='...' ...". 
    Here the real version_id is extracted from this repr.
    """
    if value is None:
        return ""
    # dict: Get the version_id field directly
    if isinstance(value, dict):
        return str(value.get("version_id") or "").strip()
    text = str(value).strip()
    if not text:
        return ""
    # Check if it is an object repr (containing version_id= or ObjectId( mark)
    if "version_id=" in text or "ObjectId(" in text:
        # Try to extract version_id='...' or version_id="..."
        m = re.search(r"version_id=['\"]([^'\"]+)['\"]", text)
        if m:
            return m.group(1).strip()
        # Bottom line: If the entire string is not like version_id (contains spaces/equal signs/brackets), return empty
        if "=" in text or "(" in text or " " in text:
            logger.warning(
                "[SanitizeVersionId] version_id Looks like object repr, cannot be extracted: %s",
                text[:200],
            )
            return ""
    return text


# ──────────────────────────────────────────────────────────────
# node function
# ──────────────────────────────────────────────────────────────

async def node_classify_user_intent(
    state: AgentBuilderState,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """LLM Intent classification node (v2: topology aware + Confidence + Customize prompt words by node).

    Select different prompt words according to current_node to let LLM focus on the core issues of the current stage.
    confidence < 0.7 clarification_needed is triggered by route_after_classify.
    """
    current_node = state.get("current_node", "")
    msg = state.get("user_message", "") or ""

    # ── Accumulate conversation history (last N rounds) ──
    history = state.setdefault("message_history", [])
    prev_response = state.get("final_response", "") or ""
    if prev_response and history and history[-1].get("role") == "user":
        # The agent reply from the previous step has not been recorded yet. → make up
        pass  # No repeated insertion, append uniformly when classifying
    if msg:
        if prev_response:
            history.append({"role": "agent", "content": prev_response})
        history.append({"role": "user", "content": msg})
        # Limit recent 20 entries (10 rounds)
        if len(history) > 20:
            state["message_history"] = history[-20:]

    node_type = _classify_node_type(current_node)
    classify_prompt = _build_classify_prompt(state, node_type)

    # ── Intent classification prompt word log (for debugging)──
    _log_intent_classify_prompt(node_type, classify_prompt, msg)

    messages = [
        {"role": "system", "content": "You are an intent classifier and just output JSON."},
        {"role": "user", "content": classify_prompt},
    ]

    try:
        response = await llm_client.achat(
            _convert_messages(messages),
            temperature=0.0,
            auto_execute_tools=False,
        )
        raw = getattr(response, "content", "") or ""
        result = _extract_json_from_result(raw)
        if not result or "intent" not in result:
            # Get the scoop: Use minimalist rules
            intent = _fallback_classify_intent(msg, current_node)
            result = {"intent": intent, "confidence": 0.3, "reason": "LLM fallback"}
            logger.warning(
                "[ClassifyIntent][Fallback] LLM Return cannot be parsed: %s, Use a pocket: %s",
                raw[:200], intent,
            )

        if _is_rerun_gap_analysis_request(msg):
            result = {
                "intent": "rerun_gap",
                "confidence": 0.98,
                "reason": "The user explicitly requested to re-perform the Agent Workshop capability gap analysis",
            }
        elif _is_regenerate_plan_request(msg):
            result = {
                "intent": "regenerate_plan",
                "confidence": 0.95,
                "reason": "User requests to regenerate candidate solutions based on current capability gaps",
            }

        state["user_intent"] = result.get("intent", "explore_more")
        state["intent_confidence"] = float(result.get("confidence", 0.0))
        state["intent_reason"] = str(result.get("reason", "") or "")

        if state["user_intent"] == "rerun_gap":
            state["gap_report"] = {}
            state["candidate_plans"] = []
            state["pending_options"] = []
            state["selected_plan_id"] = ""
            state["clarification_needed"] = False
        elif state["user_intent"] == "regenerate_plan":
            state["candidate_plans"] = []
            state["pending_options"] = []
            state["selected_plan_id"] = ""
            state["clarification_needed"] = False

        if result.get("selected_index"):
            state["user_selected_index"] = int(result["selected_index"])
        elif result.get("selected_id"):
            state["user_selected_id"] = str(result["selected_id"])

        # LLM Test ticker inferred from context
        if result.get("test_symbol"):
            state["test_symbol"] = str(result["test_symbol"]).strip()

        # 🔑 If the user confirms the test but does not give a stock code, Kweichow Moutai will be used by default.(600519)
        if state.get("user_intent") in ("confirmed",) and not state.get("test_symbol") and current_node in ("wait_test_request", "generate_candidate_agent"):
            state["test_symbol"] = "600519"
            logger.info("[ClassifyIntent] The user confirms the test but does not specify the target, and the default is used 600519")

        if state.get("user_intent") == "retry":
            state["test_result"] = {}
            state["official_acceptance_decision"] = ""
            state["final_response"] = ""
            state["tool_events"] = []
            state["clarification_needed"] = False

        # 🔑 create_skill Intent: Set the mark to let subsequent wait nodes output skill creation prompts
        # Note: The modification of state by the conditional edge function will not be persisted and must be set in the node function.
        if state.get("user_intent") == "create_skill":
            state["skill_creation_requested"] = True
            state["clarification_needed"] = False
            logger.info("[ClassifyIntent] create_skill intention: settings skill_creation_requested=True")

        # ── Stock name → Code analysis ──
        # If test_symbol is not a 6-digit code (is a stock name such as"iFlytek") , Try parsing into code.
        # First check the hardcoded common stock mapping table. If it cannot be found, use LLM to analyze it.
        test_symbol = state.get("test_symbol", "")
        if test_symbol and not re.match(r"^\d{6}$", test_symbol):
            resolved = _resolve_stock_name_to_code(test_symbol)
            if resolved:
                logger.info(
                    "[ClassifyIntent][NameResolve] test_symbol '%s' → '%s'",
                    test_symbol, resolved,
                )
                state["test_symbol"] = resolved
            else:
                # Parsing failed: clear test_symbol and let wait_test_request output"Please provide stock code"Tips
                logger.warning(
                    "[ClassifyIntent][NameResolve] Unable to parse test_symbol='%s', "
                    "Clear and trigger clarification prompts", test_symbol,
                )
                state["test_symbol"] = ""

        # ── Bottom line: wait_test_request node + confirmed/retry Intention but no test_symbol ──
        # Prevent LLM from not outputting the test_symbol field as required by the prompt word.
        # Extract the agent's most recently recommended stock symbols from message_history / final_response to fill in.
        if (
            current_node in ("wait_test_request", "generate_candidate_agent", "wait_evaluation", "evaluate_or_publish")
            and state.get("user_intent") in ("confirmed", "retry", "select_option")
            and not state.get("test_symbol")
        ):
            fallback_code = ""
            # When stock exchange is retested, stock names/codes will be parsed from the user's current round of messages first.
            if state.get("user_intent") == "retry":
                fallback_code = _resolve_stock_name_to_code(msg)
            if not fallback_code:
                fallback_code = _extract_suggested_stock_from_state(state)
            if fallback_code:
                state["test_symbol"] = fallback_code
                logger.info(
                    "[ClassifyIntent][FallbackSymbol] LLM test_symbol is not output,"
                    "Extract suggested code from history: %s", fallback_code,
                )

        logger.info(
            "[ClassifyIntent] node=%s type=%s msg=%.60s → intent=%s confidence=%.2f reason=%s",
            current_node, node_type, msg, state["user_intent"],
            state["intent_confidence"], state["intent_reason"][:80],
        )

        # ── Intent classification results log (paired with prompt words)──
        _log_intent_classify_result(
            node_type, state["user_intent"], state["intent_confidence"],
            state["intent_reason"], raw, result,
        )
    except Exception as e:
        logger.error("[ClassifyIntent][Error] %s, Use a pocket", e, exc_info=True)
        state["user_intent"] = _fallback_classify_intent(msg, current_node)
        state["intent_confidence"] = 0.0
        state["intent_reason"] = f"LLM error: {e}"

    # ── Prejudgment: Whether the intention of this round will make the process"stay where you are" (Unable to advance)──
    # The modification of state by the conditional function will not be persisted to the node, so here (within the node)
    # Precompute clarification_needed for the wait node to output clarification prompts,
    # Avoid re-outputting the content of the previous round.
    # Note: low confidence (<0.7) clarification_needed will be triggered in route_after_classify,
    # The settings are not repeated here.
    intent = state["user_intent"]
    if state.get("intent_confidence", 0.0) >= 0.7:
        state["clarification_needed"] = _will_stay_on_wait_node(state)
    else:
        # 🔑 Low confidence: the intent is unreliable and the routing function will clarification_needed=True but not persistent,
        # Must be preset within the node, otherwise the wait node cannot see it clarification_needed=True, 
        # Only options will be appended to the final_response of the previous round (shown as"Repeat last round of replies") . 
        # Clarification is only needed if you are currently on a wait node (action nodes do not check this field).
        _is_wait_node = current_node in (
            "wait_evaluation", "wait_test_request", "wait_intake_confirmation",
            "wait_requirement_confirmation", "wait_plan_selection",
            "evaluate_or_publish", "error_recovery",
        )
        state["clarification_needed"] = _is_wait_node

    # ── Special handling during error recovery phase ──
    # If the user intent is actionable (confirmed/retry/select_option),
    # It means that the user wants to try again and needs to clear the old error mark.
    # It must be done within the node (the state modification of the routing function is not persisted).
    if current_node == "error_recovery" and intent in ("confirmed", "retry", "select_option"):
        errors = state.get("errors", []) or []
        if errors:
            state["errors"] = errors[:-1] if len(errors) > 1 else []
            logger.info(
                "[ClassifyIntent] error_recovery retry: Clear old errors, "
                "remaining=%d", len(state.get("errors", [])),
            )

    # 🔑 new_agent Intent: Prompt the user to manually go to the Agent workshop to create a new Agent
    # No more attempts to create new sessions automatically because they are too complex and prone to confusion.
    if intent == "new_agent":
        spec_name = state.get("spec_name", "") or "current Agent"
        state["final_response"] = (
            f"You are currently at {spec_name}] In a session, new Agents cannot be created directly here.\n\n"
            f"Please click on Agent Workshop on the left **New Agent** button, fill in your requirements and start creating:\n"
            f"> {msg[:120]}\n\n"
            f"After creation, you can continue to modify the {spec_name}] Perform iterative optimization."
        )
        logger.info(
            "[ClassifyIntent] new_agent intention: Prompts user to create manually (old_spec_name=%s)",
            spec_name,
        )

    # 🔑 If version_id is empty but spec_id exists, complete from database version_id
    # Avoid routing to generate_candidate_agent instead iterate_agent_version
    _vid = _sanitize_version_id(state.get("version_id", ""))
    if not _vid and state.get("spec_id"):
        try:
            from app.core.database import get_mongo_db
            _db = get_mongo_db()
            _latest_ver = await _db["agent_workshop_versions"].find_one(
                {"spec_id": state["spec_id"]},
                sort=[("created_at", -1)],
            )
            if _latest_ver:
                _resolved_vid = str(_latest_ver.get("version_id") or "").strip()
                if _resolved_vid:
                    state["version_id"] = _resolved_vid
                    logger.info(
                        "[ClassifyIntent][ResolvedVersionId] spec_id=%s → version_id=%s (Complete from database)",
                        state.get("spec_id"), _resolved_vid,
                    )
        except Exception as _vid_err:
            logger.warning("[ClassifyIntent][ResolvedVersionId] failed: %s", _vid_err)

    return state


def _classify_node_type(current_node: str) -> str:
    """Map node names to node types intended to be classified, and each type has an independent prompt word."""
    if current_node in ("wait_intake_confirmation", "wait_requirement_confirmation"):
        return "confirmation"
    if current_node == "wait_plan_selection":
        return "plan_selection"
    if current_node in ("wait_test_request", "wait_evaluation", "evaluate_or_publish", "generate_candidate_agent"):
        return "test_eval"
    if current_node == "error_recovery":
        return "error"
    return "generic"


def _extract_suggested_stock_from_state(state: AgentBuilderState) -> str:
    """Extract the Agent s most recently recommended stock symbols from message_history / final_response.

    A catch-all for the wait_test_request node: when the LLM classification result does not have a test_symbol field,
    But when the user s reply is in a confirmation/agree tone, find the most recent agent reply containing the stock code from the history.
    """
    history = state.get("message_history", []) or []
    candidates = list(reversed(history))
    prev_resp = state.get("final_response", "") or ""
    if prev_resp:
        candidates.insert(0, {"role": "agent", "content": prev_resp})
    for entry in candidates:
        if not isinstance(entry, dict) or entry.get("role") != "agent":
            continue
        content = str(entry.get("content", ""))
        m = re.search(r"\b(00\d{4}|30\d{4}|60\d{4}|68\d{4}|6\d{4})\b", content)
        if m:
            return m.group(1)
    return ""


def _resolve_stock_name_to_code(query: str) -> str:
    """Parse stock names/codes into 6-digit stock codes through local stock basic information collection."""
    text = str(query or "").strip()
    if not text:
        return ""
    m = re.search(r"\b(00\d{4}|30\d{4}|60\d{4}|68\d{4}|6\d{4})\b", text)
    if m:
        return m.group(1)

    # Clean up common spoken words and retain the key words of stock names.
    keyword = re.sub(r"(Change|one|stocks|test|For a moment|retest|Test again|use|of|code|securities)", "", text).strip()
    keyword = keyword or text
    if not keyword:
        return ""

    try:
        from core.skill_runtime.project_access import query_stock_collection

        escaped = re.escape(keyword)
        projection = {"_id": 0, "code": 1, "symbol": 1, "name": 1, "source": 1}
        docs = query_stock_collection(
            "stock_basic_info",
            filters={
                "$or": [
                    {"name": keyword},
                    {"name": {"$regex": escaped, "$options": "i"}},
                    {"code": keyword},
                    {"symbol": keyword},
                ]
            },
            projection=projection,
            limit=20,
        )
        if not docs:
            return ""

        def _score(doc: Dict[str, Any]) -> tuple[int, int]:
            name = str(doc.get("name") or "")
            source = str(doc.get("source") or "")
            exact = 1 if name == keyword else 0
            preferred_source = 1 if source in ("tushare", "multi_source", "akshare", "baostock") else 0
            return (exact, preferred_source)

        best = sorted(docs, key=_score, reverse=True)[0]
        code = str(best.get("code") or best.get("symbol") or "").strip()
        code_match = re.search(r"\d{6}", code)
        if code_match:
            return code_match.group(0)
    except Exception as exc:
        logger.warning("[ResolveStockName] Query stock_basic_info failed: %s", exc)
    return ""


# ── Intent classification prompt word log ──

_INTENT_PROMPT_LOGGER: Optional[logging.Logger] = None
_INTENT_PROMPT_LOG_PATH: str = ""


def _get_intent_prompt_logger() -> logging.Logger:
    """Obtain a dedicated logger for intent classification prompt words and write it to an independent log file."""
    global _INTENT_PROMPT_LOGGER, _INTENT_PROMPT_LOG_PATH
    if _INTENT_PROMPT_LOGGER is not None:
        return _INTENT_PROMPT_LOGGER

    from pathlib import Path
    logs_dir = Path(__file__).resolve().parents[3] / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _INTENT_PROMPT_LOG_PATH = str(logs_dir / "intent_classify_prompts.log")

    _INTENT_PROMPT_LOGGER = logging.getLogger("intent_classify_prompts")
    _INTENT_PROMPT_LOGGER.setLevel(logging.DEBUG)
    _INTENT_PROMPT_LOGGER.propagate = False  # Does not pollute root logger

    # If there is already a handler, it will not be added again.
    if not any(isinstance(h, logging.FileHandler) for h in _INTENT_PROMPT_LOGGER.handlers):
        handler = logging.FileHandler(_INTENT_PROMPT_LOG_PATH, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "\n" + "=" * 80 + "\n[%(asctime)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        _INTENT_PROMPT_LOGGER.addHandler(handler)

    return _INTENT_PROMPT_LOGGER


def _log_intent_classify_prompt(node_type: str, prompt: str, user_msg: str):
    """Write the complete prompt words for the intent classification to a separate log file."""
    try:
        log = _get_intent_prompt_logger()
        sep = "-" * 60
        log.debug(
            "node_type=%s\n"
            "user_message=%s\n"
            "%s\n"
            "%s\n"
            "%s",
            node_type,
            user_msg,
            sep,
            prompt,
            sep,
        )
    except Exception:
        pass  # Log failure does not affect the main process


def _log_intent_classify_result(
    node_type: str, intent: str, confidence: float,
    reason: str, raw_response: str, parsed: dict,
):
    """Write the results of intent classification to a separate log file (in the same file as the prompt word, right next to it)."""
    try:
        log = _get_intent_prompt_logger()
        log.debug(
            ">>> Classification results: intent=%s confidence=%.2f reason=%s\n"
            ">>> LLM original response: %s",
            intent, confidence, reason,
            raw_response[:500] if raw_response else "(empty)",
        )
    except Exception:
        pass


def _format_recent_history(state: AgentBuilderState, rounds: int = 3) -> str:
    """Get the last N conversations from message_history and format them into text available for prompt."""
    history = state.get("message_history", []) or []
    recent = history[-(rounds * 2):]  # every round = agent + user
    if not recent:
        return " (No conversation history yet)"
    lines = []
    for entry in recent:
        role = entry.get("role", "unknown")
        content = str(entry.get("content", ""))[-5000:]
        label = "Agent" if role == "agent" else "User" if role == "user" else role
        lines.append(f"[{label}] {content}")
    return "\n".join(lines)


def _is_rerun_gap_analysis_request(message: str) -> bool:
    """Determine whether the user requires re-running the Agent Workshop capability gap analysis."""
    text = str(message or "").strip().lower()
    if not text:
        return False
    has_gap_word = any(word in text for word in ("gap", "notch", "Capability gap"))
    has_rerun_word = any(word in text for word in ("re", "rerun", "Do it again", "Run again", "Redo", "Refresh", "rerun", "re-run"))
    has_analysis_word = any(word in text for word in ("analysis", "Inventory", "Check", "scan"))
    return has_gap_word and has_rerun_word and has_analysis_word


def _is_regenerate_plan_request(message: str) -> bool:
    """Determine whether the user requires regeneration of candidate solutions based on the current gap."""
    text = str(message or "").strip().lower()
    if not text:
        return False
    has_regen_word = any(word in text for word in ("re", "rerun", "Do it again", "regenerate", "Redo", "Refresh", "rerun", "re-run"))
    has_plan_word = any(word in text for word in ("Plan", "solution", "Candidates", "plan", "plans"))
    return has_regen_word and has_plan_word



def _build_intent_shared_context(state: AgentBuilderState, node_type: str) -> str:
    """Build a common business background for all intent classification prompt words."""
    current_node = state.get("current_node", "") or "START"
    spec_name = state.get("spec_name", "") or "Unnamed Agent"
    stage = state.get("stage", "") or "unknown stage"
    user_message = state.get("user_message", "") or ""
    awaiting_user = bool(state.get("awaiting_user"))

    workflow_steps = """
1. Requirements exploration: Understand what Agent users want to create/iterate, and form a preliminary draft of requirements.
2. Requirements confirmation: Confirm the Agent name, responsibility boundaries, input and output, and things not to do.
3. Capability gap analysis: Check whether the existing tools/skills on the platform are sufficient to support the Agent.
4. Solution selection: Allow users to choose recommended solutions, streamlined solutions or other construction paths.
5. Agent Generate/Build: Generate candidate agent configurations, prompts, tool bindings, and versions.
6. Real data test: Run a real example with the stock code or stock name specified by the user.
7. Test evaluation/release: The user decides to publish, change stocks and retest, modify the Agent, or end it.
""".strip()

    return f"""## Project and business background
You are the intent classifier in TradingAgentsCN s Agent Workshop , not an ordinary chat assistant.
Agent The workshop is used to help users create or iterate a runnable financial analysis Agent: from requirement clarification, capability matching, solution selection, generation and construction, real data testing, to release evaluation.

## current session object
- Agent being processed:{spec_name}
- Current node:{current_node}
- Current stage:{stage}
- Node type:{node_type}
- Whether waiting for user input:{awaiting_user}
- The user s original words in this round:{user_message}

## Agent Workshop standard process
{workflow_steps}

## Classification principles
- Must be combined with current node + User s original words in this round + History of the last three rounds of dialogue +  Current optional actions to determine the user s true intention.
- A short reply from the user (e.g. OK  continue  Change another one  By default  Let s get started ) Usually you have to look back at what the Agent asked in the previous round and cannot understand it in isolation.
- distinguish Modify Agent Design and Only change test data : The stock exchange test is a retry, not a revise.
- distinguish Continue the current Agent process and create new Agent : New_agent only if the user explicitly switches to a completely different Agent theme.
- In the context of Agent Workshop, the user said gap / Gap/gap analysis Default refers to Agent Capability gap analysis/tool capability inventory , It is not a gap in the stock K-line; only if the user explicitly says Stock price gap/jump gap/K-line gap/trend chart gap Only understand it in terms of technical form.
- Users say Redo/rerun/refresh gap analysis Indicates that capability gap analysis is to be re-performed on the current Agent, and the intent should be rerun_gap.
- Users say Regenerate/refresh solutions/candidates/scenarios Indicates that the candidate build plan is regenerated based on the current gap_report, and the intent should be regenerate_plan.
- You only do intent classification and necessary field extraction, but do not output user-oriented explanations.
"""


def _build_classify_prompt(state: AgentBuilderState, node_type: str) -> str:
    """Select customized intent classification prompt words based on node type."""
    if node_type == "confirmation":
        return _build_confirmation_prompt(state)
    elif node_type == "plan_selection":
        return _build_plan_selection_prompt(state)
    elif node_type == "test_eval":
        return _build_test_eval_prompt(state)
    elif node_type == "error":
        return _build_error_prompt(state)
    else:
        return _build_generic_prompt(state)


def _build_confirmation_prompt(state: AgentBuilderState) -> str:
    """Prompt words for intent classification in the requirement confirmation phase. Main concerns: whether to confirm advancement and whether to modify requirements."""
    node = state.get("current_node", "")
    pending_q = state.get("pending_question", "") or ""
    msg = state.get("user_message", "") or ""
    spec_name = state.get("spec_name", "") or "Unnamed"
    recent_history = _format_recent_history(state, rounds=3)
    shared_context = _build_intent_shared_context(state, "confirmation")

    node_desc = {
        "wait_intake_confirmation": "In the requirements exploration phase, the Agent has just submitted the requirements draft and key questions.",
        "wait_requirement_confirmation": "In the requirement confirmation phase, the Agent has just confirmed the responsibility boundaries and output form.",
    }.get(node, f"Waiting for user confirmation ({node}) ")

    return f"""You are the intent classifier. The user is in the requirement confirmation phase of the Agent building process.

{shared_context}

## current node
{node_desc}
Previous question to be confirmed:{pending_q}
Agent Name:{spec_name}

## History of the last 3 conversations
{recent_history}

## Intent Category
- confirmed: The user confirms and can proceed to the next step (such as"OK""OK""Confirm""No problem""That s it") 
- revise: Users want to modify/supplement requirements (such as"add a dimension""Change output format""change direction") 
- rerun_gap: Re-execute the current Agent s capability gap analysis/tool capability inventory
- regenerate_plan: Regenerate candidate solutions/builds
- explore_more: Discussing/asking questions without clear instructions to proceed
- cancel: Cancel/End

## Output format (strictly JSON)
{{"intent": "confirmed|revise|rerun_gap|explore_more|cancel", "confidence": 0.85, "reason": "Determine user intent based on conversation history"}}

Just output JSON."""


def _build_plan_selection_prompt(state: AgentBuilderState) -> str:
    """Prompt words for intention classification in the solution selection phase. The main concern is: which plan the user chooses."""
    msg = state.get("user_message", "") or ""
    pending_options = state.get("pending_options", []) or []
    spec_name = state.get("spec_name", "") or "Unnamed"
    recent_history = _format_recent_history(state, rounds=3)
    shared_context = _build_intent_shared_context(state, "plan_selection")

    opts_lines = []
    for opt in pending_options:
        idx = opt.get("index", "")
        label = opt.get("name", opt.get("id", ""))
        rec = " (Recommended)" if opt.get("recommended") else ""
        opts_lines.append(f"  {idx}. {label}{rec}")
    opts_desc = "\n".join(opts_lines)

    options_json = json.dumps(
        [{"index": o.get("index", ""), "id": o.get("id", "")} for o in pending_options],
        ensure_ascii=False,
    ) if pending_options else "[]"

    return f"""You are the intent classifier. The user is in the solution selection phase of the Agent building process.

{shared_context}

## current node
Agent [{spec_name}] The plan has been generated and is waiting for user selection.

Options:
{opts_desc}

Plan index → id Mapping:
{options_json}

## History of the last 3 conversations
{recent_history}

## Intent Category
- select_option: The user selects a certain option (such as"B""Plan B""second""choose A") → output selected_index or selected_id
- confirmed: Users say"Confirm""Recommended""By default"→ Use recommended solutions
- create_skill: Users want to complete/create missing tools or skills (e.g."Completion tool""Create skill""Make the missing tools") → Prioritize options that include new skill development
- revise: The user wants to modify the requirements and return to the requirements stage.
- rerun_gap: Re-execute the current Agent s capability gap analysis/tool capability inventory
- explore_more: User asks question but has no choice
- cancel: Cancel

## key distinction
- "Completion tool""Create skill""Develop missing tools" → create_skill
- If there is a plan that includes complementing , developing new tools , creating skills , etc., create_skill should output selected_id pointing to the plan
- Prefer low confidence when unsure

## Output format (strictly JSON)
{{"intent": "select_option", "confidence": 0.95, "reason": "User said'B'", "selected_index": 2}}
or {{"intent": "confirmed", "confidence": 0.9, "reason": "Users say follow the recommendations"}}
or {{"intent": "create_skill", "confidence": 0.9, "reason": "Users need to complete missing tools", "selected_id": "plan_with_skill"}}
or {{"intent": "rerun_gap", "confidence": 0.95, "reason": "Users require re-doing capability gap analysis"}}

Just output JSON."""


def _build_test_eval_prompt(state: AgentBuilderState) -> str:
    """Prompt words for intent classification during the test/evaluation phase.

    Main focus: stock code extraction and release vs retesting vs modifying vs creating new Agents.
    """
    current_node = state.get("current_node", "")
    msg = state.get("user_message", "") or ""
    spec_name = state.get("spec_name", "") or "Unnamed"
    published = "Published" if state.get("official_acceptance_decision") == "published" else "Unpublished"
    test_result = state.get("test_result") or {}
    test_status = test_result.get("status", "Not tested") if isinstance(test_result, dict) else "Not tested"
    recent_history = _format_recent_history(state, rounds=3)
    shared_context = _build_intent_shared_context(state, "test_eval")

    # Extract agent-suggested stock symbols from history
    # Note: The reply of the generate_candidate_agent node may be very long, and 600519 may appear at the end of the reply.
    # Cannot be used content[:120] Truncate, otherwise the ticker symbol will be lost.
    # At the same time, generate_candidate_agent will then pass through the build_or_ready node (covering final_response),
    # Therefore, it is necessary to reversely search the latest agent reply containing a stock code from the entire message_history.
    last_hint_code = ""
    last_hint_snippet = ""
    if current_node in ("wait_test_request", "generate_candidate_agent"):
        history = state.get("message_history", []) or []
        # Also check state["final_response"] (The last round of agent replies may not have entered history yet)
        candidates = list(reversed(history))
        prev_resp = state.get("final_response", "") or ""
        if prev_resp:
            candidates.insert(0, {"role": "agent", "content": prev_resp})
        for entry in candidates:
            if entry.get("role") != "agent":
                continue
            content = str(entry.get("content", ""))
            m = re.search(r"\b(00\d{4}|30\d{4}|60\d{4}|68\d{4}|6\d{4})\b", content)
            if m:
                last_hint_code = m.group(1)
                # Extract context around the code (first 80 characters + code + last 80 characters), preserving semantics
                start = max(0, m.start() - 80)
                end = min(len(content), m.end() + 80)
                last_hint_snippet = content[start:end].replace("\n", " ").strip()
                break

    if last_hint_code:
        last_hint = (
            f"\n**Agent Recently suggested tickers:{last_hint_code}**"
            f" (Context: ...{last_hint_snippet}...] ) \n"
            f"**key rules**: If the user replies with a positive tone such as confirmation/agree/start testing etc."
            f" (Such as OK , OK , Let s start , Test run , Start testing , Follow the suggestions ),"
            f"Should be judged intent=confirmed, and**Must**output test_symbol=\"{last_hint_code}\". "
        )
    else:
        last_hint = ""

    node_context = {
        "wait_test_request": (
            f"Agent [{spec_name}] Ready, waiting for the user to give the test target.{last_hint}\n"
            f"The user may: directly give the code (such as 600519); confirm the code suggested by the Agent; say test , start testing , test run , etc. (the default is Kweichow Moutai 600519);"
            f"Say Complete tools , Create skills , Develop missing tools , etc. (indicating that you want to create the missing skills first); cancel."
        ),
        "wait_evaluation": (
            f"Agent [{spec_name}] Test Completed (status={test_status}) , Release status={published}. \n"
            f"Users may: release and launch; change stocks and retest; upgrade/modify Agent design; complete missing skills/tools;"
            f"Re-do capability gap analysis; re-generate candidate solutions; create other Agents; ask questions; cancel."
        ),
        "evaluate_or_publish": (
            f"Agent [{spec_name}] Under evaluation stage, testing status={test_status}. \n"
            f"Users may: Release/continue evaluation; retest; upgrade/modify requirements; complete missing skills/tools;"
            f"Re-do capability gap analysis; re-generate candidate solutions; create other Agents; ask questions; cancel."
        ),
    }.get(current_node, f"Agent [{spec_name}] , node={current_node}")

    return f"""You are the intent classifier. Users in the testing/evaluation phase of the Agent build process.

{shared_context}

## current node
{node_context}

## History of the last 3 conversations
{recent_history}

## Intent Category
- confirmed: User confirmation progress (release/start testing, etc.), including test requests such as test , start testing , test run , run it etc.
- retry: Change the data and retest, the Agent design remains unchanged (such as"Switch to iFlytek and test again""Run with Maotai""retest") 
- revise: Modify the Agent design (e.g."Add a cash flow dimension""Change output format") 
- create_skill: Users want to complete/create missing tools or skills (e.g."Completion tool""Create skill""Develop that missing tool""Make the missing tools") 
- new_agent: The Agent described by the user is the same as {spec_name}] Completely different and want to create new Agent
- rerun_gap: Re-perform the current Agent s capability gap analysis/tool capability inventory (such as"Let s do the gap analysis again.""Refresh capability gap") 
- regenerate_plan: Regenerate candidate solutions/builds based on the current gap_report (e.g."Rebuild solution""Refresh candidates") 
- explore_more: Discussion/questioning, no clear operation instructions
- cancel: Cancel/End

## key distinction
- "test""Start testing""test run" → confirmed (Test intent, default to 600519)
- "Completion tool""Create skill""Develop missing tools" → create_skill (User wants to create missing skill/tool)
- "Try another stock" → retry (Only change the test data, do not change the Agent)
- "Add another dimension of analysis" → revise (Change Agent design)
- "Create a new public opinion analysis Agent" → new_agent (Brand new Agent, unrelated to the current one)

- "Re-do the gap analysis" → rerun_gap (Current Agent workshop capability gap analysis, not stock technology gap)
- "Rebuild solution" → regenerate_plan (Do not rerun gap, only regenerate candidate solutions based on current gap_report)

## Output format (strictly JSON)
{{"intent": "confirmed|retry|revise|create_skill|rerun_gap|regenerate_plan|new_agent|explore_more|cancel", "confidence": 0.85, "reason": "short reasoning"}}

**important**: 
- If the user message contains a stock code (such as 600519), or confirms the code suggested by the Agent in the previous round, additional output:
  {{"intent": "confirmed", "confidence": 0.95, "reason": "User gave code/confirmed suggested code", "test_symbol": "600519"}}
- If the user says test , start testing or test run but does not give a code, it will still be determined as confirmed and output test_symbol="600519": 
  {{"intent": "confirmed", "confidence": 0.9, "reason": "User request to start testing", "test_symbol": "600519"}}
- If the user requests to change stocks and retest (retry intention), and the message contains the stock code (such as 002230),**Must**Output test_symbol field:
  {{"intent": "retry", "confidence": 0.95, "reason": "User requests stock exchange and retest", "test_symbol": "002230"}}
- If the user gives a stock name but no code (such as"iFlytek""Moutai") , output test_symbol=Stock name, analyzed by subsequent logic:
  {{"intent": "retry", "confidence": 0.9, "reason": "User requests stock exchange and retest", "test_symbol": "iFlytek"}}
- User on wait_evaluation said"publish""Go online"→ confirmed
- Users say"Completion tool""Create skill""Develop the missing one"→ create_skill
- Prefer low confidence when unsure

Just output JSON."""


def _build_error_prompt(state: AgentBuilderState) -> str:
    """Intent classification cue words during the error recovery phase. Main concern: Retry vs Modify vs Cancel."""
    msg = state.get("user_message", "") or ""
    recent_history = _format_recent_history(state, rounds=3)
    shared_context = _build_intent_shared_context(state, "error")
    errors = state.get("errors", []) or []
    err_lines = []
    for e in errors[-2:]:
        if isinstance(e, dict):
            err_lines.append(f"{e.get('node','?')}: {e.get('error','?')}")
    err_text = "; ".join(err_lines) if err_lines else "unknown error"

    return f"""You are the intent classifier. The user is in the error recovery phase of the Agent build process.

{shared_context}

## current node
An error was encountered during processing:{err_text}
The user needs to decide the next step.

## History of the last 3 conversations
{recent_history}

## Intent Category
- confirmed: The user wants to retry a failed step (e.g."Try again""Come again""retry") 
- revise: The user wants to modify the requirements and return to the requirements stage.
- rerun_gap: The user requests to re-perform the current Agent s capability gap analysis/tool capability inventory (such as"Re-do gap analysis") 
- regenerate_plan: User asked to regenerate candidate solutions/builds
- explore_more: User asks questions without clear instructions
- cancel: Cancel/End

## Output format (strictly JSON)
{{"intent": "confirmed|revise|rerun_gap|regenerate_plan|explore_more|cancel", "confidence": 0.85, "reason": "User says try again"}}

Just output JSON."""


def _build_generic_prompt(state: AgentBuilderState) -> str:
    """General clue word (unknown node type)."""
    msg = state.get("user_message", "") or ""
    current_node = state.get("current_node", "")
    recent_history = _format_recent_history(state, rounds=3)
    shared_context = _build_intent_shared_context(state, "generic")

    return f"""You are the intent classifier. The user is currently in the Agent build process (node={current_node}) . 

{shared_context}

## History of the last 3 conversations
{recent_history}

## Intent Category
- confirmed: Confirm and advance
- revise: Modify requirements
- new_agent: create new Agent
- rerun_gap: Re-execute the current Agent s capability gap analysis/tool capability inventory
- regenerate_plan: Regenerate candidate solutions/builds
- explore_more: Discuss/Question
- cancel: Cancel

## Output format (strictly JSON)
{{"intent": "confirmed|revise|rerun_gap|regenerate_plan|new_agent|explore_more|cancel", "confidence": 0.7, "reason": "..."}}

Just output JSON."""


def _will_stay_on_wait_node(state: AgentBuilderState) -> bool:
    """Predict whether this round will stay at the current wait node (the intention cannot be converted into effective advancement).

    Consistent with the routing logic of route_after_classify.
    """
    current_node = state.get("current_node", "")
    intent = state.get("user_intent", "explore_more")
    msg = state.get("user_message", "") or ""

    if intent == "cancel":
        return False  # cancel → end, Not a stop
    if intent == "rerun_gap":
        return False  # rerun_gap → gap_analysis
    if intent == "regenerate_plan":
        return False  # regenerate_plan → plan_generation
    if intent == "new_agent":
        return False  # new_agent → requirement_intake, New Agent
    if intent == "create_skill":
        return False  # create_skill Special processing by wait node (output skill creation prompt), not counted"Unable to advance"

    if current_node in ("wait_intake_confirmation", "wait_requirement_confirmation"):
        # confirmed/select_option/revise Both can advance, only explore_more stays.
        return intent not in ("confirmed", "select_option", "revise")

    if current_node == "wait_plan_selection":
        if intent == "revise":
            return False
        if intent in ("select_option", "confirmed"):
            # Can you analyze the solution? Stay until it cannot be parsed
            from core.embedded_nanobot.workflows.agent_builder_conditions import (
                _resolve_selected_from_llm, _resolve_plan_selection,
            )
            if _resolve_selected_from_llm(state):
                return False
            selected_id, _ = _resolve_plan_selection(state.get("pending_options", []), msg)
            if selected_id:
                return False
            if intent == "confirmed":
                # confirmed Will use the recommended/first solution to get the bottom line
                if state.get("recommended_plan_id") or state.get("pending_options"):
                    return False
            return True
        return True  # explore_more

    if current_node == "wait_test_request":
        # LLM test_symbol has been extracted in classify_intent (from message or context)
        if state.get("test_symbol"):
            return False
        return True

    if current_node == "wait_evaluation":
        # confirmed → publish;revise → modify; modify retry → retest;cancel → Cancel
        # retry Test_symbol is required, if not, it will stay (output in wait_test_request"Please provide stock code"Tips)
        if intent == "retry":
            return not state.get("test_symbol")
        return intent not in ("confirmed", "select_option", "revise", "cancel")

    if current_node == "evaluate_or_publish":
        # confirmed/retry/select_option → Retest;revise → Modify requirements
        return intent not in ("confirmed", "select_option", "revise", "cancel", "retry")

    if current_node == "error_recovery":
        # confirmed/retry → retry;revise → Modify requirements
        return intent not in ("confirmed", "select_option", "revise", "cancel", "retry")

    return False


def _fallback_classify_intent(msg: str, current_node: str) -> str:
    """LLM Minimalist cover when not available. Only the most obvious signals are judged, and the subtle intentions are not guessed."""
    from core.embedded_nanobot.workflows.agent_builder_conditions import (
        _is_cancel, _is_route_choice,
    )
    t = (msg or "").strip().lower()
    if _is_cancel(msg):
        return "cancel"
    if _is_rerun_gap_analysis_request(msg):
        return "rerun_gap"
    if _is_regenerate_plan_request(msg):
        return "regenerate_plan"
    if any(word in t for word in ("Upgrade requirements", "Modify requirements", "Adjust needs", "Change requirements")):
        return "revise"
    if _is_route_choice(msg):
        return "select_option"
    # Clear word/short word confirmation signal
    if t in ("Confirm", "OK", "OK", "OK", "No problem", "ok", "yes", "Yes", "publish", "Go online", "continue"):
        return "confirmed"
    return "explore_more"


async def _ensure_slug_uniqueness(db: Any, slug: str) -> str:
    """Check the uniqueness of the slug to avoid conflicts with existing spec_id.

    Check both the original slug and `agent_` Prefix version (compatible with the fallback logic of _resolve_nanobot_spec_id),
    Avoid inconsistencies between state.spec_id and the actual spec_id in the database.

    If there is a conflict, _2 / _3 / ... suffixes are automatically appended.
    """
    clean_slug = str(slug or "").strip()
    if not clean_slug:
        return clean_slug
    candidates_to_check = [clean_slug]
    if not clean_slug.startswith("agent_"):
        candidates_to_check.append(f"agent_{clean_slug}")

    async def _exists(candidate: str) -> bool:
        try:
            existing = await db["agent_specs"].find_one({"spec_id": candidate}, {"spec_id": 1})
            return existing is not None
        except Exception:
            return False

    # Check if original slug and agent_ prefix versions conflict
    if not (await _exists(clean_slug)) and not (await _exists(f"agent_{clean_slug}")):
        return clean_slug

    counter = 2
    while True:
        new_slug = f"{clean_slug}_{counter}"
        if not (await _exists(new_slug)) and not (await _exists(f"agent_{new_slug}")):
            logger.info(
                "[AgentBuilder][SlugUniqueness] slug '%s' Already exists (or agent_ prefix version conflicts), change to '%s'",
                clean_slug, new_slug,
            )
            return new_slug
        counter += 1
        if counter > 100:  # defensive cover
            return new_slug


async def node_requirement_intake(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Requirements exploration node.

    Call prepare_agent_requirement_intake to structure user requirements.
    """
    await _emit_event(event_callback, "step", "Requirements exploration")
    await _emit_event(event_callback, "progress", "Analyzing requirements and generating default solutions")

    system_prompt = """You are a financial product expert on the TradingAgentsCN platform + Agent Build Consultants.

Current stage: Requirements exploration. The user wants to create an analysis agent.

Your task:
1. As a financial product expert, provide a draft of the default plan based on the user s description (to attract new ideas)
2. The prepare_agent_requirement_intake tool must be called to structure the requirements
3. Don t make a questionnaire, ask no more than 1 key question at a time
4. Default A shares, structured Markdown report, research analysis only, including risk warnings

You must call the prepare_agent_requirement_intake tool."""

    final_text, tool_events, tool_results = await _run_node_llm(
        state, system_prompt, tool_registry, llm_client,
        required_tool_name="prepare_agent_requirement_intake",
        include_inspect_tools=False,
        event_callback=event_callback,
        on_stream=on_stream,
    )

    state["final_response"] = final_text
    state["tool_events"] = tool_events
    state["current_node"] = "requirement_intake"

    # Save the original user request for subsequent node force-call use
    state["original_user_request"] = state.get("user_message", "")

    # Extract tool results
    intake_result = _extract_json_from_result(
        tool_results.get("prepare_agent_requirement_intake", "{}")
    )
    if intake_result:
        proposed_plan = intake_result.get("proposed_plan", {}) or {}
        critical_questions = intake_result.get("critical_questions", []) or []
        can_proceed = intake_result.get("can_proceed_to_confirmation", False)

        # Extract key information from proposed_plan
        responsibility = str(proposed_plan.get("single_responsibility") or "").strip()
        # Prefer proposed_agent_name (short Agent name, such as"Multi-dimensional valuation analysis assistant") , 
        # Instead of describing the entire responsibility description (e.g."Perform multi-dimensional valuation analysis on A-share listed companies and output structured reports") as name
        proposed_name = str(proposed_plan.get("proposed_agent_name") or "").strip()
        proposed_slug = str(proposed_plan.get("proposed_agent_slug") or "").strip()
        # 🔑 Key tracking log: Chinese and English names generated by LLM slug
        logger.info(
            "[Intake][NameGen] LLM generate: proposed_name=%r proposed_slug=%r responsibility=%r "
            "can_proceed=%s critical_questions=%d",
            proposed_name, proposed_slug, responsibility[:80], can_proceed, len(critical_questions),
        )
        if responsibility and responsibility != " (To be confirmed)":
            state["requirement_summary"] = responsibility
            # spec_name Use a short name first, if not, use the first 15 words of the job description
            state["spec_name"] = proposed_name or (responsibility[:15] + ("…" if len(responsibility) > 15 else ""))
        else:
            # Responsibilities also to be confirmed: use short name or first 15 words of original request
            state["spec_name"] = proposed_name or state.get("original_user_request", "")[:15]
            state["requirement_summary"] = state.get("original_user_request", "")

        # 🔑 Key: don't set state.spec_id here!
        # Reason: state.spec_id will be passed to the front end through thread_context, and the front end applyThreadContext will immediately
        # use it GET /api/agent-workshop/specs/{spec_id}, But spec has not been created yet (it will be
        # node_generate_candidate_agent Call the generate_confirmed_candidate_agent tool before writing the library),
        # Resulting in 404. Therefore, only the slug is saved to proposed_plan here, and _build_force_call_params will be changed from
        # proposed_plan.proposed_agent_slug Extract and pass to tool as agent_id.
        # state.spec_id It is set after the tool successfully writes the library in node_generate_candidate_agent.
        if proposed_slug:
            # 🔑 Check slug uniqueness (also check agent_ prefix version to avoid conflict with _resolve_nanobot_spec_id)
            try:
                from app.core.database import get_mongo_db
                db = get_mongo_db()
                proposed_slug = await _ensure_slug_uniqueness(db, proposed_slug)
            except Exception as e:
                logger.warning("[AgentBuilder][SlugUniqueness] Check failed, use original slug: %s", e)
            proposed_plan["proposed_agent_slug"] = proposed_slug
        elif not (proposed_plan.get("proposed_agent_slug") or "").strip():
            # Bottom line: Generating from spec_name is simple slug
            from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import _fallback_slug_from_name
            fallback_slug = _fallback_slug_from_name(
                state.get("spec_name", ""),
                state.get("original_user_request", ""),
                responsibility
            )
            # The slug must also be checked for uniqueness (including the agent_ prefixed version)
            try:
                from app.core.database import get_mongo_db
                db = get_mongo_db()
                fallback_slug = await _ensure_slug_uniqueness(db, fallback_slug)
            except Exception:
                pass
            proposed_plan["proposed_agent_slug"] = fallback_slug

        # pending_question from critical_questions
        if critical_questions and not can_proceed:
            state["pending_question"] = str(critical_questions[0].get("question", ""))
        else:
            state["pending_question"] = ""

        # stage
        state["stage"] = "draft_preparing" if can_proceed else "exploring"

        # Save proposed_plan for subsequent nodes to use (including finalized proposed_agent_slug)
        state["proposed_plan"] = proposed_plan

        # 🔑 Key tracking log: proposed slug (note that spec_id should be empty at this moment and will not be set until the tool writes the library)
        logger.info(
            "[Intake][Final] state.spec_id=%r proposed_slug=%r state.spec_name=%r stage=%s "
            "(spec_id Will be set after generate_confirmed_candidate_agent is written to the library)",
            state.get("spec_id", ""),
            proposed_plan.get("proposed_agent_slug", ""),
            state.get("spec_name", ""),
            state.get("stage", ""),
        )

    await _emit_event(event_callback, "step", "Requirements exploration completed")
    return state


async def node_wait_intake_confirmation(
    state: AgentBuilderState,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Wait for the user to confirm the demand direction.

    wait The node does not call LLM, it only does status marking.
    """
    state["current_node"] = "wait_intake_confirmation"
    state["awaiting_user"] = True
    state["stage"] = "exploring"

    # When the intention cannot be recognized, a clarification prompt is output to avoid repeating the previous round of content.
    if state.get("clarification_needed"):
        pending_q = state.get("pending_question", "")
        clarify = (
            "Sorry, I didn t quite understand what you meant.\n\n"
            + (f"We are confirming this issue:**{pending_q}**\n\n" if pending_q else "")
            + "You can:\n"
            "- Reply Confirm and Yes and proceed with the current plan.\n"
            "- Just say what you want to adjust or add.\n"
            "- Reply Cancel to start again\n\n"
            "Please be more specific so I can continue to help you move forward."
        )
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _invoke_stream(on_stream, clarify)
        return state

    if state.get("pending_question"):
        await _emit_event(event_callback, "progress", f"To be confirmed:{state['pending_question']}")

    return state


async def node_requirement_confirmation(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Requirement confirmation node.

    Call prepare_agent_generation_confirmation to generate a confirmation.
    Pure business confirmation, does not involve capability inventory, gap analysis, or solution presentation.
    """
    await _emit_event(event_callback, "step", "Requirements confirmation")
    await _emit_event(event_callback, "progress", "Generating confirmation draft")

    system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: Requirements confirmation. The user has confirmed the basic direction and now needs to confirm the responsibility boundaries and output form.

Confirmed requirements:
- Name:{state.get('spec_name', 'Unnamed')}
- Summary:{state.get('requirement_summary', 'None')}

Your task:
1. Call prepare_agent_generation_confirmation to generate a confirmation draft
2. The confirmation draft only contains: scope of responsibilities, output form, non-objectives
3. Do not present tool candidates, capability inventory, gap analysis, and solutions at this stage
4. After the user is confirmed, the next step is to take a capability inventory

You must call the prepare_agent_generation_confirmation tool."""

    final_text, tool_events, tool_results = await _run_node_llm(
        state, system_prompt, tool_registry, llm_client,
        required_tool_name="prepare_agent_generation_confirmation",
        include_inspect_tools=False,  # No tool search is required during the confirmation phase
        event_callback=event_callback,
        on_stream=on_stream,
    )

    state["final_response"] = final_text
    state["tool_events"] = tool_events
    state["current_node"] = "requirement_confirmation"
    state["stage"] = "draft_preparing"

    # Extract tool results
    conf_result = _extract_json_from_result(
        tool_results.get("prepare_agent_generation_confirmation", "{}")
    )
    if conf_result:
        state["confirmation_brief"] = conf_result.get("confirmation_brief", {})
        state["pending_question"] = conf_result.get("pending_question", "")
        # 🔑 Don't set state.spec_id here!
        # The agent_id / proposed_agent_id in the confirmation draft is the proposed slug, not the stored spec_id.
        # If state.spec_id is set, it will be passed to the front end through thread_context.
        # The frontend applyThreadContext will immediately GET /api/agent-workshop/specs/{spec_id}, 
        # But at this time, the spec has not been created (the library will not be written until generate_confirmed_candidate_agent), resulting in 404.
        # spec_id It is only set after the tool in node_generate_candidate_agent successfully writes the library.
        # But spec_name can be updated because the frontend is only used to display the name and does not trigger a GET request.
        conf_brief = conf_result.get("confirmation_brief", {}) or {}
        spec_name = (
            conf_result.get("spec_name")
            or conf_brief.get("agent_name")
            or conf_brief.get("proposed_agent_name")
            or state.get("spec_name", "")
        )
        if spec_name:
            state["spec_name"] = spec_name

    await _emit_event(event_callback, "step", "Requirement confirmation completed")
    return state


async def node_wait_requirement_confirmation(
    state: AgentBuilderState,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Wait for user confirmation of requirement boundaries."""
    state["current_node"] = "wait_requirement_confirmation"
    state["awaiting_user"] = True
    state["stage"] = "requirement_confirmation_pending"

    # When the intention cannot be recognized, a clarification prompt is output to avoid repeating the previous round of content.
    if state.get("clarification_needed"):
        pending_q = state.get("pending_question", "")
        clarify = (
            "Sorry, I didn t quite understand what you meant.\n\n"
            + (f"We are confirming:**{pending_q}**\n\n" if pending_q else "")
            + "You can:\n"
            "- Reply Confirm and Okay and I will enter the ability inventory.\n"
            "- Name the boundaries or requirements you would like to adjust\n"
            "- Reply Cancel to start again\n\n"
            "Please be more specific."
        )
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _invoke_stream(on_stream, clarify)
        return state

    if state.get("pending_question"):
        await _emit_event(event_callback, "progress", f"To be confirmed:{state['pending_question']}")

    return state


async def node_gap_analysis(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Gap analysis node.

    Call analyze_agent_workshop_gaps to do real gap analysis.
    """
    await _emit_event(event_callback, "step", "gap analysis")
    await _emit_event(event_callback, "progress", "Scanning the platform s existing capabilities...")

    system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: gap analysis. It is necessary to scan the existing capabilities of the platform and analyze whether it meets the Agent s needs.

Agent Information:
- Name:{state.get('spec_name', 'Unnamed')}
- Requirements:{state.get('requirement_summary', 'None')}

Your task:
1. Call analyze_agent_workshop_gaps to do capability scanning and gap analysis
2. Regardless of whether there are blocking gaps, enter the solution generation
3. Do not generate plans directly at this stage or Agent

You must call the analyze_agent_workshop_gaps tool."""

    # 🔑 periodic progress emitter
    async def _periodic_gap_progress():
        elapsed = 0
        while True:
            await asyncio.sleep(8)
            elapsed += 8
            if elapsed <= 16:
                phase = "Scanning the platform for existing tools and capabilities"
            else:
                phase = "Analyzing capability gaps and making recommendations to fill them"
            await _emit_event(event_callback, "progress", f"{phase} (Already run {elapsed} seconds)...")

    gap_progress_task = asyncio.create_task(_periodic_gap_progress())
    try:
        final_text, tool_events, tool_results = await _run_node_llm(
            state, system_prompt, tool_registry, llm_client,
            required_tool_name="analyze_agent_workshop_gaps",
            include_inspect_tools=False,
            event_callback=event_callback,
            on_stream=on_stream,
        )
    finally:
        gap_progress_task.cancel()
        try:
            await gap_progress_task
        except asyncio.CancelledError:
            pass

    state["final_response"] = final_text
    state["tool_events"] = tool_events
    state["current_node"] = "gap_analysis"
    state["stage"] = "capability_check"

    # Extract gap report
    gap_result = _extract_json_from_result(
        tool_results.get("analyze_agent_workshop_gaps", "{}")
    )
    if gap_result:
        # gap_result Is the outer wrapper:{status, session_id, spec_id, gap_report, summary}
        # state["gap_report"] The real gap_report of the inner layer (including blocking_gaps, suggested_tools, etc.) should be saved
        inner_gap_report = gap_result.get("gap_report", {}) or {}
        # Bottom line: If gap_report is serialized into a string (in theory, the tool layer has been repaired, and it is handled defensively here),
        # Try parsing JSON back into dict.
        if isinstance(inner_gap_report, str) and inner_gap_report.strip().startswith("{"):
            try:
                parsed = json.loads(inner_gap_report)
                if isinstance(parsed, dict):
                    inner_gap_report = parsed
            except json.JSONDecodeError:
                pass
        if not isinstance(inner_gap_report, dict):
            inner_gap_report = {}
        state["gap_report"] = inner_gap_report

        blocking_gaps_count = len(inner_gap_report.get("blocking_gaps", []) or [])
        logger.info(
            "[GapAnalysis][Output] gap_report_keys=%s blocking_gaps=%d existing_tools=%d suggested_tools=%d",
            list(inner_gap_report.keys()),
            blocking_gaps_count,
            len(inner_gap_report.get("existing_tools", []) or []),
            len(inner_gap_report.get("suggested_tools", []) or []),
        )

        # Also save the session_id (analyze_agent_workshop_gaps may have created the session automatically)
        if gap_result.get("session_id") and not state.get("workshop_session_id"):
            state["workshop_session_id"] = gap_result["session_id"]
            logger.info("[GapAnalysis] save workshop_session_id=%s", state["workshop_session_id"])
    else:
        logger.warning(
            "[GapAnalysis][EmptyResult] tool_results keys=%s raw_len=%d",
            list(tool_results.keys()),
            len(tool_results.get("analyze_agent_workshop_gaps", "") or ""),
        )

    await _emit_event(event_callback, "step", "Gap analysis completed")

    # 🔑 Build a structured gap report display
    if state.get("gap_report"):
        gap = state["gap_report"]
        existing_tools = gap.get("existing_tools", []) or []
        blocking_gaps = gap.get("blocking_gaps", []) or []
        suggested_tools = gap.get("suggested_tools", []) or []

        gap_display = f"\n\n---\n\n## Gap Analysis Report\n\n"
        gap_display += f"**Existing tools:** {len(existing_tools)} a\n"
        if existing_tools:
            tool_names = [t.get("name", t.get("tool_id", str(t))) if isinstance(t, dict) else str(t) for t in existing_tools[:8]]
            gap_display += f"  {', '.join(tool_names)}\n"

        gap_display += f"\n**Blocking gap:** {len(blocking_gaps)} a\n"
        if blocking_gaps:
            for bg in blocking_gaps[:5]:
                gap_display += f"  - {bg if isinstance(bg, str) else bg.get('description', str(bg))}\n"

        gap_display += f"\n**Recommended completion tools:** {len(suggested_tools)} a\n"
        if suggested_tools:
            for st in suggested_tools[:5]:
                gap_display += f"  - {st if isinstance(st, str) else st.get('name', str(st))}\n"

        gap_display += f"\n{'✅ There are no blocking gaps and solutions can be generated directly' if not blocking_gaps else '⚠️ There is a blocking gap and it will be dealt with in the plan'}\n"

        state["final_response"] = (state.get("final_response") or "") + gap_display
        await _stream_chunked(gap_display, on_stream)

    return state


async def node_plan_generation(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Plan generation node.

    Call propose_agent_build_plans to generate structured candidate plans.
    This is the only place where plans can be generated, LLM cannot generate plans verbally.
    """
    await _emit_event(event_callback, "step", "Solution generation")
    await _emit_event(event_callback, "progress", "Generating candidates...")

    system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: plan generation. The gap analysis is complete and now it is time to generate candidates.

Agent Information:
- Name:{state.get('spec_name', 'Unnamed')}
- Gap Report:{json.dumps(state.get('gap_report', {}), ensure_ascii=False)}

Your task:
1. Call the propose_agent_build_plans tool to generate structured candidate plans
2. After the tool returns, it reports to the user**Full display of all candidates**, The format is as follows:

   **Candidates**

   Option A:[Scheme name] (Recommended)
   - Features:...
   - Advantages:...
   - Applicable scenarios:...
   - Data coverage: Which data is directly supported by tools, which is obtained through inference, and which is missing
   - Implementation feasibility: can it be achieved, what are the difficulties, and what additional development is needed

   Option B:[Scheme name]
   - Features:...
   - Advantages:...
   - Applicable scenarios:...
   - Data coverage:...
   - Implementation feasibility:...

   Plan C:[Scheme name]
   - Features:...
   - Advantages:...
   - Applicable scenarios:...
   - Data coverage:...
   - Implementation feasibility:...

   Please choose a plan (reply the plan letters such as A , B and C , or reply Recommended to proceed with the recommended plan).

3. After the user selects a plan, the system will call generate_confirmed_candidate_agent

Important rules:
- You must display all options for users to choose and cannot make decisions for users.
- can t say"We chose the recommended plan"or"I will proceed according to the recommended plan"Such words
- Give users a clear choice
- Each solution must truthfully demonstrate the data coverage and implementation feasibility, and cannot just talk about the advantages without mentioning the difficulties.
- For solutions with data gaps, it must be clearly stated which analysis dimensions cannot be achieved or need to be downgraded.
- Chinese reply

You must call the propose_agent_build_plans tool. Plans cannot be generated verbally."""

    # 🔑 periodic progress emitter
    async def _periodic_plan_progress():
        elapsed = 0
        while True:
            await asyncio.sleep(8)
            elapsed += 8
            if elapsed <= 16:
                phase = "Candidates are being designed based on gap analysis results"
            else:
                phase = "Evaluating program priorities and recommendation ranking"
            await _emit_event(event_callback, "progress", f"{phase} (Already run {elapsed} seconds)...")

    plan_progress_task = asyncio.create_task(_periodic_plan_progress())
    try:
        final_text, tool_events, tool_results = await _run_node_llm(
            state, system_prompt, tool_registry, llm_client,
            required_tool_name="propose_agent_build_plans",
            include_inspect_tools=False,
            event_callback=event_callback,
            on_stream=on_stream,
        )
    finally:
        plan_progress_task.cancel()
        try:
            await plan_progress_task
        except asyncio.CancelledError:
            pass

    state["final_response"] = final_text
    state["tool_events"] = tool_events
    state["current_node"] = "plan_generation"
    state["stage"] = "plan_selection_pending"

    # Extract solution results
    plan_result = _extract_json_from_result(
        tool_results.get("propose_agent_build_plans", "{}")
    )
    if plan_result:
        state["candidate_plans"] = plan_result.get("candidate_plans", [])
        state["pending_options"] = plan_result.get("pending_options", [])
        state["recommended_plan_id"] = plan_result.get("recommended_plan_id", "")
        state["pending_question"] = plan_result.get("pending_question", "")

    logger.info(
        "[ProposePlans][Output] plan_count=%d, pending_options=%d, recommended=%s",
        len(state.get("candidate_plans", [])),
        len(state.get("pending_options", [])),
        state.get("recommended_plan_id", ""),
    )

    await _emit_event(event_callback, "step", "Plan generation completed")
    return state


async def node_wait_plan_selection(
    state: AgentBuilderState,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Wait for the user to select a plan."""
    state["current_node"] = "wait_plan_selection"
    state["awaiting_user"] = True
    state["stage"] = "plan_selection_pending"

    # When the intention cannot be recognized, a clarification prompt is output to avoid repeating the previous round of plan lists.
    if state.get("clarification_needed"):
        options = state.get("pending_options", []) or []
        lines = []
        for opt in options:
            idx = opt.get("index", "")
            label = opt.get("name", opt.get("id", ""))
            rec = " (Recommended)" if opt.get("recommended") else ""
            lines.append(f"- Plan {idx}: {label}{rec}")
        options_text = "\n".join(lines) if lines else ""
        clarify = (
            "Sorry, I don t quite understand which option you chose.\n\n"
            + (f"The options are as follows:\n{options_text}\n\n" if options_text else "")
            + "Please reply directly with the plan number or letter (such as Plan A , B , Second ),"
            "Or reply Recommend and proceed with the recommended plan."
        )
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _invoke_stream(on_stream, clarify)
        return state

    if state.get("pending_question"):
        await _emit_event(event_callback, "progress", f"To be selected:{state['pending_question']}")

    # 🔑 Ensure that the list of solutions is displayed to the user: if there is no solution option in final_response, add one
    options = state.get("pending_options", []) or []
    if options:
        current_response = str(state.get("final_response", "") or "")
        # Check whether final_response already contains scheme options (contains at least two scheme identifiers)
        has_options = (
            "Plan A" in current_response or "Plan A" in current_response
            or "Plan 1" in current_response or "Plan 1" in current_response
            or "Recommended" in current_response
        )
        if not has_options:
            lines = ["", "---", "**Please select a plan:**", ""]
            for opt in options:
                idx = opt.get("index", "")
                label = opt.get("name", opt.get("id", ""))
                desc = opt.get("description", opt.get("summary", ""))
                rec = " (Recommended)" if opt.get("recommended") else ""
                lines.append(f"Plan{idx}: {label}{rec}")
                if desc:
                    lines.append(f"  {str(desc)[:120]}")
                lines.append("")
            lines.append("Please reply with the letter of the plan (such as A or B ), or reply with Recommend to proceed with the recommended plan.")
            options_block = "\n".join(lines)
            state["final_response"] = current_response + options_block
            await _invoke_stream(on_stream, options_block)

    return state


async def node_generate_candidate_agent(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Generate Agent nodes.

    Call generate_confirmed_candidate_agent to generate Agent configuration, prompt, and binding.
    """
    await _emit_event(event_callback, "step", "generate Agent")
    await _emit_event(event_callback, "progress", "Writing configuration and Prompt")
    # 🔑 Clear old errors to prevent error_recovery from overlaying irrelevant historical errors.
    state["errors"] = []

    # 🔑 Published version decision: After the user confirms the creation of a new version, automatically iterate to create a new draft session
    # Keep the previous gap report and scheme selection, just create a new draft environment to write the configuration
    if state.get("build_status") == "pending_iteration_decision":
        version_id = _sanitize_version_id(state.get("version_id", ""))
        if version_id:
            try:
                from app.core.database import get_mongo_db
                from app.pro.services.agent_workshop_service import AgentWorkshopService
                db = get_mongo_db()
                iterate_result = await AgentWorkshopService(db=db).iterate_version(
                    version_id,
                    feedback="Create iterative versions based on new gap analysis",
                )
                new_session_id = str(iterate_result.get("session_id") or "").strip()
                new_version_id = _sanitize_version_id(iterate_result.get("version_id", ""))
                new_spec_id = str(iterate_result.get("spec_id") or "").strip()
                if new_session_id:
                    state["workshop_session_id"] = new_session_id
                if new_version_id:
                    state["version_id"] = new_version_id
                if new_spec_id:
                    state["spec_id"] = new_spec_id
                # Clear pending_iteration_decision to allow subsequent generation logic to execute normally
                state["build_status"] = ""
                logger.info(
                    "[GenerateAgent][AutoIterate] New draft version created session_id=%s version_id=%s spec_id=%s",
                    new_session_id, new_version_id, new_spec_id,
                )
                await _emit_event(event_callback, "progress", "New draft version created, continue building Agent")
            except Exception as iterate_exc:
                logger.error("[GenerateAgent][AutoIterate] iterate failed: %s", iterate_exc, exc_info=True)
                state["build_status"] = "failed"
                state["errors"] = [{
                    "node": "generate_candidate_agent",
                    "error": f"Failed to create new version: {iterate_exc}",
                    "stage": "iterating",
                }]
                state["final_response"] = f"Failed to create new version:{iterate_exc}"
                return state
        else:
            logger.warning("[GenerateAgent][AutoIterate] version_id Empty, unable to iterate")
            state["build_status"] = "failed"
            state["errors"] = [{
                "node": "generate_candidate_agent",
                "error": "version_id Empty, cannot create new version",
                "stage": "iterating",
            }]
            state["final_response"] = "Unable to create new version: Missing published version ID"
            return state

    # The modification of state by the conditional function will not be persisted to the node. Let's re-analyze it here. selected_plan_id
    if not state.get("selected_plan_id"):
        from core.embedded_nanobot.workflows.agent_builder_conditions import _resolve_plan_selection
        msg = state.get("user_message", "")
        pending_options = state.get("pending_options", []) or []
        selected_id, reason = _resolve_plan_selection(pending_options, msg)
        if selected_id:
            state["selected_plan_id"] = selected_id
            logger.info("[GenerateAgent][ResolvedPlan] selected_plan_id=%s reason=%s", selected_id, reason)
        elif _is_confirm_like(msg) and state.get("recommended_plan_id"):
            state["selected_plan_id"] = state["recommended_plan_id"]
            logger.info("[GenerateAgent][ResolvedPlan] using recommended=%s", state["recommended_plan_id"])

    system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: Generate Agent. The user has selected a plan and now needs to generate an Agent.

Agent Information:
- Name:{state.get('spec_name', 'Unnamed')}
- Plan chosen:{state.get('selected_plan_id', 'Not selected')}
- Candidates:{json.dumps(state.get('candidate_plans', []), ensure_ascii=False)[:500]}
- Gap Report:{json.dumps(state.get('gap_report', {}), ensure_ascii=False)[:500]}

Your task:
1. Call generate_confirmed_candidate_agent to generate Agent
2. Report generation results (configuration, tool binding, prompt)
3. If it is a quick plan, indicate the accepted gap

You must call the generate_confirmed_candidate_agent tool."""

    final_text, tool_events, tool_results = await _run_node_llm(
        state, system_prompt, tool_registry, llm_client,
        required_tool_name="generate_confirmed_candidate_agent",
        include_inspect_tools=False,
        event_callback=event_callback,
        on_stream=on_stream,
    )

    # 🔍 Debug log: View the keys of tool_results and the original values of generate_confirmed_candidate_agent
    logger.info(
        "[GenerateAgent][Debug] tool_results keys=%s gen_tool_raw=%s",
        list(tool_results.keys()) if isinstance(tool_results, dict) else type(tool_results).__name__,
        (tool_results.get("generate_confirmed_candidate_agent", "")[:500] if isinstance(tool_results, dict) else "N/A"),
    )

    state["final_response"] = final_text
    state["tool_events"] = tool_events
    state["current_node"] = "generate_candidate_agent"
    state["stage"] = "generating"

    # Extract generated results
    gen_result = _extract_json_from_result(
        tool_results.get("generate_confirmed_candidate_agent", "{}")
    )
    # 🔍 Debug log: see the actual structure of gen_result and blocked_code
    logger.info(
        "[GenerateAgent][Debug] gen_result type=%s status=%s stage=%s blocked_code=%s nested_blocked_code=%s keys=%s",
        type(gen_result).__name__,
        gen_result.get("status") if isinstance(gen_result, dict) else "N/A",
        gen_result.get("stage") if isinstance(gen_result, dict) else "N/A",
        gen_result.get("blocked_code") if isinstance(gen_result, dict) else "N/A",
        (gen_result.get("result", {}).get("blocked_code") if isinstance(gen_result, dict) and isinstance(gen_result.get("result"), dict) else "N/A"),
        list(gen_result.keys()) if isinstance(gen_result, dict) else "N/A",
    )
    if gen_result:
        state["generated_agent"] = gen_result

        # workshop_session_id Possibly in multiple locations
        workshop_session_id = (
            gen_result.get("workshop_session_id")
            or gen_result.get("session_id")
            or ""
        )
        if not workshop_session_id:
            # Extract from nested governance_boundary.workshop_governance.session_id
            governance = gen_result.get("governance_boundary", {}) or {}
            workshop_governance = governance.get("workshop_governance", {}) or {}
            workshop_session_id = workshop_governance.get("session_id", "")
        if not workshop_session_id:
            # Extracted from steps.workshop_draft.session_id
            steps = gen_result.get("steps", {}) or {}
            workshop_draft = steps.get("workshop_draft", {}) or {}
            workshop_session_id = workshop_draft.get("session_id", "")
        state["workshop_session_id"] = workshop_session_id

        # 🔑 Synchronize spec_id from tool results (_resolve_nanobot_spec_id may return a different value than in state)
        # generate_confirmed_candidate_agent There are two situations when the tool returns a structure:
        # 1. Success:{"status": "ok", "spec_id": "...", "session_id": "...", ...}
        # 2. Failed/blocked by phase_guard:{"status": "error", "stage": "workshop_version",
        #     "result": {"status": "blocked", "spec_id": "...", "current_version_id": "...", ...}}
        # Therefore spec_id may appear at the top level,gen_result["result"] or in nested governance.
        actual_spec_id = (
            gen_result.get("spec_id")
            or gen_result.get("agent_id")
            or ""
        )
        if not actual_spec_id:
            # 🔑 Key: extract from result nesting layer (spec_id is here when phase_guard blocks)
            nested_result = gen_result.get("result", {})
            if isinstance(nested_result, dict):
                actual_spec_id = (
                    nested_result.get("spec_id")
                    or nested_result.get("agent_id")
                    or ""
                )
        if not actual_spec_id:
            # Extract from nested steps.workshop_draft
            steps = gen_result.get("steps", {}) or {}
            workshop_draft = steps.get("workshop_draft", {}) or {}
            actual_spec_id = workshop_draft.get("spec_id") or workshop_draft.get("agent_id") or ""
        if not actual_spec_id:
            governance = gen_result.get("governance_boundary", {}) or {}
            workshop_governance = governance.get("workshop_governance", {}) or {}
            actual_spec_id = workshop_governance.get("spec_id") or ""
        if actual_spec_id and actual_spec_id != state.get("spec_id", ""):
            old_spec_id = state.get("spec_id", "")
            logger.info(
                "[GenerateAgent][SpecIdSync] state.spec_id '%s' → actual '%s' (Synchronize results from tools)",
                old_spec_id, actual_spec_id,
            )
            state["spec_id"] = actual_spec_id

        # version_id Also in multiple locations
        version_id = gen_result.get("version_id", "")
        if not version_id:
            governance = gen_result.get("governance_boundary", {}) or {}
            workshop_governance = governance.get("workshop_governance", {}) or {}
            version_id = workshop_governance.get("version_id", "")
        if not version_id:
            steps = gen_result.get("steps", {}) or {}
            workshop_version = steps.get("workshop_version", {}) or {}
            version_obj = workshop_version.get("version", {})
            if isinstance(version_obj, dict):
                version_id = version_obj.get("version_id", "")
            elif isinstance(version_obj, str):
                version_id = version_obj
        # Defensive cleaning: version_id may be of AgentVersion object str repr
        #  (json.dumps default=str Convert Pydantic model to string)
        version_id = _sanitize_version_id(version_id)
        state["version_id"] = version_id

        # build_status
        if gen_result.get("status") == "ok":
            state["build_status"] = "built" if version_id else "ready"
        else:
            # 🔑 Check if version_already_in_progress of phase_guard is blocking
            # This situation is not a real error——The version already exists, just reuse it and continue testing.
            nested_result = gen_result.get("result", {}) if isinstance(gen_result.get("result"), dict) else {}
            blocked_code = (
                gen_result.get("blocked_code")
                or nested_result.get("blocked_code")
                or ""
            )
            is_version_in_progress = blocked_code == "version_already_in_progress"
            is_active_requires_iteration = blocked_code == "active_version_requires_iteration"

            if is_version_in_progress:
                # The version already exists. Extract the existing version information and enter the testing phase directly.
                existing_version_id = (
                    gen_result.get("current_version_id")
                    or nested_result.get("current_version_id")
                    or ""
                )
                existing_session_id = (
                    gen_result.get("session_id")
                    or nested_result.get("session_id")
                    or workshop_session_id
                    or ""
                )
                existing_spec_id = (
                    gen_result.get("spec_id")
                    or nested_result.get("spec_id")
                    or state.get("spec_id")
                    or ""
                )
                if existing_version_id:
                    state["version_id"] = _sanitize_version_id(existing_version_id)
                if existing_session_id:
                    state["workshop_session_id"] = existing_session_id
                if existing_spec_id:
                    state["spec_id"] = existing_spec_id
                state["build_status"] = "built"
                logger.info(
                    "[GenerateAgent][PhaseGuardBypass] version_already_in_progress → "
                    "Reuse existing versions version_id=%s session_id=%s spec_id=%s, Go directly to the test",
                    state.get("version_id"),
                    state.get("workshop_session_id"),
                    state.get("spec_id"),
                )
                # Do not add errors and let the route enter normally. wait_test_request
            elif is_active_requires_iteration:
                # The published version cannot be directly overwritten, and the user is prompted whether to create a new version (iterate)
                existing_version_id = (
                    nested_result.get("version_id")
                    or gen_result.get("version_id")
                    or ""
                )
                existing_spec_id = (
                    nested_result.get("spec_id")
                    or gen_result.get("spec_id")
                    or state.get("spec_id")
                    or ""
                )
                if existing_version_id:
                    state["version_id"] = _sanitize_version_id(existing_version_id)
                if existing_spec_id:
                    state["spec_id"] = existing_spec_id
                state["build_status"] = "pending_iteration_decision"
                state["awaiting_user"] = True
                state["decision_context"] = {
                    "type": "iterate_or_cancel",
                    "existing_version_id": existing_version_id,
                    "spec_id": existing_spec_id,
                    "message": nested_result.get("message", "") or gen_result.get("message", ""),
                    "next_action": nested_result.get("next_action", "") or gen_result.get("next_action", ""),
                }
                state["final_response"] = (
                    f"Detected that the Agent already has a released version **{existing_version_id}**. \n\n"
                    f"The published version cannot be directly overwritten, and a new iteration needs to be created based on this version.\n\n"
                    f"Please select:\n"
                    f"- Reply Confirm : Initiate an iteration based on the released version and continue optimization in a new session\n"
                    f"- Reply Cancel : end the current process"
                )
                logger.info(
                    "[GenerateAgent][PhaseGuardBypass] active_version_requires_iteration → "
                    "Wait for user decision version_id=%s spec_id=%s",
                    state.get("version_id"),
                    state.get("spec_id"),
                )
                # Without adding an error, let the route go to wait_test_request to show decision options
            else:
                state["build_status"] = "failed"
                err_msg = gen_result.get("message", "")
                err_stage = gen_result.get("stage", "")
                err_result = gen_result.get("result", {})
                # Both string and dict forms are retained to facilitate node_error_recovery processing.
                error_entry = {
                    "node": "generate_candidate_agent",
                    "error": err_msg or f"stage={err_stage} result={err_result}" or "Build failed",
                    "stage": err_stage,
                    "message": err_msg,
                }
                state["errors"] = state.get("errors", []) + [error_entry]

        logger.info(
            "[GenerateAgent][Result] status=%s session_id=%s version_id=%s build_status=%s "
            "stage=%s message=%s result_keys=%s state.spec_id=%s",
            gen_result.get("status", ""),
            workshop_session_id,
            version_id,
            state["build_status"],
            gen_result.get("stage", ""),
            gen_result.get("message", "")[:200],
            list(gen_result.get("result", {}).keys()) if isinstance(gen_result.get("result"), dict) else "N/A",
            state.get("spec_id", ""),
        )

    await _emit_event(event_callback, "step", "Agent Generation completed")
    return state


async def node_build_or_ready(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Build/prepare test node.

    Determine whether you need to build a Workshop version based on your scenario.
    quick Scheme skips build.
    """
    state["current_node"] = "build_or_ready"
    state["stage"] = "building"

    if state.get("selected_plan_id") == "quick":
        state["build_status"] = "skipped"
        await _emit_event(event_callback, "progress", "Simplified version plan, skip version building")
        return state

    # If the generate phase has automatically built the version (auto_build_workshop_version=True) , 
    # Enter wait_test_request directly, no need to adjust again build_agent_workshop_version
    if state.get("build_status") == "built" and state.get("version_id"):
        await _emit_event(event_callback, "progress", "Versions have been automatically built during the build phase, skipping repeated builds")
        return state

    # Unable to build without workshop_session_id (generate failed or not synchronized)
    workshop_session_id = state.get("workshop_session_id", "")
    if not workshop_session_id:
        state["build_status"] = "skipped_no_session"
        state["stage"] = "skipped"
        logger.warning("[BuildOrReady] No workshop_session_id, skip building")
        await _emit_event(event_callback, "progress", "No Workshop session, skip version build")
        return state

    await _emit_event(event_callback, "step", "build version")
    await _emit_event(event_callback, "progress", "Building Workshop version")

    system_prompt = """You are a financial product expert on the TradingAgentsCN platform.

Current stage: build version. The Agent has been generated and now it is time to build the Workshop version.

Your task:
1. Call build_agent_workshop_version build version
2. Report build results

You must call the build_agent_workshop_version tool."""

    # If the user chooses"Overwrite old version"Then re-enter and inform LLM to transfer overwrite_existing=True
    if state.get("build_status") == "pending_user_decision":
        decision_ctx = state.get("decision_context", {}) or {}
        old_version_id = decision_ctx.get("current_version_id", "unknown")
        session_id = decision_ctx.get("session_id", "") or state.get("workshop_session_id", "")
        system_prompt += f"""

⚠️ The user has confirmed to**Overwrite old version {old_version_id}** (deleted and then rebuilt).
You must call build_agent_workshop_version, passing in overwrite_existing=True: 
  build_agent_workshop_version(session_id="{session_id}", overwrite_existing=True)"""

    final_text, tool_events, tool_results = await _run_node_llm(
        state, system_prompt, tool_registry, llm_client,
        required_tool_name="build_agent_workshop_version",
        include_inspect_tools=False,
        event_callback=event_callback,
        on_stream=on_stream,
    )

    state["final_response"] = final_text
    state["tool_events"] = tool_events
    state["stage"] = "building"

    build_result = _extract_json_from_result(
        tool_results.get("build_agent_workshop_version", "{}")
    )
    # 🔍 Diagnostic log: print full parsing results (truncated to 500 characters)
    _raw_tool_result = tool_results.get("build_agent_workshop_version", "")
    logger.info(
        "[BuildOrReady][Debug] raw_len=%d | build_result_status=%s | build_result_keys=%s | current_version_id=%s | options_count=%d",
        len(str(_raw_tool_result)),
        build_result.get("status") if build_result else "None",
        list(build_result.keys())[:10] if build_result else [],
        build_result.get("current_version_id", "MISSING") if build_result else "None",
        len(build_result.get("options", [])) if build_result else 0,
    )
    if build_result:
        # version_id May be at top level, summary.version_id or version.version_id
        version_id = build_result.get("version_id", "")
        if not version_id:
            summary = build_result.get("summary", {}) or {}
            version_id = summary.get("version_id", "")
        if not version_id:
            version_obj = build_result.get("version", {})
            if isinstance(version_obj, dict):
                version_id = version_obj.get("version_id", "")
            elif isinstance(version_obj, str):
                version_id = version_obj
        # Defensive cleaning: version_id may be of AgentVersion object str repr
        version_id = _sanitize_version_id(version_id)
        if version_id:
            state["version_id"] = version_id

        # status="ok" Indicates successful build → build_status="built"
        build_status = build_result.get("status")
        if build_status == "ok":
            state["build_status"] = "built"
        elif build_status == "needs_user_decision":
            # The existing version is under testing and users need to decide whether to overwrite or continue.
            state["build_status"] = "pending_user_decision"
            state["awaiting_user"] = True
            state["decision_context"] = {
                "type": "overwrite_or_continue",
                "existing_version": build_result.get("existing_version", {}),
                "current_version_id": build_result.get("current_version_id", ""),
                "session_id": build_result.get("session_id", ""),
                "message": build_result.get("message", ""),
                "options": build_result.get("options", []),
            }
            # Generate user-friendly selection prompts
            existing_info = build_result.get("existing_version", {}) or {}
            old_version_id = build_result.get("current_version_id", "") or "unknown"
            options = build_result.get("options", [])
            option_lines = "\n".join(
                f"- **{opt.get('label', '')}**：{opt.get('description', '')}"
                for opt in options
            )
            state["final_response"] = (
                f"There is currently a version **{old_version_id}** In test/build phase and cannot be overridden directly.\n\n"
                f"Please choose the following actions:\n{option_lines}"
            )
        else:
            state["build_status"] = "failed"
            err_msg = build_result.get("message") or build_result.get("error") or "Build failed"
            state["errors"] = state.get("errors", []) + [{
                "node": "build_or_ready",
                "error": str(err_msg)[:300],
                "stage": "building",
            }]
            logger.warning("[BuildOrReady][Failed] %s", str(err_msg)[:200])

    return state


async def node_wait_test_request(
    state: AgentBuilderState,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Wait for the user to give the test target."""
    state["current_node"] = "wait_test_request"
    state["awaiting_user"] = True
    state["stage"] = "testing"

    # Version conflicts require user decision: show overwrite/continue options
    if state.get("build_status") == "pending_user_decision":
        decision_ctx = state.get("decision_context", {}) or {}
        old_version_id = decision_ctx.get("current_version_id", "unknown")
        options = decision_ctx.get("options", [])
        # 🔍 Diagnostic log
        logger.info(
            "[WaitTest][Debug] pending_user_decision | decision_ctx_keys=%s | current_version_id=%s | options_count=%d | build_status=%s",
            list(decision_ctx.keys()) if decision_ctx else [],
            old_version_id,
            len(options),
            state.get("build_status"),
        )
        option_lines = "\n".join(
            f"- **{opt.get('label', '')}**：{opt.get('description', '')}"
            for opt in options
        )
        state["final_response"] = (
            f"There is currently a version **{old_version_id}** In test/build phase and cannot be overridden directly.\n\n"
            f"Please choose the following actions:\n{option_lines}"
        )
        await _invoke_stream(on_stream, state["final_response"])
        await _emit_event(event_callback, "progress", "Requires user decision-making: overwrite the old version or continue to advance")
        return state

    # Published versions require user decision: whether to create a new version (iterate)
    if state.get("build_status") == "pending_iteration_decision":
        decision_ctx = state.get("decision_context", {}) or {}
        # Read from decision_context first, then read from state.version_id (to ensure availability when restoring across requests)
        existing_version_id = (
            decision_ctx.get("existing_version_id")
            or state.get("version_id", "")
            or "unknown"
        )
        logger.info(
            "[WaitTest][Debug] pending_iteration_decision | existing_version_id=%s | build_status=%s",
            existing_version_id,
            state.get("build_status"),
        )
        state["final_response"] = (
            f"Detected that the Agent already has a released version **{existing_version_id}**. \n\n"
            f"The published version cannot be directly overwritten, and a new iteration needs to be created based on this version.\n\n"
            f"Please select:\n"
            f"- Reply Confirm : Initiate an iteration based on the released version and continue optimization in a new session\n"
            f"- Reply Cancel : end the current process"
        )
        await _invoke_stream(on_stream, state["final_response"])
        await _emit_event(event_callback, "progress", "User decision required: whether to create a new version based on a published version")
        return state

    if state.get("skill_creation_requested"):
        spec_name = state.get("spec_name", "") or "candidate Agent"
        gap_report = state.get("gap_report", {}) or {}
        blocking_gaps = gap_report.get("blocking_gaps", []) or []
        gap_desc = ""
        if blocking_gaps:
            gap_items = []
            for g in blocking_gaps[:3]:
                if isinstance(g, dict):
                    gap_items.append(f"- **{g.get('name', g.get('capability', 'unknown'))}**: {g.get('description', g.get('gap_description', ''))}")
                else:
                    gap_items.append(f"- {g}")
            gap_desc = "\n".join(gap_items)

        skill_msg = (
            f"Got it, you want to fill in the missing tools/skills.\n\n"
        )
        if gap_desc:
            skill_msg += f"Capability gaps currently identified:\n{gap_desc}\n\n"
        skill_msg += (
            f"> **Note**: Skill/The creation of tools requires developers to write code to implement them."
            f"This cannot be done automatically in the current Agent build process.\n\n"
            f"You have two options:\n"
            f"1. **Test in downgrade mode first**: Reply Test or stock symbol (e.g. `600519`) , "
            f"Agent Testing will be done using existing tools and missing capabilities will be noted in the report\n"
            f"2. **Record requirements for subsequent development**: Reply to Record Requirements and I will save the requirements for the missing skill.\n\n"
            f"It is recommended to test the current version first to confirm the output quality of downgrade mode."
        )
        state["final_response"] = skill_msg
        state["skill_creation_requested"] = False
        await _invoke_stream(on_stream, skill_msg)
        await _emit_event(event_callback, "progress", "Skill Create a requirement prompt")
        return state

    if state.get("clarification_needed"):
        spec_name = state.get("spec_name", "") or "candidate Agent"
        clarify = (
            f"Sorry, I don t quite understand what you mean. [{spec_name}] Already ready,"
            f"Need one now**specific stock code**Let s run real data tests.\n\n"
            f"Please reply directly with the 6-digit stock code, for example:\n"
            f"- Kweichow Moutai → `600519`\n"
            f"- Ningde era → `300750`\n"
            f"- China Merchants Bank → `600036`\n\n"
            f"Or reply Skip to go directly to the release evaluation."
        )
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _invoke_stream(on_stream, clarify)
        await _emit_event(event_callback, "progress", "Requires stock code")
        return state

    await _emit_event(event_callback, "progress", "Agent Ready, waiting for test target")

    return state


async def node_iterate_agent_version(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Initiate the next iteration based on the current test/release version and create a new draft version."""
    state["current_node"] = "iterate_agent_version"
    state["awaiting_user"] = False
    state["stage"] = "iterating"
    # 🔑 Clear old errors to prevent error_recovery from overlaying irrelevant historical errors.
    state["errors"] = []

    # 🔑 If version_id is empty, try to check the latest version from the database according to spec_id and fill it in.
    # Scenario: The user opens a new conversation with an existing agent from the workshop management page, or tries again from error_recovery
    version_id = _sanitize_version_id(state.get("version_id", ""))
    if not version_id:
        spec_id = state.get("spec_id", "")
        if spec_id:
            try:
                from app.core.database import get_mongo_db
                db = get_mongo_db()
                latest_version_doc = await db["agent_workshop_versions"].find_one(
                    {"spec_id": spec_id},
                    sort=[("created_at", -1)],
                )
                if latest_version_doc:
                    version_id = str(latest_version_doc.get("version_id") or "").strip()
                    if version_id:
                        state["version_id"] = version_id
                        logger.info(
                            "[IterateAgent][ResolvedVersionId] spec_id=%s → version_id=%s (Complete from database)",
                            spec_id, version_id,
                        )
            except Exception as resolve_exc:
                logger.warning("[IterateAgent][ResolvedVersionId] failed: %s", resolve_exc)

        if not version_id:
            state["final_response"] = (
                "There is currently no iterable version. Please create and test an Agent version first, and then perform iterative optimization.\n"
                "You can reply Cancel to end the current process, or describe new requirements and recreate the Agent."
            )
            state["current_node"] = "error_recovery"
            state["stage"] = "error_recovery"
            state["awaiting_user"] = True
            state["errors"] = [{"node": "iterate_agent_version", "error": "version_id Empty, unable to iterate"}]
            return state

    system_prompt = """You are the iteration assistant of the Agent workshop version of the TradingAgentsCN platform, and you are also a senior financial product expert.

Current stage: Users request to upgrade/modify the tested or released Agent.

Your task:
1. Call iterate_agent_workshop_version to create the next iteration draft version based on the current version_id
2. After the tool returns, output a copy to the user**Professional iteration analysis report**, The format is as follows:

   **Iterative analysis report**

   1. Problems with the current Agent
    (Combine the evaluation results and test performance to point out specific issues, do not describe them in general terms)

   2. The direction of this optimization
    (Explain what aspects should be optimized and why these optimizations are necessary)

   3. Expected results after optimization
    (Describe the aspects in which Agent will be improved after optimization)

   4. Key decisions that require user confirmation
    (If there are any points that require further clarification from the user, list them for the user to confirm)

3. Finally, guide users to supplement or confirm their upgrade requirements.

Important rules:
- This is iterative optimization, not redesign. Analyze the problem based on the evaluation results of existing Agents
- Replies should be professional and specific, citing assessment scores and specific questions, rather than speaking in generalities.
- don t say"I have prepared a draft optimization plan for you"This kind of thing should be said"Based on the last round of evaluation, I found the following issues..."
- Chinese reply

You must call the iterate_agent_workshop_version tool."""

    final_text, tool_events, tool_results = await _run_node_llm(
        state,
        system_prompt,
        tool_registry,
        llm_client,
        required_tool_name="iterate_agent_workshop_version",
        include_inspect_tools=False,
        event_callback=event_callback,
        on_stream=on_stream,
    )

    state["tool_events"] = tool_events
    result = _extract_json_from_result(tool_results.get("iterate_agent_workshop_version", "{}"))
    if result and result.get("status") == "ok":
        new_session_id = str(result.get("session_id") or "").strip()
        new_spec_id = str(result.get("spec_id") or "").strip()
        new_version_id = _sanitize_version_id(result.get("version_id", ""))
        source_version_id = _sanitize_version_id(result.get("source_version_id", ""))
        if new_session_id:
            state["workshop_session_id"] = new_session_id
        if new_spec_id:
            state["spec_id"] = new_spec_id
        if new_version_id:
            state["version_id"] = new_version_id
            state["build_status"] = "draft"
        if source_version_id:
            state["source_version_id"] = source_version_id
        ai_message = str(result.get("ai_message") or "").strip()
        if ai_message:
            final_text = ai_message
        state["final_response"] = final_text
        state["current_node"] = "wait_intake_confirmation"
        state["stage"] = "requirement_refine"
        state["awaiting_user"] = True
        state["pending_question"] = "A draft of the next version has been created. Please add or confirm your upgrade requirements."
    else:
        state["final_response"] = final_text
        state["current_node"] = "error_recovery"
        state["stage"] = "error_recovery"
        state["awaiting_user"] = True
        message = str((result or {}).get("message") or final_text or "Failed to initiate the next iteration")
        state["errors"] = state.get("errors", []) + [{
            "node": "iterate_agent_version",
            "error": message[:300],
            "stage": "iterating",
        }]
    return state


async def node_wait_evaluation(
    state: AgentBuilderState,
    llm_client: Any = None,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """After the test is completed, wait for user decision-making: publish/retest/modify/cancel.

    When you return to this node after publishing, the prompt is adjusted to the published state.
    """
    state["current_node"] = "wait_evaluation"
    state["awaiting_user"] = True
    state["stage"] = "evaluating"
    published = state.get("official_acceptance_decision") == "published"

    if state.get("skill_creation_requested"):
        gap_report = state.get("gap_report", {}) or {}
        blocking_gaps = gap_report.get("blocking_gaps", []) or []
        gap_desc = ""
        if blocking_gaps:
            gap_items = []
            for g in blocking_gaps[:3]:
                if isinstance(g, dict):
                    gap_items.append(f"- **{g.get('name', g.get('capability', 'unknown'))}**: {g.get('description', g.get('gap_description', ''))}")
                else:
                    gap_items.append(f"- {g}")
            gap_desc = "\n".join(gap_items)

        skill_msg = "Got it, you want to fill in the missing tools/skills.\n\n"
        if gap_desc:
            skill_msg += f"Capability gaps currently identified:\n{gap_desc}\n\n"
        skill_msg += (
            "> **Note**: Skill/The creation of tools requires developers to write code to implement them."
            "This cannot be done automatically in the current Agent build process.\n\n"
            "You have two options:\n"
            "1. **Release the current version first**: The current Agent s degradation mode test results have been produced and will be released online first. After the skill development is completed, it will be iteratively upgraded.\n"
            "2. **Record requirements for subsequent development**: Reply to Record Requirements and I will save the requirements for the missing skill.\n\n"
            "It is recommended to release the current version first, and then complete the capabilities through iterative upgrades."
        )
        state["final_response"] = skill_msg
        state["skill_creation_requested"] = False
        await _invoke_stream(on_stream, skill_msg)
        return state

    if state.get("clarification_needed"):
        # 🔑 Use LLM persona dialogue guidance instead of static templates
        if llm_client:
            clarify = await _clarify_with_llm(state, llm_client, event_callback, on_stream)
        else:
            clarify = _static_clarify_fallback(state)
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _stream_chunked(clarify, on_stream)
        return state

    if published:
        state["pending_question"] = (
            "Agent Released online. Optional operations: retest other stocks, upgrade/modify requirements, redo gap analysis,"
            "Rebuild solution, create new Agent, cancel."
        )
    else:
        state["pending_question"] = (
            "Test completed. Optional operations: publish, retest, upgrade/modify requirements, re-do gap analysis,"
            "Rebuild solution, create new Agent, cancel."
        )
    options_block = (
        "\n\n---\n"
        "You can then choose:\n"
        + ("1. Publish/go online the current version\n" if not published else "")
        + "2. Retest (you can directly say: retest iFlytek)\n"
        + "3. Upgrade/modification requirements\n"
        + "4. Re-do gap analysis\n"
        + "5. Rebuild solution\n"
        + "6. Create new other Agent\n"
        + "7. Cancel/End\n"
    )
    if options_block.strip() not in str(state.get("final_response", "")):
        state["final_response"] = (state.get("final_response", "") or "") + options_block
        await _invoke_stream(on_stream, options_block)
    await _emit_event(event_callback, "progress", state["pending_question"])

    return state


async def node_real_data_test(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Real data test node (two phases: test → Show report → Assessment → display evaluation results)."""
    test_symbol = state.get("test_symbol", "unknown")
    spec_name = state.get("spec_name", "Unnamed")

    # ═══════════════════════════════════════════════════════
    # Phase 1: Real data testing (only run Agent, no evaluation)
    # ═══════════════════════════════════════════════════════
    await _emit_event(event_callback, "step", "real data test")
    await _emit_event(event_callback, "progress", f"Currently using {test_symbol} Run Agent Analysis...")

    test_system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: real data testing. The user has provided the test target.

Agent Information:
- Name:{spec_name}
- Test target:{test_symbol}

Your task:
1. Call run_agent_workshop_real_data_test for real data testing (skip_evaluation is automatically set to True)
2. Briefly explain that the test has been completed and the report will be displayed soon

You must call the run_agent_workshop_real_data_test tool."""

    async def _periodic_progress_test():
        elapsed = 0
        while True:
            await asyncio.sleep(8)
            elapsed += 8
            if elapsed <= 24:
                phase = "Loading Agent configuration and running analysis tools"
            else:
                phase = "Agent Analyzing, generating report"
            await _emit_event(event_callback, "progress", f"{phase} (Already run {elapsed} seconds)...")

    progress_task = asyncio.create_task(_periodic_progress_test())
    try:
        test_text, test_tool_events, test_tool_results = await _run_node_llm(
            state, test_system_prompt, tool_registry, llm_client,
            required_tool_name="run_agent_workshop_real_data_test",
            include_inspect_tools=False,
            event_callback=event_callback,
            on_stream=on_stream,
        )
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

    state["tool_events"] = test_tool_events
    state["current_node"] = "real_data_test"
    state["stage"] = "testing"

    # Extract test results
    test_result = _extract_json_from_result(
        test_tool_results.get("run_agent_workshop_real_data_test", "{}")
    )

    if not test_result or test_result.get("status") == "error":
        # test failed
        err_msg = (
            test_result.get("message") if test_result else ""
            or "Real data test failed"
        )
        state["test_result"] = test_result or {}
        state["errors"] = state.get("errors", []) + [{
            "node": "real_data_test",
            "error": str(err_msg)[:300],
            "stage": "testing",
        }]
        state["final_response"] = f"❌ Real data test fails:{err_msg}"
        return state

    state["test_result"] = test_result

    # 🔑 Extract test reports and display them to users
    debug_result = test_result.get("debug_result", {}) if isinstance(test_result, dict) else {}
    test_report = str(debug_result.get("report") or test_result.get("message") or "").strip()
    report_length = debug_result.get("report_length") or len(test_report)

    # Build test report display
    report_display = f"## Real data test results\n\n"
    report_display += f"**Target:** {test_symbol}\n"
    report_display += f"**Agent：** {spec_name}\n"
    report_display += f"**Report length:** {report_length} character\n\n"
    report_display += "---\n\n"
    if test_report:
        # Cut off the first 3000 characters for display to avoid being too long
        if len(test_report) > 3000:
            report_display += test_report[:3000] + "\n\n... (Report has been truncated, full content saved)"
        else:
            report_display += test_report
    else:
        report_display += "The test completed but the report text was not generated."

    state["final_response"] = report_display
    await _stream_chunked(report_display, on_stream)
    await _emit_event(event_callback, "progress", "Test report has been displayed, start evaluation...")

    # ═══════════════════════════════════════════════════════
    # Phase 2: Evaluate test results
    # ═══════════════════════════════════════════════════════
    await _emit_event(event_callback, "step", "Evaluate test results")
    await _emit_event(event_callback, "progress", "Assessing report quality and compliance...")

    # Save runtime_result for use by evaluate_agent_workshop_version tool
    runtime_result = test_result.get("runtime_result", {})
    if runtime_result:
        state["_test_runtime_result_json"] = json.dumps(runtime_result, ensure_ascii=False, default=str)
    user_feedback = test_result.get("user_feedback", "")
    if user_feedback:
        state["_test_user_feedback"] = user_feedback

    eval_system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: Evaluating test results. Agent {spec_name}] use {test_symbol} The real data test is completed and now it is time to evaluate the report quality.

Your task:
1. Call evaluate_agent_workshop_version to evaluate test results
2. Interpret evaluation conclusions (decisions, scores, main issues, recommendations) in business language

You must call the evaluate_agent_workshop_version tool."""

    async def _periodic_progress_eval():
        elapsed = 0
        while True:
            await asyncio.sleep(8)
            elapsed += 8
            if elapsed <= 24:
                phase = "Running assessment workflows and compliance checks"
            else:
                phase = "Assessment report and revision recommendations are being generated"
            await _emit_event(event_callback, "progress", f"{phase} (Already run {elapsed} seconds)...")

    eval_progress_task = asyncio.create_task(_periodic_progress_eval())
    try:
        eval_text, eval_tool_events, eval_tool_results = await _run_node_llm(
            state, eval_system_prompt, tool_registry, llm_client,
            required_tool_name="evaluate_agent_workshop_version",
            include_inspect_tools=False,
            event_callback=event_callback,
            on_stream=on_stream,
        )
    finally:
        eval_progress_task.cancel()
        try:
            await eval_progress_task
        except asyncio.CancelledError:
            pass

    # merge tool_events
    state["tool_events"] = list(state.get("tool_events", [])) + list(eval_tool_events)

    # Extract evaluation results
    eval_result = _extract_json_from_result(
        eval_tool_results.get("evaluate_agent_workshop_version", "{}")
    )

    # Build evaluation results display
    eval_display = f"\n\n---\n\n## Assessment results\n\n"
    if eval_result and eval_result.get("status") == "ok":
        evaluation = eval_result.get("evaluation", {}) if isinstance(eval_result, dict) else {}
        decision = evaluation.get("decision", "unknown") if isinstance(evaluation, dict) else "unknown"
        scores = evaluation.get("scores", {}) if isinstance(evaluation, dict) else {}
        overall_score = scores.get("overall", "N/A") if isinstance(scores, dict) else "N/A"
        issues = evaluation.get("issues", []) if isinstance(evaluation, dict) else []
        recommendations = evaluation.get("recommendations", []) if isinstance(evaluation, dict) else []

        decision_label = {"pass": "✅ Pass", "revise": "⚠️ Need revision", "reject": "❌ failed"}.get(decision, decision)
        eval_display += f"**Assessment conclusion:** {decision_label}\n"
        eval_display += f"**Overall score:** {overall_score}\n\n"

        if issues:
            eval_display += "**Main questions:**\n"
            for issue in issues[:5]:
                eval_display += f"- {issue}\n"
            eval_display += "\n"

        if recommendations:
            eval_display += "**Optimization suggestions:**\n"
            for rec in recommendations[:5]:
                eval_display += f"- {rec}\n"
            eval_display += "\n"

        # Update evaluation information in state
        state["test_result"] = {**state.get("test_result", {}), "evaluation": evaluation}
        state["official_acceptance_decision"] = decision
    else:
        eval_display += eval_text or "The assessment is complete, please see the explanation above for details."

    # Added interpretation of LLM
    if eval_text and eval_text.strip():
        eval_display += f"\n\n---\n\n{eval_text}"

    # merge final response
    state["final_response"] = report_display + eval_display
    await _emit_event(event_callback, "progress", "Testing and evaluation completed")

    # Clean up temporary state
    state.pop("_test_runtime_result_json", None)
    state.pop("_test_user_feedback", None)

    logger.info(
        "[RealDataTest][Done] symbol=%s report_len=%s eval_status=%s decision=%s",
        test_symbol,
        report_length,
        eval_result.get("status") if eval_result else "N/A",
        eval_result.get("evaluation", {}).get("decision", "N/A") if eval_result and isinstance(eval_result.get("evaluation"), dict) else "N/A",
    )

    return state


async def node_evaluate_or_publish(
    state: AgentBuilderState,
    tool_registry: Any,
    llm_client: Any,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Evaluation/Release node."""
    state["current_node"] = "evaluate_or_publish"
    state["stage"] = "evaluating"
    state["awaiting_user"] = True  # Alternative, must be retained to ensure interaction with users, the sub-state will be updated later

    # If the previous round of intentions cannot be recognized, use LLM persona dialogue guidance instead of static templates
    if state.get("clarification_needed"):
        if llm_client:
            clarify = await _clarify_with_llm(state, llm_client, event_callback, on_stream)
        else:
            clarify = _static_clarify_fallback(state)
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _stream_chunked(clarify, on_stream)
        return state

    await _emit_event(event_callback, "step", "Evaluate and publish")
    await _emit_event(event_callback, "progress", "Evaluating test results")

    system_prompt = f"""You are a financial product expert on the TradingAgentsCN platform.

Current stage: evaluation and release. Testing is complete and the results need to be evaluated and decided whether to publish.

Agent Information:
- Name:{state.get('spec_name', 'Unnamed')}
- Test results:{json.dumps(state.get('test_result', {}), ensure_ascii=False)[:1000]}

Your task:
1. If the test passes, call publish_agent_workshop_version to publish
2. If there is a problem with the test, call evaluate_agent_workshop_version to evaluate

You must call the publish_agent_workshop_version or evaluate_agent_workshop_version tool."""

    final_text, tool_events, tool_results = await _run_node_llm(
        state, system_prompt, tool_registry, llm_client,
        required_tool_name=["publish_agent_workshop_version", "evaluate_agent_workshop_version"],
        include_inspect_tools=False,
        event_callback=event_callback,
        on_stream=on_stream,
    )

    state["final_response"] = final_text
    state["tool_events"] = tool_events

    pub_result = _extract_json_from_result(
        tool_results.get("publish_agent_workshop_version", "{}")
    )
    eval_result = _extract_json_from_result(
        tool_results.get("evaluate_agent_workshop_version", "{}")
    )

    if pub_result:
        state["official_acceptance_decision"] = "published"
        state["current_node"] = "wait_evaluation"
        state["awaiting_user"] = True
        logger.info("[Eval] Published successfully, return to wait_evaluation to wait for subsequent instructions from the user")
    elif eval_result:
        decision = eval_result.get("decision", "revise")
        state["official_acceptance_decision"] = decision
        state["current_node"] = "wait_evaluation"
        state["awaiting_user"] = True
        logger.info("[Eval] Assessment completed decision=%s, Return to wait_evaluation and wait for subsequent instructions from the user", decision)

    # Always mark waiting for users after evaluation/release is completed to ensure checkpoint is persisted
    state["awaiting_user"] = True
    state["stage"] = "completed"
    logger.info(
        "[Eval] evaluate_or_publish Complete | current_node=%s | awaiting_user=%s | decision=%s",
        state["current_node"], state["awaiting_user"], state.get("official_acceptance_decision"),
    )

    return state


async def node_error_recovery(
    state: AgentBuilderState,
    llm_client: Any = None,
    event_callback: Optional[Callable] = None,
    on_stream: Optional[Callable] = None,
) -> AgentBuilderState:
    """Error recovery node.

    There is no automatic rollback or skipping, the user decides the next step.
    """
    state["current_node"] = "error_recovery"
    state["awaiting_user"] = True

    # If the previous round of intent cannot be recognized, a clarification prompt will be output.
    if state.get("clarification_needed"):
        errors = state.get("errors", [])
        err_lines = []
        for e in errors[-3:]:
            if isinstance(e, dict):
                err_lines.append(f"- {e.get('node','?')}: {e.get('error','?')}")
            else:
                err_lines.append(f"- {e}")
        err_text = "\n".join(err_lines)
        clarify = (
            f"Sorry, I don t quite understand what you mean. Currently encountering the following problems:\n{err_text}\n\n"
            "You can:\n"
            "- Reply Retry and re-execute the previous step.\n"
            "- Reply Skip to skip the current step\n"
            "- Reply Modify to return to demand adjustment\n"
            "- Reply Cancel to end the process\n\n"
            "Please be more specific."
        )
        state["final_response"] = clarify
        state["clarification_needed"] = False
        await _invoke_stream(on_stream, clarify)
        return state

    errors = state.get("errors", [])
    error_lines: list[str] = []
    for e in errors[-3:]:
        if isinstance(e, dict):
            node = e.get("node", "unknown")
            err = e.get("error", "unknown error")
            error_lines.append(f"- {node}: {err}")
        else:
            # Compatible string form error
            error_lines.append(f"- {e}")
    error_text = "\n".join(error_lines)

    state["pending_question"] = (
        f"Some problems were encountered during the processing:\n{error_text}\n\n"
        "You can choose:\n"
        "  a) Try again\n"
        "  b) skip\n"
        "  c) Cancel"
    )
    state["final_response"] = state["pending_question"]

    await _emit_event(event_callback, "step", "error recovery")
    return state