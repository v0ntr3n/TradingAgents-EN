"""
Tushare Data initialization API routing
Provides data initialization function for Web interface
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.worker.tushare_init_service import get_tushare_init_service
from app.core.response import ok

router = APIRouter(prefix="/api/tushare-init", tags=["Tushare initialization"])


class InitializationRequest(BaseModel):
    """Initialize request model"""
    historical_days: int = Field(default=365, ge=1, le=3650, description="Historical data days")
    skip_if_exists: bool = Field(default=True, description="Whether to skip if the data already exists")
    force_update: bool = Field(default=False, description="Force update of existing data")


class DatabaseStatusResponse(BaseModel):
    """Database status response model"""
    basic_info_count: int = Field(description="Amount of basic information")
    quotes_count: int = Field(description="Quantity of market data")
    extended_coverage: float = Field(description="Extended field coverage")
    latest_basic_update: Optional[datetime] = Field(description="Basic information latest update time")
    latest_quotes_update: Optional[datetime] = Field(description="Latest update time of market data")
    needs_initialization: bool = Field(description="Whether initialization is required")


class InitializationStatusResponse(BaseModel):
    """Initialize state response model"""
    is_running: bool = Field(description="Is it running")
    current_step: Optional[str] = Field(description="current step")
    progress: Optional[str] = Field(description="Progress")
    started_at: Optional[datetime] = Field(description="start time")
    estimated_completion: Optional[datetime] = Field(description="Estimated completion time")


# Global initialization status tracking
_initialization_status = {
    "is_running": False,
    "current_step": None,
    "progress": None,
    "started_at": None,
    "task": None
}


@router.get("/status", response_model=dict)
async def get_database_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get database status
    Check the data situation in the current database to determine whether initialization is needed
    """
    try:
        db = get_mongo_db()
        
        # Check the status of each collection
        basic_count = await db.stock_basic_info.count_documents({})
        quotes_count = await db.market_quotes.count_documents({})
        
        # Check extension field coverage
        extended_count = 0
        extended_coverage = 0.0
        if basic_count > 0:
            extended_count = await db.stock_basic_info.count_documents({
                "full_symbol": {"$exists": True},
                "market_info": {"$exists": True}
            })
            extended_coverage = extended_count / basic_count
        
        # Check the latest update time
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        # Determine whether initialization is required
        needs_initialization = (
            basic_count == 0 or 
            extended_coverage < 0.5
        )
        
        status = DatabaseStatusResponse(
            basic_info_count=basic_count,
            quotes_count=quotes_count,
            extended_coverage=extended_coverage,
            latest_basic_update=latest_basic.get("updated_at") if latest_basic else None,
            latest_quotes_update=latest_quotes.get("updated_at") if latest_quotes else None,
            needs_initialization=needs_initialization
        )
        
        return ok(data=status,
            message="Database status obtained successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get database status: {str(e)}")


@router.get("/initialization-status", response_model=dict)
async def get_initialization_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get initialization status
    Check if there are any initialization tasks currently running
    """
    try:
        # Estimate completion time based on progress
        estimated_completion = None
        if (_initialization_status["is_running"]
            and _initialization_status["started_at"]
            and _initialization_status["progress"]):
            try:
                parts = _initialization_status["progress"].split("/")
                completed = int(parts[0])
                total = int(parts[1])
                if completed > 0 and total > 0:
                    elapsed = (datetime.utcnow() - _initialization_status["started_at"]).total_seconds()
                    estimated_total = elapsed / (completed / total)
                    remaining = estimated_total - elapsed
                    estimated_completion = (datetime.utcnow() + timedelta(seconds=remaining)).isoformat()
            except (ValueError, IndexError, ZeroDivisionError):
                pass

        status = InitializationStatusResponse(
            is_running=_initialization_status["is_running"],
            current_step=_initialization_status["current_step"],
            progress=_initialization_status["progress"],
            started_at=_initialization_status["started_at"],
            estimated_completion=estimated_completion
        )
        
        return ok(data=status,
            message="Initialization status obtained successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain initialization status: {str(e)}")


@router.post("/start-basic", response_model=dict)
async def start_basic_initialization(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start basic information initialization
    Only basic stock information is synchronized, suitable for quick initialization
    """
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="The initialization task is already running")
    
    try:
        # Start background task
        background_tasks.add_task(_run_basic_initialization)
        
        return ok(data={"message": "Basic information initialization has started"},
            message="The basic information initialization task has been started in the background"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize basic startup information: {str(e)}")


@router.post("/start-full", response_model=dict)
async def start_full_initialization(
    request: InitializationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start full data initialization
    Including complete synchronization of basic information, historical data, financial data, and market data
    """
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="The initialization task is already running")
    
    try:
        # Start background task
        background_tasks.add_task(
            _run_full_initialization,
            request.historical_days,
            not request.skip_if_exists or request.force_update
        )
        
        return ok(data={
                "message": "Full data initialization started",
                "historical_days": request.historical_days,
                "force_update": not request.skip_if_exists or request.force_update
            },
            message="The complete data initialization task has been started in the background"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Start full data initialization failed: {str(e)}")


@router.post("/stop", response_model=dict)
async def stop_initialization(
    current_user: dict = Depends(get_current_user)
):
    """
    Stop initialization task
    Try to cancel a running initialization task
    """
    if not _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="There are no initialization tasks running")
    
    try:
        # Try to cancel the task
        if _initialization_status["task"]:
            _initialization_status["task"].cancel()
        
        # reset state
        _initialization_status.update({
            "is_running": False,
            "current_step": None,
            "progress": None,
            "started_at": None,
            "task": None
        })
        
        return ok(data={"message": "The initialization task has stopped"},
            message="Initialization task stopped successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stop initialization task failed: {str(e)}")


async def _run_basic_initialization():
    """Run basic information initialization (background task)"""
    _initialization_status.update({
        "is_running": True,
        "current_step": "Basic information initialization",
        "progress": "0/1",
        "started_at": datetime.utcnow()
    })
    
    try:
        service = await get_tushare_init_service()
        result = await service.sync_service.sync_stock_basic_info(force_update=True)
        
        _initialization_status.update({
            "is_running": False,
            "current_step": "Complete",
            "progress": "1/1"
        })
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "current_step": f"failed: {str(e)}",
            "progress": "Error"
        })


async def _run_full_initialization(historical_days: int, force_update: bool):
    """Run full data initialization (background task)"""
    _initialization_status.update({
        "is_running": True,
        "current_step": "ready to initialize",
        "progress": "0/6",
        "started_at": datetime.utcnow()
    })
    
    try:
        service = await get_tushare_init_service()
        
        # Create a task to track progress
        async def progress_tracker():
            while _initialization_status["is_running"]:
                if hasattr(service, 'stats') and service.stats:
                    _initialization_status.update({
                        "current_step": service.stats.current_step,
                        "progress": f"{service.stats.completed_steps}/{service.stats.total_steps}"
                    })
                await asyncio.sleep(1)
        
        # Start progress tracking
        tracker_task = asyncio.create_task(progress_tracker())
        _initialization_status["task"] = tracker_task
        
        # Run initialization
        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force_update
        )
        
        # Stop progress tracking
        tracker_task.cancel()
        
        _initialization_status.update({
            "is_running": False,
            "current_step": "Complete" if result["success"] else "partially completed",
            "progress": result["progress"],
            "task": None
        })
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "current_step": f"failed: {str(e)}",
            "progress": "Error",
            "task": None
        })
