"""
GatewayRouter — Route distribution and message processing

Responsibilities:
1. Register and manage adapters for each platform
2. Receive raw Webhook / WebSocket events, delegate adapter resolves to GatewayMessage
3. Perform user identity mapping (IM user → system user) 
4. Call IntelligentAssistantService to process the message
5. Format assistant response as GatewayResponse, sent by delegate adapter
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

from core.gateway.adapters.base import BaseGatewayAdapter
from core.gateway.models import (
    GatewayMessage,
    GatewayResponse,
    MessageType,
    ResponseType,
)

logger = logging.getLogger(__name__)


class GatewayRouter:
    """Gateway Route distributor (singleton)"""

    def __init__(self):
        self._adapters: Dict[str, BaseGatewayAdapter] = {}
        self._ws_client = None          # QQWebSocketClient Example
        self._ws_task: Optional[asyncio.Task] = None  # WebSocket Background tasks

    # ------------------------------------------------------------------ #
    # Adapter management
    # ------------------------------------------------------------------ #

    def register_adapter(self, adapter: BaseGatewayAdapter) -> None:
        """Register a platform adapter"""
        key = adapter.channel_type.value if hasattr(adapter.channel_type, "value") else str(adapter.channel_type)
        self._adapters[key] = adapter
        logger.info("[Gateway] Registered adapter: %s", key)

    def get_adapter(self, platform: str) -> Optional[BaseGatewayAdapter]:
        return self._adapters.get(platform)

    @property
    def supported_platforms(self) -> list:
        return list(self._adapters.keys())

    # ------------------------------------------------------------------ #
    # core processing flow
    # ------------------------------------------------------------------ #

    async def handle_webhook(
        self,
        platform: str,
        headers: Dict[str, str],
        body: bytes,
        db,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        Handle webhook requests from the IM platform.

        Returns:
            (response_json, http_status_code)
            - response_json: JSON (Challenge or ack) that needs to be returned to the platform immediately
            - http_status_code: HTTP status code
        """
        adapter = self.get_adapter(platform)
        if not adapter:
            logger.warning("[Gateway] Unknown platform: %s", platform)
            return {"error": f"Unsupported platform: {platform}"}, 400

        # 1. Verify signature / Challenge
        is_valid, challenge_resp = await adapter.verify_request(headers, body)
        if challenge_resp is not None:
            # URL verification requests from Feishu and other platforms will be returned directly.
            return challenge_resp, 200
        if not is_valid:
            logger.warning("[Gateway] Signature verification failed: platform=%s", platform)
            return {"error": "Invalid signature"}, 403

        # 2. Parse the message
        message = await adapter.parse_message(headers, body)
        if message is None:
            # Event types that do not need to be processed (such as message withdrawal, user joining the group, etc.)
            return self._ack_response(platform), 200

        # 3. Handle /command type messages
        if message.message_type == MessageType.COMMAND:
            cmd_result = await self._handle_command(message, adapter, db, platform)
            # If it is not pass_through (unknown commands are processed as ordinary messages), return directly
            if message.message_type == MessageType.COMMAND:
                return cmd_result

        # 4. Single user mode: automatically associate with the first user of the system
        system_user_id = await self._resolve_user(db)
        if not system_user_id:
            logger.error("[Gateway] There is no user in the system and the message cannot be processed")
            return self._ack_response(platform), 200

        # 5. Call Assistant
        response = await self._invoke_assistant(
            message, system_user_id, db
        )

        # 6. Reply to the platform (asynchronous, not blocking webhook responses)
        try:
            await adapter.send_response(response)
        except Exception as e:
            logger.exception("[Gateway] Failed to send reply: %s", e)

        return self._ack_response(platform), 200

    @staticmethod
    def _ack_response(platform: str) -> Dict[str, Any]:
        """Generate platform-specific ACK response"""
        if platform == "qq":
            # QQ request return op=12 Indicates event received
            return {"op": 12}
        return {"status": "ok"}

    # ------------------------------------------------------------------ #
    # internal method
    # ------------------------------------------------------------------ #

    async def _resolve_user(self, db) -> Optional[str]:
        """Single user mode: Returns the first active user in the system ID"""
        user = await db.users.find_one(
            {"is_active": {"$ne": False}},
            {"_id": 1},
            sort=[("created_at", 1)],
        )
        if user:
            return str(user["_id"])
        return None

    async def _invoke_assistant(
        self,
        message: GatewayMessage,
        user_id: str,
        db,
    ) -> GatewayResponse:
        """Call IntelligentAssistantService to process the message"""
        from app.services.intelligent_assistant_service import chat_with_assistant
        from core.gateway.session import SessionManager, build_session_key
        from core.tools.context import set_current_im_channel

        channel_type_str = (
            message.channel_type.value
            if hasattr(message.channel_type, "value")
            else str(message.channel_type)
        )
        session_key = build_session_key(user_id, channel_type_str, message.channel_id)
        session_manager = SessionManager(db)
        session = await session_manager.get_or_create(user_id, channel_type_str, message.channel_id)
        current_topic_id = ((session.get("context") or {}).get("current_topic_id") or "").strip() or None

        # Sets the IM channel context for assistant_ops tools such as trigger_stock_analysis to
        # Save the callback channel information when creating a background task. After the task is completed, you can actively push notifications to this channel.
        set_current_im_channel(channel_type_str, message.channel_id)

        result = await chat_with_assistant(
            db=db,
            user_message=message.content,
            user_id=user_id,
            conversation_id=session_key,
            current_thread_id=current_topic_id,
            is_im=True,  # IM Channel: Inject mobile format specifications, LLM avoids outputting tables and Markdown
        )

        reply_text = result.get("reply", "Sorry, there was a problem processing the message.")
        return GatewayResponse(
            channel_type=message.channel_type,
            channel_id=message.channel_id,
            response_type=ResponseType.MARKDOWN,
            content=reply_text,
            metadata=message.metadata,  # Transparently transmit platform metadata (such as msg_id)
        )

    async def _handle_command(
        self,
        message: GatewayMessage,
        adapter: BaseGatewayAdapter,
        db,
        platform: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Handle slash commands (/help etc.)"""
        cmd = message.content.strip().lower()

        if cmd == "/help":
            help_text = (
                "📋 Available commands:\n"
                "/help — show help\n\n"
                "Send text directly to chat with the Analytics Assistant, for example:\n"
                "• Analysis of Kweichow Moutai\n"
                "• Which stocks were analyzed last week?\n"
                "• View my stock watchlist\n"
                "• What is the current topic\n"
                "• Switch to new energy vehicle research"
            )
            resp = GatewayResponse(
                channel_type=message.channel_type,
                channel_id=message.channel_id,
                response_type=ResponseType.TEXT,
                content=help_text,
                metadata=message.metadata,
            )
            await adapter.send_response(resp)
            return self._ack_response(platform), 200

        # Unknown command, when normal message processing
        message.message_type = MessageType.TEXT
        return self._ack_response(platform), 200

    # ------------------------------------------------------------------ #
    # Active push (notification of events such as analysis completion)
    # ------------------------------------------------------------------ #

    async def send_im_notification(
        self, channel_type: str, channel_id: str, text: str
    ) -> bool:
        """Actively push text messages to IM channels (no msg_id required, does not rely on user message triggering)

        Args:
            channel_type: Platform type, such as "qq", "feishu"
            channel_id:   Platform side session ID, such as "c2c:openid", "group:group_openid"
            text:         Plain text content

        Returns:
            True Indicates successful transmission, False indicates failure.
        """
        adapter = self.get_adapter(channel_type)
        if not adapter:
            logger.warning("[Gateway] Platform %s has no registered adapter and cannot send IM notifications", channel_type)
            return False

        response = GatewayResponse(
            channel_type=channel_type,
            channel_id=channel_id,
            response_type=ResponseType.TEXT,
            content=text,
            metadata={},  # Without msg_id → Active push
        )
        try:
            result = await adapter.send_response(response)
            if result:
                logger.info("[Gateway] ✅ IM Notification sent successfully: %s/%s", channel_type, channel_id)
            else:
                logger.warning("[Gateway] IM Notification failed to send: %s/%s", channel_type, channel_id)
            return result
        except Exception as e:
            logger.exception("[Gateway] IM Notification sending exception: %s", e)
            return False

    # ------------------------------------------------------------------ #
    # WebSocket Schema management
    # ------------------------------------------------------------------ #

    async def start_ws_client(self, config: Dict[str, Any], db):
        """Start the QQ WebSocket client background task"""
        await self.stop_ws_client()  # Stop existing ones first

        from core.gateway.adapters.qq_ws import QQWebSocketClient
        from core.gateway.adapters.qq import QQAdapter

        # Make sure the QQ adapter is registered (for sending replies)
        if "qq" not in self._adapters:
            adapter = QQAdapter(config=config)
            self.register_adapter(adapter)

        async def on_event(event_type: str, data: dict, raw: dict):
            await self._handle_ws_event(event_type, data, raw, db)

        self._ws_client = QQWebSocketClient(
            config=config,
            on_event=on_event,
            sandbox=config.get("sandbox", False),
        )
        self._ws_task = asyncio.create_task(self._ws_client.start())
        logger.info("[Gateway] QQ WebSocket Background task started")

    async def stop_ws_client(self):
        """Stop QQ WebSocket client"""
        if self._ws_client:
            await self._ws_client.stop()
            self._ws_client = None
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
            logger.info("[Gateway] QQ WebSocket Background task stopped")

    @property
    def ws_running(self) -> bool:
        return self._ws_task is not None and not self._ws_task.done()

    async def _handle_ws_event(
        self, event_type: str, data: dict, raw: dict, db
    ):
        """Handle Dispatch events received from WebSocket"""
        adapter = self.get_adapter("qq")
        if not adapter:
            logger.warning("[Gateway] QQ Adapter is not registered and cannot handle WS events")
            return

        # Reuse QQAdapter's message parsing logic
        # Construct a payload in the same format as the Webhook for reuse parse_message
        fake_body = json.dumps(raw).encode("utf-8")
        message = await adapter.parse_message({}, fake_body)
        if message is None:
            return

        # command processing
        if message.message_type == MessageType.COMMAND:
            await self._handle_command(message, adapter, db, "qq")
            if message.message_type == MessageType.COMMAND:
                return  # command processed

        # User analysis
        system_user_id = await self._resolve_user(db)
        if not system_user_id:
            logger.error("[Gateway] There is no user in the system and the WS message cannot be processed")
            return

        # Call Assistant
        response = await self._invoke_assistant(message, system_user_id, db)

        # Send reply
        try:
            await adapter.send_response(response)
        except Exception as e:
            logger.exception("[Gateway] WS Message reply failed: %s", e)


# Global singleton
gateway_router = GatewayRouter()


def get_gateway_router() -> GatewayRouter:
    """Get the GatewayRouter global singleton"""
    return gateway_router

