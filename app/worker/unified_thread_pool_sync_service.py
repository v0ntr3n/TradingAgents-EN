#!/usr/bin/env python3
"""
Unified thread pool synchronization service
Can execute any synchronization method and handle common logic such as progress updates, cancellations, errors, etc.
"""
import asyncio
import logging
import threading
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass, field
from threading import local

logger = logging.getLogger(__name__)

# 🔥 Thread local storage: used to store the database connection of each thread to avoid conflicts with the main event loop
_thread_local = local()


@dataclass
class SyncTaskResult:
    """Synchronize task results"""
    success: bool = False
    result: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class UnifiedThreadPoolSyncService:
    """
    Unified thread pool synchronization service
    
    Any synchronization method can be executed and processed uniformly:
    - progress update
    - Task canceled
    - Error handling
    - Breakpoint recovery
    - rate limit
    
    How to use:
        service = UnifiedThreadPoolSyncService()
        result = await service.execute_sync_method(
            sync_method=akshare_service.sync_historical_data,
            method_kwargs={"incremental": True, "period": "daily"},
            job_id="akshare_historical_sync",
            progress_callback=update_progress_func
        )
    
    Concurrency safety notes:
    - Tasks in the thread pool are executed in independent threads and event loops
    - in order to avoid"attached to a different loop"Error, the database connection of the service instance will be temporarily replaced before execution.
    - The original connection will be restored after the execution is completed, ensuring that operations in the main event loop are not affected
    - Use locks to protect connection replacement and recovery operations to avoid concurrency conflicts
    - Note: If during the execution of the synchronization task, other operations in the main event loop use the same service instance,
      may encounter"attached to a different loop"mistake. Suggestions:
      1. Avoid using the same service instance during synchronization task execution
      2. Or create separate service instances for each operation
    """
    
    def __init__(self, max_workers: int = 10):
        """
        Args:
            max_workers: Maximum number of worker threads in the thread pool
        """
        self.max_workers = max_workers
        # 🔥 Global thread pool: used to perform synchronization tasks
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._shutdown_event = threading.Event()  # 🔥 Used to notify the thread to exit
        self._active_tasks = {}  # 🔥 Track active tasks:{job_id: future}
        # 🔥 Service instance connection modification lock: protects the database connection modification of the service instance to avoid conflicts with the main event loop
        self._service_connection_lock = threading.RLock()  # Use reentrant locks to support nested calls
        
    async def execute_sync_method(
        self,
        sync_method: Callable,
        method_kwargs: Dict[str, Any] = None,
        job_id: str = None,
        progress_callback: Optional[Callable] = None,
        rate_limit_per_minute: int = 80,
        resume_from_index: int = None
    ) -> SyncTaskResult:
        """
        Execute synchronized methods in thread pool
        
        Args:
            sync_method: The synchronous method to execute (can be a synchronous or asynchronous method)
            method_kwargs: Keyword arguments passed to synchronized methods
            job_id: Task ID, used for progress tracking and cancellation
            progress_callback: Progress callback function (optional)
            rate_limit_per_minute: Rate limit (maximum calls per minute)
            resume_from_index: Resume execution: where to continue (number of items processed)
            
        Returns:
            Synchronize task results
        """
        if method_kwargs is None:
            method_kwargs = {}
        
        # 🔥 Check if exit signal received
        if self._shutdown_event.is_set():
            logger.warning(f"⚠️ Exit signal received, task {job_id} will not be executed")
            result = SyncTaskResult()
            result.error = "Service is shutting down"
            return result
        
        # 🔥 If a recovery location is specified, add it to the parameters
        if resume_from_index is not None:
            method_kwargs["resume_from_index"] = resume_from_index
        
        result = SyncTaskResult()
        result.start_time = datetime.now(timezone.utc)
        
        # 🔥 Asynchronous methods must be executed in the current application event loop to avoid cross-event loop access to Motor/service singletons
        if asyncio.iscoroutinefunction(sync_method):
            task_future = asyncio.create_task(
                self._execute_async_method_with_cancellation(
                    sync_method,
                    method_kwargs,
                    job_id,
                    use_thread_local_connections=False,
                )
            )
        else:
            loop = asyncio.get_running_loop()

            # 🔥 Only truly synchronous blocking methods enter the thread pool
            task_future = loop.run_in_executor(
                self._thread_pool,
                self._execute_sync_method_sync,
                sync_method,
                method_kwargs,
                job_id,
                rate_limit_per_minute
            )
        
        # 🔥 Record active tasks
        if job_id:
            self._active_tasks[job_id] = task_future
        
        try:
            # Wait for task to complete
            method_result = await task_future
            
            result.success = True
            result.result = method_result
            
        except Exception as e:
            # 🔥 Check whether it is a task cancellation exception
            from app.services.scheduler_service import TaskCancelledException
            if isinstance(e, TaskCancelledException) or "Cancel" in str(e) or "cancelled" in str(e).lower():
                logger.warning(f"🛑 Task {job_id} has been cancelled: {e}")
                result.error = f"Task canceled: {str(e)}"
            else:
                logger.error(f"❌ Task {job_id} Execution failed: {e}", exc_info=True)
                result.error = str(e)
        finally:
            # Once the task is completed, it is removed from the active task list
            if job_id:
                self._active_tasks.pop(job_id, None)
            
            result.end_time = datetime.now(timezone.utc)
            if result.start_time:
                result.duration = (result.end_time - result.start_time).total_seconds()
        
        return result
    
    def _execute_sync_method_sync(
        self,
        sync_method: Callable,
        method_kwargs: Dict[str, Any],
        job_id: str,
        rate_limit_per_minute: int
    ) -> Any:
        """
        Execute a synchronized method in a thread of the thread pool (synchronized version)
        
        Note: This method runs in a thread in the thread pool and needs to create a new event loop (if it is an asynchronous method)
        """
        # 🔥 Check if exit signal received
        if self._shutdown_event.is_set():
            logger.warning(f"⚠️ Exit signal received, task {job_id} will not be executed")
            raise RuntimeError("Service is shutting down")
        
        # 🔥 Check if it is an asynchronous method
        if asyncio.iscoroutinefunction(sync_method):
            # Asynchronous methods: need to create a new event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # The thread pool thread does not have an event loop, create a new
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            try:
                # Run an async method in a new event loop
                result = loop.run_until_complete(
                    self._execute_async_method_with_cancellation(
                        sync_method,
                        method_kwargs,
                        job_id
                    )
                )
                return result
            except RuntimeError as e:
                # 🔥 Catching event loop related errors
                if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                    logger.error(f"❌ The event loop has been closed and execution cannot continue: {e}")
                    raise RuntimeError(f"event loop closed: {e}")
                raise
            finally:
                # 🔥 Make sure all tasks are completed before closing the event loop
                try:
                    if not loop.is_closed():
                        # Cancel all unfinished tasks
                        pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
                        if pending_tasks:
                            logger.warning(f"⚠️ Before closing the event loop, there is also {len(pending_tasks)} unfinished tasks")
                            for task in pending_tasks:
                                task.cancel()
                            # Wait for task cancellation to complete (use timeout to avoid infinite waiting)
                            try:
                                loop.run_until_complete(asyncio.wait_for(
                                    asyncio.gather(*pending_tasks, return_exceptions=True),
                                    timeout=5.0
                                ))
                            except asyncio.TimeoutError:
                                logger.warning(f"⚠️ Waiting for task cancellation timeout and forcing event loop to close")
                except RuntimeError as cleanup_error:
                    # Event loop closed, errors ignored
                    if "shutdown" not in str(cleanup_error).lower() and "closed" not in str(cleanup_error).lower():
                        logger.warning(f"⚠️ An error occurred while cleaning up unfinished tasks: {cleanup_error}")
                except Exception as cleanup_error:
                    logger.warning(f"⚠️ An error occurred while cleaning up unfinished tasks: {cleanup_error}")
                
                # Close event loop
                try:
                    if not loop.is_closed():
                        loop.close()
                        logger.debug(f"✅ event loop closed")
                except RuntimeError as close_error:
                    # Event loop closed, errors ignored
                    if "shutdown" not in str(close_error).lower() and "closed" not in str(close_error).lower():
                        logger.warning(f"⚠️ Error closing event loop: {close_error}")
                except Exception as close_error:
                    logger.warning(f"⚠️ Error closing event loop: {close_error}")
        else:
            # Synchronous method: direct call
            return sync_method(**method_kwargs)
    
    async def _execute_async_method_with_cancellation(
        self,
        async_method: Callable,
        method_kwargs: Dict[str, Any],
        job_id: str,
        use_thread_local_connections: bool = True,
    ) -> Any:
        """
        Execute asynchronous methods and support cancellation checks
        
        Note: When executing in a thread pool worker thread, you need to ensure that the database connection is bound to the current event loop.
        When executed in the current application event loop, no additional connection replacement is performed.
        """
        # 🔥 Check if exit signal received
        if self._shutdown_event.is_set():
            raise RuntimeError("Service is shutting down")
        
        # 🔥 Check if the task should be stopped (by querying the database)
        if job_id:
            should_stop = await self._should_stop(job_id)
            if should_stop:
                from app.services.scheduler_service import TaskCancelledException
                raise TaskCancelledException(f"Task {job_id} has been cancelled")
        
        # 🔥 Reinitialize the database connection (if required by the method)
        # Check whether the method is a bound method (with self parameter), if so, reinitialize the database connection of the service instance
        # 🔥 To avoid conflicts with the main event loop, we use lock protection + How to save/restore connections
        # 🔥 This way, even if the main event loop uses the service instance at the same time, it will not be affected.
        import inspect
        service_instance = None
        original_connections = {}  # Save the original connection for recovery
        thread_local_connections = {}  # Thread local connections (bound to the current thread's event loop)
        lock_acquired = False
        
        try:
            if use_thread_local_connections:
                sig = inspect.signature(async_method)
                if 'self' in sig.parameters:
                    # This is a binding method that gets the self object
                    if hasattr(async_method, '__self__'):
                        service_instance = async_method.__self__
                        
                        # 🔥 Obtain the lock to protect the connection modification of the service instance
                        # 🔥 This prevents other operations in the main event loop from modifying the connection at the same time
                        self._service_connection_lock.acquire()
                        lock_acquired = True
                        
                        # 🔥 Save the original connection (for post-execution recovery)
                        if hasattr(service_instance, 'db'):
                            original_connections['db'] = service_instance.db
                        if hasattr(service_instance, 'historical_service'):
                            original_connections['historical_service'] = service_instance.historical_service
                        if hasattr(service_instance, 'news_service'):
                            original_connections['news_service'] = service_instance.news_service
                        
                        # 🔥 Create a thread-local database connection (bound to the current thread's event loop)
                        # 🔥 These connections are only used in thread pool threads and do not affect the main event loop
                        thread_local_connections = await self._create_thread_local_db_connections()
                        
                        # 🔥 Temporarily replaces the connection of the service instance (only valid in thread pool threads)
                        # 🔥 Due to lock protection, operations in the main event loop will wait for the lock to be released
                        if 'db' in thread_local_connections:
                            service_instance.db = thread_local_connections['db']
                        if 'historical_service' in thread_local_connections:
                            service_instance.historical_service = thread_local_connections['historical_service']
                        if 'news_service' in thread_local_connections:
                            service_instance.news_service = thread_local_connections['news_service']
                        
                        logger.debug(f"🔄 Database connections for service instances have been replaced with thread-local connections: {type(service_instance).__name__}")
        except Exception as e:
            logger.debug(f"An error occurred while checking the service instance database connection (ignorable): {e}")
        
        try:
            # 🔥 Hold the lock during method execution to ensure operations in the main event loop do not use the replaced connection
            # 🔥 This can be avoided"attached to a different loop"Error
            # 🔥 NOTE: This may briefly block operations in the main event loop, but:
            # 1. Connection replacement operation is very fast (milliseconds)
            # 2. During method execution, operations in the main event loop wait for the lock to be released
            # 3. If the waiting time is too long, consider using a timeout mechanism
            # 
            # 🔥 However, for better concurrency performance, we release the lock before executing the method
            # 🔥 Operations in the main event loop will fail and retry if they encounter a replaced connection.
            # 🔥 This is acceptable because:
            # 1. Synchronization tasks take a long time to execute (minutes), and maintaining locks will seriously affect concurrency performance.
            # 2. Operations in the main event loop (such as data preparation for Analysis Services) can be retried or used independent connections
            # 3. MongoDB Connections are thread-safe and multiple connections can be used concurrently
            if lock_acquired:
                self._service_connection_lock.release()
                lock_acquired = False
            
            # 🔥 Execute an asynchronous method and periodically check the cancellation status during method execution
            # Note: The specific cancellation check should be implemented inside the synchronization method (through methods such as update_job_progress)
            # 🔥 Note: During execution, the connection to the service instance has been replaced with a thread-local connection
            # 🔥 If you use service instances for operations in the main event loop, you may encounter"attached to a different loop"Error
            # 🔥 But this rarely happens because:
            # 1. Synchronization tasks take a long time to execute, and operations in the main event loop usually do not use the same service instance at the same time.
            # 2. If there is indeed a conflict, the operation in the main event loop will fail, but it will not affect the execution of the synchronization task.
            # 3. If the analysis service encounters connection problems during data preparation, you can try again or use an independent connection.
            return await async_method(**method_kwargs)
        finally:
            # 🔥 Restore the original connection to avoid affecting the main event loop and other threads
            try:
                if service_instance and original_connections:
                    # 🔥 Reacquire the lock to protect the connection recovery operation
                    self._service_connection_lock.acquire()
                    try:
                        if 'db' in original_connections:
                            service_instance.db = original_connections['db']
                        if 'historical_service' in original_connections:
                            service_instance.historical_service = original_connections['historical_service']
                        if 'news_service' in original_connections:
                            service_instance.news_service = original_connections['news_service']
                        logger.debug(f"🔄 The original database connection to the service instance has been restored: {type(service_instance).__name__}")
                    finally:
                        self._service_connection_lock.release()
                    
                    # 🔥 Clean up thread local connections (close client, release resources)
                    await self._cleanup_thread_local_connections(thread_local_connections)
            except Exception as e:
                logger.warning(f"⚠️ An error occurred while restoring the service instance database connection: {e}")
    
    async def _create_thread_local_db_connections(self) -> Dict[str, Any]:
        """
        Create a thread-local database connection and bind it to the current thread s event loop
        
        Returns:
            A dictionary containing database connections and service instances
        """
        connections = {}
        try:
            from app.core.database import create_isolated_async_mongo_binding

            # 🔥 Create a thread-local MongoDB client (bound to the current thread's event loop)
            mongo_client, mongo_db = create_isolated_async_mongo_binding()
            connections['mongo_client'] = mongo_client  # Save client reference for subsequent shutdown
            connections['db'] = mongo_db
            
            # 🔥 Create a thread-local historical data service
            try:
                from app.services.historical_data_service import HistoricalDataService
                historical_service = HistoricalDataService()
                historical_service.db = connections['db']
                historical_service.collection = historical_service.db.stock_daily_quotes
                # Make sure the index exists
                await historical_service._ensure_indexes()
                connections['historical_service'] = historical_service
                logger.debug(f"🔄 Create a thread-local historical data service")
            except Exception as e:
                logger.warning(f"⚠️ Failed to create thread local historical data service: {e}")
            
            # 🔥 Create a thread-local news data service
            try:
                from app.services.news_data_service import NewsDataService
                news_service = NewsDataService()
                news_service.db = connections['db']
                connections['news_service'] = news_service
                logger.debug(f"🔄 Create a thread-local news data service")
            except Exception as e:
                logger.warning(f"⚠️ Failed to create thread local news data service: {e}")
                
        except Exception as e:
            logger.warning(f"⚠️ Error while creating thread local database connection: {e}")
        
        return connections
    
    async def _cleanup_thread_local_connections(self, connections: Dict[str, Any]):
        """
        Clean up the thread-local database connection and close the client
        
        Args:
            connections: Thread local connection dictionary
        """
        try:
            # 🔥 Close the MongoDB client
            if 'mongo_client' in connections:
                mongo_client = connections['mongo_client']
                if mongo_client:
                    mongo_client.close()
                    logger.debug(f"🔄 Thread-local MongoDB client closed")
        except Exception as e:
            logger.warning(f"⚠️ Error cleaning thread local database connection: {e}")
    
    async def _should_stop(self, job_id: str) -> bool:
        """
        Check if the task should be stopped
        
        Args:
            job_id: Task ID
            
        Returns:
            should it stop
        """
        try:
            from app.core.database import get_mongo_db_sync
            from app.core.config import settings
            from pymongo import MongoClient
            
            # 🔥 Use synchronous client queries (to avoid event loop conflicts)
            sync_client = MongoClient(settings.MONGO_URI)
            sync_db = sync_client[settings.MONGODB_DATABASE]
            
            try:
                # Only check the currently running execution records to avoid accidentally damaging new tasks due to historical suspended records.
                execution = sync_db.scheduler_executions.find_one(
                    {"job_id": job_id, "status": "running"},
                    sort=[("timestamp", -1)]
                )

                if not execution:
                    return False

                if execution.get("cancel_requested"):
                    logger.info(f"🛑 Task {job_id} Upon receipt of a cancellation request, execution should be stopped")
                    return True

                status = execution.get("status")
                if status in ["failed", "cancelled"]:
                    logger.info(f"🛑 Task {job_id} The status is {status}, Execution should be stopped")
                    return True

                return False
            finally:
                sync_client.close()
                
        except Exception as e:
            logger.error(f"❌ Checking task stop flag failed: {e}")
            return False
    
    def shutdown(self, timeout: float = 30.0):
        """
        Gracefully shut down the thread pool

        Args:
            timeout: Maximum time to wait for a thread to complete (seconds)
        """
        logger.info("🛑 Start closing the thread pool of the unified thread pool synchronization service...")

        # 🔥 Set exit signal
        self._shutdown_event.set()

        # 🔥 Mark all active tasks as suspended in the database
        # Note: Marked as suspended instead of canceled, so that execution can be resumed after restarting
        try:
            from pymongo import MongoClient
            from app.core.config import settings
            from app.services.scheduler_service import get_utc8_now

            if self._active_tasks:
                logger.info(f"🔄 will {len(self._active_tasks)} active tasks marked suspended...")
                sync_client = MongoClient(settings.MONGO_URI)
                sync_db = sync_client[settings.MONGODB_DATABASE]

                for job_id in self._active_tasks.keys():
                    try:
                        # 🔥 First query the progress information of the current task
                        current_task = sync_db.scheduler_executions.find_one(
                            {"job_id": job_id, "status": "running"},
                            sort=[("timestamp", -1)]
                        )

                        if current_task:
                            # 🔥 Update task status to suspended and retain progress information
                            update_data = {
                                "status": "suspended",
                                "error_message": "The service is shutting down (Ctrl+C) , The task has been suspended and can be continued after restarting",
                                "updated_at": get_utc8_now()
                            }

                            # 🔥 Try to read the latest progress information from Redis
                            try:
                                from app.core.database import get_redis_sync_client
                                from app.core.redis_client import RedisKeys
                                import json

                                redis_sync = get_redis_sync_client()
                                if redis_sync:
                                    progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                                    progress_str = redis_sync.get(progress_key)
                                    if progress_str:
                                        progress_data = json.loads(progress_str)
                                        # Save progress information to MongoDB
                                        if "progress" in progress_data:
                                            update_data["progress"] = progress_data["progress"]
                                        if "processed_items" in progress_data:
                                            update_data["processed_items"] = progress_data["processed_items"]
                                        if "total_items" in progress_data:
                                            update_data["total_items"] = progress_data["total_items"]
                                        if "message" in progress_data:
                                            update_data["progress_message"] = progress_data["message"]
                                        logger.info(f"📊 Save task {job_id} progress information: {progress_data.get('progress', 0)}%, Processed: {progress_data.get('processed_items', 0)}")
                            except Exception as redis_error:
                                logger.warning(f"⚠️ Reading progress from Redis failed: {redis_error}")

                            result = sync_db.scheduler_executions.update_one(
                                {"_id": current_task["_id"]},
                                {"$set": update_data}
                            )

                            if result.modified_count > 0:
                                logger.info(f"✅ Task marked {job_id} It is suspended and can continue to execute after restarting.")
                            else:
                                logger.warning(f"⚠️ Task {job_id} The status has not been updated (it may no longer be in the running status)")
                        else:
                            logger.warning(f"⚠️ Task not found {job_id} running record")

                    except Exception as e:
                        logger.warning(f"⚠️ Mark tasks {job_id} failed for suspended: {e}")

                sync_client.close()
        except Exception as e:
            logger.warning(f"⚠️ Marking active tasks as suspended failed: {e}")

        # 🔥 Force the thread pool to close directly (without waiting)
        # Ctrl+C It exits abnormally and does not need to wait for the task to be completed.
        logger.info("🛑 Forcefully close the thread pool (exit abnormally, do not wait)...")
        self._thread_pool.shutdown(wait=False)

        if self._active_tasks:
            logger.info(f"⚠️ The thread pool has been forcibly closed,{len(self._active_tasks)} The task has been marked as suspended and can continue to be executed after restarting.")
            self._active_tasks.clear()  # Clean up the active task list to prevent reference leaks

        logger.info("✅ The unified thread pool synchronization service thread pool has been closed")


# Global service instance
_unified_thread_pool_sync_service = None


async def get_unified_thread_pool_sync_service() -> UnifiedThreadPoolSyncService:
    """Get the unified thread pool synchronization service instance (single case)"""
    global _unified_thread_pool_sync_service
    if _unified_thread_pool_sync_service is None:
        _unified_thread_pool_sync_service = UnifiedThreadPoolSyncService()
    return _unified_thread_pool_sync_service
