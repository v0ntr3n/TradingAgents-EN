"""
AKShare Data initialization API routing
Provides a web interface for AKShare data initialization and management
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db
from app.worker.akshare_init_service import get_akshare_init_service
from app.worker.akshare_sync_service import get_akshare_sync_service
from app.routers.auth_db import get_current_user
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/akshare-init", tags=["AKShare initialization"])

# Global task state storage
_initialization_status = {
    "is_running": False,
    "current_task": None,
    "start_time": None,
    "progress": None,
    "result": None
}


class InitializationRequest(BaseModel):
    """Initialize request model"""
    historical_days: int = Field(default=365, ge=1, le=3650, description="Historical data days")
    force: bool = Field(default=False, description="Whether to force reinitialization")
    skip_if_exists: bool = Field(default=True, description="Whether to skip if data exists")


class SyncRequest(BaseModel):
    """Synchronous request model"""
    force_update: bool = Field(default=False, description="Whether to force update")
    symbols: Optional[list] = Field(default=None, description="Specify stock code list")


@router.get("/status")
async def get_database_status():
    """
    Get database status
    
    Returns:
        Database status information
    """
    try:
        db = get_mongo_db()
        
        # Check basic information
        basic_count = await db.stock_basic_info.count_documents({})
        extended_count = await db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        # Get the latest update time
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        # Check market data
        quotes_count = await db.market_quotes.count_documents({})
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        # Data quality assessment
        data_quality = "excellent"
        if basic_count == 0:
            data_quality = "empty"
        elif extended_count / basic_count < 0.5:
            data_quality = "poor"
        elif extended_count / basic_count < 0.9:
            data_quality = "good"
        
        return {
            "success": True,
            "data": {
                "basic_info": {
                    "total_count": basic_count,
                    "extended_count": extended_count,
                    "coverage_rate": round(extended_count / basic_count * 100, 2) if basic_count > 0 else 0,
                    "latest_update": latest_basic.get("updated_at") if latest_basic else None
                },
                "market_quotes": {
                    "total_count": quotes_count,
                    "latest_update": latest_quotes.get("updated_at") if latest_quotes else None
                },
                "data_quality": data_quality,
                "check_time": now_tz()
            },
            "message": "Database status check completed"
        }
        
    except Exception as e:
        logger.error(f"Failed to get database status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get database status: {str(e)}")


@router.get("/connection-test")
async def test_akshare_connection():
    """
    Test AKShare connection status
    
    Returns:
        Connection test results
    """
    try:
        service = await get_akshare_sync_service()
        connected = await service.provider.test_connection()
        
        result = {
            "connected": connected,
            "test_time": now_tz()
        }
        
        if connected:
            # Test to get the stock list
            try:
                stock_list = await service.provider.get_stock_list()
                result["stock_count"] = len(stock_list) if stock_list else 0
                result["sample_stocks"] = stock_list[:5] if stock_list else []
            except Exception as e:
                result["stock_list_error"] = str(e)
        
        return {
            "success": True,
            "data": result,
            "message": "AKShare Connection test completed"
        }
        
    except Exception as e:
        logger.error(f"AKShare Connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.post("/start-full")
async def start_full_initialization(
    request: InitializationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start full data initialization
    
    Args:
        request: Initialize request parameters
        background_tasks: Background task manager
        current_user: Current user information
        
    Returns:
        Initialization startup results
    """
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="Initialization task is running")
    
    try:
        # Set task status
        _initialization_status.update({
            "is_running": True,
            "current_task": "full_initialization",
            "start_time": now_tz(),
            "progress": {"current_step": "In preparation", "completed_steps": 0, "total_steps": 6},
            "result": None
        })
        
        # Start background task
        background_tasks.add_task(
            _run_full_initialization_background,
            request.historical_days,
            not request.skip_if_exists
        )
        
        return {
            "success": True,
            "data": {
                "task_id": "full_initialization",
                "start_time": _initialization_status["start_time"],
                "parameters": {
                    "historical_days": request.historical_days,
                    "force": not request.skip_if_exists
                }
            },
            "message": "The full initialization task has been started, please use /initialization-status to view the progress"
        }
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Start full initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup initialization failed: {str(e)}")


@router.post("/start-basic-sync")
async def start_basic_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start basic information synchronization
    
    Args:
        request: Synchronous request parameters
        background_tasks: Background task manager
        current_user: Current user information
        
    Returns:
        Synchronous startup results
    """
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="Sync task is running")
    
    try:
        # Set task status
        _initialization_status.update({
            "is_running": True,
            "current_task": "basic_sync",
            "start_time": now_tz(),
            "progress": {"current_step": "Synchronize basic information", "completed_steps": 0, "total_steps": 1},
            "result": None
        })
        
        # Start background task
        background_tasks.add_task(
            _run_basic_sync_background,
            request.force_update
        )
        
        return {
            "success": True,
            "data": {
                "task_id": "basic_sync",
                "start_time": _initialization_status["start_time"],
                "parameters": {
                    "force_update": request.force_update
                }
            },
            "message": "Basic information synchronization task has been started"
        }
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Failed to start basic information synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {str(e)}")


@router.get("/initialization-status")
async def get_initialization_status():
    """
    Get initialization task status
    
    Returns:
        Current task status
    """
    global _initialization_status
    
    return {
        "success": True,
        "data": {
            "is_running": _initialization_status["is_running"],
            "current_task": _initialization_status["current_task"],
            "start_time": _initialization_status["start_time"],
            "progress": _initialization_status["progress"],
            "result": _initialization_status["result"],
            "duration": (
                (now_tz() - _initialization_status["start_time"]).total_seconds()
                if _initialization_status["start_time"] else 0
            )
        },
        "message": "Task status obtained successfully"
    }


@router.post("/stop")
async def stop_initialization(current_user: dict = Depends(get_current_user)):
    """
    Stop the current initialization task
    
    Args:
        current_user: Current user information
        
    Returns:
        Stop results
    """
    global _initialization_status
    
    if not _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="No tasks running")
    
    try:
        # Reset task status
        _initialization_status.update({
            "is_running": False,
            "current_task": None,
            "start_time": None,
            "progress": None,
            "result": {"stopped": True, "stop_time": datetime.utcnow()}
        })
        
        return {
            "success": True,
            "data": {
                "stopped": True,
                "stop_time": datetime.utcnow()
            },
            "message": "The initialization task has stopped"
        }
        
    except Exception as e:
        logger.error(f"Stop initialization task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stop task failed: {str(e)}")


async def _run_full_initialization_background(historical_days: int, force: bool):
    """Run full initialization in the background"""
    global _initialization_status
    
    try:
        service = await get_akshare_init_service()
        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force
        )
        
        _initialization_status.update({
            "is_running": False,
            "result": result
        })
        
        logger.info(f"Complete initialization background task completed: {result}")
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "result": {"success": False, "error": str(e)}
        })
        logger.error(f"Complete initialization of background task failed: {e}")


async def _run_basic_sync_background(force_update: bool):
    """Basic information synchronization running in the background"""
    global _initialization_status
    
    try:
        service = await get_akshare_sync_service()
        result = await service.sync_stock_basic_info(
            force_update=force_update,
            manual_mode=True  # Manual initialization should not inherit scheduled task cancellation status
        )
        
        _initialization_status.update({
            "is_running": False,
            "result": result
        })
        
        logger.info(f"Basic information synchronization background task completed: {result}")
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "result": {"success": False, "error": str(e)}
        })
        logger.error(f"Basic information synchronization background task failed: {e}")
