"""
Generic HITL checkpoint service.

Extract MongoDB checkpoint mode from core/embedded_nanobot/workflows/agent_builder_store.py,
Let non-LangGraph scenarios (smart assistant ReAct loop, Skill generate asynchronous pipeline) also use HITL.

Design points:
- Does not rely on LangGraph interrupt() (That s in-process memory)
- Persistence via MongoDB"Action to be confirmed", Pause/resume across HTTP requests
- Each pending operation has a unique pending_id, and the front-end pop-up window/list uses this ID to track
- Support 24h timeout automatic expiration cleanup

Usage scenarios:
1. The smart assistant pauses before executing key operations (deleting configurations/triggering batch analysis) and waiting for user confirmation.
2. Skill After the generation is completed, it will not be automatically bound and will wait for the user to review the code and test results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

COLLECTION_NAME = "hitl_pending_operations"


class PendingOperation(BaseModel):
    """A unified data model for pending operations."""

    pending_id: str  # Unique ID, used by the front end for tracking
    user_id: str
    thread_id: str  # Session ID (smart assistant conversation_id / agent_builder thread_id)
    operation_type: str  # "assistant_critical_action" / "skill_binding_review" / ...
    operation_payload: Dict[str, Any] = Field(default_factory=dict)  # Operation parameters to be executed
    display_data: Dict[str, Any] = Field(default_factory=dict)  # Data for front-end display (title/description/risk level)
    status: str = "pending"  # pending / confirmed / rejected / expired
    created_at: str = ""
    decided_at: str = ""
    decided_by: str = ""  # user / system_timeout


class HITLCheckpointService:
    """Generic HITL checkpoint service.

    Pause/resume across HTTP requests by persisting pending operations with MongoDB.
    """

    def __init__(self, db: Any):
        self._db = db
        self._collection = db[COLLECTION_NAME]

    async def save_pending(
        self,
        *,
        pending_id: str,
        user_id: str,
        thread_id: str,
        operation_type: str,
        operation_payload: Dict[str, Any],
        display_data: Dict[str, Any],
    ) -> PendingOperation:
        """Write operation to be confirmed, the main process is paused here.

        Args:
            pending_id: Unique ID (caller generated, e.g. f"hitl_{uuid.uuid4().hex[:12]}") 
            user_id: User ID
            thread_id: session ID
            operation_type: Operation type
            operation_payload: Operation parameters to be executed (used for execution after user confirmation)
            display_data: Data for front-end display

        Returns:
            written PendingOperation
        """
        now = datetime.now(timezone.utc).isoformat()
        op = PendingOperation(
            pending_id=pending_id,
            user_id=user_id,
            thread_id=thread_id,
            operation_type=operation_type,
            operation_payload=operation_payload,
            display_data=display_data,
            status="pending",
            created_at=now,
        )
        await self._collection.update_one(
            {"pending_id": pending_id},
            {"$set": op.model_dump()},
            upsert=True,
        )
        logger.info(
            "[HITL] Action saved for confirmation: pending_id=%s type=%s thread=%s",
            pending_id, operation_type, thread_id,
        )
        return op

    async def load_pending(self, pending_id: str) -> Optional[PendingOperation]:
        """Load a single pending action.

        Returns:
            PendingOperation or None (when not present)
        """
        doc = await self._collection.find_one({"pending_id": pending_id})
        if not doc:
            return None
        # Filter on _id field
        clean = {k: v for k, v in doc.items() if k != "_id"}
        return PendingOperation(**clean)

    async def list_pending(
        self,
        *,
        user_id: str,
        thread_id: Optional[str] = None,
        operation_type: Optional[str] = None,
    ) -> List[PendingOperation]:
        """List operations to be confirmed (for front-end display).

        Args:
            user_id: User ID
            thread_id: Optional, session-limited
            operation_type: Optional, limited operation type

        Returns:
            PendingOperation List (in descending order of creation time, up to 20 items)
        """
        query: Dict[str, Any] = {"user_id": user_id, "status": "pending"}
        if thread_id:
            query["thread_id"] = thread_id
        if operation_type:
            query["operation_type"] = operation_type

        cursor = self._collection.find(query).sort("created_at", -1).limit(20)
        docs = await cursor.to_list(length=20)
        result = []
        for doc in docs:
            clean = {k: v for k, v in doc.items() if k != "_id"}
            try:
                result.append(PendingOperation(**clean))
            except Exception as e:
                logger.warning("[HITL] Skip unresolved records: %s", e)
        return result

    async def decide(
        self,
        *,
        pending_id: str,
        decision: str,  # "confirmed" / "rejected"
        decided_by: str = "user",
    ) -> Optional[PendingOperation]:
        """Update status after user confirm/deny.

        Args:
            pending_id: Action to be confirmed ID
            decision: "confirmed" or "rejected"
            decided_by: decision maker (default "user") 

        Returns:
            The updated PendingOperation, or None if it does not exist or has been processed
        """
        now = datetime.now(timezone.utc).isoformat()
        result = await self._collection.update_one(
            {"pending_id": pending_id, "status": "pending"},
            {"$set": {
                "status": decision,
                "decided_at": now,
                "decided_by": decided_by,
            }},
        )
        if result.modified_count == 0:
            # It may not exist, or the status is no longer pending
            existing = await self.load_pending(pending_id)
            if existing:
                logger.warning(
                    "[HITL] The operation has been processed and no decision can be made again: pending_id=%s Current status=%s",
                    pending_id, existing.status,
                )
            else:
                logger.warning("[HITL] Operation does not exist: pending_id=%s", pending_id)
            return None

        logger.info(
            "[HITL] The operation has been decided: pending_id=%s decision=%s by=%s",
            pending_id, decision, decided_by,
        )
        return await self.load_pending(pending_id)

    async def expire_stale(self, hours: int = 24) -> int:
        """Clean up pending operations with timeout (default 24h).

        Args:
            hours: Timeout hours

        Returns:
            Number of expired operations
        """
        cutoff_dt = datetime.now(timezone.utc).timestamp() - hours * 3600
        cutoff_str = datetime.fromtimestamp(cutoff_dt, tz=timezone.utc).isoformat()
        result = await self._collection.update_many(
            {"status": "pending", "created_at": {"$lt": cutoff_str}},
            {"$set": {"status": "expired", "decided_by": "system_timeout"}},
        )
        if result.modified_count > 0:
            logger.info("[HITL] Cleanup timeout pending confirmation operation: %d (more than %dh)", result.modified_count, hours)
        return result.modified_count


def get_hitl_service(db: Any) -> "HITLCheckpointService":
    """Factory method (no singleton, caller caches on demand).

    Args:
        db: MongoDB Database handle

    Returns:
        HITLCheckpointService Example
    """
    return HITLCheckpointService(db)
