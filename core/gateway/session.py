"""
Gateway Multi-channel session management

Session Key Format: {user_id}:{channel_type}:{channel_id}

- The same user s sessions on the Web and Feishu are completely independent
- Session stored in MongoDB `gateway_sessions` collection
- Automatically crop conversation history (retain the most recent N rounds)
- TTL Index automatic cleaning expired Session
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# By default, the last 20 rounds of conversations are retained
DEFAULT_MAX_HISTORY = 20
# Session Expiration time (seconds)— 7 day
SESSION_TTL_SECONDS = 7 * 24 * 3600

COLLECTION_NAME = "gateway_sessions"


def build_session_key(user_id: str, channel_type: str, channel_id: str) -> str:
    """Construct Gateway Session Key."""
    return f"{user_id}:{channel_type}:{channel_id}"


class SessionManager:
    """
    Gateway Session Manager

    Each Session contains:
    - session_key: "{user_id}:{channel_type}:{channel_id}"
    - user_id: system user ID
    - channel_type: platform type
    - channel_id: platform session ID
    - messages: Conversation history list
    - context: Context state (such as previous task_id, etc.)
    - created_at / updated_at
    """

    def __init__(self, db, max_history: int = DEFAULT_MAX_HISTORY):
        self.db = db
        self.collection = db[COLLECTION_NAME]
        self.max_history = max_history

    async def ensure_indexes(self) -> None:
        """Create index (called once when the application starts)"""
        # Unique index: quick search by session_key
        await self.collection.create_index("session_key", unique=True)
        # TTL Index: Automatic cleanup expired Session
        await self.collection.create_index(
            "updated_at", expireAfterSeconds=SESSION_TTL_SECONDS
        )
        logger.info("[SessionManager] Index creation completed")

    async def get_or_create(
        self,
        user_id: str,
        channel_type: str,
        channel_id: str,
    ) -> Dict[str, Any]:
        """Get or create Session"""
        session_key = build_session_key(user_id, channel_type, channel_id)
        now = datetime.now(timezone.utc)

        session = await self.collection.find_one({"session_key": session_key})
        if session:
            # Update last active time
            await self.collection.update_one(
                {"session_key": session_key},
                {"$set": {"updated_at": now}},
            )
            return session

        # create new Session
        new_session = {
            "session_key": session_key,
            "user_id": user_id,
            "channel_type": channel_type,
            "channel_id": channel_id,
            "messages": [],
            "context": {},
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(new_session)
        logger.info("[SessionManager] New Session: %s", session_key)
        return new_session

    async def get_current_topic_id(self, session_key: str) -> Optional[str]:
        """Get the research topic ID bound to the current Session."""
        session = await self.collection.find_one(
            {"session_key": session_key},
            {"context.current_topic_id": 1},
        )
        if not session:
            return None
        context = session.get("context") or {}
        current_topic_id = (context.get("current_topic_id") or "").strip()
        return current_topic_id or None

    async def set_current_topic_id(self, session_key: str, topic_id: Optional[str]) -> None:
        """Set the research topic ID bound to the current Session."""
        await self.update_context(session_key, {"current_topic_id": topic_id or None})

    async def append_message(
        self,
        session_key: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a message to the Session conversation history"""
        now = datetime.now(timezone.utc)
        msg = {
            "role": role,
            "content": content,
            "timestamp": now,
        }
        if metadata:
            msg["metadata"] = metadata

        await self.collection.update_one(
            {"session_key": session_key},
            {
                "$push": {
                    "messages": {
                        "$each": [msg],
                        "$slice": -self.max_history,  # Keep the most recent N items
                    }
                },
                "$set": {"updated_at": now},
            },
        )

    async def get_history(
        self, session_key: str
    ) -> List[Dict[str, Any]]:
        """Get Session s conversation history"""
        session = await self.collection.find_one(
            {"session_key": session_key},
            {"messages": 1},
        )
        return session.get("messages", []) if session else []

    async def update_context(
        self, session_key: str, context_updates: Dict[str, Any]
    ) -> None:
        """Update Session context (such as the most recent task_id)"""
        now = datetime.now(timezone.utc)
        set_fields = {f"context.{k}": v for k, v in context_updates.items()}
        set_fields["updated_at"] = now
        await self.collection.update_one(
            {"session_key": session_key},
            {"$set": set_fields},
        )

    async def clear_session(self, session_key: str) -> bool:
        """Clear Session conversation history and context"""
        result = await self.collection.update_one(
            {"session_key": session_key},
            {"$set": {
                "messages": [],
                "context": {},
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return result.modified_count > 0

    async def delete_session(self, session_key: str) -> bool:
        """Delete Session"""
        result = await self.collection.delete_one({"session_key": session_key})
        return result.deleted_count > 0

