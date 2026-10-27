"""
AKShare Data synchronization service
Unified data synchronization solution based on AKShare provider
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pymongo

from app.core.database import bind_loop_safe_mongo_db, get_mongo_db
from app.services.historical_data_service import get_historical_data_service
from app.services.news_data_service import get_news_data_service
from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

logger = logging.getLogger(__name__)

ETF_SH_PREFIXES = ("50", "51", "52", "56", "58")
ETF_SZ_PREFIXES = ("15", "16", "18")


def _is_etf_code(symbol: str) -> bool:
    """Determine whether the code belongs to ETF/FUND to avoid mistakenly following the stock history synchronization link."""
    digits = "".join(ch for ch in str(symbol or "") if ch.isdigit())
    normalized = digits[-6:].zfill(6) if digits else ""
    return len(normalized) == 6 and normalized.startswith(ETF_SH_PREFIXES + ETF_SZ_PREFIXES)


class AKShareSyncService:
    """
    AKShare Data synchronization service
    
    Provides complete data synchronization functions:
    - Synchronization of basic stock information
    - Real-time market synchronization
    - Historical data synchronization
    - Financial data synchronization
    """
    
    def __init__(self):
        self.provider = None
        self.historical_service = None  # Lazy initialization
        self.news_service = None  # Lazy initialization
        self.db = None
        self.batch_size = 100
        self.rate_limit_delay = 0.2  # AKShare Recommended delay
        self._current_job_id = None  # 🔥 Current task ID, used for progress tracking and stop checking

    def _resolve_job_id(self, manual_mode: bool = False) -> Optional[str]:
        """Resolve the scheduled task ID of the current execution context."""
        if manual_mode:
            return None

        job_id = getattr(self, '_current_job_id', None)
        if isinstance(job_id, str):
            job_id = job_id.strip()
        return job_id or None
    
    async def initialize(self):
        """Initialize synchronization service"""
        try:
            # Initialize database connection
            self.db = get_mongo_db()

            # Initialize historical data service
            self.historical_service = await get_historical_data_service()

            # Initialize news data service
            self.news_service = await get_news_data_service()

            # Initialize the AKShare provider (use a global singleton to ensure the monkey patch takes effect)
            self.provider = get_akshare_provider()

            # test connection
            if not await self.provider.test_connection():
                raise RuntimeError("❌ AKShare Connection failed, unable to start synchronization service")

            logger.info("✅ AKShare Synchronization service initialization completed")
            
        except Exception as e:
            logger.error(f"❌ AKShare Sync service initialization failed: {e}")
            raise
    
    async def sync_stock_basic_info(self, force_update: bool = False, manual_mode: bool = False) -> Dict[str, Any]:
        """
        Synchronize basic stock information
        
        Args:
            force_update: Whether to force update
            manual_mode: Whether it is a manual API call; manual mode does not read or write back the scheduled task status
            
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
            "end_time": None,
            "duration": 0,
            "errors": []
        }
        job_id = self._resolve_job_id(manual_mode)
        
        try:
            # 1. Get a list of stocks
            stock_list = await self.provider.get_stock_list()
            if not stock_list:
                logger.warning("⚠️ No stock list obtained")
                return stats
            
            stats["total_processed"] = len(stock_list)
            logger.info(f"📊 Get {len(stock_list)} Only stock information")
            
            # 2. Batch processing
            for i in range(0, len(stock_list), self.batch_size):
                batch = stock_list[i:i + self.batch_size]
                batch_stats = await self._process_basic_info_batch(batch, force_update)
                
                # Update statistics
                stats["success_count"] += batch_stats["success_count"]
                stats["error_count"] += batch_stats["error_count"]
                stats["skipped_count"] += batch_stats["skipped_count"]
                stats["errors"].extend(batch_stats["errors"])
                
                # progress log
                progress = min(i + self.batch_size, len(stock_list))
                logger.info(f"📈 Basic information synchronization progress: {progress}/{len(stock_list)} "
                           f"(success: {stats['success_count']}, Error: {stats['error_count']})")
                
                # API Current limiting
                if i + self.batch_size < len(stock_list):
                    await asyncio.sleep(self.rate_limit_delay)
            
            # 3. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            
            logger.info(f"🎉 Basic stock information is synchronized!")
            logger.info(f"📊 total: {stats['total_processed']}only, "
                       f"success: {stats['success_count']}, "
                       f"Error: {stats['error_count']}, "
                       f"skip: {stats['skipped_count']}, "
                       f"Time consuming: {stats['duration']:.2f}seconds")
            
            # 🔥 Update task status to Completed
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Synchronization of basic stock information failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_stock_basic_info"})
            
            # 🔥 Update task status is failed
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats
    
    def _build_basic_info_from_list(
        self, code: str, name: str, industry: str = ""
    ) -> Dict[str, Any]:
        """from stock list + Basic information of industry construction (to avoid account ban due to AKShare polling query industry)"""
        from datetime import datetime, timezone
        code6 = str(code).strip().zfill(6)
        market = "motherboard"
        if code6.startswith(("60", "68", "90")):
            market = "motherboard" if code6.startswith("60") else ("Science and Technology Innovation Board" if code6.startswith("68") else "Beijing Exchange")
        elif code6.startswith("00"):
            market = "motherboard" if code6.startswith("000") else "Small and medium board" if code6.startswith("002") else "GEM"
        elif code6.startswith("30"):
            market = "GEM"
        elif code6.startswith("8"):
            market = "Beijing Exchange"
        ts_code = f"{code6}.SH" if code6.startswith(("60", "68", "90")) else f"{code6}.SZ" if code6.startswith(("00", "30")) else f"{code6}.BJ"
        now = datetime.now(timezone.utc)
        return {
            "code": code6,
            "symbol": code6,
            "name": name or f"stocks{code6}",
            "industry": industry or "unknown",
            "area": "",
            "market": market,
            "list_date": "",
            "full_symbol": ts_code,
            "source": "akshare",
            "data_source": "akshare",
            "updated_at": now,
        }

    async def _process_basic_info_batch(self, batch: List[Dict[str, Any]], force_update: bool) -> Dict[str, Any]:
        """Process basic information batches"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "errors": []
        }

        # Priority is given to using the system industry mapping collection. In the future, it can be provided by the official website interface. If it is currently empty, it will temporarily fall back to Tushare.
        from app.services.official_industry_service import fetch_industry_mapping
        industry_mapping = await fetch_industry_mapping(refresh_if_empty=True)
        use_system_industry_mapping = bool(industry_mapping)
        if use_system_industry_mapping:
            logger.info(f"📊 Use the system industry mapping collection ({len(industry_mapping)} only), skipping AKShare polling queries")
        
        for stock_info in batch:
            try:
                code = stock_info["code"]
                name = stock_info.get("name", "")
                code6 = str(code).strip().zfill(6)
                mapped_industry = industry_mapping.get(code6, "") if use_system_industry_mapping else ""
                
                # Check if updates are needed
                if not force_update:
                    existing = await self.db.stock_basic_info.find_one({"code": code6, "source": "akshare"})
                    if existing and self._is_data_fresh(existing.get("updated_at"), hours=24):
                        existing_industry = str(existing.get("industry") or "").strip()
                        has_existing_industry = existing_industry not in ("", "unknown")
                        if use_system_industry_mapping:
                            if mapped_industry and existing_industry == mapped_industry:
                                batch_stats["skipped_count"] += 1
                                continue
                            if not mapped_industry and has_existing_industry:
                                batch_stats["skipped_count"] += 1
                                continue
                        else:
                            batch_stats["skipped_count"] += 1
                            continue
                
                if use_system_industry_mapping:
                    industry = mapped_industry or "unknown"
                    basic_info = self._build_basic_info_from_list(code, name, industry)
                else:
                    basic_info = await self.provider.get_stock_basic_info(code)
                
                if basic_info:
                    # Convert to dictionary format
                    if hasattr(basic_info, 'model_dump'):
                        basic_data = basic_info.model_dump()
                    elif hasattr(basic_info, 'dict'):
                        basic_data = basic_info.dict()
                    else:
                        basic_data = basic_info
                    
                    # 🔥 Make sure the source field exists
                    if "source" not in basic_data:
                        basic_data["source"] = "akshare"

                    if use_system_industry_mapping and mapped_industry:
                        basic_data["industry"] = mapped_industry
                        basic_data["industry_source"] = "system_industry_mapping"

                    # 🔥 Make sure the symbol field exists
                    if "symbol" not in basic_data:
                        basic_data["symbol"] = code6

                    # Update to database (using code + source Union query)
                    try:
                        await self.db.stock_basic_info.update_one(
                            {"code": code6, "source": "akshare"},
                            {"$set": basic_data},
                            upsert=True
                        )
                        batch_stats["success_count"] += 1
                    except Exception as e:
                        batch_stats["error_count"] += 1
                        batch_stats["errors"].append({
                            "code": code,
                            "error": f"Database update failed: {str(e)}",
                            "context": "update_stock_basic_info"
                        })
                else:
                    batch_stats["error_count"] += 1
                    batch_stats["errors"].append({
                        "code": code,
                        "error": "Failed to obtain basic information",
                        "context": "get_stock_basic_info"
                    })
                
            except Exception as e:
                batch_stats["error_count"] += 1
                batch_stats["errors"].append({
                    "code": stock_info.get("code", "unknown"),
                    "error": str(e),
                    "context": "_process_basic_info_batch"
                })
        
        return batch_stats
    
    def _is_data_fresh(self, updated_at: Any, hours: int = 24, minutes: int = None) -> bool:
        """
        Check if the data is fresh
        
        Args:
            updated_at: Update time
            hours: Number of hours (default 24 hours)
            minutes: Number of minutes (if specified, overrides the hours parameter)
        
        Returns:
            bool: Is the data fresh?
        """
        if not updated_at:
            return False
        
        try:
            # Parse time string
            if isinstance(updated_at, str):
                # Handling ISO format time strings
                updated_at_str = updated_at.replace('Z', '+00:00')
                try:
                    updated_at = datetime.fromisoformat(updated_at_str)
                except ValueError:
                    # Try another format
                    try:
                        updated_at = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        logger.warning(f"⚠️ Unable to parse time format: {updated_at}")
                        return False
            elif isinstance(updated_at, datetime):
                pass
            else:
                return False
            
            # 🔥 Fixed time zone issue: uniformly use local time for comparison
            # If updated_at has time zone information, convert to local time; if not, assume local time
            if updated_at.tzinfo is not None:
                # Time zone information, converted to local time
                from datetime import timezone
                if updated_at.tzinfo == timezone.utc:
                    # UTC time, converted to local time (UTC+8) 
                    updated_at = updated_at.replace(tzinfo=None) + timedelta(hours=8)
                else:
                    # Other time zones, converted to local time
                    updated_at = updated_at.astimezone().replace(tzinfo=None)
            
            # Use local time for comparison
            now = datetime.now()
            time_diff = now - updated_at
            
            # If minutes are specified, use minutes; otherwise use hours
            if minutes is not None:
                is_fresh = time_diff.total_seconds() < (minutes * 60)
            else:
                is_fresh = time_diff.total_seconds() < (hours * 3600)
            
            logger.debug(f"🔍 Data freshness check: updated_at={updated_at}, now={now}, diff={time_diff.total_seconds()/60:.1f}minutes, fresh={is_fresh}")
            
            return is_fresh
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to check data freshness: {e}")
            return False
    
    def _is_data_complete(self, quotes_data: Dict[str, Any]) -> bool:
        """
        Check if the data is complete
        
        Args:
            quotes_data: Market data dictionary
        
        Returns:
            bool: Is the data complete?
        """
        if not quotes_data:
            return False
        
        # 🔥 Check if the key field exists and is not None
        required_fields = ['price', 'change_percent', 'amount']
        optional_fields = ['volume', 'open', 'high', 'low']
        
        # Check required fields
        for field in required_fields:
            if field not in quotes_data or quotes_data[field] is None:
                logger.debug(f"⚠️ Data is incomplete: Missing required field {field}")
                return False
        
        # 🔥 Check optional fields: data is also considered incomplete if all optional fields are None
        optional_count = sum(1 for field in optional_fields if quotes_data.get(field) is not None)
        if optional_count == 0:
            logger.debug(f"⚠️ Data is incomplete: All optional fields ({optional_fields}) All None")
            return False
        
        return True
    
    async def sync_realtime_quotes(self, symbols: List[str] = None, force: bool = False, manual_mode: bool = False) -> Dict[str, Any]:
        """
        Synchronize real-time market data

        Args:
            symbols: Specify a list of stock codes. If empty, all stocks will be synchronized.
            force: Whether to enforce execution (skip transaction time check), default False
            manual_mode: Whether it is a manual API call; manual mode does not read or write back the scheduled task status

        Returns:
            Synchronization result statistics
        """
        # 🔥 If a stock list is specified, log
        if symbols:
            logger.info(f"🔄 Start synchronizing the real-time quotes of specified stocks (total {len(symbols)} only): {symbols}")
        else:
            logger.info("🔄 Start synchronizing real-time market conditions across the entire market...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": []
        }
        job_id = self._resolve_job_id(manual_mode)

        try:
            # 1. Determine the stock list to sync
            if symbols is None:
                # Get all listed stock codes from the database (excluding delisted stocks)
                basic_info_cursor = self.db.stock_basic_info.find(
                    {"list_status": "L"},  # Get only listed stocks
                    {"code": 1}
                )
                symbols = [doc["code"] async for doc in basic_info_cursor]

            if not symbols:
                logger.warning("⚠️ No stocks found to sync")
                return stats

            stats["total_processed"] = len(symbols)
            logger.info(f"📊 Prepare to sync {len(symbols)} Quotes of stocks")

            # 🔥 Optimization: If you only synchronize 1 stock, call the single stock interface directly instead of using the batch interface.
            if len(symbols) == 1:
                logger.info(f"📈 Single stock synchronization, directly use the get_stock_quotes interface")
                symbol = symbols[0]
                
                # 🔥 Check data freshness and completeness first
                try:
                    existing = await self.db.market_quotes.find_one(
                        {"code": symbol}
                    )
                    
                    # 🔥 Check that the data is fresh and complete
                    is_fresh = existing and self._is_data_fresh(existing.get("updated_at"), minutes=15)
                    is_complete = existing and self._is_data_complete(existing)
                    
                    if is_fresh and is_complete:
                        logger.info(f"✅ {symbol} Data is fresh and complete (within 15 minutes), synchronization is skipped")
                        stats["success_count"] = 1
                    elif is_fresh and not is_complete:
                        logger.warning(f"⚠️ {symbol} Data is fresh but incomplete, forced synchronization")
                        # Incomplete data, forced synchronization
                    else:
                        # If the data is older than 15 minutes or does not exist, synchronize it.
                        success = await self._get_and_save_quotes(symbol)
                        if success:
                            stats["success_count"] = 1
                        else:
                            # 🔥 Synchronization of individual stocks failed and fell back to the full synchronization interface.
                            logger.warning(f"⚠️ {symbol} Single stock synchronization failed, try to use the full synchronization interface...")
                            all_symbols = await self._get_all_listed_symbols()
                            if all_symbols:
                                quotes_map = await self.provider.get_batch_stock_quotes(all_symbols)
                                if quotes_map:
                                    # 🔥 Full synchronization is successful and all data is updated in batches to the database
                                    logger.info(f"✅ Full synchronization was successful and obtained {len(quotes_map)} Only stock data starts to be updated in batches to the database...")
                                    updated_count = await self._batch_update_quotes_to_db(quotes_map)
                                    logger.info(f"✅ Batch update completed, total updates {updated_count} Only stock data")
                                    
                                    # Check if the target stock is in the update results
                                    if symbol in quotes_map:
                                        stats["success_count"] = 1
                                    else:
                                        stats["error_count"] = 1
                                        stats["errors"].append({
                                            "code": symbol,
                                            "error": "The stock data was not found in full synchronization",
                                            "context": "sync_realtime_quotes_single_fallback"
                                        })
                                else:
                                    stats["error_count"] = 1
                                    stats["errors"].append({
                                        "code": symbol,
                                        "error": "The full synchronization interface also failed",
                                        "context": "sync_realtime_quotes_single_fallback"
                                    })
                            else:
                                stats["error_count"] = 1
                                stats["errors"].append({
                                    "code": symbol,
                                    "error": "Unable to get stock list",
                                    "context": "sync_realtime_quotes_single_fallback"
                                })
                except Exception as e:
                    logger.error(f"❌ Check {symbol} Data freshness failed: {e}, Try to sync")
                    success = await self._get_and_save_quotes(symbol)
                    if success:
                        stats["success_count"] = 1
                    else:
                        stats["error_count"] = 1
                        stats["errors"].append({
                            "code": symbol,
                            "error": f"Sync failed: {str(e)}",
                            "context": "sync_realtime_quotes_single"
                        })

                logger.info(f"📈 Market synchronization progress: 1/1 (success: {stats['success_count']}, Error: {stats['error_count']})")
            else:
                # 2. Batch synchronization: check data freshness first, and only synchronize stocks that need to be updated
                logger.info("🔍 Check data freshness (within 15 minutes)...")
                
                # Check which stocks need to be synchronized (data older than 15 minutes)
                symbols_to_sync = []
                fresh_quotes_map = {}  # Store data within 15 minutes
                
                for symbol in symbols:
                    try:
                        # Query the latest data in the database
                        existing = await self.db.market_quotes.find_one(
                            {"code": symbol},
                            {"updated_at": 1, "code": 1, "symbol": 1, "price": 1, "close": 1, 
                             "change_percent": 1, "volume": 1, "amount": 1, "open": 1, "high": 1, 
                             "low": 1, "pre_close": 1, "trade_date": 1}
                        )
                        
                        # 🔥 Check that the data is fresh and complete
                        is_fresh = existing and self._is_data_fresh(existing.get("updated_at"), minutes=15)
                        is_complete = existing and self._is_data_complete(existing)
                        
                        if is_fresh and is_complete:
                            # The data is within 15 minutes and complete, and the data in the database is used directly.
                            fresh_quotes_map[symbol] = existing
                            stats["success_count"] += 1
                            logger.debug(f"✅ {symbol} Data is fresh and complete (within 15 minutes), synchronization is skipped")
                        elif is_fresh and not is_complete:
                            # Data is fresh but incomplete and needs to be synchronized
                            logger.warning(f"⚠️ {symbol} Data is fresh but incomplete and needs to be synchronized")
                            symbols_to_sync.append(symbol)
                        else:
                            # The data is older than 15 minutes or does not exist and needs to be synchronized.
                            symbols_to_sync.append(symbol)
                    except Exception as e:
                        logger.debug(f"⚠️ Check {symbol} Data freshness failed: {e}, Synchronization will take place")
                        symbols_to_sync.append(symbol)
                
                fresh_count = len(fresh_quotes_map)
                sync_count = len(symbols_to_sync)
                logger.info(f"📊 Data check completed: {fresh_count} Only stock data is fresh (skipping synchronization),{sync_count} Only stocks need to be synchronized")
                
                # 3. Only synchronize stocks that need to be updated
                if symbols_to_sync:
                    logger.info(f"📡 get {sync_count} Real-time market snapshot of a single stock...")
                    quotes_map = await self.provider.get_batch_stock_quotes(symbols_to_sync)

                    if not quotes_map:
                        logger.warning("⚠️ Failed to obtain a market-wide snapshot and fell back to acquisition mode one by one.")
                        # Fall back to one-by-one acquisition mode
                        for i in range(0, len(symbols_to_sync), self.batch_size):
                            batch = symbols_to_sync[i:i + self.batch_size]
                            batch_stats = await self._process_quotes_batch_fallback(batch)

                            # Update statistics
                            stats["success_count"] += batch_stats["success_count"]
                            stats["error_count"] += batch_stats["error_count"]
                            stats["errors"].extend(batch_stats["errors"])

                            # progress log
                            progress = min(i + self.batch_size, len(symbols_to_sync))
                            logger.info(f"📈 Market synchronization progress: {progress}/{len(symbols_to_sync)} "
                                       f"(success: {stats['success_count']}, Error: {stats['error_count']})")

                            # API Current limiting
                            if i + self.batch_size < len(symbols_to_sync):
                                await asyncio.sleep(self.rate_limit_delay)
                    else:
                        # 4. Use the obtained market data to save it to the database in batches
                        logger.info(f"✅ Get {len(quotes_map)} Start saving the market data of only stocks....")

                        for i in range(0, len(symbols_to_sync), self.batch_size):
                            batch = symbols_to_sync[i:i + self.batch_size]

                            # Extract the current batch of data from the whole market data and save it
                            for symbol in batch:
                                try:
                                    quotes = quotes_map.get(symbol)
                                    if quotes:
                                        # Convert to dictionary format
                                        if hasattr(quotes, 'model_dump'):
                                            quotes_data = quotes.model_dump()
                                        elif hasattr(quotes, 'dict'):
                                            quotes_data = quotes.dict()
                                        else:
                                            quotes_data = quotes

                                        # Make sure the symbol and code fields exist
                                        if "symbol" not in quotes_data:
                                            quotes_data["symbol"] = symbol
                                        if "code" not in quotes_data:
                                            quotes_data["code"] = symbol

                                        # Update to database
                                        await self.db.market_quotes.update_one(
                                            {"code": symbol},
                                            {"$set": quotes_data},
                                            upsert=True
                                        )
                                        stats["success_count"] += 1
                                    else:
                                        stats["error_count"] += 1
                                        stats["errors"].append({
                                            "code": symbol,
                                            "error": "No market data found",
                                            "context": "sync_realtime_quotes"
                                        })
                                except Exception as e:
                                    stats["error_count"] += 1
                                    stats["errors"].append({
                                        "code": symbol,
                                        "error": str(e),
                                        "context": "sync_realtime_quotes"
                                    })

                            # progress log
                            progress = min(i + self.batch_size, len(symbols_to_sync))
                            logger.info(f"📈 Quotation saving progress: {progress}/{len(symbols_to_sync)} "
                                       f"(success: {stats['success_count']}, Error: {stats['error_count']})")
                else:
                    logger.info("✅ All stock data is within 15 minutes, no synchronization required")

            # 4. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"🎉 Real-time market conditions are synchronized!")
            logger.info(f"📊 total: {stats['total_processed']}only, "
                       f"success: {stats['success_count']}, "
                       f"Error: {stats['error_count']}, "
                       f"Time consuming: {stats['duration']:.2f}seconds")

            # 🔥 Update task status to Completed
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")

            return stats

        except Exception as e:
            logger.error(f"❌ Real-time market synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_realtime_quotes"})
            
            # 🔥 Update task status is failed
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats
    
    async def _process_quotes_batch(self, batch: List[str]) -> Dict[str, Any]:
        """Processing market batches - Optimized version: Get a snapshot of the entire market at once"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "errors": []
        }

        try:
            # Get a snapshot of the entire market at once (avoid frequent interface calls)
            logger.debug(f"📊 Get a market-wide snapshot to work with {len(batch)} only stocks...")
            quotes_map = await self.provider.get_batch_stock_quotes(batch)

            if not quotes_map:
                logger.warning("⚠️ Failed to obtain market-wide snapshot, fell back to obtaining one by one")
                # Return to the original one-by-one acquisition method
                return await self._process_quotes_batch_fallback(batch)

            # Batch save to database
            for symbol in batch:
                try:
                    quotes = quotes_map.get(symbol)
                    if quotes:
                        # Convert to dictionary format
                        if hasattr(quotes, 'model_dump'):
                            quotes_data = quotes.model_dump()
                        elif hasattr(quotes, 'dict'):
                            quotes_data = quotes.dict()
                        else:
                            quotes_data = quotes

                        # Make sure the symbol and code fields exist
                        if "symbol" not in quotes_data:
                            quotes_data["symbol"] = symbol
                        if "code" not in quotes_data:
                            quotes_data["code"] = symbol

                        # Update to database
                        await self.db.market_quotes.update_one(
                            {"code": symbol},
                            {"$set": quotes_data},
                            upsert=True
                        )
                        batch_stats["success_count"] += 1
                    else:
                        batch_stats["error_count"] += 1
                        batch_stats["errors"].append({
                            "code": symbol,
                            "error": "No market data found",
                            "context": "_process_quotes_batch"
                        })
                except Exception as e:
                    batch_stats["error_count"] += 1
                    batch_stats["errors"].append({
                        "code": symbol,
                        "error": str(e),
                        "context": "_process_quotes_batch"
                    })

            return batch_stats

        except Exception as e:
            logger.error(f"❌ Batch processing of quotes failed: {e}")
            # Return to the original one-by-one acquisition method
            return await self._process_quotes_batch_fallback(batch)

    async def _process_quotes_batch_fallback(self, batch: List[str]) -> Dict[str, Any]:
        """Processing quotation batches - fallback plan: obtain one by one"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "errors": []
        }

        # Get market data one by one (add delay to avoid frequency limit)
        for symbol in batch:
            try:
                success = await self._get_and_save_quotes(symbol)
                if success:
                    batch_stats["success_count"] += 1
                else:
                    batch_stats["error_count"] += 1
                    batch_stats["errors"].append({
                        "code": symbol,
                        "error": "Failed to obtain market data",
                        "context": "_process_quotes_batch_fallback"
                    })

                # Add delay to avoid frequency throttling
                await asyncio.sleep(0.1)

            except Exception as e:
                batch_stats["error_count"] += 1
                batch_stats["errors"].append({
                    "code": symbol,
                    "error": str(e),
                    "context": "_process_quotes_batch_fallback"
                })

        return batch_stats
    
    async def _get_all_listed_symbols(self) -> List[str]:
        """Get a list of ticker symbols for all listing statuses"""
        try:
            basic_info_cursor = self.db.stock_basic_info.find(
                {"list_status": "L"},  # Get only listed stocks
                {"code": 1}
            )
            symbols = [doc["code"] async for doc in basic_info_cursor]
            return symbols
        except Exception as e:
            logger.error(f"❌ Failed to get stock list: {e}")
            return []
    
    async def _batch_update_quotes_to_db(self, quotes_map: Dict[str, Dict[str, Any]]) -> int:
        """
        Batch update market data to database
        
        Args:
            quotes_map: Mapping dictionary from stock code to market data
            
        Returns:
            The number of stocks successfully updated
        """
        updated_count = 0
        batch_size = 100  # 100 stocks per batch
        
        try:
            symbols_list = list(quotes_map.keys())
            
            for i in range(0, len(symbols_list), batch_size):
                batch = symbols_list[i:i + batch_size]
                operations = []
                
                for symbol in batch:
                    quotes = quotes_map.get(symbol)
                    if quotes:
                        # Convert to dictionary format
                        if hasattr(quotes, 'model_dump'):
                            quotes_data = quotes.model_dump()
                        elif hasattr(quotes, 'dict'):
                            quotes_data = quotes.dict()
                        else:
                            quotes_data = quotes
                        
                        # Make sure the symbol and code fields exist
                        if "symbol" not in quotes_data:
                            quotes_data["symbol"] = symbol
                        if "code" not in quotes_data:
                            quotes_data["code"] = symbol
                        
                        # Build a batch update operation
                        operations.append(
                            pymongo.UpdateOne(
                                {"code": symbol},
                                {"$set": quotes_data},
                                upsert=True
                            )
                        )
                
                if operations:
                    # Perform update operations in batches
                    result = await self.db.market_quotes.bulk_write(operations, ordered=False)
                    updated_count += result.modified_count + result.upserted_count
                    logger.debug(f"📊 Batch update progress: {min(i + batch_size, len(symbols_list))}/{len(symbols_list)} (updated: {updated_count})")
            
            return updated_count
        except Exception as e:
            logger.error(f"❌ Failed to update market data in batches: {e}", exc_info=True)
            return updated_count
    
    async def _get_and_save_quotes(self, symbol: str) -> bool:
        """Get and save individual stock quotes"""
        try:
            # 🔥 Check data freshness and completeness first
            existing = await self.db.market_quotes.find_one(
                {"code": symbol}
            )
            
            # 🔥 Check that the data is fresh and complete
            is_fresh = existing and self._is_data_fresh(existing.get("updated_at"), minutes=15)
            is_complete = existing and self._is_data_complete(existing)
            
            if is_fresh and is_complete:
                logger.debug(f"✅ {symbol} Data is fresh and complete (within 15 minutes), synchronization is skipped")
                return True
            elif is_fresh and not is_complete:
                logger.warning(f"⚠️ {symbol} Data is fresh but incomplete, forced synchronization")
                # Data is incomplete, continue synchronization
            
            # If the data is older than 15 minutes or does not exist, synchronize it.
            quotes = await self.provider.get_stock_quotes(symbol)
            if quotes:
                # Convert to dictionary format
                if hasattr(quotes, 'model_dump'):
                    quotes_data = quotes.model_dump()
                elif hasattr(quotes, 'dict'):
                    quotes_data = quotes.dict()
                else:
                    quotes_data = quotes

                # 🔥 Check whether it is obtained through the batch interface, if so, update the whole market data in batches
                batch_data = quotes_data.pop('_batch_data', None)
                from_batch = quotes_data.pop('_from_batch', False)
                
                if from_batch and batch_data:
                    # 🔥 Obtained through the batch interface, batch update of all market data to the database
                    logger.info(f"📊 Batch interface data is detected and batch update starts. {len(batch_data)} Only stock quotes are sent to the database...")
                    updated_count = await self._batch_update_quotes_to_db(batch_data)
                    logger.info(f"✅ Batch update completed, total updates {updated_count} Only stock data")
                else:
                    # Single stock data, saved separately
                    # Make sure the symbol field exists
                    if "symbol" not in quotes_data:
                        quotes_data["symbol"] = symbol

                    # 🔥 Print the data about to be saved to the database
                    logger.info(f"💾 ready to save {symbol} Quotes to database:")
                    logger.info(f"   - latest price(price): {quotes_data.get('price')}")
                    logger.info(f"   - highest price(high): {quotes_data.get('high')}")
                    logger.info(f"   - lowest price(low): {quotes_data.get('low')}")
                    logger.info(f"   - opening price(open): {quotes_data.get('open')}")
                    logger.info(f"   - Yesterday s closing price(pre_close): {quotes_data.get('pre_close')}")
                    logger.info(f"   - Volume(volume): {quotes_data.get('volume')}")
                    logger.info(f"   - Turnover(amount): {quotes_data.get('amount')}")
                    logger.info(f"   - Increase or decrease(change_percent): {quotes_data.get('change_percent')}%")

                    # Update to database
                    result = await self.db.market_quotes.update_one(
                        {"code": symbol},
                        {"$set": quotes_data},
                        upsert=True
                    )

                    logger.info(f"✅ {symbol} Quotes have been saved to the database (matched={result.matched_count}, modified={result.modified_count}, upserted_id={result.upserted_id})")
                
                return True
            return False
        except Exception as e:
            logger.error(f"❌ get {symbol} Quote failed: {e}", exc_info=True)
            return False

    async def sync_historical_data(
        self,
        start_date: str = None,
        end_date: str = None,
        symbols: List[str] = None,
        incremental: bool = True,
        period: str = "daily",
        resume_from_index: int = None,  # 🔥 Resume execution: where to continue from
        manual_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Synchronize historical data

        Args:
            start_date: start date
            end_date: end date
            symbols: Specify stock code list
            incremental: Whether to incrementally synchronize
            period: data period (daily/weekly/monthly)
            manual_mode: Whether it is a manual API call; manual mode does not read or write back the scheduled task status

        Returns:
            Synchronization result statistics
        """
        period_name = {"daily": "daily line", "weekly": "perimeter", "monthly": "monthly line"}.get(period, "daily line")
        logger.info(f"🔄 Start syncing{period_name}historical data...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "total_records": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": []
        }
        job_id = self._resolve_job_id(manual_mode)

        try:
            # 🔥 When executing in a thread in the thread pool, the database connection needs to be reinitialized.
            # Because the database connection (Motor) is bound to the event loop, and the thread pool thread has an independent event loop
            self.db = bind_loop_safe_mongo_db(self)
            
            # 1. Determine global end date
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

            # 2. Determine the stock list to sync
            if symbols is None:
                # 🔥 Use aggregate queries to deduplicate, ensuring each stock symbol is only counted once
                # Because the same stock may come from multiple data sources (tushare, akshare, baostock), there will be duplicate records
                pipeline = [
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
                    logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Only unique stocks (duplication removed)")
                except (RuntimeError, Exception) as loop_error:
                    # 🔥 If an event loop conflict error or other database connection error occurs, re-create the database connection
                    error_str = str(loop_error).lower()
                    if "attached to a different loop" in error_str or "different loop" in error_str or "loop" in error_str:
                        logger.warning(f"⚠️ [AKShare] Event loop conflict or database connection error detected, rebind database agent: {loop_error}")
                        try:
                            self.db = bind_loop_safe_mongo_db(self)
                            # Retry query
                            cursor = self.db.stock_basic_info.aggregate(pipeline)
                            symbols = [doc["code"] async for doc in cursor]
                            logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} Unique stocks only (deduplicated, connections re-created)")
                        except Exception as retry_error:
                            logger.error(f"❌ [AKShare] Database connection still fails after re-creating it: {retry_error}")
                            raise RuntimeError(f"Database connection failed, unable to obtain stock list: {retry_error}")
                    else:
                        # Other types of errors are thrown directly
                        logger.error(f"❌ [AKShare] Failed to get stock list: {loop_error}")
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
                    f"⏭️ [AKShare] Stock history synchronization has detected the ETF code and has switched to skip processing. Please use the ETF dedicated synchronization link.: "
                    f"count={len(skipped_etf_symbols)}, symbols={preview}"
                )
                stats["skipped_etf_count"] = len(skipped_etf_symbols)
                stats["skipped_etf_symbols"] = skipped_etf_symbols

            if not symbols:
                if skipped_etf_symbols:
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

                logger.warning("⚠️ No stocks found to sync")
                return stats

            # 🔥 Save the original stock total (used for progress calculations)
            original_total_symbols = len(symbols)
            
            # 🔥 If a restore location is specified, skip processed stocks
            start_index = resume_from_index if resume_from_index is not None and resume_from_index > 0 else 0
            if start_index > 0:
                logger.info(f"🔄 Resume execution: from section {start_index} stocks start (processed {start_index}/{original_total_symbols}) ")
                # Skip processed stocks
                symbols = symbols[start_index:]
                if not symbols:
                    logger.warning(f"⚠️ All stocks have been processed, no need to continue synchronization")
                    stats["total_processed"] = original_total_symbols
                    stats["success_count"] = start_index
                    return stats

            stats["total_processed"] = original_total_symbols

            # 3. Determine global start date (for log display only)
            global_start_date = start_date
            if not global_start_date:
                if incremental:
                    global_start_date = "Last date of each stock"
                else:
                    global_start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

            logger.info(f"📊 Historical data synchronization: end date={end_date}, Number of shares={len(symbols)} (total{original_total_symbols}), mode={'Increment' if incremental else 'full amount'}, starting position={start_index}")

            # 4. Batch processing
            processed_count = start_index  # 🔥 Count from recovery position
            was_cancelled = False  # 🔥 Whether marking is stopped due to cancellation
            
            for i in range(0, len(symbols), self.batch_size):
                # 🔥 Check if the task should be stopped
                if job_id and await self._should_stop(job_id):
                    logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting...")
                    stats["stopped"] = True
                    was_cancelled = True
                    break

                # 🔥 Checks whether the current thread's event loop has been closed (checked only in thread pool tasks)
                # Note: Do not check the global provider in the thread pool task is_event_loop_closed(), 
                # Because thread pool tasks have their own event loop, they should not rely on the state of the main event loop.
                try:
                    current_loop = asyncio.get_running_loop()
                    if current_loop.is_closed():
                        logger.warning(f"⚠️ [AKShare] The event loop of the current thread has been closed, stopping the synchronization task")
                        stats["stopped"] = True
                        stats["errors"].append({"error": "Event loop is closed", "context": "sync_historical_data"})
                        break
                except RuntimeError:
                    # There is no event loop running, which shouldn't happen, but execution continues
                    logger.debug("⚠️ [AKShare] Unable to obtain current event loop, continue execution")

                batch = symbols[i:i + self.batch_size]
                # 🔥 Pass processed_count and original_total_symbols so that the batch processing function can update the progress in real time
                batch_stats = await self._process_historical_batch(
                    batch, start_date, end_date, period, incremental, job_id,
                    processed_count=processed_count,  # 🔥 Pass the current processed quantity
                    original_total_symbols=original_total_symbols  # 🔥 total quantity delivered
                )

                # Update statistics
                stats["success_count"] += batch_stats["success_count"]
                stats["error_count"] += batch_stats["error_count"]
                stats["total_records"] += batch_stats["total_records"]
                stats["errors"].extend(batch_stats["errors"])
                
                # 🔥 Update the processed quantity (the batch processing function returns the actual number of stocks processed)
                processed_count = batch_stats.get("processed_count", processed_count + len(batch))

                # progress log
                progress_percent = int((processed_count / original_total_symbols) * 100) if original_total_symbols > 0 else 0
                logger.info(f"📈 Historical data synchronization progress: {processed_count}/{original_total_symbols} ({progress_percent}%) "
                           f"(success: {stats['success_count']}, record: {stats['total_records']})")

                # API Current limiting
                if i + self.batch_size < len(symbols):
                    await asyncio.sleep(self.rate_limit_delay)

            # 4. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

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
                                    "message": f"Task canceled (processed {processed_count}/{original_total_symbols}) ",
                                    "progress": int((processed_count / original_total_symbols) * 100) if original_total_symbols > 0 else 0,
                                    "processed_items": processed_count,
                                    "total_items": original_total_symbols
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
                                        "message": f"Task canceled (processed {processed_count}/{original_total_symbols}) ",
                                        "progress": int((processed_count / original_total_symbols) * 100) if original_total_symbols > 0 else 0,
                                        "processed_items": processed_count,
                                        "total_items": original_total_symbols
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
                        progress_percent = int((processed_count / original_total_symbols) * 100) if original_total_symbols > 0 else 0
                        progress_data.update({
                            "status": "cancelled",
                            "progress": progress_percent,
                            "message": f"Task canceled (processed {processed_count}/{original_total_symbols}) ",
                            "processed_items": processed_count,
                            "total_items": original_total_symbols,
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

            logger.info(f"🎉 Historical data synchronization completed!")
            logger.info(f"📊 total: {stats['total_processed']}only stocks, "
                       f"success: {stats['success_count']}, "
                       f"record: {stats['total_records']}Article, "
                       f"Time consuming: {stats['duration']:.2f}seconds")

            # 🔥 Update the task status to completed (determine success/failure/partial success based on actual completion status)
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    # 🔥 If there is an error, pass the error message to mark_job_completed
                    # In this way, the task status (successful/partially successful/failed) can be correctly judged based on the error situation.
                    error_message = None
                    if stats.get("error_count", 0) > 0:
                        # Extract main error information (network error, connection interruption, etc.)
                        error_messages = []
                        for error in stats.get("errors", [])[:5]:  # Only take the first 5 errors
                            error_str = error.get("error", "") if isinstance(error, dict) else str(error)
                            if error_str:
                                error_messages.append(error_str)
                        
                        if error_messages:
                            # If all stocks failed, mark as failed; otherwise mark as partial success
                            if stats.get("success_count", 0) == 0:
                                error_message = f"Sync failed:{len(error_messages)} an error. Major error: {', '.join(error_messages[:3])}"
                            else:
                                # Partial success, do not pass error_message, let mark_job_completed judge based on success rate
                                error_message = None
                    
                    await mark_job_completed(job_id, stats, error_message)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")

            return stats

        except Exception as e:
            # 🔥 Check whether it is a task cancellation exception
            from app.services.scheduler_service import TaskCancelledException
            if isinstance(e, TaskCancelledException) or "Cancel" in str(e) or "cancelled" in str(e).lower():
                logger.warning(f"🛑 The historical data synchronization task has been cancelled.: {e}")
                was_cancelled = True
                stats["stopped"] = True
                
                # Update status is canceled
                if job_id:
                    try:
                        from app.core.database import get_mongo_db_sync, get_redis_sync_client
                        from app.core.redis_client import RedisKeys
                        
                        # Update MongoDB status
                        db = get_mongo_db_sync()
                        # 🔥 Get current progress information (if present) - using sync client
                        from pymongo import DESCENDING
                        current_execution = db.scheduler_executions.find_one(
                            {"job_id": job_id, "status": "running"},
                            sort=[("timestamp", DESCENDING)]
                        )
                        processed_count = current_execution.get("processed_items", 0) if current_execution else 0
                        total_items = current_execution.get("total_items", 0) if current_execution else 0
                        
                        # 🔥 Use the found record _id to update to avoid sort parameter errors
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
                            progress_percent = int((processed_count / total_items) * 100) if total_items > 0 else 0
                            progress_data.update({
                                "status": "cancelled",
                                "progress": progress_percent,
                                "message": f"Task canceled: {str(e)}",
                                "processed_items": processed_count,
                                "total_items": total_items,
                                "updated_at": datetime.utcnow().isoformat()
                            })
                            
                            # 🔥 save to Redis
                            redis_client.setex(
                                redis_key,
                                3600,  # 1 hours TTL
                                json.dumps(progress_data, ensure_ascii=False, default=str)
                            )
                            logger.info(f"✅ The Redis cache has been updated and the task status is cancelled: job_id={job_id}, progress={progress_percent}%")
                    except Exception as cancel_error:
                        logger.error(f"❌ Failed to update task cancellation status: {cancel_error}")
                
                return stats
            
            logger.error(f"❌ Historical data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_historical_data"})
            
            # 🔥 Update task status is failed
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats

    async def _process_historical_batch(
        self,
        batch: List[str],
        start_date: str,
        end_date: str,
        period: str = "daily",
        incremental: bool = False,
        job_id: str = None,
        processed_count: int = 0,  # 🔥 Quantity currently processed
        original_total_symbols: int = 0  # 🔥 Total number of shares
    ) -> Dict[str, Any]:
        """Process historical data batches"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "total_records": 0,
            "errors": [],
            "processed_count": processed_count  # 🔥 Save the current processed quantity
        }

        for symbol in batch:
            # 🔥 Check if the task should be stopped
            if job_id and await self._should_stop(job_id):
                logger.warning(f"⚠️ Task {job_id} Stop signal received, exiting batch processing...")
                batch_stats["stopped"] = True
                break
            
            # 🔥 Each time a stock is processed, the processed quantity is immediately updated (regardless of success or failure)
            processed_count += 1
            batch_stats["processed_count"] = processed_count
            
            try:
                # Determine the start date of the stock
                symbol_start_date = start_date
                if not symbol_start_date:
                    if incremental:
                        # Incremental synchronization: Get the last date of the stock
                        symbol_start_date = await self._get_last_sync_date(symbol)
                        logger.debug(f"📅 {symbol}: from {symbol_start_date} Start syncing")
                    else:
                        # Full synchronization: last year
                        symbol_start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

                # Get historical data
                hist_data = await self.provider.get_historical_data(symbol, symbol_start_date, end_date, period)

                if hist_data is not None and not hist_data.empty:
                    # Save to unified historical data collection
                    # 🔥 Ensure historical_service is initialized (if None, created with current db connection)
                    if self.historical_service is None:
                        from app.services.historical_data_service import HistoricalDataService
                        self.historical_service = HistoricalDataService()
                        self.historical_service.db = self.db
                        self.historical_service.collection = self.db.stock_daily_quotes
                        await self.historical_service._ensure_indexes()

                    saved_count = await self.historical_service.save_historical_data(
                        symbol=symbol,
                        data=hist_data,
                        data_source="akshare",
                        market="CN",
                        period=period
                    )

                    batch_stats["success_count"] += 1
                    batch_stats["total_records"] += saved_count
                    logger.debug(f"✅ {symbol}Historical data synchronization successful: {saved_count}records")
                else:
                    batch_stats["error_count"] += 1
                    batch_stats["errors"].append({
                        "code": symbol,
                        "error": "Historical data is empty",
                        "context": "_process_historical_batch"
                    })

            except Exception as e:
                batch_stats["error_count"] += 1
                batch_stats["errors"].append({
                    "code": symbol,
                    "error": str(e),
                    "context": "_process_historical_batch"
                })
            
            # 🔥 Every time a stock is processed (regardless of success or failure), the progress is updated immediately
            if job_id and original_total_symbols > 0:
                try:
                    from app.services.scheduler_service import update_job_progress
                    
                    # 🔥 Calculate progress percentage
                    progress_percent = int((processed_count / original_total_symbols) * 100) if original_total_symbols > 0 else 0
                    
                    # 🔥 Build progress messages
                    progress_message = f"Synchronizing historical data ({processed_count}/{original_total_symbols})"
                    
                    # 🔥 If there is an error, include error information in the message
                    if batch_stats.get("error_count", 0) > 0:
                        recent_errors = batch_stats.get("errors", [])[-3:]  # Only take the last 3 errors
                        if recent_errors:
                            error_summary = []
                            for error in recent_errors:
                                error_str = error.get("error", "") if isinstance(error, dict) else str(error)
                                if error_str:
                                    # Extract key error information (network connection interruption, connection error, etc.)
                                    if "Network connection interrupted" in error_str or "Connection" in error_str or "connect" in error_str or "RemoteDisconnected" in error_str:
                                        error_summary.append("Network connection issues")
                                    elif "network error" in error_str:
                                        error_summary.append("network error")
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
                        total_items=original_total_symbols,
                        processed_items=processed_count
                    )
                except Exception as progress_error:
                    # 🔥 Failure in progress update should not affect task execution
                    logger.debug(f"⚠️ Update progress failed (execution continues): {progress_error}")

        return batch_stats

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
                latest_date = await self.historical_service.get_latest_date(symbol, "akshare")
                if latest_date:
                    # Returns the day after the last date (to avoid repeated synchronization)
                    try:
                        last_date_obj = datetime.strptime(latest_date, '%Y-%m-%d')
                        next_date = last_date_obj + timedelta(days=1)
                        return next_date.strftime('%Y-%m-%d')
                    except ValueError:
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

                    # If there is no launch date, only the data of the last 10 years will be synchronized (to avoid timeout caused by excessive data volume)
                    ten_years_ago = (datetime.now() - timedelta(days=3650)).strftime('%Y-%m-%d')
                    logger.warning(f"⚠️ {symbol}: No listing date found, from {ten_years_ago} Start synchronization (last 10 years)")
                    return ten_years_ago

            # Returns to 30 days ago by default (to ensure no data leakage)
            return (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        except Exception as e:
            logger.error(f"❌ Failed to get last sync date {symbol}: {e}")
            # When an error occurs, return to 30 days ago to ensure no data is leaked.
            return (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    async def sync_financial_data(self, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Sync financial data

        Args:
            symbols: Specify stock code list

        Returns:
            Synchronization result statistics
        """
        logger.info("🔄 Start syncing financial data...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": []
        }

        try:
            # 1. Determine the stock list to sync
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
                logger.info(f"📋 Obtained from stock_basic_info {len(symbols)} only stocks")

            if not symbols:
                logger.warning("⚠️ No stocks found to sync")
                return stats

            stats["total_processed"] = len(symbols)
            logger.info(f"📊 Prepare to sync {len(symbols)} Financial data for only stocks")

            # 2. Batch processing
            for i in range(0, len(symbols), self.batch_size):
                batch = symbols[i:i + self.batch_size]
                batch_stats = await self._process_financial_batch(batch)

                # Update statistics
                stats["success_count"] += batch_stats["success_count"]
                stats["error_count"] += batch_stats["error_count"]
                stats["errors"].extend(batch_stats["errors"])

                # progress log
                progress = min(i + self.batch_size, len(symbols))
                logger.info(f"📈 Financial data synchronization progress: {progress}/{len(symbols)} "
                           f"(success: {stats['success_count']}, Error: {stats['error_count']})")

                # API Current limiting
                if i + self.batch_size < len(symbols):
                    await asyncio.sleep(self.rate_limit_delay)

            # 3. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"🎉 Financial data synchronization completed!")
            logger.info(f"📊 total: {stats['total_processed']}only stocks, "
                       f"success: {stats['success_count']}, "
                       f"Error: {stats['error_count']}, "
                       f"Time consuming: {stats['duration']:.2f}seconds")

            # 🔥 Update task status to Completed
            job_id = getattr(self, '_current_job_id', None) or "akshare_financial_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")

            return stats

        except Exception as e:
            logger.error(f"❌ Financial data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_financial_data"})
            
            # 🔥 Update task status is failed
            job_id = getattr(self, '_current_job_id', None) or "akshare_financial_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats

    async def _process_financial_batch(self, batch: List[str]) -> Dict[str, Any]:
        """Process batches of financial data"""
        batch_stats = {
            "success_count": 0,
            "error_count": 0,
            "errors": []
        }

        for symbol in batch:
            try:
                # Get financial data
                financial_data = await self.provider.get_financial_data(symbol)

                if financial_data:
                    # Save data using a unified financial data service
                    success = await self._save_financial_data(symbol, financial_data)
                    if success:
                        batch_stats["success_count"] += 1
                        logger.debug(f"✅ {symbol}Financial data saved successfully")
                    else:
                        batch_stats["error_count"] += 1
                        batch_stats["errors"].append({
                            "code": symbol,
                            "error": "Financial data saving failed",
                            "context": "_process_financial_batch"
                        })
                else:
                    batch_stats["error_count"] += 1
                    batch_stats["errors"].append({
                        "code": symbol,
                        "error": "Financial data is empty",
                        "context": "_process_financial_batch"
                    })

            except Exception as e:
                batch_stats["error_count"] += 1
                batch_stats["errors"].append({
                    "code": symbol,
                    "error": str(e),
                    "context": "_process_financial_batch"
                })

        return batch_stats

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
                data_source="akshare",
                market="CN",
                report_type="quarterly"
            )

            return saved_count > 0

        except Exception as e:
            logger.error(f"❌ save {symbol} Financial data failed: {e}")
            return False

    async def run_status_check(self) -> Dict[str, Any]:
        """Running status check"""
        try:
            logger.info("🔍 Start AKShare status check...")

            # 🔥 Critical fix: reacquire database connection on every use, ensure correct event loop is used
            # 🔥 This can avoid event loop conflicts when executing in scheduled tasks
            db = get_mongo_db()

            # Check provider connection
            provider_connected = await self.provider.test_connection()

            # Check database collection status
            collections_status = {}

            # Check basic information collection
            basic_count = await db.stock_basic_info.count_documents({})
            latest_basic = await db.stock_basic_info.find_one(
                {}, sort=[("updated_at", -1)]
            )
            collections_status["stock_basic_info"] = {
                "count": basic_count,
                "latest_update": latest_basic.get("updated_at") if latest_basic else None
            }

            # Check the market data collection
            quotes_count = await db.market_quotes.count_documents({})
            latest_quotes = await db.market_quotes.find_one(
                {}, sort=[("updated_at", -1)]
            )
            collections_status["market_quotes"] = {
                "count": quotes_count,
                "latest_update": latest_quotes.get("updated_at") if latest_quotes else None
            }

            status_result = {
                "provider_connected": provider_connected,
                "collections": collections_status,
                "status_time": datetime.utcnow()
            }

            logger.info(f"✅ AKShare Status check completed: {status_result}")
            return status_result

        except Exception as e:
            logger.error(f"❌ AKShare Status check failed: {e}", exc_info=True)
            return {
                "provider_connected": False,
                "error": str(e),
                "status_time": datetime.utcnow()
            }

    # ==================== News data synchronization ====================

    async def _get_favorite_stocks(self) -> List[str]:
        """
        Get the stock watch list list of valid users (remove duplicates)

        Stock watch lists are currently stored uniformly in the user_favorites collection.
        Only valid users that still exist in the users collection are aggregated here to avoid leaving history behind.
        Or the data of the wrong account is brought into the news synchronization task.

        Returns:
            Stock Watch List Symbol List
        """
        try:
            valid_user_ids = set()
            users_cursor = self.db.users.find({}, {"_id": 1})

            async for user in users_cursor:
                user_id = user.get("_id")
                if user_id is not None:
                    valid_user_ids.add(str(user_id))

            favorite_codes = set()
            skipped_count = 0

            favorites_cursor = self.db.user_favorites.find(
                {"favorites": {"$exists": True, "$ne": []}},
                {"user_id": 1, "favorites.stock_code": 1, "_id": 0}
            )

            async for doc in favorites_cursor:
                user_id = str(doc.get("user_id") or "")
                if not user_id or user_id not in valid_user_ids:
                    skipped_count += 1
                    logger.warning(
                        "⚠️ News sync skips invalid user stock watchlist document: %s",
                        user_id or "unknown",
                    )
                    continue

                for fav in doc.get("favorites", []):
                    code = str(fav.get("stock_code") or "").strip()
                    if code:
                        favorite_codes.add(code)

            if skipped_count:
                logger.info("🗑️ News sync has skipped %s invalid user stock watchlist documents", skipped_count)

            result = sorted(list(favorite_codes))
            logger.info("📌 Aggregated from %s valid users to %s stock watchlist", len(valid_user_ids), len(result))
            return result

        except Exception as e:
            logger.error(f"❌ Failed to get stock watchlist list: {e}")
            return []

    async def sync_news_data(
        self,
        symbols: List[str] = None,
        max_news_per_stock: int = 20,
        force_update: bool = False,
        favorites_only: bool = True
    ) -> Dict[str, Any]:
        """
        Synchronize news data

        Args:
            symbols: Stock code list, when it is None, the synchronization range is determined based on favorites_only
            max_news_per_stock: Maximum number of news per stock
            force_update: Whether to force update
            favorites_only: Whether to synchronize only stock watchlists (default True)

        Returns:
            Synchronization result statistics
        """
        logger.info("🔄 Start synchronizing AKShare news data...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "news_count": 0,
            "start_time": datetime.utcnow(),
            "favorites_only": favorites_only,
            "errors": []
        }

        try:
            # 1. Get a list of stocks
            if symbols is None:
                if favorites_only:
                    # Sync stock watchlist only
                    symbols = await self._get_favorite_stocks()
                    logger.info(f"📌 Only sync stock watchlist, total {len(symbols)} only")
                else:
                    # Get all stocks (without limiting the data source)
                    # 🔥 Use aggregate queries to deduplicate, ensuring each stock symbol is only counted once
                    pipeline = [
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
                    logger.info(f"📊 Sync all stocks, total {len(symbols)} Only unique stocks (duplication removed)")

            if not symbols:
                logger.warning("⚠️ No stocks found that require synchronized news")
                return stats

            stats["total_processed"] = len(symbols)
            logger.info(f"📊 Need to synchronize {len(symbols)} Stock news")

            # 2. Batch processing
            for i in range(0, len(symbols), self.batch_size):
                batch = symbols[i:i + self.batch_size]
                batch_stats = await self._process_news_batch(
                    batch, max_news_per_stock
                )

                # Update statistics
                stats["success_count"] += batch_stats["success_count"]
                stats["error_count"] += batch_stats["error_count"]
                stats["news_count"] += batch_stats["news_count"]
                stats["errors"].extend(batch_stats["errors"])

                # Progress log and updates
                progress = min(i + self.batch_size, len(symbols))
                progress_percent = int((progress / len(symbols)) * 100) if len(symbols) > 0 else 0
                logger.info(f"📈 News synchronization progress: {progress}/{len(symbols)} ({progress_percent}%) "
                           f"(success: {stats['success_count']}, News: {stats['news_count']})")
                
                # 🔥 Update task progress
                job_id = getattr(self, '_current_job_id', None) or "akshare_news_sync"
                if job_id:
                    try:
                        from app.services.scheduler_service import update_job_progress
                        await update_job_progress(
                            job_id=job_id,
                            progress=progress_percent,
                            message=f"Synchronizing news ({progress}/{len(symbols)})",
                            total_items=len(symbols),
                            processed_items=progress
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to update task progress: {e}")

                # API Current limiting
                if i + self.batch_size < len(symbols):
                    await asyncio.sleep(self.rate_limit_delay)

            # 3. Complete statistics
            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ AKShare News data synchronization completed: "
                       f"total {stats['total_processed']} only stocks, "
                       f"success {stats['success_count']} only, "
                       f"get {stats['news_count']} news, "
                       f"Error {stats['error_count']} only, "
                       f"Time consuming {stats['duration']:.2f} seconds")

            # 🔥 Update task status to Completed
            job_id = getattr(self, '_current_job_id', None) or "akshare_news_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update task completion status: {e}")

            return stats

        except Exception as e:
            logger.error(f"❌ AKShare News data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_news_data"})
            
            # 🔥 Update task status is failed
            job_id = getattr(self, '_current_job_id', None) or "akshare_news_sync"
            if job_id:
                try:
                    from app.services.scheduler_service import mark_job_completed
                    await mark_job_completed(job_id, stats, str(e))
                except Exception as update_error:
                    logger.warning(f"⚠️ An error occurred while updating task failure status: {update_error}")
            
            return stats

    async def _process_news_batch(
        self,
        batch: List[str],
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
                # Get news data from AKShare
                news_data = await self.provider.get_stock_news(
                    symbol=symbol,
                    limit=max_news_per_stock
                )

                if news_data:
                    # Save news data
                    saved_count = await self.news_service.save_news_data(
                        news_data=news_data,
                        data_source="akshare",
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

    async def retry_failed_symbols(
        self,
        errors: List[Dict[str, Any]],
        start_date: str = None,
        end_date: str = None,
        period: str = "daily",
        job_id: str = None,
        _is_retry: bool = False
    ) -> Dict[str, Any]:
        """
        Retry failed stocks (retry only retryable errors, skip errors with no data)
        
        Args:
            errors: Error list (obtained from previous sync results)
            start_date: start date
            end_date: end date
            period: data period (daily/weekly/monthly)
            job_id: Task ID (for progress tracking)
            _is_retry: Internal mark indicating that this is a retry task to avoid automatic retries again
            
        Returns:
            Retry result statistics
        """
        period_name = {"daily": "daily line", "weekly": "perimeter", "monthly": "monthly line"}.get(period, period)
        
        # 🔥 Filter out retryable errors (AKShare's error format is similar to Tushare)
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
        retry_symbols = [error.get("code") for error in retryable_errors if error.get("code")]
        
        logger.info(f"📋 Will retry following {len(retry_symbols)} only stocks: {', '.join(retry_symbols[:10])}{'...' if len(retry_symbols) > 10 else ''}")
        
        # Call the synchronization method to synchronize only these failed stocks
        retry_result = await self.sync_historical_data(
            symbols=retry_symbols,
            start_date=start_date,
            end_date=end_date,
            incremental=False,  # Use full sync when retrying
            period=period
        )
        
        # Merge results
        retry_result["total_retried"] = len(retry_symbols)
        retry_result["no_data_count"] = len(no_data_errors)
        retry_result["retryable_errors_count"] = len(retryable_errors)
        
        logger.info(f"✅ Retry complete: success {retry_result['success_count']}/{retry_result['total_retried']}, "
                   f"failed {retry_result['error_count']}, No data {retry_result['no_data_count']} (skipped)")
        
        return retry_result


# Global synchronization service instance
_akshare_sync_service = None

async def get_akshare_sync_service() -> AKShareSyncService:
    """Get the AKShare synchronization service instance"""
    global _akshare_sync_service
    if _akshare_sync_service is None:
        _akshare_sync_service = AKShareSyncService()
        await _akshare_sync_service.initialize()
    return _akshare_sync_service


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


async def run_akshare_basic_info_sync(force_update: bool = False, **kwargs):
    """
    APScheduler Task: Synchronize basic stock information

    🔥 Use unified thread pool service execution to avoid blocking the main event loop and ensure API response
    """
    job_id = "akshare_basic_info_sync"
    
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
        service = await get_akshare_sync_service()
        service._current_job_id = job_id
        sync_result = await unified_service.execute_sync_method(
            sync_method=service.sync_stock_basic_info,
            method_kwargs={"force_update": force_update},
            job_id=job_id,
            rate_limit_per_minute=300,
        )
        if sync_result.success:
            logger.info(f"✅ AKShare Basic information synchronization completed: {sync_result.result}")
            return sync_result.result
        elif sync_result.error and ("Cancel" in sync_result.error or "cancelled" in sync_result.error.lower()):
            logger.info(f"ℹ️ AKShare The basic information synchronization task has been canceled by the user")
            return {"cancelled": True, "message": sync_result.error}
        else:
            raise RuntimeError(sync_result.error or "Sync failed")
    except Exception as e:
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ AKShare The basic information synchronization task has been canceled by the user")
            return {"cancelled": True, "message": str(e)}
        logger.error(f"❌ AKShare Basic information synchronization failed: {e}")
        raise


async def run_akshare_quotes_sync(force: bool = False, **kwargs):
    """
    APScheduler Task: Synchronize real-time market conditions

    Args:
        force: Whether to enforce execution (skip transaction time check), default False

    🔥 Use unified thread pool service execution to avoid blocking the main event loop and ensure API response
    """
    # 🔥 Allow execution when manually triggered or forced (even if there is a running record)
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    job_id = "akshare_quotes_sync"
    
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
        service = await get_akshare_sync_service()
        service._current_job_id = job_id
        # Note: AKShare does not have transaction time checking logic, the force parameter is only used for interface consistency
        sync_result = await unified_service.execute_sync_method(
            sync_method=service.sync_realtime_quotes,
            method_kwargs={"force": force},
            job_id=job_id,
            rate_limit_per_minute=300,
        )
        if sync_result.success:
            logger.info(f"✅ AKShare Market synchronization completed: {sync_result.result}")
            return sync_result.result
        elif sync_result.error and ("Cancel" in sync_result.error or "cancelled" in sync_result.error.lower()):
            logger.info(f"ℹ️ AKShare The market synchronization task has been canceled by the user")
            return {"cancelled": True, "message": sync_result.error}
        else:
            raise RuntimeError(sync_result.error or "Sync failed")
    except Exception as e:
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ AKShare The market synchronization task has been canceled by the user")
            return {"cancelled": True, "message": str(e)}
        logger.error(f"❌ AKShare Market synchronization failed: {e}")
        raise


async def run_akshare_historical_sync(incremental: bool = True, **kwargs):
    """
    APScheduler Task: Synchronize historical data (using unified thread pool service)
    
    🔥 Updated to use unified thread pool synchronization service
    """
    job_id = "akshare_historical_sync"
    
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
        # 🔥 Use unified thread pool synchronization service
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
        
        unified_service = await get_unified_thread_pool_sync_service()
        
        # 🔥 Get the AK data source service instance
        service = await get_akshare_sync_service()
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
                "incremental": incremental,
                "period": kwargs.get("period", "daily"),
                "start_date": kwargs.get("start_date"),
                "end_date": kwargs.get("end_date"),
                "symbols": kwargs.get("symbols")
            },
            job_id=job_id,
            rate_limit_per_minute=kwargs.get("rate_limit_per_minute", 200),  # AKShare rate limit
            resume_from_index=resume_from_index
        )
        
        if sync_result.success:
            result = sync_result.result
            logger.info(f"✅ AKShare Historical data synchronization completed: {result}")
            return result
        else:
            # 🔥 Check if the task is canceled
            if "Cancel" in sync_result.error or "cancelled" in sync_result.error.lower():
                logger.info(f"ℹ️ AKShare The historical data synchronization task has been canceled by the user")
                return {"cancelled": True, "message": sync_result.error}
            else:
                logger.error(f"❌ AKShare Historical data synchronization failed: {sync_result.error}")
                raise RuntimeError(sync_result.error)
                
    except Exception as e:
        # Check whether it is a task cancellation exception (the user actively cancels and should not be recorded as an error)
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ AKShare The historical data synchronization task has been canceled by the user")
            return {"cancelled": True, "message": "The task has been canceled by the user"}
        # Other exceptions are recorded as errors
        logger.error(f"❌ AKShare Historical data synchronization failed: {e}")
        raise


