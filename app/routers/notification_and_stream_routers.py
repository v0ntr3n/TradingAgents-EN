from __future__ import annotations
import sys as _sys
import types as _types
import app.routers as _routers_pkg
_self_mod = _sys.modules[__name__]
_snapshots = {}

# === notifications.py ===
"""
Notification REST API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.auth_db import get_current_user
from app.core.response import ok
from app.core.database import get_redis_client
from app.services.notifications_service import get_notifications_service

router = APIRouter()
logger = logging.getLogger("webapi.notifications")


@router.get("/notifications")
async def list_notifications(
    status: Optional[str] = Query(None, description="Status: unread|read|all"),
    type: Optional[str] = Query(None, description="Type: analysis|alert|system"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
):
    svc = get_notifications_service()
    s = status if status in ("read","unread") else None
    t = type if type in ("analysis","alert","system") else None
    data = await svc.list(user_id=user["id"], status=s, ntype=t, page=page, page_size=page_size)
    return ok(data=data.model_dump(), message="ok")


@router.get("/notifications/unread_count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    svc = get_notifications_service()
    cnt = await svc.unread_count(user_id=user["id"])
    return ok(data={"count": cnt})


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    svc = get_notifications_service()
    ok_flag = await svc.mark_read(user_id=user["id"], notif_id=notif_id)
    if not ok_flag:
        raise HTTPException(status_code=404, detail="Notification not found")
    return ok()


@router.post("/notifications/read_all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    svc = get_notifications_service()
    n = await svc.mark_all_read(user_id=user["id"])
    return ok(data={"updated": n})


@router.get("/notifications/debug/redis_pool")
async def debug_redis_pool(user: dict = Depends(get_current_user)):
    """Debug endpoint: View Redis connection pool status"""
    try:
        r = get_redis_client()
        pool = r.connection_pool

        # Get connection pool information
        pool_info = {
            "max_connections": pool.max_connections,
            "connection_class": str(pool.connection_class),
            "available_connections": len(pool._available_connections) if hasattr(pool, '_available_connections') else "N/A",
            "in_use_connections": len(pool._in_use_connections) if hasattr(pool, '_in_use_connections') else "N/A",
        }

        # Get Redis server information
        info = await r.info("clients")
        redis_info = {
            "connected_clients": info.get("connected_clients", "N/A"),
            "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer", "N/A"),
            "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer", "N/A"),
            "blocked_clients": info.get("blocked_clients", "N/A"),
        }

        # 🔥 New: Get PubSub channel information
        try:
            pubsub_info = await r.execute_command("PUBSUB", "CHANNELS", "notifications:*")
            pubsub_channels = {
                "active_channels": len(pubsub_info) if pubsub_info else 0,
                "channels": pubsub_info if pubsub_info else []
            }
        except Exception as e:
            logger.warning(f"Failed to obtain PubSub channel information: {e}")
            pubsub_channels = {"error": str(e)}

        return ok(data={
            "pool": pool_info,
            "redis_server": redis_info,
            "pubsub": pubsub_channels
        })
    except Exception as e:
        logger.error(f"Failed to obtain Redis connection pool information: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
_snapshots['notifications'] = dict(globals())

# === internal_messages.py ===
"""
Internal message data API routing
Provide query, search and management interface for internal messages
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from app.services.internal_message_service import (
    get_internal_message_service,
    InternalMessageQueryParams,
    InternalMessageStats
)
from app.core.response import ok

router = APIRouter(prefix="/api/internal-messages", tags=["internal-messages"])


class InternalMessage(BaseModel):
    """Internal message model"""
    message_id: str
    message_type: str  # research_report/insider_info/analyst_note/meeting_minutes/internal_analysis
    title: str
    content: str
    summary: Optional[str] = ""
    source: Dict[str, Any]
    category: str
    subcategory: Optional[str] = ""
    tags: Optional[List[str]] = []
    importance: str = "medium"
    impact_scope: str = "stock_specific"
    time_sensitivity: str = "medium_term"
    confidence_level: float = Field(0.5, ge=0.0, le=1.0)
    sentiment: Optional[str] = "neutral"
    sentiment_score: Optional[float] = 0.0
    keywords: Optional[List[str]] = []
    risk_factors: Optional[List[str]] = []
    opportunities: Optional[List[str]] = []
    related_data: Optional[Dict[str, Any]] = {}
    access_level: str = "internal"
    permissions: Optional[List[str]] = []
    created_time: datetime
    effective_time: Optional[datetime] = None
    expiry_time: Optional[datetime] = None
    language: str = "zh-CN"
    data_source: str = "internal_system"


