#!/usr/bin/env python3
"""
BaoStock Data initialization service
Provides complete initialization function for BaoStock data
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.database import get_database
from app.worker.baostock_sync_service import BaoStockSyncService, BaoStockSyncStats

logger = logging.getLogger(__name__)


@dataclass
class BaoStockInitializationStats:
    """BaoStock Initialize statistics"""
    completed_steps: int = 0
    total_steps: int = 6
    current_step: str = ""
    basic_info_count: int = 0
    quotes_count: int = 0
    historical_records: int = 0
    weekly_records: int = 0
    monthly_records: int = 0
    financial_records: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> float:
        """Calculation time (seconds)"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def progress(self) -> str:
        """progress string"""
        return f"{self.completed_steps}/{self.total_steps}"


class BaoStockInitService:
    """BaoStock Data initialization service"""

    def __init__(self):
        """
        Initialize service

        Note: The database connection is in initialize() Asynchronous initialization in method
        """
        try:
            self.settings = get_settings()
            self.db = None  # 🔥 Lazy initialization
            self.sync_service = BaoStockSyncService()
            logger.info("✅ BaoStock Initialization service initialization successful")
        except Exception as e:
            logger.error(f"❌ BaoStock Initialization service failed to initialize: {e}")
            raise

    async def initialize(self):
        """Asynchronous initialization service"""
        try:
            # 🔥 Initialize database connection
            from app.core.database import get_mongo_db
            self.db = get_mongo_db()

            # 🔥 Initialize synchronization service
            await self.sync_service.initialize()

            logger.info("✅ BaoStock The asynchronous initialization of the initialization service is completed")
        except Exception as e:
            logger.error(f"❌ BaoStock Initialization service asynchronous initialization failed: {e}")
            raise
    
    async def check_database_status(self) -> Dict[str, Any]:
        """Check database status"""
        try:
            # Check basic information
            basic_info_count = await self.db.stock_basic_info.count_documents({"source": "baostock"})
            basic_info_latest = None
            if basic_info_count > 0:
                latest_doc = await self.db.stock_basic_info.find_one(
                    {"source": "baostock"},
                    sort=[("last_sync", -1)]
                )
                if latest_doc:
                    basic_info_latest = latest_doc.get("last_sync")
            
            # Check market data
            quotes_count = await self.db.market_quotes.count_documents({"source": "baostock"})
            quotes_latest = None
            if quotes_count > 0:
                latest_doc = await self.db.market_quotes.find_one(
                    {"source": "baostock"},
                    sort=[("last_sync", -1)]
                )
                if latest_doc:
                    quotes_latest = latest_doc.get("last_sync")
            
            return {
                "basic_info_count": basic_info_count,
                "basic_info_latest": basic_info_latest,
                "quotes_count": quotes_count,
                "quotes_latest": quotes_latest,
                "status": "ready" if basic_info_count > 0 else "empty"
            }
            
        except Exception as e:
            logger.error(f"❌ Checking database status failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def full_initialization(self, historical_days: int = 365,
                                force: bool = False,
                                enable_multi_period: bool = False) -> BaoStockInitializationStats:
        """
        Complete data initialization

        Args:
            historical_days: Historical data days
            force: Whether to force reinitialization
            enable_multi_period: Whether to enable multi-period data synchronization (daily, weekly, monthly)

        Returns:
            Initialize statistics
        """
        stats = BaoStockInitializationStats()
        stats.total_steps = 8 if enable_multi_period else 6
        stats.start_time = datetime.now()
        
        try:
            logger.info("🚀 Start BaoStock complete data initialization...")
            
            # steps 1: Check database status
            stats.current_step = "Check database status"
            logger.info(f"1️⃣ {stats.current_step}...")
            
            db_status = await self.check_database_status()
            if db_status["status"] != "empty" and not force:
                logger.info("ℹ️ The database already has data, skip initialization (use --force to force reinitialization)")
                stats.completed_steps = 6
                stats.end_time = datetime.now()
                return stats
            
            stats.completed_steps += 1
            
            # steps 2: Initialize basic stock information
            stats.current_step = "Initialize basic stock information"
            logger.info(f"2️⃣ {stats.current_step}...")
            
            basic_stats = await self.sync_service.sync_stock_basic_info()
            stats.basic_info_count = basic_stats.basic_info_count
            stats.errors.extend(basic_stats.errors)
            stats.completed_steps += 1
            
            if stats.basic_info_count == 0:
                raise Exception("Basic information synchronization failed and cannot continue.")
            
            # steps 3: Synchronize historical data (daily line)
            stats.current_step = "Synchronize historical data (daily line)"
            logger.info(f"3️⃣ {stats.current_step} (Recently{historical_days}day)...")

            historical_stats = await self.sync_service.sync_historical_data(days=historical_days, period="daily")
            stats.historical_records = historical_stats.historical_records
            stats.errors.extend(historical_stats.errors)
            stats.completed_steps += 1

            # steps 4: Synchronize multi-cycle data (if enabled)
            if enable_multi_period:
                # Synchronize weekly data
                stats.current_step = "Synchronize weekly data"
                logger.info(f"4️⃣a {stats.current_step} (Recently{historical_days}day)...")
                try:
                    weekly_stats = await self.sync_service.sync_historical_data(days=historical_days, period="weekly")
                    stats.weekly_records = weekly_stats.historical_records
                    stats.errors.extend(weekly_stats.errors)
                    logger.info(f"✅ Weekly data synchronization completed: {stats.weekly_records}records")
                except Exception as e:
                    logger.warning(f"⚠️ Weekly data synchronization failed: {e} (Continue to next steps)")
                stats.completed_steps += 1

                # Synchronize monthly data
                stats.current_step = "Synchronize monthly data"
                logger.info(f"4️⃣b {stats.current_step} (Recently{historical_days}day)...")
                try:
                    monthly_stats = await self.sync_service.sync_historical_data(days=historical_days, period="monthly")
                    stats.monthly_records = monthly_stats.historical_records
                    stats.errors.extend(monthly_stats.errors)
                    logger.info(f"✅ Monthly data synchronization completed: {stats.monthly_records}records")
                except Exception as e:
                    logger.warning(f"⚠️ Monthly data synchronization failed: {e} (Continue to next steps)")
                stats.completed_steps += 1
            
            # steps 4: Sync financial data
            stats.current_step = "Sync financial data"
            logger.info(f"4️⃣ {stats.current_step}...")
            
            financial_stats = await self._sync_financial_data()
            stats.financial_records = financial_stats
            stats.completed_steps += 1
            
            # steps 5: Synchronize the latest market conditions
            stats.current_step = "Synchronize the latest market conditions"
            logger.info(f"5️⃣ {stats.current_step}...")
            
            quotes_stats = await self.sync_service.sync_realtime_quotes()
            stats.quotes_count = quotes_stats.quotes_count
            stats.errors.extend(quotes_stats.errors)
            stats.completed_steps += 1
            
            # steps 6: Verify data integrity
            stats.current_step = "Verify data integrity"
            logger.info(f"6️⃣ {stats.current_step}...")
            
            await self._verify_data_integrity(stats)
            stats.completed_steps += 1
            
            stats.end_time = datetime.now()
            logger.info(f"🎉 BaoStock Full initialization completed successfully! Time consuming: {stats.duration:.1f}seconds")
            
            return stats
            
        except Exception as e:
            stats.end_time = datetime.now()
            error_msg = f"BaoStock Initialization failed: {e}"
            logger.error(f"❌ {error_msg}")
            stats.errors.append(error_msg)
            return stats
    
    async def _sync_financial_data(self) -> int:
        """Sync financial data"""
        try:
            # Get a list of stocks
            collection = self.db.stock_basic_info
            cursor = collection.find({"source": "baostock"}, {"code": 1})
            stock_codes = [doc["code"] async for doc in cursor]
            
            if not stock_codes:
                return 0
            
            # Limit quantity to avoid timeouts
            limited_codes = stock_codes[:50]  # Only the first 50 stocks are processed
            financial_count = 0
            
            for code in limited_codes:
                try:
                    financial_data = await self.sync_service.provider.get_financial_data(code)
                    if financial_data:
                        # Update to database
                        await collection.update_one(
                            {"code": code},
                            {"$set": {
                                "financial_data": financial_data,
                                "financial_data_updated": datetime.now()
                            }}
                        )
                        financial_count += 1
                    
                    # Avoid API restrictions
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"get{code}Financial data failed: {e}")
                    continue
            
            logger.info(f"✅ Financial data synchronization completed: {financial_count}records")
            return financial_count
            
        except Exception as e:
            logger.error(f"❌ Financial data synchronization failed: {e}")
            return 0
    
    async def _verify_data_integrity(self, stats: BaoStockInitializationStats):
        """Verify data integrity"""
        try:
            # Check basic information
            basic_count = await self.db.stock_basic_info.count_documents({"source": "baostock"})
            if basic_count != stats.basic_info_count:
                logger.warning(f"⚠️ The amount of basic information does not match: expected{stats.basic_info_count}, actual{basic_count}")
            
            # Check market data
            quotes_count = await self.db.market_quotes.count_documents({"source": "baostock"})
            if quotes_count != stats.quotes_count:
                logger.warning(f"⚠️ Quantity of market data does not match: expected{stats.quotes_count}, actual{quotes_count}")
            
            logger.info("✅ Data integrity verification completed")
            
        except Exception as e:
            logger.error(f"❌ Data integrity verification failed: {e}")
            stats.errors.append(f"Data integrity verification failed: {e}")
    
    async def basic_initialization(self) -> BaoStockInitializationStats:
        """Basic data initialization (only basic information and market prices)"""
        stats = BaoStockInitializationStats()
        stats.start_time = datetime.now()
        stats.total_steps = 3
        
        try:
            logger.info("🚀 Start BaoStock basic data initialization...")
            
            # steps 1: Initialize basic stock information
            stats.current_step = "Initialize basic stock information"
            logger.info(f"1️⃣ {stats.current_step}...")
            
            basic_stats = await self.sync_service.sync_stock_basic_info()
            stats.basic_info_count = basic_stats.basic_info_count
            stats.errors.extend(basic_stats.errors)
            stats.completed_steps += 1
            
            # steps 2: Synchronize the latest market conditions
            stats.current_step = "Synchronize the latest market conditions"
            logger.info(f"2️⃣ {stats.current_step}...")
            
            quotes_stats = await self.sync_service.sync_realtime_quotes()
            stats.quotes_count = quotes_stats.quotes_count
            stats.errors.extend(quotes_stats.errors)
            stats.completed_steps += 1
            
            # steps 3: Validate data
            stats.current_step = "Verify data integrity"
            logger.info(f"3️⃣ {stats.current_step}...")
            
            await self._verify_data_integrity(stats)
            stats.completed_steps += 1
            
            stats.end_time = datetime.now()
            logger.info(f"🎉 BaoStock Basic initialization completed! Time consuming: {stats.duration:.1f}seconds")
            
            return stats
            
        except Exception as e:
            stats.end_time = datetime.now()
            error_msg = f"BaoStock Basic initialization failed: {e}"
            logger.error(f"❌ {error_msg}")
            stats.errors.append(error_msg)
            return stats


# APScheduler Compatible initialization functions
async def run_baostock_full_initialization():
    """Run BaoStock full initialization"""
    try:
        service = BaoStockInitService()
        await service.initialize()  # 🔥 Must be initialized first
        stats = await service.full_initialization()
        logger.info(f"🎯 BaoStock Complete initialization completed: {stats.progress}, Time consuming: {stats.duration:.1f}seconds")
    except Exception as e:
        logger.error(f"❌ BaoStock Complete initialization task failed: {e}")


async def run_baostock_basic_initialization():
    """Run BaoStock basic initialization"""
    try:
        service = BaoStockInitService()
        await service.initialize()  # 🔥 Must be initialized first
        stats = await service.basic_initialization()
        logger.info(f"🎯 BaoStock Basic initialization completed: {stats.progress}, Time consuming: {stats.duration:.1f}seconds")
    except Exception as e:
        logger.error(f"❌ BaoStock Basic initialization task failed: {e}")
