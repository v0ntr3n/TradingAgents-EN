#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scheduled task management routing
Provides functions such as query, pause, resume, and manual triggering of scheduled tasks
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.routers.auth_db import get_current_user
from app.services.scheduler_service import get_scheduler_service, SchedulerService
from app.core.response import ok
from tradingagents.utils.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


SCHEDULER_STOPPING_STATUSES = {"cancelling", "cancelled", "failed", "success", "suspended"}


def _serialize_scheduler_time(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_execution_progress_data(job_id: str, execution: Dict[str, Any]) -> Dict[str, Any]:
    started_at = execution.get("timestamp") or execution.get("scheduled_time")
    status = execution.get("status", "unknown")
    if status == "running" and execution.get("cancel_requested"):
        status = "cancelling"

    message = execution.get("progress_message")
    if not message and status == "cancelling":
        message = "Task is being canceled..."
    if not message and status in {"cancelled", "failed"}:
        message = execution.get("error_message")

    return {
        "job_id": job_id,
        "execution_id": str(execution.get("_id")) if execution.get("_id") else None,
        "progress": execution.get("progress", 0),
        "status": status,
        "message": message,
        "current_item": execution.get("current_item"),
        "total_items": execution.get("total_items"),
        "processed_items": execution.get("processed_items"),
        "started_at": _serialize_scheduler_time(started_at),
        "updated_at": _serialize_scheduler_time(execution.get("updated_at", started_at)),
    }


def _should_prefer_execution_progress(
    redis_progress: Dict[str, Any],
    execution_progress: Optional[Dict[str, Any]],
) -> bool:
    if not execution_progress:
        return False

    execution_status = execution_progress.get("status")
    if execution_status not in SCHEDULER_STOPPING_STATUSES:
        return False

    redis_execution_id = redis_progress.get("execution_id")
    execution_id = execution_progress.get("execution_id")
    return not redis_execution_id or redis_execution_id == execution_id


def _update_scheduler_progress_cache(
    job_id: str,
    execution_id: str,
    status: str,
    message: str,
    progress: Optional[int] = None,
    processed_items: Optional[int] = None,
    total_items: Optional[int] = None,
) -> None:
    try:
        import json
        from app.core.database import get_redis_sync_client
        from app.core.redis_client import RedisKeys

        redis_sync = get_redis_sync_client()
        if not redis_sync:
            return

        progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
        status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)

        existing_progress: Dict[str, Any] = {}
        existing_progress_str = redis_sync.get(progress_key)
        if existing_progress_str:
            try:
                existing_progress = json.loads(existing_progress_str)
            except Exception:
                existing_progress = {}

        updated_at = datetime.utcnow().isoformat()
        progress_data = dict(existing_progress)
        progress_data.update({
            "job_id": job_id,
            "execution_id": execution_id,
            "status": status,
            "message": message,
            "updated_at": updated_at,
        })

        if progress is not None:
            progress_data["progress"] = progress
        if processed_items is not None:
            progress_data["processed_items"] = processed_items
        if total_items is not None:
            progress_data["total_items"] = total_items

        ttl_seconds = 3600 if status in {"cancelling", "cancelled"} else 86400
        redis_sync.setex(progress_key, ttl_seconds, json.dumps(progress_data, ensure_ascii=False, default=str))

        status_data = {
            "job_id": job_id,
            "status": status,
            "progress": progress_data.get("progress", 0),
            "updated_at": updated_at,
        }
        redis_sync.setex(status_key, ttl_seconds, json.dumps(status_data, ensure_ascii=False, default=str))
    except Exception as exc:
        logger.warning(f"⚠️ Failed to update task progress cache (job_id={job_id}, status={status}) : {exc}")


class JobTriggerRequest(BaseModel):
    """Manually trigger task requests"""
    job_id: str
    kwargs: Optional[Dict[str, Any]] = None


class JobUpdateRequest(BaseModel):
    """Update task request"""
    job_id: str
    enabled: Optional[bool] = None
    cron: Optional[str] = None


class JobMetadataUpdateRequest(BaseModel):
    """Update task metadata request"""
    display_name: Optional[str] = None
    description: Optional[str] = None


