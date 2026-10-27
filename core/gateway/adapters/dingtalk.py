"""
DingTalk Bot Adapter

Implemented based on the Outgoing callback mode of DingTalk Robot, supporting:
- Single chat message
- group chat @Bot news
- Signature Verification (timestamp + sign) 
- Access Token Automatic management

DingTalk Open Platform Documentation: https://open.dingtalk.com/document/orgapp/robot-overview

Configuration items (stored in system_configs, config_key="gateway_dingtalk") :
{
    "app_key": "xxx",              # AppKey
    "app_secret": "xxx",           # AppSecret
    "robot_code": "xxx",           # Robot coding (for proactive messaging)
    "enabled": true
}
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote_plus

import httpx

from core.gateway.adapters.base import BaseGatewayAdapter
from core.gateway.models import (
    ChannelType,
    GatewayMessage,
    GatewayResponse,
    MessageType,
    ResponseType,
)

logger = logging.getLogger(__name__)

DINGTALK_API_BASE = "https://api.dingtalk.com"
DINGTALK_OLD_API = "https://oapi.dingtalk.com"


class DingTalkAdapter(BaseGatewayAdapter):
    """DingTalk Bot Adapter"""

    channel_type = ChannelType.DINGTALK

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Access Token management
    # ------------------------------------------------------------------ #

    async def _ensure_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at - 120:
            return self._access_token

        url = f"{DINGTALK_API_BASE}/v1.0/oauth2/accessToken"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "appKey": self.config["app_key"],
                "appSecret": self.config["app_secret"],
            })
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data.get("accessToken")
        expire_in = data.get("expireIn", 7200)
        self._token_expires_at = now + expire_in
        logger.info("[DingTalkAdapter] Access Token Refreshed, valid period %ss", expire_in)
        return self._access_token

    def _get_auth_headers(self, token: str) -> Dict[str, str]:
        return {
            "x-acs-dingtalk-access-token": token,
            "Content-Type": "application/json; charset=utf-8",
        }

    # ------------------------------------------------------------------ #
    # Webhook Verify
    # ------------------------------------------------------------------ #

    async def verify_request(
        self, headers: Dict[str, str], body: bytes
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify DingTalk Outgoing robot callback request.

        DingTalk is passed in the header timestamp + sign, 
        Use AppSecret to timestamp + "\\n" + AppSecret Do HMAC-SHA256 verification.
        """
        timestamp = headers.get("timestamp", "")
        sign = headers.get("sign", "")

        if not timestamp or not sign:
            # In the new version of DingTalk, some modes may not transmit signatures, and will be released and reminded in the log.
            logger.warning("[DingTalkAdapter] Missing signature header, released")
            return True, None

        app_secret = self.config.get("app_secret", "")
        if not app_secret:
            return True, None

        string_to_sign = f"{timestamp}\n{app_secret}"
        hmac_code = hmac.new(
            app_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_sign = quote_plus(base64.b64encode(hmac_code).decode("utf-8"))

        if sign != expected_sign:
            logger.warning("[DingTalkAdapter] Signature verification failed")
            return False, None

        return True, None

    # ------------------------------------------------------------------ #
    # Message parsing
    # ------------------------------------------------------------------ #

    async def parse_message(
        self, headers: Dict[str, str], body: bytes
    ) -> Optional[GatewayMessage]:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        msg_type = payload.get("msgtype", "")
        if msg_type != "text":
            logger.debug("[DingTalkAdapter] Ignore message type: %s", msg_type)
            return None

        text_content = payload.get("text", {}).get("content", "").strip()
        if not text_content:
            return None

        sender_id = payload.get("senderStaffId") or payload.get("senderId", "")
        sender_nick = payload.get("senderNick", "")
        conversation_id = payload.get("conversationId", "")
        conversation_type = payload.get("conversationType", "")
        # 1 = Private chat, 2 = group chat
        is_group = str(conversation_type) == "2"
        msg_id = payload.get("msgId", "")
        chatbot_user_id = payload.get("chatbotUserId", "")
        session_webhook = payload.get("sessionWebhook", "")

        if is_group:
            channel_id = f"group:{conversation_id}"
        else:
            channel_id = f"p2p:{sender_id}"

        is_command = text_content.startswith("/")

        return GatewayMessage(
            channel_type=ChannelType.DINGTALK,
            channel_id=channel_id,
            user_identity=sender_id,
            message_type=MessageType.COMMAND if is_command else MessageType.TEXT,
            content=text_content,
            is_mention_bot=True,
            metadata={
                "msg_id": msg_id,
                "conversation_id": conversation_id,
                "conversation_type": conversation_type,
                "sender_nick": sender_nick,
                "chatbot_user_id": chatbot_user_id,
                "session_webhook": session_webhook,
            },
        )

    # ------------------------------------------------------------------ #
    # message sending
    # ------------------------------------------------------------------ #

    async def send_response(self, response: GatewayResponse) -> bool:
        """
        Send a message to DingTalk.

        Prioritize using sessionWebhook (reply URL in Outgoing scenario),
        Otherwise use the active messaging API.
        """
        session_webhook = (response.metadata or {}).get("session_webhook")
        if session_webhook:
            return await self._send_via_webhook(session_webhook, response)

        return await self._send_via_api(response)

    async def _send_via_webhook(self, webhook_url: str, response: GatewayResponse) -> bool:
        """Reply via sessionWebhook (the simplest way)"""
        text = self.truncate_for_platform(response.content, max_length=4000)
        body = {
            "msgtype": "text",
            "text": {"content": text},
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=body)
            data = resp.json()
            if data.get("errcode", 0) == 0:
                logger.info("[DingTalkAdapter] Webhook Reply successful")
                return True
            else:
                logger.warning(
                    "[DingTalkAdapter] Webhook Reply failed: %s", data.get("errmsg")
                )
                return False
        except Exception as e:
            logger.exception("[DingTalkAdapter] Webhook Exception in reply: %s", e)
            return False

    async def _send_via_api(self, response: GatewayResponse) -> bool:
        """Actively send messages through DingTalk s open API"""
        token = await self._ensure_access_token()

        robot_code = self.config.get("robot_code", "")
        if not robot_code:
            logger.warning("[DingTalkAdapter] Missing robot_code, unable to actively send messages")
            return False

        channel_id = response.channel_id
        text = self.truncate_for_platform(response.content, max_length=4000)

        if channel_id.startswith("p2p:"):
            user_id = channel_id[4:]
            url = f"{DINGTALK_API_BASE}/v1.0/robot/oToMessages/batchSend"
            body = {
                "robotCode": robot_code,
                "userIds": [user_id],
                "msgKey": "sampleText",
                "msgParam": json.dumps({"content": text}, ensure_ascii=False),
            }
        elif channel_id.startswith("group:"):
            conversation_id = channel_id[6:]
            url = f"{DINGTALK_API_BASE}/v1.0/robot/groupMessages/send"
            body = {
                "robotCode": robot_code,
                "openConversationId": conversation_id,
                "msgKey": "sampleText",
                "msgParam": json.dumps({"content": text}, ensure_ascii=False),
            }
        else:
            logger.warning("[DingTalkAdapter] Unknown channel_id format: %s", channel_id)
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url, json=body, headers=self._get_auth_headers(token)
                )
            data = resp.json()
            if resp.status_code in (200, 201) and not data.get("code"):
                logger.info("[DingTalkAdapter] API Message sent successfully")
                return True
            else:
                logger.warning(
                    "[DingTalkAdapter] API Message sending failed: %s",
                    data.get("message") or data.get("errmsg"),
                )
                return False
        except Exception as e:
            logger.exception("[DingTalkAdapter] API Message sending exception: %s", e)
            return False

    def format_report_as_response(
        self, report_text: str, channel_id: str
    ) -> GatewayResponse:
        """Format analysis reports as DingTalk Markdown messages"""
        truncated = self.truncate_for_platform(report_text, max_length=3500)
        return GatewayResponse(
            channel_type=self.channel_type.value,
            channel_id=channel_id,
            response_type=ResponseType.MARKDOWN,
            content=truncated,
        )
