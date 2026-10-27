#!/usr/bin/env python3
"""
Multi-cycle data synchronization API
Provides synchronization management interface for daily, weekly and monthly data
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.worker.multi_period_sync_service import get_multi_period_sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multi-period-sync", tags=["Multi-cycle synchronization"])


class MultiPeriodSyncRequest(BaseModel):
    """Multi-cycle synchronization request"""
    symbols: Optional[List[str]] = Field(None, description="List of stock codes, None means all stocks")
    periods: Optional[List[str]] = Field(["daily"], description="period list (daily/weekly/monthly)")
    data_sources: Optional[List[str]] = Field(["tushare", "akshare", "baostock"], description="Data source list")
    start_date: Optional[str] = Field(None, description="start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="end date (YYYY-MM-DD)")
    all_history: Optional[bool] = Field(False, description="Whether to synchronize all historical data (ignore time range)")


class MultiPeriodSyncResponse(BaseModel):
    """Multi-cycle synchronous response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post("/start", response_model=MultiPeriodSyncResponse)
async def start_multi_period_sync(
    request: MultiPeriodSyncRequest,
    background_tasks: BackgroundTasks
):
    """
    Start multi-cycle data synchronization
    """
    try:
        service = await get_multi_period_sync_service()
        
        # Background task execution synchronization
        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=request.symbols,
            periods=request.periods,
            data_sources=request.data_sources,
            start_date=request.start_date,
            end_date=request.end_date,
            all_history=request.all_history
        )
        
        return MultiPeriodSyncResponse(
            success=True,
            message="Multi-cycle data synchronization has started",
            data={
                "request_params": request.dict(),
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start multi-cycle synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {e}")


@router.post("/start-daily", response_model=MultiPeriodSyncResponse)
async def start_daily_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start daily data synchronization"""
    try:
        service = await get_multi_period_sync_service()
        
        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=["daily"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"]
        )
        
        return MultiPeriodSyncResponse(
            success=True,
            message="Daily data synchronization has started",
            data={
                "period": "daily",
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start daily synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start daily synchronization: {e}")


@router.post("/start-weekly", response_model=MultiPeriodSyncResponse)
async def start_weekly_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start weekly data synchronization"""
    try:
        service = await get_multi_period_sync_service()
        
        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=["weekly"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"]
        )
        
        return MultiPeriodSyncResponse(
            success=True,
            message="Weekly data synchronization has started",
            data={
                "period": "weekly",
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start weekly synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start weekly synchronization: {e}")


@router.post("/start-monthly", response_model=MultiPeriodSyncResponse)
async def start_monthly_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start monthly data synchronization"""
    try:
        service = await get_multi_period_sync_service()

        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=["monthly"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"]
        )

        return MultiPeriodSyncResponse(
            success=True,
            message="Monthly data synchronization has started",
            data={
                "period": "monthly",
                "start_time": datetime.utcnow().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"Failed to start monthly synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start monthly synchronization: {e}")


@router.post("/start-all-history", response_model=MultiPeriodSyncResponse)
async def start_all_history_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    periods: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start full historical data synchronization (starting in 1990)"""
    try:
        service = await get_multi_period_sync_service()

        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=periods or ["daily", "weekly", "monthly"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"],
            all_history=True
        )

        return MultiPeriodSyncResponse(
            success=True,
            message="Full historical data synchronization started (from 1990)",
            data={
                "sync_type": "all_history",
                "periods": periods or ["daily", "weekly", "monthly"],
                "data_sources": data_sources or ["tushare", "akshare", "baostock"],
                "date_range": "1990-01-01 to today",
                "start_time": datetime.utcnow().isoformat(),
                "warning": "Full historical data synchronization may take a long time, please be patient."
            }
        )

    except Exception as e:
        logger.error(f"Failed to start full history synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start full history synchronization: {e}")


@router.post("/start-incremental", response_model=MultiPeriodSyncResponse)
async def start_incremental_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    periods: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None,
    days_back: Optional[int] = 30
):
    """Start incremental data synchronization (last N days)"""
    try:
        from datetime import datetime, timedelta

        service = await get_multi_period_sync_service()

        # Calculate date range for incremental synchronization
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=periods or ["daily"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"],
            start_date=start_date,
            end_date=end_date
        )

        return MultiPeriodSyncResponse(
            success=True,
            message=f"Incremental data synchronization started (recently{days_back}days)",
            data={
                "sync_type": "incremental",
                "periods": periods or ["daily"],
                "data_sources": data_sources or ["tushare", "akshare", "baostock"],
                "date_range": f"{start_date} Arrive {end_date}",
                "days_back": days_back,
                "start_time": datetime.utcnow().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"Failed to start incremental sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start incremental sync: {e}")


@router.get("/statistics")
async def get_sync_statistics():
    """Get multi-cycle synchronization statistics"""
    try:
        service = await get_multi_period_sync_service()
        stats = await service.get_sync_statistics()
        
        return {
            "success": True,
            "data": stats,
            "message": "Statistics obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to obtain synchronization statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain statistics: {e}")


@router.get("/period-comparison/{symbol}")
async def compare_period_data(
    symbol: str,
    trade_date: str,
    data_source: str = "tushare"
):
    """
    Compare data from different periods for the same stock
    """
    try:
        from app.services.historical_data_service import get_historical_data_service
        service = await get_historical_data_service()
        
        periods = ["daily", "weekly", "monthly"]
        comparison = {}
        
        for period in periods:
            results = await service.get_historical_data(
                symbol=symbol,
                start_date=trade_date,
                end_date=trade_date,
                data_source=data_source,
                period=period,
                limit=1
            )
            
            if results:
                comparison[period] = results[0]
            else:
                comparison[period] = None
        
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "trade_date": trade_date,
                "data_source": data_source,
                "comparison": comparison,
                "available_periods": [k for k, v in comparison.items() if v is not None]
            },
            "message": "Cycle data comparison completed"
        }
        
    except Exception as e:
        logger.error(f"Period data comparison failed {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Period data comparison failed: {e}")


@router.get("/supported-periods")
async def get_supported_periods():
    """Get supported data periods"""
    return {
        "success": True,
        "data": {
            "periods": [
                {
                    "code": "daily",
                    "name": "daily line",
                    "description": "Daily transaction data",
                    "supported_sources": ["tushare", "akshare", "baostock"]
                },
                {
                    "code": "weekly",
                    "name": "perimeter",
                    "description": "Weekly transaction data",
                    "supported_sources": ["tushare", "akshare", "baostock"]
                },
                {
                    "code": "monthly",
                    "name": "monthly line",
                    "description": "monthly transaction data",
                    "supported_sources": ["tushare", "akshare", "baostock"]
                }
            ],
            "data_sources": [
                {
                    "code": "tushare",
                    "name": "Tushare",
                    "description": "Professional financial data services",
                    "supported_periods": ["daily", "weekly", "monthly"]
                },
                {
                    "code": "akshare",
                    "name": "AKShare",
                    "description": "Free open source financial data",
                    "supported_periods": ["daily", "weekly", "monthly"]
                },
                {
                    "code": "baostock",
                    "name": "BaoStock",
                    "description": "Free securities data platform",
                    "supported_periods": ["daily", "weekly", "monthly"]
                }
            ]
        },
        "message": "Supported cycle information is obtained successfully"
    }


@router.get("/health")
async def health_check():
    """health check"""
    try:
        service = await get_multi_period_sync_service()
        stats = await service.get_sync_statistics()
        
        return {
            "success": True,
            "data": {
                "service": "Multi-cycle synchronization service",
                "status": "healthy",
                "statistics": stats,
                "last_check": datetime.utcnow().isoformat()
            },
            "message": "Service is normal"
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "data": {
                "service": "Multi-cycle synchronization service",
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            },
            "message": "Service exception"
        }
