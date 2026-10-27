"""
QQ Bot adapter

Implemented based on QQ open platform Webhook callback mode, supporting:
- C2C Single chat message (C2C_MESSAGE_CREATE)
- group chat @Bot Message (GROUP_AT_MESSAGE_CREATE)
- ed25519 Signature verification + Callback address verification (op=13) 
- AccessToken Automatic management (7200s validity period)

QQ Bot API Documentation: https://bot.q.qq.com/wiki/develop/api-v2/

Configuration items (stored in system_configs, config_key="gateway_qq") :
{
    "app_id": "xxx",
    "app_secret": "xxx",         # clientSecret
    "bot_secret": "xxx",         # for webhook signature verification secret
}
"""

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.gateway.adapters.base import BaseGatewayAdapter
from core.gateway.models import (
    ChannelType,
    GatewayMessage,
    MessageType,
    GatewayResponse,
)

logger = logging.getLogger(__name__)

QQ_API_BASE = "https://api.sgroup.qq.com"
QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"


class QQAdapter(BaseGatewayAdapter):
    """QQ Bot Adapter (Webhook mode)"""

    channel_type = ChannelType.QQ

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    # AccessToken management
    # ------------------------------------------------------------------ #

    async def _ensure_access_token(self) -> str:
        """Get or refresh AccessToken"""
        now = time.time()
        # Refresh 120s in advance
        if self._access_token and now < self._token_expires_at - 120:
            return self._access_token

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(QQ_TOKEN_URL, json={
                "appId": self.config["app_id"],
                "clientSecret": self.config["app_secret"],
            })
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._token_expires_at = now + int(data.get("expires_in", 7200))
        logger.info("[QQAdapter] AccessToken Refreshed, valid period %ss", data.get("expires_in"))
        return self._access_token

    def _get_auth_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Webhook Signature verification
    # ------------------------------------------------------------------ #

    async def verify_request(
        self, headers: Dict[str, str], body: bytes
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify QQ webhook requests.

        - op=13: Callback address verification, needs to be returned with ed25519 signature
        - Others: Ordinary event push, verify signature header
        """
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, None

        op = payload.get("op")

        # op=13: Callback address verification
        if op == 13:
            return True, self._handle_validation(payload)

        # Common event: Verify signature in request header
        # QQ Webhook Pass signature information in header
        # Currently simplified processing: verify origin via X-Bot-Appid
        bot_appid = headers.get("x-bot-appid", "")
        if bot_appid and bot_appid == self.config.get("app_id", ""):
            return True, None

        # If there is no appid header, it will also pass (some versions may not have it)
        if not bot_appid:
            logger.warning("[QQAdapter] Missing X-Bot-Appid header, allowed")
            return True, None

        return False, None

    def _handle_validation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process op=13 Callback address verification"""
        d = payload.get("d", {})
        plain_token = d.get("plain_token", "")
        event_ts = d.get("event_ts", "")

        bot_secret = self.config.get("bot_secret", "")
        signature = self._ed25519_sign(bot_secret, event_ts, plain_token)

        return {
            "plain_token": plain_token,
            "signature": signature,
        }

    @staticmethod
    def _ed25519_sign(secret: str, event_ts: str, plain_token: str) -> str:
        """
        Use bot_secret as seed to generate ed25519 private key,
        Yes event_ts + plain_token Signature, returns the hex-encoded signature.
        """
        # seed Must be 32 bytes
        seed = secret
        while len(seed) < 32:
            seed = seed * 2
        seed_bytes = seed[:32].encode("utf-8")

        private_key = Ed25519PrivateKey.from_private_bytes(seed_bytes)
        msg = (event_ts + plain_token).encode("utf-8")
        sig = private_key.sign(msg)
        return sig.hex()

    # ------------------------------------------------------------------ #
    # Message parsing
    # ------------------------------------------------------------------ #

    async def parse_message(
        self, headers: Dict[str, str], body: bytes
    ) -> Optional[GatewayMessage]:
        """
        Parse QQ Webhook events into unified GatewayMessage.

        Supported event types:
        - C2C_MESSAGE_CREATE: Single chat message
        - GROUP_AT_MESSAGE_CREATE: group chat @Bot news
        """
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        op = payload.get("op")
        if op != 0:
            # Non-Dispatch events (heartbeat, verification, etc.), skipped
            return None

        event_type = payload.get("t", "")
        d = payload.get("d", {})

        if event_type == "C2C_MESSAGE_CREATE":
            return self._parse_c2c_message(d)
        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            return self._parse_group_message(d)
        else:
            logger.debug("[QQAdapter] Ignore event type: %s", event_type)
            return None

    def _parse_c2c_message(self, d: Dict[str, Any]) -> GatewayMessage:
        """Parsing C2C (personal chat) messages"""
        user_openid = d.get("author", {}).get("user_openid", "")
        content = (d.get("content") or "").strip()
        msg_id = d.get("id", "")
        logger.info("[QQ receive messages] C2C Private chat | user=%s | msg_id=%s | content=%r", user_openid, msg_id, content)

        # Determine whether it is a command
        msg_type = MessageType.COMMAND if content.startswith("/") else MessageType.TEXT

        return GatewayMessage(
            channel_type=ChannelType.QQ,
            channel_id=f"c2c:{user_openid}",  # Single chat uses user_openid as channel
            user_identity=user_openid,
            message_type=msg_type,
            content=content,
            is_mention_bot=True,  # By default, single chat is sent to Bot
            metadata={
                "msg_id": msg_id,
                "scene": "c2c",
                "user_openid": user_openid,
            },
        )

    def _parse_group_message(self, d: Dict[str, Any]) -> GatewayMessage:
        """Parse group chat @Bot news"""
        member_openid = d.get("author", {}).get("member_openid", "")
        group_openid = d.get("group_openid", "")
        content = (d.get("content") or "").strip()
        msg_id = d.get("id", "")
        logger.info("[QQ receive messages] group chat@Bot | group=%s | member=%s | msg_id=%s | content=%r", group_openid, member_openid, msg_id, content)

        msg_type = MessageType.COMMAND if content.startswith("/") else MessageType.TEXT

        return GatewayMessage(
            channel_type=ChannelType.QQ,
            channel_id=f"group:{group_openid}",
            user_identity=member_openid,
            message_type=msg_type,
            content=content,
            is_mention_bot=True,
            metadata={
                "msg_id": msg_id,
                "scene": "group",
                "group_openid": group_openid,
                "member_openid": member_openid,
            },
        )

    # ------------------------------------------------------------------ #
    # Markdown → Plain text conversion (QQ messages do not support Markdown rendering)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _convert_md_table(table_lines: list) -> str:
        """
        Convert Markdown horizontal table to vertical key: value format, adapted to narrow screen IM.

        Input example:
            | indicator | numerical value | Rating |
            |------|------|------|
            | PE   | 35x  | in   |
            | PB   | 12x  | high   |

        Output example:
            ▶ indicator: PE  numerical value: 35x  Rating: in
            ▶ indicator: PB  numerical value: 12x  Rating: high
        """
        rows = []
        for line in table_lines:
            stripped = line.strip().strip('|')
            cells = [c.strip() for c in stripped.split('|')]
            rows.append(cells)

        if len(rows) < 2:
            return '\n'.join(table_lines)

        headers = rows[0]
        result_parts = []

        for row in rows[1:]:
            # Skip delimited lines (such as |---|---|) 
            if all(re.match(r'^[-: ]+$', c) for c in row if c.strip()):
                continue
            # A single row has only one column or is completely empty → skip
            non_empty = [c for c in row if c.strip()]
            if not non_empty:
                continue

            if len(headers) == 2:
                # Two-column table: use directly "Title: value" format, most compact
                key = row[0].strip() if len(row) > 0 else ''
                val = row[1].strip() if len(row) > 1 else ''
                if key or val:
                    result_parts.append(f"  {key}: {val}")
            else:
                # Multi-column table: use delimiters to connect fields in each row
                parts = []
                for i, cell in enumerate(row):
                    if i < len(headers) and (cell.strip() or headers[i].strip()):
                        parts.append(f"{headers[i]}: {cell.strip()}")
                if parts:
                    result_parts.append('  ' + '  '.join(parts))

        return '\n'.join(result_parts)

    @staticmethod
    def _extract_tables(text: str):
        """
        Extract all Markdown table blocks (contiguous | starting line),
        Return (Processed text, ) —— Replace directly in the text.
        """
        lines = text.split('\n')
        result_lines = []
        table_buf = []

        def flush_table():
            if table_buf:
                converted = QQAdapter._convert_md_table(table_buf)
                result_lines.append(converted)
                table_buf.clear()

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|') and len(stripped) > 1:
                table_buf.append(line)
            else:
                flush_table()
                result_lines.append(line)

        flush_table()
        return '\n'.join(result_lines)

    @staticmethod
    def _md_to_plain(text: str) -> str:
        """
        Convert Markdown format text to QQ-friendly plain text.

        Conversion rules:
        - Markdown table        → Vertical key: value (Deal with it first, avoid it | deleted by mistake)
        - **bold** / __bold__  → bold
        - *italic* / _italic_  → italic
        - `code`               → code
        - ```code block```     → code block (Keep content, de-fence)
        - ### Title             →  [Title]
        - - / * list           → • list
        - [text](url)          → text
        - > Quote               →  | Quote
        - ---                  → ————
        - Merge excess blank lines
        """
        s = text

        # ① Prioritize table (use | separated, must precede other substitutions)
        s = QQAdapter._extract_tables(s)

        # ② code block ```...``` → Keep content, remove fences
        s = re.sub(r'```[a-zA-Z]*\n?', '', s)

        # ③ inline code
        s = re.sub(r'`([^`]+)`', r'\1', s)

        # ④ Title ### Text →  [Text] 
        s = re.sub(r'^#{1,6}\s+(.+)$', r'【\1】', s, flags=re.MULTILINE)

        # ⑤ Bold + italics
        s = re.sub(r'\*{3}(.+?)\*{3}', r'\1', s)
        s = re.sub(r'_{3}(.+?)_{3}', r'\1', s)
        s = re.sub(r'\*{2}(.+?)\*{2}', r'\1', s)
        s = re.sub(r'_{2}(.+?)_{2}', r'\1', s)
        s = re.sub(r'\*(.+?)\*', r'\1', s)
        s = re.sub(r'_(.+?)_', r'\1', s)

        # ⑥ link [text](url) → text
        s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)

        # ⑦ pictures → remove
        s = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', s)

        # ⑧ Quote > text →  | text
        s = re.sub(r'^>\s?(.*)$', r'｜\1', s, flags=re.MULTILINE)

        # ⑨ unordered list - / * → •
        s = re.sub(r'^[ \t]*[-*]\s+', '• ', s, flags=re.MULTILINE)

        # ⑩ dividing line
        s = re.sub(r'^-{3,}$', '————————', s, flags=re.MULTILINE)
        s = re.sub(r'^\*{3,}$', '————————', s, flags=re.MULTILINE)

        # ⑪ strikethrough
        s = re.sub(r'~~(.+?)~~', r'\1', s)

        # ⑫ Merge extra blank lines
        s = re.sub(r'\n{3,}', '\n\n', s)

        return s.strip()

    # ------------------------------------------------------------------ #
    # message sending
    # ------------------------------------------------------------------ #

    async def send_response(self, response: GatewayResponse) -> bool:
        """
        Send messages to QQ platform.

        Determine the scenario based on the channel_id prefix:
        - c2c:xxx   → Private chat reply
        - group:xxx → Group chat reply
        """
        channel_id = response.channel_id

        # Parse scene from channel_id
        if channel_id.startswith("c2c:"):
            user_openid = channel_id[4:]
            return await self._send_c2c_message(user_openid, response)
        elif channel_id.startswith("group:"):
            group_openid = channel_id[6:]
            return await self._send_group_message(group_openid, response)
        else:
            logger.warning("[QQAdapter] Unknown channel_id format: %s", channel_id)
            return False

    async def _send_c2c_message(
        self, user_openid: str, response: GatewayResponse
    ) -> bool:
        """Send private message"""
        token = await self._ensure_access_token()
        url = f"{QQ_API_BASE}/v2/users/{user_openid}/messages"

        plain = self._md_to_plain(response.content)
        content = self.truncate_for_platform(plain, max_length=3500)
        body: Dict[str, Any] = {
            "content": content,
            "msg_type": 0,  # text message
        }

        # If there is msg_id, as a passive reply
        if hasattr(response, "metadata") and response.metadata:
            msg_id = response.metadata.get("msg_id")
            if msg_id:
                body["msg_id"] = msg_id

        return await self._do_send(url, body, token)

    async def _send_group_message(
        self, group_openid: str, response: GatewayResponse
    ) -> bool:
        """Send group chat message"""
        token = await self._ensure_access_token()
        url = f"{QQ_API_BASE}/v2/groups/{group_openid}/messages"

        plain = self._md_to_plain(response.content)
        content = self.truncate_for_platform(plain, max_length=3500)
        body: Dict[str, Any] = {
            "content": content,
            "msg_type": 0,
        }

        if hasattr(response, "metadata") and response.metadata:
            msg_id = response.metadata.get("msg_id")
            if msg_id:
                body["msg_id"] = msg_id

        return await self._do_send(url, body, token)

    async def _do_send(
        self, url: str, body: Dict[str, Any], token: str
    ) -> bool:
        """Perform HTTP POST to send message"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers=self._get_auth_headers(token),
                )
            if resp.status_code in (200, 201, 204):
                logger.info("[QQAdapter] Message sent successfully: %s", url)
                return True
            else:
                logger.warning(
                    "[QQAdapter] Message sending failed: status=%s, body=%s",
                    resp.status_code, resp.text[:300],
                )
                return False
        except Exception as e:
            logger.exception("[QQAdapter] Message sending exception: %s", e)
            return False

