"""
Gateway User identity mapping

IM Platform user (open_id / QQ number / DingTalk userId)→ System user_id mapping.

Binding process:
1. User sends in IM /bind
2. The system generates a one-time verification code and deposits it pending_bindings
3. The user enters the verification code in the Web UI to complete the binding.
4. Binding records are written to the user_identity_mappings collection

Set structure (user_identity_mappings):
{
    "user_id": "60f1a2b3c4d5e6f7a8b9c0d1",
    "platform": "feishu",
    "platform_identity": "ou_xxxxxxxxx",
    "display_name": "Zhang San",
    "bound_at": ISODate("2026-03-04T08:00:00Z"),
    "is_active": true
}

Set structure (gateway_pending_bindings):
{
    "code": "A3X9K2",
    "platform": "feishu",
    "platform_identity": "ou_xxxxxxxxx",
    "channel_id": "oc_xxx",
    "display_name": "Zhang San",
    "created_at": ISODate("2026-03-04T08:00:00Z"),
    "expires_at": ISODate("2026-03-04T08:10:00Z")   // TTL 10 minutes
}
"""

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MAPPINGS_COLLECTION = "user_identity_mappings"
PENDING_COLLECTION = "gateway_pending_bindings"
BIND_CODE_LENGTH = 6
BIND_CODE_TTL_MINUTES = 10


class UserMappingManager:
    """User Identity Mapping Manager"""

    def __init__(self, db):
        self.db = db
        self.mappings = db[MAPPINGS_COLLECTION]
        self.pending = db[PENDING_COLLECTION]

    async def ensure_indexes(self) -> None:
        """Create index (called once when the application starts)"""
        # Composite unique index: a platform user can only be bound to one system user
        await self.mappings.create_index(
            [("platform", 1), ("platform_identity", 1)],
            unique=True,
        )
        await self.mappings.create_index("user_id")

        # pending TTL index of
        await self.pending.create_index(
            "expires_at", expireAfterSeconds=0
        )
        await self.pending.create_index("code", unique=True)
        logger.info("[UserMapping] Index creation completed")

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    async def get_system_user_id(
        self, platform: str, platform_identity: str
    ) -> Optional[str]:
        """Query the system corresponding to the IM user user_id"""
        doc = await self.mappings.find_one({
            "platform": platform,
            "platform_identity": platform_identity,
            "is_active": True,
        })
        return doc["user_id"] if doc else None

    async def get_platform_identities(self, user_id: str) -> list:
        """Query all platform identities bound to system users"""
        cursor = self.mappings.find(
            {"user_id": user_id, "is_active": True},
            {"platform": 1, "platform_identity": 1, "display_name": 1},
        )
        return await cursor.to_list(length=50)

    # ------------------------------------------------------------------ #
    # Binding process
    # ------------------------------------------------------------------ #

    async def create_bind_code(
        self,
        platform: str,
        platform_identity: str,
        channel_id: str,
        display_name: Optional[str] = None,
    ) -> str:
        """Generate one-time binding verification code"""
        code = self._generate_code()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=BIND_CODE_TTL_MINUTES)

        # If there is already pending, replace
        await self.pending.delete_many({
            "platform": platform,
            "platform_identity": platform_identity,
        })

        await self.pending.insert_one({
            "code": code,
            "platform": platform,
            "platform_identity": platform_identity,
            "channel_id": channel_id,
            "display_name": display_name,
            "created_at": now,
            "expires_at": expires,
        })
        logger.info(
            "[UserMapping] Generate binding code: platform=%s, identity=%s, code=%s",
            platform, platform_identity, code,
        )
        return code

    async def confirm_bind(self, code: str, user_id: str) -> Optional[dict]:
        """
        Web End-to-end confirmation binding: Use code to find the pending record and create a formal mapping.

        Returns:
            Binding information dict, or None (code does not exist/has expired)
        """
        pending = await self.pending.find_one_and_delete({"code": code})
        if not pending:
            return None

        now = datetime.now(timezone.utc)
        mapping = {
            "user_id": user_id,
            "platform": pending["platform"],
            "platform_identity": pending["platform_identity"],
            "display_name": pending.get("display_name"),
            "bound_at": now,
            "is_active": True,
        }

        # upsert: same platform+identity Keep only one
        await self.mappings.update_one(
            {
                "platform": pending["platform"],
                "platform_identity": pending["platform_identity"],
            },
            {"$set": mapping},
            upsert=True,
        )
        logger.info(
            "[UserMapping] Binding successful: user_id=%s, platform=%s, identity=%s",
            user_id, pending["platform"], pending["platform_identity"],
        )
        return mapping


    async def unbind(
        self, user_id: str, platform: str, platform_identity: str
    ) -> bool:
        """Unbind platform identity"""
        result = await self.mappings.update_one(
            {
                "user_id": user_id,
                "platform": platform,
                "platform_identity": platform_identity,
            },
            {"$set": {"is_active": False}},
        )
        return result.modified_count > 0

    # ------------------------------------------------------------------ #
    # Tool method
    # ------------------------------------------------------------------ #

    @staticmethod
    def _generate_code() -> str:
        """Generate 6 uppercase letters+Numeric verification code"""
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(BIND_CODE_LENGTH))