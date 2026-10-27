"""
MCP Server Authentication module

realize API Key → user_id Mapping:
1. The client carries Bearer Token (API Key) when connecting to MCP
2. TokenVerifier Find matching from system_configs collection mcp_api_keys
3. After the verification is passed, write mapped_user_id into AccessToken.client_id
4. MCP The tool obtains the current user through Context.client_id ID

Database structure (system_configs collection):
{
    "config_key": "mcp_auth",
    "category": "mcp",
    "api_keys": [
        {
            "key": "sk-mcp-xxxx",
            "user_id": "60f1a2b3c4d5e6f7a8b9c0d1",
            "name": "mine Claude Desktop",
            "daily_quota": 50,
            "enabled": true
        }
    ]
}
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)


class MCPApiKeyVerifier:
    """API Key-Based MCP Authenticator

    Verify API Key from MongoDB system_configs collection,
    And maps the associated user_id to AccessToken.client_id.
    """

    def __init__(self, required_scopes: list[str] | None = None):
        self.required_scopes = required_scopes or ["mcp:tools"]
        self._config_cache: Optional[dict] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minutes cache

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify Bearer Token (API Key), return AccessToken or None

        Args:
            token: Incoming from client Bearer Token

        Returns:
            AccessToken (client_id is the mapped user_id) or None (validation failed)
        """
        if not token:
            logger.warning("🔒 MCP Authentication failed: empty token")
            return None

        key_entry = await self._find_api_key(token)
        if not key_entry:
            logger.warning("🔒 MCP Authentication failed: Invalid API Key")
            return None

        if not key_entry.get("enabled", True):
            logger.warning(f"🔒 MCP Authentication failed: API Key Disabled ({key_entry.get('name', 'unknown')})")
            return None

        # Check daily quota
        user_id = key_entry["user_id"]
        daily_quota = key_entry.get("daily_quota", 0)
        if daily_quota > 0:
            within_quota = await self._check_daily_quota(user_id, daily_quota)
            if not within_quota:
                logger.warning(f"🔒 MCP Quota exceeded: user={user_id}, quota={daily_quota}")
                return None

        logger.info(f"✅ MCP Authentication successful: user={user_id}, name={key_entry.get('name', 'N/A')}")

        # Put user_id into client_id, the tool obtains it through ctx.client_id
        return AccessToken(
            token=token,
            client_id=user_id,
            scopes=self.required_scopes,
        )

    async def _find_api_key(self, token: str) -> Optional[dict]:
        """Find matching API Key configuration from database"""
        config = await self._get_mcp_config()
        if not config:
            return None

        api_keys = config.get("api_keys", [])
        for entry in api_keys:
            if entry.get("key") == token:
                return entry
        return None

    async def _get_mcp_config(self) -> Optional[dict]:
        """Get MCP authentication configuration (with cache)"""
        now = datetime.now(timezone.utc)

        # Check cache
        if (
            self._config_cache is not None
            and self._cache_time is not None
            and (now - self._cache_time).total_seconds() < self._cache_ttl_seconds
        ):
            return self._config_cache

        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            config = await db.system_configs.find_one(
                {"config_key": "mcp_auth", "category": "mcp"}
            )
            self._config_cache = config
            self._cache_time = now
            return config
        except Exception as e:
            logger.error(f"❌ Failed to read MCP authentication configuration: {e}")
            return self._config_cache  # Downgrade to use old cache

    async def _check_daily_quota(self, user_id: str, daily_quota: int) -> bool:
        """Check whether the user s MCP analysis times today are within the quota"""
        try:
            from bson import ObjectId
            from app.core.database import get_mongo_db
            db = get_mongo_db()

            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # user_id Stored as ObjectId in database, needs to be converted
            # Mark the source via task_params._mcp_source (written when analyze_stock is created)
            count = await db.unified_analysis_tasks.count_documents({
                "user_id": ObjectId(user_id),
                "created_at": {"$gte": today_start},
                "task_params._mcp_source": True,
            })
            return count < daily_quota
        except Exception as e:
            logger.error(f"❌ Quota check failed: {e}")
            return True  # Release when errors occur to avoid blocking service


# ── Module-level convenience examples ──
mcp_auth = MCPApiKeyVerifier()

