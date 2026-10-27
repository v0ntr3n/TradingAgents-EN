#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hong Kong stock data service (obtain on demand+cache mode)

Function:
1. Obtain Hong Kong stock information from data sources on demand (yfinance/akshare)
2. Automatically cache to MongoDB to avoid repeated requests
3. Support multiple data sources: the same stock can have multiple data source records
4. Use (code, source) Union query performs upsert operation

Design description:
- Get on demand+Cache mode to avoid batch sync triggering rate limiting
- Refer to the A-share data source management method (Tushare/AKShare/BaoStock)
- Cache duration is configurable (default 24 hours)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pymongo import UpdateOne

# Import Hong Kong stock data provider
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.dataflows.providers.hk.hk_stock import HKStockProvider
from tradingagents.dataflows.providers.hk.improved_hk import ImprovedHKStockProvider
from app.core.database import get_mongo_db
from app.core.config import settings

logger = logging.getLogger(__name__)


class HKDataService:
    """Hong Kong stock data service (obtain on demand+cache mode)"""

    def __init__(self):
        self.db = get_mongo_db()
        self.settings = settings

        # Data provider mapping
        self.providers = {
            "yfinance": HKStockProvider(),
            "akshare": ImprovedHKStockProvider(),
        }

        # Cache configuration
        self.cache_hours = getattr(settings, 'HK_DATA_CACHE_HOURS', 24)
        self.default_source = getattr(settings, 'HK_DEFAULT_DATA_SOURCE', 'yfinance')

        # Hong Kong stock list cache (dynamically obtained from AKShare)
        self.hk_stock_list = []
        self._stock_list_cache_time = None
        self._stock_list_cache_ttl = 3600 * 24  # Cache for 24 hours

    async def initialize(self):
        """Initialize synchronization service"""
        logger.info("✅ Hong Kong stock synchronization service initialization completed")

    def _get_hk_stock_list_from_akshare(self) -> List[str]:
        """
        Get all Hong Kong stocks list from AKShare

        Returns:
            List[str]: Hong Kong stock code list
        """
        try:
            import akshare as ak
            from datetime import datetime, timedelta

            # Check if cache is valid
            if (self.hk_stock_list and self._stock_list_cache_time and
                datetime.now() - self._stock_list_cache_time < timedelta(seconds=self._stock_list_cache_ttl)):
                logger.debug(f"📦 Use cached Hong Kong stock list: {len(self.hk_stock_list)} only")
                return self.hk_stock_list

            logger.info("🔄 Get Hong Kong stock list from AKShare...")

            # Get real-time quotes of all Hong Kong stocks (including codes and names)
            # Use Sina Finance interface (more stable)
            df = ak.stock_hk_spot()

            if df is None or df.empty:
                logger.warning("⚠️ AKShare Return empty data, use fallback list")
                return self._get_fallback_stock_list()

            # Extract a list of stock symbols
            stock_codes = df['代码'].tolist()

            # Standardized code format (make sure it is 5 digits)
            stock_codes = [code.zfill(5) for code in stock_codes if code]

            logger.info(f"✅ successfully obtained {len(stock_codes)} Only Hong Kong stocks")

            # Update cache
            self.hk_stock_list = stock_codes
            self._stock_list_cache_time = datetime.now()

            return stock_codes

        except Exception as e:
            logger.error(f"❌ Failed to obtain Hong Kong stock list from AKShare: {e}")
            logger.info("📋 Use alternate Hong Kong stock list")
            return self._get_fallback_stock_list()

    def _get_fallback_stock_list(self) -> List[str]:
        """
        Obtain the backup Hong Kong stock list (main Hong Kong stock targets)

        Returns:
            List[str]: Hong Kong stock code list
        """
        return [
            "00700",  # Tencent Holdings
            "09988",  # Alibaba
            "03690",  # Meituan
            "01810",  # Xiaomi Group
            "00941",  # China Mobile
            "00762",  # China Unicom
            "00728",  # China Telecom
            "00939",  # China Construction Bank
            "01398",  # ICBC
            "03988",  # Bank of China
            "00005",  # HSBC Holdings
            "01299",  # AIA
            "02318",  # Ping An of China
            "02628",  # China Life
            "00857",  # PetroChina
            "00386",  # Sinopec
            "01211",  # BYD
            "02015",  # ideal car
            "09868",  # Xpeng Motors
            "09866",  # NIO
        ]
    
    async def sync_basic_info_from_source(
        self,
        source: str,
        force_update: bool = False
    ) -> Dict[str, int]:
        """
        Synchronize basic information of Hong Kong stocks from specified data source

        Args:
            source: Data source name (yfinance/akshare)
            force_update: Whether to force update (forcibly refresh the stock list)

        Returns:
            Dict: Sync statistics {updated: int, inserted: int, failed: int}
        """
        # AKShare Data sources use batch synchronization
        if source == "akshare":
            return await self._sync_basic_info_from_akshare_batch(force_update)

        # yfinance Data sources use one-by-one synchronization
        provider = self.providers.get(source)
        if not provider:
            logger.error(f"❌ Unsupported data source: {source}")
            return {"updated": 0, "inserted": 0, "failed": 0}

        # If update is forced, clear cache
        if force_update:
            self._stock_list_cache_time = None
            logger.info("🔄 Forced refresh of Hong Kong stock list")

        # Get Hong Kong stock list (from AKShare or cache)
        stock_list = self._get_hk_stock_list_from_akshare()

        if not stock_list:
            logger.error("❌ Unable to obtain Hong Kong stock list")
            return {"updated": 0, "inserted": 0, "failed": 0}

        logger.info(f"🇭🇰 Start synchronizing basic information of Hong Kong stocks (data source: {source})")
        logger.info(f"📊 Number of stocks to be synchronized: {len(stock_list)}")

        operations = []
        failed_count = 0

        for stock_code in stock_list:
            try:
                # Get data from data source
                stock_info = provider.get_stock_info(stock_code)

                if not stock_info or not stock_info.get('name'):
                    logger.warning(f"⚠️ Skip invalid data: {stock_code}")
                    failed_count += 1
                    continue

                # standardized data format
                normalized_info = self._normalize_stock_info(stock_info, source)
                normalized_info["code"] = stock_code.lstrip('0').zfill(5)  # Normalized to 5-digit code
                normalized_info["source"] = source
                normalized_info["updated_at"] = datetime.now()

                # Batch update operation
                operations.append(
                    UpdateOne(
                        {"code": normalized_info["code"], "source": source},  # 🔥 Union query conditions
                        {"$set": normalized_info},
                        upsert=True
                    )
                )

                logger.debug(f"✅ Prepare to sync: {stock_code} ({stock_info.get('name')}) from {source}")

            except Exception as e:
                logger.error(f"❌ Sync failed: {stock_code} from {source}: {e}")
                failed_count += 1

        # Perform batch operations
        result = {"updated": 0, "inserted": 0, "failed": failed_count}

        if operations:
            try:
                bulk_result = await self.db.stock_basic_info_hk.bulk_write(operations)
                result["updated"] = bulk_result.modified_count
                result["inserted"] = bulk_result.upserted_count

                logger.info(
                    f"✅ Basic information on Hong Kong stocks is completed simultaneously ({source}): "
                    f"update {result['updated']} Article, "
                    f"Insert {result['inserted']} Article, "
                    f"failed {result['failed']} Article"
                )
            except Exception as e:
                logger.error(f"❌ Batch write failed: {e}")
                result["failed"] += len(operations)

        return result

    async def _sync_basic_info_from_akshare_batch(self, force_update: bool = False) -> Dict[str, int]:
        """
        Batch synchronize basic Hong Kong stock information from AKShare (get all data in one API call)

        Args:
            force_update: Whether to force update (force refresh data)

        Returns:
            Dict: Sync statistics {updated: int, inserted: int, failed: int}
        """
        try:
            import akshare as ak
            from datetime import datetime

            logger.info("🇭🇰 Start synchronizing basic Hong Kong stock information in batches (data source: akshare)")

            # Get real-time quotes for all Hong Kong stocks (including basic information such as codes, names, etc.)
            # Use Sina Finance interface (more stable)
            df = ak.stock_hk_spot()

            if df is None or df.empty:
                logger.error("❌ AKShare Return empty data")
                return {"updated": 0, "inserted": 0, "failed": 0}

            logger.info(f"📊 Get {len(df)} Hong Kong stock data only")

            operations = []
            failed_count = 0

            for _, row in df.iterrows():
                try:
                    # Extract stock code and name
                    stock_code = str(row.get('代码', '')).strip()
                    # The column name of Sina interface is 'Chinese name'
                    stock_name = str(row.get('中文名称', '')).strip()

                    if not stock_code or not stock_name:
                        failed_count += 1
                        continue

                    # Standardized code format (make sure it is 5 digits)
                    normalized_code = stock_code.lstrip('0').zfill(5)

                    # Build basic information
                    stock_info = {
                        "code": normalized_code,
                        "name": stock_name,
                        "currency": "HKD",
                        "exchange": "HKG",
                        "market": "Hong Kong Exchange",
                        "area": "Hong Kong",
                        "source": "akshare",
                        "updated_at": datetime.now()
                    }

                    # Optional fields: Extract other information from market data
                    if 'latest price' in row and row['最新价']:
                        stock_info["latest_price"] = float(row['最新价'])

                    if 'Increase or decrease' in row and row['涨跌幅']:
                        stock_info["change_percent"] = float(row['涨跌幅'])

                    if 'Total market capitalization' in row and row['总市值']:
                        # Convert to 100 million Hong Kong dollars
                        stock_info["total_mv"] = float(row['总市值']) / 100000000

                    if 'P/E ratio' in row and row['市盈率']:
                        stock_info["pe"] = float(row['市盈率'])

                    # Batch update operation
                    operations.append(
                        UpdateOne(
                            {"code": normalized_code, "source": "akshare"},
                            {"$set": stock_info},
                            upsert=True
                        )
                    )

                except Exception as e:
                    logger.debug(f"⚠️ Failed to process stock data: {stock_code}: {e}")
                    failed_count += 1

            # Perform batch operations
            result = {"updated": 0, "inserted": 0, "failed": failed_count}

            if operations:
                try:
                    bulk_result = await self.db.stock_basic_info_hk.bulk_write(operations)
                    result["updated"] = bulk_result.modified_count
                    result["inserted"] = bulk_result.upserted_count

                    logger.info(
                        f"✅ Hong Kong stock basic information is synchronized in batches (akshare): "
                        f"update {result['updated']} Article, "
                        f"Insert {result['inserted']} Article, "
                        f"failed {result['failed']} Article"
                    )
                except Exception as e:
                    logger.error(f"❌ Batch write failed: {e}")
                    result["failed"] += len(operations)

            return result

        except Exception as e:
            logger.error(f"❌ AKShare Batch sync failed: {e}")
            return {"updated": 0, "inserted": 0, "failed": 0}

    def _normalize_stock_info(self, stock_info: Dict, source: str) -> Dict:
        """
        Standardized stock information format
        
        Args:
            stock_info: Original stock information
            source: data source
        
        Returns:
            Dict: Standardized stock information
        """
        # Extract common fields
        normalized = {
            "name": stock_info.get("name", ""),
            "name_en": stock_info.get("name_en", ""),
            "currency": stock_info.get("currency", "HKD"),
            "exchange": stock_info.get("exchange", "HKG"),
            "market": "Hong Kong Exchange",
            "area": "Hong Kong",
        }
        
        # optional fields
        if "market_cap" in stock_info and stock_info["market_cap"]:
            # Convert to 100 million Hong Kong dollars
            normalized["total_mv"] = stock_info["market_cap"] / 100000000
        
        if "sector" in stock_info:
            normalized["sector"] = stock_info["sector"]
        
        if "industry" in stock_info:
            normalized["industry"] = stock_info["industry"]
        
        return normalized
    
    async def sync_quotes_from_source(
        self,
        source: str = "yfinance"
    ) -> Dict[str, int]:
        """
        Synchronize real-time quotes of Hong Kong stocks from designated data sources
        
        Args:
            source: Data source name (Default yfinance)
        
        Returns:
            Dict: Sync statistics
        """
        provider = self.providers.get(source)
        if not provider:
            logger.error(f"❌ Unsupported data source: {source}")
            return {"updated": 0, "inserted": 0, "failed": 0}
        
        logger.info(f"🇭🇰 Start synchronizing the real-time market conditions of Hong Kong stocks (data source: {source})")
        
        operations = []
        failed_count = 0
        
        for stock_code in self.hk_stock_list:
            try:
                # Get real-time prices
                quote = provider.get_real_time_price(stock_code)
                
                if not quote or not quote.get('price'):
                    logger.warning(f"⚠️ Skip invalid quotes: {stock_code}")
                    failed_count += 1
                    continue
                
                # Standardized market data
                normalized_quote = {
                    "code": stock_code.lstrip('0').zfill(5),
                    "close": float(quote.get('price', 0)),
                    "open": float(quote.get('open', 0)),
                    "high": float(quote.get('high', 0)),
                    "low": float(quote.get('low', 0)),
                    "volume": int(quote.get('volume', 0)),
                    "currency": "HKD",
                    "updated_at": datetime.now()
                }
                
                # Calculate the increase or decrease
                if normalized_quote["open"] > 0:
                    pct_chg = ((normalized_quote["close"] - normalized_quote["open"]) / normalized_quote["open"]) * 100
                    normalized_quote["pct_chg"] = round(pct_chg, 2)
                
                operations.append(
                    UpdateOne(
                        {"code": normalized_quote["code"]},
                        {"$set": normalized_quote},
                        upsert=True
                    )
                )
                
                logger.debug(f"✅ Prepare to sync the market: {stock_code} (price: {normalized_quote['close']} HKD)")
                
            except Exception as e:
                logger.error(f"❌ Synchronized market failure: {stock_code}: {e}")
                failed_count += 1
        
        # Perform batch operations
        result = {"updated": 0, "inserted": 0, "failed": failed_count}
        
        if operations:
            try:
                bulk_result = await self.db.market_quotes_hk.bulk_write(operations)
                result["updated"] = bulk_result.modified_count
                result["inserted"] = bulk_result.upserted_count
                
                logger.info(
                    f"✅ Hong Kong stock prices are completed simultaneously: "
                    f"update {result['updated']} Article, "
                    f"Insert {result['inserted']} Article, "
                    f"failed {result['failed']} Article"
                )
            except Exception as e:
                logger.error(f"❌ Batch write failed: {e}")
                result["failed"] += len(operations)
        
        return result


