"""
Smart filtering API routing

Reuse the ChatRequest schema and add a filter-specific response model.
"""

import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional

from app.core.database import get_mongo_db
from app.routers.auth_db import get_current_user
from app.routers.websocket_notifications import _authenticate_websocket
from app.services.auth_service import AuthService
from app.schemas.intelligent_assistant import ChatRequest
from app.schemas.intelligent_screening import (
    ScreeningChatResponse,
    ScreeningConversationResponse,
    ScreeningConversationListResponse,
    ScreeningConversationSummary,
    ScreeningMessageItem,
)
from app.services.intelligent_screening_service import IntelligentScreeningService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

# Configuration: whether to use V2 version
USE_V2 = os.environ.get("SCREENING_USE_V2", "true").lower() in ("true", "1", "yes")

# Delayed import of V2 services (avoiding circular dependencies)
def get_screening_service(db: AsyncIOMotorDatabase):
    if USE_V2:
        try:
            from app.services.intelligent_screening_v2 import IntelligentScreeningServiceV2
            logger.info("[Smart filtering] Use V2 version (based on intent understanding)")
            return IntelligentScreeningServiceV2(db)
        except Exception as e:
            logger.warning(f"[Smart filtering] V2 Version loading failed: {e}, Fallback to V1")

    logger.info("[Smart filtering] Use V1 version (keyword matching)")
    return IntelligentScreeningService(db)


router = APIRouter(prefix="/api/screening/intelligent")
user_service = UserService()


@router.post("/chat", response_model=ScreeningChatResponse, summary="Intelligent filtering of conversations")
async def chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Handle the user s stock picking dialogue request.

    - New requirement: return phase="confirmation", Contains needs analysis and improvement suggestions
    - Confirm/Question: Return phase="result", Contains recommended stocks
    """
    user_id = str(user.get("_id", user.get("id", "")))
    service = get_screening_service(db)
    result = await service.chat(user_id, req.message, conversation_id=req.conversation_id)
    return result


@router.websocket("/ws")
async def websocket_chat(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """Intelligent filtering of WebSocket endpoints, real-time push progress by stage and tool call.

    Authentication method:
    - JWT mode: ws://.../ws?token=<jwt_token>
    - Jingdong cloud model: ws://.../ws  (No token required, Basic Auth injected by gateway)
    """
    user_id = await _authenticate_websocket(websocket, token)
    if not user_id:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    db = get_mongo_db()

    await websocket.send_json({
        "type": "connected",
        "data": {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Intelligent filtering streaming connection established",
        },
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Message format error, needs to be JSON"},
                })
                continue

            msg_type = payload.get("type")
            if msg_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "data": {"timestamp": datetime.utcnow().isoformat()},
                })
                continue

            if msg_type != "chat":
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Unsupported message type"},
                })
                continue

            message = str(payload.get("message") or "").strip()
            conversation_id = payload.get("conversation_id")
            if not message:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Message cannot be empty"},
                })
                continue

            service = get_screening_service(db)

            async def progress_sender(event: dict):
                await websocket.send_json({"type": "progress", "data": event})

            await websocket.send_json({
                "type": "started",
                "data": {
                    "message": "Screening request received and processing started",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            })

            try:
                result = await service.chat(
                    user_id,
                    message,
                    conversation_id=conversation_id,
                    progress_callback=progress_sender,
                )
                await websocket.send_json({"type": "final", "data": result})
            except Exception as e:
                logger.exception("[Smart filtering WS] Processing failed")
                await websocket.send_json({
                    "type": "error",
                    "data": {
                        "message": f"Processing failed:{str(e)}",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                })
    except WebSocketDisconnect:
        logger.info("[Smart filtering WS] Client disconnected: user=%s", user_id)


@router.get("/conversation", response_model=ScreeningConversationResponse, summary="Get filtered conversation history")
async def get_conversation(
    conversation_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the current user s smart filter conversation history"""
    user_id = str(user.get("_id", user.get("id", "")))
    service = get_screening_service(db)
    resolved_conversation_id, messages = await service.get_conversation(user_id, conversation_id)
    items = []
    for m in messages:
        items.append(ScreeningMessageItem(
            role=m.get("role", ""),
            content=m.get("content", ""),
            tools_used=m.get("tools_used"),
            stocks=m.get("stocks"),
            phase=m.get("phase"),
            is_fallback=m.get("is_fallback"),
        ))
    return ScreeningConversationResponse(conversation_id=resolved_conversation_id, messages=items)


@router.get("/conversations", response_model=ScreeningConversationListResponse, summary="Get filtered history conversation list")
async def list_conversations(
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the current user s smart filter history session list"""
    user_id = str(user.get("_id", user.get("id", "")))
    service = get_screening_service(db)
    conversations = await service.list_conversations(user_id)
    items = [ScreeningConversationSummary(**item) for item in conversations]
    return ScreeningConversationListResponse(items=items)


@router.delete("/conversation", summary="Clear filtered conversation history")
async def clear_conversation(
    conversation_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Clear the current user s smart filter conversation history"""
    user_id = str(user.get("_id", user.get("id", "")))
    service = get_screening_service(db)
    await service.clear_conversation(user_id, conversation_id)
    return {"message": "Smart filter conversation cleared"}

