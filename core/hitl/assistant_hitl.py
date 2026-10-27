"""Smart Assistant HITL integration (v3.5.0 item 4).

In the Smart Assistant ReAct loop, do"critical operations"Achieve real HITL:
1. LLM When calling key tools, they are not executed directly, but the pending operations are saved to MongoDB
2. Return"Need confirmation"Message to LLM, LLM relays to user
3. The user confirms/denies via the frontend (calling /api/assistant/hitl/{pending_id}/confirm or reject)
4. Perform real work after confirmation; discard if rejected

List of key actions (based on the"Confirm before executing"principle):
- trigger_stock_analysis (Trigger analysis)
- trigger_batch_analysis (batch analysis)
- remove_stock_from_watchlist (Remove discretionary stocks)
- delete_scheduled_config (Delete timing configuration)
- delete_topic (Delete research topic)
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .checkpoint_store import HITLCheckpointService, get_hitl_service

logger = logging.getLogger(__name__)


# List of key tool IDs requiring HITL confirmation
CRITICAL_TOOL_IDS: Dict[str, Dict[str, Any]] = {
    "trigger_stock_analysis": {
        "display_name": "Trigger stock analysis",
        "risk_level": "medium",
        "reason": "Analysis tasks will consume more Tokens and time",
    },
    "trigger_batch_analysis": {
        "display_name": "Trigger batch analysis",
        "risk_level": "high",
        "reason": "Batch analysis consumes a lot of resources at the same time",
    },
    "remove_stock_from_watchlist": {
        "display_name": "Remove discretionary stocks",
        "risk_level": "medium",
        "reason": "The removal operation cannot be automatically restored",
    },
    "delete_scheduled_config": {
        "display_name": "Delete scheduled analysis configuration",
        "risk_level": "high",
        "reason": "Deleting the configuration will affect subsequent automatic analysis",
    },
    "delete_topic": {
        "display_name": "Delete research topic",
        "risk_level": "high",
        "reason": "Deleting a topic will lose related conversation history",
    },
}


# Keywords for user confirmation of intent
CONFIRM_KEYWORDS = {"Confirm", "OK", "yes", "ok", "OK", "Agree", "execute", "Confirm execution", "Confirm deletion", "continue"}
REJECT_KEYWORDS = {"Cancel", "no", "No", "Don t", "reject", "Forget it", "give up", "Not executed", "Cancel execution"}


def is_critical_tool(tool_id: str) -> bool:
    """Determine whether the tool is a critical operation (requires HITL)"""
    return tool_id in CRITICAL_TOOL_IDS


def is_user_confirming(user_message: str) -> bool:
    """Determine whether the user message is a confirmation intention"""
    if not user_message:
        return False
    msg = user_message.strip().lower()
    return any(kw in msg for kw in CONFIRM_KEYWORDS)


def is_user_rejecting(user_message: str) -> bool:
    """Determine whether the user message is intended to reject"""
    if not user_message:
        return False
    msg = user_message.strip().lower()
    return any(kw in msg for kw in REJECT_KEYWORDS)


def generate_pending_id() -> str:
    """generate unique pending_id"""
    return f"hitl_{uuid.uuid4().hex[:12]}"


async def save_pending_critical_action(
    db: Any,
    *,
    user_id: str,
    conversation_id: str,
    tool_id: str,
    tool_arguments: Dict[str, Any],
    display_message: str = "",
) -> Optional[str]:
    """Save key operations pending confirmation.

    Args:
        db: MongoDB handle
        user_id: User ID
        conversation_id: session ID
        tool_id: Tools ID
        tool_arguments: Tool parameters (used for execution after user confirmation)
        display_message: Instructions for users

    Returns:
        pending_id or None (when saving fails)
    """
    if not is_critical_tool(tool_id):
        return None

    tool_meta = CRITICAL_TOOL_IDS[tool_id]
    pending_id = generate_pending_id()

    svc = get_hitl_service(db)
    try:
        await svc.save_pending(
            pending_id=pending_id,
            user_id=user_id,
            thread_id=conversation_id,
            operation_type="assistant_critical_action",
            operation_payload={
                "tool_id": tool_id,
                "tool_arguments": tool_arguments,
            },
            display_data={
                "tool_name": tool_meta["display_name"],
                "risk_level": tool_meta["risk_level"],
                "reason": tool_meta["reason"],
                "display_message": display_message or f"About to execute:{tool_meta['display_name']}",
                "arguments_preview": _format_arguments_preview(tool_arguments),
            },
        )
        return pending_id
    except Exception as e:
        logger.warning("[HITL·Assistant] Failed to save pending confirmation operation: %s", e)
        return None


def _format_arguments_preview(arguments: Dict[str, Any]) -> str:
    """Format parameter preview (for users to see)"""
    if not arguments:
        return " (no parameters)"
    parts = []
    for k, v in list(arguments.items())[:5]:
        v_str = str(v)
        if len(v_str) > 50:
            v_str = v_str[:50] + "..."
        parts.append(f"{k}={v_str}")
    return ", ".join(parts)


def build_pending_confirmation_reply(
    tool_id: str,
    tool_arguments: Dict[str, Any],
    pending_id: str,
) -> str:
    """build"Need confirmation"The reply text (LLM will forward it to the user after seeing it)"""
    tool_meta = CRITICAL_TOOL_IDS.get(tool_id, {})
    display_name = tool_meta.get("display_name", tool_id)
    reason = tool_meta.get("reason", "")
    risk_level = tool_meta.get("risk_level", "medium")

    risk_emoji = {"high": "⚠️", "medium": "🟡", "low": "🟢"}.get(risk_level, "🟡")
    args_preview = _format_arguments_preview(tool_arguments)

    return (
        f"{risk_emoji} Key operations are about to be performed:**{display_name}**\n\n"
        f"- Operating parameters:{args_preview}\n"
        f"- Risk level:{risk_level}\n"
        f"- Reason:{reason}\n\n"
        f"Please confirm whether to execute (reply Confirm to execute, reply Cancel to give up).\n"
        f"Confirm ID:`{pending_id}`"
    )


async def try_resolve_pending_action(
    db: Any,
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
) -> Optional[Dict[str, Any]]:
    """Attempts to parse the user s confirm/deny intent and perform or discard the pending action.

    in chat() Called at the beginning of the main process, if the user is confirming/denying, the corresponding operation is performed and the result is returned.

    Returns:
        - None: The user message is not a confirmation/deny, or there is no pending operation
        - {"type": "confirmed", "result": ...}: Confirmed and executed
        - {"type": "rejected", "message": ...}: Rejected
    """
    svc = get_hitl_service(db)
    pending_list = await svc.list_pending(
        user_id=user_id,
        thread_id=conversation_id,
        operation_type="assistant_critical_action",
    )
    if not pending_list:
        return None

    # Get the latest pending operation
    pending = pending_list[0]
    if pending.status != "pending":
        return None

    if is_user_rejecting(user_message):
        await svc.decide(pending_id=pending.pending_id, decision="rejected")
        return {
            "type": "rejected",
            "message": f"Operation canceled:{pending.display_data.get('tool_name', '')}",
        }

    if not is_user_confirming(user_message):
        return None

    # User confirmation → perform real work
    tool_id = pending.operation_payload.get("tool_id", "")
    tool_arguments = pending.operation_payload.get("tool_arguments", {})

    try:
        result = await _execute_critical_tool(db, tool_id, tool_arguments, user_id=user_id)
        await svc.decide(pending_id=pending.pending_id, decision="confirmed")
        return {
            "type": "confirmed",
            "result": result,
            "tool_id": tool_id,
        }
    except Exception as e:
        logger.error("[HITL·Assistant] Failed to perform confirmation operation: %s", e, exc_info=True)
        await svc.decide(pending_id=pending.pending_id, decision="rejected")
        return {
            "type": "rejected",
            "message": f"Operation execution failed:{e}",
        }


async def _execute_critical_tool(
    db: Any,
    tool_id: str,
    arguments: Dict[str, Any],
    *,
    user_id: str = "",
) -> str:
    """Execute the real key tool (called after user confirmation)"""
    import inspect
    from core.tools import get_tool_registry
    registry = get_tool_registry()
    func = registry.get_function(tool_id)
    if func is None:
        raise ValueError(f"Tools {tool_id} Not registered")

    call_args = dict(arguments or {})

    # Check tool signature: accept user_id / accept **kwargs
    try:
        sig = inspect.signature(func)
        param_names = set(sig.parameters.keys())
        accepts_var_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        param_names = set()
        accepts_var_kwargs = False

    # Inject only if tool signature accepts user_id (such as remember_this closure);
    # Tools that do not accept user_id (such as trigger_stock_analysis internally takes the current user) will not be injected.
    # Otherwise func(**arguments) Can throw TypeError
    if (
        user_id
        and "user_id" not in call_args
        and ("user_id" in param_names or accepts_var_kwargs)
    ):
        call_args["user_id"] = user_id

    # Parameters not accepted by the filtering tool (LLM may make up redundant parameters to cause TypeError),**kwargs Except
    if not accepts_var_kwargs and param_names:
        call_args = {k: v for k, v in call_args.items() if k in param_names}

    result = func(**call_args)
    if hasattr(result, "__await__"):
        result = await result

    return str(result) if result is not None else ""


async def list_pending_for_user(
    db: Any,
    *,
    user_id: str,
    conversation_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List user operations to be confirmed (for front-end display)"""
    svc = get_hitl_service(db)
    pending_list = await svc.list_pending(
        user_id=user_id,
        thread_id=conversation_id,
        operation_type="assistant_critical_action",
    )
    return [
        {
            "pending_id": p.pending_id,
            "tool_name": p.display_data.get("tool_name", ""),
            "display_message": p.display_data.get("display_message", ""),
            "risk_level": p.display_data.get("risk_level", "medium"),
            "reason": p.display_data.get("reason", ""),
            "arguments_preview": p.display_data.get("arguments_preview", ""),
            "created_at": p.created_at,
        }
        for p in pending_list
    ]


