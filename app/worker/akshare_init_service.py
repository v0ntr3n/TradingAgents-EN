"""
AKShare Data initialization service
Used for complete data initialization during first deployment, including basic data, historical data, financial data, etc.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.core.database import get_mongo_db
from app.worker.akshare_sync_service import get_akshare_sync_service

logger = logging.getLogger(__name__)


@dataclass
class AKShareInitializationStats:
    """AKShare Initialize statistics"""
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_steps: int = 0
    completed_steps: int = 0
    current_step: str = ""
    basic_info_count: int = 0
    historical_records: int = 0
    weekly_records: int = 0
    monthly_records: int = 0
    financial_records: int = 0
    quotes_count: int = 0
    news_count: int = 0
    errors: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AKShareInitService:
    """
    AKShare Data initialization service
    
    Responsible for complete data initialization on first deployment:
    1. Check database status
    2. Initialize basic stock information
    3. Synchronize historical data (configurable time range)
    4. Sync financial data
    5. Synchronize the latest market data
    6. Verify data integrity
    """
    
    def __init__(self):
        self.db = None
        self.sync_service = None
        self.stats = None
    
    async def initialize(self):
        """Initialize service"""
        self.db = get_mongo_db()
        self.sync_service = await get_akshare_sync_service()
        logger.info("✅ AKShare Initialization service is ready")
    
    async def run_full_initialization(
        self,
        historical_days: int = 365,
        skip_if_exists: bool = True,
        batch_size: int = 100,
        enable_multi_period: bool = False,
        sync_items: List[str] = None
    ) -> Dict[str, Any]:
        """
        Run full data initialization

        Args:
            historical_days: Number of days of historical data (default 1 year)
            skip_if_exists: Whether to skip if the data already exists
            batch_size: batch size
            enable_multi_period: Whether to enable multi-period data synchronization (daily, weekly, monthly)
            sync_items: List of data types to synchronize, optional values:
                - 'basic_info': Basic stock information
                - 'historical': Historical market data (daily line)
                - 'weekly': Weekly data
                - 'monthly': monthly data
                - 'financial': financial data
                - 'quotes': Latest Quotes
                - 'news': news data
                - None: Sync all data (default)

        Returns:
            Initialization result statistics
        """
        # If sync_items is not specified, all data is synchronized
        if sync_items is None:
            sync_items = ['basic_info', 'historical', 'financial', 'quotes']
            if enable_multi_period:
                sync_items.extend(['weekly', 'monthly'])

        logger.info("🚀 Start complete initialization of AKShare data...")
        logger.info(f"📋 Sync projects: {', '.join(sync_items)}")

        # Calculate the total number of steps (check status + Number of synchronized items + verification)
        total_steps = 1 + len(sync_items) + 1

        self.stats = AKShareInitializationStats(
            started_at=datetime.utcnow(),
            total_steps=total_steps
        )

        try:
            # steps 1: Check database status
            # Check if skipped only when synchronizing basic_info
            if 'basic_info' in sync_items:
                await self._step_check_database_status(skip_if_exists)
            else:
                logger.info("📊 Check database status...")
                basic_count = await self.db.stock_basic_info.count_documents({})
                logger.info(f"  Current stock basic information: {basic_count}Article")
                if basic_count == 0:
                    logger.warning("⚠️ There is no basic stock information in the database. It is recommended to synchronize it first. basic_info")

            # steps 2: Initialize basic stock information
            if 'basic_info' in sync_items:
                await self._step_initialize_basic_info()
            else:
                logger.info("⏭️ Skip basic stock information synchronization")

            # steps 3: Synchronize historical data (daily line)
            if 'historical' in sync_items:
                await self._step_initialize_historical_data(historical_days)
            else:
                logger.info("⏭️ Skip historical data (daily line) synchronization")

            # steps 4: Synchronize weekly data
            if 'weekly' in sync_items:
                await self._step_initialize_weekly_data(historical_days)
            else:
                logger.info("⏭️ Skip weekly data synchronization")

            # steps 5: Synchronize monthly data
            if 'monthly' in sync_items:
                await self._step_initialize_monthly_data(historical_days)
            else:
                logger.info("⏭️ Skip monthly data synchronization")

            # steps 6: Sync financial data
            if 'financial' in sync_items:
                await self._step_initialize_financial_data()
            else:
                logger.info("⏭️ Skip financial data sync")

            # steps 7: Synchronize the latest market conditions
            if 'quotes' in sync_items:
                await self._step_initialize_quotes()
            else:
                logger.info("⏭️ Skip the latest market synchronization")

            # steps 8: Synchronize news data
            if 'news' in sync_items:
                await self._step_initialize_news_data()
            else:
                logger.info("⏭️ Skip news data sync")

            # finally: Verify data integrity
            await self._step_verify_data_integrity()
            
            self.stats.finished_at = datetime.utcnow()
            duration = (self.stats.finished_at - self.stats.started_at).total_seconds()
            
            logger.info(f"🎉 AKShare Data initialization completed! Time consuming: {duration:.2f}seconds")
            
            return self._get_initialization_summary()
            
        except Exception as e:
            logger.error(f"❌ AKShare Data initialization failed: {e}")
            self.stats.errors.append({
                "step": self.stats.current_step,
                "error": str(e),
                "timestamp": datetime.utcnow()
            })
            return self._get_initialization_summary()
    
    async def _step_check_database_status(self, skip_if_exists: bool):
        """steps 1: Check database status"""
        self.stats.current_step = "Check database status"
        logger.info(f"📊 {self.stats.current_step}...")
        
        # Check the data volume of each collection
        basic_count = await self.db.stock_basic_info.count_documents({})
        quotes_count = await self.db.market_quotes.count_documents({})
        
        logger.info(f"  Current data status:")
        logger.info(f"    Basic stock information: {basic_count}Article")
        logger.info(f"    Market data: {quotes_count}Article")
        
        if skip_if_exists and basic_count > 0:
            logger.info("⚠️ Existing data is detected and initialization is skipped (can be passed skip_if_exists=False forced initialization)")
            raise Exception("Data already exists, skip initialization")
        
        self.stats.completed_steps += 1
        logger.info(f"✅ {self.stats.current_step}Complete")
    
    async def _step_initialize_basic_info(self):
        """steps 2: Initialize basic stock information"""
        self.stats.current_step = "Initialize basic stock information"
        logger.info(f"📋 {self.stats.current_step}...")
        
        # Force update of all basic information
        result = await self.sync_service.sync_stock_basic_info(force_update=True)
        
        if result:
            self.stats.basic_info_count = result.get("success_count", 0)
            logger.info(f"✅ Basic information initialization completed: {self.stats.basic_info_count}only stocks")
        else:
            raise Exception("Basic information initialization failed")
        
        self.stats.completed_steps += 1
    
    async def _step_initialize_historical_data(self, historical_days: int):
        """steps 3: Synchronize historical data"""
        self.stats.current_step = f"Synchronize historical data({historical_days}day)"
        logger.info(f"📊 {self.stats.current_step}...")

        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')

        # If historical_days is greater than or equal to 10 years (3650 days), synchronize the entire history
        if historical_days >= 3650:
            start_date = "1990-01-01"  # Full history synchronized
            logger.info(f"  Historical data range: Full history (from 1990-01-01 to{end_date}) ")
        else:
            start_date = (datetime.now() - timedelta(days=historical_days)).strftime('%Y-%m-%d')
            logger.info(f"  Historical data range: {start_date} Arrive {end_date}")

        # Synchronize historical data
        result = await self.sync_service.sync_historical_data(
            start_date=start_date,
            end_date=end_date,
            incremental=False  # Full synchronization
        )
        
        if result:
            self.stats.historical_records = result.get("total_records", 0)
            logger.info(f"✅ Historical data initialization completed: {self.stats.historical_records}records")
        else:
            logger.warning("⚠️ The historical data initialization part failed, continue with the next steps.")
        
        self.stats.completed_steps += 1

    async def _step_initialize_weekly_data(self, historical_days: int):
        """steps 4a: Synchronize weekly data"""
        self.stats.current_step = f"Synchronize weekly data({historical_days}day)"
        logger.info(f"📊 {self.stats.current_step}...")

        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')

        # If historical_days is greater than or equal to 10 years (3650 days), synchronize the entire history
        if historical_days >= 3650:
            start_date = "1990-01-01"  # Full history synchronized
            logger.info(f"  Weekly data range: Full history (from 1990-01-01 to{end_date}) ")
        else:
            start_date = (datetime.now() - timedelta(days=historical_days)).strftime('%Y-%m-%d')
            logger.info(f"  Weekly data range: {start_date} Arrive {end_date}")

        try:
            # Synchronize weekly data
            result = await self.sync_service.sync_historical_data(
                start_date=start_date,
                end_date=end_date,
                incremental=False,
                period="weekly"  # Specify perimeter
            )

            if result:
                weekly_records = result.get("total_records", 0)
                self.stats.weekly_records = weekly_records
                logger.info(f"✅ Weekly data initialization completed: {weekly_records}records")
            else:
                logger.warning("⚠️ Partial initialization of weekly data failed, continue with subsequent steps.")
        except Exception as e:
            logger.warning(f"⚠️ Weekly data initialization failed: {e} (Continue to next steps)")

        self.stats.completed_steps += 1

    async def _step_initialize_monthly_data(self, historical_days: int):
        """steps 4b: Synchronize monthly data"""
        self.stats.current_step = f"Synchronize monthly data({historical_days}day)"
        logger.info(f"📊 {self.stats.current_step}...")

        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')

        # If historical_days is greater than or equal to 10 years (3650 days), synchronize the entire history
        if historical_days >= 3650:
            start_date = "1990-01-01"  # Full history synchronized
            logger.info(f"  monthly data range: Full history (from 1990-01-01 to{end_date}) ")
        else:
            start_date = (datetime.now() - timedelta(days=historical_days)).strftime('%Y-%m-%d')
            logger.info(f"  monthly data range: {start_date} Arrive {end_date}")

        try:
            # Synchronize monthly data
            result = await self.sync_service.sync_historical_data(
                start_date=start_date,
                end_date=end_date,
                incremental=False,
                period="monthly"  # Specify monthly line
            )

            if result:
                monthly_records = result.get("total_records", 0)
                self.stats.monthly_records = monthly_records
                logger.info(f"✅ Monthly data initialization completed: {monthly_records}records")
            else:
                logger.warning("⚠️ Partial initialization of monthly data failed, continue with subsequent steps")
        except Exception as e:
            logger.warning(f"⚠️ Monthly data initialization failed: {e} (Continue to next steps)")

        self.stats.completed_steps += 1

    async def _step_initialize_financial_data(self):
        """steps 4: Sync financial data"""
        self.stats.current_step = "Sync financial data"
        logger.info(f"💰 {self.stats.current_step}...")
        
        try:
            result = await self.sync_service.sync_financial_data()
            
            if result:
                self.stats.financial_records = result.get("success_count", 0)
                logger.info(f"✅ Financial data initialization completed: {self.stats.financial_records}records")
            else:
                logger.warning("⚠️ Financial data initialization failed")
        except Exception as e:
            logger.warning(f"⚠️ Financial data initialization failed: {e} (Continue to next steps)")
        
        self.stats.completed_steps += 1
    
    async def _step_initialize_quotes(self):
        """steps 5: Synchronize the latest market conditions"""
        self.stats.current_step = "Synchronize the latest market conditions"
        logger.info(f"📈 {self.stats.current_step}...")

        try:
            result = await self.sync_service.sync_realtime_quotes()

            if result:
                self.stats.quotes_count = result.get("success_count", 0)
                logger.info(f"✅ Latest market initialization completed: {self.stats.quotes_count}only stocks")
            else:
                logger.warning("⚠️ Latest market initialization failed")
        except Exception as e:
            logger.warning(f"⚠️ Latest market initialization failed: {e} (Continue to next steps)")

        self.stats.completed_steps += 1

    async def _step_initialize_news_data(self):
        """steps 6: Synchronize news data"""
        self.stats.current_step = "Synchronize news data"
        logger.info(f"📰 {self.stats.current_step}...")

        try:
            result = await self.sync_service.sync_news_data(
                max_news_per_stock=20
            )

            if result:
                self.stats.news_count = result.get("news_count", 0)
                logger.info(f"✅ News data initialization completed: {self.stats.news_count}news")
            else:
                logger.warning("⚠️ News data initialization failed")
        except Exception as e:
            logger.warning(f"⚠️ News data initialization failed: {e} (Continue to next steps)")

        self.stats.completed_steps += 1

    async def _step_verify_data_integrity(self):
        """steps 6: Verify data integrity"""
        self.stats.current_step = "Verify data integrity"
        logger.info(f"🔍 {self.stats.current_step}...")
        
        # Check final data status
        basic_count = await self.db.stock_basic_info.count_documents({})
        quotes_count = await self.db.market_quotes.count_documents({})
        
        # Check data quality
        extended_count = await self.db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        logger.info(f"  Data integrity verification:")
        logger.info(f"    Basic stock information: {basic_count}Article")
        logger.info(f"    Extended field coverage: {extended_count}Article ({extended_count/basic_count*100:.1f}%)")
        logger.info(f"    Market data: {quotes_count}Article")
        
        if basic_count == 0:
            raise Exception("Data initialization failed: no basic data")
        
        if extended_count / basic_count < 0.9:  # 90%The above should have extension fields
            logger.warning("⚠️ Extended field coverage is low and there may be data quality issues")
        
        self.stats.completed_steps += 1
        logger.info(f"✅ {self.stats.current_step}Complete")
    
    def _get_initialization_summary(self) -> Dict[str, Any]:
        """Get initialization summary"""
        duration = 0
        if self.stats.finished_at:
            duration = (self.stats.finished_at - self.stats.started_at).total_seconds()
        
        return {
            "success": self.stats.completed_steps == self.stats.total_steps,
            "started_at": self.stats.started_at,
            "finished_at": self.stats.finished_at,
            "duration": duration,
            "completed_steps": self.stats.completed_steps,
            "total_steps": self.stats.total_steps,
            "progress": f"{self.stats.completed_steps}/{self.stats.total_steps}",
            "data_summary": {
                "basic_info_count": self.stats.basic_info_count,
                "daily_records": self.stats.historical_records,
                "weekly_records": self.stats.weekly_records,
                "monthly_records": self.stats.monthly_records,
                "financial_records": self.stats.financial_records,
                "quotes_count": self.stats.quotes_count,
                "news_count": self.stats.news_count
            },
            "errors": self.stats.errors,
            "current_step": self.stats.current_step
        }


# Global initialization service instance
_akshare_init_service = None

async def get_akshare_init_service() -> AKShareInitService:
    """Get the AKShare initialization service instance"""
    global _akshare_init_service
    if _akshare_init_service is None:
        _akshare_init_service = AKShareInitService()
        await _akshare_init_service.initialize()
    return _akshare_init_service


# APScheduler Compatible initialization task function
async def run_akshare_full_initialization(
    historical_days: int = 365,
    skip_if_exists: bool = True
):
    """APScheduler Task: Run complete AKShare data initialization"""
    try:
        service = await get_akshare_init_service()
        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=skip_if_exists
        )
        logger.info(f"✅ AKShare Complete initialization completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ AKShare Full initialization failed: {e}")
        raise
