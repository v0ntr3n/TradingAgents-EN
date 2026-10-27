"""
WebSocket Notification system
substitute SSE + Redis PubSub, Troubleshoot connection leaks
"""
import asyncio
import base64
import json
import logging
from typing import Dict, Optional, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from datetime import datetime

from app.services.auth_service import AuthService
from app.services.user_service import user_service

router = APIRouter()
logger = logging.getLogger("webapi.websocket")


async def _authenticate_websocket(websocket: WebSocket, token: Optional[str]) -> Optional[str]:
    """
    Unified WebSocket authentication (supports JWT and JD Cloud Basic Auth)

    Authentication priority:
    1. JWT token (query parameters)— Main path of non-JD Cloud mode
    2. JD Cloud Basic Auth (Authorization header)— JD Cloud gateway injection, carried during WebSocket handshake

    Args:
        websocket: WebSocket connection object
        token: query JWT token in parameters (can be empty)

    Returns:
        If the authentication is successful, user_id (string) will be returned. If the authentication fails, user_id will be returned. None
    """
    # way 1: JWT token Certification
    if token:
        token_data = AuthService.verify_token(token)
        if token_data:
            user = await user_service.get_user_by_username(token_data.sub)
            if user:
                return str(user.id)
        logger.warning("❌ [WS] JWT token Verification failed, try JD Cloud Basic Auth")

    # way 2: JD Cloud Basic Auth authentication (the Authorization header is injected by JD Cloud gateway during WebSocket handshake)
    from app.core.jdyun import (
        is_jdyun_mode,
        is_from_jdyun_gateway,
        verify_jdyun_basic_auth,
    )

    if not is_jdyun_mode():
        return None

    authorization = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not authorization or not authorization.lower().startswith("basic "):
        logger.debug("ℹ️ [WS] JD Cloud mode does not carry Basic Auth header")
        return None

    # IP Whitelist verification (second line of defense)
    client_ip = websocket.client.host if websocket.client else ""
    if not is_from_jdyun_gateway(client_ip):
        logger.warning(f"❌ [WS] JD Cloud Basic Auth IP is not in the gateway whitelist: {client_ip}")
        return None

    try:
        encoded = authorization.split(" ", 1)[1]
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        if ":" not in decoded:
            logger.warning("❌ [WS] JD Cloud Basic Auth format error: missing delimiter")
            return None
        username, basic_token = decoded.split(":", 1)

        # Hierarchical verification: old users are exempt from tokens, new users are strictly verified
        is_existing = user_service.is_existing_jdyun_user(username)
        if is_existing:
            auth_passed = True
            logger.info(f"✅ [WS] JD Cloud old users are exempt from token verification: user={username}")
        else:
            auth_passed = verify_jdyun_basic_auth(username, basic_token)
            if not auth_passed:
                logger.warning(f"❌ [WS] New JD Cloud user failed to authenticate for the first time: user={username}")

        if not auth_passed:
            return None

        # Get or create a user
        jdyun_user = await user_service.get_or_create_jdyun_user(
            jdyun_username=username,
            is_admin=True,
        )
        if jdyun_user:
            logger.info(f"✅ [WS] JD Cloud Basic Auth authentication successful: user={username} db_id={jdyun_user.id}")
            return str(jdyun_user.id)
        logger.error(f"❌ [WS] JD Cloud user profile creation failed: {username}")
        return None
    except Exception as e:
        logger.warning(f"❌ [WS] JD Cloud Basic Auth parsing failed: {e}", exc_info=True)
        return None

