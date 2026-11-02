from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['thread_pool_sync_service', 'unified_thread_pool_sync_service', 'unified_historical_sync_service', 'multi_period_sync_service']:
    _sys.modules[f"app.worker.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === thread_pool_sync_service.py ===
#!/usr/bin/env python3
"""
Data synchronization service based on thread pool

Provides true multi-threaded parallel processing capabilities and solves the problem that coroutine concurrency may get stuck.
"""
import asyncio
import logging
import threading
import queue
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from collections import defaultdict

logger = logging.getLogger(__name__)


class CancellationToken:
    """
    Thread-safe cancellation token
    """
    
    def __init__(self):
        self._cancelled = False
        self._lock = threading.Lock()
    
    def cancel(self):
        """Cancel task"""
        with self._lock:
            self._cancelled = True
            logger.info("🛑 Task cancellation token has been set")
    
    def is_cancelled(self) -> bool:
        """Check if canceled"""
        with self._lock:
            return self._cancelled
    
    def reset(self):
        """Reset (for starting over)"""
        with self._lock:
            self._cancelled = False


@dataclass
class SyncStats:
    """Sync statistics"""
    total_items: int = 0
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_items": self.total_items,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "success_rate": round(self.success_count / max(self.total_items, 1) * 100, 2),
            "errors": self.errors[:10]  # Only return the first 10 errors
        }