class InternalMessageBatchRequest(BaseModel):
    """Save internal message requests in batches"""
    symbol: str = Field(..., description="Stock code")
    messages: List[InternalMessage] = Field(..., description="Internal message list")


class InternalMessageQueryRequest(BaseModel):
    """Internal message query request"""
    symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    message_type: Optional[str] = None
    category: Optional[str] = None
    source_type: Optional[str] = None
    department: Optional[str] = None
    author: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    importance: Optional[str] = None
    access_level: Optional[str] = None
    min_confidence: Optional[float] = None
    rating: Optional[str] = None
    keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    limit: int = Field(50, ge=1, le=1000)
    skip: int = Field(0, ge=0)


@router.post("/save", response_model=dict)
async def save_internal_messages(request: InternalMessageBatchRequest):
    """Save internal messages in batches"""
    try:
        service = await get_internal_message_service()
        
        # Convert message format and add stock symbol
        messages = []
        for msg in request.messages:
            message_dict = msg.dict()
            message_dict["symbol"] = request.symbol
            messages.append(message_dict)
        
        # save message
        result = await service.save_internal_messages(messages)
        
        return ok(data=result,
            message=f"Saved successfully {result['saved']} internal news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save internal message: {str(e)}")


@router.post("/query", response_model=dict)
async def query_internal_messages(request: InternalMessageQueryRequest):
    """Check inside information"""
    try:
        service = await get_internal_message_service()
        
        # Build query parameters
        params = InternalMessageQueryParams(
            symbol=request.symbol,
            symbols=request.symbols,
            message_type=request.message_type,
            category=request.category,
            source_type=request.source_type,
            department=request.department,
            author=request.author,
            start_time=request.start_time,
            end_time=request.end_time,
            importance=request.importance,
            access_level=request.access_level,
            min_confidence=request.min_confidence,
            rating=request.rating,
            keywords=request.keywords,
            tags=request.tags,
            limit=request.limit,
            skip=request.skip
        )
        
        # Execute query
        messages = await service.query_internal_messages(params)
        
        return ok(data={
                "messages": messages,
                "count": len(messages),
                "params": request.dict()
            },
            message=f"Found {len(messages)} internal news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query internal information: {str(e)}")


@router.get("/latest/{symbol}", response_model=dict)
async def get_latest_messages(
    symbol: str,
    message_type: Optional[str] = Query(None, description="Message type"),
    access_level: Optional[str] = Query(None, description="access level"),
    limit: int = Query(20, ge=1, le=100, description="Return quantity")
):
    """Get the latest inside news"""
    try:
        service = await get_internal_message_service()
        messages = await service.get_latest_messages(symbol, message_type, access_level, limit)
        
        return ok(data={
                "messages": messages,
                "count": len(messages),
                "symbol": symbol,
                "message_type": message_type,
                "access_level": access_level
            },
            message=f"Get {len(messages)} latest news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get latest news: {str(e)}")