@router.get("/jobs")
async def list_jobs(
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get a list of all scheduled tasks
    
    Returns:
        Task list, including task ID, name, status, next execution time and other information
    """
    try:
        jobs = await service.list_jobs()
        return ok(data=jobs, message=f"Get {len(jobs)} scheduled tasks")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task list: {str(e)}")


@router.put("/jobs/{job_id}/metadata")
async def update_job_metadata_route(
    job_id: str,
    request: JobMetadataUpdateRequest,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Update task metadata (trigger name and comments)

    Args:
        job_id: Task ID
        request: update request

    Returns:
        Operation result
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can update task metadata")

    try:
        success = await service.update_job_metadata(
            job_id,
            display_name=request.display_name,
            description=request.description
        )
        if success:
            return ok(message=f"Task {job_id} Metadata updated")
        else:
            raise HTTPException(status_code=400, detail=f"update task {job_id} Metadata failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update task metadata: {str(e)}")


@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get task details

    Args:
        job_id: Task ID

    Returns:
        Task details
    """
    try:
        job = await service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Task {job_id} does not exist")
        return ok(data=job, message="Obtained task details successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task details: {str(e)}")


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Pause task
    
    Args:
        job_id: Task ID
        
    Returns:
        Operation result
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can pause tasks")
    
    try:
        success = await service.pause_job(job_id)
        if success:
            return ok(message=f"Task {job_id} Suspended")
        else:
            raise HTTPException(status_code=400, detail=f"Pause task {job_id} failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to suspend task: {str(e)}")


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    recovery task

    Args:
        job_id: Task ID

    Returns:
        Operation result
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can restore tasks")

    try:
        success = await service.resume_job(job_id)
        if success:
            return ok(message=f"Task {job_id} Restored")
        else:
            raise HTTPException(status_code=400, detail=f"recovery task {job_id} failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recovery task failed: {str(e)}")


class RescheduleRequest(BaseModel):
    """Modify task CRON expression request"""
    cron: str


@router.put("/jobs/{job_id}/schedule")
async def reschedule_job(
    job_id: str,
    request: RescheduleRequest,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Modify the CRON expression of the task

    Args:
        job_id: Task ID
        request: Request body containing new CRON expression

    Returns:
        Operation result
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can modify task schedules")

    try:
        success = await service.reschedule_job(job_id, request.cron)
        if success:
            return ok(message=f"Task {job_id} The schedule has been updated to: {request.cron}")
        else:
            raise HTTPException(status_code=400, detail=f"Modify task {job_id} Scheduling failed, please check CRON expression format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to modify task schedule: {str(e)}")


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service),
    force: bool = Query(False, description="Whether to enforce (skip transaction time checks, etc.)"),
    incremental: Optional[bool] = Query(None, description="Whether to incrementally synchronize (only historical data synchronization tasks are valid,None=Use default value)")
):
    """
    Manually trigger task execution

    Args:
        job_id: Task ID
        force: Whether to enforce execution (skip transaction time check, etc.), default False
        incremental: Whether to incrementally synchronize (only historical data synchronization tasks are valid),None=Use default value (increment),False=Full synchronization

    Returns:
        Operation result
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can trigger tasks manually")

    try:
        # Pass parameters for a specific task
        kwargs = {}
        if force and job_id in ["tushare_quotes_sync", "akshare_quotes_sync"]:
            kwargs["force"] = True
        
        # 🔥 The historical data synchronization task supports the incremental parameter
        if incremental is not None and job_id in ["tushare_historical_sync", "akshare_historical_sync"]:
            kwargs["incremental"] = incremental

        success = await service.trigger_job(job_id, kwargs=kwargs, force=force)
        if success:
            message = f"Task {job_id} Execution triggered"
            if force:
                message += " (forced mode)"
            if incremental is not None and job_id in ["tushare_historical_sync", "akshare_historical_sync"]:
                sync_mode = "Incremental synchronization" if incremental else "Full synchronization"
                message += f"（{sync_mode}）"
            return ok(message=message)
        else:
            raise HTTPException(status_code=400, detail=f"trigger task {job_id} failed")
    except HTTPException as e:
        # 🔥 If it is 409 Conflict (the task is running), return it directly to the front end
        if e.status_code == 409:
            raise
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger task: {str(e)}")


@router.get("/jobs/{job_id}/history")
async def get_job_history(
    job_id: str,
    limit: int = Query(20, ge=1, le=100, description="Return quantity limit"),
    offset: int = Query(0, ge=0, description="offset"),
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get task execution history
    
    Args:
        job_id: Task ID
        limit: Return quantity limit
        offset: offset
        
    Returns:
        Task execution history
    """
    try:
        history = await service.get_job_history(job_id, limit=limit, offset=offset)
        total = await service.count_job_history(job_id)
        
        return ok(
            data={
                "history": history,
                "total": total,
                "limit": limit,
                "offset": offset
            },
            message=f"Get {len(history)} execution records"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain execution history: {str(e)}")


@router.get("/history")
async def get_all_history(
    limit: int = Query(50, ge=1, le=200, description="Return quantity limit"),
    offset: int = Query(0, ge=0, description="offset"),
    job_id: Optional[str] = Query(None, description="Task ID filtering"),
    status: Optional[str] = Query(None, description="Status filtering: success/failed"),
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get all task execution history
    
    Args:
        limit: Return quantity limit
        offset: offset
        job_id: Task ID filtering
        status: Status filtering
        
    Returns:
        All task execution history
    """
    try:
        history = await service.get_all_history(
            limit=limit,
            offset=offset,
            job_id=job_id,
            status=status
        )
        total = await service.count_all_history(job_id=job_id, status=status)
        
        return ok(
            data={
                "history": history,
                "total": total,
                "limit": limit,
                "offset": offset
            },
            message=f"Get {len(history)} execution records"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain execution history: {str(e)}")


@router.get("/stats")
async def get_scheduler_stats(
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get scheduler statistics
    
    Returns:
        Scheduler statistics, including total number of tasks, number of running tasks, number of suspended tasks, etc.
    """
    try:
        stats = await service.get_stats()
        return ok(data=stats, message="Obtaining statistics successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain statistics: {str(e)}")


@router.get("/health")
async def scheduler_health_check(
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Scheduler health check

    Returns:
        Scheduler health status
    """
    try:
        health = await service.health_check()
        return ok(data=health, message="The scheduler is running normally")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/executions")
async def get_job_executions(
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service),
    job_id: Optional[str] = Query(None, description="Task ID filtering"),
    status: Optional[str] = Query(None, description="Status filtering (success/failed/missed/running)"),
    is_manual: Optional[bool] = Query(None, description="Whether to trigger manually (true=manual,false=automatic,None=all)"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity limit"),
    offset: int = Query(0, ge=0, description="offset")
):
    """
    Get task execution history

    Args:
        job_id: Task ID filtering (optional)
        status: Status filtering (optional)
        is_manual: Whether to trigger manually (optional)
        limit: Return quantity limit
        offset: offset

    Returns:
        Execution history list
    """
    try:
        executions = await service.get_job_executions(
            job_id=job_id,
            status=status,
            is_manual=is_manual,
            limit=limit,
            offset=offset
        )
        total = await service.count_job_executions(job_id=job_id, status=status, is_manual=is_manual)
        return ok(data={
            "items": executions,
            "total": total,
            "limit": limit,
            "offset": offset
        }, message=f"Get {len(executions)} execution records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain execution history: {str(e)}")


@router.get("/jobs/{job_id}/executions")
async def get_single_job_executions(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service),
    status: Optional[str] = Query(None, description="Status filtering (success/failed/missed/running)"),
    is_manual: Optional[bool] = Query(None, description="Whether to trigger manually (true=manual,false=automatic,None=all)"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity limit"),
    offset: int = Query(0, ge=0, description="offset")
):
    """
    Get the execution history of a specified task

    Args:
        job_id: Task ID
        status: Status filtering (optional)
        is_manual: Whether to trigger manually (optional)
        limit: Return quantity limit
        offset: offset

    Returns:
        Execution history list
    """
    try:
        executions = await service.get_job_executions(
            job_id=job_id,
            status=status,
            is_manual=is_manual,
            limit=limit,
            offset=offset
        )
        total = await service.count_job_executions(job_id=job_id, status=status, is_manual=is_manual)
        return ok(data={
            "items": executions,
            "total": total,
            "limit": limit,
            "offset": offset
        }, message=f"Get {len(executions)} execution records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain execution history: {str(e)}")


@router.get("/jobs/{job_id}/execution-stats")
async def get_job_execution_stats(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get task execution statistics

    Args:
        job_id: Task ID

    Returns:
        Statistics
    """
    try:
        stats = await service.get_job_execution_stats(job_id)
        return ok(data=stats, message="Obtaining statistics successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain statistics: {str(e)}")


@router.get("/suspended-executions")
async def get_suspended_executions(
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get all pending task execution records (tasks interrupted due to service restart)
    
    Returns:
        List of pending task execution records
    """
    try:
        db = service._get_db()
        
        # Find all pending tasks
        suspended_executions = await db.scheduler_executions.find({
            "status": "suspended"
        }).sort("timestamp", -1).to_list(length=100)
        
        # Convert to the format required by the front end
        executions = []
        for exec_record in suspended_executions:
            executions.append({
                "execution_id": str(exec_record["_id"]),
                "job_id": exec_record.get("job_id"),
                "job_name": exec_record.get("job_name", exec_record.get("job_id")),
                "status": exec_record.get("status"),
                "progress": exec_record.get("progress", 0),
                "message": exec_record.get("progress_message"),
                "current_item": exec_record.get("current_item"),
                "total_items": exec_record.get("total_items"),
                "processed_items": exec_record.get("processed_items"),
                "started_at": exec_record.get("timestamp").isoformat() if exec_record.get("timestamp") else None,
                "updated_at": exec_record.get("updated_at").isoformat() if exec_record.get("updated_at") else None,
                "error_message": exec_record.get("error_message")
            })
        
        return ok(data=executions, message=f"Get {len(executions)} pending tasks")
    except Exception as e:
        logger.error(f"❌ Failed to get pending tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pending tasks: {str(e)}")


@router.post("/executions/{execution_id}/cancel-suspended")
async def cancel_suspended_execution(
    execution_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Cancel the pending task execution record (used when the user chooses to restart)
    
    Note: This endpoint is specifically used to cancel suspended tasks.
    For running tasks, use /executions/{execution_id}/cancel endpoint
    
    Args:
        execution_id: Execution record ID (MongoDB _id)
    
    Returns:
        Operation result
    """
    try:
        db = service._get_db()
        from bson import ObjectId
        
        # Find pending execution records
        exec_record = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
        if not exec_record:
            raise HTTPException(status_code=404, detail="Execution record does not exist")
        
        if exec_record.get("status") != "suspended":
            raise HTTPException(status_code=400, detail=f"The task status is not pending, the current status: {exec_record.get('status')}")
        
        job_id = exec_record.get("job_id")
        
        # 🔥 Mark all pending records for this task as cancelled
        cancelled_result = await db.scheduler_executions.update_many(
            {"job_id": job_id, "status": "suspended"},
            {
                "$set": {
                    "status": "cancelled",
                    "error_message": "The user chose to restart and the pending task was canceled",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"✅ Canceled {cancelled_result.modified_count} pending tasks (user chooses to restart)")
        return ok(message=f"Canceled {cancelled_result.modified_count} pending tasks")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to cancel pending task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel pending task: {str(e)}")


@router.post("/executions/{execution_id}/resume")
async def resume_suspended_execution(
    execution_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Resume suspended task execution (continue execution from where it was last interrupted)
    
    Args:
        execution_id: Execution record ID (MongoDB _id)
    
    Returns:
        Operation result
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can resume suspended tasks")
    
    try:
        db = service._get_db()
        from bson import ObjectId
        
        # Find pending execution records
        exec_record = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
        if not exec_record:
            raise HTTPException(status_code=404, detail="Execution record does not exist")
        
        if exec_record.get("status") != "suspended":
            raise HTTPException(status_code=400, detail=f"The task status is not pending, the current status: {exec_record.get('status')}")
        
        job_id = exec_record.get("job_id")
        if not job_id:
            raise HTTPException(status_code=400, detail="There is no task in the execution record ID")
        
        # 🔥 Find all pending records of this task (sorted by timestamp in reverse order)
        all_suspended = await db.scheduler_executions.find({
            "job_id": job_id,
            "status": "suspended"
        }).sort("timestamp", -1).to_list(length=100)
        
        if not all_suspended:
            raise HTTPException(status_code=404, detail="Pending execution record not found")
        
        # 🔥 Make sure the current record to be restored is the latest (the first one)
        latest_suspended_id = str(all_suspended[0]["_id"])
        if latest_suspended_id != execution_id:
            logger.warning(f"⚠️ The user is trying to restore a pending record that is not the latest: Request={execution_id}, Latest={latest_suspended_id}")
            # Continue execution using the latest record
            execution_id = latest_suspended_id
            exec_record = all_suspended[0]
        
        # 🔥 Detailed log: record progress information of pending recording
        logger.info(f"📊 Task {job_id} share {len(all_suspended)} pending records, the latest record will be restored {execution_id}")
        logger.info(f"📋 Pending record details:")
        logger.info(f"   - execution_id: {execution_id}")
        logger.info(f"   - progress: {exec_record.get('progress', 0)}%")
        logger.info(f"   - processed_items: {exec_record.get('processed_items')}")
        logger.info(f"   - total_items: {exec_record.get('total_items')}")
        logger.info(f"   - current_item: {exec_record.get('current_item')}")
        logger.info(f"   - job_kwargs: {exec_record.get('job_kwargs', {})}")
        
        # 🔥 Mark all pending records except the latest record as canceled (to avoid data pollution)
        if len(all_suspended) > 1:
            other_suspended_ids = [ObjectId(str(e["_id"])) for e in all_suspended[1:]]  # all records except the first
            cancelled_result = await db.scheduler_executions.update_many(
                {"_id": {"$in": other_suspended_ids}},
                {
                    "$set": {
                        "status": "cancelled",
                        "error_message": "Execution resumed with updated pending record, canceled to avoid data contamination",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info(f"✅ Canceled {cancelled_result.modified_count} Keep old pending records to avoid data pollution")
        
        # 🔥 Read the task's kwargs (including incremental parameters) from the execution record
        resume_kwargs = exec_record.get("job_kwargs", {})
        if resume_kwargs:
            logger.info(f"📋 recovery task {job_id}, Use saved parameters: {resume_kwargs}")
        else:
            logger.warning(f"⚠️ There are no kwargs saved in the execution record, using default parameters")
        
        # 🔥 Save progress information to kwargs for use by task functions
        processed_items = exec_record.get("processed_items")
        if processed_items is not None:
            resume_kwargs["_resume_from_index"] = processed_items  # Mark where to continue from
            logger.info(f"🔄 will be from {processed_items} Position continues execution (processed {processed_items}/{exec_record.get('total_items', '?')}) ")
        else:
            logger.warning(f"⚠️ There is no processed_items in the execution record and execution will start from 0")
        
        # 🔥 First update the execution record status to running, and save the execution_id to kwargs.
        # In this way, trigger_job can recognize that this is a recovery operation and reuse this execution record instead of creating a new one.
        resume_kwargs["_resume_execution_id"] = execution_id  # Mark this as a recovery operation
        
        # 🔥 First update the execution record status to running (update before triggering the task to ensure that the status has been updated during front-end query)
        # This way the front end calls loadTasks(), records in the suspended state will no longer be queried.
        # 🔥 At the same time, the cancellation mark is cleared because the user actively resumes the task and indicates that he wants to continue execution.
        # 🔥 Clears the cancellation mark of the current execution record and all related execution records (including subtasks)
        update_result = await db.scheduler_executions.update_one(
            {"_id": ObjectId(execution_id)},
            {
                "$set": {
                    "status": "running",
                    "cancel_requested": False,  # 🔥 Clear the cancellation mark and the user actively resumes the task
                    "updated_at": datetime.utcnow(),
                    "resumed_at": datetime.utcnow()  # Record recovery time
                }
            }
        )
        
        # 🔥 Also clears the cancellation marks of all related execution records (including subtasks)
        # For example: If you restore tushare_financial_sync, also clear the cancellation flags of tushare_financial_sync_tushare, etc.
        related_update_result = await db.scheduler_executions.update_many(
            {
                "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                "status": {"$in": ["running", "suspended"]}
            },
            {
                "$set": {
                    "cancel_requested": False,  # 🔥 Clear the cancellation flags of all related execution records
                    "updated_at": datetime.utcnow()
                }
            }
        )
        if related_update_result.modified_count > 0:
            logger.info(f"✅ Also cleared {related_update_result.modified_count} Cancellation mark for related execution records "
                      f"(job_id match: ^{job_id}(_|$))")
        logger.info(f"✅ pending tasks {execution_id} The status has been updated to running and is ready to resume execution. (matched={update_result.matched_count}, modified={update_result.modified_count})")
        
        # 🔥 Verify the update was successful
        if update_result.matched_count == 0:
            logger.error(f"❌ Execution record {execution_id} Does not exist and cannot be restored")
            raise HTTPException(status_code=404, detail="Execution record does not exist")
        
        # 🔥 Confirm again that the status has been updated
        verify_record = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
        if verify_record and verify_record.get("status") != "running":
            logger.error(f"❌ Execution record {execution_id} Status update failed, current status: {verify_record.get('status')}")
            raise HTTPException(status_code=500, detail=f"Status update failed, current status: {verify_record.get('status')}")
        logger.info(f"✅ Verified execution record {execution_id} Status has been successfully updated to running")
        
        # Trigger the task to continue execution (manually trigger, pass the saved parameters and execution_id, the task will reuse this execution record)
        success = await service.trigger_job(job_id, kwargs=resume_kwargs)
        
        if success:
            # 🔥 Make sure the status is still running (the status may be updated internally in trigger_job)
            final_update_result = await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "running",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info(f"✅ Confirm the status again after successful recovery: execution_id={execution_id}, matched={final_update_result.matched_count}, modified={final_update_result.modified_count}")
            
            # 🔥 Final verification: Make sure the status is indeed running
            final_verify = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if final_verify:
                final_status = final_verify.get("status")
                logger.info(f"📊 final status verification: execution_id={execution_id}, status={final_status}")
                if final_status != "running":
                    logger.warning(f"⚠️ Execution record {execution_id} The final state is not running, but: {final_status}")
            else:
                logger.error(f"❌ Execution record {execution_id} does not exist at the time of final verification")
            
            return ok(message=f"Task {job_id} Execution has resumed and will continue from the last progress position")
        else:
            # If the trigger fails, the recovery status is suspended
            await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "suspended",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            raise HTTPException(status_code=400, detail=f"trigger task {job_id} failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to resume suspended task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume suspended task: {str(e)}")


@router.get("/jobs/{job_id}/progress")
async def get_job_progress(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get the real-time progress of the task (read from Redis cache, or MongoDB if Redis is not available)

    Args:
        job_id: Task ID

    Returns:
        Task progress information, including progress percentage, current item, total number of items, etc.
    """
    try:
        import json
        from app.core.redis_client import RedisKeys
        latest_execution = await service.get_latest_execution(job_id)
        latest_execution_progress = (
            _build_execution_progress_data(job_id, latest_execution)
            if latest_execution else None
        )
        
        # 🔥 Try to read real-time progress from Redis, fallback to if Redis is not available MongoDB
        try:
            from app.core.database import get_redis_client  # Use the unified Redis client of the system
            redis_client = get_redis_client()
            
            # 🔥 First check whether there are new execution records in MongoDB (manually triggered, and the timestamp is very new, within 30 seconds)
            # If there is a new execution record, the new execution record will be returned first instead of the old Redis cache.
            recent_execution = latest_execution
            if recent_execution:
                execution_time = recent_execution.get("timestamp") or recent_execution.get("scheduled_time")
                if execution_time:
                    # 🔥 Check whether the execution record is very recent (within 30 seconds) and is triggered manually
                    # Need to handle cases where execution_time may be a datetime object or a string
                    try:
                        execution_time_dt = None
                        if isinstance(execution_time, datetime):
                            execution_time_dt = execution_time
                        elif isinstance(execution_time, str):
                            # If it's a string, try parsing as datetime
                            try:
                                # Try using datetime.fromisoformat(Python 3.7+) 
                                execution_time_dt = datetime.fromisoformat(execution_time.replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                # If that fails, try using strptime
                                try:
                                    execution_time_dt = datetime.strptime(execution_time, '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    # If all else fails, try using dateutil if available
                                    try:
                                        from dateutil import parser
                                        execution_time_dt = parser.parse(execution_time)
                                    except (ImportError, ValueError):
                                        logger.debug(f"⚠️ Unable to parse execution_time string: {execution_time}")
                        
                        if execution_time_dt:
                            # Calculate time difference
                            now = datetime.now(execution_time_dt.tzinfo) if execution_time_dt.tzinfo else datetime.now()
                            if execution_time_dt.tzinfo:
                                time_diff = now - execution_time_dt
                            else:
                                time_diff = datetime.now() - execution_time_dt.replace(tzinfo=None)
                            
                            is_recent = time_diff.total_seconds() < 30
                            is_manual = recent_execution.get("is_manual", False)
                            
                            # 🔥 If it is a new manually triggered task (within 30 seconds), the new records in MongoDB will be returned first instead of the old Redis cache.
                            if is_recent and is_manual:
                                logger.info(f"🔍 [Progress query] When a new manually triggered task is detected (within 30 seconds), MongoDB records will be returned first: job_id={job_id}, execution_id={recent_execution.get('_id')}")
                                # Skip Redis cache and return new records directly in MongoDB
                                progress_data = _build_execution_progress_data(job_id, recent_execution)
                                logger.info(f"🔍 [Progress query] Read new task progress from MongoDB: job_id={job_id}, execution_id={progress_data.get('execution_id')}, progress={progress_data.get('progress')}, status={progress_data.get('status')}")
                                return ok(data=progress_data, message="Get progress successfully (new task, from database)")
                    except Exception as time_check_error:
                        # Time check failed, continue to use Redis cache
                        logger.debug(f"⚠️ Checking execution record time failed (continue using Redis cache): {time_check_error}")
            
            # Prioritize reading real-time progress from Redis
            progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
            progress_data_str = await redis_client.get(progress_key)
            
            if progress_data_str:
                progress_data = json.loads(progress_data_str)
                if _should_prefer_execution_progress(progress_data, latest_execution_progress):
                    logger.info(
                        f"🔍 [Progress query] Redis state lag detected, use MongoDB state instead: "
                        f"job_id={job_id}, execution_id={latest_execution_progress.get('execution_id')}, "
                        f"redis_status={progress_data.get('status')}, mongo_status={latest_execution_progress.get('status')}"
                    )
                    return ok(data=latest_execution_progress, message="Obtain progress successfully (subject to database status)")
                # 🔥 If there is no execution_id in Redis, try to get the latest execution record from MongoDB
                if not progress_data.get("execution_id") and latest_execution_progress:
                    progress_data["execution_id"] = latest_execution_progress.get("execution_id")
                logger.info(f"🔍 [Progress query] Read progress from Redis: job_id={job_id}, execution_id={progress_data.get('execution_id')}, progress={progress_data.get('progress')}, status={progress_data.get('status')}")
                return ok(data=progress_data, message="Get real-time progress successfully")
            else:
                logger.info(f"🔍 [Progress query] Redis No progress data found in: job_id={job_id}, key={progress_key}")
        except RuntimeError as redis_error:
            # Redis Uninitialized, logs but continues reading from MongoDB
            logger.debug(f"⚠️ Redis Unavailable, reading progress from MongoDB: {redis_error}")
        except Exception as redis_error:
            # Other Redis errors, logs but continues reading from MongoDB
            logger.warning(f"⚠️ Redis Read failed, read progress from MongoDB: {redis_error}")
        
        # If there is none in Redis or Redis is not available, read the latest execution record from MongoDB
        execution = latest_execution
        if execution:
            progress_data = _build_execution_progress_data(job_id, execution)
            logger.info(f"🔍 [Progress query] Read progress from MongoDB: job_id={job_id}, execution_id={progress_data.get('execution_id')}, progress={progress_data.get('progress')}, status={progress_data.get('status')}")
            return ok(data=progress_data, message="Get progress successfully (from database)")
        else:
            logger.warning(f"🔍 [Progress query] MongoDB No execution records were found in: job_id={job_id}")
        
        return ok(data={
            "job_id": job_id,
            "progress": 0,
            "status": "unknown",
            "message": "No progress information yet"
        }, message="No progress information yet")
        
    except Exception as e:
        logger.error(f"❌ Failed to get task progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task progress: {str(e)}")


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Cancel/terminate task execution (unified entrance, automatically processed according to task status)

    For the task being executed (running), set the cancellation flag (cancel_requested=True) ; 
    For suspended tasks (suspended), they are marked as canceled;
    For failed tasks (failed), mark them as canceled (the user explicitly terminates the failed task);
    For other completed tasks (success), mark them as canceled (the user explicitly terminates the completed task)

    Args:
        execution_id: Execution record ID (MongoDB _id)

    Returns:
        Operation result
    """
    try:
        db = service._get_db()
        from bson import ObjectId
        
        # Find execution records
        exec_record = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
        if not exec_record:
            raise HTTPException(status_code=404, detail="Execution record does not exist")
        
        status = exec_record.get("status")
        job_id = exec_record.get("job_id")
        
        # 🔥 Perform different operations based on task status
        if status == "running":
            # Task in progress: Set cancellation flag
            logger.info(f"🛑 User requests to terminate task: execution_id={execution_id}, job_id={job_id}, status={status}")
            success = await service.cancel_job_execution(execution_id)
            if success:
                logger.info(f"✅ Terminate task successfully: execution_id={execution_id}")
                return ok(message="Cancellation flag set, task will be stopped on next check")
            else:
                logger.error(f"❌ Failed to terminate task: execution_id={execution_id}")
                raise HTTPException(status_code=400, detail="Failed to cancel task")
        elif status == "suspended":
            # Pending tasks: marked as cancelled
            cancelled_result = await db.scheduler_executions.update_many(
                {"job_id": job_id, "status": "suspended"},
                {
                    "$set": {
                        "status": "cancelled",
                        "error_message": "The user chose to restart and the pending task was canceled",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            _update_scheduler_progress_cache(
                job_id=job_id,
                execution_id=execution_id,
                status="cancelled",
                message="The task has been canceled (original status: suspended) ",
                progress=exec_record.get("progress"),
                processed_items=exec_record.get("processed_items"),
                total_items=exec_record.get("total_items"),
            )
            logger.info(f"✅ Canceled {cancelled_result.modified_count} pending tasks")
            return ok(message=f"Canceled {cancelled_result.modified_count} pending tasks")
        elif status == "failed":
            # 🔥 Failed tasks: marked as canceled (the user explicitly terminates the failed task)
            cancelled_result = await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "cancelled",
                        "error_message": "The user has terminated this failed task",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            _update_scheduler_progress_cache(
                job_id=job_id,
                execution_id=execution_id,
                status="cancelled",
                message="The user has terminated this failed task",
                progress=exec_record.get("progress"),
                processed_items=exec_record.get("processed_items"),
                total_items=exec_record.get("total_items"),
            )
            logger.info(f"✅ Failed task terminated: execution_id={execution_id}, job_id={job_id}")
            return ok(message="Failed task terminated")
        elif status == "success":
            # 🔥 Completed tasks: Marked as canceled (the user explicitly terminated the completed task)
            cancelled_result = await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "cancelled",
                        "error_message": "The user has terminated this completed task",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            _update_scheduler_progress_cache(
                job_id=job_id,
                execution_id=execution_id,
                status="cancelled",
                message="The user has terminated this completed task",
                progress=exec_record.get("progress"),
                processed_items=exec_record.get("processed_items"),
                total_items=exec_record.get("total_items"),
            )
            logger.info(f"✅ Completed task terminated: execution_id={execution_id}, job_id={job_id}")
            return ok(message="Completed task terminated")
        elif status == "cancelled":
            # It is already in the canceled state and will directly return success.
            _update_scheduler_progress_cache(
                job_id=job_id,
                execution_id=execution_id,
                status="cancelled",
                message=exec_record.get("error_message") or "The task is already canceled",
                progress=exec_record.get("progress"),
                processed_items=exec_record.get("processed_items"),
                total_items=exec_record.get("total_items"),
            )
            logger.info(f"ℹ️ The task is already canceled: execution_id={execution_id}, job_id={job_id}")
            return ok(message="The task is already canceled")
        else:
            # 🔥 Other unknown states: Termination is also allowed, marked as cancelled
            cancelled_result = await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "cancelled",
                        "error_message": f"The user has terminated this task (original status: {status}) ",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            _update_scheduler_progress_cache(
                job_id=job_id,
                execution_id=execution_id,
                status="cancelled",
                message=f"Task terminated (original status: {status}) ",
                progress=exec_record.get("progress"),
                processed_items=exec_record.get("processed_items"),
                total_items=exec_record.get("total_items"),
            )
            logger.info(f"✅ Task terminated (original status: {status}) : execution_id={execution_id}, job_id={job_id}")
            return ok(message=f"Task terminated (original status: {status}) ")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to cancel task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@router.post("/executions/{execution_id}/mark-failed")
async def mark_execution_failed(
    execution_id: str,
    reason: str = Query("User manually marks as failed", description="Reason for failure"),
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Mark execution records as failed

    Used to handle tasks that have exited but are still running in the database

    Args:
        execution_id: Execution record ID (MongoDB _id)
        reason: Reason for failure

    Returns:
        Operation result
    """
    try:
        success = await service.mark_execution_as_failed(execution_id, reason)
        if success:
            return ok(message="Marked as failed")
        else:
            raise HTTPException(status_code=400, detail="Marking failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Marking failed: {str(e)}")


@router.delete("/executions/{execution_id}")
async def delete_execution(
    execution_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Delete execution record

    Args:
        execution_id: Execution record ID (MongoDB _id)

    Returns:
        Operation result
    """
    try:
        success = await service.delete_execution(execution_id)
        if success:
            return ok(message="Execution record deleted")
        else:
            raise HTTPException(status_code=400, detail="Delete failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete execution record: {str(e)}")


@router.post("/executions/{execution_id}/retry-failed")
async def retry_failed_symbols(
    execution_id: str,
    user: dict = Depends(get_current_user),
    service: SchedulerService = Depends(get_scheduler_service),
    start_date: Optional[str] = Query(None, description="Start date (optional, the date of the original task is used by default)"),
    end_date: Optional[str] = Query(None, description="End date (optional, the date of the original task is used by default)"),
    period: Optional[str] = Query("daily", description="Data period (daily/weekly/monthly), default daily")
):
    """
    Retry failed stocks (retry only retryable errors, skip errors with no data)
    
    Suitable for historical data synchronization tasks (Tushare/AKShare)
    
    Args:
        execution_id: Execution record ID (MongoDB _id)
        start_date: Start date (optional, the date of the original task is used by default)
        end_date: End date (optional, the date of the original task is used by default)
        period: Data period (daily/weekly/monthly), default daily
        
    Returns:
        Retry result statistics
    """
    # Check admin rights
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Only administrators can retry failed stocks")
    
    try:
        from bson import ObjectId
        from app.worker.tushare_sync_service import get_tushare_sync_service
        
        db = service._get_db()
        
        # Find execution records
        exec_record = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
        if not exec_record:
            raise HTTPException(status_code=404, detail="Execution record does not exist")
        
        job_id = exec_record.get("job_id")
        if not job_id:
            raise HTTPException(status_code=400, detail="There is no task in the execution record ID")
        
        # 🔥 Check the task type. Only historical data synchronization tasks are supported.
        supported_jobs = ["tushare_historical_sync", "akshare_historical_sync", "baostock_historical_sync", "qmt_basic_info_sync", "qmt_historical_sync"]
        if job_id not in supported_jobs:
            raise HTTPException(
                status_code=400, 
                detail=f"This task type does not support retry failure items, only: {', '.join(supported_jobs)}"
            )
        
        # 🔥 Get error list from execution record
        # Error information may be stored in multiple places:
        # 1. execution The errors field of the record (if saved when the task was completed)
        # 2. Extracted from stats (if the task has statistics)
        
        errors = exec_record.get("errors", [])
        
        # If errors are not stored directly, try to extract them from other fields
        if not errors:
            # Try to extract the error message from progress_message or other fields
            # This may need to be adjusted according to the actual data structure
            logger.warning(f"⚠️ Execution record {execution_id} Error list not found, cannot retry")
            raise HTTPException(
                status_code=400, 
                detail="There is no error message in the execution record and retry cannot be performed. Please ensure that the task is completed and error messages are logged."
            )
        
        # 🔥 Obtain the corresponding synchronization service instance according to the task type
        if job_id == "tushare_historical_sync":
            from app.worker.tushare_sync_service import get_tushare_sync_service
            sync_service = await get_tushare_sync_service()
        elif job_id == "akshare_historical_sync":
            from app.worker.akshare_sync_service import get_akshare_sync_service
            sync_service = await get_akshare_sync_service()
        elif job_id == "baostock_historical_sync":
            from app.worker.baostock_sync_service import get_baostock_sync_service
            sync_service = await get_baostock_sync_service()
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported task type: {job_id}")
        
        # 🔥 If no date is provided, try to get it from the execution record
        if not start_date:
            # Can be obtained from job_kwargs or other fields
            job_kwargs = exec_record.get("job_kwargs", {})
            start_date = job_kwargs.get("start_date")
        
        if not end_date:
            job_kwargs = exec_record.get("job_kwargs", {})
            end_date = job_kwargs.get("end_date")
        
        # 🔥 Call the retry method (different services may have different interfaces)
        if job_id == "baostock_historical_sync":
            # BaoStock Using the days parameter, you need to calculate the number of days
            if start_date and end_date:
                from datetime import datetime as dt
                start_dt = dt.strptime(start_date, '%Y-%m-%d')
                end_dt = dt.strptime(end_date, '%Y-%m-%d')
                days = (end_dt - start_dt).days
            else:
                days = 30  # Default 30 days
            
            retry_result = await sync_service.retry_failed_symbols(
                errors=errors,
                days=days,
                period=period,
                job_id=f"{job_id}_retry_{execution_id}"
            )
        else:
            # Tushare Use with AKShare start_date/end_date
            retry_result = await sync_service.retry_failed_symbols(
                errors=errors,
                start_date=start_date,
                end_date=end_date,
                period=period,
                job_id=f"{job_id}_retry_{execution_id}"  # Use new job_id to avoid conflicts
            )
        
        return ok(
            data=retry_result,
            message=f"Retry complete: success {retry_result.get('success_count', 0)}/{retry_result.get('total_retried', 0)}, "
                   f"failed {retry_result.get('error_count', 0)}, "
                   f"No data {retry_result.get('no_data_count', 0)} (skipped)"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Retry failed stock failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retry failed stock failed: {str(e)}")
