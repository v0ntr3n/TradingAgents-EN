#!/usr/bin/env python3
"""
BaoStock Initialize API routing
Provides RESTful API interface for BaoStock data initialization
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.worker.baostock_init_service import BaoStockInitService
from app.worker.baostock_sync_service import BaoStockSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/baostock-init", tags=["BaoStock initialization"])

# Global state management
_initialization_status = {
    "is_running": False,
    "current_task": None,
    "stats": None,
    "start_time": None,
    "last_update": None
}


class InitializationRequest(BaseModel):
    """Initialize request model"""
    historical_days: int = Field(default=365, ge=1, le=3650, description="Historical data days")
    force: bool = Field(default=False, description="Whether to force reinitialization")


class InitializationResponse(BaseModel):
    """Initialize response model"""
    success: bool
    message: str
    task_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.get("/status", response_model=Dict[str, Any])
async def get_database_status():
    """Get database status"""
    try:
        service = BaoStockInitService()
        status = await service.check_database_status()
        
        return {
            "success": True,
            "data": status,
            "message": "Database status obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to get database status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get database status: {e}")


@router.get("/connection-test", response_model=Dict[str, Any])
async def test_baostock_connection():
    """Test BaoStock connection"""
    try:
        service = BaoStockSyncService()
        connected = await service.provider.test_connection()
        
        return {
            "success": connected,
            "data": {
                "connected": connected,
                "test_time": datetime.now().isoformat()
            },
            "message": "BaoStock The connection is normal" if connected else "BaoStock Connection failed"
        }
        
    except Exception as e:
        logger.error(f"BaoStock Connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connection test failed: {e}")


@router.post("/start-full", response_model=InitializationResponse)
async def start_full_initialization(
    request: InitializationRequest,
    background_tasks: BackgroundTasks
):
    """Start full initialization"""
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(
            status_code=409, 
            detail="The initialization task is running, please wait for completion and try again."
        )
    
    try:
        # Generate tasks ID
        task_id = f"baostock_full_init_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # update status
        _initialization_status.update({
            "is_running": True,
            "current_task": "full_initialization",
            "stats": None,
            "start_time": datetime.now(),
            "last_update": datetime.now()
        })
        
        # Start background task
        background_tasks.add_task(
            _run_full_initialization_task,
            request.historical_days,
            request.force,
            task_id
        )
        
        return InitializationResponse(
            success=True,
            message="Full initialization task started",
            task_id=task_id,
            data={
                "historical_days": request.historical_days,
                "force": request.force,
                "estimated_duration": "30-60 minutes"
            }
        )
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Start full initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup initialization failed: {e}")


@router.post("/start-basic", response_model=InitializationResponse)
async def start_basic_initialization(background_tasks: BackgroundTasks):
    """Start basic initialization"""
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="The initialization task is running, please wait for completion and try again."
        )
    
    try:
        # Generate tasks ID
        task_id = f"baostock_basic_init_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # update status
        _initialization_status.update({
            "is_running": True,
            "current_task": "basic_initialization",
            "stats": None,
            "start_time": datetime.now(),
            "last_update": datetime.now()
        })
        
        # Start background task
        background_tasks.add_task(_run_basic_initialization_task, task_id)
        
        return InitializationResponse(
            success=True,
            message="Basic initialization tasks have been started",
            task_id=task_id,
            data={
                "estimated_duration": "10-20 minutes"
            }
        )
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Startup basic initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup initialization failed: {e}")


@router.get("/initialization-status", response_model=Dict[str, Any])
async def get_initialization_status():
    """Get initialization status"""
    global _initialization_status
    
    try:
        status = _initialization_status.copy()
        
        # Calculate running time
        if status["start_time"]:
            if status["is_running"]:
                duration = (datetime.now() - status["start_time"]).total_seconds()
            else:
                duration = (status["last_update"] - status["start_time"]).total_seconds() if status["last_update"] else 0
            status["duration"] = duration
        
        # Format statistics
        if status["stats"]:
            stats = status["stats"]
            status["progress"] = {
                "completed_steps": stats.completed_steps,
                "total_steps": stats.total_steps,
                "current_step": stats.current_step,
                "progress_percent": (stats.completed_steps / stats.total_steps) * 100
            }
            status["data_summary"] = {
                "basic_info_count": stats.basic_info_count,
                "quotes_count": stats.quotes_count,
                "historical_records": stats.historical_records,
                "financial_records": stats.financial_records,
                "error_count": len(stats.errors)
            }
        
        return {
            "success": True,
            "data": status,
            "message": "Status obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to obtain initialization status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@router.post("/stop", response_model=Dict[str, Any])
async def stop_initialization():
    """Stop initialization task"""
    global _initialization_status
    
    if not _initialization_status["is_running"]:
        return {
            "success": True,
            "message": "There are no initialization tasks running",
            "data": {"was_running": False}
        }
    
    try:
        # update status
        _initialization_status.update({
            "is_running": False,
            "current_task": None,
            "last_update": datetime.now()
        })
        
        return {
            "success": True,
            "message": "The initialization task has stopped",
            "data": {"was_running": True}
        }
        
    except Exception as e:
        logger.error(f"Stop initialization task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stop task failed: {e}")


async def _run_full_initialization_task(historical_days: int, force: bool, task_id: str):
    """Run full initialization task"""
    global _initialization_status
    
    try:
        logger.info(f"🚀 Start BaoStock complete initialization task: {task_id}")
        
        service = BaoStockInitService()
        stats = await service.full_initialization(
            historical_days=historical_days,
            force=force
        )
        
        # update status
        _initialization_status.update({
            "is_running": False,
            "stats": stats,
            "last_update": datetime.now()
        })
        
        if stats.completed_steps == stats.total_steps:
            logger.info(f"✅ BaoStock Complete initialization task completed: {task_id}")
        else:
            logger.warning(f"⚠️ BaoStock Complete initialization task partially completed: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ BaoStock Complete initialization task failed: {task_id}, Error: {e}")
        _initialization_status.update({
            "is_running": False,
            "last_update": datetime.now()
        })


async def _run_basic_initialization_task(task_id: str):
    """Run basic initialization tasks"""
    global _initialization_status
    
    try:
        logger.info(f"🚀 Start BaoStock basic initialization task: {task_id}")
        
        service = BaoStockInitService()
        stats = await service.basic_initialization()
        
        # update status
        _initialization_status.update({
            "is_running": False,
            "stats": stats,
            "last_update": datetime.now()
        })
        
        if stats.completed_steps == stats.total_steps:
            logger.info(f"✅ BaoStock Basic initialization tasks completed: {task_id}")
        else:
            logger.warning(f"⚠️ BaoStock Basic initialization tasks partially completed: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ BaoStock Basic initialization task failed: {task_id}, Error: {e}")
        _initialization_status.update({
            "is_running": False,
            "last_update": datetime.now()
        })


@router.get("/service-status", response_model=Dict[str, Any])
async def get_service_status():
    """Get BaoStock service status"""
    try:
        service = BaoStockSyncService()
        status = await service.check_service_status()
        
        return {
            "success": True,
            "data": status,
            "message": "Service status obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to get service status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get service status: {e}")
