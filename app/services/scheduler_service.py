#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scheduled task management service
Provides functions such as query, pause, resume, and manual triggering of scheduled tasks
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent
)

from app.core.database import get_mongo_db, get_mongo_db_sync
from tradingagents.utils.logging_manager import get_logger
from app.utils.timezone import now_tz

logger = get_logger(__name__)

# UTC+8 time zone
UTC_8 = timezone(timedelta(hours=8))
ACTIVE_EXECUTION_WINDOW_MINUTES = 30
FALLBACK_EXECUTION_WINDOW_MINUTES = 60


def get_utc8_now():
    """
    get UTC+8 Current time (naive datetime)

    Note: Returning a naive datetime (without time zone information), MongoDB will store the local time value as is
    In this way, the front end can be added directly +08:00 Suffix display
    """
    return now_tz().replace(tzinfo=None)


def get_execution_activity_time(execution: Optional[Dict[str, Any]]) -> Optional[datetime]:
    """To obtain the latest activity time of execution records, updated_at is preferred, and is compatible with old data falling back to timestamp."""
    if not execution:
        return None

    return execution.get("updated_at") or execution.get("timestamp") or execution.get("scheduled_time")


def build_active_running_query(job_filter: Optional[Dict[str, Any]] = None, window_minutes: int = ACTIVE_EXECUTION_WINDOW_MINUTES) -> Dict[str, Any]:
    """Build query conditions for running execution records that are still active."""
    active_threshold = get_utc8_now() - timedelta(minutes=window_minutes)
    query: Dict[str, Any] = {
        "status": "running",
        "$or": [
            {"updated_at": {"$gte": active_threshold}},
            {
                "updated_at": {"$exists": False},
                "timestamp": {"$gte": active_threshold}
            }
        ]
    }

    if job_filter:
        query.update(job_filter)

    return query


def build_recent_execution_query(job_filter: Dict[str, Any], statuses: Optional[List[str]] = None, window_minutes: int = ACTIVE_EXECUTION_WINDOW_MINUTES) -> Dict[str, Any]:
    """Construct query conditions for recently active execution records."""
    active_threshold = get_utc8_now() - timedelta(minutes=window_minutes)
    query: Dict[str, Any] = {
        **job_filter,
        "$or": [
            {"updated_at": {"$gte": active_threshold}},
            {
                "updated_at": {"$exists": False},
                "timestamp": {"$gte": active_threshold}
            }
        ]
    }

    if statuses is not None:
        query["status"] = {"$in": statuses} if len(statuses) > 1 else statuses[0]

    return query


class TaskCancelledException(Exception):
    """任务被取消异常"""
    pass