async def run_akshare_financial_sync(**kwargs):
    """
    APScheduler Task: Synchronize financial data (using thread pool version)
    
    🔥 Updated to use unified financial data synchronization service (thread pool version)
    """
    job_id = "akshare_financial_sync"
    
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
        # 🔥 Use unified financial data synchronization service (thread pool version)
        from app.worker.financial_data_sync_service import get_financial_sync_service
        
        service = await get_financial_sync_service()
        
        # 🔥 Check whether it is a resume execution and read the resume location from kwargs
        resume_from_index = kwargs.get("_resume_from_index")
        if resume_from_index is not None:
            logger.info(f"🔄 [Resume execution] will be from {resume_from_index} Stock positions continue to be synchronized")
        
        results = await service.sync_financial_data(
            symbols=None,  # None Indicates synchronization of all stocks
            data_sources=["akshare"],  # Only synchronize AKShare data source
            report_types=["quarterly", "annual"],
            job_id=job_id,
            _resume_from_index=resume_from_index  # 🔥 Pass restore position parameters
        )
        
        # Convert to older formats to maintain compatibility
        if "akshare" in results:
            stats = results["akshare"]
            result = {
                "success": True,
                "total_symbols": stats.total_symbols,
                "success_count": stats.success_count,
                "error_count": stats.error_count,
                "duration": stats.duration
            }
        else:
            result = {"success": False, "message": "AKShare Data source synchronization failed"}
        
        logger.info(f"✅ AKShare Financial data synchronization completed (thread pool version): {result}")
        return result
    except Exception as e:
        # Check whether it is a task cancellation exception (the user actively cancels and should not be recorded as an error)
        from app.services.scheduler_service import TaskCancelledException
        if isinstance(e, TaskCancelledException):
            logger.info(f"ℹ️ AKShare The financial data synchronization task has been canceled by the user")
            return {"cancelled": True, "message": "The task has been canceled by the user"}
        # Other exceptions are recorded as errors
        logger.error(f"❌ AKShare Financial data synchronization failed: {e}", exc_info=True)
        raise


