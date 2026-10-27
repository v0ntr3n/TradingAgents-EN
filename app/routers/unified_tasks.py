"""
unified mission center API

Provides a unified task query interface to support all types of analysis tasks
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
import logging

from app.models.analysis import AnalysisTaskType, AnalysisStatus
from app.models.user import PyObjectId
from app.services.task_analysis_service import get_task_analysis_service
from app.routers.auth_db import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tasks", tags=["unified-task-center"])


# ==================== response model ====================

class TaskListItem(BaseModel):
    """task list item"""
    task_id: str
    task_type: str
    status: str
    progress: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    execution_time: float = 0.0
    error_message: Optional[str] = None
    
    # Task parameters (for display)
    symbol: Optional[str] = None
    code: Optional[str] = None
    market: Optional[str] = None


class TaskStatistics(BaseModel):
    """Task statistics"""
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    cancelled: int


# ==================== API endpoint ====================

@router.get("/list", summary="Get task list")
async def get_task_list(
    task_type: Optional[AnalysisTaskType] = Query(None, description="Task type filter"),
    status: Optional[AnalysisStatus] = Query(None, description="Status filtering"),
    symbol: Optional[str] = Query(None, description="Stock code filtering (matches symbol/code/stock_code in task_params)"),
    limit: Optional[int] = Query(None, description="Return quantity (optional, if not set, all will be returned)"),
    skip: int = Query(0, ge=0, description="skip quantity"),
    user: dict = Depends(get_current_user)
):
    """Get the user s task list

    Supports filtering by task type and status

    Note: If limit is not specified, all records will be returned and paging will be handled by the front end.
    """
    try:
        logger.info(f"🎯 [unified mission center] Get task list request")
        logger.info(f"👤 User information: {user}")
        logger.info(f"📊 query parameters: task_type={task_type}, status={status}, limit={limit}, skip={skip}")

        user_id = PyObjectId(user["id"])
        logger.info(f"🔄 converted user_id: {user_id} (Type: {type(user_id)})")

        service = get_task_analysis_service()

        # If limit is not specified, all records are returned
        actual_limit = limit if limit is not None else 999999

        tasks = await service.list_user_tasks(
            user_id=user_id,
            task_type=task_type,
            status=status,
            symbol=symbol,
            limit=actual_limit,
            skip=skip
        )
        
        # Convert to list item format
        items = []
        for task in tasks:
            # Extract display information from task parameters
            symbol = task.task_params.get("symbol")
            code = task.task_params.get("code")
            market = task.task_params.get("market") or task.task_params.get("market_type")
            
            items.append(TaskListItem(
                task_id=task.task_id,
                task_type=task.task_type,
                status=task.status,
                progress=task.progress,
                created_at=task.created_at.isoformat(),
                started_at=task.started_at.isoformat() if task.started_at else None,
                completed_at=task.completed_at.isoformat() if task.completed_at else None,
                execution_time=task.execution_time,
                error_message=task.error_message,
                symbol=symbol,
                code=code,
                market=market
            ))
        
        return {
            "success": True,
            "data": {
                "tasks": items,
                "total": len(items),
                "limit": limit,
                "skip": skip
            },
            "message": "ok"
        }
        
    except Exception as e:
        logger.error(f"Failed to get task list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task list: {str(e)}")


@router.get("/statistics", summary="Get task statistics")
async def get_task_statistics(
    user: dict = Depends(get_current_user)
):
    """Get user s task statistics"""
    try:
        logger.info(f"🎯 [unified mission center] Get task statistics request")
        logger.info(f"👤 User information: {user}")

        user_id = PyObjectId(user["id"])
        logger.info(f"🔄 converted user_id: {user_id} (Type: {type(user_id)})")

        service = get_task_analysis_service()

        stats = await service.get_task_statistics(user_id)
        logger.info(f"📊 Statistical results: {stats}")
        
        return {
            "success": True,
            "data": TaskStatistics(**stats),
            "message": "ok"
        }
        
    except Exception as e:
        logger.error(f"Failed to obtain task statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain task statistics: {str(e)}")


@router.get("/{task_id}", summary="Get task details")
async def get_task_detail(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Get task details"""
    try:
        user_id = PyObjectId(user["id"])
        service = get_task_analysis_service()

        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        # Verify permissions
        if task.user_id != user_id:
            raise HTTPException(status_code=403, detail="Don t have permission to access this task")
        
        return {
            "success": True,
            "data": task.model_dump(),
            "message": "ok"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task details: {str(e)}")


@router.delete("/{task_id}", summary="Cancel task")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Cancel task"""
    try:
        user_id = PyObjectId(user["id"])
        service = get_task_analysis_service()

        # Verify task existence and permissions
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        if task.user_id != user_id:
            raise HTTPException(status_code=403, detail="Don t have permission to access this task")

        # Cancel task
        success = await service.cancel_task(task_id)

        if success:
            return {
                "success": True,
                "message": "Task canceled"
            }
        else:
            return {
                "success": False,
                "message": "Task cannot be canceled (may have completed or failed)"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@router.post("/{task_id}/resume", summary="Resume a suspended task")
async def resume_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Resume a suspended task and re-enqueue the task"""
    try:
        user_id = PyObjectId(user["id"])
        service = get_task_analysis_service()

        # Verify task existence and permissions
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        if task.user_id != user_id:
            raise HTTPException(status_code=403, detail="Don t have permission to access this task")

        # Check task status
        if task.status != AnalysisStatus.SUSPENDED:
            raise HTTPException(status_code=400, detail=f"Only tasks in suspended state can be resumed, the current state: {task.status}")

        # recovery task
        success = await service.resume_task(task_id)

        if success:
            return {
                "success": True,
                "message": "Task has been resumed and is being requeued..."
            }
        else:
            return {
                "success": False,
                "message": "Recovery task failed"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Recovery task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Recovery task failed: {str(e)}")


# ==================== General research task-specific queries ====================

@router.get("/general/list", summary="Get a list of general research tasks")
async def get_general_task_list(
    workflow_id: Optional[str] = Query(None, description="Filter by workflow ID"),
    date_start: Optional[str] = Query(None, description="start date (YYYY-MM-DD)"),
    date_end: Optional[str] = Query(None, description="end date (YYYY-MM-DD)"),
    keyword: Optional[str] = Query(None, description="Keyword search (match analysis target)"),
    status: Optional[AnalysisStatus] = Query(None, description="Status filtering"),
    limit: int = Query(50, ge=1, le=500, description="Return quantity"),
    skip: int = Query(0, ge=0, description="skip quantity"),
    user: dict = Depends(get_current_user)
):
    """Get a list of general research tasks

    Special inquiry task_params.task_category == "general" task,
    Supports filtering by workflow, time range, and keywords.
    """
    try:
        from datetime import datetime, timedelta
        from app.core.database import get_mongo_db
        from bson import ObjectId

        user_id = user["id"]
        # user_id May be a string or ObjectId, processed uniformly
        try:
            user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        except Exception:
            user_oid = user_id

        # Build query conditions
        query = {
            "user_id": user_oid,
            "task_params.task_category": "general",
        }

        # Filter by workflow
        if workflow_id:
            query["workflow_id"] = workflow_id

        # Filter by status
        if status:
            query["status"] = status

        # Filter by time range
        if date_start or date_end:
            time_query = {}
            if date_start:
                try:
                    start_dt = datetime.strptime(date_start, "%Y-%m-%d")
                    time_query["$gte"] = start_dt
                except ValueError:
                    raise HTTPException(status_code=400, detail="date_start The format should be YYYY-MM-DD")
            if date_end:
                try:
                    end_dt = datetime.strptime(date_end, "%Y-%m-%d") + timedelta(days=1)
                    time_query["$lt"] = end_dt
                except ValueError:
                    raise HTTPException(status_code=400, detail="date_end The format should be YYYY-MM-DD")
            if time_query:
                query["created_at"] = time_query

        # Keyword search (match task_params.symbol/stock_code)
        if keyword and keyword.strip():
            kw = keyword.strip()
            # Use regular matching to analyze targets
            query["$or"] = [
                {"task_params.symbol": {"$regex": kw, "$options": "i"}},
                {"task_params.stock_code": {"$regex": kw, "$options": "i"}},
            ]

        logger.info(f"🎯 [General Research Task List] Query conditions: {query}")

        db = get_mongo_db()
        cursor = db.unified_analysis_tasks.find(query).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        total = await db.unified_analysis_tasks.count_documents(query)

        # Build response
        items = []
        for doc in docs:
            task_params = doc.get("task_params", {}) or {}
            items.append({
                "task_id": doc.get("task_id", ""),
                "task_type": doc.get("task_type", ""),
                "status": doc.get("status", ""),
                "progress": doc.get("progress", 0),
                "workflow_id": doc.get("workflow_id"),
                "analysis_target": task_params.get("symbol") or task_params.get("stock_code") or "",
                "research_depth": task_params.get("research_depth"),
                "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                "started_at": doc.get("started_at").isoformat() if doc.get("started_at") else None,
                "completed_at": doc.get("completed_at").isoformat() if doc.get("completed_at") else None,
                "execution_time": doc.get("execution_time", 0),
                "error_message": doc.get("error_message"),
                "current_step": doc.get("current_step"),
            })

        return {
            "success": True,
            "data": {
                "tasks": items,
                "total": total,
                "limit": limit,
                "skip": skip
            },
            "message": "ok"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get general research task list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get general research task list: {str(e)}")


@router.get("/general/statistics", summary="Get general research task statistics")
async def get_general_task_statistics(
    user: dict = Depends(get_current_user)
):
    """Get statistics for common research tasks"""
    try:
        from app.core.database import get_mongo_db
        from bson import ObjectId

        user_id = user["id"]
        try:
            user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        except Exception:
            user_oid = user_id

        query = {
            "user_id": user_oid,
            "task_params.task_category": "general",
        }

        db = get_mongo_db()
        total = await db.unified_analysis_tasks.count_documents(query)
        completed = await db.unified_analysis_tasks.count_documents({**query, "status": "completed"})
        failed = await db.unified_analysis_tasks.count_documents({**query, "status": "failed"})
        processing = await db.unified_analysis_tasks.count_documents({**query, "status": "processing"})
        pending = await db.unified_analysis_tasks.count_documents({**query, "status": "pending"})

        return {
            "success": True,
            "data": {
                "total": total,
                "completed": completed,
                "failed": failed,
                "processing": processing,
                "pending": pending,
            },
            "message": "ok"
        }

    except Exception as e:
        logger.error(f"Failed to obtain general research task statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to obtain general research task statistics: {str(e)}")

