"""
Using Statistics API routing
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException

from app.routers.auth_db import get_current_user
from app.models.config import UsageRecord, UsageStatistics
from app.services.usage_statistics_service import usage_statistics_service

logger = logging.getLogger("app.routers.usage_statistics")

router = APIRouter(prefix="/api/usage", tags=["usage statistics"], redirect_slashes=False)


# ============================================================================
# /api/usage/stats - KPI Friendly and concise statistical endpoint (v3.0 for JD Cloud dashboard)
# Return {used_tokens, quota_tokens, percentage, period_days, reset_at}
# quota_tokens Source:
#   1. Jingdong cloud model: Environment variable JDYUN_TOKEN_QUOTA (optional, default 0 means no quota)
#   2. Standard Edition: License Premium feature quota (0 if not configured)
# When quota_tokens = 0 The quota percentage is not displayed, only the cumulative usage is displayed.
# ============================================================================

def _resolve_token_quota() -> int:
    """Analyze the current user s Token quota limit (0 means no limit)"""
    # JD Cloud mode: reading from environment variables
    if os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes"):
        return int(os.getenv("JDYUN_TOKEN_QUOTA", "0"))
    # Standard Edition: Unlimited by default, can be expanded by License module
    return 0


@router.get("/stats", summary="Get KPI usage statistics")
async def get_usage_stats(
    days: int = Query(7, ge=1, le=365, description="Number of statistical days (default last 7 days)"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get concise, KPI-friendly usage statistics

    for dashboard"API Dosage"Card, returns used Token/Quota/Percentage.
    Difference from /api/usage/statistics:
    - statistics Return multi-dimensional detailed statistics (by_provider/by_model/by_date)
    - stats Return single value KPI (used_tokens/quota_tokens/percentage)

    quota_tokens Source:
    - JD Cloud mode: environment variable JDYUN_TOKEN_QUOTA (default 0 means no quota)
    - Standard Edition: Unlimited by default, can be expanded by License module

    When quota_tokens = 0 when,percentage = 0, The front end only displays the accumulated usage and does not display the progress bar.
    """
    try:
        # Reuse existing services to get detailed statistics
        stats = await usage_statistics_service.get_usage_statistics(days=days)

        used_tokens = stats.total_input_tokens + stats.total_output_tokens
        quota_tokens = _resolve_token_quota()
        percentage = round((used_tokens / quota_tokens) * 100, 2) if quota_tokens > 0 else 0.0

        # Quota reset time: end time of the current cycle (days later)
        reset_at = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"

        return {
            "success": True,
            "message": "Obtaining usage statistics successfully",
            "data": {
                "used_tokens": used_tokens,
                "quota_tokens": quota_tokens,
                "percentage": percentage,
                "period_days": days,
                "reset_at": reset_at,
                "input_tokens": stats.total_input_tokens,
                "output_tokens": stats.total_output_tokens,
                "total_requests": stats.total_requests,
                "currency_breakdown": stats.cost_by_currency,
            }
        }
    except Exception as e:
        logger.error(f"Failed to obtain KPI usage statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records", summary="Get usage records")
async def get_usage_records(
    provider: Optional[str] = Query(None, description="supplier"),
    model_name: Optional[str] = Query(None, description="Model name"),
    start_date: Optional[str] = Query(None, description="start date(ISO Format)"),
    end_date: Optional[str] = Query(None, description="end date(ISO Format)"),
    limit: int = Query(100, ge=1, le=1000, description="Return the number of records"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get usage records"""
    try:
        # parse date
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        # Get records
        records = await usage_statistics_service.get_usage_records(
            provider=provider,
            model_name=model_name,
            start_date=start_dt,
            end_date=end_dt,
            limit=limit
        )

        return {
            "success": True,
            "message": "Obtain usage record successfully",
            "data": {
                "records": [record.model_dump() for record in records],
                "total": len(records)
            }
        }
    except Exception as e:
        logger.error(f"Failed to obtain usage records: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", summary="Get usage statistics")
async def get_usage_statistics(
    days: int = Query(7, ge=1, le=365, description="Statistical days"),
    provider: Optional[str] = Query(None, description="supplier"),
    model_name: Optional[str] = Query(None, description="Model name"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get usage statistics"""
    try:
        stats = await usage_statistics_service.get_usage_statistics(
            days=days,
            provider=provider,
            model_name=model_name
        )

        return {
            "success": True,
            "message": "Obtain usage statistics successfully",
            "data": stats.model_dump()
        }
    except Exception as e:
        logger.error(f"Failed to obtain usage statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/by-provider", summary="Cost statistics by supplier")
async def get_cost_by_provider(
    days: int = Query(7, ge=1, le=365, description="Statistical days"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Cost statistics by supplier"""
    try:
        cost_data = await usage_statistics_service.get_cost_by_provider(days=days)

        return {
            "success": True,
            "message": "Obtain cost statistics successfully",
            "data": cost_data
        }
    except Exception as e:
        logger.error(f"Failed to obtain cost statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/by-model", summary="Cost statistics by model")
async def get_cost_by_model(
    days: int = Query(7, ge=1, le=365, description="Statistical days"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Cost statistics by model"""
    try:
        cost_data = await usage_statistics_service.get_cost_by_model(days=days)

        return {
            "success": True,
            "message": "Obtain cost statistics successfully",
            "data": cost_data
        }
    except Exception as e:
        logger.error(f"Failed to obtain cost statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/daily", summary="Daily cost statistics")
async def get_daily_cost(
    days: int = Query(7, ge=1, le=365, description="Statistical days"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Daily cost statistics"""
    try:
        cost_data = await usage_statistics_service.get_daily_cost(days=days)

        return {
            "success": True,
            "message": "Get daily cost successfully",
            "data": cost_data
        }
    except Exception as e:
        logger.error(f"Failed to get daily cost: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/records/old", summary="Delete old records")
async def delete_old_records(
    days: int = Query(90, ge=30, le=365, description="retention days"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete old records"""
    try:
        deleted_count = await usage_statistics_service.delete_old_records(days=days)

        return {
            "success": True,
            "message": f"Delete old records successfully",
            "data": {"deleted_count": deleted_count}
        }
    except Exception as e:
        logger.error(f"Failed to delete old records: {e}")
        raise HTTPException(status_code=500, detail=str(e))