class SchedulerService:
    """定时任务管理服务"""

    def __init__(self, scheduler: AsyncIOScheduler):
        """
        Initialize service

        Args:
            scheduler: APScheduler Scheduler instance
        """
        self.scheduler = scheduler
        self.db = None

        # Add event listener to monitor task execution
        self._setup_event_listeners()
    
    def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def _get_active_running_executions(self, job_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get the latest running execution records that still have heartbeats."""
        db = self._get_db()
        query = build_active_running_query({"job_id": job_id} if job_id else None)

        running_executions = await db.scheduler_executions.find(query).sort("timestamp", -1).to_list(length=100)

        running_by_job: Dict[str, Dict[str, Any]] = {}
        for exec_record in running_executions:
            current_job_id = exec_record.get("job_id")
            if current_job_id and current_job_id not in running_by_job:
                running_by_job[current_job_id] = exec_record

        return running_by_job

    def _build_execution_summary(self, exec_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Build execution record summaries that can be used directly by the front end."""
        if not exec_record:
            return None

        started_at = exec_record.get("timestamp")
        updated_at = exec_record.get("updated_at")
        return {
            "execution_id": str(exec_record.get("_id")),
            "progress": exec_record.get("progress", 0),
            "processed_items": exec_record.get("processed_items"),
            "total_items": exec_record.get("total_items"),
            "current_item": exec_record.get("current_item"),
            "started_at": started_at.isoformat() if started_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "message": exec_record.get("progress_message")
        }
    
    async def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Get a list of all scheduled tasks

        Returns:
            Task list (contains pending task information)
        """
        db = self._get_db()
        running_by_job = await self._get_active_running_executions()
        
        # 🔥 Get all suspended execution records (only query the suspended status, excluding the restored running status)
        # Note: Only records whose status is suspended are queried. Records that have been restored to running will not be displayed.
        suspended_executions = await db.scheduler_executions.find({
            "status": "suspended"
        }).sort("timestamp", -1).to_list(length=100)
        
        # 🔥 Debug log: record the number of pending tasks queried
        if suspended_executions:
            logger.debug(f"📊 查询到 {len(suspended_executions)} 个挂起任务: {[str(e.get('_id')) + ':' + e.get('job_id', '') + ':' + e.get('status', '') for e in suspended_executions[:5]]}")
        
        # 🔥 Grouped by job_id, each job_id only retains the latest pending record (for front-end display)
        suspended_by_job = {}
        for exec_record in suspended_executions:
            job_id = exec_record.get("job_id")
            if job_id:
                # 🔥 Only the latest pending record is kept for each job_id (sorted by timestamp, the first one is the latest)
                if job_id not in suspended_by_job:
                    suspended_by_job[job_id] = exec_record  # Only save the latest one
                # If there is already a record, since it is sorted by timestamp in reverse order, the first one is the latest and does not need to be updated.
        
        jobs = []
        for job in self.scheduler.get_jobs():
            job_dict = self._job_to_dict(job)
            # Get task metadata (trigger name and comments)
            metadata = await self._get_job_metadata(job.id)
            if metadata:
                job_dict["display_name"] = metadata.get("display_name")
                job_dict["description"] = metadata.get("description")

            latest_running = running_by_job.get(job.id)
            job_dict["has_running_execution"] = latest_running is not None
            if latest_running:
                job_dict["running_execution"] = self._build_execution_summary(latest_running)
            
            # 🔥 Check for pending execution records
            # Note: Only records whose status is suspended are displayed. Records that have been restored to running will not be displayed.
            # Only the latest pending record is displayed for each job_id
            if job.id in suspended_by_job:
                latest_suspended = suspended_by_job[job.id]  # Already the latest record sorted by timestamp
                # Confirm again that the status is suspended (to prevent data inconsistency)
                if latest_suspended.get("status") == "suspended":
                    job_dict["has_suspended_execution"] = True
                    job_dict["suspended_execution"] = {
                        "execution_id": str(latest_suspended["_id"]),
                        "progress": latest_suspended.get("progress", 0),
                        "processed_items": latest_suspended.get("processed_items"),
                        "total_items": latest_suspended.get("total_items"),
                        "current_item": latest_suspended.get("current_item"),
                        "started_at": latest_suspended.get("timestamp").isoformat() if latest_suspended.get("timestamp") else None,
                        "message": latest_suspended.get("progress_message")
                    }
                else:
                    # If the status is not suspended, no suspension prompt is displayed.
                    job_dict["has_suspended_execution"] = False
            else:
                job_dict["has_suspended_execution"] = False
            
            jobs.append(job_dict)

        logger.info(f"📋 获取到 {len(jobs)} 个定时任务")
        return jobs
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task details

        Args:
            job_id: Task ID

        Returns:
            Task details, returned if they do not exist None
        """
        job = self.scheduler.get_job(job_id)
        if job:
            job_dict = self._job_to_dict(job, include_details=True)
            running_by_job = await self._get_active_running_executions(job_id=job_id)
            # Get task metadata
            metadata = await self._get_job_metadata(job_id)
            if metadata:
                job_dict["display_name"] = metadata.get("display_name")
                job_dict["description"] = metadata.get("description")

            latest_running = running_by_job.get(job_id)
            job_dict["has_running_execution"] = latest_running is not None
            if latest_running:
                job_dict["running_execution"] = self._build_execution_summary(latest_running)
            return job_dict
        return None
    
    async def pause_job(self, job_id: str) -> bool:
        """
        Pause task
        
        Args:
            job_id: Task ID
            
        Returns:
            Is it successful?
        """
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"⏸️ 任务 {job_id} 已暂停")
            
            # Record operation history
            await self._record_job_action(job_id, "pause", "success")
            return True
        except Exception as e:
            logger.error(f"❌ 暂停任务 {job_id} 失败: {e}")
            await self._record_job_action(job_id, "pause", "failed", str(e))
            return False
    
    async def resume_job(self, job_id: str) -> bool:
        """
        recovery task

        Args:
            job_id: Task ID

        Returns:
            Is it successful?
        """
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"▶️ 任务 {job_id} 已恢复")

            # Record operation history
            await self._record_job_action(job_id, "resume", "success")
            return True
        except Exception as e:
            logger.error(f"❌ 恢复任务 {job_id} 失败: {e}")
            await self._record_job_action(job_id, "resume", "failed", str(e))
            return False

    async def reschedule_job(self, job_id: str, cron_expression: str) -> bool:
        """
        Modify the CRON expression of the task

        Args:
            job_id: Task ID
            cron_expression: New CRON expressions such as "0 8 * * 1-5"

        Returns:
            Is it successful?
        """
        from apscheduler.triggers.cron import CronTrigger
        from app.core.config import settings

        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error(f"❌ 任务 {job_id} 不存在")
                return False

            current_execution_id: Optional[str] = None

            # Validate CRON expression format
            try:
                new_trigger = CronTrigger.from_crontab(cron_expression, timezone=settings.TIMEZONE)
            except Exception as e:
                logger.error(f"❌ Invalid CRON expression '{cron_expression}': {e}")
                return False

            # Logging old trigger information
            old_trigger_str = str(job.trigger)

            # Modify task triggers
            self.scheduler.reschedule_job(job_id, trigger=new_trigger)

            logger.info(f"🔄 任务 {job_id} CRON已更新: {old_trigger_str} -> {cron_expression}")

            # Record operation history
            await self._record_job_action(
                job_id,
                "reschedule",
                "success",
                f"CRON表达式已更新: {cron_expression}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ 修改任务 {job_id} CRON失败: {e}")
            await self._record_job_action(job_id, "reschedule", "failed", str(e))
            return False

    async def trigger_job(self, job_id: str, kwargs: Optional[Dict[str, Any]] = None, force: bool = False) -> bool:
        """
        Manually trigger task execution

        Note: If the task is in a suspended state, the task will be temporarily resumed first and will not be automatically suspended after execution once.

        Args:
            job_id: Task ID
            kwargs: Keyword arguments passed to the task function (optional)
            force: Whether to force execution (execute even if there is a running record), default False

        Returns:
            Is it successful?
            
        Raises:
            HTTPException: If there is a running record and force=False, Throws a 409 status code to prompt the user whether to force execution
        """
        from fastapi import HTTPException
        # 🔥 When triggered manually, add a flag to allow the task function to skip concurrency checks
        if kwargs is None:
            kwargs = {}
        kwargs["_manual_trigger"] = True  # Mark this as a manual trigger and allow execution
        if force:
            kwargs["_force_execute"] = True  # Whether the tag is enforced
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error(f"❌ 任务 {job_id} 不存在")
                return False

            # Check whether the task is suspended (next_run_time is None to indicate suspension)
            was_paused = job.next_run_time is None
            if was_paused:
                logger.warning(f"⚠️ 任务 {job_id} 处于暂停状态，临时恢复以执行一次")
                self.scheduler.resume_job(job_id)
                # Reacquire the job object (the status has changed after recovery)
                job = self.scheduler.get_job(job_id)
                logger.info(f"✅ 任务 {job_id} 已临时恢复")

            # If kwargs are provided, merge into the task's kwargs
            # 🔥 Initialize merged_kwargs to avoid being undefined when kwargs is empty
            original_kwargs = job.kwargs.copy() if job.kwargs else {}
            merged_kwargs = original_kwargs.copy()
            
            if kwargs:
                # 🔥 First remove the internal tags (_resume_execution_id), these should not be passed to the task function
                clean_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_")}
                # Merge new kwargs (containing only parameters that the task function can accept)
                merged_kwargs = {**original_kwargs, **clean_kwargs}
                # Modify the kwargs of the task (so that update_job_progress can read the correct parameters)
                job.modify(kwargs=merged_kwargs)
                logger.info(f"📝 任务 {job_id} 参数已更新: {clean_kwargs} -> 合并后: {merged_kwargs}")

            # 🔥 First create an execution record and save kwargs to ensure that the correct parameters can be read during recovery.
            # In this way, even if the task is executed immediately, update_job_progress can read the correct kwargs
            try:
                db = self._get_db()
                # Get the final kwargs (merged)
                final_kwargs = job.kwargs.copy() if job.kwargs else {}
                if kwargs:
                    final_kwargs.update(kwargs)
                
                # 🔥 Check if it is a recovery operation (marked by _resume_execution_id)
                # Note: _resume_execution_id needs to be passed to the task function so that the task function knows that this is a resume execution and is allowed to execute
                resume_execution_id = final_kwargs.pop("_resume_execution_id", None)
                
                if resume_execution_id:
                    # This is a recovery operation, reusing the pending execution record
                    from bson import ObjectId
                    existing_record = await db.scheduler_executions.find_one({"_id": ObjectId(resume_execution_id)})
                    if existing_record:
                        current_execution_id = str(existing_record["_id"])
                        # 🔥 Read progress information from the execution record and add it to kwargs
                        processed_items = existing_record.get("processed_items")
                        if processed_items is not None:
                            final_kwargs["_resume_from_index"] = processed_items
                            logger.info(f"📊 Recovery operation: Read from execution record processed_items={processed_items}, has been added to kwargs")
                        else:
                            logger.warning(f"⚠️ There is no processed_items in the execution record and will start from 0")
                        
                        # 🔥 Add _resume_execution_id to final_kwargs as well so that the task function knows this is a resume execution
                        final_kwargs["_resume_execution_id"] = resume_execution_id
                        
                        # Update kwargs and status of existing records (note: final_kwargs contains _resume_from_index and _resume_execution_id)
                        # 🔥 Clear the cancellation mark because the user actively resumed the task and indicated that he wanted to continue execution.
                        await db.scheduler_executions.update_one(
                            {"_id": ObjectId(resume_execution_id)},
                            {
                                "$set": {
                                    "job_kwargs": final_kwargs,  # Save kwargs (contains _resume_from_index and _resume_execution_id)
                                    "status": "running",
                                    "is_manual": True,  # 🔥 When resuming execution, mark it as manual operation
                                    "cancel_requested": False,  # 🔥 Clear cancellation mark
                                    "updated_at": get_utc8_now()
                                }
                            }
                        )
                        
                        # 🔥 Also clears the cancellation marks of all related execution records (including subtasks)
                        related_update_result = await db.scheduler_executions.update_many(
                            {
                                "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                                "status": {"$in": ["running", "suspended"]}
                            },
                            {
                                "$set": {
                                    "cancel_requested": False,  # 🔥 Clear the cancellation flags of all related execution records
                                    "updated_at": get_utc8_now()
                                }
                            }
                        )
                        if related_update_result.modified_count > 0:
                            logger.info(f"✅ 同时清除了 {related_update_result.modified_count} 个相关执行记录的取消标记 "
                                      f"(job_id match: ^{job_id}(_|$))")
                        logger.info(f"📝 已复用执行记录 {resume_execution_id} 并更新kwargs: {final_kwargs} (is_manual=True)")
                    else:
                        logger.warning(f"⚠️ 指定的执行记录 {resume_execution_id} 不存在，将创建新记录")
                        resume_execution_id = None  # Mark it as None and create new records later.
                
                if not resume_execution_id:
                    # 🔥 It is not a recovery operation. Check whether there are suspended tasks (suspended status, no time limit)
                    # Prioritize the search for records in the suspended state (suspended tasks should resume execution)
                    suspended_record = await db.scheduler_executions.find_one(
                        {
                            "job_id": job_id,
                            "status": "suspended"
                        },
                        sort=[("timestamp", -1)]
                    )
                    
                    # 🔥 If there are no pending tasks, check whether there are still active running records.
                    # Judgment criteria: There is updated_at heartbeat in the last 30 minutes; old data is compatible with fallback to timestamp
                    if not suspended_record:
                        active_threshold = get_utc8_now() - timedelta(minutes=30)
                        running_record = await db.scheduler_executions.find_one(
                            {
                                "job_id": job_id,
                                "status": "running",
                                "$or": [
                                    {"updated_at": {"$gte": active_threshold}},
                                    {
                                        "updated_at": {"$exists": False},
                                        "timestamp": {"$gte": active_threshold}
                                    }
                                ]
                            },
                            sort=[("timestamp", -1)]
                        )
                        existing_record = running_record
                    else:
                        existing_record = suspended_record
                    
                    # 🔥 If no suspended or running records are found, check whether there is a canceled record (within 1 hour)
                    # If there is a canceled record, the user clicks"Execute immediately"A new task should be created and started from scratch
                    if not existing_record:
                        one_hour_ago = get_utc8_now() - timedelta(hours=1)
                        cancelled_record = await db.scheduler_executions.find_one(
                            {
                                "job_id": job_id,
                                "status": "cancelled",
                                "timestamp": {"$gte": one_hour_ago}
                            },
                            sort=[("timestamp", -1)]
                        )
                        # 🔥 If a canceled record is found, do not restore it, but create a new task (from scratch)
                        # So existing_record remains None and new records will be created later.
                        if cancelled_record:
                            logger.info(f"🔄 Canceled records within 1 hour were detected (execution_id={cancelled_record.get('_id')}) , "
                                      f"New tasks will be created from scratch and canceled records will not be restored.")
                    
                    if existing_record:
                        # 🔥 If it is in suspended state, execution will be automatically resumed (when triggered manually)
                        if existing_record.get("status") == "suspended":
                            current_execution_id = str(existing_record["_id"])
                            resume_execution_id = str(existing_record["_id"])
                            # Read progress information from execution records
                            processed_items = existing_record.get("processed_items")
                            if processed_items is not None:
                                final_kwargs["_resume_from_index"] = processed_items
                                logger.info(f"📊 Manually trigger the resumption of pending tasks: Read from execution record processed_items={processed_items}, has been added to kwargs")
                            else:
                                logger.warning(f"⚠️ There is no processed_items in the execution record and will start from 0")
                            
                            # Add _resume_execution_id to final_kwargs
                            final_kwargs["_resume_execution_id"] = resume_execution_id
                            
                            # Update the status of existing records to running and set is_manual=True (manually trigger recovery)
                            # 🔥 Clear the cancellation mark because the user actively triggered the task and indicated that it wanted to continue execution.
                            await db.scheduler_executions.update_one(
                                {"_id": existing_record["_id"]},
                                {
                                    "$set": {
                                        "job_kwargs": final_kwargs,
                                        "status": "running",
                                        "is_manual": True,  # 🔥 When recovery is triggered manually, it is marked as a manual operation
                                        "cancel_requested": False,  # 🔥 Clear cancellation mark
                                        "updated_at": get_utc8_now()
                                    }
                                }
                            )
                            
                            # 🔥 Also clears the cancellation marks of all related execution records (including subtasks)
                            related_update_result = await db.scheduler_executions.update_many(
                                {
                                    "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                                    "status": {"$in": ["running", "suspended"]}
                                },
                                {
                                    "$set": {
                                        "cancel_requested": False,  # 🔥 Clear the cancellation flags of all related execution records
                                        "updated_at": get_utc8_now()
                                    }
                                }
                            )
                            if related_update_result.modified_count > 0:
                                logger.info(f"✅ 同时清除了 {related_update_result.modified_count} 个相关执行记录的取消标记 "
                                          f"(job_id match: ^{job_id}(_|$))")
                            logger.info(f"🔄 When manually triggered, a suspended task is detected and execution is automatically resumed.: {resume_execution_id} (is_manual=True)")
                        else:
                            current_execution_id = str(existing_record["_id"])
                            # 🔥 If it is running state, check whether user confirmation is required
                            if not force:
                                # There is a running record and it is not forced. User confirmation is required.
                                running_instance_id = str(existing_record["_id"])
                                running_start_time = existing_record.get("timestamp")
                                running_progress = existing_record.get("progress", 0)
                                
                                logger.warning(f"⚠️ 任务 {job_id} 已有实例在运行（_id={running_instance_id}），需要用户确认是否强制执行")
                                
                                # Throws 409 Conflict, prompting the front end to display a confirmation dialog box
                                raise HTTPException(
                                    status_code=409,
                                    detail={
                                        "code": "TASK_ALREADY_RUNNING",
                                        "message": f"任务 {job_id} 已有实例正在运行中",
                                        "running_instance_id": running_instance_id,
                                        "running_start_time": running_start_time.isoformat() if running_start_time else None,
                                        "running_progress": running_progress,
                                        "suggestion": "Is it enforceable? Forcing execution will skip concurrency checks, potentially causing duplicate executions."
                                    }
                                )
                            
                            # When forcing, update kwargs and continue execution while clearing the cancellation flag
                            await db.scheduler_executions.update_one(
                                {"_id": existing_record["_id"]},
                                {
                                    "$set": {
                                        "job_kwargs": final_kwargs,
                                        "cancel_requested": False  # 🔥 Clear the cancellation mark and the user actively triggers the task
                                    }
                                }
                            )
                            logger.info(f"🔧 强制执行：已更新执行记录 {existing_record['_id']} 的kwargs: {final_kwargs}")
                    else:
                        # Create a new execution record (the task has just started)
                        # 🔥 When triggering manually, set is_manual=True, and clear the cancel flag
                        execution_record = {
                            "job_id": job_id,
                            "job_name": job.name if job else job_id,
                            "status": "running",
                            "timestamp": get_utc8_now(),
                            "scheduled_time": get_utc8_now(),
                            "is_manual": True,  # 🔥 Marked as manual operation when triggered manually
                            "cancel_requested": False,  # 🔥 New tasks are not marked as canceled by default
                            "job_kwargs": final_kwargs  # 🔥 Save kwargs (cleaned, does not contain _resume_execution_id)
                        }
                        insert_result = await db.scheduler_executions.insert_one(execution_record)
                        current_execution_id = str(insert_result.inserted_id)
                        logger.info(f"📝 Execution record created and saved kwargs: {final_kwargs} (is_manual=True)")
                        
                        # 🔥 Clear the old Redis cache immediately to ensure that the front-end does not read old data when querying the progress
                        try:
                            from app.core.database import get_redis_sync_client
                            from app.core.redis_client import RedisKeys
                            redis_sync = get_redis_sync_client()
                            if redis_sync:
                                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                                redis_sync.delete(progress_key)
                                logger.info(f"🗑️ [手动触发] 已清除旧的Redis进度缓存: {progress_key}（新任务从头开始）")
                        except Exception as redis_error:
                            logger.warning(f"⚠️ [manual trigger] Failed to clear Redis cache (does not affect task execution): {redis_error}")
            except Exception as record_error:
                logger.warning(f"⚠️ Failed to save execution record kwargs (does not affect task execution): {record_error}")
            
            # 🔥 Execute the task immediately (without waiting for APScheduler scheduling)
            # This ensures that the task is executed immediately rather than waiting for the next scheduling cycle
            try:
                import asyncio
                import inspect
                
                # 🔥 Clean up internal tags in kwargs (these should not be passed to task functions)
                # But _resume_from_index, _resume_execution_id, _manual_trigger and _force_execute are retained because the task function needs them to determine whether execution is allowed
                # 🔥 Use final_kwargs instead of merged_kwargs because final_kwargs contains recovery location information
                clean_kwargs_for_execution = {}
                for k, v in final_kwargs.items():
                    if k.startswith("_") and k not in ["_resume_from_index", "_resume_execution_id", "_manual_trigger", "_force_execute"]:
                        # Skip internal tags (except _resume_from_index, _resume_execution_id, _manual_trigger and _force_execute)
                        continue
                    clean_kwargs_for_execution[k] = v
                
                # 🔥 If it is to resume execution, add _resume_execution_id to kwargs as well
                if resume_execution_id:
                    clean_kwargs_for_execution["_resume_execution_id"] = resume_execution_id
                
                # 🔥 Manual trigger flags are already included in final_kwargs (via kwargs["_manual_trigger"] = True) 
                
                logger.info(f"🔍 Build execution parameters: merged_kwargs={merged_kwargs}, final_kwargs={final_kwargs}, clean_kwargs_for_execution={clean_kwargs_for_execution}")

                if current_execution_id:
                    clean_kwargs_for_execution["_trigger_execution_id"] = current_execution_id
                    logger.info(f"🧷 Current manually triggered execution record ID: {current_execution_id}")
                
                # Get task function and parameters
                func = job.func
                
                # 🔥 Check the function signature and only pass parameters accepted by the function
                sig = inspect.signature(func)
                func_params = set(sig.parameters.keys())
                
                # Filter kwargs to only keep parameters accepted by the function
                filtered_kwargs = {}
                for k, v in clean_kwargs_for_execution.items():
                    # If the function has **kwargs parameter, or if the parameter name is in the function signature, it is passed
                    if k in func_params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                        filtered_kwargs[k] = v
                    else:
                        logger.debug(f"⏭️ 跳过参数 {k}（函数 {func.__name__} 不接受此参数）")
                
                # 🔥 Use filtered kwargs (only parameters accepted by the function)
                logger.info(f"⚡ 立即执行任务 {job_id} (协程函数, kwargs={filtered_kwargs})")
                
                # Check if the task function is a coroutine
                if inspect.iscoroutinefunction(func):
                    # Coroutine function, executed immediately (in the background)
                    asyncio.create_task(func(**filtered_kwargs))
                    logger.info(f"✅ 任务 {job_id} 已立即执行（协程函数，后台执行中）")
                else:
                    # Synchronous function, executed using thread pool
                    import concurrent.futures
                    logger.info(f"⚡ 立即执行任务 {job_id} (同步函数, kwargs={filtered_kwargs})")
                    # Use thread pool to execute synchronized functions
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    executor.submit(func, **filtered_kwargs)
                    logger.info(f"✅ 任务 {job_id} 已提交到线程池执行")
                
                # 🔥 Successful execution immediately, no need to call again job.modify(next_run_time=now)
                # Because this will trigger APScheduler to schedule the task again, resulting in repeated execution
                logger.info(f"🚀 任务 {job_id} 已立即执行 (was_paused={was_paused}, kwargs={clean_kwargs_for_execution})")
            except Exception as immediate_exec_error:
                # Immediate execution fails and falls back to APScheduler scheduling
                logger.warning(f"⚠️ 立即执行任务 {job_id} 失败，回退到APScheduler调度: {immediate_exec_error}", exc_info=True)
                # Triggering tasks manually - using current time with time zone
                from datetime import timezone
                now = datetime.now(timezone.utc)
                job.modify(next_run_time=now)
                logger.info(f"🚀 Scheduling tasks through APScheduler {job_id} (next_run_time={now})")

            # Record operation history
            action_note = f"Manually trigger execution (suspended state: {was_paused}"
            if kwargs:
                action_note += f", 参数: {kwargs}"
            action_note += ")"
            await self._record_job_action(job_id, "trigger", "success", action_note)

            # 🔥 NOTE: No longer called here _record_job_execution
            # Reason:
            # 1. The execution record has been created at lines 352-361 if it does not exist
            # 2. If you create it again here, it will result in duplicate records.
            # 3. update_job_progress Records will be created or updated at the start of the task
            # 4. If the record already exists, update_job_progress will update it; if it does not exist, it will create it
            logger.info(f"📝 任务 {job_id} 已触发，执行记录将在任务开始时由 update_job_progress 创建或更新")

            return True
        except Exception as e:
            logger.error(f"❌ 触发任务 {job_id} 失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            await self._record_job_action(job_id, "trigger", "failed", str(e))
            return False
    
    async def get_job_history(
        self,
        job_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get task execution history
        
        Args:
            job_id: Task ID
            limit: Return quantity limit
            offset: offset
            
        Returns:
            execution history
        """
        try:
            db = self._get_db()
            cursor = db.scheduler_history.find(
                {"job_id": job_id}
            ).sort("timestamp", -1).skip(offset).limit(limit)
            
            history = []
            async for doc in cursor:
                doc.pop("_id", None)
                history.append(doc)
            
            return history
        except Exception as e:
            logger.error(f"❌ 获取任务 {job_id} 执行历史失败: {e}")
            return []
    
    async def count_job_history(self, job_id: str) -> int:
        """
        Statistics of task execution history
        
        Args:
            job_id: Task ID
            
        Returns:
            Number of historical records
        """
        try:
            db = self._get_db()
            count = await db.scheduler_history.count_documents({"job_id": job_id})
            return count
        except Exception as e:
            logger.error(f"❌ 统计任务 {job_id} 执行历史失败: {e}")
            return 0
    
    async def get_all_history(
        self,
        limit: int = 50,
        offset: int = 0,
        job_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all task execution history
        
        Args:
            limit: Return quantity limit
            offset: offset
            job_id: Task ID filtering
            status: Status filtering
            
        Returns:
            execution history
        """
        try:
            db = self._get_db()
            
            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status
            
            cursor = db.scheduler_history.find(query).sort("timestamp", -1).skip(offset).limit(limit)
            
            history = []
            async for doc in cursor:
                doc.pop("_id", None)
                history.append(doc)
            
            return history
        except Exception as e:
            logger.error(f"❌ 获取执行历史失败: {e}")
            return []
    
    async def count_all_history(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> int:
        """
        Count the execution history of all tasks

        Args:
            job_id: Task ID filtering
            status: Status filtering

        Returns:
            Number of historical records
        """
        try:
            db = self._get_db()

            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status

            count = await db.scheduler_history.count_documents(query)
            return count
        except Exception as e:
            logger.error(f"❌ 统计执行历史失败: {e}")
            return 0

    async def get_job_executions(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        is_manual: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get task execution history

        Args:
            job_id: Task ID (optional, if not specified, all tasks will be returned)
            status: Status filtering (success/failed/missed/running)
            is_manual: Whether to trigger manually (True=manual,False=automatic,None=all)
            limit: Return quantity limit
            offset: offset

        Returns:
            Execution history list
        """
        try:
            db = self._get_db()

            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status

            # Handling is_manual filtering
            if is_manual is not None:
                if is_manual:
                    # Manual trigger: is_manual must be true
                    query["is_manual"] = True
                else:
                    # Automatically triggered: is_manual field does not exist or is false
                    # Use $ne (not equal) to exclude is_manual=true records
                    query["is_manual"] = {"$ne": True}

            cursor = db.scheduler_executions.find(query).sort("timestamp", -1).skip(offset).limit(limit)

            executions = []
            async for doc in cursor:
                # Convert _id to string
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])

                # Formatted time (MongoDB stores naive datetime, which represents local time)
                # Directly serialize to ISO format string, the front end will automatically add +08:00 suffix
                for time_field in ["scheduled_time", "timestamp", "updated_at"]:
                    if doc.get(time_field):
                        dt = doc[time_field]
                        # If it is a datetime object, convert it to an ISO format string
                        if hasattr(dt, 'isoformat'):
                            doc[time_field] = dt.isoformat()

                executions.append(doc)

            return executions
        except Exception as e:
            logger.error(f"❌ Failed to obtain task execution history: {e}")
            return []

    async def count_job_executions(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        is_manual: Optional[bool] = None
    ) -> int:
        """
        Statistics of task execution history

        Args:
            job_id: Task ID (optional)
            status: Status filtering (optional)
            is_manual: Whether to trigger manually (optional)

        Returns:
            Execution history quantity
        """
        try:
            db = self._get_db()

            # Build query conditions
            query = {}
            if job_id:
                query["job_id"] = job_id
            if status:
                query["status"] = status

            # Handling is_manual filtering
            if is_manual is not None:
                if is_manual:
                    # Manual trigger: is_manual must be true
                    query["is_manual"] = True
                else:
                    # Automatically triggered: is_manual field does not exist or is false
                    query["is_manual"] = {"$ne": True}

            count = await db.scheduler_executions.count_documents(query)
            return count
        except Exception as e:
            logger.error(f"❌ Statistics task execution history failed: {e}")
            return 0

    async def cancel_job_execution(self, execution_id: str) -> bool:
        """
        Cancel/terminate task execution

        For the task being executed, set the cancellation mark;
        For tasks that have exited but are still running in the database, mark them directly as failed

        Args:
            execution_id: Execution record ID (MongoDB _id)

        Returns:
            Is it successful?
        """
        try:
            from bson import ObjectId
            db = self._get_db()

            # Find execution records
            execution = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if not execution:
                logger.error(f"❌ 执行记录不存在: {execution_id}")
                return False

            if execution.get("status") != "running":
                logger.warning(f"⚠️ The execution record status is not running: {execution_id} (status={execution.get('status')})")
                return False

            job_id = execution.get("job_id")
            
            # 🔥 Set cancellation mark: update the current execution record and all related execution records (including subtasks) at the same time
            # For example: If you cancel tushare_financial_sync, you must also cancel subtasks such as tushare_financial_sync_tushare
            update_result = await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "cancel_requested": True,
                        "updated_at": get_utc8_now()
                    }
                }
            )
            
            # 🔥 Also update all execution records starting with the job_id (including subtasks)
            # For example: all subtasks of tushare_financial_sync (tushare_financial_sync_tushare, etc.)
            if job_id:
                related_update_result = await db.scheduler_executions.update_many(
                    {
                        "job_id": {"$regex": f"^{job_id}(_|$)"},  # Matches job_id or starts with job_id
                        "status": {"$in": ["running", "suspended"]},
                        "cancel_requested": {"$ne": True}  # Only update records that have not yet been marked as cancelled.
                    },
                    {
                        "$set": {
                            "cancel_requested": True,
                            "updated_at": get_utc8_now()
                        }
                    }
                )
                if related_update_result.modified_count > 0:
                    logger.info(f"✅ 同时设置了 {related_update_result.modified_count} 个相关执行记录的取消标记 "
                              f"(job_id match: ^{job_id}(_|$))")
            
            # 🔥 Check if the update is successful
            if update_result.modified_count == 0:
                logger.warning(f"⚠️ Failed to set cancellation flag: execution record may not exist or status may have changed (execution_id={execution_id})")
                return False

            # 🔥 Update the Redis cache immediately so the front end can immediately see that the task has been cancelled.
            try:
                from app.core.database import get_redis_sync_client
                from app.core.redis_client import RedisKeys
                import json
                
                redis_sync = get_redis_sync_client()
                if redis_sync and job_id:
                    progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                    
                    # 🔥 Read the current progress data (if it exists)
                    existing_progress_str = redis_sync.get(progress_key)
                    if existing_progress_str:
                        try:
                            progress_data = json.loads(existing_progress_str)
                        except:
                            progress_data = {}
                    else:
                        progress_data = {}
                    
                    # 🔥 The update status is"cancelling" (being canceled) and retain the current progress information
                    progress_data.update({
                        "status": "cancelling",  # 🔥 Mark as canceling
                        "message": "任务正在取消中...",
                        "updated_at": get_utc8_now().isoformat(),
                        "execution_id": execution_id
                    })
                    
                    # 🔥 Save to Redis (set a shorter TTL since the task will be canceled soon)
                    redis_sync.setex(
                        progress_key,
                        3600,  # 1 hours TTL
                        json.dumps(progress_data, ensure_ascii=False, default=str)
                    )
                    logger.info(f"✅ The Redis cache has been updated and the task status is cancelling: job_id={job_id}")
            except Exception as redis_error:
                # Redis Failure to update does not affect the cancellation operation
                logger.warning(f"⚠️ Failed to update Redis cache (does not affect cancellation operation): {redis_error}")

            logger.info(f"✅ 已设置取消标记: {execution.get('job_name', execution.get('job_id'))} "
                       f"(execution_id={execution_id}, job_id={execution.get('job_id')})")
            return True

        except Exception as e:
            logger.error(f"❌ 取消任务执行失败: {e}")
            return False

    async def mark_execution_as_failed(self, execution_id: str, reason: str = "用户手动标记为失败") -> bool:
        """
        Mark execution records as failed

        Used to handle tasks that have exited but are still running in the database

        Args:
            execution_id: Execution record ID (MongoDB _id)
            reason: Reason for failure

        Returns:
            Is it successful?
        """
        try:
            from bson import ObjectId
            db = self._get_db()

            # Find execution records
            execution = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if not execution:
                logger.error(f"❌ 执行记录不存在: {execution_id}")
                return False

            # Update to failed status
            await db.scheduler_executions.update_one(
                {"_id": ObjectId(execution_id)},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": reason,
                        "updated_at": get_utc8_now()
                    }
                }
            )

            logger.info(f"✅ 已标记为失败: {execution.get('job_name', execution.get('job_id'))} (execution_id={execution_id}, reason={reason})")
            return True

        except Exception as e:
            logger.error(f"❌ Mark execution record as failed failed: {e}")
            return False

    async def delete_execution(self, execution_id: str) -> bool:
        """
        Delete execution record

        Args:
            execution_id: Execution record ID (MongoDB _id)

        Returns:
            Is it successful?
        """
        try:
            from bson import ObjectId
            db = self._get_db()

            # Find execution records
            execution = await db.scheduler_executions.find_one({"_id": ObjectId(execution_id)})
            if not execution:
                logger.error(f"❌ 执行记录不存在: {execution_id}")
                return False

            # Do not allow deletion of currently executing tasks
            if execution.get("status") == "running":
                logger.error(f"❌ Cannot delete tasks in progress: {execution_id}")
                return False

            # delete record
            result = await db.scheduler_executions.delete_one({"_id": ObjectId(execution_id)})

            if result.deleted_count > 0:
                logger.info(f"✅ 已删除执行记录: {execution.get('job_name', execution.get('job_id'))} (execution_id={execution_id})")
                return True
            else:
                logger.error(f"❌ 删除执行记录失败: {execution_id}")
                return False

        except Exception as e:
            logger.error(f"❌ 删除执行记录失败: {e}")
            return False

    async def get_latest_execution(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest execution record of the task

        Args:
            job_id: Task ID

        Returns:
            The latest execution record, if there is none, return None
        """
        try:
            db = self._get_db()
            execution = await db.scheduler_executions.find_one(
                {"job_id": job_id},
                sort=[("timestamp", -1)]
            )
            
            if execution:
                # Convert _id to string
                if "_id" in execution:
                    execution["_id"] = str(execution["_id"])
                
                # Format time
                for time_field in ["scheduled_time", "timestamp", "updated_at"]:
                    if execution.get(time_field):
                        dt = execution[time_field]
                        if hasattr(dt, 'isoformat'):
                            execution[time_field] = dt.isoformat()
            
            return execution
        except Exception as e:
            logger.error(f"❌ Failed to obtain the latest execution record: {e}")
            return None

    async def get_job_execution_stats(self, job_id: str) -> Dict[str, Any]:
        """
        Get task execution statistics

        Args:
            job_id: Task ID

        Returns:
            Statistics
        """
        try:
            db = self._get_db()

            # Count the execution times of each status
            pipeline = [
                {"$match": {"job_id": job_id}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "avg_execution_time": {"$avg": "$execution_time"}
                }}
            ]

            stats = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "missed": 0,
                "avg_execution_time": 0
            }

            async for doc in db.scheduler_executions.aggregate(pipeline):
                status = doc["_id"]
                count = doc["count"]
                stats["total"] += count
                stats[status] = count

                if status == "success" and doc.get("avg_execution_time"):
                    stats["avg_execution_time"] = round(doc["avg_execution_time"], 2)

            # Get the latest execution
            last_execution = await db.scheduler_executions.find_one(
                {"job_id": job_id},
                sort=[("timestamp", -1)]
            )

            if last_execution:
                stats["last_execution"] = {
                    "status": last_execution.get("status"),
                    "timestamp": last_execution.get("timestamp").isoformat() if last_execution.get("timestamp") else None,
                    "execution_time": last_execution.get("execution_time")
                }

            return stats
        except Exception as e:
            logger.error(f"❌ Failed to obtain task execution statistics: {e}")
            return {}
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get scheduler statistics
        
        Returns:
            Statistics
        """
        jobs = self.scheduler.get_jobs()
        
        total = len(jobs)
        running = sum(1 for job in jobs if job.next_run_time is not None)
        paused = total - running
        
        return {
            "total_jobs": total,
            "running_jobs": running,
            "paused_jobs": paused,
            "scheduler_running": self.scheduler.running,
            "scheduler_state": self.scheduler.state
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Scheduler health check
        
        Returns:
            health status
        """
        return {
            "status": "healthy" if self.scheduler.running else "stopped",
            "running": self.scheduler.running,
            "state": self.scheduler.state,
            "timestamp": get_utc8_now().isoformat()
        }
    
    def _job_to_dict(self, job: Job, include_details: bool = False) -> Dict[str, Any]:
        """
        Convert Job object to dictionary
        
        Args:
            job: Job object
            include_details: Whether to include detailed information
            
        Returns:
            Dictionary representation
        """
        result = {
            "id": job.id,
            "name": job.name or job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "paused": job.next_run_time is None,
            "trigger": str(job.trigger),
        }
        
        if include_details:
            result.update({
                "func": f"{job.func.__module__}.{job.func.__name__}",
                "args": job.args,
                "kwargs": job.kwargs,
                "misfire_grace_time": job.misfire_grace_time,
                "max_instances": job.max_instances,
            })
        
        return result
    
    def _setup_event_listeners(self):
        """Set APScheduler event listener"""
        # Listen for task execution success events
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED
        )

        # Listen for task execution failure events
        self.scheduler.add_listener(
            self._on_job_error,
            EVENT_JOB_ERROR
        )

        # Listening task misses execution event
        self.scheduler.add_listener(
            self._on_job_missed,
            EVENT_JOB_MISSED
        )

        logger.info("✅ APScheduler Event listener is set")

        # Add scheduled tasks and detect zombie tasks (running state for a long time)
        self.scheduler.add_job(
            self._check_zombie_tasks,
            'interval',
            minutes=5,
            id='check_zombie_tasks',
            name='检测僵尸任务',
            replace_existing=True
        )
        logger.info("✅ Zombie task detection scheduled task has been added")

    async def check_suspended_tasks_on_startup(self):
        """
        Detect pending tasks when the service starts (tasks that are being executed before the service restarts)
        
        Mark the remaining running status tasks as suspended and the user can continue execution
        """
        try:
            db = self._get_db()

            # Find all tasks in the running state (these are the tasks that are being executed before the service is restarted)
            suspended_tasks = await db.scheduler_executions.find({
                "status": "running"
            }).to_list(length=100)

            for task in suspended_tasks:
                job_id = task.get("job_id")
                
                # 🔥 Attempt to read progress information from Redis if present
                progress_data = {}
                try:
                    from app.core.database import get_redis_sync_client
                    from app.core.redis_client import RedisKeys
                    redis_sync = get_redis_sync_client()
                    if redis_sync:
                        progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                        progress_str = redis_sync.get(progress_key)
                        if progress_str:
                            import json
                            progress_data = json.loads(progress_str)
                            logger.info(f"📊 从Redis读取到挂起任务的进度: {job_id}, 进度: {progress_data.get('progress', 0)}%, 已处理: {progress_data.get('processed_items', 0)}")
                except Exception as e:
                    logger.warning(f"⚠️ Reading progress from Redis failed: {e}")
                
                # Construct update data, giving priority to using progress information in Redis
                update_data = {
                    "status": "suspended",
                    "error_message": "The service restart causes the task to be interrupted and can continue to be executed.",
                    "updated_at": get_utc8_now()
                }
                
                # 🔥 If there is progress information in Redis, save it to MongoDB execution record
                if progress_data:
                    if "progress" in progress_data:
                        update_data["progress"] = progress_data["progress"]
                    if "processed_items" in progress_data:
                        update_data["processed_items"] = progress_data["processed_items"]
                    if "current_item" in progress_data:
                        update_data["current_item"] = progress_data["current_item"]
                    if "total_items" in progress_data:
                        update_data["total_items"] = progress_data["total_items"]
                    if "message" in progress_data:
                        update_data["progress_message"] = progress_data["message"]
                
                # updated to suspended state (suspended) instead of failed
                await db.scheduler_executions.update_one(
                    {"_id": task["_id"]},
                    {"$set": update_data}
                )
                
                progress_info = progress_data.get("progress", task.get("progress", 0))
                processed_info = progress_data.get("processed_items", task.get("processed_items", 0))
                logger.info(f"⏸️ 检测到挂起任务: {task.get('job_name', task.get('job_id'))} (开始时间: {task.get('timestamp')}, 进度: {progress_info}%, 已处理: {processed_info})")

            if suspended_tasks:
                logger.info(f"✅ 已标记 {len(suspended_tasks)} 个挂起任务（服务重启导致）")

        except Exception as e:
            logger.error(f"❌ 检测挂起任务失败: {e}")

    async def _check_zombie_tasks(self):
        """
        Detect zombie tasks (tasks that are running for a long time and have no progress updates)

        Note: This method only handles real timeout tasks. Suspended tasks caused by service restart are handled by check_suspended_tasks_on_startup.

        Judgment criteria:
        1. The status is running
        2. The last updated time (updated_at) has not been updated for more than 30 minutes
        3. If there is no updated_at field, the start time (timestamp) is used to determine
        """
        try:
            db = self._get_db()

            # Find running tasks that have not been updated for more than 30 minutes
            threshold_time = get_utc8_now() - timedelta(minutes=30)

            # 🔥 Modify query conditions: check updated_at instead timestamp
            zombie_tasks = await db.scheduler_executions.find({
                "status": "running",
                "$or": [
                    # Case 1: There is an updated_at field, and there is no update for more than 30 minutes.
                    {"updated_at": {"$lt": threshold_time}},
                    # Case 2: There is no updated_at field, use timestamp to judge (compatible with old data)
                    {
                        "updated_at": {"$exists": False},
                        "timestamp": {"$lt": threshold_time}
                    }
                ]
            }).to_list(length=100)

            for task in zombie_tasks:
                # Get the last updated time (for logs)
                last_update = task.get('updated_at') or task.get('timestamp')
                start_time = task.get('timestamp')

                # Update to failed status
                await db.scheduler_executions.update_one(
                    {"_id": task["_id"]},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": "Task execution times out or the process terminates abnormally (no progress update for more than 30 minutes)",
                            "updated_at": get_utc8_now()
                        }
                    }
                )
                logger.warning(
                    f"⚠️ 检测到僵尸任务: {task.get('job_name', task.get('job_id'))} "
                    f"(start time: {start_time}, last updated: {last_update})"
                )

            if zombie_tasks:
                logger.info(f"✅ 已标记 {len(zombie_tasks)} 个僵尸任务为失败状态")

        except Exception as e:
            logger.error(f"❌ 检测僵尸任务失败: {e}")

    def _on_job_executed(self, event: JobExecutionEvent):
        """任务执行成功回调"""
        # Calculate execution time (handling time zone issues)
        execution_time = None
        if event.scheduled_run_time:
            now = datetime.now(event.scheduled_run_time.tzinfo)
            execution_time = (now - event.scheduled_run_time).total_seconds()

        asyncio.create_task(self._record_job_execution(
            job_id=event.job_id,
            status="success",
            scheduled_time=event.scheduled_run_time,
            execution_time=execution_time,
            return_value=str(event.retval) if event.retval else None,
            progress=100  # Task completed, progress 100%
        ))

    def _on_job_error(self, event: JobExecutionEvent):
        """任务执行失败回调"""
        # Calculate execution time (handling time zone issues)
        execution_time = None
        if event.scheduled_run_time:
            now = datetime.now(event.scheduled_run_time.tzinfo)
            execution_time = (now - event.scheduled_run_time).total_seconds()

        asyncio.create_task(self._record_job_execution(
            job_id=event.job_id,
            status="failed",
            scheduled_time=event.scheduled_run_time,
            execution_time=execution_time,
            error_message=str(event.exception) if event.exception else None,
            traceback=event.traceback if hasattr(event, 'traceback') else None,
            progress=None  # Do not set progress on failure
        ))

    def _on_job_missed(self, event: JobExecutionEvent):
        """任务错过执行回调"""
        asyncio.create_task(self._record_job_execution(
            job_id=event.job_id,
            status="missed",
            scheduled_time=event.scheduled_run_time,
            progress=None  # No progress set when missed
        ))

    async def _record_job_execution(
        self,
        job_id: str,
        status: str,
        scheduled_time: datetime = None,
        execution_time: float = None,
        return_value: str = None,
        error_message: str = None,
        traceback: str = None,
        progress: int = None,
        is_manual: bool = False
    ):
        """
        Record task execution history

        Args:
            job_id: Task ID
            status: Status (running/success/failed/missed)
            scheduled_time: Planned execution time
            execution_time: Actual execution time (seconds)
            return_value: return value
            error_message: error message
            traceback: error stack
            progress: Execution progress (0-100)
            is_manual: Whether to trigger manually
        """
        try:
            db = self._get_db()

            # Get the task name and kwargs
            job = self.scheduler.get_job(job_id)
            job_name = job.name if job else job_id
            job_kwargs = job.kwargs.copy() if job and job.kwargs else {}

            # If it is in the completion status (success/failed), first check whether there is a corresponding running record.
            if status in ["success", "failed"]:
                existing_record = await db.scheduler_executions.find_one(
                    build_active_running_query({"job_id": job_id}),
                    sort=[("timestamp", -1)]
                )

                if existing_record:
                    # Update existing record
                    update_data = {
                        "status": status,
                        "execution_time": execution_time,
                        "updated_at": get_utc8_now()
                    }

                    if return_value:
                        update_data["return_value"] = return_value
                    if error_message:
                        update_data["error_message"] = error_message
                    if traceback:
                        update_data["traceback"] = traceback
                    if progress is not None:
                        update_data["progress"] = progress

                    await db.scheduler_executions.update_one(
                        {"_id": existing_record["_id"]},
                        {"$set": update_data}
                    )

                    # logging
                    if status == "success":
                        logger.info(f"✅ [任务执行] {job_name} 执行成功，耗时: {execution_time:.2f}秒")
                    elif status == "failed":
                        logger.error(f"❌ [任务执行] {job_name} 执行失败: {error_message}")

                    # 🔥 Update Redis cache (asynchronous)
                    await self._update_redis_execution_cache(
                        job_id=job_id,
                        status=status,
                        progress=progress,
                        execution_time=execution_time,
                        error_message=error_message,
                        scheduled_time=existing_record.get("scheduled_time")
                    )

                    return

            # If no running record is found, or is in running/missed status, insert a new record
            # scheduled_time Possibly aware datetime (from APScheduler) which needs to be converted to naive datetime
            scheduled_time_naive = None
            if scheduled_time:
                if scheduled_time.tzinfo is not None:
                    # Convert to local time zone and then remove time zone information
                    scheduled_time_naive = scheduled_time.astimezone(UTC_8).replace(tzinfo=None)
                else:
                    scheduled_time_naive = scheduled_time

            execution_record = {
                "job_id": job_id,
                "job_name": job_name,
                "status": status,
                "scheduled_time": scheduled_time_naive,
                "execution_time": execution_time,
                "timestamp": get_utc8_now(),
                "is_manual": is_manual,
                "job_kwargs": job_kwargs  # 🔥 Save the kwargs of the task for passing parameters when restoring
            }

            if return_value:
                execution_record["return_value"] = return_value
            if error_message:
                execution_record["error_message"] = error_message
            if traceback:
                execution_record["traceback"] = traceback
            if progress is not None:
                execution_record["progress"] = progress

            await db.scheduler_executions.insert_one(execution_record)

            # logging
            if status == "success":
                logger.info(f"✅ [任务执行] {job_name} 执行成功，耗时: {execution_time:.2f}秒")
            elif status == "failed":
                logger.error(f"❌ [任务执行] {job_name} 执行失败: {error_message}")
            elif status == "missed":
                logger.warning(f"⚠️ [任务执行] {job_name} 错过执行时间")
            elif status == "running":
                trigger_type = "手动触发" if is_manual else "自动触发"
                logger.info(f"🔄 [任务执行] {job_name} 开始执行 ({trigger_type})，进度: {progress}%")

            # 🔥 Update Redis cache (asynchronous)
            await self._update_redis_execution_cache(
                job_id=job_id,
                status=status,
                progress=progress,
                execution_time=execution_time,
                error_message=error_message,
                scheduled_time=scheduled_time_naive
            )

        except Exception as e:
            logger.error(f"❌ Record task execution history failure: {e}")

    async def _update_redis_execution_cache(
        self,
        job_id: str,
        status: str,
        progress: int = None,
        execution_time: float = None,
        error_message: str = None,
        scheduled_time: datetime = None
    ):
        """
        Update task execution cache in Redis

        Args:
            job_id: Task ID
            status: Status
            progress: Progress
            execution_time: Execution time
            error_message: error message
            scheduled_time: Planned execution time
        """
        try:
            import json
            from app.core.redis_client import RedisKeys
            from app.core.database import get_redis_client
            
            # Use the system's unified asynchronous Redis client
            redis_client = get_redis_client()
            
            # Build execution data
            execution_data = {
                "job_id": job_id,
                "status": status,
                "updated_at": get_utc8_now().isoformat()
            }
            
            if progress is not None:
                execution_data["progress"] = progress
            if execution_time is not None:
                execution_data["execution_time"] = execution_time
            if error_message:
                execution_data["error_message"] = error_message
            if scheduled_time:
                execution_data["scheduled_time"] = scheduled_time.isoformat() if isinstance(scheduled_time, datetime) else str(scheduled_time)
            
            # Store execution records
            execution_key = RedisKeys.SCHEDULER_JOB_EXECUTION.format(job_id=job_id)
            await redis_client.setex(
                execution_key,
                86400,  # 24 hours TTL
                json.dumps(execution_data, ensure_ascii=False, default=str)
            )
            
            # Update status (simplified version)
            status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)
            status_data = {
                "job_id": job_id,
                "status": status,
                "updated_at": get_utc8_now().isoformat()
            }
            if progress is not None:
                status_data["progress"] = progress
            
            await redis_client.setex(
                status_key,
                86400,
                json.dumps(status_data, ensure_ascii=False, default=str)
            )
            
            # If the task is completed (success/failed), clear the progress cache
            if status in ["success", "failed"]:
                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                await redis_client.delete(progress_key)
                
        except Exception as redis_error:
            # Redis Update failure does not affect the main process, only logs are recorded
            logger.debug(f"⚠️ Failed to update Redis execution cache (does not affect the main process): {redis_error}")

    async def _record_job_action(
        self,
        job_id: str,
        action: str,
        status: str,
        error_message: str = None
    ):
        """
        Record task operation history

        Args:
            job_id: Task ID
            action: Operation type (pause/resume/trigger)
            status: Status (success/failed)
            error_message: error message
        """
        try:
            db = self._get_db()
            await db.scheduler_history.insert_one({
                "job_id": job_id,
                "action": action,
                "status": status,
                "error_message": error_message,
                "timestamp": get_utc8_now()
            })
        except Exception as e:
            logger.error(f"❌ Recording task operation history failed: {e}")

    async def _get_job_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task metadata (trigger name and comments)

        Args:
            job_id: Task ID

        Returns:
            Metadata dictionary, returned if it does not exist None
        """
        try:
            db = self._get_db()
            metadata = await db.scheduler_metadata.find_one({"job_id": job_id})
            if metadata:
                metadata.pop("_id", None)
                return metadata
            return None
        except Exception as e:
            logger.error(f"❌ 获取任务 {job_id} 元数据失败: {e}")
            return None

    async def update_job_metadata(
        self,
        job_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        Update task metadata

        Args:
            job_id: Task ID
            display_name: Trigger name
            description: Remarks

        Returns:
            Is it successful?
        """
        try:
            # Check if the task exists
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error(f"❌ 任务 {job_id} 不存在")
                return False

            db = self._get_db()
            update_data = {
                "job_id": job_id,
                "updated_at": get_utc8_now()
            }

            if display_name is not None:
                update_data["display_name"] = display_name
            if description is not None:
                update_data["description"] = description

            # Update or insert using upsert
            await db.scheduler_metadata.update_one(
                {"job_id": job_id},
                {"$set": update_data},
                upsert=True
            )

            logger.info(f"✅ 任务 {job_id} 元数据已更新")
            return True
        except Exception as e:
            logger.error(f"❌ 更新任务 {job_id} 元数据失败: {e}")
            return False


