"""
QQ Bot WebSocket client

Connect to QQ gateway to receive events through WebSocket, no public IP is required.

Agreement process:
  Connect → Hello(op=10) → Identify(op=2) → Ready(op=0) → heartbeat cycle → Dispatch(op=0)

QQ Official documentation: https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

import aiohttp
import httpx

logger = logging.getLogger(__name__)

QQ_API_BASE = "https://api.sgroup.qq.com"
QQ_SANDBOX_API_BASE = "https://sandbox.api.sgroup.qq.com"
QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

# OpCodes
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

# Intents - Event types to be received
INTENT_GROUP_AND_C2C = 1 << 25       # C2C_MESSAGE_CREATE + GROUP_AT_MESSAGE_CREATE
INTENT_PUBLIC_GUILD_MESSAGES = 1 << 30  # AT_MESSAGE_CREATE (Channel public domain)


class QQWebSocketClient:
    """QQ Bot WebSocket client — Connect to QQ gateway to receive event push"""

    def __init__(
        self,
        config: Dict[str, Any],
        on_event=None,
        sandbox: bool = False,
    ):
        """
        Args:
            config: contains app_id, app_secret configuration dictionary
            on_event: Callback when Dispatch event is received, async def on_event(event_type, data, raw_payload)
            sandbox: Whether to use a sandbox environment
        """
        self.config = config
        self.on_event = on_event
        self.sandbox = sandbox

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._session_id: Optional[str] = None
        self._seq: Optional[int] = None
        self._heartbeat_interval: float = 45.0  # Default 45s, will be updated in Hello
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._reconnect_delay: float = 1.0  # Reconnection delay (exponential backoff)
        self._max_reconnect_delay: float = 60.0

    # ------------------------------------------------------------------ #
    # AccessToken management
    # ------------------------------------------------------------------ #

    async def _ensure_access_token(self) -> str:
        now = time.time()
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
        logger.info("[QQ-WS] AccessToken Refreshed, valid period %ss", data.get("expires_in"))
        return self._access_token

    # ------------------------------------------------------------------ #
    # Get WebSocket gateway address
    # ------------------------------------------------------------------ #

    async def _get_gateway_url(self) -> str:
        token = await self._ensure_access_token()
        base = QQ_SANDBOX_API_BASE if self.sandbox else QQ_API_BASE
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/gateway",
                headers={"Authorization": f"QQBot {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        url = data.get("url", "")
        logger.info("[QQ-WS] Gateway address: %s", url)
        return url

    # ------------------------------------------------------------------ #
    # main run loop
    # ------------------------------------------------------------------ #

    async def start(self):
        """Start WebSocket client (blocking, should be called in asyncio.create_task)"""
        self._running = True
        self._reconnect_delay = 1.0
        logger.info("[QQ-WS] Start the WebSocket client...")

        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.info("[QQ-WS] Client canceled")
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning("[QQ-WS] Connection abnormality: %s, %.1fs Reconnect later", e, self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

        logger.info("[QQ-WS] Client has stopped")

    async def stop(self):
        """Stop the WebSocket client"""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        logger.info("[QQ-WS] Stop signal sent")

    # ------------------------------------------------------------------ #
    # WebSocket Connect and monitor
    # ------------------------------------------------------------------ #

    async def _connect_and_listen(self):
        """Establish a WebSocket connection and listen for messages"""
        gateway_url = await self._get_gateway_url()
        if not gateway_url:
            raise RuntimeError("Gateway address not obtained")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(gateway_url) as ws:
                self._ws = ws
                logger.info("[QQ-WS] Connected to gateway")

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(ws, json.loads(msg.data))
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("[QQ-WS] WebSocket Error: %s", ws.exception())
                        break
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                        logger.warning("[QQ-WS] connection closed: %s", msg.data)
                        break

        # clear heartbeat
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _handle_message(self, ws: aiohttp.ClientWebSocketResponse, payload: Dict[str, Any]):
        """Process messages received from the gateway"""
        op = payload.get("op")
        d = payload.get("d")
        s = payload.get("s")
        t = payload.get("t")

        # Update serial number
        if s is not None:
            self._seq = s

        if op == OP_HELLO:
            # Receive Hello, get the heartbeat interval and send Identify
            self._heartbeat_interval = d.get("heartbeat_interval", 45000) / 1000.0
            logger.info("[QQ-WS] Hello: heartbeat interval %.1fs", self._heartbeat_interval)

            if self._session_id and self._seq is not None:
                # Disconnection and reconnection:Resume
                await self._send_resume(ws)
            else:
                # First time connection:Identify
                await self._send_identify(ws)

            # Start heartbeat
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

        elif op == OP_DISPATCH:
            # event distribution
            self._reconnect_delay = 1.0  # Reset reconnection delay
            if t == "READY":
                self._session_id = d.get("session_id")
                user_info = d.get("user", {})
                logger.info(
                    "[QQ-WS] Authentication successful! session=%s, bot=%s",
                    self._session_id, user_info.get("username", "?"),
                )
            elif t == "RESUMED":
                logger.info("[QQ-WS] Restore connection successfully")
            else:
                # Business events (messages, etc.), callback processing
                if self.on_event:
                    try:
                        await self.on_event(t, d, payload)
                    except Exception as e:
                        logger.exception("[QQ-WS] Event handling exception: %s", e)

        elif op == OP_HEARTBEAT_ACK:
            logger.debug("[QQ-WS] heartbeat ACK")

        elif op == OP_RECONNECT:
            logger.warning("[QQ-WS] Server requires reconnection")
            await ws.close()

        elif op == OP_INVALID_SESSION:
            logger.warning("[QQ-WS] Invalid Session, Re-authenticate")
            self._session_id = None
            self._seq = None
            await ws.close()

        else:
            logger.debug("[QQ-WS] unprocessed op=%s", op)

    # ------------------------------------------------------------------ #
    # Send operation
    # ------------------------------------------------------------------ #

    async def _send_identify(self, ws: aiohttp.ClientWebSocketResponse):
        """Send authentication Identify"""
        token = await self._ensure_access_token()
        intents = INTENT_GROUP_AND_C2C  # C2C + group chat @Bot
        payload = {
            "op": OP_IDENTIFY,
            "d": {
                "token": f"QQBot {token}",
                "intents": intents,
                "shard": [0, 1],
                "properties": {
                    "$os": "windows",
                    "$browser": "TradingAgentsCN",
                    "$device": "TradingAgentsCN",
                },
            },
        }
        await ws.send_json(payload)
        logger.info("[QQ-WS] Sent Identify, intents=%d", intents)

    async def _send_resume(self, ws: aiohttp.ClientWebSocketResponse):
        """Send Resume to restore the connection"""
        token = await self._ensure_access_token()
        payload = {
            "op": OP_RESUME,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self._session_id,
                "seq": self._seq,
            },
        }
        await ws.send_json(payload)
        logger.info("[QQ-WS] Sent Resume, session=%s, seq=%s", self._session_id, self._seq)

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse):
        """Send heartbeat periodically"""
        try:
            while self._running and not ws.closed:
                await asyncio.sleep(self._heartbeat_interval)
                if ws.closed:
                    break
                payload = {"op": OP_HEARTBEAT, "d": self._seq}
                await ws.send_json(payload)
                logger.debug("[QQ-WS] Heartbeat sent, seq=%s", self._seq)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[QQ-WS] Abnormal heartbeat: %s", e)

