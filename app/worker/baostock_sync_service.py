#!/usr/bin/env python3
"""
BaoStock Data synchronization service
Provides batch synchronization function of BaoStock data and integrates into APScheduler scheduling system
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.database import get_database
from app.services.historical_data_service import get_historical_data_service
from tradingagents.dataflows.providers.china.baostock import BaoStockProvider

logger = logging.getLogger(__name__)


@dataclass
class BaoStockSyncStats:
    """BaoStock Synchronization statistics"""
    basic_info_count: int = 0
    quotes_count: int = 0
    historical_records: int = 0
    financial_records: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class BaoStockSyncService:
    """BaoStock Data synchronization service"""

    def __init__(self):
        """
        Initialize synchronization service

        Note: The database connection is in initialize() Asynchronous initialization in method
        """
        try:
            self.settings = get_settings()
            self.provider = BaoStockProvider()
            self.historical_service = None  # Lazy initialization
            self.db = None  # 🔥 Lazy initialization, in initialize() Medium settings
            self._current_job_id = None  # 🔥 Current task ID, used for progress tracking and stop checking

            logger.info("✅ BaoStock Synchronization service initialization successful")
        except Exception as e:
            logger.error(f"❌ BaoStock Sync service initialization failed: {e}")
            raise

    async def initialize(self):
        """Asynchronous initialization service"""
        try:
            # 🔥 Initialize database connection (must be in an asynchronous context)
            from app.core.database import get_mongo_db
            self.db = get_mongo_db()

            # Initialize historical data service
            if self.historical_service is None:
                from app.services.historical_data_service import get_historical_data_service
                self.historical_service = await get_historical_data_service()

            logger.info("✅ BaoStock The asynchronous initialization of the synchronization service is completed")
        except Exception as e:
            logger.error(f"❌ BaoStock Asynchronous initialization of sync service failed: {e}")
            raise
    
    async def sync_stock_basic_info(self, batch_size: int = 100) -> BaoStockSyncStats:
        """
        Synchronize basic stock information
        
        Args:
            batch_size: batch size
            
        Returns:
            Sync statistics
        """
        stats = BaoStockSyncStats()
        
        try:
            logger.info("🔄 Start BaoStock stock basic information synchronization...")
            
            # Get a list of stocks
            stock_list = await self.provider.get_stock_list()
            if not stock_list:
                logger.warning("⚠️ BaoStock Stock list is empty")
                return stats
            
            logger.info(f"📋 Get{len(stock_list)}Only stocks, start batch synchronization...")
            
            # Batch processing
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i + batch_size]
                batch_stats = await self._sync_basic_info_batch(batch)
                
                stats.basic_info_count += batch_stats.basic_info_count
                stats.errors.extend(batch_stats.errors)
                
                logger.info(f"📊 batch progress: {i + len(batch)}/{len(stock_list)}, "
                          f"success: {batch_stats.basic_info_count}, "
                          f"Error: {len(batch_stats.errors)}")
                
                # Avoid API restrictions
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ BaoStock Basic information synchronization completed: {stats.basic_info_count}records")
            
            # 🔥 Update task status to Completed
            job_id = getattr(self, '_current_job_id', None) or "baostock_basic_info_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    # Convert BaoStockSyncStats to dictionary format
                    stats_dict = {
                        "total_processed": stats.basic_info_count,
                        "success_count": stats.basic_info_count,
                        "error_count": len(stats.errors),
                        "errors": [{"error": e} if isinstance(e, str) else e for e in stats.errors]
                    }
                    await mark_job_completed(job_id, stats_dict)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ BaoStock Basic information synchronization failed: {e}")
            stats.errors.append(str(e))
            
            # 🔥 Update task status is failed
            job_id = getattr(self, '_current_job_id', None) or "baostock_basic_info_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, None, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats
    
    async def _sync_basic_info_batch(self, stock_batch: List[Dict[str, Any]]) -> BaoStockSyncStats:
        """Synchronize basic information batches (including valuation data and total market capitalization)"""
        stats = BaoStockSyncStats()

        for stock in stock_batch:
            try:
                code = stock['code']

                # 1. Get basic information
                basic_info = await self.provider.get_stock_basic_info(code)

                if not basic_info:
                    stats.errors.append(f"get{code}Basic information failed")
                    continue

                # 2. Get valuation data (PE, PB, PS, PCF, etc.)
                try:
                    valuation_data = await self.provider.get_valuation_data(code)
                    if valuation_data:
                        # Merge valuation data into basic information
                        basic_info['pe'] = valuation_data.get('pe_ttm')  # Price to Earnings Ratio (TTM)
                        basic_info['pb'] = valuation_data.get('pb_mrq')  # Price to Book Ratio (MRQ)
                        basic_info['pe_ttm'] = valuation_data.get('pe_ttm')
                        basic_info['pb_mrq'] = valuation_data.get('pb_mrq')
                        basic_info['ps'] = valuation_data.get('ps_ttm')  # price to sales ratio
                        basic_info['pcf'] = valuation_data.get('pcf_ttm')  # price to cash ratio
                        basic_info['close'] = valuation_data.get('close')  # latest price

                        # 3. Calculate total market capitalization (need to obtain total share capital)
                        close_price = valuation_data.get('close')
                        if close_price and close_price > 0:
                            # Try to get total share capital from financial data
                            total_shares_wan = await self._get_total_shares(code)
                            if total_shares_wan and total_shares_wan > 0:
                                # Total market value (100 million yuan)= Stock price (yuan)× Total share capital (10,000 shares)/ 10000
                                total_mv_yi = (close_price * total_shares_wan) / 10000
                                basic_info['total_mv'] = total_mv_yi
                                logger.debug(f"✅ {code} Total market capitalization calculation: {close_price}Yuan × {total_shares_wan}10,000 shares / 10000 = {total_mv_yi:.2f}billion")
                            else:
                                logger.debug(f"⚠️ {code} Unable to obtain total share capital, skip market capitalization calculation")

                        logger.debug(f"✅ {code} Valuation data: PE={basic_info.get('pe')}, PB={basic_info.get('pb')}, Market value={basic_info.get('total_mv')}")
                except Exception as e:
                    logger.warning(f"⚠️ get{code}Valuation data failed: {e}")
                    # Failure to obtain valuation data does not affect basic information synchronization

                # 4. Update database
                await self._update_stock_basic_info(basic_info)
                stats.basic_info_count += 1

            except Exception as e:
                stats.errors.append(f"Process{stock.get('code', 'unknown')}failed: {e}")

        return stats
    
    async def _get_total_shares(self, code: str) -> Optional[float]:
        """
        Get the total share capital of stocks (10,000 shares)

        Args:
            code: Stock code

        Returns:
            Total share capital (10,000 shares), returned if acquisition fails None
        """
        try:
            # Try to get total share capital from financial data
            financial_data = await self.provider.get_financial_data(code)

            if financial_data:
                # BaoStock Total Equity Field in Financial Data
                # Profitability data includes totalShare (total share capital, unit: 10,000 shares)
                profit_data = financial_data.get('profit_data', {})
                if profit_data:
                    total_shares = profit_data.get('totalShare')
                    if total_shares:
                        return self._safe_float(total_shares)

                # Growth capacity data may also include total equity
                growth_data = financial_data.get('growth_data', {})
                if growth_data:
                    total_shares = growth_data.get('totalShare')
                    if total_shares:
                        return self._safe_float(total_shares)

            # If there is no financial data, try to get it from the data already in the database
            collection = self.db.stock_financial_data
            doc = await collection.find_one(
                {"code": code},
                {"total_shares": 1, "totalShare": 1},
                sort=[("report_period", -1)]
            )

            if doc:
                total_shares = doc.get('total_shares') or doc.get('totalShare')
                if total_shares:
                    return self._safe_float(total_shares)

            return None

        except Exception as e:
            logger.debug(f"get{code}total equity failed: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        """safe conversion to floating point"""
        try:
            if value is None or value == '' or value == 'None':
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    async def _update_stock_basic_info(self, basic_info: Dict[str, Any]):
        """Update basic stock information to the database"""
        try:
            collection = self.db.stock_basic_info

            # Make sure the symbol field exists (normalized field)
            if "symbol" not in basic_info and "code" in basic_info:
                basic_info["symbol"] = basic_info["code"]

            # 🔥 Make sure the source field exists
            if "source" not in basic_info:
                basic_info["source"] = "baostock"

            # 🔥 Use (code, source) Union query conditions
            await collection.update_one(
                {"code": basic_info["code"], "source": "baostock"},
                {"$set": basic_info},
                upsert=True
            )

        except Exception as e:
            logger.error(f"❌ Failed to update basic information to database: {e}")
            raise
    
    async def sync_daily_quotes(self, batch_size: int = 50) -> BaoStockSyncStats:
        """
        Synchronized daily K-line data (latest trading day)

        Note: BaoStock does not support real-time market conditions. This method obtains the daily K-line data of the latest trading day.

        Args:
            batch_size: batch size

        Returns:
            Sync statistics
        """
        stats = BaoStockSyncStats()

        try:
            logger.info("🔄 Start BaoStock daily K-line synchronization (latest trading day)...")
            logger.info("ℹ️ Note: BaoStock does not support real-time market conditions. This task synchronizes the daily K-line data of the latest trading day.")

            # Get stock list from database
            collection = self.db.stock_basic_info
            cursor = collection.find({"source": "baostock"}, {"code": 1})
            stock_codes = [doc["code"] async for doc in cursor]

            if not stock_codes:
                logger.warning("⚠️ There is no BaoStock stock data in the database")
                return stats

            logger.info(f"📈 Start syncing{len(stock_codes)}Daily K-line data of only stocks...")

            # Batch processing
            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                batch_stats = await self._sync_quotes_batch(batch)

                stats.quotes_count += batch_stats.quotes_count
                stats.errors.extend(batch_stats.errors)

                logger.info(f"📊 batch progress: {i + len(batch)}/{len(stock_codes)}, "
                          f"success: {batch_stats.quotes_count}, "
                          f"Error: {len(batch_stats.errors)}")

                # Avoid API restrictions
                await asyncio.sleep(0.2)

            logger.info(f"✅ BaoStock Daily K-line synchronization completed: {stats.quotes_count}records")
            
            # 🔥 Update task status to Completed
            job_id = getattr(self, '_current_job_id', None) or "baostock_daily_quotes_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    # Convert BaoStockSyncStats to dictionary format
                    stats_dict = {
                        "total_processed": len(stock_codes),
                        "success_count": stats.quotes_count,
                        "error_count": len(stats.errors),
                        "errors": [{"error": e} if isinstance(e, str) else e for e in stats.errors]
                    }
                    await mark_job_completed(job_id, stats_dict)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")
            
            return stats

        except Exception as e:
            logger.error(f"❌ BaoStock Daily K line synchronization failed: {e}")
            stats.errors.append(str(e))
            
            # 🔥 Update task status is failed
            job_id = getattr(self, '_current_job_id', None) or "baostock_daily_quotes_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, None, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats
    
    async def _sync_quotes_batch(self, code_batch: List[str]) -> BaoStockSyncStats:
        """Synchronous daily K-line batches"""
        stats = BaoStockSyncStats()

        for code in code_batch:
            try:
                # Note: get_stock_quotes actually returns the latest daily K-line data, not real-time quotes.
                quotes = await self.provider.get_stock_quotes(code)

                if quotes:
                    # Update database
                    await self._update_stock_quotes(quotes)
                    stats.quotes_count += 1
                else:
                    stats.errors.append(f"get{code}Daily K line failed")

            except Exception as e:
                stats.errors.append(f"Process{code}Daily K line failed: {e}")

        return stats

    async def _update_stock_quotes(self, quotes: Dict[str, Any]):
        """Update the stock daily K-line to the database"""
        try:
            collection = self.db.market_quotes

            # Make sure the symbol field exists
            code = quotes.get("code", "")
            if code and "symbol" not in quotes:
                quotes["symbol"] = code

            # Update or insert using upsert
            await collection.update_one(
                {"code": code},
                {"$set": quotes},
                upsert=True
            )

        except Exception as e:
            logger.error(f"❌ Failed to update daily K-line to database: {e}")
            raise
    
    async def sync_historical_data(self, days: int = 30, batch_size: int = 20, period: str = "daily", incremental: bool = True, symbols: List[str] = None) -> BaoStockSyncStats:
        """
        Synchronize historical data

        Args:
            days: Number of days to sync (if>=3650 Then synchronize the entire history, if<0 then use incremental mode)
            batch_size: batch size
            period: data period (daily/weekly/monthly)
            incremental: Whether to sync incrementally (each stock starts from its own last date)

        Returns:
            Sync statistics
        """
        stats = BaoStockSyncStats()

        try:
            # 🔥 When executing in a thread in the thread pool, the database connection needs to be reinitialized.
            from app.core.database import bind_loop_safe_mongo_db
            self.db = bind_loop_safe_mongo_db(self)
            
            period_name = {"daily": "daily line", "weekly": "perimeter", "monthly": "monthly line"}.get(period, "daily line")

            # Calculate date range
            end_date = datetime.now().strftime('%Y-%m-%d')

            # Determine synchronization mode
            use_incremental = incremental or days < 0

            # 🔥 Incremental synchronization time check: If incremental synchronization and the end date is today, and the current time is 18:00 before, skip synchronization
            if use_incremental and end_date == datetime.now().strftime('%Y-%m-%d'):
                current_time = datetime.now()
                cutoff_time = current_time.replace(hour=18, minute=0, second=0, microsecond=0)
                
                if current_time < cutoff_time:
                    skip_message = (
                        f"⏰ Incremental sync skip: current time {current_time.strftime('%H:%M:%S')} earlier than 18:00, "
                        f"The data source may not yet have data for the current day. It is recommended to 18:00 Then perform incremental synchronization."
                    )
                    logger.info(skip_message)
                    stats.errors.append(skip_message)
                    return stats

            # Get stock list from database
            collection = self.db.stock_basic_info
            logger.info(f"🔍 [BaoStock] Query the stock list in the database (source=baostock)...")
            try:
                cursor = collection.find({"source": "baostock"}, {"code": 1})
                stock_codes = [doc["code"] async for doc in cursor]
                logger.info(f"📊 [BaoStock] Query results: found {len(stock_codes)} only stocks")
            except RuntimeError as loop_error:
                # 🔥 If an event loop conflict error occurs, re-create the database connection
                if "attached to a different loop" in str(loop_error) or "different loop" in str(loop_error):
                    logger.warning(f"⚠️ [BaoStock] Event loop conflict detected, rebind database agent: {loop_error}")
                    self.db = bind_loop_safe_mongo_db(self)
                    # Retry query
                    collection = self.db.stock_basic_info
                    cursor = collection.find({"source": "baostock"}, {"code": 1})
                    stock_codes = [doc["code"] async for doc in cursor]
                    logger.info(f"📊 [BaoStock] Query results: found {len(stock_codes)} Stock only (connection re-created)")
                else:
                    raise

            if not stock_codes:
                error_msg = "There is no BaoStock stock data in the database. Please perform the BaoStock basic information synchronization task first."
                logger.error(f"❌ {error_msg} (source=baostock)")
                
                # 🔥 Mark task as failed
                job_id = getattr(self, '_current_job_id', None) or "baostock_historical_sync"
                if job_id:
                    try:
                        from app.services.scheduler_service import mark_job_completed
                        await mark_job_completed(
                            job_id=job_id,
                            error_message=error_msg
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ Update task failed status failed: {e}")
                
                # 🔥 Throw an exception to ensure the task is marked as failed
                raise ValueError(error_msg)

            if use_incremental:
                logger.info(f"🔄 start BaoStock{period_name}Historical data synchronization (incremental mode: Each stock from the last date to{end_date})...")
            elif days >= 3650:
                logger.info(f"🔄 start BaoStock{period_name}Historical data synchronization (whole history: 1990-01-01 Arrive{end_date})...")
            else:
                logger.info(f"🔄 start BaoStock{period_name}Historical data synchronization (Recently{days}The day has come{end_date})...")

            logger.info(f"📊 Start syncing{len(stock_codes)}Historical data for only stocks...")

            # Batch processing
            job_id = getattr(self, '_current_job_id', None) or "baostock_historical_sync"
            total_batches = (len(stock_codes) + batch_size - 1) // batch_size
            processed_count = 0  # 🔥 Processed quantity (add 1 immediately after each stock is processed)
            
            was_cancelled = False  # 🔥 Whether marking is stopped due to cancellation
            
            for i in range(0, len(stock_codes), batch_size):
                # 🔥 Check if the task should be stopped
                if job_id and await self._should_stop(job_id):
                    logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting...")
                    stats.stopped = True
                    was_cancelled = True
                    break

                batch = stock_codes[i:i + batch_size]
                batch_num = i // batch_size + 1
                logger.info(f"🔄 [BaoStock] process batch {batch_num}/{total_batches}: {len(batch)} only stocks")
                
                # 🔥 Pass processed_count and total_stocks so that the batch processing function can update the progress in real time
                batch_stats_dict = await self._sync_historical_batch(
                    batch, days, end_date, period, use_incremental, job_id,
                    processed_count=processed_count,  # 🔥 Pass the current processed quantity
                    total_stocks=len(stock_codes)  # 🔥 total quantity delivered
                )
                
                # 🔥 Update statistics
                batch_records = batch_stats_dict.get("historical_records", 0)
                batch_errors = batch_stats_dict.get("errors", [])
                stats.historical_records += batch_records
                stats.errors.extend(batch_errors)
                
                # 🔥 Update the processed quantity (the batch processing function returns the actual number of stocks processed)
                processed_count = batch_stats_dict.get("processed_count", processed_count + len(batch))
                
                # 🔥 Check if stopped
                if batch_stats_dict.get("stopped", False):
                    stats.stopped = True
                    break
                
                logger.info(f"📊 [BaoStock] batch progress: {processed_count}/{len(stock_codes)}, "
                          f"record: {batch_records}, "
                          f"Error: {len(batch_errors)}")
                
                # Avoid API restrictions
                await asyncio.sleep(0.5)
            
            # 🔥 If the task is canceled, the update status is canceled
            if was_cancelled:
                logger.warning(f"🛑 Task {job_id} Canceled, update status...")
                try:
                    from app.services.scheduler_service import update_job_progress
                    from app.core.database import get_mongo_db_sync, get_redis_sync_client
                    from app.core.redis_client import RedisKeys
                    
                    # Update MongoDB status
                    db = get_mongo_db_sync()
                    # 🔥 First find the latest running record, and then update it using _id
                    from pymongo import DESCENDING
                    latest_execution = db.scheduler_executions.find_one(
                        {"job_id": job_id, "status": "running"},
                        sort=[("timestamp", DESCENDING)]
                    )
                    if latest_execution:
                        db.scheduler_executions.update_one(
                            {"_id": latest_execution["_id"]},
                            {
                                "$set": {
                                    "status": "cancelled",
                                    "updated_at": datetime.utcnow(),
                                    "message": f"Task canceled (processed {processed_count}/{len(stock_codes)}) ",
                                    "progress": int((processed_count / len(stock_codes)) * 100) if len(stock_codes) > 0 else 0,
                                    "processed_items": processed_count,
                                    "total_items": len(stock_codes)
                                }
                            }
                        )
                    else:
                        # If no running record is found, try to find and update records with any status
                        any_execution = db.scheduler_executions.find_one(
                            {"job_id": job_id},
                            sort=[("timestamp", DESCENDING)]
                        )
                        if any_execution:
                            db.scheduler_executions.update_one(
                                {"_id": any_execution["_id"]},
                                {
                                    "$set": {
                                        "status": "cancelled",
                                        "updated_at": datetime.utcnow(),
                                        "message": f"Task canceled (processed {processed_count}/{len(stock_codes)}) ",
                                        "progress": int((processed_count / len(stock_codes)) * 100) if len(stock_codes) > 0 else 0,
                                        "processed_items": processed_count,
                                        "total_items": len(stock_codes)
                                    }
                                }
                            )
                    
                    # 🔥 Update the Redis progress cache and set the status to"cancelled", Keep current progress information
                    redis_client = get_redis_sync_client()
                    if redis_client:
                        redis_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                        import json
                        
                        # 🔥 Read the current progress data (if it exists)
                        existing_progress_str = redis_client.get(redis_key)
                        if existing_progress_str:
                            try:
                                progress_data = json.loads(existing_progress_str)
                            except:
                                progress_data = {}
                        else:
                            progress_data = {}
                        
                        # 🔥 The update status is"cancelled", and retain current progress information
                        progress_percent = int((processed_count / len(stock_codes)) * 100) if len(stock_codes) > 0 else 0
                        progress_data.update({
                            "status": "cancelled",
                            "progress": progress_percent,
                            "message": f"Task canceled (processed {processed_count}/{len(stock_codes)}) ",
                            "processed_items": processed_count,
                            "total_items": len(stock_codes),
                            "updated_at": datetime.utcnow().isoformat()
                        })
                        
                        # 🔥 save to Redis
                        redis_client.setex(
                            redis_key,
                            3600,  # 1 hours TTL
                            json.dumps(progress_data, ensure_ascii=False, default=str)
                        )
                        logger.info(f"✅ The Redis cache has been updated and the task status is cancelled: job_id={job_id}, progress={progress_percent}%")
                    
                    logger.info(f"✅ Task {job_id} Status updated to Canceled")
                except Exception as cancel_error:
                    logger.error(f"❌ Failed to update task cancellation status: {cancel_error}")
                
                return stats
            
            logger.info(f"✅ BaoStock Historical data synchronization completed: {stats.historical_records}records")
            
            # 🔥 Update task status to Completed
            job_id = getattr(self, '_current_job_id', None) or "baostock_historical_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    # Convert BaoStockSyncStats to dictionary format
                    stats_dict = {
                        "total_processed": len(stats.errors) + stats.historical_records,  # Estimated total
                        "success_count": stats.historical_records,
                        "error_count": len(stats.errors),
                        "errors": [{"error": e} if isinstance(e, str) else e for e in stats.errors]
                    }
                    await mark_job_completed(job_id, stats_dict)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")
            
            return stats
            
        except Exception as e:
            # 🔥 Check whether it is a task cancellation exception
            from app.services.scheduler_service import TaskCancelledException
            if isinstance(e, TaskCancelledException) or "Cancel" in str(e) or "cancelled" in str(e).lower():
                logger.warning(f"🛑 BaoStock The historical data synchronization task has been cancelled.: {e}")
                stats.stopped = True
                
                # Update status is canceled
                job_id = getattr(self, '_current_job_id', None) or "baostock_historical_sync"
                if job_id:
                    try:
                        from app.core.database import get_mongo_db_sync, get_redis_sync_client
                        from app.core.redis_client import RedisKeys
                        
                        # Update MongoDB status
                        db = get_mongo_db_sync()
                        # 🔥 Get current progress information (if it exists)
                        from pymongo import DESCENDING
                        current_execution = db.scheduler_executions.find_one(
                            {"job_id": job_id, "status": "running"},
                            sort=[("timestamp", DESCENDING)]
                        )
                        processed_count = current_execution.get("processed_items", 0) if current_execution else 0
                        total_items = current_execution.get("total_items", 0) if current_execution else 0
                        
                        # 🔥 Update using the found record_id
                        if current_execution:
                            db.scheduler_executions.update_one(
                                {"_id": current_execution["_id"]},
                                {
                                    "$set": {
                                        "status": "cancelled",
                                        "updated_at": datetime.utcnow(),
                                        "message": f"Task canceled: {str(e)}",
                                        "progress": int((processed_count / total_items) * 100) if total_items > 0 else 0,
                                        "processed_items": processed_count,
                                        "total_items": total_items
                                    }
                                }
                            )
                        else:
                            # If no running record is found, try to find and update records with any status
                            any_execution = db.scheduler_executions.find_one(
                                {"job_id": job_id},
                                sort=[("timestamp", DESCENDING)]
                            )
                            if any_execution:
                                db.scheduler_executions.update_one(
                                    {"_id": any_execution["_id"]},
                                    {
                                        "$set": {
                                            "status": "cancelled",
                                            "updated_at": datetime.utcnow(),
                                            "message": f"Task canceled: {str(e)}",
                                            "progress": int((processed_count / total_items) * 100) if total_items > 0 else 0,
                                            "processed_items": processed_count,
                                            "total_items": total_items
                                        }
                                    }
                                )
                        
                        # 🔥 Update Redis progress cache
                        redis_client = get_redis_sync_client()
                        if redis_client:
                            redis_key = RedisKeys.SCHEDULER_JOB_PROGRESS.format(job_id=job_id)
                            import json
                            
                            progress_percent = int((processed_count / total_items) * 100) if total_items > 0 else 0
                            progress_data = {
                                "status": "cancelled",
                                "progress": progress_percent,
                                "message": f"Task canceled: {str(e)}",
                                "processed_items": processed_count,
                                "total_items": total_items,
                                "updated_at": datetime.utcnow().isoformat()
                            }
                            
                            redis_client.setex(
                                redis_key,
                                3600,  # 1 hours TTL
                                json.dumps(progress_data, ensure_ascii=False, default=str)
                            )
                            logger.info(f"✅ The Redis cache has been updated and the task status is cancelled: job_id={job_id}, progress={progress_percent}%")
                        
                        logger.info(f"✅ Task {job_id} Status updated to Canceled")
                    except Exception as cancel_error:
                        logger.error(f"❌ Failed to update task cancellation status: {cancel_error}")
                
                return stats
            
            # Other exceptions are recorded as errors
            logger.error(f"❌ BaoStock Historical data synchronization failed: {e}")
            stats.errors.append(str(e))
            
            # 🔥 Update task status is failed
            job_id = getattr(self, '_current_job_id', None) or "baostock_historical_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, None, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats
    
    async def _sync_historical_batch(
        self,
        code_batch: List[str],
        days: int,
        end_date: str,
        period: str = "daily",
        incremental: bool = False,
        job_id: str = None,
        processed_count: int = 0,  # 🔥 Quantity currently processed
        total_stocks: int = 0  # 🔥 Total number of shares
    ) -> Dict[str, Any]:
        """Synchronize historical data batches"""
        stats = BaoStockSyncStats()
        stats_dict = {
            "historical_records": 0,
            "errors": [],
            "processed_count": processed_count  # 🔥 Save the current processed quantity
        }

        for idx, code in enumerate(code_batch):
            # 🔥 Check if the task should be stopped
            if job_id and await self._should_stop(job_id):
                logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting batch processing...")
                stats.stopped = True
                stats_dict["stopped"] = True
                break
            
            # 🔥 Each time a stock is processed, the processed quantity is immediately updated (regardless of success or failure)
            processed_count += 1
            stats_dict["processed_count"] = processed_count
            
            try:
                # Determine the start date of the stock
                if incremental:
                    # Incremental synchronization: Get the last date of the stock
                    start_date = await self._get_last_sync_date(code)
                    logger.debug(f"📅 {code}: from {start_date} Start syncing")
                elif days >= 3650:
                    # Full history synchronized
                    start_date = "1990-01-01"
                else:
                    # Fixed number of days synchronization
                    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

                logger.debug(f"🔄 [BaoStock] get {code} historical data: {start_date} Arrive {end_date}")
                hist_data = await self.provider.get_historical_data(code, start_date, end_date, period)

                if hist_data is not None and not hist_data.empty:
                    logger.info(f"✅ [BaoStock] {code} Get {len(hist_data)} historical data, start saving...")
                    # Update database
                    records_count = await self._update_historical_data(code, hist_data, period)
                    stats.historical_records += records_count
                    stats_dict["historical_records"] = stats.historical_records
                    logger.info(f"✅ [BaoStock] {code} Saved successfully: {records_count} records")
                else:
                    logger.warning(f"⚠️ [BaoStock] {code} No historical data was obtained")
                    error_msg = f"get{code}Historical data failed"
                    stats.errors.append(error_msg)
                    stats_dict["errors"].append(error_msg)

            except Exception as e:
                logger.error(f"❌ [BaoStock] {code} Historical data synchronization failed: {e}", exc_info=True)
                error_msg = f"Process{code}Historical data failed: {e}"
                stats.errors.append(error_msg)
                stats_dict["errors"].append(error_msg)
            
            # 🔥 Every time a stock is processed (regardless of success or failure), the progress is updated immediately
            if job_id and total_stocks > 0:
                try:
                    from app.services.scheduler_service import update_job_progress, TaskCancelledException
                    
                    # 🔥 Calculate progress percentage
                    progress_percent = int((processed_count / total_stocks) * 100) if total_stocks > 0 else 0
                    
                    # 🔥 Build progress messages
                    progress_message = f"Synchronizing BaoStock historical data ({processed_count}/{total_stocks})"
                    
                    # 🔥 If there is an error, include error information in the message
                    if len(stats_dict.get("errors", [])) > 0:
                        recent_errors = stats_dict.get("errors", [])[-3:]  # Only take the last 3 errors
                        if recent_errors:
                            error_summary = []
                            for error in recent_errors:
                                error_str = error if isinstance(error, str) else str(error)
                                if error_str:
                                    # Extract key error information
                                    if "Historical data is empty" in error_str or "Not obtained" in error_str:
                                        error_summary.append("Data is empty")
                                    elif "network" in error_str or "connect" in error_str:
                                        error_summary.append("network problems")
                                    else:
                                        # Truncate the first 30 characters
                                        short_error = error_str[:30] + "..." if len(error_str) > 30 else error_str
                                        error_summary.append(short_error)
                            
                            if error_summary:
                                # Remove duplicates and show only the first 2 different error types
                                unique_errors = list(set(error_summary))[:2]
                                progress_message += f" | Encountered an error: {', '.join(unique_errors)}"
                    
                    await update_job_progress(
                        job_id=job_id,
                        progress=progress_percent,
                        message=progress_message,
                        total_items=total_stocks,
                        processed_items=processed_count
                    )
                except TaskCancelledException:
                    logger.warning(f"⚠️ BaoStock The historical data synchronization task was canceled by the user (Processed {processed_count}/{total_stocks})")
                    stats.stopped = True
                    stats_dict["stopped"] = True
                    break
                except Exception as progress_error:
                    # 🔥 Failure in progress update should not affect task execution
                    logger.debug(f"⚠️ Update progress failed (execution continues): {progress_error}")

        # 🔥 Returns dictionary format, containing processed_count
        stats_dict.update({
            "historical_records": stats.historical_records,
            "errors": stats.errors,
            "stopped": getattr(stats, 'stopped', False)
        })
        return stats_dict

    async def _should_stop(self, job_id: str) -> bool:
        """
        Check if the task should be stopped

        Args:
            job_id: Task ID

        Returns:
            should it stop
        """
        try:
            # 🔥 Query execution records, check cancel_requested flag and task status
            # Not only checks the running status, but also checks the failed/cancelled/suspended status
            execution = await self.db.scheduler_executions.find_one(
                {"job_id": job_id},
                sort=[("timestamp", -1)]
            )

            if not execution:
                return False

            # Check the cancellation request flag
            if execution.get("cancel_requested"):
                logger.info(f"🛑 Task {job_id} Upon receipt of a cancellation request, execution should be stopped")
                return True

            # 🔥 Check task status: if the task has been marked as failed, canceled or pending, it should also be stopped
            status = execution.get("status")
            if status in ["failed", "cancelled", "suspended"]:
                logger.info(f"🛑 Task {job_id} The status is {status}, Execution should be stopped")
                return True

            return False

        except Exception as e:
            logger.error(f"❌ Checking task stop flag failed: {e}")
            return False

    async def _update_historical_data(self, code: str, hist_data, period: str = "daily") -> int:
        """Update historical data to database"""
        try:
            if hist_data is None or hist_data.empty:
                logger.warning(f"⚠️ {code} Historical data is empty, skip saving")
                return 0

            # 🔥 Ensure historical_service is initialized (if None, created with current db connection)
            if self.historical_service is None:
                from app.services.historical_data_service import get_historical_data_service
                self.historical_service = await get_historical_data_service()
            
            # 🔥 Make sure historical_service uses the correct database connection (important when executing in a thread pool)
            if self.db is not None:
                self.historical_service.db = self.db
                self.historical_service.collection = self.db.stock_daily_quotes

            # Save to unified historical data collection
            logger.info(f"💾 [BaoStock] save {code} Historical data to database ({len(hist_data)} records)...")
            saved_count = await self.historical_service.save_historical_data(
                symbol=code,
                data=hist_data,
                data_source="baostock",
                market="CN",
                period=period
            )
            logger.info(f"✅ [BaoStock] {code} Data saving completed: {saved_count} records")

            # Also update the meta information of the market_quotes collection (to maintain compatibility)
            if self.db is not None:
                collection = self.db.market_quotes
                latest_record = hist_data.iloc[-1] if not hist_data.empty else None

                await collection.update_one(
                    {"code": code},
                    {"$set": {
                        "historical_data_updated": datetime.now(),
                        "latest_historical_date": latest_record.get('date') if latest_record is not None else None,
                        "historical_records_count": saved_count
                    }},
                    upsert=True
                )

            return saved_count

        except Exception as e:
            logger.error(f"❌ Failed to update historical data to database: {e}")
            return 0
    
    async def _get_last_sync_date(self, symbol: str = None) -> str:
        """
        Get last sync date

        Args:
            symbol: Stock symbol, if provided returns the last date for this stock+1 day

        Returns:
            date string (YYYY-MM-DD)
        """
        try:
            # 🔥 Ensure historical_service is initialized (if None, created with current db connection)
            if self.historical_service is None:
                from app.services.historical_data_service import get_historical_data_service
                self.historical_service = await get_historical_data_service()
            
            # 🔥 Make sure historical_service uses the correct database connection (important when executing in a thread pool)
            if self.db is not None:
                self.historical_service.db = self.db
                self.historical_service.collection = self.db.stock_daily_quotes

            if symbol:
                # Get the latest date for a specific stock
                latest_date = await self.historical_service.get_latest_date(symbol, "baostock")
                if latest_date:
                    # Returns the day after the last date (to avoid repeated synchronization)
                    try:
                        last_date_obj = datetime.strptime(latest_date, '%Y-%m-%d')
                        next_date = last_date_obj + timedelta(days=1)
                        next_date_str = next_date.strftime('%Y-%m-%d')
                        
                        # 🔥 Check: If next_date is greater than today, it means that the data is already the latest and no synchronization is required.
                        # Returns today's date (like this start_date == end_date, BaoStock Empty data will be returned but no error will be reported)
                        today_str = datetime.now().strftime('%Y-%m-%d')
                        if next_date_str > today_str:
                            logger.debug(f"📅 {symbol}: last date {latest_date} the next day {next_date_str} greater than today {today_str}, The data is the latest, return today s date")
                            return today_str
                        
                        return next_date_str
                    except ValueError:
                        # If the date format is incorrect, return directly
                        return latest_date
                else:
                    # 🔥 When there is no historical data, synchronize all data starting from the launch date (instead of only synchronizing for 30 days)
                    if self.db is not None:
                        stock_info = await self.db.stock_basic_info.find_one(
                            {"code": symbol, "source": "baostock"},
                            {"list_date": 1}
                        )
                        if stock_info and stock_info.get("list_date"):
                            list_date = stock_info["list_date"]
                            # Handle different date formats
                            if isinstance(list_date, str):
                                # Trying to parse a date string
                                try:
                                    # Try YYYY-MM-DD format
                                    if len(list_date) >= 10:
                                        parsed_date = datetime.strptime(list_date[:10], '%Y-%m-%d')
                                        return parsed_date.strftime('%Y-%m-%d')
                                    # Try YYYYMMDD format
                                    elif len(list_date) == 8:
                                        parsed_date = datetime.strptime(list_date, '%Y%m%d')
                                        return parsed_date.strftime('%Y-%m-%d')
                                except ValueError:
                                    pass
                            elif isinstance(list_date, datetime):
                                return list_date.strftime('%Y-%m-%d')
                    
                    # 🔥 If the listing date cannot be obtained, return to 1990-01-01 (full history synchronization)
                    logger.info(f"📅 {symbol}: No historical data and listing date found, full synchronization started from 1990-01-01")
                    return "1990-01-01"

            # By default, 1990-01-01 is returned (full history synchronization, not 30 days ago)
            return "1990-01-01"

        except Exception as e:
            logger.error(f"❌ Failed to get last sync date {symbol}: {e}")
            # 🔥 When an error occurs, 1990-01-01 is returned (full history synchronization) to ensure no data leakage.
            return "1990-01-01"

    async def check_service_status(self) -> Dict[str, Any]:
        """Check service status"""
        try:
            # 🔥 Critical fix: reacquire database connection on every use, ensure correct event loop is used
            # 🔥 This can avoid event loop conflicts when executing in scheduled tasks
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            
            # Test BaoStock connection
            connection_ok = await self.provider.test_connection()
            
            # Check database connection
            db_ok = True
            try:
                await db.stock_basic_info.count_documents({})
            except Exception:
                db_ok = False
            
            # Statistics
            basic_info_count = await db.stock_basic_info.count_documents({"source": "baostock"})
            quotes_count = await db.market_quotes.count_documents({"source": "baostock"})
            
            return {
                "service": "BaoStock Synchronization service",
                "baostock_connection": connection_ok,
                "database_connection": db_ok,
                "basic_info_count": basic_info_count,
                "quotes_count": quotes_count,
                "status": "healthy" if connection_ok and db_ok else "unhealthy",
                "last_check": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ BaoStock Service status check failed: {e}", exc_info=True)
            return {
                "service": "BaoStock Synchronization service",
                "status": "error",
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }


# APScheduler Compatible task functions
async def _check_task_running(job_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if an instance of the task is already running
    
    Args:
        job_id: Task ID
        
    Returns:
        (is_running, running_instance_id): Whether it is running, the running instance ID
    """
    try:
        from pymongo import MongoClient
        from app.core.config import settings
        from datetime import timedelta
        from app.services.scheduler_service import get_utc8_now
        
        sync_client = MongoClient(settings.MONGO_URI)
        sync_db = sync_client[settings.MONGODB_DATABASE]
        
        # 🔥 Find if there are any running instances (excluding tasks that have timed out)
        # If a task runs for more than 30 minutes, it is considered a zombie task and new tasks are not blocked from execution.
        threshold_time = get_utc8_now() - timedelta(minutes=30)
        
        running_instance = sync_db.scheduler_executions.find_one(
            {
                "job_id": job_id, 
                "status": "running",
                "timestamp": {"$gte": threshold_time}  # Only consider running tasks within the last 30 minutes
            },
            sort=[("timestamp", -1)]
        )
        
        # 🔥 If a running task that times out is found, it is automatically marked as failed.
        if not running_instance:
            # Check if there are any running tasks that have timed out
            zombie_instance = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": "running",
                    "timestamp": {"$lt": threshold_time}
                },
                sort=[("timestamp", -1)]
            )
            
            if zombie_instance:
                # Automatically marked as failed
                sync_db.scheduler_executions.update_one(
                    {"_id": zombie_instance["_id"]},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": "Task execution times out or process terminates abnormally (automatic detection)",
                            "updated_at": get_utc8_now()
                        }
                    }
                )
                logger.warning(f"⚠️ Timeout tasks are detected and automatically marked as failed: {job_id} (start time: {zombie_instance.get('timestamp')})")
        
        sync_client.close()
        
        if running_instance:
            return True, str(running_instance["_id"])
        return False, None
    except Exception as e:
        logger.warning(f"⚠️ Failed to check task running status: {e}")
        return False, None