async def run_akshare_status_check():
    """APScheduler Task: status check"""
    try:
        service = await get_akshare_sync_service()
        result = await service.run_status_check()
        logger.info(f"✅ AKShare Status check completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ AKShare Status check failed: {e}")
        raise


async def run_akshare_news_sync(max_news_per_stock: int = 20, **kwargs):
    """APScheduler Task: Synchronize news data"""
    job_id = kwargs.get("job_id", "akshare_news_sync")
    
    # 🔥 Check if there is already an instance running
    is_running, instance_id = await _check_task_running(job_id)
    if is_running:
        logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
        return {
            "skipped": True,
            "reason": "There is already an instance running",
            "running_instance_id": instance_id
        }
    
    try:
        service = await get_akshare_sync_service()
        # 🔥 Set the current task ID for use by sync_news_data
        service._current_job_id = job_id
        result = await service.sync_news_data(
            max_news_per_stock=max_news_per_stock
        )
        logger.info(f"✅ AKShare News data synchronization completed: {result}")
        return result
    except Exception as e:
        # 🔥 When the task fails, the updated status is failed
        try:
            from app.services.scheduler_service import update_job_progress
            await update_job_progress(
                job_id=job_id,
                progress=0,
                message=f"Task failed: {str(e)}"
            )
        except:
            pass
        logger.error(f"❌ AKShare News data synchronization failed: {e}")
        raise