# 🔥 Global WebSocket connection manager
class ConnectionManager:
    """WebSocket connection manager"""
    
    def __init__(self):
        # user_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """connect WebSocket"""
        await websocket.accept()
        
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)
            
            total_connections = sum(len(conns) for conns in self.active_connections.values())
            logger.info(f"✅ [WS] new connection: user={user_id}, "
                       f"Number of connections for this user={len(self.active_connections[user_id])}, "
                       f"total connections={total_connections}")
    
    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Disconnect WebSocket"""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            
            total_connections = sum(len(conns) for conns in self.active_connections.values())
            logger.info(f"🔌 [WS] Disconnect: user={user_id}, total connections={total_connections}")
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Send a message to all connections of the specified user"""
        async with self._lock:
            if user_id not in self.active_connections:
                logger.debug(f"⚠️ [WS] User {user_id} No active connection")
                return
            
            connections = list(self.active_connections[user_id])
        
        # Send messages outside the lock to avoid blocking
        message_json = json.dumps(message, ensure_ascii=False)
        dead_connections = []
        
        for connection in connections:
            try:
                await connection.send_text(message_json)
                logger.debug(f"📤 [WS] Send message to user={user_id}")
            except Exception as e:
                logger.warning(f"❌ [WS] Failed to send message: {e}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                if user_id in self.active_connections:
                    for conn in dead_connections:
                        self.active_connections[user_id].discard(conn)
                    if not self.active_connections[user_id]:
                        del self.active_connections[user_id]
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        async with self._lock:
            all_connections = []
            for connections in self.active_connections.values():
                all_connections.extend(connections)
        
        message_json = json.dumps(message, ensure_ascii=False)
        
        for connection in all_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"❌ [WS] Broadcast message failed: {e}")
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "total_users": len(self.active_connections),
            "total_connections": sum(len(conns) for conns in self.active_connections.values()),
            "users": {user_id: len(conns) for user_id, conns in self.active_connections.items()}
        }


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws/notifications")
async def websocket_notifications_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    WebSocket notification endpoint

    client connection:
    - JWT mode: ws://localhost:8000/api/ws/notifications?token=<jwt_token>
    - Jingdong cloud model: ws://localhost:8000/api/ws/notifications  (No token required, Basic Auth injected by gateway)

    Message format:
    {
        "type": "notification",  // Message type: notification, heartbeat, connected
        "data": {
            "id": "...",
            "title": "...",
            "content": "...",
            "type": "analysis",
            "link": "/stocks/000001",
            "source": "analysis",
            "created_at": "2025-10-23T12:00:00",
            "status": "unread"
        }
    }
    """
    # Unified authentication (JWT or JD Cloud Basic Auth)
    user_id = await _authenticate_websocket(websocket, token)
    if not user_id:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    # connect WebSocket
    await manager.connect(websocket, user_id)
    
    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "data": {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "WebSocket Connection successful"
        }
    })
    
    try:
        # heartbeat task
        async def send_heartbeat():
            while True:
                try:
                    await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                    await websocket.send_json({
                        "type": "heartbeat",
                        "data": {
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    })
                except Exception as e:
                    logger.debug(f"💓 [WS] Heartbeat sending failed: {e}")
                    break
        
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(send_heartbeat())
        
        # Receive client messages (mainly used to maintain connections)
        while True:
            try:
                data = await websocket.receive_text()
                # Can handle messages sent by the client (such as ping/pong)
                logger.debug(f"📥 [WS] Receive client message: user={user_id}, data={data}")
            except WebSocketDisconnect:
                logger.info(f"🔌 [WS] Client actively disconnects: user={user_id}")
                break
            except Exception as e:
                logger.error(f"❌ [WS] Receive message error: {e}")
                break
    
    finally:
        # Cancel heartbeat task
        if 'heartbeat_task' in locals():
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect
        await manager.disconnect(websocket, user_id)


@router.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress_endpoint(
    websocket: WebSocket,
    task_id: str,
    token: Optional[str] = Query(None),
):
    """
    WebSocket Task progress endpoint

    client connection:
    - JWT mode: ws://localhost:8000/api/ws/tasks/<task_id>?token=<jwt_token>
    - Jingdong cloud model: ws://localhost:8000/api/ws/tasks/<task_id>  (No token required, Basic Auth injected by gateway)

    Message format:
    {
        "type": "progress",  // Message type: progress, completed, error, heartbeat
        "data": {
            "task_id": "...",
            "message": "Analyzing...",
            "step": 1,
            "total_steps": 5,
            "progress": 20.0,
            "timestamp": "2025-10-23T12:00:00"
        }
    }
    """
    # Unified authentication (JWT or JD Cloud Basic Auth)
    user_id = await _authenticate_websocket(websocket, token)
    if not user_id:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    channel = f"task_progress:{task_id}"
    
    # connect WebSocket
    await websocket.accept()
    logger.info(f"✅ [WS-Task] new connection: task={task_id}, user={user_id}")
    
    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "data": {
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Connected task progress flow"
        }
    })
    
    try:
        # Here you can get the task progress from Redis or database
        # Stay connected temporarily and wait for the task to complete
        while True:
            try:
                data = await websocket.receive_text()
                logger.debug(f"📥 [WS-Task] Receive client message: task={task_id}, data={data}")
            except WebSocketDisconnect:
                logger.info(f"🔌 [WS-Task] Client actively disconnects: task={task_id}")
                break
            except Exception as e:
                logger.error(f"❌ [WS-Task] Receive message error: {e}")
                break
    
    finally:
        logger.info(f"🔌 [WS-Task] Disconnect: task={task_id}")


@router.get("/ws/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics"""
    return manager.get_stats()


# 🔥 Auxiliary function: for other modules to call and send notifications
async def send_notification_via_websocket(user_id: str, notification: dict):
    """
    Send notifications via WebSocket
    
    Args:
        user_id: User ID
        notification: notification data
    """
    message = {
        "type": "notification",
        "data": notification
    }
    await manager.send_personal_message(message, user_id)


async def send_task_progress_via_websocket(task_id: str, progress_data: dict):
    """
    Send task progress via WebSocket
    
    Args:
        task_id: Task ID
        progress_data: progress data
    """
    # Note: Here you need to know which user the task belongs to
    # Can be queried from the database or passed in progress_data
    # Temporarily simplify processing
    message = {
        "type": "progress",
        "data": progress_data
    }
    # Broadcast to all connections (production environment should only send it to the user who owns the task)
    await manager.broadcast(message)