async def confirm_pending(
    db: Any,
    *,
    pending_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """API Endpoint use: Confirm execution of pending operations"""
    svc = get_hitl_service(db)
    pending = await svc.load_pending(pending_id)
    if not pending:
        return {"success": False, "error": "Operation does not exist"}
    if pending.user_id != user_id:
        return {"success": False, "error": "No permission to operate"}
    if pending.status != "pending":
        return {"success": False, "error": f"Operation processed (status:{pending.status}) "}

    tool_id = pending.operation_payload.get("tool_id", "")
    tool_arguments = pending.operation_payload.get("tool_arguments", {})

    try:
        result = await _execute_critical_tool(db, tool_id, tool_arguments, user_id=user_id)
        await svc.decide(pending_id=pending_id, decision="confirmed")
        return {
            "success": True,
            "result": result,
            "tool_id": tool_id,
        }
    except Exception as e:
        await svc.decide(pending_id=pending_id, decision="rejected")
        return {"success": False, "error": str(e)}


async def reject_pending(
    db: Any,
    *,
    pending_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """API Endpoint use: Deny execution of pending operations"""
    svc = get_hitl_service(db)
    pending = await svc.load_pending(pending_id)
    if not pending:
        return {"success": False, "error": "Operation does not exist"}
    if pending.user_id != user_id:
        return {"success": False, "error": "No permission to operate"}
    if pending.status != "pending":
        return {"success": False, "error": f"Operation processed (status:{pending.status}) "}

    await svc.decide(pending_id=pending_id, decision="rejected")
    return {"success": True, "message": "Operation denied"}
