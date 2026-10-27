"""
Tool execution context management

Use Python contextvars to pass user context in asynchronous call chains,
Enables operation tools (assistant_ops) to obtain the current user identity without exposing the user_id in the tool signature.
"""

import contextvars
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 🔒 Isolated intent storage by thread_id (replacement for unstable contextvar)
# contextvar It will be silently rolled back in the tool call chain of LangChain/LLM provider.
# Therefore use module level dict + thread_id Index to reliably deliver intent changes.
_nanobot_intents_by_thread: Dict[str, Dict[str, Any]] = {}

# Current user ID (set in IntelligentAssistantService.chat entry)
_current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_user_id', default=None
)

# Current IM channel information (set in the GatewayRouter._invoke_assistant entry)
# Format: {"channel_type": "qq", "channel_id": "c2c:xxx"}
_current_im_channel: contextvars.ContextVar[Optional[Dict[str, str]]] = contextvars.ContextVar(
    'current_im_channel', default=None
)

# Current intelligent assistant topic ID (set in the IntelligentAssistantService.chat entry)
_current_assistant_thread_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_assistant_thread_id', default=None
)

# Current smart assistant thread context (used to read the object currently selected by the front end during the tool call period, such as Agent Workshop spec/version)
_current_assistant_thread_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'current_assistant_thread_context', default=None
)

# Current analysis data source (set before the Agent tool is called)
_current_analysis_data_source: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_analysis_data_source', default=None
)


def set_current_user_id(user_id: str) -> contextvars.Token:
    """Set current user ID

    Args:
        user_id: User ID string

    Returns:
        contextvars.Token, Available for reset
    """
    return _current_user_id.set(user_id)


def get_current_user_id() -> Optional[str]:
    """Get current user ID

    Returns:
        Current user ID, returned if not set None
    """
    return _current_user_id.get()


def require_current_user_id() -> str:
    """Get the current user ID, throw an exception if not set

    Returns:
        current user ID

    Raises:
        RuntimeError: User not set in context ID
    """
    user_id = _current_user_id.get()
    if user_id is None:
        raise RuntimeError(
            "user_id is not set in the current context."
            "Please make sure to IntelligentAssistantService.chat() The entrance is called set_current_user_id(). "
        )
    return user_id


def set_current_im_channel(channel_type: str, channel_id: str) -> contextvars.Token:
    """Set current IM channel information (called by GatewayRouter when processing a message)

    Args:
        channel_type: Platform type, such as "qq", "feishu"
        channel_id:   Platform side session ID, such as "c2c:openid", "group:group_openid"

    Returns:
        contextvars.Token, Available for reset
    """
    return _current_im_channel.set({"channel_type": channel_type, "channel_id": channel_id})


def get_current_im_channel() -> Optional[Dict[str, str]]:
    """Get current IM channel information

    Returns:
        {"channel_type": "qq", "channel_id": "c2c:xxx"} or None (non-IM channels)
    """
    return _current_im_channel.get()


def set_current_assistant_thread_id(thread_id: Optional[str]) -> contextvars.Token:
    """Set the current smart assistant theme ID"""
    return _current_assistant_thread_id.set(thread_id)


def get_current_assistant_thread_id() -> Optional[str]:
    """Get the current smart assistant theme ID"""
    return _current_assistant_thread_id.get()


def set_current_assistant_thread_context(thread_context: Optional[Dict[str, Any]]) -> contextvars.Token:
    """Sets the current smart assistant thread context."""
    clean_context = dict(thread_context or {}) if isinstance(thread_context, dict) else None
    return _current_assistant_thread_context.set(clean_context)


def get_current_assistant_thread_context() -> Dict[str, Any]:
    """Get the current smart assistant thread context."""
    return dict(_current_assistant_thread_context.get() or {})


def set_current_analysis_data_source(data_source: Optional[str]) -> contextvars.Token:
    """Set the current analysis data source.

    Args:
        data_source: Data source name, such as "qmt", "tushare"

    Returns:
        contextvars.Token, Available for reset
    """
    normalized = None
    if isinstance(data_source, str):
        text = data_source.strip().lower()
        normalized = text or None
    return _current_analysis_data_source.set(normalized)


def reset_current_analysis_data_source(token: contextvars.Token) -> None:
    """Reset the current analysis data source."""
    _current_analysis_data_source.reset(token)


def get_current_analysis_data_source() -> Optional[str]:
    """Get the current analysis data source."""
    return _current_analysis_data_source.get()


# ── Nanobot Intent storage independent of contextvar ──
# contextvar May be isolated/overridden by Task boundaries in asynchronous tool calls, so use module-level dict as a fallback.
# Write path:update_intent_context_in_thread() Write here at the same time
# Reading path:service.chat() persist read before
#
# 🔒 Governance rules (from nanobot-memory-governance-design.md):
# - contextvar It is only used as an acceleration cache within the same process and cannot be used as the only source across rounds.
# - Module-level dict isolated by thread_id as a source of trust before persistence.
# - At the end of each conversation round, embedded_nanobot_service.py reads the intent from here and merges it into the thread_context.
# - It is forbidden to write implicitly through contextvar within the tool call chain without writing back the module-level dict.

def set_latest_nanobot_intent(intent_dict: Dict[str, Any]) -> None:
    """Stores the latest Nanobot intent (isolated by thread_id).

    After each tool call completes, the current intent should be written here.
    This is the only reliable source of persistence across rounds.
    """
    thread_id = _current_assistant_thread_id.get() or "unknown"
    _nanobot_intents_by_thread[thread_id] = dict(intent_dict)
    logger.debug(
        "[IntentStore] set_latest_nanobot_intent thread_id=%s stage=%s action=%s spec_id=%s",
        thread_id,
        intent_dict.get("stage", "-"),
        intent_dict.get("action", "-"),
        intent_dict.get("spec_id", "-"),
    )


def get_latest_nanobot_intent() -> Dict[str, Any]:
    """Read the latest Nanobot intent (isolated by thread_id)."""
    thread_id = _current_assistant_thread_id.get() or "unknown"
    return _nanobot_intents_by_thread.get(thread_id, {})


def clear_latest_nanobot_intent() -> None:
    """Clear the Nanobot intent for the current thread."""
    thread_id = _current_assistant_thread_id.get() or "unknown"
    _nanobot_intents_by_thread.pop(thread_id, None)