# Global service instance
_scheduler_service: Optional[SchedulerService] = None
_scheduler_instance: Optional[AsyncIOScheduler] = None


def set_scheduler_instance(scheduler: AsyncIOScheduler):
    """
    Set up scheduler instance
    
    Args:
        scheduler: APScheduler Scheduler instance
    """
    global _scheduler_instance
    _scheduler_instance = scheduler
    logger.info("✅ 调度器实例已设置")


def get_scheduler_service() -> SchedulerService:
    """
    Get scheduler service instance

    Returns:
        Scheduler service instance
    """
    global _scheduler_service, _scheduler_instance

    if _scheduler_instance is None:
        raise RuntimeError("The scheduler instance is not set, please call first set_scheduler_instance()")

    if _scheduler_service is None:
        _scheduler_service = SchedulerService(_scheduler_instance)
        logger.info("✅ 调度器服务实例已创建")

    return _scheduler_service


async def update_job_progress(
    job_id: str,
    progress: int,
    message: str = None,
    current_item: str = None,
    total_items: int = None,
    processed_items: int = None
):
    """
    Update task execution progress (for internal calls by scheduled tasks)

    Args:
        job_id: Task ID
        progress: Progress percentage (0-100)
        message: progress message
        current_item: Current processing item
        total_items: Total number of items
        processed_items: Number of items processed
    """
    try:
        import json
        from app.core.redis_client import RedisKeys

        # Reuse the globally synchronized MongoDB singleton to avoid high-frequency creation/closure of PyMongo background threads.
        sync_db = get_mongo_db_sync()

        # 🔥 Extract the original job_id (if the job_id is tushare_financial_sync_tushare, the original is tushare_financial_sync)
        # Check if job_id ends with data source name (tushare, akshare, baostock)
        original_job_id = job_id
        for data_source in ["tushare", "akshare", "baostock"]:
            if job_id.endswith(f"_{data_source}"):
                original_job_id = job_id[:-len(f"_{data_source}")]
                break

        # 🔥 Find the latest execution record (first look for running/suspended status for recovery)
        # If it is a recovery operation, the pending execution records should be reused
        # First search for records in the running/suspended state (need to be reused during recovery)
        # 🔥 First look for records in the running state (most likely the task currently being executed)
        # 🔥 First search for the record of the current job_id. If it cannot be found, then search for the record of the original job_id.
        latest_execution = sync_db.scheduler_executions.find_one(
            {
                "job_id": job_id,
                "status": "running"  # 🔥 Search for records in running status first
            },
            sort=[("timestamp", -1)]
        )
        
        # 🔥 If the record for the current job_id is not found, try to find the record for the original job_id (using regular expression matching)
        if not latest_execution and original_job_id != job_id:
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": {"$regex": f"^{original_job_id}(_|$)"},  # Matches the original job_id or starts with job_id
                    "status": "running"
                },
                sort=[("timestamp", -1)]
            )
        
        # If no running record is found, search for records in other states.
        if not latest_execution:
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": {"$in": ["suspended", "failed", "cancelled"]}
                },
                sort=[("timestamp", -1)]
            )
        
        # 🔥 If still not found, try to find other status records of the original job_id
        if not latest_execution and original_job_id != job_id:
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                    "status": {"$in": ["suspended", "failed", "cancelled"]}
                },
                sort=[("timestamp", -1)]
            )
        
        # If no record in the above status is found, then search for the most recent success record (within 24 hours)
        # This handles tasks that have just been completed but avoids finding records that are too old
        if not latest_execution:
            from datetime import timedelta
            one_day_ago = get_utc8_now() - timedelta(days=1)
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": "success",
                    "timestamp": {"$gte": one_day_ago}
                },
                sort=[("timestamp", -1)]
            )
        
        # 🔥 If it still cannot be found, try to find the success record of the original job_id
        if not latest_execution and original_job_id != job_id:
            from datetime import timedelta
            one_day_ago = get_utc8_now() - timedelta(days=1)
            latest_execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                    "status": "success",
                    "timestamp": {"$gte": one_day_ago}
                },
                sort=[("timestamp", -1)]
            )

        # 🔥 Determine the start time first for later saving to Redis
        started_at = None
        execution_timestamp = None
        
        if latest_execution:
            # Check if there is a cancellation request
            execution_id = latest_execution.get("_id")
            execution_job_id = latest_execution.get("job_id", "")
            cancel_requested = latest_execution.get("cancel_requested", False)
            
            # 🔥 If the current execution record does not have a cancellation mark, check whether other related execution records have been cancelled.
            # For example: If the cancel flag is set in tushare_financial_sync, also check tushare_financial_sync_tushare
            if not cancel_requested:
                # Extract original job_id
                original_job_id = execution_job_id
                for data_source in ["tushare", "akshare", "baostock"]:
                    if execution_job_id.endswith(f"_{data_source}"):
                        original_job_id = execution_job_id[:-len(f"_{data_source}")]
                        break
                
                # 🔥 Check whether the execution record of the original job_id has a cancellation mark (only the running status is checked, not the suspended status)
                # Because the records in the suspended state may be old tasks, they should not affect new tasks.
                if original_job_id != execution_job_id:
                    original_execution = sync_db.scheduler_executions.find_one(
                        build_active_running_query({
                            "job_id": original_job_id
                        }),
                        sort=[("timestamp", -1)]
                    )
                    # 🔥 If an active running record of the original job_id is found, check whether synchronization of cancellation markers is required
                    if original_execution:
                        execution_time = get_execution_activity_time(original_execution)
                        if execution_time:
                            time_diff = (get_utc8_now() - execution_time).total_seconds()
                            if original_execution.get("cancel_requested", False):
                                # 🔥 Synchronize the cancellation mark to the current execution record
                                sync_db.scheduler_executions.update_one(
                                    {"_id": execution_id},
                                    {
                                        "$set": {
                                            "cancel_requested": True,
                                            "updated_at": get_utc8_now()
                                        }
                                    }
                                )
                                cancel_requested = True
                                logger.info(f"🔄 同步取消标记: 从 {original_job_id} 同步到 {execution_job_id} (时间差: {time_diff:.0f}秒)")
                            else:
                                logger.debug(f"🔍 The active execution record of the original job_id does not have a cancellation mark set and the cancellation status is not synchronized.")
            
            if cancel_requested:
                logger.warning(f"⚠️ 任务 {job_id} 收到取消请求，即将停止 (execution_job_id={execution_job_id})")
                raise TaskCancelledException(f"任务 {job_id} 已被用户取消")

            # 🔥 Check if the task has been marked as failed or canceled
            current_status = latest_execution.get("status")
            cancel_requested = latest_execution.get("cancel_requested", False)
            
            # 🔥 If the task has been marked as failed, canceled, or canceled request, the status should not be updated as running
            # However, if this is a new task execution (by checking the timestamp) it should be allowed to update the progress
            execution_time = latest_execution.get("timestamp") or latest_execution.get("scheduled_time")
            from datetime import timedelta
            time_diff = None
            if execution_time:
                time_diff = (get_utc8_now() - execution_time).total_seconds()
            
            # 🔥 If the failed/cancelled record is older than 1 hour, it may be an old record, allow new records to be created
            is_old_record = time_diff and time_diff > 3600  # 1 hours
            
            if current_status in ["failed", "cancelled"] and not is_old_record:
                logger.warning(f"⚠️ 任务 {job_id} 状态为 {current_status}，不更新状态为running，保持 {current_status} 状态")
                # Only updates progress, not status
                update_data = {
                    "progress": progress,
                    "updated_at": get_utc8_now()
                }
                # 🔥 Even if the status is failed/cancelled, the progress related fields must be updated.
                if current_item:
                    update_data["current_item"] = current_item
                if total_items is not None:
                    update_data["total_items"] = total_items
                if processed_items is not None:
                    update_data["processed_items"] = processed_items
            elif cancel_requested:
                logger.warning(f"⚠️ 任务 {job_id} 已收到取消请求，不更新状态为running")
                # Only update the progress, not the status (keep running, wait for the task to stop)
                update_data = {
                    "progress": progress,
                    "updated_at": get_utc8_now()
                }
                # 🔥 Update progress related fields
                if current_item:
                    update_data["current_item"] = current_item
                if total_items is not None:
                    update_data["total_items"] = total_items
                if processed_items is not None:
                    update_data["processed_items"] = processed_items
            else:
                # 🔥 Update existing record
                # If the progress is 100%, the status should be success; otherwise it remains running
                status = "success" if progress >= 100 else "running"
                update_data = {
                    "progress": progress,
                    "status": status,
                    "updated_at": get_utc8_now()
                }
                
                # 🔥 If the task is completed, record the completion time
                if progress >= 100:
                    update_data["finished_at"] = get_utc8_now()
                    logger.info(f"✅ 任务 {job_id} 已完成，状态更新为success")

            if message:
                update_data["progress_message"] = message
            if current_item:
                update_data["current_item"] = current_item
            if total_items is not None:
                update_data["total_items"] = total_items
            if processed_items is not None:
                update_data["processed_items"] = processed_items

            result = sync_db.scheduler_executions.update_one(
                {"_id": latest_execution["_id"]},
                {"$set": update_data}
            )
            
            # 🔥 Check if the update is successful
            if result.modified_count == 0 and result.matched_count == 0:
                logger.warning(f"⚠️ 任务 {job_id} 进度更新失败：未找到执行记录 {latest_execution['_id']}")
            elif result.modified_count == 0:
                # 🔥 Log even if data has not changed (for debugging)
                logger.debug(f"📝 任务 {job_id} 进度更新：数据未变化（progress={progress}%, processed={processed_items}/{total_items}）")
            else:
                logger.info(f"📝 任务 {job_id} 更新进度成功: {progress}%, 已处理: {processed_items}/{total_items}, execution_id={latest_execution['_id']}")
            
            # Get start time from existing record (make sure not to reset)
            started_at = latest_execution.get("timestamp") or latest_execution.get("scheduled_time")
        else:
            # 🔥 If no execution records are found, check for recent failure or cancellation records
            # 🔥 Check if there is a recent failed or canceled record
            # However, if it is triggered manually (is_manual=True) , should allow creation of new records
            
            # 🔥 Get the task name and kwargs first (before judging is_manual)
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            job_name = job_id
            job_kwargs = {}
            if _scheduler_instance:
                job = _scheduler_instance.get_job(job_id)
                if job:
                    job_name = job.name
                    job_kwargs = job.kwargs.copy() if job.kwargs else {}
            
            # 🔥 Determine whether it is manually triggered (by checking whether there is a _manual_trigger tag in job_kwargs)
            is_manual = job_kwargs.get("_manual_trigger", False) or job_kwargs.get("_force_execute", False)
            
            from datetime import timedelta
            one_hour_ago = get_utc8_now() - timedelta(hours=1)
            recent_failed_or_cancelled = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": {"$in": ["failed", "cancelled"]},
                    "timestamp": {"$gte": one_hour_ago}
                },
                sort=[("timestamp", -1)]
            )
            
            if recent_failed_or_cancelled and not is_manual:
                # 🔥 Prevent new records from being created only when not manually triggered
                # Allow new records to be created when triggered manually (user explicitly asks to start over)
                logger.warning(f"⚠️ 任务 {job_id} 在1小时内有失败/取消记录 ({recent_failed_or_cancelled.get('status')})，"
                             f"It is not triggered manually and does not create new execution records to prevent the state from reverting to running")
                return  # Don't update progress, keep failed/cancelled status
            elif recent_failed_or_cancelled and is_manual:
                # 🔥 When triggered manually, allows new records to be created (from scratch) even if there are canceled records
                logger.info(f"✅ 任务 {job_id} 在1小时内有取消记录，但这是手动触发，将创建新任务从头开始")
            
            # Create a new execution record (the task has just started)

            # 🔥 Recording start time
            execution_timestamp = get_utc8_now()
            started_at = execution_timestamp

            # 🔥 Determine whether it is manually triggered (by checking whether there is a _manual_trigger tag in job_kwargs)
            # Note: If the judgment has been made above, there is no need to repeat the judgment here, but for the sake of code clarity, the judgment is retained.
            if 'is_manual' not in locals():
                is_manual = job_kwargs.get("_manual_trigger", False) or job_kwargs.get("_force_execute", False)

            # 🔥 When creating a new execution record, first insert it into the database to obtain_id
            # 🔥 Clear the previous cancellation flag (if any) since this is a new task
            execution_record = {
                "job_id": job_id,
                "job_name": job_name,
                "status": "running",
                "progress": progress,
                "scheduled_time": execution_timestamp,
                "timestamp": execution_timestamp,
                "is_manual": is_manual,  # 🔥 Set according to _manual_trigger tag is_manual
                "cancel_requested": False,  # 🔥 New tasks are not marked as canceled by default
                "job_kwargs": job_kwargs  # 🔥 Save the kwargs of the task for passing parameters when restoring
            }

            if message:
                execution_record["progress_message"] = message
            if current_item:
                execution_record["current_item"] = current_item
            if total_items is not None:
                execution_record["total_items"] = total_items
            if processed_items is not None:
                execution_record["processed_items"] = processed_items

            result = sync_db.scheduler_executions.insert_one(execution_record)
            # 🔥 Save the newly created execution_id for subsequent saving to Redis
            new_execution_id = str(result.inserted_id)
            logger.info(f"📝 任务 {job_id} 创建新执行记录，execution_id: {new_execution_id}")

        # 🔥 Update the Redis cache at the same time (using the system's unified synchronous Redis client)
        try:
            from app.core.database import get_redis_sync_client
            from app.core.redis_client import RedisKeys
            
            # Get the unified synchronization Redis client of the system
            redis_sync = get_redis_sync_client()
            
            # 🔥 If it is a newly created execution record (manually triggered), clear the old Redis cache and make sure to start from scratch
            if 'new_execution_id' in locals() and is_manual:
                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                try:
                    redis_sync.delete(progress_key)
                    logger.info(f"🗑️ 已清除旧的Redis进度缓存: {progress_key}（新任务从头开始）")
                except Exception as delete_error:
                    logger.warning(f"⚠️ Clearing Redis cache failed: {delete_error}")
            
            # 🔥 If the start time has not been obtained yet, try to obtain it from Redis (compatible with old data)
            # This avoids resetting the start time when the MongoDB record is not found
            if not started_at:
                try:
                    from app.core.redis_client import RedisKeys
                    progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                    existing_progress_str = redis_sync.get(progress_key)
                    if existing_progress_str:
                        existing_progress = json.loads(existing_progress_str)
                        if existing_progress.get("started_at"):
                            # started_at obtained from Redis is a string and needs to be parsed
                            started_at_str = existing_progress["started_at"]
                            try:
                                from datetime import datetime
                                # Try parsing ISO format string
                                if isinstance(started_at_str, str):
                                    started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                                    logger.info(f"📝 任务 {job_id} 从Redis恢复开始时间: {started_at}")
                                else:
                                    started_at = started_at_str
                            except Exception as parse_error:
                                logger.warning(f"⚠️ 解析Redis中的started_at失败: {parse_error}, 使用原始值")
                                started_at = started_at_str
                except Exception as redis_error:
                    logger.debug(f"⚠️ Failed to get started_at from Redis: {redis_error}")
            
            # If still not, use the current time (a covert solution, only for new tasks)
            if not started_at:
                started_at = get_utc8_now()
                logger.info(f"📝 任务 {job_id} 创建新执行记录，开始时间: {started_at}")
            
            # Make sure started_at is in string format
            if hasattr(started_at, 'isoformat'):
                started_at_str = started_at.isoformat()
            elif isinstance(started_at, str):
                started_at_str = started_at
            else:
                started_at_str = str(started_at)
            
            # 🔥 Determine the status according to the progress: if the progress is 100%, the status should be success; otherwise, keep running
            # Note: The same logic as MongoDB is used here to ensure consistency
            redis_status = "success" if progress >= 100 else "running"
            
            progress_data = {
                "job_id": job_id,
                "progress": progress,
                "status": redis_status,  # 🔥 Use the calculated state instead of hardcoding it as running
                "started_at": started_at_str,
                "updated_at": get_utc8_now().isoformat()
            }
            # 🔥 If the execution record is found, save the execution_id to Redis (for front-end termination operation)
            if latest_execution and latest_execution.get("_id"):
                progress_data["execution_id"] = str(latest_execution["_id"])
            elif 'new_execution_id' in locals():
                # 🔥 If it is a newly created execution record, it is also saved.execution_id
                progress_data["execution_id"] = new_execution_id
            if message:
                progress_data["message"] = message
            if current_item:
                progress_data["current_item"] = current_item
            if total_items is not None:
                progress_data["total_items"] = total_items
            if processed_items is not None:
                progress_data["processed_items"] = processed_items
            
            # 🔥 If progress is 100%, add completion time
            if progress >= 100:
                progress_data["finished_at"] = get_utc8_now().isoformat()
            
            # Store in Redis, set to expire in 24 hours (will be cleaned up after the task is completed)
            progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
            try:
                redis_sync.setex(
                    progress_key,
                    86400,  # 24 hours TTL
                    json.dumps(progress_data, ensure_ascii=False)
                )
                logger.debug(f"📝 任务 {job_id} 进度已保存到Redis: {progress}%, 已处理: {processed_items}/{total_items}")
            except Exception as redis_error:
                logger.warning(f"⚠️ 任务 {job_id} 进度保存到Redis失败: {redis_error}，但不影响主流程")
            
            # Also stores state (simplified version for quick querying)
            status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)
            status_data = {
                "job_id": job_id,
                "status": redis_status,  # 🔥 Use the calculated state instead of hardcoding it as running
                "progress": progress,
                "updated_at": get_utc8_now().isoformat()
            }
            redis_sync.setex(
                status_key,
                86400,
                json.dumps(status_data, ensure_ascii=False)
            )
            
        except Exception as redis_error:
            # Redis Update failure does not affect the main process, only logs are recorded
            logger.debug(f"⚠️ Failed to update Redis cache (does not affect the main process): {redis_error}")

    except TaskCancelledException:
        # 🔥 TaskCancelledException Must be re-thrown to allow the caller to catch and stop the task
        raise
    except Exception as e:
        logger.error(f"❌ 更新任务进度失败: {e}")


