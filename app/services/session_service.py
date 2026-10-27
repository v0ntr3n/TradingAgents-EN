"""
User session management service

Provides session creation, verification, revocation and other functions to solve the problem that JWT Token cannot be revoked
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from pymongo.database import Database
from app.models.user import UserSession

logger = logging.getLogger(__name__)


class SessionService:
    """用户会话管理服务"""
    
    def __init__(self, db: Database):
        self.db = db
        self.sessions_collection = db.user_sessions
        
        # Create index
        self._create_indexes()
    
    def _create_indexes(self):
        """创建索引"""
        try:
            # session_id unique index
            self.sessions_collection.create_index("session_id", unique=True)
            
            # user_id Index (used to query all sessions of a user)
            self.sessions_collection.create_index("user_id")
            
            # expires_at Index (for automatic cleaning of expired sessions)
            self.sessions_collection.create_index("expires_at", expireAfterSeconds=0)
            
            logger.debug("✅ Session Index created successfully")
        except Exception as e:
            logger.warning(f"⚠️ Session Index creation failed: {e}")

    def _get_session_ttl_seconds(self, session_doc: dict) -> int:
        """Restore original TTL from session document for active renewal."""
        ttl_seconds = session_doc.get("session_ttl_seconds")
        if isinstance(ttl_seconds, (int, float)) and ttl_seconds > 0:
            return int(ttl_seconds)

        created_at = session_doc.get("created_at")
        expires_at = session_doc.get("expires_at")
        if isinstance(created_at, datetime) and isinstance(expires_at, datetime):
            inferred = int((expires_at - created_at).total_seconds())
            if inferred > 0:
                return inferred

        return 3600
    
    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expires_in_seconds: int = 3600  # Default 1 hour
    ) -> str:
        """
        Create new session
        
        Args:
            user_id: User ID
            ip_address: IP address
            user_agent: User-Agent
            expires_in_seconds: Expiration time (seconds)
            
        Returns:
            session_id: session ID
        """
        try:
            # generate unique session_id
            session_id = secrets.token_urlsafe(32)

            # 🔥 Use UTC time (naive datetime) to store MongoDB
            # This avoids time zone comparison issues
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            expires_at_utc = now_utc + timedelta(seconds=expires_in_seconds)

            session_doc = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": now_utc,
                "expires_at": expires_at_utc,
                "session_ttl_seconds": expires_in_seconds,
                "last_activity": now_utc,
                "ip_address": ip_address,
                "user_agent": user_agent
            }

            self.sessions_collection.insert_one(session_doc)
            
            logger.info(f"✅ Create session: user_id={user_id}, session_id={session_id[:16]}..., expires_at={expires_at_utc} UTC")
            return session_id
            
        except Exception as e:
            logger.error(f"❌ 创建会话失败: {e}")
            raise
    
    def verify_session(self, session_id: str, update_activity: bool = True) -> Optional[UserSession]:
        """
        Verify session is valid
        
        Args:
            session_id: session ID
            update_activity: Whether to update the last activity time
            
        Returns:
            UserSession: Session information, returned if invalid None
        """
        try:
            session_doc = self.sessions_collection.find_one({"session_id": session_id})

            if not session_doc:
                logger.debug(f"❌ 会话不存在: {session_id[:16]}...")
                return None

            # Check for expiration (using UTC time)
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            expires_at = session_doc["expires_at"]

            if expires_at < now_utc:
                logger.debug(f"⏰ 会话已过期: {session_id[:16]}...")
                # Delete expired session
                self.sessions_collection.delete_one({"session_id": session_id})
                return None

            # Update last activity time
            if update_activity:
                renewed_expires_at = now_utc + timedelta(seconds=self._get_session_ttl_seconds(session_doc))
                self.sessions_collection.update_one(
                    {"session_id": session_id},
                    {"$set": {"last_activity": now_utc, "expires_at": renewed_expires_at}}
                )
                session_doc["last_activity"] = now_utc
                session_doc["expires_at"] = renewed_expires_at
            
            logger.debug(f"✅ Session is valid: user_id={session_doc['user_id']}, session_id={session_id[:16]}...")
            return UserSession(**session_doc)
            
        except Exception as e:
            logger.error(f"❌ 验证会话失败: {e}")
            return None
    
    def revoke_session(self, session_id: str) -> bool:
        """
        Revoke session (log out)

        Args:
            session_id: session ID

        Returns:
            bool: Is it successful?
        """
        try:
            result = self.sessions_collection.delete_one({"session_id": session_id})

            if result.deleted_count > 0:
                logger.info(f"✅ 撤销会话: {session_id[:16]}...")
                return True
            else:
                logger.warning(f"⚠️ 会话不存在: {session_id[:16]}...")
                return False

        except Exception as e:
            logger.error(f"❌ 撤销会话失败: {e}")
            return False

    def revoke_all_user_sessions(self, user_id: str) -> int:
        """
        Revoke all user sessions (change password, force logout, etc.)

        Args:
            user_id: User ID

        Returns:
            int: Number of sessions revoked
        """
        try:
            result = self.sessions_collection.delete_many({"user_id": user_id})
            count = result.deleted_count

            logger.info(f"✅ Revoke all user sessions: user_id={user_id}, count={count}")
            return count

        except Exception as e:
            logger.error(f"❌ Failed to revoke all user sessions: {e}")
            return 0

    def get_user_sessions(self, user_id: str) -> list[UserSession]:
        """
        Get all active sessions of a user

        Args:
            user_id: User ID

        Returns:
            list[UserSession]: Conversation list
        """
        try:
            # 🔥 Query using UTC time (consistent with storage)
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

            sessions = self.sessions_collection.find({
                "user_id": user_id,
                "expires_at": {"$gt": now_utc}
            }).sort("last_activity", -1)

            return [UserSession(**s) for s in sessions]

        except Exception as e:
            logger.error(f"❌ 获取用户会话失败: {e}")
            return []

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions (scheduled tasks)

        Returns:
            int: Number of sessions cleaned
        """
        try:
            # 🔥 Query using UTC time
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

            result = self.sessions_collection.delete_many({"expires_at": {"$lt": now_utc}})
            count = result.deleted_count

            if count > 0:
                logger.info(f"🧹 Clean up expired sessions: count={count}")

            return count

        except Exception as e:
            logger.error(f"❌ 清理过期会话失败: {e}")
            return 0


# Global SessionService instance
_session_service: Optional[SessionService] = None


def get_session_service(db: Optional[Database] = None) -> SessionService:
    """
    Get SessionService singleton

    Note: SessionService uses synchronous MongoDB operations,
    Therefore it is necessary to use get_mongo_db_sync() instead of get_mongo_db()
    """
    global _session_service

    if _session_service is None:
        if db is None:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()  # 🔥 Use a synchronized database connection

        _session_service = SessionService(db)

    return _session_service