class ProgressTracker:
    """
    Thread-safe progress tracker
    """
    
    def __init__(self, job_id: str, total_items: int):
        self.job_id = job_id
        self.total_items = total_items
        
        # Thread-safe counter
        self._processed_items = 0
        self._success_count = 0
        self._error_count = 0
        self._current_item = None
        
        # lock
        self._lock = threading.Lock()
        
        # error list
        self._errors = []
    
    def record_success(self, item: str):
        """Record success"""
        with self._lock:
            self._processed_items += 1
            self._success_count += 1
            self._current_item = item
    
    def record_error(self, item: str, error: str):
        """Log errors"""
        with self._lock:
            self._processed_items += 1
            self._error_count += 1
            self._current_item = item
            self._errors.append({
                "item": item,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    def get_progress(self) -> int:
        """Get progress percentage"""
        with self._lock:
            if self.total_items == 0:
                return 0
            return int((self._processed_items / self.total_items) * 100)
    
    @property
    def processed_items(self) -> int:
        """Number of items processed"""
        with self._lock:
            return self._processed_items
    
    @property
    def success_count(self) -> int:
        """Number of successes"""
        with self._lock:
            return self._success_count
    
    @property
    def error_count(self) -> int:
        """Number of errors"""
        with self._lock:
            return self._error_count
    
    def get_current_item(self) -> str:
        """Get the current processing item"""
        with self._lock:
            return self._current_item
    
    def is_complete(self) -> bool:
        """Is it done?"""
        with self._lock:
            return self._processed_items >= self.total_items
    
    def get_errors(self) -> List[Dict[str, Any]]:
        """Get error list"""
        with self._lock:
            return self._errors.copy()


class RateLimiter:
    """
    Thread-safe rate limiter
    
    Used to control the frequency of API calls to avoid exceeding the rate limit
    """
    
    def __init__(self, max_calls: int, time_window: float):
        """
        Args:
            max_calls: Maximum number of calls within the time window
            time_window: Time window (seconds)
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = defaultdict(list)  # Record call time by data source
        self.lock = threading.Lock()
    
    def wait_if_needed(self, data_source: str = "default"):
        """
        If necessary, wait until you can call
        
        Args:
            data_source: Data source name (different data sources have independent rate limits)
        """
        with self.lock:
            now = time.time()
            # Clean up expired records
            self.calls[data_source] = [
                call_time for call_time in self.calls[data_source]
                if now - call_time < self.time_window
            ]
            
            # If the limit is exceeded, calculate the waiting time
            if len(self.calls[data_source]) >= self.max_calls:
                oldest_call = min(self.calls[data_source])
                wait_time = self.time_window - (now - oldest_call) + 0.2  # Wait an extra 0.2 seconds to ensure safety
                if wait_time > 0:
                    logger.warning(f"⏳ [{data_source}] Rate Limit: Called {len(self.calls[data_source])}/{self.max_calls} times, need to wait {wait_time:.2f} seconds")
                    time.sleep(wait_time)
                    # Clean up expired records again
                    now = time.time()
                    self.calls[data_source] = [
                        call_time for call_time in self.calls[data_source]
                        if now - call_time < self.time_window
                    ]
            
            # 🔥 Record this call (recorded in the lock to ensure thread safety)
            self.calls[data_source].append(time.time())
            
            # 🔥 Record current call frequency (for debugging)
            current_rate = len(self.calls[data_source])
            if current_rate > self.max_calls * 0.8:  # Log warning when exceeds 80%
                logger.debug(f"⚠️ [{data_source}] Current call frequency: {current_rate}/{self.max_calls} times/{self.time_window}seconds")


class ThreadPoolSyncService:
    """
    Data synchronization service based on thread pool
    
    Features:
    - True multi-threaded parallel processing
    - Real-time progress updates
    - Task cancellation support
    - Timeout protection
    - Error isolation and retries
    - API Rate limit protection
    """
    
    def __init__(
        self,
        max_workers: int = 10,
        timeout_per_task: int = 36000,  # Default 10 hours (36000 seconds), used for historical data synchronization
        progress_update_interval: int = 5,  # Progress update interval (seconds)
        enable_retry: bool = True,
        max_retries: int = 3,
        rate_limit_per_minute: int = 200,  # Maximum number of requests per minute (Tushare limit)
        delay_between_items: float = 0.3  # Delay between each task (seconds)
    ):
        self.max_workers = max_workers
        self.timeout_per_task = timeout_per_task
        self.progress_update_interval = progress_update_interval
        self.enable_retry = enable_retry
        self.max_retries = max_retries
        self.delay_between_items = delay_between_items
        
        # 🔥 Rate limiter (200 requests per minute, Tushare limit)
        self.rate_limiter = RateLimiter(
            max_calls=rate_limit_per_minute,
            time_window=60.0  # 60 seconds window
        )
        
        # thread pool
        self.executor = None
        
        # task queue
        self.task_queue = queue.Queue()
        
        # progress tracker
        self.progress_tracker = None
        
        # cancel token
        self.cancellation_token = CancellationToken()
        
        # Statistics
        self.stats = SyncStats()
    
    async def sync_in_thread_pool(
        self,
        items: List[str],
        process_func: Callable,
        job_id: str,
        context: Dict[str, Any] = None
    ) -> SyncStats:
        """
        Execute synchronization tasks in the thread pool
        
        Args:
            items: A list of items to process (such as a list of stock symbols)
            process_func: Handler function (synchronous or asynchronous)
            job_id: Task ID, used for progress tracking
            context: Context information (passed to handler function)
        
        Returns:
            Sync statistics
        """
        if not items:
            logger.warning("⚠️ No items to process")
            return self.stats
        
        # 1. Initialize statistics
        self.stats = SyncStats()
        self.stats.total_items = len(items)
        self.stats.start_time = datetime.now(timezone.utc)
        
        # 2. Initialize progress tracker
        self.progress_tracker = ProgressTracker(
            job_id=job_id,
            total_items=len(items)
        )
        
        logger.info(f"🚀 Start thread pool synchronization: job_id={job_id}, Total number of tasks={len(items)}, "
                   f"Number of threads={self.max_workers}, timeout={self.timeout_per_task}seconds")
        
        # 3. Create thread pool
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # 4. Populate task queue
        for item in items:
            self.task_queue.put((item, context))
        
        # 5. Start worker thread
        futures = []
        for i in range(self.max_workers):
            future = self.executor.submit(
                self._worker_loop,
                process_func,
                context or {}
            )
            futures.append(future)
        
        # 6. Start progress update task
        progress_task = asyncio.create_task(self._progress_update_loop())
        
        # 7. Wait for all tasks to complete
        try:
            # Wait for all worker threads to complete
            completed_count = 0
            for future in as_completed(futures):
                try:
                    future.result()
                    completed_count += 1
                    logger.debug(f"✅ Worker thread {completed_count}/{self.max_workers} Completed")
                except Exception as e:
                    logger.error(f"❌ Worker thread exception: {e}", exc_info=True)
            
            # Wait for progress update task to complete
            await progress_task
            
        except Exception as e:
            logger.error(f"❌ Thread pool synchronization exception: {e}", exc_info=True)
            raise
        finally:
            # Close thread pool
            self.executor.shutdown(wait=True)
            logger.info("🔒 Thread pool is closed")
        
        # 8. Update statistics
        self.stats.end_time = datetime.now(timezone.utc)
        self.stats.duration = (self.stats.end_time - self.stats.start_time).total_seconds()
        self.stats.success_count = self.progress_tracker.success_count
        self.stats.error_count = self.progress_tracker.error_count
        self.stats.errors = self.progress_tracker.get_errors()
        
        logger.info(f"✅ Thread pool synchronization completed: job_id={job_id}, "
                   f"success={self.stats.success_count}, "
                   f"failed={self.stats.error_count}, "
                   f"Time consuming={self.stats.duration:.2f}seconds")
        
        return self.stats
    
    def _worker_loop(self, process_func: Callable, context: Dict[str, Any]):
        """
        Worker thread main loop
        
        Get tasks from the task queue and process them
        """
        thread_name = threading.current_thread().name
        logger.debug(f"🔧 Worker thread {thread_name} start")
        
        while True:
            # Check if canceled
            if self.cancellation_token.is_cancelled():
                logger.info(f"🛑 Worker thread {thread_name} Receive cancellation signal, exit")
                break
            
            try:
                # Get tasks from the queue (timeout 1 second to avoid infinite waiting)
                try:
                    item, task_context = self.task_queue.get(timeout=1)
                except queue.Empty:
                    # Queue is empty, check if all tasks have been completed
                    if self.progress_tracker.is_complete():
                        logger.debug(f"✅ Worker thread {thread_name} All tasks have been completed, exit")
                        break
                    continue
                
                # processing tasks
                try:
                    # merge context
                    merged_context = {**(context or {}), **(task_context or {})}
                    
                    # 🔥 Rate limiting: wait before calling API (if needed)
                    data_source = merged_context.get("data_source", "default")
                    self.rate_limiter.wait_if_needed(data_source)
                    
                    # Processing tasks (with timeout)
                    result = self._process_item_with_timeout(
                        item,
                        process_func,
                        merged_context
                    )
                    
                    # Update statistics
                    if result:
                        self.progress_tracker.record_success(item)
                    else:
                        self.progress_tracker.record_error(item, "Handle return False")
                    
                    # 🔥 Latency between tasks (to avoid requesting too quickly)
                    if self.delay_between_items > 0:
                        time.sleep(self.delay_between_items)
                    
                except Exception as e:
                    # Processing failed
                    error_msg = str(e)
                    self.progress_tracker.record_error(item, error_msg)
                    logger.error(f"❌ {item} Processing failed: {error_msg}")
                    
                    # 🔥 Delay even if it fails to avoid rate limiting due to consecutive failures
                    if self.delay_between_items > 0:
                        time.sleep(self.delay_between_items)
                
                finally:
                    self.task_queue.task_done()
                    
            except Exception as e:
                logger.error(f"❌ Worker thread {thread_name} Abnormal: {e}", exc_info=True)
                break
        
        logger.debug(f"🔧 Worker thread {thread_name} Exit")
    
    def _process_item_with_timeout(
        self,
        item: str,
        process_func: Callable,
        context: Dict[str, Any]
    ):
        """
        Processing of single items (with timeout protection)
        
        Supports synchronous and asynchronous functions
        """
        # Check if canceled
        if self.cancellation_token.is_cancelled():
            raise RuntimeError("Task canceled")
        
        # If it is an asynchronous function, it needs to be run in a thread
        if asyncio.iscoroutinefunction(process_func):
            return self._run_async_in_thread(process_func, item, context)
        else:
            # Synchronous function, called directly (timeout is controlled by the future of the thread pool)
            # Note: executor.submit cannot be used directly here because it is already in the worker thread
            # Just call it directly, the timeout is determined by the outer layer future.result(timeout) control
            return process_func(item, **context)
    
    def _run_async_in_thread(
        self,
        async_func: Callable,
        item: str,
        context: Dict[str, Any]
    ):
        """
        Run an asynchronous function in a thread
        
        Create a new event loop to avoid conflict with the main event loop
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Use asyncio.wait_for to implement timeouts
            return loop.run_until_complete(
                asyncio.wait_for(
                    async_func(item, **context),
                    timeout=self.timeout_per_task
                )
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Asynchronous task timeout ({self.timeout_per_task}seconds)")
        finally:
            loop.close()
    
    async def _progress_update_loop(self):
        """
        progress update loop
        
        Regularly update progress to the database
        """
        logger.debug("📊 Progress update loop starts")
        
        while not self.progress_tracker.is_complete():
            # Check if canceled
            if self.cancellation_token.is_cancelled():
                logger.info("🛑 Progress update loop received cancellation signal")
                break
            
            # update progress
            await self._update_progress()
            
            # Wait for update interval
            await asyncio.sleep(self.progress_update_interval)
        
        # last updated
        await self._update_progress()
        logger.debug("📊 Progress update loop exits")
    
    async def _update_progress(self):
        """
        Update progress to database
        """
        if not self.progress_tracker:
            return
        
        try:
            progress = self.progress_tracker.get_progress()
            current_item = self.progress_tracker.get_current_item()
            processed_items = self.progress_tracker.processed_items
            total_items = self.progress_tracker.total_items
            
            from app.services.scheduler_service import update_job_progress
            
            await update_job_progress(
                job_id=self.progress_tracker.job_id,
                progress=progress,
                message=f"Synchronizing data ({processed_items}/{total_items})",
                current_item=current_item or f"Processed {processed_items} item",
                total_items=total_items,
                processed_items=processed_items
            )
            
            logger.debug(f"📊 progress update: {progress}% ({processed_items}/{total_items})")
            
        except Exception as e:
            logger.warning(f"⚠️ Update progress failed: {e}")
    
    def cancel(self):
        """
        Cancel task
        """
        self.cancellation_token.cancel()
        logger.info("🛑 Task cancellation request sent")

# === unified_thread_pool_sync_service.py ===
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
                                logger.warning("⚠️ Waiting for task cancellation timeout and forcing event loop to close")
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
                        logger.debug("✅ event loop closed")
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
                logger.debug("🔄 Create a thread-local historical data service")
            except Exception as e:
                logger.warning(f"⚠️ Failed to create thread local historical data service: {e}")
            
            # 🔥 Create a thread-local news data service
            try:
                from app.services.news_data_service import NewsDataService
                news_service = NewsDataService()
                news_service.db = connections['db']
                connections['news_service'] = news_service
                logger.debug("🔄 Create a thread-local news data service")
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
                    logger.debug("🔄 Thread-local MongoDB client closed")
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

# === unified_historical_sync_service.py ===
#!/usr/bin/env python3
"""
Unified historical data synchronization service
Supports parallel execution of historical data synchronization tasks from multiple data sources
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.worker.tushare_sync_service import get_tushare_sync_service
from app.worker.akshare_sync_service import get_akshare_sync_service
from app.worker.baostock_sync_service import BaoStockSyncService

logger = logging.getLogger(__name__)


async def run_unified_historical_sync(
    data_sources: List[str] = None,
    incremental: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Unified historical data synchronization task: perform historical data synchronization of multiple data sources in parallel
    
    Args:
        data_sources: List of data sources to be synchronized, such as ["tushare", "akshare", "baostock"]
                     If None, synchronizes all enabled data sources
        incremental: Whether to incrementally synchronize
        **kwargs: Other parameters (passed to the synchronization function of each data source)
    
    Returns:
        Synchronization result statistics
    """
    # Synchronize all data sources by default
    if data_sources is None:
        data_sources = ["tushare", "akshare", "baostock"]
    
    logger.info(f"🚀 Start unified historical data synchronization: data source={data_sources}, Incremental synchronization={incremental}")
    
    # Prepare task list
    tasks = []
    task_info = []
    
    # 🔥 Create parallel tasks for each data source
    for data_source in data_sources:
        if data_source == "tushare":
            task = _run_tushare_historical_sync_task(incremental, **kwargs)
            tasks.append(task)
            task_info.append("tushare")
        elif data_source == "akshare":
            task = _run_akshare_historical_sync_task(incremental, **kwargs)
            tasks.append(task)
            task_info.append("akshare")
        elif data_source == "baostock":
            task = _run_baostock_historical_sync_task(**kwargs)
            tasks.append(task)
            task_info.append("baostock")
        else:
            logger.warning(f"⚠️ Unsupported data source: {data_source}, skip")
    
    if not tasks:
        logger.warning("⚠️ No data source available for historical data synchronization")
        return {
            "success": False,
            "message": "No data source available",
            "results": {}
        }
    
    # 🔥 Execute synchronization tasks for all data sources in parallel
    logger.info(f"🚀 Start parallel synchronization {len(tasks)} historical data from data sources: {task_info}")
    
    try:
        # Parallel execution using asyncio.gather
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Processing results
        final_results = {}
        success_count = 0
        error_count = 0
        
        for i, (data_source, result) in enumerate(zip(task_info, results)):
            if isinstance(result, Exception):
                logger.error(f"❌ {data_source} Historical data synchronization failed: {result}", exc_info=True)
                final_results[data_source] = {
                    "success": False,
                    "error": str(result)
                }
                error_count += 1
            else:
                logger.info(f"✅ {data_source} Historical data synchronization completed: {result}")
                final_results[data_source] = {
                    "success": True,
                    "result": result
                }
                success_count += 1
        
        logger.info(f"🎉 Unified historical data synchronization completed: success {success_count}/{len(tasks)}, failed {error_count}/{len(tasks)}")
        
        return {
            "success": error_count == 0,
            "total_sources": len(tasks),
            "success_count": success_count,
            "error_count": error_count,
            "results": final_results
        }
        
    except Exception as e:
        logger.error(f"❌ Unified historical data synchronization failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "results": {}
        }


async def _run_tushare_historical_sync_task(incremental: bool, **kwargs):
    """Run Tushare historical data synchronization task"""
    try:
        from app.worker.tushare_sync_service import run_tushare_historical_sync
        # Set manual trigger flag to allow parallel execution
        kwargs["_manual_trigger"] = True
        result = await run_tushare_historical_sync(incremental=incremental, **kwargs)
        return result
    except Exception as e:
        logger.error(f"❌ Tushare Historical data synchronization task failed: {e}", exc_info=True)
        raise


async def _run_akshare_historical_sync_task(incremental: bool, **kwargs):
    """Run AKShare historical data synchronization task"""
    try:
        from app.worker.akshare_sync_service import run_akshare_historical_sync
        # Set manual trigger flag to allow parallel execution
        kwargs["_manual_trigger"] = True
        result = await run_akshare_historical_sync(incremental=incremental, **kwargs)
        return result
    except Exception as e:
        logger.error(f"❌ AKShare Historical data synchronization task failed: {e}", exc_info=True)
        raise


async def _run_baostock_historical_sync_task(**kwargs):
    """Run the BaoStock historical data synchronization task"""
    try:
        from app.worker.baostock_sync_service import run_baostock_historical_sync
        # Set manual trigger flag to allow parallel execution
        kwargs["_manual_trigger"] = True
        result = await run_baostock_historical_sync(**kwargs)
        return result
    except Exception as e:
        logger.error(f"❌ BaoStock Historical data synchronization task failed: {e}", exc_info=True)
        raise

# === multi_period_sync_service.py ===
#!/usr/bin/env python3
"""
Multi-period historical data synchronization service
Supports unified synchronization of daily, weekly and monthly data
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from app.services.historical_data_service import get_historical_data_service
from app.worker.tushare_sync_service import TushareSyncService
from app.worker.akshare_sync_service import AKShareSyncService
from app.worker.baostock_sync_service import BaoStockSyncService

logger = logging.getLogger(__name__)


@dataclass
class MultiPeriodSyncStats:
    """Multi-cycle synchronization statistics"""
    total_symbols: int = 0
    daily_records: int = 0
    weekly_records: int = 0
    monthly_records: int = 0
    success_count: int = 0
    error_count: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class MultiPeriodSyncService:
    """Multi-period historical data synchronization service"""
    
    def __init__(self):
        self.historical_service = None
        self.tushare_service = None
        self.akshare_service = None
        self.baostock_service = None
        
    async def initialize(self):
        """Initialize service"""
        try:
            self.historical_service = await get_historical_data_service()
            
            # Initialize each data source service
            self.tushare_service = TushareSyncService()
            await self.tushare_service.initialize()
            
            self.akshare_service = AKShareSyncService()
            await self.akshare_service.initialize()
            
            self.baostock_service = BaoStockSyncService()
            await self.baostock_service.initialize()
            
            logger.info("✅ Multi-cycle synchronization service initialization completed")
            
        except Exception as e:
            logger.error(f"❌ Multi-cycle synchronization service initialization failed: {e}")
            raise
    
    async def sync_multi_period_data(
        self,
        symbols: List[str] = None,
        periods: List[str] = None,
        data_sources: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        all_history: bool = False
    ) -> MultiPeriodSyncStats:
        """
        Synchronize multi-period historical data

        Args:
            symbols: List of stock codes, None means all stocks
            periods: period list (daily/weekly/monthly)
            data_sources: Data source list (tushare/akshare/baostock)
            start_date: start date
            end_date: end date
            all_history: Whether to synchronize all historical data (ignore time range)
        """
        if self.historical_service is None:
            await self.initialize()
        
        # Default parameters
        if periods is None:
            periods = ["daily", "weekly", "monthly"]
        if data_sources is None:
            data_sources = ["tushare", "akshare", "baostock"]
        if symbols is None:
            symbols = await self._get_all_symbols()

        # Handle all_history parameter
        if all_history:
            start_date, end_date = await self._get_full_history_date_range()
            logger.info(f"🔄 Enable full historical data synchronization mode: {start_date} Arrive {end_date}")

        stats = MultiPeriodSyncStats()
        stats.total_symbols = len(symbols)

        logger.info(f"🔄 Start multi-cycle data synchronization: {len(symbols)}only stocks, "
                   f"cycle{periods}, data source{data_sources}, "
                   f"time range: {start_date or 'Default'} Arrive {end_date or 'today'}")
        
        try:
            # 🔥 Optimization: Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
            # Different cycles of the same data source are still executed serially (to avoid API current limiting)
            
            # Create tasks for each data source (all cycles are processed serially within each data source)
            tasks = []
            task_info = []  # Save task information for result processing
            
            for data_source in data_sources:
                # Create a task for each data source that serially processes all cycles of that data source
                task = self._sync_data_source_all_periods(
                    data_source, periods, symbols, start_date, end_date
                )
                tasks.append(task)
                task_info.append(data_source)
            
            # Execute synchronization tasks for all data sources in parallel
            if tasks:
                logger.info(f"🚀 Start parallel synchronization {len(tasks)} historical data from data sources: {task_info}")
                
                # Parallel execution using asyncio.gather
                period_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Processing results
                for i, (data_source, result) in enumerate(zip(task_info, period_results)):
                    if isinstance(result, Exception):
                        logger.error(f"❌ {data_source} Historical data synchronization failed: {result}", exc_info=True)
                        stats.error_count += len(symbols)  # Assume all fails
                    else:
                        # result is a dictionary containing statistical information for each period
                        for period in periods:
                            period_stats = result.get(period, {})
                            
                            # Cumulative statistics
                            if period == "daily":
                                stats.daily_records += period_stats.get("records", 0)
                            elif period == "weekly":
                                stats.weekly_records += period_stats.get("records", 0)
                            elif period == "monthly":
                                stats.monthly_records += period_stats.get("records", 0)
                            
                            stats.success_count += period_stats.get("success", 0)
                            stats.error_count += period_stats.get("errors", 0)
                            
                            # progress log
                            logger.info(f"📊 {data_source}-{period}Synchronization completed: "
                                       f"{period_stats.get('records', 0)}records")
            else:
                logger.warning("⚠️ No data source available for historical data synchronization")
            
            logger.info(f"✅ Multi-cycle data synchronization completed: "
                       f"daily line{stats.daily_records}, perimeter{stats.weekly_records}, "
                       f"monthly line{stats.monthly_records}records")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Multi-cycle data synchronization failed: {e}")
            stats.errors.append(str(e))
            return stats
    
    async def _sync_data_source_all_periods(
        self,
        data_source: str,
        periods: List[str],
        symbols: List[str],
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Synchronize all periodic data of a data source (serial execution to avoid API current limit)
        
        Returns:
            Dictionary, key is the period name, value is the statistical information of the period
        """
        results = {}
        
        # Serial execution of different cycles of the same data source (avoiding API current limit)
        for period in periods:
            try:
                period_stats = await self._sync_period_data(
                    data_source, period, symbols, start_date, end_date
                )
                results[period] = period_stats
            except Exception as e:
                logger.error(f"❌ {data_source}-{period}Sync failed: {e}")
                results[period] = {"records": 0, "success": 0, "errors": len(symbols)}
        
        return results
    
    async def _sync_period_data(
        self,
        data_source: str,
        period: str,
        symbols: List[str],
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Any]:
        """Synchronize data for a specific period"""
        stats = {"records": 0, "success": 0, "errors": 0}
        
        try:
            logger.info(f"📈 Start syncing{data_source}-{period}data: {len(symbols)}only stocks")
            
            # Choose the corresponding service
            if data_source == "tushare":
                service = self.tushare_service
            elif data_source == "akshare":
                service = self.akshare_service
            elif data_source == "baostock":
                service = self.baostock_service
            else:
                logger.error(f"❌ Unsupported data source: {data_source}")
                return stats
            
            # Batch processing
            batch_size = 50
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                batch_stats = await self._sync_batch_period_data(
                    service, data_source, period, batch, start_date, end_date
                )
                
                stats["records"] += batch_stats["records"]
                stats["success"] += batch_stats["success"]
                stats["errors"] += batch_stats["errors"]
                
                # progress log
                progress = min(i + batch_size, len(symbols))
                logger.info(f"📊 {data_source}-{period}Progress: {progress}/{len(symbols)}")
                
                # API Current limiting
                await asyncio.sleep(0.5)
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ {data_source}-{period}Sync failed: {e}")
            stats["errors"] += 1
            return stats
    
    async def _sync_batch_period_data(
        self,
        service,
        data_source: str,
        period: str,
        symbols: List[str],
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Any]:
        """Synchronize batch cycle data"""
        stats = {"records": 0, "success": 0, "errors": 0}
        
        for symbol in symbols:
            try:
                # Get historical data
                if data_source == "tushare":
                    hist_data = await service.provider.get_historical_data(
                        symbol, start_date, end_date, period
                    )
                elif data_source == "akshare":
                    hist_data = await service.provider.get_historical_data(
                        symbol, start_date, end_date, period
                    )
                elif data_source == "baostock":
                    hist_data = await service.provider.get_historical_data(
                        symbol, start_date, end_date, period
                    )
                else:
                    continue
                
                if hist_data is not None and not hist_data.empty:
                    # Save to database
                    saved_count = await self.historical_service.save_historical_data(
                        symbol=symbol,
                        data=hist_data,
                        data_source=data_source,
                        market="CN",
                        period=period
                    )
                    
                    stats["records"] += saved_count
                    stats["success"] += 1
                else:
                    stats["errors"] += 1
                    
            except Exception as e:
                logger.error(f"❌ {symbol}-{period}Sync failed: {e}")
                stats["errors"] += 1
        
        return stats
    
    async def _get_all_symbols(self) -> List[str]:
        """Get all tickers"""
        try:
            # Get stock list from database
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            collection = db.stock_basic_info

            cursor = collection.find({}, {"symbol": 1})
            symbols = [doc["symbol"] async for doc in cursor]

            logger.info(f"📊 Get a list of stocks: {len(symbols)}only stocks")
            return symbols

        except Exception as e:
            logger.error(f"❌ Failed to get stock list: {e}")
            return []

    async def _get_full_history_date_range(self) -> tuple[str, str]:
        """Get the date range of the entire historical data"""
        try:
            from datetime import datetime, timedelta

            # End date: today
            end_date = datetime.now().strftime('%Y-%m-%d')

            # Start date: Determined based on data source
            # Tushare: 1990 start of year
            # AKShare: 1990 start of year
            # BaoStock: 1990 start of year
            # To be on the safe side, starting in 1990
            start_date = "1990-01-01"

            logger.info(f"📅 Full historical data range: {start_date} Arrive {end_date}")
            return start_date, end_date

        except Exception as e:
            logger.error(f"❌ Failed to obtain the full historical date range: {e}")
            # By default, data for the last 5 years is returned
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
            return start_date, end_date
    
    async def get_sync_statistics(self) -> Dict[str, Any]:
        """Get sync statistics"""
        try:
            if self.historical_service is None:
                await self.initialize()
            
            # Statistics by period
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            collection = db.stock_daily_quotes
            
            pipeline = [
                {"$group": {
                    "_id": {
                        "period": "$period",
                        "data_source": "$data_source"
                    },
                    "count": {"$sum": 1},
                    "latest_date": {"$max": "$trade_date"}
                }}
            ]
            
            results = await collection.aggregate(pipeline).to_list(length=None)
            
            # Format statistical results
            stats = {}
            for result in results:
                period = result["_id"]["period"]
                source = result["_id"]["data_source"]
                
                if period not in stats:
                    stats[period] = {}
                
                stats[period][source] = {
                    "count": result["count"],
                    "latest_date": result["latest_date"]
                }
            
            return {
                "period_statistics": stats,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to obtain synchronization statistics: {e}")
            return {}


# Global service instance
_multi_period_sync_service = None


async def get_multi_period_sync_service() -> MultiPeriodSyncService:
    """Get a multi-cycle synchronization service instance"""
    global _multi_period_sync_service
    if _multi_period_sync_service is None:
        _multi_period_sync_service = MultiPeriodSyncService()
        await _multi_period_sync_service.initialize()
    return _multi_period_sync_service


# APScheduler Task function
async def run_multi_period_sync(periods: List[str] = None):
    """APScheduler Task: Multi-cycle data synchronization"""
    try:
        service = await get_multi_period_sync_service()
        result = await service.sync_multi_period_data(periods=periods)
        logger.info(f"✅ Multi-cycle data synchronization completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Multi-cycle data synchronization failed: {e}")
        raise


async def run_daily_sync():
    """APScheduler Task: Daily data synchronization"""
    return await run_multi_period_sync(["daily"])


async def run_weekly_sync():
    """APScheduler Task: Weekly data synchronization"""
    return await run_multi_period_sync(["weekly"])


async def run_monthly_sync():
    """APScheduler Task: Monthly data synchronization"""
    return await run_multi_period_sync(["monthly"])
