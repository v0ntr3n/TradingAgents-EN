"""
Enhanced version of queue service
Based on the existing implementation, add concurrency control, priority queue, visibility timeout and other functions
"""

import json
import time
import uuid
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from redis.asyncio import Redis

from app.core.database import get_redis_client

from app.services.queue import (
    READY_LIST,
    TASK_PREFIX,
    BATCH_PREFIX,
    SET_PROCESSING,
    SET_COMPLETED,
    SET_FAILED,
    BATCH_TASKS_PREFIX,
    USER_PROCESSING_PREFIX,
    GLOBAL_CONCURRENT_KEY,
    VISIBILITY_TIMEOUT_PREFIX,
    DEFAULT_USER_CONCURRENT_LIMIT,
    GLOBAL_CONCURRENT_LIMIT,
    VISIBILITY_TIMEOUT_SECONDS,
    check_user_concurrent_limit,
    check_global_concurrent_limit,
    mark_task_processing,
    unmark_task_processing,
    set_visibility_timeout,
    clear_visibility_timeout,
)

logger = logging.getLogger(__name__)

# Redis Key names and configuration constants are provided by app.services.queue.keys (not repeated here)


class QueueService:
    """增强版队列服务类"""

    def __init__(self, redis: Redis):
        self.r = redis
        self.user_concurrent_limit = DEFAULT_USER_CONCURRENT_LIMIT
        self.global_concurrent_limit = GLOBAL_CONCURRENT_LIMIT
        self.visibility_timeout = VISIBILITY_TIMEOUT_SECONDS

    def _clean_params_for_json(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Clean parameters and convert non-serializable objects to serializable format
        
        Args:
            params: Original parameter dictionary
            
        Returns:
            Cleaned parameter dictionary
        """
        cleaned = {}
        for key, value in params.items():
            try:
                if value is None:
                    cleaned[key] = None
                elif isinstance(value, (str, int, float, bool)):
                    # Basic types are retained directly
                    cleaned[key] = value
                elif isinstance(value, datetime):
                    # Convert datetime to ISO format string
                    cleaned[key] = value.isoformat()
                elif isinstance(value, dict):
                    # Recursively process nested dictionaries
                    cleaned[key] = self._clean_params_for_json(value)
                elif isinstance(value, (list, tuple)):
                    # Working with lists and tuples
                    cleaned[key] = [
                        self._clean_single_value(item) for item in value
                    ]
                elif hasattr(value, 'model_dump'):
                    # Pydantic v2 model
                    cleaned[key] = self._clean_params_for_json(value.model_dump())
                elif hasattr(value, 'dict'):
                    # Pydantic v1 model
                    cleaned[key] = self._clean_params_for_json(value.dict())
                elif hasattr(value, '__dict__'):
                    # Other objects, try converting to dictionary
                    try:
                        cleaned[key] = self._clean_params_for_json(value.__dict__)
                    except Exception:
                        cleaned[key] = str(value)
                else:
                    # Other types attempt JSON serialization and convert to string if that fails
                    try:
                        json.dumps(value)  # Test whether it can be serialized
                        cleaned[key] = value
                    except (TypeError, ValueError):
                        cleaned[key] = str(value)
            except Exception as e:
                # If processing fails, log a warning and use a string representation
                logger.warning(f"清理参数 {key} 时出错: {e}, 使用字符串表示")
                cleaned[key] = str(value)
        return cleaned
    
    def _clean_single_value(self, value: Any) -> Any:
        """清理单个值"""
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return self._clean_params_for_json(value)
        elif isinstance(value, (list, tuple)):
            return [self._clean_single_value(item) for item in value]
        elif hasattr(value, 'model_dump'):
            return self._clean_params_for_json(value.model_dump())
        elif hasattr(value, 'dict'):
            return self._clean_params_for_json(value.dict())
        else:
            try:
                json.dumps(value)
                return value
            except (TypeError, ValueError):
                return str(value)

    async def enqueue_task(
        self,
        user_id: str,
        symbol: str,
        params: Dict[str, Any],
        batch_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> str:
        """Task enqueue (FIFO queue, no limit on submission concurrency, worker controls processing concurrency)

        Args:
            user_id: User ID
            symbol: Stock code
            params: Task parameters
            batch_id: Batch ID (optional)
            task_id: Task ID (optional, automatically generated if not provided)
        """

        # Comment out the concurrency limit check on submission - let the task be queued
        # Concurrency control is handled by Worker at dequeue_task time
        # if not await self._check_user_concurrent_limit(user_id):
        #     raise ValueError(f"User {user_id} Concurrency limit reached ({self.user_concurrent_limit})")
        # if not await self._check_global_concurrent_limit():
        #     raise ValueError(f"The system reaches the global concurrency limit ({self.global_concurrent_limit})")

        # If task_id is not provided, a new one is generated
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        key = TASK_PREFIX + task_id
        now = int(time.time())

        # 🔥 Clean parameters and convert non-serializable objects to serializable format
        cleaned_params = self._clean_params_for_json(params or {})
        
        mapping = {
            "id": task_id,
            "user": user_id,
            "symbol": symbol,
            "status": "queued",
            "created_at": str(now),
            "params": json.dumps(cleaned_params),
            "enqueued_at": str(now)
        }

        if batch_id:
            mapping["batch_id"] = batch_id

        # Save task data
        await self.r.hset(key, mapping=mapping)

        # Add to FIFO queue
        await self.r.lpush(READY_LIST, task_id)

        if batch_id:
            await self.r.sadd(BATCH_TASKS_PREFIX + batch_id, task_id)

        logger.info(f"任务已入队: {task_id}")
        return task_id

    async def dequeue_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """从FIFO队列中取出任务"""
        try:
            # Get tasks from FIFO queue
            task_id = await self.r.rpop(READY_LIST)
            if not task_id:
                return None

            # Get task details
            task_data = await self.get_task(task_id)
            if not task_data:
                logger.warning(f"任务数据不存在: {task_id}")
                return None

            user_id = task_data.get("user")

            # Concurrency limit check when dequeue is commented out - lets the Worker handle all queued tasks
            # Worker The concurrency control is implemented by semaphore, not the user concurrency limit here
            # if not await self._check_user_concurrent_limit(user_id):
            #     await self.r.lpush(READY_LIST, task_id)
            #     logger.warning(f"User {user_id} Concurrency limit, task requeue: {task_id}")
            #     return None

            # Mark task as in progress
            await self._mark_task_processing(task_id, user_id, worker_id)

            # Set visibility timeout
            await self._set_visibility_timeout(task_id, worker_id)

            # Update task status
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "processing",
                "worker_id": worker_id,
                "started_at": str(int(time.time()))
            })

            logger.info(f"任务已出队: {task_id} -> Worker: {worker_id}")
            return task_data

        except Exception as e:
            logger.error(f"出队失败: {e}")
            return None

    async def ack_task(self, task_id: str, success: bool = True) -> bool:
        """确认任务完成"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return False

            user_id = task_data.get("user")
            worker_id = task_data.get("worker_id")

            # Remove from processing collection
            await self._unmark_task_processing(task_id, user_id)

            # Clear visibility timeout
            await self._clear_visibility_timeout(task_id)

            # Update task status
            status = "completed" if success else "failed"
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": status,
                "completed_at": str(int(time.time()))
            })

            # Add to corresponding collection
            if success:
                await self.r.sadd(SET_COMPLETED, task_id)
            else:
                await self.r.sadd(SET_FAILED, task_id)

            logger.info(f"任务已确认: {task_id} (成功: {success})")
            return True

        except Exception as e:
            logger.error(f"确认任务失败: {e}")
            return False

    async def create_batch(self, user_id: str, symbols: List[str], params: Dict[str, Any]) -> tuple[str, int]:
        batch_id = str(uuid.uuid4())
        now = int(time.time())
        batch_key = BATCH_PREFIX + batch_id
        await self.r.hset(batch_key, mapping={
            "id": batch_id,
            "user": user_id,
            "status": "queued",
            "submitted": str(len(symbols)),
            "created_at": str(now),
        })
        for s in symbols:
            await self.enqueue_task(user_id=user_id, symbol=s, params=params, batch_id=batch_id)
        return batch_id, len(symbols)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        key = TASK_PREFIX + task_id
        data = await self.r.hgetall(key)
        if not data:
            return None
        # parse fields
        if "params" in data:
            try:
                data["parameters"] = json.loads(data.pop("params"))
            except Exception:
                data["parameters"] = {}
        if "created_at" in data and data["created_at"].isdigit():
            data["created_at"] = int(data["created_at"])
        if "submitted" in data and str(data["submitted"]).isdigit():
            data["submitted"] = int(data["submitted"])
        return data

    async def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        key = BATCH_PREFIX + batch_id
        data = await self.r.hgetall(key)
        if not data:
            return None
        # enrich with tasks count if set exists
        submitted = data.get("submitted")
        if submitted is not None and str(submitted).isdigit():
            data["submitted"] = int(submitted)
        if "created_at" in data and data["created_at"].isdigit():
            data["created_at"] = int(data["created_at"])
        data["tasks"] = list(await self.r.smembers(BATCH_TASKS_PREFIX + batch_id))
        return data

    async def stats(self) -> Dict[str, int]:
        queued = await self.r.llen(READY_LIST)
        processing = await self.r.scard(SET_PROCESSING)
        completed = await self.r.scard(SET_COMPLETED)
        failed = await self.r.scard(SET_FAILED)
        return {
            "queued": int(queued or 0),
            "processing": int(processing or 0),
            "completed": int(completed or 0),
            "failed": int(failed or 0),
        }

    # New: Concurrency control methods
    async def _check_user_concurrent_limit(self, user_id: str) -> bool:
        """Check user concurrency limits (delegate helpers)"""
        return await check_user_concurrent_limit(self.r, user_id, self.user_concurrent_limit)

    async def _check_global_concurrent_limit(self) -> bool:
        """Check global concurrency limits (delegate helpers)"""
        return await check_global_concurrent_limit(self.r, self.global_concurrent_limit)

    async def _mark_task_processing(self, task_id: str, user_id: str, worker_id: str):
        """Mark a task as being processed (delegate helpers)"""
        await mark_task_processing(self.r, task_id, user_id)

    async def _unmark_task_processing(self, task_id: str, user_id: str):
        """Cancel the task processing mark (delegate helpers)"""
        await unmark_task_processing(self.r, task_id, user_id)

    async def _set_visibility_timeout(self, task_id: str, worker_id: str):
        """Set visibility timeout (delegate helpers)"""
        await set_visibility_timeout(self.r, task_id, worker_id, self.visibility_timeout)

    async def _clear_visibility_timeout(self, task_id: str):
        """清除可见性超时"""
        await clear_visibility_timeout(self.r, task_id)

    async def get_user_queue_status(self, user_id: str) -> Dict[str, int]:
        """获取用户队列状态"""
        user_processing_key = USER_PROCESSING_PREFIX + user_id
        processing_count = await self.r.scard(user_processing_key)

        return {
            "processing": int(processing_count or 0),
            "concurrent_limit": self.user_concurrent_limit,
            "available_slots": max(0, self.user_concurrent_limit - int(processing_count or 0))
        }

    async def cleanup_expired_tasks(self):
        """Clean up expired tasks (visibility timeout)"""
        try:
            # Get all visibility timeout keys
            timeout_keys = await self.r.keys(VISIBILITY_TIMEOUT_PREFIX + "*")

            current_time = int(time.time())
            expired_tasks = []

            for timeout_key in timeout_keys:
                timeout_data = await self.r.hgetall(timeout_key)
                if timeout_data:
                    timeout_at = int(timeout_data.get("timeout_at", 0))
                    if current_time > timeout_at:
                        task_id = timeout_data.get("task_id")
                        if task_id:
                            expired_tasks.append(task_id)

            # Handle overdue tasks
            for task_id in expired_tasks:
                await self._handle_expired_task(task_id)

            if expired_tasks:
                logger.warning(f"处理了 {len(expired_tasks)} 个过期任务")

        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")

    async def _handle_expired_task(self, task_id: str):
        """处理过期任务"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return

            user_id = task_data.get("user")

            # Remove from processing collection
            await self._unmark_task_processing(task_id, user_id)

            # Clear visibility timeout
            await self._clear_visibility_timeout(task_id)

            # rejoin queue
            await self.r.lpush(READY_LIST, task_id)

            # Update task status
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "queued",
                "worker_id": "",
                "requeued_at": str(int(time.time()))
            })

            logger.warning(f"过期任务重新入队: {task_id}")

        except Exception as e:
            logger.error(f"处理过期任务失败: {task_id} - {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return False

            status = task_data.get("status")
            user_id = task_data.get("user")

            if status == "processing":
                # If it is being processed, remove it from the processing collection
                await self._unmark_task_processing(task_id, user_id)
                await self._clear_visibility_timeout(task_id)
            elif status == "queued":
                # If in queue, remove from queue
                await self.r.lrem(READY_LIST, 0, task_id)

            # Update task status
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "cancelled",
                "cancelled_at": str(int(time.time()))
            })

            logger.info(f"任务已取消: {task_id}")
            return True

        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False


def get_queue_service() -> QueueService:
    return QueueService(get_redis_client())