"""
Sample SDK data synchronization service (app layer)
Shows how to create a data synchronization service to write external SDK data to a standardized MongoDB collection

Architecture description:
- tradingagents layer: Pure data acquisition and standardization, no database operations involved
- app layer: Data synchronization service, responsible for database operations and business logic
- data flow: external SDK → tradingagents adapter → app Synchronization service → MongoDB
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import os
from app.services.stock_data_service import get_stock_data_service
from app.core.database import get_mongo_db
from tradingagents.dataflows.providers.examples.example_sdk import ExampleSDKProvider

logger = logging.getLogger(__name__)


class ExampleSDKSyncService:
    """
    Sample SDK data synchronization service (app layer)

    Responsibilities:
    - Call the SDK adapter of the tradingagents layer to obtain standardized data
    - Perform business logic processing and data validation
    - Write data to MongoDB database
    - Manage sync status and error handling
    - Provide performance monitoring and statistics

    Architecture layering:
    - tradingagents/dataflows/: Pure data acquisition adapter
    - app/worker/: Data synchronization service (This category)
    - app/services/: Data access service
    """

    def __init__(self):
        # Adapter using tradingagents layer (Pure data acquisition)
        self.provider = ExampleSDKProvider()
        # Using app layer data services (Database operations)
        self.stock_service = get_stock_data_service()
        
        # Sync configuration
        self.batch_size = int(os.getenv("EXAMPLE_SDK_BATCH_SIZE", "100"))
        self.retry_times = int(os.getenv("EXAMPLE_SDK_RETRY_TIMES", "3"))
        self.retry_delay = int(os.getenv("EXAMPLE_SDK_RETRY_DELAY", "5"))
        
        # Statistics
        self.sync_stats = {
            "basic_info": {"total": 0, "success": 0, "failed": 0},
            "quotes": {"total": 0, "success": 0, "failed": 0},
            "financial": {"total": 0, "success": 0, "failed": 0}
        }
    
    async def sync_all_data(self):
        """Sync all data"""
        logger.info("🚀 Start ExampleSDK full data synchronization...")
        
        start_time = datetime.now()
        
        try:
            # Connect to data source
            if not await self.provider.connect():
                logger.error("❌ ExampleSDK Connection failed, sync aborted")
                return False
            
            # Synchronize basic information
            await self.sync_basic_info()
            
            # Synchronize real-time quotes
            await self.sync_realtime_quotes()
            
            # Sync financial data
            await self.sync_financial_data()
            
            # Record sync status
            await self._record_sync_status("success", start_time)
            
            logger.info("✅ ExampleSDK Full data synchronization completed")
            self._log_sync_stats()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ ExampleSDK Data synchronization failed: {e}")
            await self._record_sync_status("failed", start_time, str(e))
            return False
            
        finally:
            await self.provider.disconnect()
    
    async def sync_basic_info(self):
        """Synchronize basic stock information"""
        logger.info("📊 Start synchronizing basic stock information...")
        
        try:
            # Get a list of stocks
            stock_list = await self.provider.get_stock_list()
            
            if not stock_list:
                logger.warning("⚠️ No stock list obtained")
                return
            
            self.sync_stats["basic_info"]["total"] = len(stock_list)
            
            # Batch processing
            for i in range(0, len(stock_list), self.batch_size):
                batch = stock_list[i:i + self.batch_size]
                await self._process_basic_info_batch(batch)
                
                # progress log
                processed = min(i + self.batch_size, len(stock_list))
                logger.info(f"📈 Basic information synchronization progress: {processed}/{len(stock_list)}")
                
                # Avoid API restrictions
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ Basic stock information synchronization completed: {self.sync_stats['basic_info']['success']}/{self.sync_stats['basic_info']['total']}")
            
        except Exception as e:
            logger.error(f"❌ Synchronization of basic stock information failed: {e}")
    
    async def sync_realtime_quotes(self):
        """Synchronize real-time quotes"""
        logger.info("📈 Start synchronizing real-time quotes...")
        
        try:
            # Get the list of stock codes that need to be synchronized
            db = get_mongo_db()
            cursor = db.stock_basic_info.find({}, {"code": 1})
            stock_codes = [doc["code"] async for doc in cursor]
            
            if not stock_codes:
                logger.warning("⚠️ No stocks needing synchronized quotes found")
                return
            
            self.sync_stats["quotes"]["total"] = len(stock_codes)
            
            # Batch processing
            for i in range(0, len(stock_codes), self.batch_size):
                batch = stock_codes[i:i + self.batch_size]
                await self._process_quotes_batch(batch)
                
                # progress log
                processed = min(i + self.batch_size, len(stock_codes))
                logger.info(f"📈 Real-time market synchronization progress: {processed}/{len(stock_codes)}")
                
                # Avoid API restrictions
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ Real-time market synchronization completed: {self.sync_stats['quotes']['success']}/{self.sync_stats['quotes']['total']}")
            
        except Exception as e:
            logger.error(f"❌ Real-time market synchronization failed: {e}")
    
    async def sync_financial_data(self):
        """Sync financial data"""
        logger.info("💰 Start syncing financial data...")
        
        try:
            # Get stocks whose financial data needs to be updated
            # Here you can filter based on business needs, such as only synchronizing major stocks or updating regularly.
            db = get_mongo_db()
            cursor = db.stock_basic_info.find(
                {"total_mv": {"$gte": 100}},  # Only synchronize stocks with market capitalization greater than 10 billion
                {"code": 1}
            ).limit(50)  # Limit the number to avoid too many API calls
            
            stock_codes = [doc["code"] async for doc in cursor]
            
            if not stock_codes:
                logger.warning("⚠️ No stocks found that require synchronized financial data")
                return
            
            self.sync_stats["financial"]["total"] = len(stock_codes)
            
            # Processed one by one (financial data is usually API more restrictive)
            for code in stock_codes:
                await self._process_financial_data(code)
                await asyncio.sleep(1)  # longer delay
            
            logger.info(f"✅ Financial data synchronization completed: {self.sync_stats['financial']['success']}/{self.sync_stats['financial']['total']}")
            
        except Exception as e:
            logger.error(f"❌ Financial data synchronization failed: {e}")
    
    async def _process_basic_info_batch(self, batch: List[Dict[str, Any]]):
        """Process basic information batches"""
        for stock_info in batch:
            try:
                code = stock_info.get("code")
                if not code:
                    continue
                
                # Update to database
                success = await self.stock_service.update_stock_basic_info(code, stock_info)
                
                if success:
                    self.sync_stats["basic_info"]["success"] += 1
                else:
                    self.sync_stats["basic_info"]["failed"] += 1
                    logger.warning(f"⚠️ update{code}Basic information failed")
                    
            except Exception as e:
                self.sync_stats["basic_info"]["failed"] += 1
                logger.error(f"❌ Process{stock_info.get('code', 'N/A')}Basic information failed: {e}")
    
    async def _process_quotes_batch(self, batch: List[str]):
        """Process quotation batches"""
        for code in batch:
            try:
                # Get real-time quotes
                quotes = await self.provider.get_stock_quotes(code)
                
                if quotes:
                    # Update to database
                    success = await self.stock_service.update_market_quotes(code, quotes)
                    
                    if success:
                        self.sync_stats["quotes"]["success"] += 1
                    else:
                        self.sync_stats["quotes"]["failed"] += 1
                        logger.warning(f"⚠️ update{code}Quote failed")
                else:
                    self.sync_stats["quotes"]["failed"] += 1
                    
            except Exception as e:
                self.sync_stats["quotes"]["failed"] += 1
                logger.error(f"❌ Process{code}Quote failed: {e}")
    
    async def _process_financial_data(self, code: str):
        """Process financial data"""
        try:
            # Get financial data
            financial_data = await self.provider.get_financial_data(code)
            
            if financial_data:
                # Here you need to implement the storage logic of financial data
                # New collections may need to be created stock_financial_data
                db = get_mongo_db()
                
                # Build update data
                update_data = {
                    "code": code,
                    "financial_data": financial_data,
                    "updated_at": datetime.utcnow()
                }
                
                # Update or insert financial data
                await db.stock_financial_data.update_one(
                    {"code": code},
                    {"$set": update_data},
                    upsert=True
                )
                
                self.sync_stats["financial"]["success"] += 1
                logger.debug(f"✅ update{code}financial data success")
            else:
                self.sync_stats["financial"]["failed"] += 1
                
        except Exception as e:
            self.sync_stats["financial"]["failed"] += 1
            logger.error(f"❌ Process{code}Financial data failed: {e}")
    
    async def _record_sync_status(self, status: str, start_time: datetime, error_msg: str = None):
        """Record sync status"""
        try:
            db = get_mongo_db()
            
            sync_record = {
                "job": "example_sdk_sync",
                "status": status,
                "started_at": start_time,
                "finished_at": datetime.now(),
                "duration": (datetime.now() - start_time).total_seconds(),
                "stats": self.sync_stats.copy(),
                "error_message": error_msg,
                "created_at": datetime.now()
            }
            
            await db.sync_status.update_one(
                {"job": "example_sdk_sync"},
                {"$set": sync_record},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"❌ Logging sync status failed: {e}")
    
    def _log_sync_stats(self):
        """Record sync statistics"""
        logger.info("📊 ExampleSDK Synchronization statistics:")
        for data_type, stats in self.sync_stats.items():
            total = stats["total"]
            success = stats["success"]
            failed = stats["failed"]
            success_rate = (success / total * 100) if total > 0 else 0
            
            logger.info(f"   {data_type}: {success}/{total} ({success_rate:.1f}%) success, {failed} failed")
    
    async def sync_incremental(self):
        """Incremental synchronization - only synchronize real-time quotes"""
        logger.info("🔄 Start ExampleSDK incremental synchronization...")
        
        try:
            if not await self.provider.connect():
                logger.error("❌ ExampleSDK Connection failed, incremental sync aborted")
                return False
            
            # Only synchronize real-time quotes
            await self.sync_realtime_quotes()
            
            logger.info("✅ ExampleSDK Incremental synchronization completed")
            return True
            
        except Exception as e:
            logger.error(f"❌ ExampleSDK Incremental sync failed: {e}")
            return False
            
        finally:
            await self.provider.disconnect()


# ==================== Scheduled task function ====================

async def run_full_sync():
    """Run full synchronization - called by scheduled tasks"""
    sync_service = ExampleSDKSyncService()
    return await sync_service.sync_all_data()


async def run_incremental_sync():
    """Run incremental synchronization - called by scheduled tasks"""
    sync_service = ExampleSDKSyncService()
    return await sync_service.sync_incremental()


# ==================== Usage example ====================

async def main():
    """Main function - for testing"""
    logging.basicConfig(level=logging.INFO)
    
    sync_service = ExampleSDKSyncService()
    
    # Test full synchronization
    await sync_service.sync_all_data()


if __name__ == "__main__":
    asyncio.run(main())