async def mark_job_completed(job_id: str, stats: Optional[Dict[str, Any]] = None, error_message: Optional[str] = None):
    """
    Mark task as completed (general function)
    
    Args:
        job_id: Task ID
        stats: Synchronize statistics (optional)
        error_message: Error message (optional, mark as failed if present)
    """
    try:
        logger.info(f"✅ [任务完成] 开始标记任务 {job_id} 为已完成状态")

        # Reuse the global synchronization MongoDB singleton to avoid creating/closing independent clients every time writeback is completed.
        sync_db = get_mongo_db_sync()

        # 🔥 Improve search logic:
        # 1. Prioritize the search for running records that still have active heartbeats
        # 2. If not, look for suspended/running records within the active window (handling the case of resuming suspended tasks)
        # 3. If not, look for the success record in the active window (handling the situation where update_job_progress has updated the status first)
        # 4. If not, search for any recent status record in the pocket window
        recent_window_minutes = ACTIVE_EXECUTION_WINDOW_MINUTES
        fallback_window_minutes = FALLBACK_EXECUTION_WINDOW_MINUTES
        fallback_threshold = get_utc8_now() - timedelta(minutes=fallback_window_minutes)
        
        # 🔍 Debugging: first query all relevant records
        all_recent_records = list(sync_db.scheduler_executions.find(
            build_recent_execution_query(
                {"job_id": job_id},
                window_minutes=fallback_window_minutes
            ),
            sort=[("timestamp", -1)]
        ).limit(5))
        
        if all_recent_records:
            logger.info(f"🔍 [调试] 找到 {len(all_recent_records)} 条最近{fallback_window_minutes}分钟内的记录:")
            for idx, rec in enumerate(all_recent_records):
                logger.info(f"   [{idx+1}] _id={rec.get('_id')}, status={rec.get('status')}, timestamp={rec.get('timestamp')}, updated_at={rec.get('updated_at')}, progress={rec.get('progress')}")
        else:
            logger.warning(f"🔍 [调试] 未找到任务 {job_id} 最近{fallback_window_minutes}分钟内的任何记录")
        
        # First try to find records in the running state
        execution = sync_db.scheduler_executions.find_one(
            build_active_running_query({"job_id": job_id}),
            sort=[("timestamp", -1)]
        )
        
        # If no running record is found, try to find the most recent suspended or running record (maybe just restored)
        if not execution:
            execution = sync_db.scheduler_executions.find_one(
                build_recent_execution_query(
                    {"job_id": job_id},
                    statuses=["running", "suspended"],
                    window_minutes=recent_window_minutes
                ),
                sort=[("timestamp", -1)]
            )
            if execution:
                logger.info(f"📝 Find the most recent suspended/running record (possibly a resumed task): {execution.get('_id')}, status={execution.get('status')}")
        
        # 🔥 If not found yet, try to find the most recent success record (maybe update_job_progress has updated the status to success)
        if not execution:
            execution = sync_db.scheduler_executions.find_one(
                build_recent_execution_query(
                    {"job_id": job_id},
                    statuses=["success"],
                    window_minutes=recent_window_minutes
                ),
                sort=[("timestamp", -1)]
            )
            if execution:
                logger.info(f"📝 找到最近的 success 记录（可能是 update_job_progress 已更新状态）: {execution.get('_id')}, 将更新为最终状态")
        
        # 🔥 The final solution: Find any records in the recent window (in reverse order by timestamp, take the latest)
        if not execution:
            execution = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "$or": [
                        {"updated_at": {"$gte": fallback_threshold}},
                        {
                            "updated_at": {"$exists": False},
                            "timestamp": {"$gte": fallback_threshold}
                        }
                    ]
                },
                sort=[("timestamp", -1)]
            )
            if execution:
                logger.info(f"📝 [兜底] 找到最近{fallback_window_minutes}分钟内的记录: {execution.get('_id')}, status={execution.get('status')}, timestamp={execution.get('timestamp')}")

        if not execution:
            logger.warning(f"⚠️ 未找到任务 {job_id} 的运行记录，无法标记为已完成")
            return

        # 🔥 Modify the logic: even if there is error_message, if the success rate >= 80%, should also be marked as success
        # 🔥 Because the task has been completed (all stocks have been processed), failed items can be retried individually
        if error_message and stats:
            # Check success rate if >= 80%, Even if there are errors they should be marked as success
            success_count = stats.get("success_count", 0)
            total_processed = stats.get("total_processed", 0)
            if total_processed > 0:
                success_rate = (success_count / total_processed) * 100
                if success_rate >= 80:
                    # success rate >= 80%, Even if there are errors they should be marked as success
                    # Not handled here, let the stats branch below handle it
                    error_message = None
                    logger.info(f"✅ 任务 {job_id} 成功率 {success_rate:.1f}% >= 80%，即使有错误也标记为 success")
        
        # Determine status: If there is an error message and the success rate < 80%, marked as failed
        if error_message:
            status = "failed"
            # 🔥 If the task fails, set the progress according to the actual processing situation
            # 🔥 But if all stocks are processed, the progress should be 100%
            if stats and stats.get("total_processed", 0) > 0:
                total_processed = stats.get("total_processed", 0)
                # All stocks have been processed and the progress should be 100%
                actual_progress = 100
            else:
                # If no data is processed, the progress is set to 0 (the task failed during the initialization phase)
                actual_progress = 0
            
            update_data = {
                "status": status,
                "progress": actual_progress,
                "finished_at": get_utc8_now(),
                "updated_at": get_utc8_now(),
                "error_message": error_message[:500]  # Limit error message length
            }
            
            # 🔥 If there is processing information in stats, the relevant fields will also be updated.
            if stats:
                update_data["processed_items"] = stats.get("total_processed", 0)
                update_data["total_items"] = stats.get("total_processed", 0)
                update_data["success_count"] = stats.get("success_count", 0)
                update_data["error_count"] = stats.get("error_count", 0)
        elif stats:
            error_count = stats.get("error_count", 0)
            success_count = stats.get("success_count", 0)
            total_processed = stats.get("total_processed", 0)
            
            # 🔥 Modify logic: If all stocks are processed (regardless of success or failure), the progress should be 100%
            # 🔥 Because the task has been completed, the failed item can pass"Retry failed items"Functions are handled individually
            if total_processed > 0:
                # All stocks have been processed and the progress should be 100%
                actual_progress = 100
            else:
                # If no data is processed, the progress is 0
                actual_progress = 0
            
            # 🔥 Determine task status based on success rate (more reasonable logic)
            # - success rate >= 80%: Marked as success (partial failure is acceptable, especially for data sources with unstable network)
            # - success rate < 80% But > 0%: Marked as partial (partial success)
            # - success rate = 0%: Marked as failed (complete failure)
            if total_processed > 0:
                success_rate = (success_count / total_processed) * 100
                if success_rate >= 80:
                    status = "success"
                elif success_rate > 0:
                    status = "partial"  # Partially successful
                else:
                    status = "failed"  # complete failure
            else:
                # No data was processed, marked as failed
                status = "failed"
            
            # Calculate success rate
            success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0

            update_data = {
                "status": status,
                "progress": actual_progress,  # 🔥 Use actual calculated progress
                "finished_at": get_utc8_now(),
                "updated_at": get_utc8_now(),
                "progress_message": f"同步完成：成功 {success_count}/{total_processed} 只股票 (成功率: {success_rate:.1f}%)",
                # 🔥 Update processed_items and total_items to ensure that the front end can display correctly
                "processed_items": total_processed,  # Processed (including successful and failed)
                "total_items": total_processed,
                "success_count": success_count,  # successfully processed
                "error_count": error_count  # failed
            }

            # Add corresponding messages based on status
            if status == "success":
                if error_count > 0:
                    # success rate >= 80%, But some failed
                    error_messages = [e.get("error", "") for e in stats.get("errors", [])[:3]]  # Only take the first 3 errors
                    update_data["error_message"] = f"✅ 同步成功 (成功率: {success_rate:.1f}%)，但有 {error_count} 个股票失败: {', '.join(error_messages)}"
                    update_data["errors"] = stats.get("errors", [])
                else:
                    # 100% success
                    update_data["error_message"] = f"✅ 同步完成，所有 {success_count} 只股票均成功"
            elif status == "partial":
                # Partially successful (0% < success rate < 80%)
                failed_count = total_processed - success_count
                error_messages = [e.get("error", "") for e in stats.get("errors", [])[:3]]
                update_data["error_message"] = f"⚠️ Partially successful (success rate: {success_rate:.1f}%): success {success_count}, failed {failed_count}. Major error: {', '.join(error_messages)}"
                update_data["errors"] = stats.get("errors", [])
            elif status == "failed":
                # complete failure (success rate = 0%)
                error_messages = [e.get("error", "") for e in stats.get("errors", [])[:5]]
                update_data["error_message"] = f"❌ Sync failed:{total_processed} All stocks failed. Error: {', '.join(error_messages)}"
                update_data["errors"] = stats.get("errors", [])
        else:
            # No statistics, default marked as success
            status = "success"
            update_data = {
                "status": status,
                "progress": 100,
                "finished_at": get_utc8_now(),
                "updated_at": get_utc8_now(),
                "progress_message": "任务完成"
            }

        result = sync_db.scheduler_executions.update_one(
            {"_id": execution["_id"]},
            {"$set": update_data}
        )

        logger.info(f"✅ [任务完成] 任务 {job_id} 状态已更新为 {status}: matched={result.matched_count}, modified={result.modified_count}")

        # 🔥 Update or delete the Redis cache to ensure that the front end can obtain the latest status
        try:
            from app.core.database import get_redis_sync_client
            from app.core.redis_client import RedisKeys
            import json
            
            redis_sync = get_redis_sync_client()
            if redis_sync:
                # 🔥 Obtain complete information from the execution record to ensure that the front end can obtain all necessary fields
                started_at = execution.get("timestamp") or execution.get("scheduled_time")
                finished_at = update_data.get("finished_at") or execution.get("finished_at")
                
                # Update the progress cache (contains all fields required by the front end)
                progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                progress_data = {
                    "job_id": job_id,
                    "progress": update_data.get("progress", 100),
                    "status": status,
                    "updated_at": get_utc8_now().isoformat(),
                    "started_at": started_at.isoformat() if started_at and hasattr(started_at, 'isoformat') else (str(started_at) if started_at else None)
                }
                if finished_at:
                    progress_data["finished_at"] = finished_at.isoformat() if hasattr(finished_at, 'isoformat') else str(finished_at)
                if update_data.get("progress_message"):
                    progress_data["message"] = update_data["progress_message"]
                if execution.get("current_item"):
                    progress_data["current_item"] = execution.get("current_item")
                
                # 🔥 The information in stats will be used first, if not, the information in execution will be used.
                if stats:
                    total_processed = stats.get("total_processed", 0)
                    success_count = stats.get("success_count", 0)
                    if total_processed > 0:
                        progress_data["total_items"] = total_processed
                        # processed_items should be processed (including success and failure), used here total_processed
                        # But actually the front end may need success_count, so we provide both
                        progress_data["processed_items"] = total_processed  # Processed (including successful and failed)
                        progress_data["success_count"] = success_count  # successfully processed
                else:
                    # If stats are not available, use information from execution
                    if execution.get("total_items"):
                        progress_data["total_items"] = execution.get("total_items")
                    if execution.get("processed_items") is not None:
                        progress_data["processed_items"] = execution.get("processed_items")
                
                redis_sync.setex(
                    progress_key,
                    86400,  # 24 hours TTL
                    json.dumps(progress_data, ensure_ascii=False, default=str)
                )
                
                # Update status cache
                status_key = RedisKeys.SCHEDULER_JOB_STATUS.format(job_id=job_id)
                status_data = {
                    "job_id": job_id,
                    "status": status,
                    "progress": update_data.get("progress", 100),
                    "updated_at": get_utc8_now().isoformat()
                }
                redis_sync.setex(
                    status_key,
                    86400,
                    json.dumps(status_data, ensure_ascii=False, default=str)
                )
                
                logger.info(f"✅ [Mission accomplished] Redis cache updated: job_id={job_id}, status={status}, progress={update_data.get('progress', 100)}")
        except Exception as redis_error:
            logger.warning(f"⚠️ Failed to update Redis cache (does not affect the main process): {redis_error}")

    except Exception as e:
        logger.error(f"❌ 标记任务完成失败: {e}", exc_info=True)