async def run_baostock_basic_info_sync(**kwargs):
    """
    Run BaoStock basic information synchronization task

    🔥 Use unified thread pool service execution to avoid blocking the main event loop and ensure API response
    """
    job_id = "baostock_basic_info_sync"
    
    # 🔥 Allow execution when manually triggered or forced (even if there is a running record)
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    if not manual_trigger and not force_execute:
        # 🔥 Check whether there is already an instance running (check only if it is not triggered manually and is not forced to execute)
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    else:
        if manual_trigger:
            logger.info(f"🔧 [APScheduler] Manually trigger execution and allow execution (even if there is a running record)")
        if force_execute:
            logger.info(f"🔧 [APScheduler] Force execution, skip concurrency checks")
    
    try:
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        unified_service = await get_unified_thread_pool_sync_service()
        service = BaoStockSyncService()
        await service.initialize()  # 🔥 Must be initialized first
        service._current_job_id = job_id
        sync_result = await unified_service.execute_sync_method(
            sync_method=service.sync_stock_basic_info,
            method_kwargs={},
            job_id=job_id,
            rate_limit_per_minute=300,
        )
        if sync_result.success:
            stats = sync_result.result
            logger.info(f"🎯 BaoStock Basic information synchronization completed: {stats.basic_info_count}records, {len(stats.errors)}errors")
            return stats
        elif sync_result.error and ("Cancel" in sync_result.error or "cancelled" in sync_result.error.lower()):
            logger.info(f"ℹ️ BaoStock The basic information synchronization task has been canceled by the user")
            return {"cancelled": True, "message": sync_result.error}
        else:
            raise RuntimeError(sync_result.error or "Sync failed")
    except Exception as e:
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ BaoStock The basic information synchronization task has been canceled by the user")
            return {"cancelled": True, "message": str(e)}
        logger.error(f"❌ BaoStock Basic information synchronization task failed: {e}")
        raise


