"""Intelligent Assistant Quality Architecture (A11)—— Quality buried point (stage 4, S9).

Each assistant conversation turn direction ``assistant_quality_events`` The collection writes an event, covering:
- Route hit: route_id/route_priority/route_type/passthrough;
- Quality defense line: gate passing or not, failed check items, whether to be downgraded to fallback_evidence,
  Main path automatic error correction retry signal (unsourced/untraced/fabricated, etc.);
- Output form: streaming, reply length, number of data_refs/evidence, time consumption, errors.

Design constraints:
- **Never affect the main link**: The library is fire-and-forget (create_task), any exceptions will only be recorded
  debug Log, do not throw upward;
- Only the original events for offline statistics are retained (no TTL is set), and aggregation/kanban is a follow-up work (D6:
  Get the true failure distribution first before deciding whether to invest in LLM intent classification/referencing).

This module does not import service; db is passed in as a parameter (service holds the connection).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AssistantQualityMetrics:
    """Quality event dropper (in-process singleton)."""

    COLLECTION = "assistant_quality_events"

    def __init__(self) -> None:
        self._indexes_ready = False

    async def create_indexes(self, db=None) -> None:
        """Initialize the collection index (called when the application starts; failure does not affect startup)."""
        if db is None:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
        coll = db[self.COLLECTION]
        await coll.create_index([("created_at", -1)])
        await coll.create_index([("route_id", 1), ("created_at", -1)])
        await coll.create_index([("streaming", 1), ("created_at", -1)])
        self._indexes_ready = True

    def record(self, db=None, **fields: Any) -> None:
        """Record a quality event (fire-and-forget, never throw exception).

        The caller is within the event loop; if there is currently no running loop (such as a single test synchronization context),
        give up silently——Hiding points cannot block or slow down the main link.
        """
        try:
            import asyncio
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("[Quality issues] No running event loop, discard events: %s", fields.get("route_id"))
            return
        if db is None:
            logger.debug("[Quality issues] No db handle, event discarded: %s", fields.get("route_id"))
            return
        event = {"created_at": datetime.now(timezone.utc), **fields}
        loop.create_task(self._insert(db, event))

    async def _insert(self, db, event: Dict[str, Any]) -> None:
        try:
            if not self._indexes_ready:
                await self.create_indexes(db)
            await db[self.COLLECTION].insert_one(event)
        except Exception as exc:  # Failure to bury the point will never affect the dialogue
            logger.debug("[Quality issues] Failed to drop into library (ignored): %s", exc)

    async def recent(self, db=None, limit: int = 50) -> list:
        """Read recent events (troubleshooting/offline statistics assistance)."""
        if db is None:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
        cursor = db[self.COLLECTION].find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]


# Module-level singleton (service shared by two adapters)
quality_metrics = AssistantQualityMetrics()
