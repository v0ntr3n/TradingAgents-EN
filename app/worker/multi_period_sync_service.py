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
