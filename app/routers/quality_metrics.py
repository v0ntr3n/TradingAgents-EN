"""Report quality metrics API routing (v3.6.0 item 5)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_mongo_db
from app.routers.auth_db import get_current_user
from app.services.quality_metrics_service import get_quality_metrics_service

router = APIRouter(prefix="/api/quality-metrics", tags=["quality-metrics"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_quality_summary(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
):
    """Get quality summary statistics (for the numbers at the top of the dashboard)."""
    user_id = str(current_user.id) if hasattr(current_user, "id") else str(current_user.get("_id", ""))
    svc = get_quality_metrics_service(db)
    summary = await svc.get_quality_summary(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return summary


@router.get("/records")
async def list_quality_records(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    ticker: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    only_low_quality: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
):
    """Query the quality index record list."""
    user_id = str(current_user.id) if hasattr(current_user, "id") else str(current_user.get("_id", ""))
    svc = get_quality_metrics_service(db)
    records = await svc.query_metrics(
        user_id=user_id,
        ticker=ticker,
        agent_id=agent_id,
        agent_type=agent_type,
        start_date=start_date,
        end_date=end_date,
        only_low_quality=only_low_quality,
        limit=limit,
    )
    return {"items": records, "count": len(records)}


@router.post("/record")
async def record_metric(
    payload: dict,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Manually write a quality indicator record (usually automatically called by the workflow, this interface is for debugging)."""
    user_id = str(current_user.id) if hasattr(current_user, "id") else str(current_user.get("_id", ""))
    svc = get_quality_metrics_service(db)
    record_id = await svc.record_analysis_metrics(
        user_id=user_id,
        ticker=payload.get("ticker", ""),
        agent_id=payload.get("agent_id", ""),
        agent_type=payload.get("agent_type", ""),
        report_content=payload.get("report_content", ""),
        report_length=payload.get("report_length", 0),
        is_low_quality=payload.get("is_low_quality", False),
        quality_flags=payload.get("quality_flags", []),
        hit_fallback=payload.get("hit_fallback", False),
        fallback_pattern=payload.get("fallback_pattern", ""),
        llm_elapsed_seconds=payload.get("llm_elapsed_seconds", 0.0),
        llm_tokens_used=payload.get("llm_tokens_used", 0),
        llm_cost_estimate=payload.get("llm_cost_estimate", 0.0),
        retry_count=payload.get("retry_count", 0),
        analysis_date=payload.get("analysis_date", ""),
        workflow_id=payload.get("workflow_id", ""),
        extra=payload.get("extra"),
    )
    if not record_id:
        raise HTTPException(status_code=500, detail="Write failed")
    return {"success": True, "record_id": record_id}
