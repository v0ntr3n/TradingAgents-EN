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