async def run_baostock_daily_quotes_sync(**kwargs):
    """
    Run BaoStock daily K-line synchronization task (latest trading day)

    🔥 Use unified thread pool service execution to avoid blocking the main event loop and ensure API response
    """
    job_id = "baostock_daily_quotes_sync"
    
    # 🔥 Allow execution when manually triggered or forced (even if there is a running record)
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    if not manual_trigger and not force_execute:
        # 🔥 Check whether there is already an instance running (check only if it is not triggered manually and is not forced to execute)
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    else:
        if manual_trigger:
            logger.info(f"🔧 [APScheduler] Manually trigger execution and allow execution (even if there is a running record)")
        if force_execute:
            logger.info(f"🔧 [APScheduler] Force execution, skip concurrency checks")
    
    try:
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        unified_service = await get_unified_thread_pool_sync_service()
        service = BaoStockSyncService()
        await service.initialize()  # 🔥 Must be initialized first
        service._current_job_id = job_id
        sync_result = await unified_service.execute_sync_method(
            sync_method=service.sync_daily_quotes,
            method_kwargs={},
            job_id=job_id,
            rate_limit_per_minute=300,
        )
        if sync_result.success:
            stats = sync_result.result
            logger.info(f"🎯 BaoStock Daily K-line synchronization completed: {stats.quotes_count}records, {len(stats.errors)}errors")
            return stats
        elif sync_result.error and ("Cancel" in sync_result.error or "cancelled" in sync_result.error.lower()):
            logger.info(f"ℹ️ BaoStock The daily K-line synchronization task has been canceled by the user")
            return {"cancelled": True, "message": sync_result.error}
        else:
            raise RuntimeError(sync_result.error or "Sync failed")
    except Exception as e:
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ BaoStock The daily K-line synchronization task has been canceled by the user")
            return {"cancelled": True, "message": str(e)}
        logger.error(f"❌ BaoStock Daily K-line synchronization task failed: {e}")
        raise


