"""
Tushare Data synchronization service
Responsible for synchronizing Tushare data to MongoDB standardized collection
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import logging

from tradingagents.dataflows.providers.china.tushare import TushareProvider
from app.services.stock_data_service import get_stock_data_service
from app.services.historical_data_service import get_historical_data_service
from app.services.news_data_service import get_news_data_service
from app.core.database import bind_loop_safe_mongo_db, get_mongo_db
from app.core.config import settings
from app.core.rate_limiter import get_tushare_rate_limiter
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

# UTC+8 time zone
UTC_8 = timezone(timedelta(hours=8))
ETF_SH_PREFIXES = ("50", "51", "52", "56", "58")
ETF_SZ_PREFIXES = ("15", "16", "18")


def get_utc8_now():
    """
    get UTC+8 Current time (naive datetime)

    Note: Returning a naive datetime (without time zone information), MongoDB will store the local time value as is
    In this way, the front end can be added directly +08:00 Suffix display
    """
    return now_tz().replace(tzinfo=None)


def _is_etf_code(symbol: str) -> bool:
    """Determine whether the code belongs to ETF/FUND to avoid mistakenly following the stock history synchronization link."""
    digits = "".join(ch for ch in str(symbol or "") if ch.isdigit())
    normalized = digits[-6:].zfill(6) if digits else ""
    return len(normalized) == 6 and normalized.startswith(ETF_SH_PREFIXES + ETF_SZ_PREFIXES)


class TushareSyncService:
    """
    Tushare Data synchronization service
    Responsible for synchronizing Tushare data to MongoDB standardized collection
    """
    
    def __init__(self):
        self.provider = TushareProvider()
        self.stock_service = get_stock_data_service()
        self.historical_service = None  # Lazy initialization
        self.news_service = None  # Lazy initialization
        self.db = get_mongo_db()
        self.settings = settings

        # Sync configuration
        self.batch_size = 100  # Batch size
        self.rate_limit_delay = 0.1  # API Call interval(seconds) - Deprecated, use rate_limiter
        self.max_retries = 3  # Maximum number of retries

        # Rate limiter (read configuration from environment variables)
        tushare_tier = getattr(settings, "TUSHARE_TIER", "standard")  # free/basic/standard/premium/vip
        safety_margin = float(getattr(settings, "TUSHARE_RATE_LIMIT_SAFETY_MARGIN", "0.8"))
        self.rate_limiter = get_tushare_rate_limiter(tier=tushare_tier, safety_margin=safety_margin)
    
    async def initialize(self):
        """Initialize synchronization service"""
        success = await self.provider.connect()
        if not success:
            raise RuntimeError("❌ Tushare Connection failed, unable to start synchronization service")

        # Initialize historical data service
        self.historical_service = await get_historical_data_service()

        # Initialize news data service
        self.news_service = await get_news_data_service()

        logger.info("✅ Tushare Synchronization service initialization completed")
    
    # ==================== Basic information synchronization ====================
    
    async def sync_stock_basic_info(self, force_update: bool = False, job_id: str = None) -> Dict[str, Any]:
        """
        Synchronize basic stock information

        Args:
            force_update: Whether to force update of all data
            job_id: Task ID (for progress tracking)

        Returns:
            Synchronization result statistics
        """
        logger.info("🔄 Start synchronizing basic stock information...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "start_time": datetime.utcnow(),
            "errors": []
        }
        
        try:
            # 1. Get stock list from Tushare
            stock_list = await self.provider.get_stock_list(market="CN")
            if not stock_list:
                logger.error("❌ Unable to get stock list")
                return stats
            
            stats["total_processed"] = len(stock_list)
            logger.info(f"📊 Get {len(stock_list)} Only stock information")

            try:
                from app.services.official_industry_service import upsert_industry_mapping_from_records
                mapping_result = await upsert_industry_mapping_from_records(stock_list, provider="tushare_fallback")
                if mapping_result.get("total", 0) > 0:
                    logger.info(f"📊 The system industry mapping collection has been updated: {mapping_result['total']} only stocks")
            except Exception as mapping_error:
                logger.warning(f"⚠️ Failed to update system industry mapping collection, continue to perform basic information synchronization: {mapping_error}")

            # 2. Batch processing
            for i in range(0, len(stock_list), self.batch_size):
                # Check if you need to exit
                if job_id and await self._should_stop(job_id):
                    logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting...")
                    stats["stopped"] = True
                    break

                batch = stock_list[i:i + self.batch_size]
                batch_stats = await self._process_basic_info_batch(batch, force_update)

                # Update statistics
                stats["success_count"] += batch_stats["success_count"]
                stats["error_count"] += batch_stats["error_count"]
                stats["skipped_count"] += batch_stats["skipped_count"]
                stats["errors"].extend(batch_stats["errors"])

                # Progress log and progress updates
                progress = min(i + self.batch_size, len(stock_list))
                progress_percent = int((progress / len(stock_list)) * 100)
                logger.info(f"📈 Basic information synchronization progress: {progress}/{len(stock_list)} ({progress_percent}%) "
                           f"(success: {stats['success_count']}, Error: {stats['error_count']})")

                # Update task progress
                if job_id:
                    await self._update_progress(
                        job_id,
                        progress_percent,
                        f"Processed {progress}/{len(stock_list)} only stocks"
                    )

                # API Current limiting
                if i + self.batch_size < len(stock_list):
                    await asyncio.sleep(self.rate_limit_delay)
            
            # 3. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            
            logger.info(f"✅ Basic stock information synchronization completed: "
                       f"total {stats['total_processed']} only, "
                       f"success {stats['success_count']} only, "
                       f"Error {stats['error_count']} only, "
                       f"skip {stats['skipped_count']} only, "
                       f"Time consuming {stats['duration']:.2f} seconds")
            
            # 🔥 Update task status to Completed (Progress 100%)
            if job_id:
                await self._update_progress(
                    job_id,
                    100,
                    f"Synchronization completed: successful {stats['success_count']}/{stats['total_processed']} only stocks"
                )
                # Explicit update status is completed
                await self._mark_task_completed(job_id, stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Synchronization of basic stock information failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_stock_basic_info"})
            
            # 🔥 Update task status is failed
            if job_id:
                try:
                    await self._mark_task_failed(job_id, str(e))
                except Exception as update_error:
                    logger.error(f"❌ An error occurred while updating task failure status: {update_error}")
            
            return stats
    
    async def _process_basic_info_batch(self, batch: List[Dict[str, Any]], force_update: bool) -> Dict[str, Any]:
        """Process basic information batches"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "errors": []
        }
        
        for stock_info in batch:
            try:
                # 🔥 Convert to dictionary format first (if it is a Pydantic model)
                if hasattr(stock_info, 'model_dump'):
                    stock_data = stock_info.model_dump()
                elif hasattr(stock_info, 'dict'):
                    stock_data = stock_info.dict()
                else:
                    stock_data = stock_info

                code = stock_data["code"]

                # Check if updates are needed
                if not force_update:
                    existing = await self.stock_service.get_stock_basic_info(code)
                    if existing:
                        # 🔥 existing It may also be a Pydantic model that requires safe access to properties
                        existing_dict = existing.model_dump() if hasattr(existing, 'model_dump') else (existing.dict() if hasattr(existing, 'dict') else existing)
                        if self._is_data_fresh(existing_dict.get("updated_at"), hours=24):
                            batch_stats["skipped_count"] += 1
                            continue

                # Update to database (specify data source as tushare)
                success = await self.stock_service.update_stock_basic_info(code, stock_data, source="tushare")
                if success:
                    batch_stats["success_count"] += 1
                else:
                    batch_stats["error_count"] += 1
                    batch_stats["errors"].append({
                        "code": code,
                        "error": "Database update failed",
                        "context": "update_stock_basic_info"
                    })

            except Exception as e:
                batch_stats["error_count"] += 1
                # 🔥 Safely obtain code (handling Pydantic models and dictionaries)
                try:
                    if hasattr(stock_info, 'code'):
                        code = stock_info.code
                    elif hasattr(stock_info, 'model_dump'):
                        code = stock_info.model_dump().get("code", "unknown")
                    elif hasattr(stock_info, 'dict'):
                        code = stock_info.dict().get("code", "unknown")
                    else:
                        code = stock_info.get("code", "unknown")
                except:
                    code = "unknown"

                batch_stats["errors"].append({
                    "code": code,
                    "error": str(e),
                    "context": "_process_basic_info_batch"
                })
        
        return batch_stats
    
    # ==================== Real-time market synchronization ====================
    
    async def sync_realtime_quotes(self, symbols: List[str] = None, force: bool = False) -> Dict[str, Any]:
        """
        Synchronize real-time market data

        Strategy:
        - If a small number of shares is specified (≤10 only), automatically switch to the AKShare interface (to avoid wasting Tushare rt_k quota)
        - If you specify a large number of stocks or the entire market, use the Tushare batch interface to obtain it at one time

        Args:
            symbols: Specify a stock code list. If it is empty, all stocks will be synchronized. If a stock list is specified, only the data of these stocks will be saved.
            force: Whether to enforce execution (skip transaction time check), default False

        Returns:
            Synchronization result statistics
        """
        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "start_time": datetime.utcnow(),
            "errors": [],
            "stopped_by_rate_limit": False,
            "skipped_non_trading_time": False,
            "switched_to_akshare": False  # whether to switch to AKShare
        }

        try:
            # Check if it is during trading hours (check can be skipped when synchronizing manually)
            if not force and not self._is_trading_time():
                logger.info("⏸️ It is not currently in trading hours, skip real-time market synchronization (use force=True enforceable)")
                stats["skipped_non_trading_time"] = True
                return stats

            # 🔥 Strategy selection: switch to AKShare for a small number of stocks, use the Tushare batch interface for a large number of stocks or the entire market
            USE_AKSHARE_THRESHOLD = 10  # Switch to when there are less than or equal to 10 stocks AKShare

            if symbols and len(symbols) <= USE_AKSHARE_THRESHOLD:
                # 🔥 Automatically switch to AKShare (to avoid wasting Tushare rt_k quota, only 2 calls per hour)
                logger.info(
                    f"💡 Number of shares ≤{USE_AKSHARE_THRESHOLD} Only, automatically switches to the AKShare interface"
                    f" (To avoid wasting Tushare rt_k quota, it can only be called 2 times per hour)"
                )
                logger.info(f"🎯 Sync using AKShare {len(symbols)} Real-time quotes of individual stocks: {symbols}")

                # Call the AKShare service
                from app.worker.akshare_sync_service import get_akshare_sync_service
                akshare_service = await get_akshare_sync_service()

                if not akshare_service:
                    logger.error("❌ AKShare Service is unavailable, fall back to Tushare batch interface")
                    # Fall back to Tushare batch interface
                    quotes_map = await self.provider.get_realtime_quotes_batch()
                    if quotes_map and symbols:
                        quotes_map = {symbol: quotes_map[symbol] for symbol in symbols if symbol in quotes_map}
                else:
                    # Sync using AKShare
                    akshare_result = await akshare_service.sync_realtime_quotes(
                        symbols=symbols,
                        force=force
                    )
                    stats["switched_to_akshare"] = True
                    stats["success_count"] = akshare_result.get("success_count", 0)
                    stats["error_count"] = akshare_result.get("error_count", 0)
                    stats["total_processed"] = akshare_result.get("total_processed", 0)
                    stats["errors"] = akshare_result.get("errors", [])
                    stats["end_time"] = datetime.utcnow()
                    stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

                    logger.info(
                        f"✅ AKShare Real-time market synchronization completed: "
                        f"total {stats['total_processed']} only, "
                        f"success {stats['success_count']} only, "
                        f"Error {stats['error_count']} only, "
                        f"Time consuming {stats['duration']:.2f} seconds"
                    )
                    return stats
            else:
                # Use Tushare batch interface to obtain all market information at once
                if symbols:
                    logger.info(f"📊 Sync using Tushare batch interface {len(symbols)} Real-time quotes of individual stocks (screened from all market data)")
                else:
                    logger.info("📊 Use Tushare batch interface to synchronize real-time market prices across the market...")

                logger.info("📡 Call the rt_k batch interface to obtain real-time market information...")
                quotes_map = await self.provider.get_realtime_quotes_batch()

                if not quotes_map:
                    logger.warning("⚠️ No real-time market data was obtained")
                    return stats

                logger.info(f"✅ Get {len(quotes_map)} Real-time quotes of individual stocks")

                # 🔥 If a stock list is specified, only these stocks are processed
                if symbols:
                    # Filter out specified stocks
                    filtered_quotes_map = {symbol: quotes_map[symbol] for symbol in symbols if symbol in quotes_map}

                    # Check if any stocks are not found
                    missing_symbols = [s for s in symbols if s not in quotes_map]
                    if missing_symbols:
                        logger.warning(f"⚠️ The following stocks were not found in real-time quotes: {missing_symbols}")

                    quotes_map = filtered_quotes_map
                    logger.info(f"🔍 Keep after filtering {len(quotes_map)} Quotes for specified stocks only")

            if not quotes_map:
                logger.warning("⚠️ No real-time market data was obtained")
                return stats

            stats["total_processed"] = len(quotes_map)

            # Batch save to database
            success_count = 0
            error_count = 0

            for symbol, quote_data in quotes_map.items():
                try:
                    # Save to database
                    result = await self.stock_service.update_market_quotes(symbol, quote_data)
                    if result:
                        success_count += 1
                    else:
                        error_count += 1
                        stats["errors"].append({
                            "code": symbol,
                            "error": "Update database failed",
                            "context": "sync_realtime_quotes"
                        })
                except Exception as e:
                    error_count += 1
                    stats["errors"].append({
                        "code": symbol,
                        "error": str(e),
                        "context": "sync_realtime_quotes"
                    })

            stats["success_count"] = success_count
            stats["error_count"] = error_count

            # Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ Real-time market synchronization completed: "
                      f"total {stats['total_processed']} only, "
                      f"success {stats['success_count']} only, "
                      f"Error {stats['error_count']} only, "
                      f"Time consuming {stats['duration']:.2f} seconds")

            return stats

        except Exception as e:
            # Check whether it is a current limiting error
            error_msg = str(e)
            if self._is_rate_limit_error(error_msg):
                stats["stopped_by_rate_limit"] = True
                logger.error(f"❌ Real-time market synchronization failed (API current limit): {e}")
            else:
                logger.error(f"❌ Real-time market synchronization failed: {e}")

            stats["errors"].append({"error": str(e), "context": "sync_realtime_quotes"})
            return stats

    # 🔥 Deprecated: Tushare single interface is no longer used (rt_k can only be called 2 times per hour, too precious)
    # A small amount of stock (≤10 only) automatically switches to the AKShare interface
    # async def _get_quotes_individually(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    #     """
    #     Use a single interface to obtain real-time stock quotes one by one (obsolete)
    #
    #     Args:
    #         symbols: Stock code list
    #
    #     Returns:
    #         Dict[symbol, quote_data]
    #     """
    #     quotes_map = {}
    #
    #     for symbol in symbols:
    #         try:
    #             quote_data = await self.provider.get_stock_quotes(symbol)
    #             if quote_data:
    #                 quotes_map[symbol] = quote_data
    #                 logger.info(f"✅ get {symbol} Real-time market success")
    #             else:
    #                 logger.warning(f"⚠️ Not obtained {symbol} real-time quotes")
    #         except Exception as e:
    #             logger.error(f"❌ get {symbol} Real-time quotes failed: {e}")
    #             continue
    #
    #     logger.info(f"✅ Acquisition of single interface completed, successful {len(quotes_map)}/{len(symbols)} only")
    #     return quotes_map

    async def _process_quotes_batch(self, batch: List[str]) -> Dict[str, Any]:
        """Process quotation batches"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "rate_limit_hit": False
        }

        # Concurrently obtain market data
        tasks = []
        for symbol in batch:
            task = self._get_and_save_quotes(symbol)
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Statistical results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = str(result)
                batch_stats["error_count"] += 1
                batch_stats["errors"].append({
                    "code": batch[i],
                    "error": error_msg,
                    "context": "_process_quotes_batch"
                })

                # Detecting API throttling errors
                if self._is_rate_limit_error(error_msg):
                    batch_stats["rate_limit_hit"] = True
                    logger.warning(f"⚠️ API throttling error detected: {error_msg}")

            elif result:
                batch_stats["success_count"] += 1
            else:
                batch_stats["error_count"] += 1
                batch_stats["errors"].append({
                    "code": batch[i],
                    "error": "Failed to obtain market data",
                    "context": "_process_quotes_batch"
                })

        return batch_stats

    def _is_rate_limit_error(self, error_msg: str) -> bool:
        """Detect whether it is an API current limiting error"""
        rate_limit_keywords = [
            "Most visits per minute",
            "max per minute",
            "rate limit",
            "too many requests",
            "Access frequency",
            "Requests are too frequent"
        ]
        error_msg_lower = error_msg.lower()
        return any(keyword in error_msg_lower for keyword in rate_limit_keywords)

    def _is_trading_time(self) -> bool:
        """
        Determine whether it is currently trading time
        A Stock trading hours:
        - Monday to Friday (excluding holidays)
        - Morning:9:30-11:30
        - Afternoon:13:00-15:00

        Note: This method does not check holidays, only the time period
        """
        from datetime import datetime
        import pytz

        # Use Shanghai time zone
        tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(tz)

        # Check if it is weekend
        if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return False

        # Check time period
        current_time = now.time()

        # Morning trading hours:9:30-11:30
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()

        # Afternoon trading hours:13:00-15:00
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()

        # Determine whether it is within the trading time period
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end

        return is_morning or is_afternoon

    async def _get_and_save_quotes(self, symbol: str) -> bool:
        """Get and save individual stock quotes"""
        try:
            quotes = await self.provider.get_stock_quotes(symbol)
            if quotes:
                # Convert to dictionary format (if Pydantic model)
                if hasattr(quotes, 'model_dump'):
                    quotes_data = quotes.model_dump()
                elif hasattr(quotes, 'dict'):
                    quotes_data = quotes.dict()
                else:
                    quotes_data = quotes

                return await self.stock_service.update_market_quotes(symbol, quotes_data)
            return False
        except Exception as e:
            error_msg = str(e)
            # Detect current limiting errors and throw them directly for the upper layer to handle
            if self._is_rate_limit_error(error_msg):
                logger.error(f"❌ get {symbol} Market failure (current limit): {e}")
                raise  # Thrown current limiting error
            logger.error(f"❌ get {symbol} Quote failed: {e}")
            return False

    # ==================== Historical data synchronization ====================

    async def sync_historical_data(
        self,
        symbols: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        incremental: bool = True,
        all_history: bool = False,
        period: str = "daily",
        job_id: str = None,
        auto_retry: bool = True,  # 🔥 New: Whether to automatically retry failed stocks (enabled by default)
        max_auto_retries: int = 1,  # 🔥 New: Maximum number of automatic retries (default 1 to avoid infinite retries)
        **kwargs  # 🔥 Receive additional kwargs including recovery location information
    ) -> Dict[str, Any]:
        """
        Synchronize historical data

        Args:
            symbols: Stock code list
            start_date: start date
            end_date: end date
            incremental: Whether to incrementally synchronize
            all_history: Whether to synchronize all historical data
            period: data period (daily/weekly/monthly)
            job_id: Task ID (for progress tracking)
            auto_retry: Whether to automatically retry failed stocks (default True)
                       - True: After all data synchronization is completed, retryable errors are automatically checked and retried.
                       - False: No automatic retry, you need to call retry manually API
            max_auto_retries: Maximum number of automatic retries (default 1 to avoid infinite retries)
                            - Retry strategy: After all data synchronization is completed, retryable errors will be automatically retried.
                            - Retry only marked as"Can be retried"Errors (network errors, API timeouts, etc.)
                            - Skip errors with no data (stock does not exist, date range is unreasonable, etc.)
                            - If a certain round of retries fails, stop retrying
                            - Stop retrying if all retryable errors have been resolved

        Returns:
            Synchronization result statistics
        """
        period_name = {"daily": "daily line", "weekly": "perimeter", "monthly": "monthly line"}.get(period, period)
        logger.info(f"🔄 Start syncing{period_name}historical data...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "total_records": 0,
            "start_time": datetime.utcnow(),
            "errors": []
        }

        try:
            # 🔥 When executing in a thread in the thread pool, the database connection needs to be reinitialized.
            self.db = bind_loop_safe_mongo_db(self)
            
            # 1. Get a list of stocks (excluding delisted stocks)
            if symbols is None:
                try:
                    # 🔥 Use aggregate queries to deduplicate, ensuring each stock symbol is only counted once
                    # Because the same stock may come from multiple data sources (tushare, akshare, baostock), there will be duplicate records
                    pipeline = [
                        {
                            "$match": {
                                "$and": [
                                    {
                                        "$or": [
                                            {"market_info.market": "CN"},  # new data structure
                                            {"category": "stock_cn"},      # old data structure
                                            {"market": {"$in": ["motherboard", "GEM", "Science and Technology Innovation Board", "Beijing Exchange"]}}  # By market type
                                        ]
                                    },
                                    # Exclude delisted stocks
                                    {
                                        "$or": [
                                            {"status": {"$ne": "D"}},  # status Not D (delisted)
                                            {"status": {"$exists": False}}  # Or the status field does not exist
                                        ]
                                    }
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
                    try:
                        cursor = self.db.stock_basic_info.aggregate(pipeline)
                        symbols = [doc["code"] async for doc in cursor]
                        logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Only unique stocks (duplication has been removed, delisted stocks have been excluded)")
                    except RuntimeError as loop_error:
                        # 🔥 If an event loop related error occurs, re-create the database connection
                        error_msg = str(loop_error).lower()
                        if any(keyword in error_msg for keyword in ["loop", "event loop is closed", "attached to a different loop"]):
                            logger.warning(f"⚠️ Event loop error detected, rebind database agent: {loop_error}")
                            self.db = bind_loop_safe_mongo_db(self)
                            # Retry query
                            cursor = self.db.stock_basic_info.aggregate(pipeline)
                            symbols = [doc["code"] async for doc in cursor]
                            logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Only unique stocks (duplication removed, delisted stocks excluded, connection re-created)")
                        else:
                            raise
                except Exception as e:
                    logger.error(f"❌ Failed to get stock list, use alternate method: {e}")
                    # 🔥 If an event loop related error occurs, re-create the database connection
                    error_msg = str(e).lower()
                    if any(keyword in error_msg for keyword in ["loop", "event loop is closed", "attached to a different loop"]):
                        logger.warning(f"⚠️ Event loop error detected, rebind database agent: {e}")
                        self.db = bind_loop_safe_mongo_db(self)
                    # Alternate method: use find() Query (may contain duplicates)
                    cursor = self.db.stock_basic_info.find(
                        {
                            "$and": [
                                {
                                    "$or": [
                                        {"market_info.market": "CN"},
                                        {"category": "stock_cn"},
                                        {"market": {"$in": ["motherboard", "GEM", "Science and Technology Innovation Board", "Beijing Exchange"]}}
                                    ]
                                },
                                {
                                    "$or": [
                                        {"status": {"$ne": "D"}},
                                        {"status": {"$exists": False}}
                                    ]
                                }
                            ]
                        },
                        {"code": 1}
                    )
                    try:
                        symbols = list(set([doc["code"] async for doc in cursor]))  # Use set to remove duplicates
                        logger.warning(f"⚠️ Obtained using alternative methods {len(symbols)} Only stocks (duplication removed)")
                    except RuntimeError as loop_error:
                        # 🔥 If an event loop related error occurs, re-create the database connection and try again
                        error_msg = str(loop_error).lower()
                        if any(keyword in error_msg for keyword in ["loop", "event loop is closed", "attached to a different loop"]):
                            logger.warning(f"⚠️ Alternate method also occurs event loop error, rebind database agent: {loop_error}")
                            self.db = bind_loop_safe_mongo_db(self)
                            # Retry query
                            cursor = self.db.stock_basic_info.find(
                                {
                                    "$and": [
                                        {
                                            "$or": [
                                                {"market_info.market": "CN"},
                                                {"category": "stock_cn"},
                                                {"market": {"$in": ["motherboard", "GEM", "Science and Technology Innovation Board", "Beijing Exchange"]}}
                                            ]
                                        },
                                        {
                                            "$or": [
                                                {"status": {"$ne": "D"}},
                                                {"status": {"$exists": False}}
                                            ]
                                        }
                                    ]
                                },
                                {"code": 1}
                            )
                            symbols = list(set([doc["code"] async for doc in cursor]))  # Use set to remove duplicates
                            logger.warning(f"⚠️ Obtained using alternative methods {len(symbols)} Stock only (deduplicated, connection re-created)")
                        else:
                            raise

            skipped_etf_symbols = []
            if symbols:
                stock_symbols = []
                for symbol in symbols:
                    if _is_etf_code(symbol):
                        skipped_etf_symbols.append(str(symbol))
                    else:
                        stock_symbols.append(symbol)
                symbols = stock_symbols

            if skipped_etf_symbols:
                preview = ", ".join(skipped_etf_symbols[:10])
                if len(skipped_etf_symbols) > 10:
                    preview = f"{preview}, ..."
                logger.info(
                    f"⏭️ Stock history synchronization has detected the ETF code and has switched to skip processing. Please use the ETF dedicated synchronization link.: "
                    f"count={len(skipped_etf_symbols)}, symbols={preview}"
                )
                stats["skipped_etf_count"] = len(skipped_etf_symbols)
                stats["skipped_etf_symbols"] = skipped_etf_symbols

            if not symbols:
                skip_message = "The incoming codes are all ETF/FUND, stock history synchronization has been skipped, please use the ETF dedicated synchronization link"
                logger.info(skip_message)
                stats["skipped"] = True
                stats["skip_reason"] = skip_message
                return {
                    "success": True,
                    "skipped": True,
                    "message": skip_message,
                    "stats": stats,
                }

            stats["total_processed"] = len(symbols)

            # 2. Determine global end date
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')

            # 🔥 Incremental synchronization time check: If incremental synchronization and the end date is today, and the current time is 18:00 before, skip synchronization
            if incremental and end_date == datetime.now().strftime('%Y-%m-%d'):
                current_time = datetime.now()
                cutoff_time = current_time.replace(hour=18, minute=0, second=0, microsecond=0)
                
                if current_time < cutoff_time:
                    skip_message = (
                        f"⏰ Incremental sync skip: current time {current_time.strftime('%H:%M:%S')} earlier than 18:00, "
                        f"The data source may not yet have data for the current day. It is recommended to 18:00 Then perform incremental synchronization."
                    )
                    logger.info(skip_message)
                    stats["skipped"] = True
                    stats["skip_reason"] = skip_message
                    return {
                        "success": True,
                        "skipped": True,
                        "message": skip_message,
                        "stats": stats
                    }

            # 3. Determine global start date (for log display only)
            global_start_date = start_date
            if not global_start_date:
                if all_history:
                    global_start_date = "1990-01-01"
                elif incremental:
                    global_start_date = "Last date of each stock"
                else:
                    global_start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

            logger.info(f"📊 Historical data synchronization: end date={end_date}, Number of shares={len(symbols)}, mode={'Increment' if incremental else 'full amount'}")

            # 🔥 Check whether there is a pending execution record, and if so, continue from the last progress position
            resume_from_index = 0
            
            # 🔥 Method 1: Prioritize reading the recovery location from kwargs (passed during the recovery operation)
            if kwargs and "_resume_from_index" in kwargs:
                resume_from_index = kwargs.get("_resume_from_index", 0)
                logger.info(f"🔄 Read recovery location from kwargs: {resume_from_index}")
            
            # 🔥 Method 2: If not obtained from kwargs, find the execution record (compatible with old logic)
            if resume_from_index == 0 and job_id:
                try:
                    # Find pending or running execution records
                    suspended_execution = await self.db.scheduler_executions.find_one(
                        {"job_id": job_id, "status": {"$in": ["suspended", "running"]}},
                        sort=[("timestamp", -1)]
                    )
                    
                    if suspended_execution:
                        processed_items = suspended_execution.get("processed_items")
                        logger.info(f"📊 Find execution records: execution_id={suspended_execution.get('_id')}, status={suspended_execution.get('status')}, processed_items={processed_items}, total_items={suspended_execution.get('total_items')}")
                        
                        if processed_items is not None and processed_items > 0:
                            resume_from_index = processed_items
                            logger.info(f"🔄 Read recovery location from execution record: {resume_from_index} (Processed {processed_items}/{len(symbols)}) ")
                        else:
                            logger.warning(f"⚠️ There is no valid execution record processed_items ({processed_items}), Will start execution from 0")
                    else:
                        logger.info(f"📊 No pending or running execution record found, execution will start from 0")
                except Exception as e:
                    logger.warning(f"⚠️ Check for pending task failure, start execution from: {e}", exc_info=True)
            
            logger.info(f"🚀 Historical data synchronization starts: Total number of shares={len(symbols)}, From the first {resume_from_index} a start, will handle {len(symbols) - resume_from_index} stocks")
            
            # 4. Batch processing (continue from last progress position)
            for i in range(resume_from_index, len(symbols)):
                symbol = symbols[i]
                # Record the start time of a single stock
                stock_start_time = datetime.now()

                try:
                    # 🔥 Checks whether the current thread's event loop has been closed (checked only in thread pool tasks)
                    # Note: Do not check the global provider in the thread pool task is_event_loop_closed(), 
                    # Because thread pool tasks have their own event loop, they should not rely on the state of the main event loop.
                    try:
                        current_loop = asyncio.get_running_loop()
                        if current_loop.is_closed():
                            logger.warning(f"⚠️ The event loop of the current thread has been closed and the task {job_id} Exit now...")
                            stats["stopped"] = True
                            stats["error_message"] = "Service is shutting down (event loop has closed)"
                            break
                    except RuntimeError:
                        # There is no event loop running, which shouldn't happen, but execution continues
                        logger.debug("⚠️ [Tushare] Unable to obtain current event loop, continue execution")

                    # Check if you need to exit
                    if job_id and await self._should_stop(job_id):
                        logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting...")
                        stats["stopped"] = True
                        break

                    # rate limit
                    await self.rate_limiter.acquire()

                    # Determine the start date of the stock
                    symbol_start_date = start_date
                    if not symbol_start_date:
                        if all_history:
                            symbol_start_date = "1990-01-01"
                        elif incremental:
                            # Incremental synchronization: Get the last date of the stock
                            symbol_start_date = await self._get_last_sync_date(symbol)
                            logger.debug(f"📅 {symbol}: from {symbol_start_date} Start syncing")
                            
                            # 🔥 Check if start_date is greater than end_date (avoid invalid date range)
                            if symbol_start_date > end_date:
                                logger.warning(
                                    f"⚠️ {symbol}: start date {symbol_start_date} greater than end date {end_date}, "
                                    f"Maybe the latest date in the database is already today or later, skip the stock"
                                )
                                stats["skipped_count"] = stats.get("skipped_count", 0) + 1
                                continue
                        else:
                            symbol_start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

                    # 🔥 Check again whether start_date is greater than end_date (double insurance)
                    if symbol_start_date > end_date:
                        logger.warning(
                            f"⚠️ {symbol}: start date {symbol_start_date} greater than end date {end_date}, skip this stock"
                        )
                        stats["skipped_count"] = stats.get("skipped_count", 0) + 1
                        continue

                    # Record request parameters
                    logger.debug(
                        f"🔍 {symbol}: Request{period_name}data "
                        f"start={symbol_start_date}, end={end_date}, period={period}"
                    )

                    # 🔍 Check Tushare connection status and try to reconnect if not available
                    if not self.provider.is_available():
                        logger.warning(f"⚠️ {symbol}: Tushare Connection unavailable, try reconnecting...")
                        try:
                            reconnect_success = await self.provider.connect()
                            if reconnect_success:
                                logger.info(f"✅ {symbol}: Tushare Reconnected successfully")
                            else:
                                logger.error(f"❌ {symbol}: Tushare Reconnect failed, skipping the stock")
                                stats["error_count"] += 1
                                continue
                        except Exception as reconnect_error:
                            logger.error(f"❌ {symbol}: Tushare Reconnect exception: {reconnect_error}")
                            stats["error_count"] += 1
                            continue

                    # ⏱️ Performance Monitoring: API Calls
                    api_start = datetime.now()
                    try:
                        logger.debug(f"🔍 [sync_historical_data] ready to call get_historical_data: symbol={symbol}, start={symbol_start_date}, end={end_date}, period={period}")
                        df = await self.provider.get_historical_data(symbol, symbol_start_date, end_date, period=period)
                        api_duration = (datetime.now() - api_start).total_seconds()
                        logger.debug(f"🔍 [sync_historical_data] get_historical_data Return: df={'None' if df is None else ('empty' if df.empty else f'{len(df)}OK')}, Time consuming={api_duration:.3f}seconds")
                    except Exception as api_error:
                        api_duration = (datetime.now() - api_start).total_seconds()
                        import traceback
                        error_details = traceback.format_exc()
                        stock_duration = (datetime.now() - stock_start_time).total_seconds()
                        
                        # Detailed records of API call exceptions
                        logger.error(
                            f"❌ {symbol}: Tushare API Call exception\n"
                            f"   Request parameters:\n"
                            f"     - symbol: {symbol}\n"
                            f"     - ts_code: {self._get_ts_code(symbol)}\n"
                            f"     - start_date: {symbol_start_date}\n"
                            f"     - end_date: {end_date}\n"
                            f"     - period: {period}\n"
                            f"   Error type: {type(api_error).__name__}\n"
                            f"   error message: {str(api_error)}\n"
                            f"   API The call takes time: {api_duration:.2f}seconds\n"
                            f"   Total time spent: {stock_duration:.2f}seconds\n"
                            f"   stack trace:\n{error_details}"
                        )
                        
                        stats["error_count"] += 1
                        stats["errors"].append({
                            "code": symbol,
                            "error": str(api_error),
                            "error_type": type(api_error).__name__,
                            "context": f"tushare_api_call_{period}",
                            "traceback": error_details,
                            "api_params": {
                                "symbol": symbol,
                                "start_date": symbol_start_date,
                                "end_date": end_date,
                                "period": period
                            }
                        })
                        continue

                    if df is not None and not df.empty:
                        # ⏱️ Performance Monitoring: Data Saving
                        save_start = datetime.now()
                        records_saved = await self._save_historical_data(symbol, df, period=period)
                        save_duration = (datetime.now() - save_start).total_seconds()

                        stats["success_count"] += 1
                        stats["total_records"] += records_saved

                        # Calculate the time taken for a single stock
                        stock_duration = (datetime.now() - stock_start_time).total_seconds()
                        logger.info(
                            f"✅ {symbol}: save {records_saved} Article{period_name}record,"
                            f"Total time spent {stock_duration:.2f}seconds "
                            f"(API: {api_duration:.2f}seconds, save: {save_duration:.2f}seconds)"
                        )
                    else:
                        stock_duration = (datetime.now() - stock_start_time).total_seconds()
                        
                        # Record the reasons for no data in detail
                        ts_code = self._get_ts_code(symbol)
                        list_date = self._get_list_date(symbol)
                        
                        # 🔍 Check if the stock exists in the database
                        stock_exists = await self._check_stock_exists(symbol)
                        
                        # 🔥 Determine whether it is"No data" (should not be retried) or"real failure" (You can try again)
                        is_no_data = False  # The default is to retry
                        likely_reason = ""
                        
                        # Determine possible causes based on the time taken by API calls
                        if api_duration < 0.01:
                            # API The call takes very little time (<10ms) , Might be fail fast
                            likely_reason = "Tushare API Fail fast (maybe parameter validation failed or ticker doesn t exist)"
                            # This situation may be a real failure, or it may be that there is no data and further judgment is required.
                            if not stock_exists:
                                is_no_data = True  # The stock does not exist, there may be no data
                        elif not stock_exists:
                            likely_reason = "The stock symbol does not exist in the database (may be delisted or has the wrong code)"
                            is_no_data = True  # The stock does not exist, there should be no data
                        elif list_date == "unknown":
                            likely_reason = "Unable to obtain the stock listing date, the stock information may be incomplete"
                            # This situation may be a real failure, or it may be no data
                        else:
                            # Check if the date range is reasonable
                            try:
                                from datetime import datetime as dt
                                start_dt = dt.strptime(symbol_start_date, '%Y-%m-%d')
                                end_dt = dt.strptime(end_date, '%Y-%m-%d')
                                list_dt = dt.strptime(list_date, '%Y-%m-%d') if list_date != "unknown" else None
                                
                                if list_dt and start_dt < list_dt:
                                    likely_reason = f"start date({symbol_start_date})earlier than launch date({list_date})"
                                    is_no_data = True  # The date range is unreasonable and there should be no data
                                elif end_dt < start_dt:
                                    likely_reason = f"end date({end_date})earlier than start date({symbol_start_date})"
                                    is_no_data = True  # The date range is unreasonable and there should be no data
                                else:
                                    # Check if it is a North Exchange stock (starting on 92/9/8), these stocks may indeed have no data
                                    if symbol.startswith('92') or symbol.startswith('9') or symbol.startswith('8'):
                                        likely_reason = f"North Exchange/NEEQ stocks({symbol}), There may be no transaction data during this period"
                                        is_no_data = True  # North Exchange stocks, may be no data
                                    else:
                                        likely_reason = "There is no trading data for this stock during this period (possible suspension, delisting or data source issues)"
                                        # In other cases, it may be a real failure or there may be no data. It is conservatively judged as no data.
                                        is_no_data = True
                            except:
                                likely_reason = "There may be a problem with the date range"
                                is_no_data = True  # Date parsing failed, there may be no data
                        
                        # 🔥 Record error information and mark error types
                        error_info = {
                            "code": symbol,
                            "error": f"None{period_name}data: {likely_reason}",
                            "error_type": "no_data" if is_no_data else "api_error",
                            "error_category": "no_data" if is_no_data else "retryable_error",  # 🔥 New: Error classification
                            "context": f"sync_historical_data_{period}_no_data",
                            "api_duration": api_duration,
                            "likely_reason": likely_reason,
                            "stock_exists": stock_exists,
                            "list_date": list_date
                        }
                        
                        # Only true failures are counted in error_count (can be retried)
                        # Cases without data are not included in error_count, but are recorded in errors for statistical purposes
                        if not is_no_data:
                            stats["error_count"] += 1
                        
                        stats["errors"].append(error_info)
                        
                        logger.warning(
                            f"⚠️ {symbol}: None{period_name}data ({'No data, no retry' if is_no_data else 'API Error, try again'})\n"
                            f"   Request parameters:\n"
                            f"     - symbol: {symbol}\n"
                            f"     - ts_code: {ts_code}\n"
                            f"     - start_date: {symbol_start_date}\n"
                            f"     - end_date: {end_date}\n"
                            f"     - period: {period}\n"
                            f"   API Return: {'None' if df is None else 'empty DataFrame'}\n"
                            f"   API The call takes time: {api_duration:.2f}seconds\n"
                            f"   Total time spent: {stock_duration:.2f}seconds\n"
                            f"   stock status: {'✅ exists in database' if stock_exists else '❌ does not exist in database'}\n"
                            f"   Listing date: {list_date}\n"
                            f"   🔍 most likely cause: {likely_reason}\n"
                            f"   💡 Other possible reasons:\n"
                            f"     1) There is no trading data for this stock during this period (trading suspended, delisted, unlisted)\n"
                            f"     2) Date range exceeds stock trading history\n"
                            f"     3) Stock symbol format is wrong or does not exist in Tushare\n"
                            f"     4) Tushare API Limit or insufficient points\n"
                            f"     5) Network connection problem or API service exception"
                        )

                    # Progress updated for each stock (considering continuing from last position)
                    # i is the current index (starting from resume_from_index) and needs to be converted to actual progress
                    actual_index = i + 1  # Index of actual processing (starting from 1)
                    
                    # 🔥 Fix: Progress should reflect"Number of stocks processed", instead of"Number of stocks successfully synchronized"
                    # This way the user can see the progress of processing even if some stocks fail
                    # But when it is finally completed, mark_job_completed will calculate the final progress based on success_count
                    processed_count = actual_index  # Number of stocks processed (both successful and failed)
                    progress_percent = int((processed_count / len(symbols)) * 100)

                    # Update task progress
                    if job_id:
                        from app.services.scheduler_service import update_job_progress, TaskCancelledException
                        try:
                            await update_job_progress(
                                job_id=job_id,
                                progress=progress_percent,
                                message=f"Synchronizing {symbol} ({processed_count}/{len(symbols)}, success: {stats['success_count']})",
                                current_item=symbol,
                                total_items=len(symbols),
                                processed_items=processed_count  # Processed (including successful and failed)
                            )
                        except TaskCancelledException:
                            # The task is canceled, logged and exited
                            logger.warning(f"⚠️ The historical data synchronization task was canceled by the user (Processed {i + 1}/{len(symbols)})")
                            stats["end_time"] = datetime.utcnow()
                            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
                            stats["cancelled"] = True
                            raise

                    # Output detailed logs every 50 stocks
                    if actual_index % 50 == 0 or actual_index == len(symbols):
                        logger.info(f"📈 {period_name}Data synchronization progress: {actual_index}/{len(symbols)} ({progress_percent}%) "
                                   f"(success: {stats['success_count']}, record: {stats['total_records']})")

                        # Output rate limiter statistics
                        limiter_stats = self.rate_limiter.get_stats()
                        logger.info(f"   rate limit: {limiter_stats['current_calls']}/{limiter_stats['max_calls']}times, "
                                   f"Wait times: {limiter_stats['total_waits']}, "
                                   f"total waiting time: {limiter_stats['total_wait_time']:.1f}seconds")

                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    
                    # 🔥 Determine the type of exception and distinguish"real failure" (retryable) and"No data" (No retry)
                    error_type_name = type(e).__name__
                    error_message = str(e)
                    
                    # Determine whether it is a retryable error
                    is_retryable = True  # Retryable by default
                    error_category = "retryable_error"
                    
                    # Certain exception types usually indicate a real failure and can be retried
                    retryable_exceptions = [
                        "ConnectionError", "TimeoutError", "HTTPError", 
                        "RequestException", "APIError", "RateLimitError"
                    ]
                    
                    # Some error messages may indicate that there is no data and should not be retried
                    no_data_keywords = [
                        "no data", "No data", "empty", "does not exist", 
                        "not found", "invalid", "Parameter error"
                    ]
                    
                    if any(keyword in error_message.lower() for keyword in no_data_keywords):
                        is_retryable = False
                        error_category = "no_data"
                    elif error_type_name not in retryable_exceptions:
                        # If it is not a common network/API error, it may be a data problem. It is conservatively judged as no data.
                        is_retryable = False
                        error_category = "no_data"
                    
                    stats["error_count"] += 1  # Exceptions are included error_count
                    stats["errors"].append({
                        "code": symbol,
                        "error": error_message,
                        "error_type": error_type_name,
                        "error_category": error_category,  # 🔥 New: Error classification
                        "is_retryable": is_retryable,  # 🔥 New: Whether it can be retried
                        "context": f"sync_historical_data_{period}",
                        "traceback": error_details
                    })
                    logger.error(
                        f"❌ {symbol} {period_name}Data synchronization failed ({'Can be retried' if is_retryable else 'No data, no retry'})\n"
                        f"   parameters: start={symbol_start_date if 'symbol_start_date' in locals() else 'N/A'}, "
                        f"end={end_date}, period={period}\n"
                        f"   Error type: {error_type_name}\n"
                        f"   error message: {error_message}\n"
                        f"   stack trace:\n{error_details}"
                    )

            # 4. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ {period_name}Data synchronization completed: "
                       f"stocks {stats['success_count']}/{stats['total_processed']}, "
                       f"record {stats['total_records']} Article, "
                       f"Error {stats['error_count']} a, "
                       f"Time consuming {stats['duration']:.2f} seconds")

            # 🔥 Automatically retry failed stocks (if enabled and not retry the task itself)
            # Strategy: After all data synchronization is completed, automatically check and retry retryable errors.
            if auto_retry and max_auto_retries > 0 and not kwargs.get("_is_retry", False):
                retryable_errors = [
                    error for error in stats.get("errors", [])
                    if error.get("error_category") == "retryable_error" 
                    or error.get("is_retryable", False)
                ]
                
                if retryable_errors:
                    logger.info(f"🔄 detected {len(retryable_errors)} retryable errors, start automatically retrying (up to {max_auto_retries} times)...")
                    
                    # Record statistics before retrying
                    initial_success_count = stats["success_count"]
                    initial_error_count = len(retryable_errors)
                    
                    # Perform automatic retries (up to max_auto_retries times)
                    for retry_round in range(1, max_auto_retries + 1):
                        # Get the current retryable errors (only errors marked as retryable are retried)
                        current_retryable = [
                            error for error in stats.get("errors", [])
                            if error.get("error_category") == "retryable_error" 
                            or error.get("is_retryable", False)
                        ]
                        
                        if not current_retryable:
                            logger.info(f"✅ No. {retry_round} Round of retries: There are no more errors to retry")
                            break
                        
                        logger.info(f"🔄 No. {retry_round}/{max_auto_retries} Round automatic retry:{len(current_retryable)} only stocks")
                        
                        # Call the retry method (marked for automatic retry to avoid recursion)
                        retry_result = await self.retry_failed_symbols(
                            errors=current_retryable,
                            start_date=start_date,
                            end_date=end_date,
                            period=period,
                            job_id=f"{job_id}_auto_retry_{retry_round}" if job_id else None,
                            _is_retry=True  # Mark the task as retry to avoid automatic retry again
                        )
                        
                        # Update main statistics: cumulative number of stocks and records with successful attempts
                        stats["success_count"] += retry_result.get("success_count", 0)
                        stats["total_records"] += retry_result.get("total_records", 0)
                        
                        # Updated error list: Remove errors for stocks that have succeeded, keep those that still failed
                        # Stocks with successful retries are removed from errors (as their errors will not be included in retry_result)
                        retry_symbols = set([e["code"] for e in current_retryable])
                        successful_symbols = set()
                        
                        # Infer the successful stock from the retry result (if the retry is successful, the stock will not appear in the new error list)
                        # Simplified processing: if the number of successful retries > 0, It means that some stocks are successful
                        # But since we don't know exactly which stocks were successful, we retain all errors and let them filter naturally during the next round of retries.
                        
                        # If there is no new success in this round of retries, stop retrying.
                        if retry_result.get("success_count", 0) == 0:
                            logger.info(f"⚠️ No. {retry_round} Round retry failed, stop automatic retry")
                            break
                        
                        # Updated error list: Removed errors for stocks with successful retries
                        # Since retry_result will return a new error list, we need to merge
                        # Simplified processing: retain the original no-data errors and remove errors for stocks that have been successfully retried.
                        updated_errors = []
                        retry_success_count = retry_result.get("success_count", 0)
                        retry_failed_symbols = set()
                        
                        # Extract failed stocks from retry results (if there is an error list)
                        if retry_result.get("errors"):
                            retry_failed_symbols = set([e.get("code") for e in retry_result.get("errors", [])])
                        
                        # Update error list
                        for error in stats.get("errors", []):
                            error_code = error.get("code")
                            # If it is a retryable error and is not in the list of failed retry attempts, it means the retry was successful and remove it.
                            if (error.get("error_category") == "retryable_error" or error.get("is_retryable", False)):
                                if error_code not in retry_failed_symbols and error_code in retry_symbols:
                                    # Retry successfully, error removed
                                    continue
                            # Other errors (no data, etc.) are retained
                            updated_errors.append(error)
                        
                        # Added error if still fails after retrying
                        if retry_result.get("errors"):
                            updated_errors.extend(retry_result.get("errors", []))
                        
                        stats["errors"] = updated_errors
                        
                        # Stop retrying if all retryable errors have been resolved
                        remaining_retryable = [
                            error for error in stats.get("errors", [])
                            if error.get("error_category") == "retryable_error" 
                            or error.get("is_retryable", False)
                        ]
                        if not remaining_retryable:
                            logger.info(f"✅ All retryable errors resolved, stop automatic retries")
                            break
                    
                    # Record automatic retry statistics
                    final_success_count = stats["success_count"]
                    retry_success_count = final_success_count - initial_success_count
                    logger.info(f"✅ Automatic retry complete: total {retry_round} wheel,"
                               f"Try again {initial_error_count} only stocks,"
                               f"success {retry_success_count} only,"
                               f"Retryable errors remaining {len([e for e in stats.get('errors', []) if e.get('error_category') == 'retryable_error' or e.get('is_retryable', False)])} a")
                    
                    # Update final statistics
                    stats["auto_retry_stats"] = {
                        "retry_rounds": retry_round,
                        "initial_retryable_errors": initial_error_count,
                        "retry_success_count": retry_success_count
                    }

            # 🔥 Update task status to Completed (if job_id exists)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed, update_job_progress
                    
                    # 🔥 Before calling mark_job_completed, update the progress once
                    # Use the number of successfully synchronized stocks to calculate final progress, not the number of stocks processed
                    if stats.get("total_processed", 0) > 0:
                        success_count = stats.get("success_count", 0)
                        total_processed = stats.get("total_processed", 0)
                        final_progress = int((success_count / total_processed) * 100)
                        final_progress = max(0, min(100, final_progress))
                        
                        # Update progress to actual successful progress
                        try:
                            await update_job_progress(
                                job_id=job_id,
                                progress=final_progress,
                                message=f"Synchronization completed: successful {success_count}/{total_processed} only stocks",
                                total_items=total_processed,
                                processed_items=total_processed  # Processed (including successful and failed)
                            )
                        except Exception as progress_error:
                            logger.warning(f"⚠️ Error updating final progress: {progress_error}")
                    
                    # 🔥 Modify the logic: if the success rate >= 80%, It should not be marked as failed even if there are errors
                    # 🔥 Progress should show 100% (as all stocks have been processed) and failed items can be retried individually
                    success_count = stats.get("success_count", 0)
                    total_processed = stats.get("total_processed", 0)
                    error_count = stats.get("error_count", 0)
                    
                    # Calculate success rate
                    success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
                    
                    # 🔥 If success rate >= 80%, Do not set error_message and let mark_job_completed determine the status based on the success rate.
                    # 🔥 In this way, even if some parts fail, as long as most of them succeed, the task will be marked as success
                    error_message = None
                    if error_count > 0 and success_rate < 80:
                        # only success rate < 80% error_message is only set and marked as failure
                        error_messages = [e.get("error", "") for e in stats.get("errors", [])[:5]]
                        error_message = f"Synchronization is complete but there are {error_count} errors: {', '.join(error_messages)}"
                    # If success rate >= 80%, Do not set error_message even if there is an error, let mark_job_completed mark as success
                    
                    await mark_job_completed(job_id, stats, error_message)
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task completion status: {update_error}")

            return stats

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(
                f"❌ Historical data synchronization failed (outer layer exception)\n"
                f"   Error type: {type(e).__name__}\n"
                f"   error message: {str(e)}\n"
                f"   stack trace:\n{error_details}"
            )
            stats["errors"].append({
                "error": str(e),
                "error_type": type(e).__name__,
                "context": "sync_historical_data",
                "traceback": error_details
            })
            
            # 🔥 Update task status to failed (if job_id exists)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, None, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats

    async def _save_historical_data(self, symbol: str, df, period: str = "daily") -> int:
        """Save historical data to database"""
        try:
            # 🔥 Ensure historical_service is initialized (if None, created with current db connection)
            if self.historical_service is None:
                from app.services.historical_data_service import HistoricalDataService
                self.historical_service = HistoricalDataService()
                self.historical_service.db = self.db
                self.historical_service.collection = self.db.stock_daily_quotes
                await self.historical_service._ensure_indexes()

            # Save using unified historical data service (specified period)
            saved_count = await self.historical_service.save_historical_data(
                symbol=symbol,
                data=df,
                data_source="tushare",
                market="CN",
                period=period
            )

            return saved_count

        except Exception as e:
            logger.error(f"❌ save{period}Data failed {symbol}: {e}")
            return 0

    def _get_ts_code(self, symbol: str) -> str:
        """
        Get the stock code in Tushare format (ts_code)
        
        Args:
            symbol: Stock code (e.g. 300750)
            
        Returns:
            Tushare Format code (such as 300750.SZ)
        """
        try:
            # Determine the market based on code prefix
            # Shanghai Stock Exchange: 60/68 (A shares), 50/51/52/58/56 (ETF/LOF/convertible bonds, etc.), 11 (treasury bonds/convertible bonds)
            if symbol.startswith(('60', '68', '50', '51', '52', '58', '56', '11')):
                return f"{symbol}.SH"
            # Shenzhen Stock Exchange: 00/30 (A shares), 15/16/12 (ETF/LOF/convertible bonds, etc.)
            elif symbol.startswith(('00', '30', '15', '16', '12')):
                return f"{symbol}.SZ"
            elif symbol.startswith(('8', '4', '92')):
                return f"{symbol}.BJ"  # North Exchange (8/4 old number section, 920 will be the unified number section from 2025-10)
            else:
                return f"{symbol}.SZ"  # Default Shenzhen Stock Exchange
        except:
            return f"{symbol}.SZ"
    
    def _get_list_date(self, symbol: str) -> str:
        """
        Get stock listing date
        
        Args:
            symbol: Stock code
            
        Returns:
            Listing date string, returned if not found "unknown"
        """
        try:
            # Try querying the listing date from the database (synchronous query as this is a helper method)
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If the event loop is running, use the synchronous client
                    from pymongo import MongoClient
                    from app.core.config import settings
                    sync_client = MongoClient(settings.MONGO_URI)
                    sync_db = sync_client[settings.MONGODB_DATABASE]
                    stock_info = sync_db.stock_basic_info.find_one(
                        {"code": symbol},
                        {"list_date": 1}
                    )
                    sync_client.close()
                    if stock_info and stock_info.get("list_date"):
                        list_date = stock_info["list_date"]
                        if isinstance(list_date, str):
                            if len(list_date) == 8 and list_date.isdigit():
                                return f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:]}"
                            return list_date
                        else:
                            return list_date.strftime('%Y-%m-%d')
            except:
                pass
            return "unknown"
        except:
            return "unknown"
    
    async def _check_stock_exists(self, symbol: str) -> bool:
        """
        Check if the stock exists in the database
        
        Args:
            symbol: Stock code
            
        Returns:
            True False if the stock exists, otherwise
        """
        try:
            stock_info = await self.db.stock_basic_info.find_one(
                {"code": symbol},
                {"code": 1}  # Only query the code field to improve performance
            )
            return stock_info is not None
        except Exception as e:
            logger.debug(f"check stock {symbol} Error when exists: {e}")
            return False  # Returns False when an error occurs and does not affect the main process.
    
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
                from app.services.historical_data_service import HistoricalDataService
                self.historical_service = HistoricalDataService()
                self.historical_service.db = self.db
                self.historical_service.collection = self.db.stock_daily_quotes
                await self.historical_service._ensure_indexes()

            if symbol:
                # Get the latest date for a specific stock
                latest_date = await self.historical_service.get_latest_date(symbol, "tushare")
                if latest_date:
                    # Returns the day after the last date (to avoid repeated synchronization)
                    try:
                        last_date_obj = datetime.strptime(latest_date, '%Y-%m-%d')
                        next_date = last_date_obj + timedelta(days=1)
                        next_date_str = next_date.strftime('%Y-%m-%d')
                        
                        # 🔥 If the date after adding 1 day exceeds today, return today (avoid start_date > end_date) 
                        today_str = datetime.now().strftime('%Y-%m-%d')
                        if next_date_str > today_str:
                            logger.debug(
                                f"📅 {symbol}: Database latest date {latest_date} +1 day = {next_date_str} "
                                f"has exceeded today {today_str}, Return today as the start date"
                            )
                            return today_str
                        
                        return next_date_str
                    except:
                        # If the date format is incorrect, return directly
                        return latest_date
                else:
                    # 🔥 When there is no historical data, all data will be synchronized starting from the launch date.
                    stock_info = await self.db.stock_basic_info.find_one(
                        {"code": symbol},
                        {"list_date": 1}
                    )
                    if stock_info and stock_info.get("list_date"):
                        list_date = stock_info["list_date"]
                        # Handle different date formats
                        if isinstance(list_date, str):
                            # The format may be "20100101" or "2010-01-01"
                            if len(list_date) == 8 and list_date.isdigit():
                                return f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:]}"
                            else:
                                return list_date
                        else:
                            return list_date.strftime('%Y-%m-%d')

                    # If there is no launch date, start from 1990
                    logger.warning(f"⚠️ {symbol}: No listing date found, synchronized starting from 1990-01-01")
                    return "1990-01-01"

            # Returns to 30 days ago by default (to ensure no data leakage)
            return (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        except Exception as e:
            logger.error(f"❌ Failed to get last sync date {symbol}: {e}")
            # When an error occurs, return to 30 days ago to ensure no data is leaked.
            return (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    # ==================== Financial data synchronization ====================

    async def sync_financial_data(self, symbols: List[str] = None, limit: int = None, job_id: str = None) -> Dict[str, Any]:
        """
        Sync financial data

        Args:
            symbols: Stock code list, None means synchronize all stocks
            limit: Get the financial report period number, None means synchronize all reporting periods available for the stock
            job_id: Task ID (for progress tracking)
        """
        limit_text = "All reporting periods" if limit is None else f"Recently {limit} period"
        logger.info(f"🔄 Start syncing financial data (get{limit_text})...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "start_time": datetime.utcnow(),
            "errors": []
        }

        try:
            # Get a list of stocks
            if symbols is None:
                # 🔥 Use aggregate queries to deduplicate, ensuring each stock symbol is only counted once
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
                logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Only unique stocks (duplication removed)")

            stats["total_processed"] = len(symbols)
            logger.info(f"📊 Need to synchronize {len(symbols)} Only stock financial data")

            # Batch processing
            for i, symbol in enumerate(symbols):
                try:
                    # 🔥 Check if the task should be stopped
                    if job_id and await self._should_stop(job_id):
                        logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting...")
                        stats["stopped"] = True
                        break

                    # rate limit
                    await self.rate_limiter.acquire()

                    # Get financial data (specify the number of periods to get)
                    financial_data = await self.provider.get_financial_data(symbol, limit=limit)

                    if financial_data:
                        # Save financial data
                        success = await self._save_financial_data(symbol, financial_data)
                        if success:
                            stats["success_count"] += 1
                        else:
                            stats["error_count"] += 1
                    else:
                        logger.warning(f"⚠️ {symbol}: No financial data")

                    # Progress log and progress tracking
                    if (i + 1) % 20 == 0:
                        progress = int((i + 1) / len(symbols) * 100)
                        logger.info(f"📈 Financial data synchronization progress: {i + 1}/{len(symbols)} ({progress}%) "
                                   f"(success: {stats['success_count']}, Error: {stats['error_count']})")
                        # Output rate limiter statistics
                        limiter_stats = self.rate_limiter.get_stats()
                        logger.info(f"   rate limit: {limiter_stats['current_calls']}/{limiter_stats['max_calls']}times")

                        # Update task progress
                        if job_id:
                            from app.services.scheduler_service import update_job_progress, TaskCancelledException
                            try:
                                await update_job_progress(
                                    job_id=job_id,
                                    progress=progress,
                                    message=f"Synchronizing {symbol} financial data",
                                    current_item=symbol,
                                    total_items=len(symbols),
                                    processed_items=i + 1
                                )
                            except TaskCancelledException:
                                # The task is canceled, logged and exited
                                logger.warning(f"⚠️ The financial data synchronization task was canceled by the user (Processed {i + 1}/{len(symbols)})")
                                stats["end_time"] = datetime.utcnow()
                                stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
                                stats["cancelled"] = True
                                raise

                except Exception as e:
                    stats["error_count"] += 1
                    stats["errors"].append({
                        "code": symbol,
                        "error": str(e),
                        "context": "sync_financial_data"
                    })
                    logger.error(f"❌ {symbol} Financial data synchronization failed: {e}")

            # Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ Financial data synchronization completed: "
                       f"success {stats['success_count']}/{stats['total_processed']}, "
                       f"Error {stats['error_count']} a, "
                       f"Time consuming {stats['duration']:.2f} seconds")

            # 🔥 Update task status to Completed (if job_id exists)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    # 🔥 Modify the logic: if the success rate >= 80%, It should not be marked as failed even if there are errors
                    success_count = stats.get("success_count", 0)
                    total_processed = stats.get("total_processed", 0)
                    error_count = stats.get("error_count", 0)
                    success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
                    
                    error_message = None
                    if error_count > 0 and success_rate < 80:
                        # only success rate < 80% Set only when error_message
                        error_messages = [e.get("error", "") for e in stats.get("errors", [])[:5]]
                        error_message = f"Synchronization is complete but there are {error_count} errors: {', '.join(error_messages)}"
                    
                    await mark_job_completed(job_id, stats, error_message)
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task completion status: {update_error}")

            return stats

        except Exception as e:
            logger.error(f"❌ Financial data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_financial_data"})
            
            # 🔥 Update task status to failed (if job_id exists)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, None, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats

    async def _save_financial_data(self, symbol: str, financial_data: Dict[str, Any]) -> bool:
        """Save financial data"""
        try:
            # Use unified financial data services
            from app.services.financial_data_service import get_financial_data_service

            financial_service = await get_financial_data_service()

            # Save financial data
            saved_count = await financial_service.save_financial_data(
                symbol=symbol,
                financial_data=financial_data,
                data_source="tushare",
                market="CN",
                report_period=financial_data.get("report_period"),
                report_type=financial_data.get("report_type", "quarterly")
            )

            return saved_count > 0

        except Exception as e:
            logger.error(f"❌ save {symbol} Financial data failed: {e}")
            return False

    # ==================== Helper methods ====================

    def _is_data_fresh(self, updated_at: datetime, hours: int = 24) -> bool:
        """Check if the data is fresh"""
        if not updated_at:
            return False

        threshold = datetime.utcnow() - timedelta(hours=hours)
        return updated_at > threshold

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get sync status"""
        try:
            # 🔥 Critical fix: reacquire database connection on every use, ensure correct event loop is used
            # 🔥 This can avoid event loop conflicts when executing in scheduled tasks
            db = get_mongo_db()
            
            # Count the amount of data in each collection
            basic_info_count = await db.stock_basic_info.count_documents({})
            quotes_count = await db.market_quotes.count_documents({})

            # Get the latest update time
            latest_basic = await db.stock_basic_info.find_one(
                {},
                sort=[("updated_at", -1)]
            )
            latest_quotes = await db.market_quotes.find_one(
                {},
                sort=[("updated_at", -1)]
            )

            return {
                "provider_connected": self.provider.is_available(),
                "collections": {
                    "stock_basic_info": {
                        "count": basic_info_count,
                        "latest_update": latest_basic.get("updated_at") if (latest_basic and isinstance(latest_basic, dict)) else None
                    },
                    "market_quotes": {
                        "count": quotes_count,
                        "latest_update": latest_quotes.get("updated_at") if (latest_quotes and isinstance(latest_quotes, dict)) else None
                    }
                },
                "status_time": datetime.utcnow()
            }

        except Exception as e:
            logger.error(f"❌ Failed to get sync status: {e}", exc_info=True)
            return {"error": str(e)}

    # ==================== News data synchronization ====================

    async def sync_news_data(
        self,
        symbols: List[str] = None,
        hours_back: int = 24,
        max_news_per_stock: int = 20,
        force_update: bool = False,
        job_id: str = None
    ) -> Dict[str, Any]:
        """
        Synchronize news data

        Args:
            symbols: Stock code list, if None, get all stocks
            hours_back: Number of hours to look back, default is 24 hours
            max_news_per_stock: Maximum number of news per stock
            force_update: Whether to force update
            job_id: Task ID (for progress tracking)

        Returns:
            Synchronization result statistics
        """
        logger.info("🔄 Start synchronizing news data...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "news_count": 0,
            "start_time": datetime.utcnow(),
            "errors": []
        }

        try:
            # 1. Get a list of stocks
            if symbols is None:
                stock_list = await self.stock_service.get_all_stocks()
                symbols = [stock["code"] for stock in stock_list]

            if not symbols:
                logger.warning("⚠️ No stocks found that require synchronized news")
                return stats

            stats["total_processed"] = len(symbols)
            logger.info(f"📊 Need to synchronize {len(symbols)} Stock news")

            # 2. Batch processing
            for i in range(0, len(symbols), self.batch_size):
                # Check if you need to exit
                if job_id and await self._should_stop(job_id):
                    logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting...")
                    stats["stopped"] = True
                    break

                batch = symbols[i:i + self.batch_size]
                batch_stats = await self._process_news_batch(
                    batch, hours_back, max_news_per_stock
                )

                # Update statistics
                stats["success_count"] += batch_stats["success_count"]
                stats["error_count"] += batch_stats["error_count"]
                stats["news_count"] += batch_stats["news_count"]
                stats["errors"].extend(batch_stats["errors"])

                # Progress log and progress updates
                progress = min(i + self.batch_size, len(symbols))
                progress_percent = int((progress / len(symbols)) * 100)
                logger.info(f"📈 News synchronization progress: {progress}/{len(symbols)} ({progress_percent}%) "
                           f"(success: {stats['success_count']}, News: {stats['news_count']})")

                # Update task progress
                if job_id:
                    await self._update_progress(
                        job_id,
                        progress_percent,
                        f"Processed {progress}/{len(symbols)} Only stocks, get {stats['news_count']} news"
                    )

                # API Current limiting
                if i + self.batch_size < len(symbols):
                    await asyncio.sleep(self.rate_limit_delay)

            # 3. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ News data synchronization completed: "
                       f"total {stats['total_processed']} only stocks, "
                       f"success {stats['success_count']} only, "
                       f"get {stats['news_count']} news, "
                       f"Error {stats['error_count']} only, "
                       f"Time consuming {stats['duration']:.2f} seconds")

            # 🔥 Update task status to Completed (if job_id exists)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    # 🔥 Modify the logic: if the success rate >= 80%, It should not be marked as failed even if there are errors
                    success_count = stats.get("success_count", 0)
                    total_processed = stats.get("total_processed", 0)
                    error_count = stats.get("error_count", 0)
                    success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
                    
                    error_message = None
                    if error_count > 0 and success_rate < 80:
                        # only success rate < 80% Set only when error_message
                        error_messages = [e.get("error", "") for e in stats.get("errors", [])[:5]]
                        error_message = f"Synchronization is complete but there are {error_count} errors: {', '.join(error_messages)}"
                    
                    await mark_job_completed(job_id, stats, error_message)
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task completion status: {update_error}")

            return stats

        except Exception as e:
            logger.error(f"❌ News data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_news_data"})
            
            # 🔥 Update task status to failed (if job_id exists)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, None, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats

    async def _process_news_batch(
        self,
        batch: List[str],
        hours_back: int,
        max_news_per_stock: int
    ) -> Dict[str, Any]:
        """Process news batches"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "news_count": 0,
            "errors": []
        }

        for symbol in batch:
            try:
                # Get news data from Tushare
                news_data = await self.provider.get_stock_news(
                    symbol=symbol,
                    limit=max_news_per_stock,
                    hours_back=hours_back
                )

                if news_data:
                    # Save news data
                    saved_count = await self.news_service.save_news_data(
                        news_data=news_data,
                        data_source="tushare",
                        market="CN"
                    )

                    batch_stats["success_count"] += 1
                    batch_stats["news_count"] += saved_count

                    logger.debug(f"✅ {symbol} News synchronization successful: {saved_count}Article")
                else:
                    logger.debug(f"⚠️ {symbol} News data not obtained")
                    batch_stats["success_count"] += 1  # Success without news

                # 🔥 API Current limiting: sleep after success
                await asyncio.sleep(0.2)

            except Exception as e:
                batch_stats["error_count"] += 1
                error_msg = f"{symbol}: {str(e)}"
                batch_stats["errors"].append(error_msg)
                logger.error(f"❌ {symbol} News sync failed: {e}")

                # 🔥 Also sleep after failure to avoid"avalanche of failure"
                # Sleep longer on failure to give the API server a chance to recover
                await asyncio.sleep(1.0)

        return batch_stats

    # ==================== Progress tracking helper methods ====================

    async def _should_stop(self, job_id: str) -> bool:
        """
        Check if the task should be stopped

        Args:
            job_id: Task ID

        Returns:
            should it stop
        """
        try:
            # 🔥 Use synchronous MongoDB client queries (to avoid errors after the event loop is closed)
            from pymongo import MongoClient
            from app.core.config import settings

            sync_client = MongoClient(settings.MONGO_URI)
            sync_db = sync_client[settings.MONGODB_DATABASE]

            try:
                # 🔥 Query execution records, check cancel_requested flag and task status
                # Not only checks the running status, but also checks the failed/cancelled/suspended status
                execution = sync_db.scheduler_executions.find_one(
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
            finally:
                sync_client.close()

        except Exception as e:
            logger.error(f"❌ Checking task stop flag failed: {e}")
            return False

    async def _update_progress(self, job_id: str, progress: int, message: str):
        """
        Update task progress

        Args:
            job_id: Task ID
            progress: progress percentage (0-100)
            message: progress message
        """
        try:
            from app.services.scheduler_service import TaskCancelledException
            from pymongo import MongoClient
            from app.core.config import settings

            logger.info(f"📊 [progress update] Start update task {job_id} Progress: {progress}% - {message}")

            # Use a synchronous PyMongo client (to avoid event loop conflicts)
            sync_client = MongoClient(settings.MONGO_URI)
            sync_db = sync_client[settings.MONGODB_DATABASE]

            # Find the latest running record
            execution = sync_db.scheduler_executions.find_one(
                {"job_id": job_id, "status": "running"},
                sort=[("timestamp", -1)]
            )

            if not execution:
                logger.warning(f"⚠️ Task not found {job_id} execution record")
                sync_client.close()
                return

            logger.info(f"📊 [progress update] Find the execution record: _id={execution['_id']}, Current progress={execution.get('progress', 0)}%")

            # Check if a cancellation request was received
            if execution.get("cancel_requested"):
                sync_client.close()
                raise TaskCancelledException(f"Task {job_id} Canceled by user")

            # Update progress (using UTC+8 time)
            result = sync_db.scheduler_executions.update_one(
                {"_id": execution["_id"]},
                {
                    "$set": {
                        "progress": progress,
                        "progress_message": message,
                        "updated_at": get_utc8_now()
                    }
                }
            )

            logger.info(f"📊 [progress update] Update results: matched={result.matched_count}, modified={result.modified_count}")

            sync_client.close()
            logger.info(f"✅ Task {job_id} Progress updated successfully: {progress}% - {message}")

        except Exception as e:
            if "TaskCancelledException" in str(type(e).__name__):
                raise
            logger.error(f"❌ Failed to update task progress: {e}", exc_info=True)

    async def _mark_task_completed(self, job_id: str, stats: Dict[str, Any]):
        """
        Mark task as completed
        
        Args:
            job_id: Task ID
            stats: Sync statistics
        """
        # 🔥 Use mark_job_completed function uniformly to ensure that both MongoDB and Redis are updated correctly
        try:
            from app.services.scheduler_service import mark_job_completed
            # 🔥 Modify the logic: if the success rate >= 80%, It should not be marked as failed even if there are errors
            success_count = stats.get("success_count", 0)
            total_processed = stats.get("total_processed", 0)
            error_count = stats.get("error_count", 0)
            success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
            
            error_message = None
            if error_count > 0 and success_rate < 80:
                # only success rate < 80% Set only when error_message
                error_messages = [e.get("error", "") for e in stats.get("errors", [])[:5]]
                error_message = f"Synchronization is complete but there are {error_count} errors: {', '.join(error_messages)}"
            
            await mark_job_completed(job_id, stats, error_message)
        except Exception as e:
            logger.error(f"❌ Mark task completion failed: {e}", exc_info=True)

    async def _mark_task_failed(self, job_id: str, error_message: str):
        """
        Mark task as failed
        
        Args:
            job_id: Task ID
            error_message: error message
        """
        # 🔥 Use mark_job_completed function uniformly to ensure that both MongoDB and Redis are updated correctly
        try:
            from app.services.scheduler_service import mark_job_completed
            await mark_job_completed(job_id, None, error_message)
        except Exception as e:
            logger.error(f"❌ Error while marking task failed status: {e}", exc_info=True)

    async def retry_failed_symbols(
        self,
        errors: List[Dict[str, Any]],
        start_date: str = None,
        end_date: str = None,
        period: str = "daily",
        job_id: str = None,
        _is_retry: bool = False  # 🔥 Internal mark indicating that this is a retry task to avoid automatic retries again
    ) -> Dict[str, Any]:
        """
        Retry failed stocks (retry only retryable errors, skip errors with no data)
        
        Args:
            errors: Error list (obtained from previous sync results)
            start_date: start date
            end_date: end date
            period: data period (daily/weekly/monthly)
            job_id: Task ID (for progress tracking)
            
        Returns:
            Retry result statistics
        """
        period_name = {"daily": "daily line", "weekly": "perimeter", "monthly": "monthly line"}.get(period, period)
        
        # 🔥 Filter out retryable errors
        retryable_errors = [
            error for error in errors
            if error.get("error_category") == "retryable_error" 
            or error.get("is_retryable", False)
        ]
        
        no_data_errors = [
            error for error in errors
            if error.get("error_category") == "no_data"
            or (not error.get("is_retryable", True) and error.get("error_category") != "retryable_error")
        ]
        
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
        
        # Extract retryable tickers
        retry_symbols = [error["code"] for error in retryable_errors]
        
        logger.info(f"📋 Will retry following {len(retry_symbols)} only stocks: {', '.join(retry_symbols[:10])}{'...' if len(retry_symbols) > 10 else ''}")
        
        # Call the synchronization method to synchronize only these failed stocks
        retry_result = await self.sync_historical_data(
            symbols=retry_symbols,
            start_date=start_date,
            end_date=end_date,
            incremental=False,  # Use full sync when retrying
            all_history=False,
            period=period,
            job_id=job_id,
            auto_retry=False,  # 🔥 The retry task itself will no longer be automatically retried to avoid infinite loops
            _is_retry=True  # 🔥 Mark task for retry
        )
        
        # Merge results
        retry_result["total_retried"] = len(retry_symbols)
        retry_result["no_data_count"] = len(no_data_errors)
        retry_result["retryable_errors_count"] = len(retryable_errors)
        
        logger.info(f"✅ Retry complete: success {retry_result['success_count']}/{retry_result['total_retried']}, "
                   f"failed {retry_result['error_count']}, No data {retry_result['no_data_count']} (skipped)")
        
        return retry_result


# Global synchronization service instance
_tushare_sync_service = None

async def get_tushare_sync_service() -> TushareSyncService:
    """Get Tushare synchronization service instance"""
    global _tushare_sync_service
    if _tushare_sync_service is None:
        _tushare_sync_service = TushareSyncService()
        await _tushare_sync_service.initialize()
    return _tushare_sync_service


async def create_tushare_sync_service() -> TushareSyncService:
    """Create an independent Tushare synchronization service instance.

    Used for long tasks in the thread pool to avoid reusing global singletons that will cause the database connection to be bound to a closed or wrong event loop.
    """
    service = TushareSyncService()
    await service.initialize()
    return service


# APScheduler Compatible task functions

async def _check_task_running(
    job_id: str,
    resume_execution_id: Optional[str] = None,
    exclude_execution_id: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Check if an instance of the task is already running
    
    Args:
        job_id: Task ID
        resume_execution_id: If the execution is to be resumed, pass in the execution record ID to be resumed (execution is allowed at this time, even if there is a running record)
        exclude_execution_id: The ID of the record currently being prepared for execution. It should exclude itself when checking concurrency.
        
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
        
        # 🔥 If execution is resumed, check whether the same execution record is restored
        if resume_execution_id:
            try:
                from bson import ObjectId
                resume_record = sync_db.scheduler_executions.find_one({"_id": ObjectId(resume_execution_id)})
                if resume_record:
                    # If the same execution record is restored, execution is allowed (even if the status is running)
                    # Because this is a user-initiated recovery, execution should be allowed to continue.
                    logger.info(f"✅ Restore execution record {resume_execution_id}, allow execution")
                    sync_client.close()
                    return False, None  # allow execution
            except Exception as e:
                logger.warning(f"⚠️ Checking recovery execution records failed: {e}")
        
        # 🔥 Find if there are any running instances (excluding tasks that have timed out)
        # Judgment criteria:
        # 1. status=running
        # 2. Prioritize using updated_at to determine whether there is still a heartbeat in the last 30 minutes
        # 3. Compatible with old records: fall back to when there is no updated_at timestamp
        threshold_time = get_utc8_now() - timedelta(minutes=30)
        
        query = {
            "job_id": job_id,
            "status": "running",
            "$or": [
                {"updated_at": {"$gte": threshold_time}},
                {
                    "updated_at": {"$exists": False},
                    "timestamp": {"$gte": threshold_time}
                }
            ]
        }

        if exclude_execution_id:
            try:
                from bson import ObjectId
                query["_id"] = {"$ne": ObjectId(exclude_execution_id)}
            except Exception as e:
                logger.warning(f"⚠️ Unable to parse execution records that need to be excluded ID {exclude_execution_id}: {e}")

        running_instance = sync_db.scheduler_executions.find_one(
            query,
            sort=[("timestamp", -1)]
        )
        
        # 🔥 If a running task that times out is found, it is automatically marked as failed.
        if not running_instance:
            # Check if there are any running tasks that have timed out
            zombie_instance = sync_db.scheduler_executions.find_one(
                {
                    "job_id": job_id,
                    "status": "running",
                    "$or": [
                        {"updated_at": {"$lt": threshold_time}},
                        {
                            "updated_at": {"$exists": False},
                            "timestamp": {"$lt": threshold_time}
                        }
                    ]
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


async def run_tushare_basic_info_sync(force_update: bool = False, **kwargs):
    """APScheduler Task: Synchronize basic stock information"""
    job_id = "tushare_basic_info_sync"
    
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
        service = await get_tushare_sync_service()
        result = await service.sync_stock_basic_info(force_update, job_id=job_id)
        logger.info(f"✅ Tushare Basic information synchronization completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Tushare Basic information synchronization failed: {e}")
        raise


async def run_tushare_quotes_sync(force: bool = False):
    """
    APScheduler Task: Synchronize real-time market conditions

    Args:
        force: Whether to enforce execution (skip transaction time check), default False
    """
    try:
        service = await get_tushare_sync_service()
        result = await service.sync_realtime_quotes(force=force)
        logger.info(f"✅ Tushare Market synchronization completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Tushare Market synchronization failed: {e}")
        raise


async def run_tushare_realtime_quotes_hourly(**kwargs):
    """
    APScheduler Task: Synchronize Tushare real-time quotes every hour at 31 minutes
    
    Special handling:
    - If it is after 3 p.m. (15:00) , Update to historical data after successful call
    - if not more than 15:00, Normal updates of real-time quotes
    
    Note: Free users can only call the rt_k interface once per hour, so choose to execute it at 31 minutes every hour.
    """
    from datetime import datetime
    from app.utils.timezone import now_tz
    from app.core.database import get_mongo_db
    from app.services.historical_data_service import get_historical_data_service
    import pandas as pd
    
    job_id = "tushare_realtime_quotes_hourly"
    
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
        current_time = now_tz()
        current_hour = current_time.hour
        
        logger.info(f"🕐 [Tushare Real-time quotes synchronized every hour] Start execution, current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Call real-time market synchronization
        service = await get_tushare_sync_service()
        result = await service.sync_realtime_quotes(force=True)  # Force sync, skip transaction time check
        
        if not result.get("success_count", 0) > 0:
            logger.warning(f"⚠️ [Tushare Real-time quotes synchronized every hour] Synchronization failed or data was not obtained")
            
            # 🔥 Update task status is failed
            job_id = "tushare_realtime_quotes_hourly"
            error_message = "Synchronization failed: no data obtained"
            if result.get("errors"):
                error_messages = [e.get("error", "") for e in result.get("errors", [])[:3]]
                error_message = f"Sync failed: {', '.join(error_messages)}"
            
            try:
                from app.services.scheduler_service import mark_job_completed
                await mark_job_completed(job_id, result, error_message)
            except Exception as update_error:
                logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return result
        
        logger.info(f"✅ [Tushare Real-time quotes synchronized every hour] Real-time market synchronization successful: success {result.get('success_count', 0)} only")
        
        # If it is after 3 p.m. (15:00) , Save real-time quotes to historical data
        if current_hour >= 15:
            logger.info(f"📊 [Tushare Real-time quotes synchronized every hour] The current time exceeds 15:00, Start saving real-time quotes to historical data...")
            
            try:
                db = get_mongo_db()
                historical_service = await get_historical_data_service()
                
                # Get today's date (YYYYMMDD format)
                today_str = current_time.strftime('%Y%m%d')
                
                # Read all real-time market data from the market_quotes collection
                market_quotes_collection = db["market_quotes"]
                cursor = market_quotes_collection.find({})
                
                quotes_list = await cursor.to_list(length=None)
                
                if not quotes_list:
                    logger.warning(f"⚠️ [Tushare Real-time quotes synchronized every hour] market_quotes The collection is empty and historical data cannot be saved.")
                    # 🔥 Although the real-time market synchronization was successful, the historical data failed to be saved and was marked as partial failure.
                    job_id = "tushare_realtime_quotes_hourly"
                    try:
                        from app.services.scheduler_service import mark_job_completed
                        result["error_count"] = result.get("error_count", 0) + 1
                        result["errors"] = result.get("errors", [])
                        result["errors"].append({"error": "market_quotes The collection is empty and historical data cannot be saved."})
                        await mark_job_completed(job_id, result)
                    except Exception as update_error:
                        logger.warning(f"⚠️ An error occurred while updating task status: {update_error}")
                    return result
                
                logger.info(f"📊 [Tushare Real-time quotes synchronized every hour] Read from market_quotes {len(quotes_list)} pieces of real-time market data")
                
                # Batch convert to historical data format and save
                saved_count = 0
                error_count = 0
                
                for quote_doc in quotes_list:
                    try:
                        symbol = quote_doc.get("symbol") or quote_doc.get("code", "")
                        if not symbol:
                            continue
                        
                        # Build historical data records (single record DataFrame)
                        # Note: The format of the data in market_quotes depends on the data source
                        # - if from get_realtime_quotes_batch(): volume (stocks, rt_k returns vol), amount (yuan, rt_k returns amount)
                        # - if from standardize_quotes(): volume (shares, converted), amount (yuan, converted)
                        # Historical data service expectations tushare data source format is: volume (hand), amount (thousand yuan)
                        # Therefore, reverse conversion is required: volume / 100 (shares change hands), amount / 1000 (yuan converted into thousand yuan)
                        
                        # Get raw data
                        volume_gu = float(quote_doc.get("volume", 0) or 0)  # shares
                        amount_yuan = float(quote_doc.get("amount", 0) or 0)  # Yuan
                        pre_close = float(quote_doc.get("pre_close", 0) or 0)
                        
                        # Convert to historical data format (lots, thousand dollars)
                        volume_shou = volume_gu / 100.0 if volume_gu > 0 else 0  # Shares change hands
                        amount_qian = amount_yuan / 1000.0 if amount_yuan > 0 else 0  # Yuan to thousand Yuan
                        
                        # If there is no pre_close, try to calculate from change and close
                        if not pre_close and quote_doc.get("close") and quote_doc.get("change"):
                            try:
                                close = float(quote_doc.get("close", 0))
                                change = float(quote_doc.get("change", 0))
                                pre_close = close - change
                            except (ValueError, TypeError):
                                pass
                        
                        historical_data = {
                            "trade_date": today_str,  # YYYYMMDD Format
                            "open": float(quote_doc.get("open", 0) or 0),
                            "high": float(quote_doc.get("high", 0) or 0),
                            "low": float(quote_doc.get("low", 0) or 0),
                            "close": float(quote_doc.get("close", 0) or 0),
                            "pre_close": pre_close,  # Previous closing price (important field)
                            "volume": volume_shou,  # hands, the historical data service will automatically convert to stocks
                            "amount": amount_qian,  # thousand yuan, the historical data service will automatically convert it to yuan
                            "pct_chg": float(quote_doc.get("pct_chg", 0) or 0),
                        }
                        
                        # Create DataFrame (single row of data)
                        # Index usage date to facilitate historical_data_service processing
                        df = pd.DataFrame([historical_data])
                        df.index = pd.to_datetime([today_str], format='%Y%m%d')
                        
                        # Save to historical data collection
                        count = await historical_service.save_historical_data(
                            symbol=symbol,
                            data=df,
                            data_source="tushare",
                            market="CN",
                            period="daily"
                        )
                        
                        if count > 0:
                            saved_count += 1
                        else:
                            error_count += 1
                            
                    except Exception as e:
                        error_count += 1
                        symbol = quote_doc.get("symbol") or quote_doc.get("code", "unknown")
                        logger.error(f"❌ [Tushare Real-time quotes synchronized every hour] save {symbol} Historical data failed: {e}")
                
                logger.info(
                    f"✅ [Tushare Real-time quotes synchronized every hour] Historical data saving completed: "
                    f"total {len(quotes_list)} only, "
                    f"success {saved_count} only, "
                    f"failed {error_count} only"
                )
                
                result["historical_saved_count"] = saved_count
                result["historical_error_count"] = error_count
                
            except Exception as e:
                logger.error(f"❌ [Tushare Real-time quotes synchronized every hour] Failed to save historical data: {e}", exc_info=True)
                result["historical_save_error"] = str(e)
        else:
            logger.info(f"📊 [Tushare Real-time quotes synchronized every hour] The current time has not exceeded 15:00, Only update real-time quotes")
        
        # 🔥 Update task status to Completed (successful)
        job_id = "tushare_realtime_quotes_hourly"
        try:
            from app.services.scheduler_service import mark_job_completed
            await mark_job_completed(job_id, result)
        except Exception as update_error:
            logger.warning(f"⚠️ An error occurred while updating task completion status: {update_error}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ [Tushare Real-time quotes synchronized every hour] Execution failed: {e}", exc_info=True)
        
        # 🔥 Update task status is failed
        job_id = "tushare_realtime_quotes_hourly"
        try:
            from app.services.scheduler_service import mark_job_completed
            await mark_job_completed(job_id, None, str(e))
        except Exception as update_error:
            logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
        
        raise


async def run_tushare_historical_sync(incremental: bool = True, **kwargs):
    """APScheduler Task: Synchronize historical data"""
    job_id = "tushare_historical_sync"
    
    # 🔥 Extract recovery location information, manual trigger flags and enforcement flags from kwargs
    resume_from_index = kwargs.get("_resume_from_index")
    resume_execution_id = kwargs.get("_resume_execution_id")  # Execution records when resuming execution ID
    trigger_execution_id = kwargs.get("_trigger_execution_id")  # Pre-created execution records when triggered manually ID
    manual_trigger = kwargs.get("_manual_trigger", False)  # Manual trigger tag
    force_execute = kwargs.get("_force_execute", False)  # Enforce flag
    
    # 🔥 Only resuming execution or forcing execution allows bypassing concurrency checks
    # Ordinary manual triggering still needs to check whether there are existing unfinished tasks of the same type to prevent users from repeatedly clicking on multiple instances.
    if resume_from_index is not None or resume_execution_id is not None or force_execute:
        if resume_from_index is not None or resume_execution_id is not None:
            logger.info(f"🔄 [APScheduler] Resume execution from section {resume_from_index} positions to continue (execution_id={resume_execution_id})")
        if force_execute:
            logger.info(f"🔧 [APScheduler] Force execution, skip concurrency checks")
        # When resuming execution or forcing execution, concurrency is not checked and execution is allowed directly.
    else:
        # 🔥 Check whether there is already an instance running (normal manual triggers should also be checked)
        is_running, instance_id = await _check_task_running(
            job_id,
            exclude_execution_id=trigger_execution_id
        )
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    
    # 🔥 Clean up internal tags (these should not be passed to sync_historical_data)
    clean_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_") or k == "_resume_from_index"}
    
    logger.info(f"🚀 [APScheduler] Start Tushare historical data synchronization task (incremental={incremental}, kwargs={clean_kwargs})")
    try:
        # 🔥 Use unified thread pool synchronization service
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        # 🔥 Create an independent service instance for historical synchronization to avoid cross-event loop connection pollution caused by reusing global singletons
        service = await create_tushare_sync_service()
        logger.info(f"✅ [APScheduler] Tushare The independent synchronization service has been initialized (only for historical synchronization)")
        
        # 🔥 Execute synchronized methods in thread pool
        sync_result = await unified_service.execute_sync_method(
            sync_method=service.sync_historical_data,
            method_kwargs={
                "incremental": incremental,
                "period": clean_kwargs.get("period", "daily"),
                "start_date": clean_kwargs.get("start_date"),
                "end_date": clean_kwargs.get("end_date"),
                "symbols": clean_kwargs.get("symbols"),
                "job_id": "tushare_historical_sync",
                **{k: v for k, v in clean_kwargs.items() if k not in ["period", "start_date", "end_date", "symbols"]}
            },
            job_id=job_id,
            rate_limit_per_minute=kwargs.get("rate_limit_per_minute", 200),  # Tushare rate limit
            resume_from_index=resume_from_index
        )
        
        if sync_result.success:
            result = sync_result.result
            logger.info(f"✅ [APScheduler] Tushare Historical data synchronization completed: {result}")
            return result
        else:
            # 🔥 Check if the task is canceled
            if "Cancel" in sync_result.error or "cancelled" in sync_result.error.lower():
                logger.info(f"ℹ️ [APScheduler] Tushare The historical data synchronization task has been canceled by the user")
                return {"cancelled": True, "message": sync_result.error}
            else:
                logger.error(f"❌ [APScheduler] Tushare Historical data synchronization failed: {sync_result.error}")
                raise RuntimeError(sync_result.error)
                
    except Exception as e:
        # Check whether it is a task cancellation exception (the user actively cancels and should not be recorded as an error)
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ [APScheduler] Tushare The historical data synchronization task has been canceled by the user")
            return {"cancelled": True, "message": "The task has been canceled by the user"}
        # Other exceptions are recorded as errors
        logger.error(f"❌ [APScheduler] Tushare Historical data synchronization failed: {e}", exc_info=True)
        raise


async def run_tushare_financial_sync(**kwargs):
    """
    APScheduler Task: Synchronize financial data (using thread pool version)
    
    🔥 Updated to use unified financial data synchronization service (thread pool version)
    """
    job_id = "tushare_financial_sync"
    
    # 🔥 Ordinary manual triggering also needs to check whether there are any unfinished tasks, and it will only be skipped if it is forced to execute.
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    trigger_execution_id = kwargs.get("_trigger_execution_id")
    if not force_execute:
        # 🔥 Check whether there is already an instance running (normal manual triggering also checks)
        is_running, instance_id = await _check_task_running(
            job_id,
            exclude_execution_id=trigger_execution_id
        )
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {
                "skipped": True,
                "reason": "There is already an instance running",
                "running_instance_id": instance_id
            }
    else:
        if force_execute:
            logger.info(f"🔧 [APScheduler] Force execution, skip concurrency checks")
    
    try:
        # 🔥 Use unified financial data synchronization service (thread pool version)
        from app.worker.financial_data_sync_service import get_financial_sync_service
        
        service = await get_financial_sync_service()
        
        # 🔥 Check whether it is a resume execution and read the resume location from kwargs
        resume_from_index = kwargs.get("_resume_from_index")
        if resume_from_index is not None:
            logger.info(f"🔄 [Resume execution] will be from {resume_from_index} Stock positions continue to be synchronized")
        
        results = await service.sync_financial_data(
            symbols=None,  # None Indicates synchronization of all stocks
            data_sources=["tushare"],  # Only synchronize Tushare data sources
            report_types=["quarterly", "annual"],
            job_id=job_id,
            _resume_from_index=resume_from_index  # 🔥 Pass restore position parameters
        )
        
        # Convert to older formats to maintain compatibility
        if "tushare" in results:
            stats = results["tushare"]
            result = {
                "success": True,
                "total_symbols": stats.total_symbols,
                "success_count": stats.success_count,
                "error_count": stats.error_count,
                "duration": stats.duration
            }
        else:
            result = {"success": False, "message": "Tushare Data source synchronization failed"}
        
        logger.info(f"✅ Tushare Financial data synchronization completed (thread pool version): {result}")
        return result
    except Exception as e:
        # Check whether it is a task cancellation exception (the user actively cancels and should not be recorded as an error)
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ Tushare The financial data synchronization task has been canceled by the user")
            return {"cancelled": True, "message": "The task has been canceled by the user"}
        # Other exceptions are recorded as errors
        logger.error(f"❌ Tushare Financial data synchronization failed: {e}", exc_info=True)
        raise


async def run_tushare_status_check():
    """APScheduler Task: Check sync status"""
    try:
        service = await get_tushare_sync_service()
        result = await service.get_sync_status()
        logger.info(f"✅ Tushare Status check completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Tushare Status check failed: {e}")
        return {"error": str(e)}


async def run_tushare_news_sync(hours_back: int = 24, max_news_per_stock: int = 20, **kwargs):
    """APScheduler Task: Synchronize news data"""
    job_id = "tushare_news_sync"
    
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
        service = await get_tushare_sync_service()
        result = await service.sync_news_data(
            hours_back=hours_back,
            max_news_per_stock=max_news_per_stock,
            job_id="tushare_news_sync"
        )
        logger.info(f"✅ Tushare News data synchronization completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Tushare News data synchronization failed: {e}")
        raise
