"""
mem0 unified memory layer API

Provides memory health check, status query, list browsing, semantic search and deletion management interfaces.
"""

import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger(__name__)

ALL_SCOPES = [
    "conversation", "user_preference", "analysis_insight",
    "skill_lesson", "agent_experience", "trade_pattern",
]


def _resolve_user_id(user: dict) -> str:
    return str(user.get("user_id") or user.get("id") or "")


def _build_metadata_filters(
    *,
    object_type: Optional[str] = None,
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    memory_kind: Optional[str] = None,
) -> Optional[dict[str, str]]:
    filters: dict[str, str] = {}
    if object_type:
        filters["object_type"] = object_type.strip().lower()
    if symbol:
        filters["symbol"] = symbol.strip().upper()
    if market:
        filters["market"] = market.strip().lower()
    if memory_kind:
        filters["memory_kind"] = memory_kind.strip().lower()
    return filters or None


@router.get("/health")
async def memory_health(db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    """mem0 Memory layer health check"""
    from core.memory.service import get_memory_service
    svc = get_memory_service(db)
    result = await svc.health_check()
    ok = bool(result.get("ok", False))
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "success": ok,
            "data": result,
            "message": "" if ok else (result.get("error") or "Memory layer is not available"),
        },
    )


@router.get("/stats")
async def memory_stats(
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the memory statistics of the current user (count by scope)"""
    from core.memory.service import get_memory_service, _is_mem0_enabled
    user_id = _resolve_user_id(user)
    logger.info("[memory-api] stats request — resolved_user_id=%s", user_id)

    if not _is_mem0_enabled():
        return {
            "success": True,
            "data": {"enabled": False, "message": "Memory function is not enabled"},
        }

    svc = get_memory_service(db)
    if not svc.available:
        await svc._ensure_init()

    if not svc.available:
        return {
            "success": True,
            "data": {"enabled": True, "available": False, "message": svc._init_error},
        }

    all_result = await svc.get_all(user_id=user_id, limit=200, page=1)
    total = all_result["total"]
    scope_counts: dict[str, int] = {}
    for item in all_result["items"]:
        s = item.scope or "unknown"
        scope_counts[s] = scope_counts.get(s, 0) + 1

    if total > len(all_result["items"]):
        remaining = await svc.get_all(user_id=user_id, limit=total, page=1)
        scope_counts = {}
        for item in remaining["items"]:
            s = item.scope or "unknown"
            scope_counts[s] = scope_counts.get(s, 0) + 1

    return {
        "success": True,
        "data": {
            "enabled": True,
            "available": True,
            "user_id": user_id,
            "total": total,
            "scopes": scope_counts,
        },
    }


@router.get("/list")
async def memory_list(
    scope: Optional[str] = Query(None, description="Filter by scope"),
    object_type: Optional[str] = Query(None, description="Filter by object type"),
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    market: Optional[str] = Query(None, description="Filter by market"),
    memory_kind: Optional[str] = Query(None, description="Filter by memory type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the memory list of the current user by pagination"""
    from core.memory.service import get_memory_service
    user_id = _resolve_user_id(user)
    logger.info(
        "[memory-api] list request — resolved_user_id=%s scope=%s page=%d page_size=%d",
        user_id, scope, page, page_size,
    )
    svc = get_memory_service(db)

    scopes = [scope] if scope else None
    metadata_filters = _build_metadata_filters(
        object_type=object_type,
        symbol=symbol,
        market=market,
        memory_kind=memory_kind,
    )
    result = await svc.get_all(
        user_id=user_id,
        scopes=scopes,
        metadata_filters=metadata_filters,
        limit=page_size,
        page=page,
    )
    return {
        "success": True,
        "data": {
            "items": [item.model_dump() for item in result["items"]],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/recall")
async def memory_recall(
    query: str = Query(..., min_length=1, description="Query text"),
    scope: Optional[str] = Query(None, description="limited scope"),
    object_type: Optional[str] = Query(None, description="Filter by object type"),
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    market: Optional[str] = Query(None, description="Filter by market"),
    memory_kind: Optional[str] = Query(None, description="Filter by memory type"),
    limit: int = Query(5, ge=1, le=20),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """semantic search memory"""
    from core.memory.service import get_memory_service
    user_id = _resolve_user_id(user)
    logger.info(
        "[memory-api] recall request — resolved_user_id=%s scope=%s limit=%d query=%s",
        user_id, scope, limit, query[:80],
    )
    svc = get_memory_service(db)

    scopes = [scope] if scope else None
    metadata_filters = _build_metadata_filters(
        object_type=object_type,
        symbol=symbol,
        market=market,
        memory_kind=memory_kind,
    )
    items = await svc.recall(
        query=query,
        user_id=user_id,
        scopes=scopes,
        metadata_filters=metadata_filters,
        limit=limit,
    )
    return {
        "success": True,
        "data": {
            "count": len(items),
            "items": [item.model_dump() for item in items],
        },
    }


@router.post("/batch-delete")
async def memory_batch_delete(
    memory_ids: List[str] = Body(..., embed=True),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete memories in batches"""
    from core.memory.service import get_memory_service
    svc = get_memory_service(db)
    deleted = 0
    for mid in memory_ids[:50]:
        if await svc.delete_memory(mid):
            deleted += 1
    return {"success": True, "data": {"deleted": deleted, "requested": len(memory_ids)}}


@router.delete("/clear-all")
async def memory_delete_all(
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Clear all memories of current user"""
    from core.memory.service import get_memory_service
    user_id = _resolve_user_id(user)
    svc = get_memory_service(db)
    count = await svc.delete_all_user_memories(user_id)
    return {"success": True, "data": {"deleted": count}}


@router.delete("/{memory_id}")
async def memory_delete(
    memory_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete a single memory"""
    from core.memory.service import get_memory_service
    svc = get_memory_service(db)
    ok = await svc.delete_memory(memory_id)
    if ok:
        return {"success": True, "message": "memory deleted"}
    return {"success": False, "message": "Deletion failed, please try again later"}


# =============================================================================
# Intelligent Assistant Fact Memory (assistant_memory_facts)
# Unlike mem0 object memory: fact memory is extracted by the intelligent assistant from the network tool results (including numeric
# short sentences,≤150 characters), stored in the assistant_memory_facts collection, recalled across sessions for reference by the assistant.
# Read-only browsing, search and delete capabilities are provided here.
# =============================================================================
_FACTS_COLLECTION = "assistant_memory_facts"


def _serialize_fact(doc: dict) -> dict:
    """Serialize the fact document into a front-end usable dict (_id -> id) . """
    out = {"id": str(doc["_id"])}
    out.update({k: v for k, v in doc.items() if k != "_id"})
    return out


@router.get("/assistant-facts")
async def assistant_facts_list(
    q: Optional[str] = Query(None, description="Search by topic/content keywords"),
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    category: Optional[str] = Query(None, description="Filter by data category"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Paging query of the fact memory extracted by the intelligent assistant (in reverse order of collection time)."""
    query: dict = {}
    if q:
        q = q.strip()
        if q:
            query["$or"] = [
                {"topic": {"$regex": re.escape(q), "$options": "i"}},
                {"content": {"$regex": re.escape(q), "$options": "i"}},
            ]
    if symbol:
        query["symbol"] = symbol.strip()
    if category:
        query["category"] = category.strip()
    total = await db[_FACTS_COLLECTION].count_documents(query)
    cursor = (
        db[_FACTS_COLLECTION]
        .find(query)
        .sort("fetched_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_serialize_fact(doc) async for doc in cursor]
    logger.info("[memory-api] assistant-facts list — page=%d page_size=%d total=%d", page, page_size, total)
    return {
        "success": True,
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.post("/assistant-facts/batch-delete")
async def assistant_facts_batch_delete(
    fact_ids: List[str] = Body(..., embed=True),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete fact memories in batches."""
    from bson import ObjectId
    ids = [ObjectId(fid) for fid in fact_ids[:100] if ObjectId.is_valid(fid)]
    result = await db[_FACTS_COLLECTION].delete_many({"_id": {"$in": ids}})
    return {
        "success": True,
        "data": {"deleted": result.deleted_count, "requested": len(fact_ids)},
    }


@router.delete("/assistant-facts/{fact_id}")
async def assistant_facts_delete(
    fact_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete single fact memory."""
    from bson import ObjectId
    if not ObjectId.is_valid(fact_id):
        return {"success": False, "message": "invalid fact ID"}
    result = await db[_FACTS_COLLECTION].delete_one({"_id": ObjectId(fact_id)})
    if result.deleted_count:
        return {"success": True, "message": "Factual memory deleted"}
    return {"success": False, "message": "Deletion failed, please try again later"}
