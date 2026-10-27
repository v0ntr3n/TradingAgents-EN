#!/usr/bin/env python3
"""
Financial data synchronization service
Unified management of financial data synchronization from three data sources
"""
import asyncio
import logging
import time
import threading
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from app.core.database import create_isolated_async_mongo_binding, get_mongo_db
from app.services.financial_data_service import get_financial_data_service
from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
from tradingagents.dataflows.providers.china.baostock import get_baostock_provider

logger = logging.getLogger(__name__)


@dataclass
class FinancialSyncStats:
    """Financial data synchronization statistics"""
    total_symbols: int = 0
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
            "total_symbols": self.total_symbols,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "success_rate": round(self.success_count / max(self.total_symbols, 1) * 100, 2),
            "errors": self.errors[:10]  # Only return the first 10 errors
        }


class FinancialDataSyncService:
    """Financial data synchronization service"""
    
    def __init__(self):
        self.db = None
        self.financial_service = None
        self.providers = {}
        
    async def initialize(self):
        """Initialize service"""
        try:
            self.db = get_mongo_db()
            self.financial_service = await get_financial_data_service()
            
            # Initialize data source provider
            self.providers = {
                "tushare": get_tushare_provider(),
                "akshare": get_akshare_provider(),
                "baostock": get_baostock_provider()
            }
            
            logger.info("✅ Financial data synchronization service initialization successful")
            
        except Exception as e:
            logger.error(f"❌ Financial data synchronization service initialization failed: {e}")
            raise
    
    async def sync_financial_data(
        self,
        symbols: List[str] = None,
        data_sources: List[str] = None,
        report_types: List[str] = None,
        batch_size: int = 50,
        delay_seconds: float = 1.0,
        job_id: str = None,
        rate_limit_per_minute: int = 80,  # 🔥 Rate Limit: Maximum number of calls per minute
        _resume_from_index: int = None  # 🔥 Resume execution: from which position to continue (number of stocks processed)
    ) -> Dict[str, FinancialSyncStats]:
        """
        Synchronize financial data (using thread pool)
        
        Args:
            symbols: Stock code list, None means synchronize all stocks
            data_sources: Data source list ["tushare", "akshare", "baostock"]
            report_types: List of report types ["quarterly", "annual"]
            batch_size: Batch size (deprecated for compatibility)
            delay_seconds: API Call deferral (deprecated, retaining compatibility)
            job_id: Task ID, used for progress tracking
            
        Returns:
            Synchronized statistical results of each data source
        """
        if self.db is None:
            await self.initialize()
        
        # Default parameters
        if data_sources is None:
            data_sources = ["tushare", "akshare", "baostock"]
        if report_types is None:
            report_types = ["quarterly", "annual"]
        
        logger.info(f"🔄 Start financial data synchronization (thread pool mode): data source={data_sources}, Report type filter={report_types}")
        
        # Get a list of stocks
        if symbols is None:
            symbols = await self._get_stock_symbols()
        
        if not symbols:
            logger.warning("⚠️ No stocks found to sync")
            return {}
        
        logger.info(f"📊 Prepare to sync {len(symbols)} Financial data for only stocks")
        
        # Perform synchronization for each data source
        results = {}
        
        # 🔥 Process each data source in parallel using a unified thread pool service
        # Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        tasks = []
        for data_source in data_sources:
            if data_source not in self.providers:
                logger.warning(f"⚠️ Unsupported data source: {data_source}")
                continue
            
            # 🔥 Create concurrent tasks: Use the unified thread pool service to perform synchronization of each data source
            # 🔥 Use the original job_id instead of the modified job_id so that progress updates will be updated to the correct execution record
            data_source_job_id = job_id if job_id else f"financial_{data_source}"
            
            # 🔥 Create wrapper method with data source as closure variable (use default parameters to ensure proper capture)
            def create_sync_wrapper(ds, syms, rpts, jid, rate_limit):
                """Create wrapper methods to ensure variables are captured correctly"""
                async def sync_data_source_wrapper(**kwargs):
                    """Wrapper method for unifying thread pool service calls"""
                    return await self._sync_source_financial_data_serial_async(
                        data_source=ds,
                        symbols=syms,
                        report_types=rpts,
                        job_id=jid,
                        rate_limit_per_minute=rate_limit,
                        resume_from_index=kwargs.get("resume_from_index")
                    )
                return sync_data_source_wrapper
            
            sync_data_source_wrapper = create_sync_wrapper(
                data_source, symbols, report_types, data_source_job_id, rate_limit_per_minute
            )
            
            # 🔥 Execute using unified thread pool service
            task = unified_service.execute_sync_method(
                sync_method=sync_data_source_wrapper,
                method_kwargs={},
                job_id=data_source_job_id,
                rate_limit_per_minute=rate_limit_per_minute,
                resume_from_index=_resume_from_index
            )
            tasks.append((data_source, task))
        
        # Execute synchronization tasks for all data sources in parallel
        if tasks:
            logger.info(f"🚀 Start parallel synchronization {len(tasks)} financial data from data sources: {[ds for ds, _ in tasks]}")
            
            # Parallel execution using asyncio.gather
            task_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True
            )
            
            # Processing results
            for i, ((data_source, _), task_result) in enumerate(zip(tasks, task_results)):
                if isinstance(task_result, Exception):
                    logger.error(f"❌ {data_source} Financial data synchronization failed: {task_result}", exc_info=True)
                    # Creation of statistics failed
                    failed_stats = FinancialSyncStats()
                    failed_stats.total_symbols = len(symbols) if symbols else 0
                    failed_stats.error_count = failed_stats.total_symbols
                    failed_stats.errors.append({
                        "error": str(task_result),
                        "data_source": data_source
                    })
                    results[data_source] = failed_stats
                elif not task_result.success:
                    # Unified service returns failure result
                    logger.error(f"❌ {data_source} Financial data synchronization failed: {task_result.error}")
                    failed_stats = FinancialSyncStats()
                    failed_stats.total_symbols = len(symbols) if symbols else 0
                    failed_stats.error_count = failed_stats.total_symbols
                    failed_stats.errors.append({
                        "error": task_result.error or "unknown error",
                        "data_source": data_source
                    })
                    results[data_source] = failed_stats
                else:
                    # success
                    result = task_result.result
                    results[data_source] = result
                    logger.info(f"✅ {data_source} Financial data synchronization completed: "
                               f"success {result.success_count}/{result.total_symbols} "
                               f"({result.success_count/max(result.total_symbols,1)*100:.1f}%)")
        else:
            logger.warning("⚠️ No data source available for financial data synchronization")
        
        return results
    
    async def _sync_source_financial_data_serial_async(
        self,
        data_source: str,
        symbols: List[str],
        report_types: List[str],
        job_id: str,
        rate_limit_per_minute: int,
        resume_from_index: int = None  # 🔥 Resume execution: where to continue from
    ) -> FinancialSyncStats:
        """
        Serial synchronization of financial data from a single data source (asynchronous version, runs in a thread of the thread pool)
        """
        provider = self.providers[data_source]
        
        # Check data source availability
        if not provider.is_available():
            logger.warning(f"⚠️ {data_source} Data source is not available")
            stats = FinancialSyncStats()
            stats.total_symbols = len(symbols)
            stats.skipped_count = len(symbols)
            return stats
        
        # Calculate latency (make sure you don't exceed the rate limit)
        # For example: 80 times/minute = 60/80 = 0.75 seconds/times
        delay_between_calls = 60.0 / rate_limit_per_minute if rate_limit_per_minute > 0 else 0.5
        
        # 🔥 Save the original stock total (used for progress calculations)
        original_total_symbols = len(symbols)
        
        # 🔥 If a restore location is specified, skip processed stocks
        start_index = resume_from_index if resume_from_index is not None and resume_from_index > 0 else 0
        if start_index > 0:
            logger.info(f"🔄 [{data_source}] Resume execution: from section {start_index} stocks start (processed {start_index}/{original_total_symbols}) ")
            # Skip processed stocks
            symbols = symbols[start_index:]
            if not symbols:
                logger.warning(f"⚠️ [{data_source}] All stocks have been processed, no need to continue synchronization")
                stats = FinancialSyncStats()
                stats.total_symbols = original_total_symbols
                stats.success_count = start_index
                return stats
        
        logger.info(f"🔧 [{data_source}] Serial sync configuration: Number of shares remaining={len(symbols)}, Total number of shares={original_total_symbols}, "
                   f"rate limit={rate_limit_per_minute}times/minute, "
                   f"delay={delay_between_calls:.2f}seconds/request, "
                   f"starting position={start_index}")
        
        # Initialize statistics
        stats = FinancialSyncStats()
        stats.total_symbols = original_total_symbols  # 🔥 Total number of shares (including processed)
        stats.start_time = datetime.now(timezone.utc)
        
        # 🔥 Create a new service instance in a thread in the thread pool (to avoid event loop conflicts)
        # Create an independent asynchronous database connection using the current thread's event loop
        from app.services.financial_data_service import FinancialDataService

        mongo_client, mongo_db = create_isolated_async_mongo_binding()
        
        # Create a new service instance, using the database connection of the current thread's event loop
        financial_service = FinancialDataService()
        financial_service.db = mongo_db
        
        # Make sure the index exists (asynchronously, executed in the event loop of the current thread)
        try:
            collection = financial_service.db[financial_service.collection_name]
            # Create index (asynchronous operation)
            await collection.create_indexes([
                # Composite unique index
                [("symbol", 1), ("report_period", 1), ("data_source", 1)],
                # Other indexes
                [("symbol", 1)],
                [("report_period", -1)],
                [("data_source", 1)]
            ])
        except Exception as e:
            logger.debug(f"Index creation check: {e}")  # Index may already exist, ignore error
        
        # Process each stock serially
        processed_count = start_index  # 🔥 Count from recovery position
        try:
            for i, symbol in enumerate(symbols):
                # 🔥 Check if the task should be stopped (by querying the database)
                try:
                    # 🔥 Check if the task was canceled (checked at the beginning of each loop)
                    should_stop = await self._should_stop_sync(job_id)
                    if should_stop:
                        logger.warning(f"🛑 [{data_source}] Cancellation request detected, task canceled, sync stopped (job_id={job_id})")
                        # Update progress to current progress
                        try:
                            from app.services.scheduler_service import update_job_progress, TaskCancelledException
                            # 🔥 The number of stocks processed needs to be taken into account when calculating progress (when execution is resumed)
                            total_items = stats.total_symbols  # Use the total number of shares (including those processed)
                            progress_int = int((processed_count / total_items) * 100) if total_items > 0 else 0
                            progress_int = min(progress_int, 100)
                            await update_job_progress(
                                job_id=job_id,
                                progress=progress_int,
                                current_item=f"[{data_source}] {symbol}",
                                total_items=total_items,
                                processed_items=processed_count,
                                message=f"[{data_source}] The task has been canceled by the user"
                            )
                        except TaskCancelledException:
                            # If update_job_progress also detects cancellation, exit directly
                            logger.warning(f"🛑 [{data_source}] update_job_progress Cancellation request also detected, stop immediately")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Update progress failed: {e}")
                        break

                    # 🔥 Rate limiting: wait before calling API (cancellation is also checked during wait)
                    if delay_between_calls > 0:
                        # Wait in segments, checking cancellation status every 0.5 seconds
                        wait_time = 0
                        check_interval = 0.5
                        while wait_time < delay_between_calls:
                            await asyncio.sleep(min(check_interval, delay_between_calls - wait_time))
                            wait_time += check_interval
                            # Check cancellation status
                            should_stop = await self._should_stop_sync(job_id)
                            if should_stop:
                                logger.warning(f"🛑 [{data_source}] Cancellation request detected while waiting, sync stopped (job_id={job_id})")
                                # Update progress and exit the loop
                                try:
                                    from app.services.scheduler_service import update_job_progress
                                    # 🔥 The number of stocks processed needs to be taken into account when calculating progress (when execution is resumed)
                                    total_items = stats.total_symbols  # Use the total number of shares (including those processed)
                                    progress_int = int((processed_count / total_items) * 100) if total_items > 0 else 0
                                    progress_int = min(progress_int, 100)
                                    await update_job_progress(
                                        job_id=job_id,
                                        progress=progress_int,
                                        current_item=f"[{data_source}] {symbol}",
                                        total_items=total_items,
                                        processed_items=processed_count,
                                        message=f"[{data_source}] The task has been canceled by the user"
                                    )
                                except Exception as e:
                                    logger.warning(f"⚠️ Update progress failed: {e}")
                                break

                    # 🔥 Before syncing stock data, check again for cancellation flag (prevents receiving cancellation request during sync)
                    should_stop = await self._should_stop_sync(job_id)
                    if should_stop:
                        logger.warning(f"🛑 [{data_source}] Cancellation request detected before sync, sync stopped (job_id={job_id})")
                        break

                    # Synchronize financial data for individual stocks
                    success = await self._sync_symbol_financial_data_async(
                        symbol=symbol,
                        data_source=data_source,
                        provider=provider,
                        report_types=report_types,
                        financial_service=financial_service
                    )

                    if success:
                        stats.success_count += 1
                    else:
                        stats.skipped_count += 1

                    processed_count += 1

                    # 🔥 After the sync is complete, check again for the cancellation flag
                    should_stop = await self._should_stop_sync(job_id)
                    if should_stop:
                        logger.warning(f"🛑 [{data_source}] Cancellation request detected after sync, sync stopped (job_id={job_id})")
                        break

                    # 🔥 Update progress every time 1 stock is processed or completed (more frequent updates)
                    # Calculate progress percentage: ensure that even small progress is displayed correctly (at least 1% is displayed)
                    # 🔥 The number of stocks processed needs to be taken into account when calculating progress (when execution is resumed)
                    total_items = stats.total_symbols  # Use the total number of shares (including those processed)
                    if total_items > 0:
                        progress_float = (processed_count / total_items) * 100
                        # 🔥 If the progress is greater than 0 but less than 1%, display at least 1% to avoid displaying 0%
                        if progress_float > 0 and progress_float < 1:
                            progress_int = 1
                        else:
                            progress_int = int(round(progress_float))
                        # Make sure not to exceed 100%
                        progress_int = min(progress_int, 100)
                    else:
                        progress_int = 0

                    # update_job_progress is an independent asynchronous function
                    try:
                        from app.services.scheduler_service import update_job_progress, TaskCancelledException
                        # 🔥 Logging progress update calls (for debugging)
                        logger.debug(f"📊 [{data_source}] Prepare to update progress: job_id={job_id}, progress={progress_int}%, "
                                   f"processed={processed_count}/{total_items}, current_item={symbol}")

                        await update_job_progress(
                            job_id=job_id,
                            progress=progress_int,  # Use whole number percentages
                            current_item=f"[{data_source}] {symbol}",  # 🔥 Mark the data source in current_item
                            total_items=total_items,  # 🔥 Use the total number of shares (including those processed)
                            processed_items=processed_count,
                            message=f"[{data_source}] Synchronizing: {symbol} ({processed_count}/{total_items})"  # 🔥 Mark the data source and total number of stocks in the message
                        )

                        # 🔥 Record detailed logs every 10 stocks to avoid excessive logs
                        if processed_count % 10 == 0 or (i + 1) == len(symbols):
                            logger.info(f"📊 [{data_source}] Progress updated successfully: {processed_count}/{total_items} "
                                       f"({progress_int}%), success={stats.success_count}, skip={stats.skipped_count}")
                    except TaskCancelledException as cancel_error:
                        # 🔥 If a cancellation request is received, stop the task immediately
                        logger.warning(f"🛑 [{data_source}] Received cancellation request (via update_job_progress), stopped synchronization: {cancel_error}")
                        # 🔥 Set a flag to ensure the loop exits
                        should_stop = True
                        # 🔥 Break out of the loop immediately
                        break
                    except Exception as progress_error:
                        # 🔥 Check if it is a cancellation related exception (maybe other forms of cancellation exception)
                        error_msg = str(progress_error)
                        error_type = type(progress_error).__name__
                        logger.warning(f"🔍 [{data_source}] Progress update exception type: {error_type}, news: {error_msg}")

                        error_lower = error_msg.lower()
                        if "Cancel" in error_lower or "cancel" in error_lower or "cancelled" in error_lower or "TaskCancelledException" in error_type:
                            logger.warning(f"🛑 [{data_source}] A cancellation-related exception was detected during progress update and synchronization was stopped.: {progress_error}")
                            break
                        # 🔥 Failure in progress update should not affect the main process, but needs to be logged
                        logger.error(f"❌ [{data_source}] Progress update failed: job_id={job_id}, error={progress_error}", exc_info=True)
                        # Log errors every 10 stocks to avoid excessive logs
                        if processed_count % 10 == 0:
                            logger.warning(f"⚠️ [{data_source}] Progress update fails, but execution continues: {progress_error}")

                except Exception as e:
                    # 🔥 Check if it is a cancellation related exception
                    error_msg = str(e)
                    error_type = type(e).__name__
                    error_lower = error_msg.lower()

                    # 🔥 Check if it is TaskCancelledException or its subclass
                    from app.services.scheduler_service import TaskCancelledException
                    if isinstance(e, TaskCancelledException):
                        logger.warning(f"🛑 [{data_source}] TaskCancelledException detected, synchronization stopped: {error_msg}")
                        break

                    # 🔥 Check whether the exception type name or message contains cancellation-related keywords
                    if "Cancel" in error_lower or "cancel" in error_lower or "cancelled" in error_lower or "TaskCancelledException" in error_type:
                        logger.warning(f"🛑 [{data_source}] Cancellation related exception detected, synchronization stopped: Type={error_type}, news={error_msg}")
                        break

                    stats.error_count += 1
                    stats.errors.append({
                        "symbol": symbol,
                        "error": error_msg,
                        "data_source": data_source
                    })
                    logger.error(f"❌ [{data_source}] {symbol} Financial data synchronization failed: {error_msg}")
                    processed_count += 1
        finally:
            try:
                mongo_client.close()
            except Exception as close_error:
                logger.warning(f"⚠️ [{data_source}] Failed to close in-thread MongoDB client: {close_error}")
        
        # 🔥 Check if the task is stopped due to cancellation
        was_cancelled = False
        try:
            should_stop = await self._should_stop_sync(job_id)
            if should_stop:
                was_cancelled = True
                logger.warning(f"🛑 [{data_source}] The task is stopped due to cancellation and the status will be updated to cancelled (job_id={job_id})")
        except Exception as e:
            logger.warning(f"⚠️ [{data_source}] Checking cancellation status failed: {e}")
        
        # Complete statistics
        stats.end_time = datetime.now(timezone.utc)
        stats.duration = (stats.end_time - stats.start_time).total_seconds()
        
        # 🔥 If the task is canceled, the updated status is cancelled
        if was_cancelled:
            try:
                # Use a synchronous way to update the state (because in the thread pool thread, the event loop may be closed)
                from pymongo import MongoClient
                from app.core.config import settings
                sync_client = MongoClient(settings.MONGO_URI)
                sync_db = sync_client[settings.MONGODB_DATABASE]
                try:
                    # Extract original job_id
                    original_job_id = job_id
                    for ds in ["tushare", "akshare", "baostock"]:
                        if job_id.endswith(f"_{ds}"):
                            original_job_id = job_id[:-len(f"_{ds}")]
                            break
                    
                    # Update all related execution records to canceled status
                    update_result = sync_db.scheduler_executions.update_many(
                        {
                            "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                            "status": "running"
                        },
                        {
                            "$set": {
                                "status": "cancelled",
                                "error_message": f"[{data_source}] The task has been canceled by the user",
                                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)
                            }
                        }
                    )
                    logger.info(f"✅ [{data_source}] updated {update_result.modified_count} The execution record status is cancelled (job_id={job_id})")
                    
                    # 🔥 Also update the status in the Redis cache
                    try:
                        from app.core.redis_client import RedisKeys
                        from app.core.database import get_redis_sync_client
                        import json
                        redis_sync_client = get_redis_sync_client()
                        if redis_sync_client:
                            progress_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=original_job_id)
                            # Get current progress data
                            progress_data_str = redis_sync_client.get(progress_key)
                            if progress_data_str:
                                progress_data = json.loads(progress_data_str)
                                progress_data["status"] = "cancelled"
                                progress_data["message"] = f"[{data_source}] The task has been canceled by the user"
                                redis_sync_client.setex(
                                    progress_key,
                                    86400,  # 24 hour expires
                                    json.dumps(progress_data, ensure_ascii=False)
                                )
                                logger.info(f"✅ [{data_source}] The updated Redis cache status is cancelled")
                    except Exception as redis_error:
                        logger.warning(f"⚠️ [{data_source}] Failed to update Redis cache: {redis_error}")
                finally:
                    sync_client.close()
            except Exception as e:
                logger.error(f"❌ [{data_source}] Failed to update task status to canceled: {e}", exc_info=True)
        
        logger.info(f"✅ [{data_source}] Financial data synchronization completed: "
                   f"success={stats.success_count}, failed={stats.error_count}, "
                   f"skip={stats.skipped_count}, Time consuming={stats.duration:.2f}seconds, "
                   f"Cancel={was_cancelled}")
        
        return stats
    
    async def _should_stop_sync(self, job_id: str) -> bool:
        """
        Check if the task should be stopped
        
        Args:
            job_id: Task ID (may be a modified job_id, such as tushare_financial_sync_tushare)
            
        Returns:
            If the task should be stopped, return True
        """
        try:
            # 🔥 Extract the original job_id (if the job_id is tushare_financial_sync_tushare, the original is tushare_financial_sync)
            # Check if job_id ends with data source name (tushare, akshare, baostock)
            original_job_id = job_id
            for data_source in ["tushare", "akshare", "baostock"]:
                if job_id.endswith(f"_{data_source}"):
                    original_job_id = job_id[:-len(f"_{data_source}")]
                    break
            
            # 🔥 Use synchronous MongoDB client queries (to avoid event loop conflicts)
            from pymongo import MongoClient
            from app.core.config import settings
            
            def query_execution():
                sync_client = MongoClient(settings.MONGO_URI)
                sync_db = sync_client[settings.MONGODB_DATABASE]
                try:
                    # 🔥 Only query the currently running tasks (running status), do not query old records in suspended status
                    # Because the suspended record may be an old task that was canceled before, it should not affect the new task
                    query = {
                        "job_id": {"$regex": f"^{original_job_id}(_|$)"},
                        "status": "running"  # 🔥 Only query the running status and ignore the suspended status
                    }
                    execution = sync_db.scheduler_executions.find_one(
                        query,
                        sort=[("started_at", -1)]
                    )
                    
                    # 🔥 If an execution record is found, check whether it is the execution record of the current task.
                    # By checking the timestamp, if the execution record was created within the last minute, it is considered to be the current task.
                    if execution:
                        from datetime import datetime, timedelta
                        execution_time = execution.get("started_at") or execution.get("timestamp") or execution.get("scheduled_time")
                        if execution_time:
                            # If it is a datetime object, compare directly; if it is a string, it needs to be converted
                            if isinstance(execution_time, str):
                                try:
                                    execution_time = datetime.fromisoformat(execution_time.replace('Z', '+00:00'))
                                except:
                                    execution_time = None
                            
                            if execution_time:
                                time_diff = (datetime.now() - execution_time.replace(tzinfo=None)).total_seconds()
                                # If the execution record exceeds 5 minutes, it is considered an old task and the cancellation mark is not checked.
                                if time_diff > 300:  # 5 minutes
                                    logger.debug(f"🔍 The execution record is too old ({time_diff:.0f}seconds ago), ignoring unmark checks")
                                    return None
                    
                    return execution
                finally:
                    sync_client.close()
            
            # 🔥 Execute synchronous query using current event loop
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    execution = await loop.run_in_executor(None, query_execution)
                else:
                    # If the event loop is closed, use synchronous query directly
                    execution = query_execution()
            except RuntimeError:
                # No event loop, use synchronous query directly
                execution = query_execution()
            
            if execution:
                execution_id = str(execution.get("_id", ""))
                execution_job_id = execution.get("job_id", "")
                cancel_requested = execution.get("cancel_requested", False)
                execution_status = execution.get("status", "")
                
                # 🔥 INFO level logs are only output when cancellation or exception status is detected, and DEBUG level is used for normal checks.
                if cancel_requested or execution_status in ["failed", "cancelled"]:
                    logger.info(f"🔍 Check task status: job_id={job_id}, original_job_id={original_job_id}, "
                               f"record found: execution_id={execution_id}, execution_job_id={execution_job_id}, "
                               f"cancel_requested={cancel_requested}, status={execution_status}")
                else:
                    # Use DEBUG level during normal inspection to reduce log output
                    logger.debug(f"🔍 Check task status: job_id={job_id}, original_job_id={original_job_id}, "
                               f"record found: execution_id={execution_id}, execution_job_id={execution_job_id}, "
                               f"cancel_requested={cancel_requested}, status={execution_status}")
                
                # Check if canceled
                if cancel_requested:
                    logger.warning(f"🛑 Cancellation request detected: job_id={job_id}, original_job_id={original_job_id}, "
                                 f"execution_id={execution_id}, execution_job_id={execution_job_id}")
                    return True
                
                # Check if status is failed or canceled
                if execution_status in ["failed", "cancelled"]:
                    logger.warning(f"🛑 The detected task status is {execution_status}: job_id={job_id}, "
                                 f"original_job_id={original_job_id}, execution_job_id={execution_job_id}")
                    return True
            else:
                # 🔥 If no execution record is found, log
                logger.debug(f"⚠️ Execution record not found: job_id={job_id}, original_job_id={original_job_id}")
            
            return False
        except RuntimeError as e:
            # 🔥 Catching event loop related errors
            if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                logger.warning(f"⚠️ Event loop closed, task status check skipped: {job_id}")
                return False
            logger.error(f"❌ Checking task status failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Checking task status failed: {e}")
            return False
    
    async def _sync_symbol_financial_data_async(
        self,
        symbol: str,
        data_source: str,
        provider: Any,
        report_types: List[str],
        financial_service: Any
    ) -> bool:
        """
        Synchronize financial data for a single stock (asynchronous version)
        """
        try:
            # 🔥 Check if the event loop has been closed
            try:
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    logger.warning(f"⚠️ {symbol} Event loop is closed, unable to get financial data ({data_source})")
                    return False
            except RuntimeError:
                logger.warning(f"⚠️ {symbol} Unable to obtain event loop, may be closed ({data_source})")
                return False
            
            # Get financial data
            financial_data = await provider.get_financial_data(symbol)
            
            if not financial_data:
                logger.debug(f"⚠️ {symbol} No financial data ({data_source})")
                return False
            
            saved_count = 0
            try:
                saved_count = await financial_service.save_financial_data(
                    symbol=symbol,
                    financial_data=financial_data,
                    data_source=data_source,
                )
            except RuntimeError as e:
                # 🔥 Catching event loop shutdown errors
                if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                    logger.warning(f"⚠️ {symbol} Event loop closed while saving financial data ({data_source}): {e}")
                    return False
                raise
            
            return saved_count > 0
            
        except RuntimeError as e:
            # 🔥 Catching event loop related errors
            if "shutdown" in str(e).lower() or "closed" in str(e).lower():
                logger.warning(f"⚠️ {symbol} Event loop closed while synchronizing financial data ({data_source}): {e}")
                return False
            logger.error(f"❌ {symbol} Financial data synchronization exception ({data_source}): {e}")
            raise
        except Exception as e:
            logger.error(f"❌ {symbol} Financial data synchronization exception ({data_source}): {e}")
            raise
    
    async def _sync_source_financial_data(
        self,
        data_source: str,
        symbols: List[str],
        report_types: List[str],
        batch_size: int,
        delay_seconds: float
    ) -> FinancialSyncStats:
        """Synchronize financial data from a single data source"""
        stats = FinancialSyncStats()
        stats.total_symbols = len(symbols)
        stats.start_time = datetime.now(timezone.utc)
        
        provider = self.providers[data_source]
        
        # Check data source availability
        if not provider.is_available():
            logger.warning(f"⚠️ {data_source} Data source is not available")
            stats.skipped_count = len(symbols)
            stats.end_time = datetime.now(timezone.utc)
            return stats
        
        # Process stocks in batches
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            
            logger.info(f"📈 {data_source} process batch {i//batch_size + 1}: "
                       f"{len(batch_symbols)} only stocks")
            
            # Concurrent processing of stocks within batches
            tasks = []
            for symbol in batch_symbols:
                task = self._sync_symbol_financial_data(
                    symbol=symbol,
                    data_source=data_source,
                    provider=provider,
                    report_types=report_types
                )
                tasks.append(task)
            
            # Execute concurrent tasks
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Statistics batch results
            for j, result in enumerate(batch_results):
                symbol = batch_symbols[j]
                
                if isinstance(result, Exception):
                    stats.error_count += 1
                    stats.errors.append({
                        "symbol": symbol,
                        "data_source": data_source,
                        "error": str(result),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    logger.error(f"❌ {symbol} Financial data synchronization failed ({data_source}): {result}")
                elif result:
                    stats.success_count += 1
                    logger.debug(f"✅ {symbol} Financial data synchronization successful ({data_source})")
                else:
                    stats.skipped_count += 1
                    logger.debug(f"⏭️ {symbol} Financial data skipped ({data_source})")
            
            # API Current limiting delay
            if i + batch_size < len(symbols):
                await asyncio.sleep(delay_seconds)
        
        stats.end_time = datetime.now(timezone.utc)
        stats.duration = (stats.end_time - stats.start_time).total_seconds()
        
        return stats
    
    async def _sync_symbol_financial_data(
        self,
        symbol: str,
        data_source: str,
        provider: Any,
        report_types: List[str]
    ) -> bool:
        """Synchronize financial data for individual stocks"""
        try:
            # Get financial data
            financial_data = await provider.get_financial_data(symbol)
            
            if not financial_data:
                logger.debug(f"⚠️ {symbol} No financial data ({data_source})")
                return False
            
            saved_count = await self.financial_service.save_financial_data(
                symbol=symbol,
                financial_data=financial_data,
                data_source=data_source,
            )
            
            return saved_count > 0
            
        except Exception as e:
            logger.error(f"❌ {symbol} Financial data synchronization exception ({data_source}): {e}")
            raise
    
    async def _get_stock_symbols(self) -> List[str]:
        """Get a list of stock symbols (remove duplicates)"""
        try:
            # 🔥 Use aggregate queries to deduplicate, ensuring each stock symbol is only counted once
            # Because the same stock may come from multiple data sources (tushare, akshare, baostock), there will be duplicate records
            pipeline = [
                {
                    "$match": {
                        "$or": [
                            {"market_info.market": "CN"},  # new data structure
                            {"category": "stock_cn"},      # old data structure
                            {"market": {"$in": ["motherboard", "GEM", "Science and Technology Innovation Board", "Beijing Exchange"]}}  # By market type
                        ]
                    }
                },
                {
                    "$group": {
                        "_id": "$code"  # Group by stock code to remove duplicates
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "code": "$_id"
                    }
                }
            ]
            cursor = self.db.stock_basic_info.aggregate(pipeline)
            symbols = [doc["code"] async for doc in cursor]
            logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Only unique stock codes (duplication removed)")

            return symbols

        except Exception as e:
            logger.error(f"❌ Failed to get list of stock symbols: {e}")
            return []
    
    async def get_sync_statistics(self) -> Dict[str, Any]:
        """Get sync statistics"""
        try:
            if self.financial_service is None:
                await self.initialize()
            
            return await self.financial_service.get_financial_statistics()
            
        except Exception as e:
            logger.error(f"❌ Failed to obtain synchronization statistics: {e}")
            return {}
    
    async def sync_single_stock(
        self,
        symbol: str,
        data_sources: List[str] = None
    ) -> Dict[str, bool]:
        """Synchronize financial data for individual stocks"""
        if self.db is None:
            await self.initialize()
        
        if data_sources is None:
            data_sources = ["tushare", "akshare", "baostock"]
        
        results = {}
        
        for data_source in data_sources:
            if data_source not in self.providers:
                results[data_source] = False
                continue
            
            try:
                provider = self.providers[data_source]
                
                if not provider.is_available():
                    results[data_source] = False
                    continue
                
                result = await self._sync_symbol_financial_data(
                    symbol=symbol,
                    data_source=data_source,
                    provider=provider,
                    report_types=["quarterly"]
                )
                
                results[data_source] = result
                
            except Exception as e:
                logger.error(f"❌ {symbol} Single stock financial data synchronization failed ({data_source}): {e}")
                results[data_source] = False
        
        return results


# Global service instance
_financial_sync_service = None


async def get_financial_sync_service() -> FinancialDataSyncService:
    """Obtain financial data synchronization service instance"""
    global _financial_sync_service
    if _financial_sync_service is None:
        _financial_sync_service = FinancialDataSyncService()
        await _financial_sync_service.initialize()
    return _financial_sync_service