async def run_baostock_historical_sync(**kwargs):
    """Run BaoStock historical data synchronization task"""
    job_id = "baostock_historical_sync"
    
    logger.info(f"🚀 [BaoStock] Start performing historical data synchronization task (job_id={job_id}, kwargs={kwargs})")
    
    # 🔥 Allow execution when manually triggered or forced (even if there is a running record)
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    
    logger.info(f"🔍 [BaoStock] Check task status: manual_trigger={manual_trigger}, force_execute={force_execute}")
    
    if not manual_trigger and not force_execute:
        # 🔥 Check whether there is already an instance running (check only if it is not triggered manually and is not forced to execute)
        is_running, instance_id = await _check_task_running(job_id)
        logger.info(f"🔍 [BaoStock] Task running status check: is_running={is_running}, instance_id={instance_id}")
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    else:
        if manual_trigger:
            logger.info(f"🔧 [APScheduler] BaoStock Manually trigger execution and allow execution (even if there is a running record)")
        if force_execute:
            logger.info(f"🔧 [APScheduler] BaoStock Force execution, skip concurrency checks")
    
    try:
        # 🔥 Use unified thread pool synchronization service
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        # 🔥 Get BaoStock data source service instance
        logger.info(f"🔄 [BaoStock] Initialize synchronization service...")
        service = BaoStockSyncService()
        await service.initialize()  # 🔥 Must be initialized first
        logger.info(f"✅ [BaoStock] Synchronization service initialization completed")
        
        # 🔥 Set the correct job_id to ensure progress updates and status markers use the correct task ID
        service._current_job_id = job_id
        
        # 🔥 Check whether it is a resume execution and read the resume location from kwargs
        resume_from_index = kwargs.get("_resume_from_index")
        if resume_from_index is not None:
            logger.info(f"🔄 [Resume execution] will be from {resume_from_index} Stock positions continue to be synchronized")
        
        # 🔥 Execute synchronized methods in thread pool
        sync_result = await unified_service.execute_sync_method(
            sync_method=service.sync_historical_data,
            method_kwargs={
                "days": kwargs.get("days", 30),
                "batch_size": kwargs.get("batch_size", 20),
                "period": kwargs.get("period", "daily"),
                "incremental": kwargs.get("incremental", True),
                "symbols": kwargs.get("symbols")
            },
            job_id=job_id,
            rate_limit_per_minute=kwargs.get("rate_limit_per_minute", 200),  # BaoStock rate limit
            resume_from_index=resume_from_index
        )
        
        if sync_result.success:
            stats = sync_result.result
            logger.info(f"🎯 BaoStock Historical data synchronization completed: {stats.historical_records}records, {len(stats.errors)}errors")
            return stats
        else:
            # 🔥 Check if the task is canceled
            if "Cancel" in sync_result.error or "cancelled" in sync_result.error.lower():
                logger.info(f"ℹ️ BaoStock The historical data synchronization task has been canceled by the user")
                return {"cancelled": True, "message": sync_result.error}
            else:
                logger.error(f"❌ BaoStock Historical data synchronization failed: {sync_result.error}")
                raise RuntimeError(sync_result.error)
                
    except Exception as e:
        # Check whether it is a task cancellation exception (the user actively cancels and should not be recorded as an error)
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ BaoStock The historical data synchronization task has been canceled by the user")
            return {"cancelled": True, "message": "The task has been canceled by the user"}
        # Other exceptions are recorded as errors
        logger.error(f"❌ BaoStock Historical data synchronization task failed: {e}", exc_info=True)
        raise  # 🔥 Rethrow the exception to ensure that the error can be caught by the upper layer


    async def retry_failed_symbols(
        self,
        errors: List[Dict[str, Any]],
        days: int = 30,
        period: str = "daily",
        job_id: str = None,
        _is_retry: bool = False
    ) -> Dict[str, Any]:
        """
        Retry failed stocks (retry only retryable errors, skip errors with no data)
        
        Args:
            errors: Error list (obtained from previous sync results)
            days: Number of days to synchronize (BaoStock uses the days parameter)
            period: data period (daily/weekly/monthly)
            job_id: Task ID (for progress tracking)
            _is_retry: Internal mark indicating that this is a retry task to avoid automatic retries again
            
        Returns:
            Retry result statistics
        """
        period_name = {"daily": "daily line", "weekly": "perimeter", "monthly": "monthly line"}.get(period, period)
        
        # 🔥 BaoStock The error format may be a string or a dictionary, which needs to be processed uniformly
        retryable_errors = []
        no_data_errors = []
        
        for error in errors:
            # Handling string format errors
            if isinstance(error, str):
                # String errors usually represent retryable errors (network errors, etc.)
                retryable_errors.append({"error": error, "error_category": "retryable_error"})
            # Handling dictionary formatting errors
            elif isinstance(error, dict):
                if error.get("error_category") == "retryable_error" or error.get("is_retryable", False):
                    retryable_errors.append(error)
                else:
                    no_data_errors.append(error)
        
        logger.info(f"🔄 Start retrying failed stocks...")
        logger.info(f"   Retryable errors: {len(retryable_errors)} a")
        logger.info(f"   No data error (skip): {len(no_data_errors)} a")
        
        if not retryable_errors:
            logger.info("✅ There are no retryable errors, all failures are no-data cases")
            return {
                "total_retried": 0,
                "success_count": 0,
                "error_count": 0,
                "no_data_count": len(no_data_errors),
                "errors": []
            }
        
        # Extract retryable ticker (extracted from error message)
        retry_symbols = []
        for error in retryable_errors:
            if isinstance(error, dict) and error.get("code"):
                retry_symbols.append(error["code"])
            elif isinstance(error, str):
                # Extract ticker from string error (format: handle{code}Historical data failed)
                import re
                match = re.search(r'Process(\d{6})', error)
                if match:
                    retry_symbols.append(match.group(1))
        
        if not retry_symbols:
            logger.warning("⚠️ Unable to extract ticker from error list")
            return {
                "total_retried": 0,
                "success_count": 0,
                "error_count": len(retryable_errors),
                "no_data_count": len(no_data_errors),
                "errors": retryable_errors
            }
        
        logger.info(f"📋 Will retry following {len(retry_symbols)} only stocks: {', '.join(retry_symbols[:10])}{'...' if len(retry_symbols) > 10 else ''}")
        
        # Call the synchronization method to synchronize only these failed stocks
        retry_result_stats = await self.sync_historical_data(
            days=days,
            period=period,
            incremental=False,  # Use full sync when retrying
            symbols=retry_symbols  # 🔥 Only sync failed stocks
        )
        
        # Convert to unified format
        retry_result = {
            "total_retried": len(retry_symbols),
            "success_count": retry_result_stats.historical_records,  # BaoStock Use historical_records to represent the number of successes
            "error_count": len(retry_result_stats.errors),
            "total_records": retry_result_stats.historical_records,
            "no_data_count": len(no_data_errors),
            "retryable_errors_count": len(retryable_errors),
            "errors": retry_result_stats.errors
        }
        
        logger.info(f"✅ Retry complete: success {retry_result['success_count']}/{retry_result['total_retried']}, "
                   f"failed {retry_result['error_count']}, No data {retry_result['no_data_count']} (skipped)")
        
        return retry_result


# Global synchronization service instance
_baostock_sync_service = None

async def get_baostock_sync_service() -> BaoStockSyncService:
    """Get BaoStock synchronization service instance"""
    global _baostock_sync_service
    if _baostock_sync_service is None:
        _baostock_sync_service = BaoStockSyncService()
        await _baostock_sync_service.initialize()
    return _baostock_sync_service


async def run_baostock_status_check():
    """Run the BaoStock status check task"""
    try:
        service = BaoStockSyncService()
        await service.initialize()  # 🔥 Must be initialized first
        status = await service.check_service_status()
        logger.info(f"🔍 BaoStock Service status: {status['status']}")
    except Exception as e:
        logger.error(f"❌ BaoStock Status check task failed: {e}")
