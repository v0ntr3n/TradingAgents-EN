"""
Agent Builder Graph MongoDB state storage

Based on MongoDB s checkpoint mechanism, it is used to wait for nodes to be paused and resumed across HTTP requests.
Does not rely on LangGraph s built-in interrupt (it relies on in-process memory).
"""

from __future__ import annotations

import asyncio as _asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.embedded_nanobot.workflows.agent_builder_state import AgentBuilderState

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_builder_graph_sessions"

# Known field whitelist
_KNOWN_KEYS = frozenset({
    "thread_id", "user_id", "user_message", "channel", "chat_id",
    "current_node", "stage", "awaiting_user", "pending_question",
    "spec_id", "spec_name", "requirement_summary", "confirmation_brief",
    "original_user_request", "proposed_plan",
    "capability_inventory", "gap_report",
    "candidate_plans", "pending_options", "recommended_plan_id",
    "selected_plan_id", "acknowledged_gaps",
    "generated_agent", "workshop_session_id", "version_id", "build_status",
    "decision_context",
    "test_symbol", "test_result", "official_acceptance_decision",
    "errors", "conversation_summary", "tool_events", "final_response",
    # ── Intent classification v2 fields ──
    "user_intent", "user_selected_index", "user_selected_id",
    "intent_confidence", "intent_reason",
    # ── Conversation history (persistent across requests, used for LLM intent classification) ──
    "message_history",
    # ── Clarification markup (persisted across requests) ──
    "clarification_needed",
    "skill_creation_requested",
    # ── tool progress ──
    "test_progress",
})

# Inject fields at runtime (not persisted)
_RUNTIME_KEYS = frozenset({
    "db", "workspace", "provider", "event_callback",
    "_tool_registry", "_llm_client", "_event_callback", "_on_stream",
    # Compatible with fields that may remain in old checkpoints (will be automatically stripped when loading)
    "_provider", "_model",
})


class AgentBuilderGraphStore:
    """Agent Builder Graph MongoDB state store."""

    def __init__(self, db: Any):
        self.db = db
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.db[COLLECTION_NAME]
        return self._collection

    async def save_checkpoint(
        self,
        thread_id: str,
        state: AgentBuilderState,
        current_node: str,
    ) -> None:
        """in wait_* Save the state before the node."""
        now = datetime.now(timezone.utc)
        safe_state = _make_state_serializable(state)

        try:
            await self.collection.update_one(
                {"thread_id": thread_id},
                {
                    "$set": {
                        "current_node": current_node,
                        "state": safe_state,
                        "stage": safe_state.get("stage", ""),
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
            logger.info(
                "[GraphStore][Save] thread=%s, node=%s, stage=%s",
                thread_id, current_node, safe_state.get("stage", ""),
            )
        except Exception as e:
            logger.error("[GraphStore][SaveError] thread=%s: %s", thread_id, e)

    async def load_checkpoint(self, thread_id: str) -> Optional[AgentBuilderState]:
        """Restore a saved state. Returning None means there is no checkpoint (new session)."""
        try:
            doc = await self.collection.find_one({"thread_id": thread_id})
            if not doc:
                logger.info("[GraphStore][Load] thread=%s: no checkpoint", thread_id)
                return None
            state = doc.get("state", {})
            if not isinstance(state, dict):
                state = {}
            logger.info(
                "[GraphStore][Load] thread=%s: node=%s, stage=%s",
                thread_id, doc.get("current_node"), state.get("stage"),
            )
            clean_state = {k: v for k, v in state.items() if k in _KNOWN_KEYS}
            return AgentBuilderState(**clean_state)
        except Exception as e:
            logger.error("[GraphStore][LoadError] thread=%s: %s", thread_id, e)
            return None

    async def update_state(self, thread_id: str, state: AgentBuilderState) -> None:
        """Update saved state (non-waiting nodes)."""
        safe_state = _make_state_serializable(state)
        try:
            await self.collection.update_one(
                {"thread_id": thread_id},
                {
                    "$set": {
                        "state": safe_state,
                        "stage": safe_state.get("stage", ""),
                        "current_node": safe_state.get("current_node", ""),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
        except Exception as e:
            logger.error("[GraphStore][UpdateError] thread=%s: %s", thread_id, e)

    async def delete_checkpoint(self, thread_id: str) -> None:
        """Graph Clean up after completion/cancellation."""
        try:
            await self.collection.delete_one({"thread_id": thread_id})
            logger.info("[GraphStore][Delete] thread=%s: checkpoint deleted", thread_id)
        except Exception as e:
            logger.error("[GraphStore][DeleteError] thread=%s: %s", thread_id, e)

    async def get_current_node(self, thread_id: str) -> Optional[str]:
        """Get the current node name (without loading the full state)."""
        try:
            doc = await self.collection.find_one(
                {"thread_id": thread_id}, {"current_node": 1}
            )
            return doc.get("current_node") if doc else None
        except Exception:
            return None


def _make_state_serializable(state: AgentBuilderState) -> Dict[str, Any]:
    """Remove the non-serializable fields in the state and generate a dictionary that can be safely written to MongoDB."""
    safe = {}
    for key, value in state.items():
        if key in _RUNTIME_KEYS:
            continue
        if key not in _KNOWN_KEYS:
            continue
        safe[key] = _deep_clean(value)
    return safe


def _deep_clean(value: Any) -> Any:
    """Recursively clean up non-serializable values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, _asyncio.Future):
        return None
    if isinstance(value, (list, tuple)):
        return [_deep_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _deep_clean(v) for k, v in value.items() if not isinstance(v, _asyncio.Future)}
    # Convert other types to string
    try:
        str(value)
        return value
    except Exception:
        return str(value)
