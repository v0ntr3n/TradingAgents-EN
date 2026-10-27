"""
Gateway Webhook routing

Receive the Webhook callback of the IM platform (Feishu/QQ/DingTalk),
Entrust GatewayRouter to perform signature verification, message parsing, assistant calling, and reply sending.

endpoint: POST /api/gateway/{platform}
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.database import get_mongo_db
from core.gateway.router import gateway_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


@router.post("/{platform}")
async def gateway_webhook(platform: str, request: Request):
    """
    IM Platform Webhook callback unified entrance

    - Feishu: POST /api/gateway/feishu
    - QQ:   POST /api/gateway/qq
    - DingTalk: POST /api/gateway/dingtalk
    """
    body = await request.body()
    headers = dict(request.headers)

    db = await get_mongo_db()

    resp_json, status_code = await gateway_router.handle_webhook(
        platform=platform,
        headers=headers,
        body=body,
        db=db,
    )

    return JSONResponse(content=resp_json, status_code=status_code)


@router.get("/platforms")
async def list_supported_platforms():
    """List currently registered IM platform adapters"""
    return {
        "platforms": gateway_router.supported_platforms,
    }