# ==================== Global service instance ====================

_hk_sync_service = None

async def get_hk_sync_service() -> HKSyncService:
    """Get an instance of Hong Kong stock synchronization service"""
    global _hk_sync_service
    if _hk_sync_service is None:
        _hk_sync_service = HKSyncService()
        await _hk_sync_service.initialize()
    return _hk_sync_service


# ==================== APScheduler Compatible task functions ====================

async def run_hk_yfinance_basic_info_sync(force_update: bool = False):
    """APScheduler Task: Synchronization of basic information on Hong Kong stocks (yfinance)"""
    try:
        service = await get_hk_sync_service()
        result = await service.sync_basic_info_from_source("yfinance", force_update)
        logger.info(f"✅ Basic information on Hong Kong stocks is completed simultaneously (yfinance): {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Hong Kong stock basic information synchronization failed (yfinance): {e}")
        raise


async def run_hk_akshare_basic_info_sync(force_update: bool = False):
    """APScheduler Task: Basic information synchronization of Hong Kong stocks (akshare)"""
    try:
        service = await get_hk_sync_service()
        result = await service.sync_basic_info_from_source("akshare", force_update)
        logger.info(f"✅ Basic information on Hong Kong stocks is completed simultaneously (AKShare): {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Hong Kong stock basic information synchronization failed (AKShare): {e}")
        raise


async def run_hk_yfinance_quotes_sync():
    """APScheduler Task: Real-time market synchronization of Hong Kong stocks (yfinance)"""
    try:
        service = await get_hk_sync_service()
        result = await service.sync_quotes_from_source("yfinance")
        logger.info(f"✅ Hong Kong stock real-time quotes are completed simultaneously: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Hong Kong stock real-time quotation synchronization failed: {e}")
        raise


async def run_hk_status_check():
    """APScheduler Task: Check the status of Hong Kong stock data source"""
    try:
        service = await get_hk_sync_service()
        # Refresh the stock list (if cache expires)
        stock_list = service._get_hk_stock_list_from_akshare()

        # Simple status check: return stock list quantity
        result = {
            "status": "ok",
            "stock_count": len(stock_list),
            "data_sources": list(service.providers.keys()),
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"✅ Hong Kong stock status check completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Hong Kong stock status check failed: {e}")
        return {"status": "error", "error": str(e)}