@router.get("/search", response_model=dict)
async def search_messages(
    query: str = Query(..., description="Search keywords"),
    symbol: Optional[str] = Query(None, description="Stock code"),
    access_level: Optional[str] = Query(None, description="access level"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity")
):
    """Full-text search for inside information"""
    try:
        service = await get_internal_message_service()
        messages = await service.search_messages(query, symbol, access_level, limit)
        
        return ok(data={
                "messages": messages,
                "count": len(messages),
                "query": query,
                "symbol": symbol,
                "access_level": access_level
            },
            message=f"Searched for {len(messages)} related news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search message failed: {str(e)}")


@router.get("/research-reports/{symbol}", response_model=dict)
async def get_research_reports(
    symbol: str,
    department: Optional[str] = Query(None, description="Department"),
    limit: int = Query(20, ge=1, le=100, description="Return quantity")
):
    """Get research report"""
    try:
        service = await get_internal_message_service()
        reports = await service.get_research_reports(symbol, department, limit)
        
        return ok(data={
                "reports": reports,
                "count": len(reports),
                "symbol": symbol,
                "department": department
            },
            message=f"Get {len(reports)} research reports"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain research report: {str(e)}")


@router.get("/analyst-notes/{symbol}", response_model=dict)
async def get_analyst_notes(
    symbol: str,
    author: Optional[str] = Query(None, description="analyst"),
    limit: int = Query(20, ge=1, le=100, description="Return quantity")
):
    """Get analyst notes"""
    try:
        service = await get_internal_message_service()
        notes = await service.get_analyst_notes(symbol, author, limit)
        
        return ok(data={
                "notes": notes,
                "count": len(notes),
                "symbol": symbol,
                "author": author
            },
            message=f"Get {len(notes)} analyst notes"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analyst notes: {str(e)}")


@router.get("/statistics", response_model=dict)
async def get_statistics(
    symbol: Optional[str] = Query(None, description="Stock code"),
    hours_back: int = Query(24, ge=1, le=168, description="Lookback hours")
):
    """Get internal message statistics"""
    try:
        service = await get_internal_message_service()
        
        # Calculation time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        
        stats = await service.get_internal_statistics(symbol, start_time, end_time)
        
        return ok(data={
                "statistics": stats.__dict__,
                "symbol": symbol,
                "time_range": {
                    "start_time": start_time,
                    "end_time": end_time,
                    "hours_back": hours_back
                }
            },
            message="Statistics obtained successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain statistics: {str(e)}")


@router.get("/message-types", response_model=dict)
async def get_message_types():
    """Get a list of supported message types"""
    message_types = [
        {
            "code": "research_report",
            "name": "research report",
            "description": "In-depth research analysis report"
        },
        {
            "code": "insider_info",
            "name": "Insider information",
            "description": "Important information obtained internally"
        },
        {
            "code": "analyst_note",
            "name": "Analyst Notes",
            "description": "Analyst views and notes"
        },
        {
            "code": "meeting_minutes",
            "name": "meeting minutes",
            "description": "Minutes of important meetings"
        },
        {
            "code": "internal_analysis",
            "name": "internal analysis",
            "description": "Analytical results from internal team"
        }
    ]
    
    return ok(data={
            "message_types": message_types,
            "count": len(message_types)
        },
        message="Message type list obtained successfully"
    )


@router.get("/categories", response_model=dict)
async def get_categories():
    """Get a list of supported categories"""
    categories = [
        {
            "code": "fundamental_analysis",
            "name": "fundamental analysis",
            "description": "Analysis related to company fundamentals"
        },
        {
            "code": "technical_analysis",
            "name": "technical analysis",
            "description": "Technical indicators and chart analysis"
        },
        {
            "code": "market_sentiment",
            "name": "market sentiment",
            "description": "Market sentiment and investor behavior analysis"
        },
        {
            "code": "risk_assessment",
            "name": "risk assessment",
            "description": "Investment risk assessment and management"
        }
    ]
    
    return ok(data={
            "categories": categories,
            "count": len(categories)
        },
        message="Category list obtained successfully"
    )


@router.get("/health", response_model=dict)
async def health_check():
    """health check"""
    try:
        service = await get_internal_message_service()
        
        # Simple connection test
        collection = await service._get_collection()
        count = await collection.estimated_document_count()
        
        return ok(data={
                "status": "healthy",
                "total_messages": count,
                "service": "internal_message_service"
            },
            message="Internal messaging service is running normally"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
_snapshots['internal_messages'] = dict(globals())

# === websocket_notifications.py ===
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

_snapshots['websocket_notifications'] = dict(globals())

# === sse.py ===
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
import time

from app.routers.auth_db import get_current_user
from app.core.database import get_redis_client
from app.core.config import settings

from app.services.queue_service import get_queue_service, QueueService

router = APIRouter()
logger = logging.getLogger("webapi.sse")


async def task_progress_generator(task_id: str, user_id: str):
    """Generate SSE events for task progress updates"""
    r = get_redis_client()
    pubsub = None
    channel = f"task_progress:{task_id}"

    try:
        # Load dynamic SSE settings
        try:
            from app.services.config_provider import provider as config_provider
            eff = await config_provider.get_effective_system_settings()
            poll_timeout = float(eff.get("sse_poll_timeout_seconds", 1.0))
            heartbeat_every = int(eff.get("sse_heartbeat_interval_seconds", 10))
            max_idle_seconds = int(eff.get("sse_task_max_idle_seconds", 300))
        except Exception:
            poll_timeout = float(getattr(settings, "SSE_POLL_TIMEOUT_SECONDS", 1.0))
            heartbeat_every = int(getattr(settings, "SSE_HEARTBEAT_INTERVAL_SECONDS", 10))
            max_idle_seconds = int(getattr(settings, "SSE_TASK_MAX_IDLE_SECONDS", 300))

        # 🔥 Fix: Create PubSub connection
        pubsub = r.pubsub()
        logger.info(f"📡 [SSE-Task] Create a PubSub connection: task={task_id}, user={user_id}")

        # 🔥 Fix: Subscribe to channel (may fail, need to make sure pubsub is cleaned)
        try:
            await pubsub.subscribe(channel)
            logger.info(f"✅ [SSE-Task] Subscription to channel successful: {channel}")
            # Send initial connection confirmation
            yield f"event: connected\ndata: {{\"task_id\": \"{task_id}\", \"message\": \"Progress stream connected\"}}\n\n"
        except Exception as subscribe_error:
            # 🔥 Immediately clean up pubsub connections when subscription fails
            logger.error(f"❌ [SSE-Task] Failed to subscribe to channel: {subscribe_error}")
            try:
                await pubsub.close()
                logger.info("🧹 [SSE-Task] PubSub connection closed after subscription failed")
            except Exception as close_error:
                logger.error(f"❌ [SSE-Task] Failed to close PubSub connection: {close_error}")
            # Rethrow the exception and let the outer except handle it
            raise

        # Listen for progress updates
        idle_elapsed = 0.0
        last_hb = time.monotonic()

        while idle_elapsed < max_idle_seconds:
            try:
                message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=poll_timeout)
                if message and message['type'] == 'message':
                    # Reset idle timer on valid message
                    idle_elapsed = 0.0
                    try:
                        progress_data = json.loads(message['data'])
                        yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in progress message: {message['data']}")
                else:
                    # No update: accumulate idle time and send heartbeat if due
                    idle_elapsed += poll_timeout
                    now = time.monotonic()
                    if now - last_hb >= heartbeat_every:
                        yield f"event: heartbeat\ndata: {{\"timestamp\": \"{asyncio.get_event_loop().time()}\"}}\n\n"
                        last_hb = now

            except asyncio.TimeoutError:
                idle_elapsed += poll_timeout
                continue

    except Exception as e:
        logger.exception(f"SSE error for task {task_id}: {e}")
        yield f"event: error\ndata: {{\"error\": \"Connection abnormality: {str(e)}\"}}\n\n"
    finally:
        # 🔥 Fix: Ensure connections are released in all cases
        if pubsub:
            logger.info(f"🧹 [SSE-Task] Clean up PubSub connections: task={task_id}")

            # Stepped shutdown to ensure the connection is closed even if unsubscribe fails
            try:
                await pubsub.unsubscribe(channel)
                logger.debug(f"✅ [SSE-Task] Channel unsubscribed: {channel}")
            except Exception as e:
                logger.warning(f"⚠️ [SSE-Task] Unsubscription failed (will continue to close the connection): {e}")

            try:
                await pubsub.close()
                logger.info(f"✅ [SSE-Task] PubSub connection closed: task={task_id}")
            except Exception as e:
                logger.error(f"❌ [SSE-Task] Failed to close PubSub connection: {e}", exc_info=True)
                # Try to reset connection even if shutdown fails
                try:
                    await pubsub.reset()
                    logger.info(f"🔄 [SSE-Task] PubSub Connection reset: task={task_id}")
                except Exception as reset_error:
                    logger.error(f"❌ [SSE-Task] Resetting the PubSub connection also failed: {reset_error}")


async def batch_progress_generator(batch_id: str, user_id: str):
    """Generate SSE events for batch progress updates"""
    svc = get_queue_service()

    try:
        # Load dynamic SSE settings for batch stream
        try:
            from app.services.config_provider import provider as config_provider
            eff = await config_provider.get_effective_system_settings()
            batch_poll_interval = float(eff.get("sse_batch_poll_interval_seconds", 2))
            batch_max_idle_seconds = int(eff.get("sse_batch_max_idle_seconds", 600))
        except Exception:
            batch_poll_interval = float(getattr(settings, "SSE_BATCH_POLL_INTERVAL_SECONDS", 2.0))
            batch_max_idle_seconds = int(getattr(settings, "SSE_BATCH_MAX_IDLE_SECONDS", 600))

        # Send initial connection confirmation
        yield f"event: connected\ndata: {{\"batch_id\": \"{batch_id}\", \"message\": \"Batch progress flow connected\"}}\n\n"

        idle_elapsed = 0.0

        while idle_elapsed < batch_max_idle_seconds:
            try:
                # Get current batch status
                batch_data = await svc.get_batch(batch_id)
                if not batch_data:
                    yield "event: error\ndata: {\"error\": \"Batch does not exist\"}\n\n"
                    break

                # Check if batch belongs to user
                if batch_data.get("user") != user_id:
                    yield "event: error\ndata: {\"error\": \"No permission to access this batch\"}\n\n"
                    break

                # Calculate batch progress based on task statuses
                task_ids = batch_data.get("tasks", [])
                if not task_ids:
                    yield f"event: progress\ndata: {{\"batch_id\": \"{batch_id}\", \"message\": \"No tasks in batch\", \"progress\": 0}}\n\n"
                    await asyncio.sleep(batch_poll_interval)
                    idle_elapsed += batch_poll_interval
                    continue

                completed_count = 0
                failed_count = 0
                processing_count = 0

                for task_id in task_ids:
                    task_data = await svc.get_task(task_id)
                    if task_data:
                        status = task_data.get("status", "queued")
                        if status == "completed":
                            completed_count += 1
                        elif status == "failed":
                            failed_count += 1
                        elif status == "processing":
                            processing_count += 1

                total_tasks = len(task_ids)
                finished_tasks = completed_count + failed_count
                progress = round((finished_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0

                # Determine batch status
                if finished_tasks == total_tasks:
                    if failed_count == 0:
                        batch_status = "completed"
                        message = f"Batch completed: {completed_count}/{total_tasks} success"
                    elif completed_count == 0:
                        batch_status = "failed"
                        message = f"Batch failed: {failed_count}/{total_tasks} failed"
                    else:
                        batch_status = "partial"
                        message = f"Batch partially successful: {completed_count} success, {failed_count} failed"
                elif processing_count > 0 or finished_tasks < total_tasks:
                    batch_status = "processing"
                    message = f"Batch processing: {finished_tasks}/{total_tasks} Completed, {processing_count} Processing"
                else:
                    batch_status = "queued"
                    message = f"Batch in queue: {total_tasks} Task pending"

                progress_data = {
                    "batch_id": batch_id,
                    "status": batch_status,
                    "message": message,
                    "progress": progress,
                    "total_tasks": total_tasks,
                    "completed": completed_count,
                    "failed": failed_count,
                    "processing": processing_count,
                    "timestamp": asyncio.get_event_loop().time()
                }

                yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

                # Break if batch is finished
                if batch_status in ["completed", "failed", "partial"]:
                    yield f"event: finished\ndata: {{\"batch_id\": \"{batch_id}\", \"final_status\": \"{batch_status}\"}}\n\n"
                    break

                # Wait before next update
                await asyncio.sleep(batch_poll_interval)
                idle_elapsed += batch_poll_interval

            except Exception as e:
                logger.exception(f"Batch progress error: {e}")
                yield f"event: error\ndata: {{\"error\": \"Failed to get batch status: {str(e)}\"}}\n\n"
                break

    except Exception as e:
        logger.exception(f"SSE batch error for {batch_id}: {e}")
        yield f"event: error\ndata: {{\"error\": \"Connection abnormality: {str(e)}\"}}\n\n"


@router.get("/tasks/{task_id}")
async def stream_task_progress(task_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    """Stream real-time progress updates for a specific task"""
    # Verify task exists and belongs to user
    task_data = await svc.get_task(task_id)
    if not task_data or task_data.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        task_progress_generator(task_id, user["id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/batches/{batch_id}")
async def stream_batch_progress(batch_id: str, user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    """Stream real-time progress updates for a batch"""
    # Verify batch exists and belongs to user
    batch_data = await svc.get_batch(batch_id)
    if not batch_data or batch_data.get("user") != user["id"]:
        raise HTTPException(status_code=404, detail="Batch not found")

    return StreamingResponse(
        batch_progress_generator(batch_id, user["id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
_snapshots['sse'] = dict(globals())

for _stem, _snap in _snapshots.items():
    _vmod = _types.ModuleType(f"app.routers.{_stem}")
    _vmod.__dict__.update(_snap)
    _sys.modules[f"app.routers.{_stem}"] = _vmod
    setattr(_routers_pkg, _stem, _vmod)
    setattr(_self_mod, _stem, _vmod)