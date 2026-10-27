"""
Channel push scheduler (ChannelNotifier)

Core Responsibilities:
1. Read user in MongoDB `user_channel_configs` Channel list configured in
2. Filter: push only enabled channels + This channel is subscribed to channels of this event_type
3. Concurrent fire-and-forget sending without blocking the caller

Integration points:NotificationsService.create_and_publish() Call at the end dispatch()
"""
import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_mongo_db
from app.models.channel_config import ChannelConfig, ChannelType
from app.utils.timezone import now_tz

logger = logging.getLogger("webapi.channel_notifier")

COLLECTION = "user_channel_configs"


class ChannelNotifier:
    """Unified channel push scheduler (single case)"""

    # -------------------------------------------------------------------------
    # MongoDB CRUD helpers
    # -------------------------------------------------------------------------

    async def get_channels(self, user_id: str) -> List[ChannelConfig]:
        """获取用户所有渠道配置"""
        db = get_mongo_db()
        doc = await db[COLLECTION].find_one({"user_id": user_id})
        if not doc:
            return []
        return [ChannelConfig(**ch) for ch in doc.get("channels", [])]

    async def save_channels(self, user_id: str, channels: List[ChannelConfig]) -> None:
        """Save user channel configuration (overwrite)"""
        db = get_mongo_db()
        await db[COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "channels": [ch.model_dump() for ch in channels],
                "updated_at": now_tz().isoformat(),
            }},
            upsert=True,
        )

    async def add_channel(self, user_id: str, channel: ChannelConfig) -> ChannelConfig:
        channels = await self.get_channels(user_id)
        channel.channel_id = str(uuid.uuid4())
        channel.created_at = now_tz().isoformat()
        channel.updated_at = channel.created_at
        channels.append(channel)
        await self.save_channels(user_id, channels)
        return channel

    async def update_channel(
        self, user_id: str, channel_id: str, updates: Dict[str, Any]
    ) -> Optional[ChannelConfig]:
        channels = await self.get_channels(user_id)
        for ch in channels:
            if ch.channel_id == channel_id:
                for k, v in updates.items():
                    if v is not None and hasattr(ch, k):
                        setattr(ch, k, v)
                ch.updated_at = now_tz().isoformat()
                await self.save_channels(user_id, channels)
                return ch
        return None

    async def delete_channel(self, user_id: str, channel_id: str) -> bool:
        channels = await self.get_channels(user_id)
        new_channels = [ch for ch in channels if ch.channel_id != channel_id]
        if len(new_channels) == len(channels):
            return False
        await self.save_channels(user_id, new_channels)
        return True

    # -------------------------------------------------------------------------
    # Core push logic
    # -------------------------------------------------------------------------

    async def dispatch(
        self,
        user_id: str,
        title: str,
        content: str,
        event_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Scheduling pushes to all matching channels for users (fire-and-forget)

        Args:
            user_id:    User ID
            title:      Notification title
            content:    Notification content
            event_type: event type, see channel_config.EVENT_TYPES
            metadata:   Extended metadata. If _im_channel is included, QQ IM notifications will be automatically pushed
        """
        metadata = metadata or {}

        # ① QQ IM Automatic callback channel (determined by the trigger source, no manual configuration required by the user)
        im_channel = metadata.get("_im_channel")
        if im_channel:
            asyncio.ensure_future(self._send_im_notification(im_channel, title, content))

        # ② External channels configured by users (Feishu/DingTalk/Qiwei/Email)
        try:
            channels = await self.get_channels(user_id)
        except Exception as e:
            logger.warning(f"Failed to obtain channel configuration(ignore): {e}")
            return

        # Filtering: enabled + Subscribed to this event type
        matched = [
            ch for ch in channels
            if ch.enabled and event_type in ch.events
        ]

        if not matched:
            return

        # Send concurrently, errors are not propagated
        tasks = [self._send_one(ch, title, content) for ch in matched]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_one(self, channel: ChannelConfig, title: str, content: str) -> None:
        """Send to a single channel and automatically catch exceptions"""
        try:
            if channel.type in (
                ChannelType.FEISHU, ChannelType.DINGTALK, ChannelType.WECHATWORK
            ):
                from app.services.channel_senders.webhook_sender import send_webhook
                await send_webhook(channel, title, content)

            elif channel.type == ChannelType.EMAIL:
                await self._send_email(channel, title, content)

        except Exception as e:
            logger.error(f"❌ 渠道推送异常 [{channel.name}]: {e}")

    async def _send_im_notification(
        self, im_channel: Dict[str, Any], title: str, content: str
    ) -> None:
        """Actively push notifications to IM channels through GatewayRouter (QQ / Feishu Bot, etc.)"""
        try:
            from core.gateway.router import get_gateway_router
            gateway_router = get_gateway_router()
            if gateway_router is None:
                logger.warning("[ChannelNotifier] GatewayRouter Not initialized, skip IM push")
                return

            channel_type = im_channel.get("channel_type", "")
            channel_id = im_channel.get("channel_id", "")
            if not channel_type or not channel_id:
                logger.warning("[ChannelNotifier] _im_channel Incomplete format: %s", im_channel)
                return

            text = f"{title}\n{content}" if content else title
            logger.info("[ChannelNotifier] Push IM notifications: %s/%s", channel_type, channel_id)
            await gateway_router.send_im_notification(channel_type, channel_id, text)
        except Exception as e:
            logger.error("[ChannelNotifier] IM Push failed: %s", e)

    async def _send_email(self, channel: ChannelConfig, title: str, content: str) -> None:
        """Send email channel notifications through existing EmailService"""
        if not channel.email_address:
            logger.warning(f"邮件渠道 [{channel.name}] 未配置邮箱地址，跳过")
            return

        from app.services.email_service import get_email_service
        from app.models.email import EmailType

        email_service = get_email_service()
        smtp_config = await email_service.get_smtp_config()
        if not smtp_config:
            logger.debug("SMTP Not configured, skip email channel push")
            return

        await email_service._send_smtp(
            to_email=channel.email_address,
            subject=f"[TradingAgents-CN] {title}",
            html_content=f"<p>{content}</p>",
            text_content=content,
            smtp_config=smtp_config,
        )
        logger.info(f"✅ Email channel push successful: [{channel.name}] -> {channel.email_address}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_channel_notifier: Optional[ChannelNotifier] = None


def get_channel_notifier() -> ChannelNotifier:
    global _channel_notifier
    if _channel_notifier is None:
        _channel_notifier = ChannelNotifier()
    return _channel_notifier

