from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['hk_data_service', 'hk_sync_service', 'us_data_service', 'us_sync_service', 'qmt_sync_service', 'example_sdk_sync_service', 'base_market_sync', 'akshare_init_service', 'akshare_sync_service', 'tushare_init_service', 'tushare_sync_service', 'baostock_init_service', 'baostock_sync_service']:
    _sys.modules[f"app.worker.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === hk_data_service.py ===
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

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

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

    async def initialize(self):
        """Initialize data service"""
        logger.info("✅ Hong Kong stock data service initialization completed")
    
    async def get_stock_info(
        self, 
        stock_code: str, 
        source: Optional[str] = None,
        force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Obtain basic information on Hong Kong stocks (obtain on demand+cache)
        
        Args:
            stock_code: Stock code (e.g. "00700") 
            source: Data source (yfinance/akshare), None uses the default data source
            force_refresh: Whether to force refresh (ignore cache)
        
        Returns:
            Stock information dictionary, returned on failure None
        """
        try:
            # Use default data source
            if source is None:
                source = self.default_source
            
            # Standardized stock code
            normalized_code = stock_code.lstrip('0').zfill(5)
            
            # Check cache
            if not force_refresh:
                cached_info = await self._get_cached_info(normalized_code, source)
                if cached_info:
                    logger.debug(f"✅ Use cached data: {normalized_code} ({source})")
                    return cached_info
            
            # Get from data source
            provider = self.providers.get(source)
            if not provider:
                logger.error(f"❌ Unsupported data source: {source}")
                return None
            
            logger.info(f"🔄 from {source} Get Hong Kong stock information: {stock_code}")
            stock_info = provider.get_stock_info(stock_code)
            
            if not stock_info or not stock_info.get('name'):
                logger.warning(f"⚠️ Failed to obtain or the data is invalid: {stock_code} ({source})")
                return None
            
            # Normalize and save to cache
            normalized_info = self._normalize_stock_info(stock_info, source)
            normalized_info["code"] = normalized_code
            normalized_info["source"] = source
            normalized_info["updated_at"] = datetime.now()
            
            await self._save_to_cache(normalized_info)
            
            logger.info(f"✅ get success: {normalized_code} - {stock_info.get('name')} ({source})")
            return normalized_info
            
        except Exception as e:
            logger.error(f"❌ Failed to obtain Hong Kong stock information: {stock_code} ({source}): {e}")
            return None
    
    async def _get_cached_info(self, code: str, source: str) -> Optional[Dict[str, Any]]:
        """Get stock information from cache"""
        try:
            cache_expire_time = datetime.now() - timedelta(hours=self.cache_hours)
            
            cached = await self.db.stock_basic_info_hk.find_one({
                "code": code,
                "source": source,
                "updated_at": {"$gte": cache_expire_time}
            })
            
            return cached
            
        except Exception as e:
            logger.error(f"❌ Failed to read cache: {code} ({source}): {e}")
            return None
    
    async def _save_to_cache(self, stock_info: Dict[str, Any]) -> bool:
        """Save stock information to cache"""
        try:
            await self.db.stock_basic_info_hk.update_one(
                {"code": stock_info["code"], "source": stock_info["source"]},
                {"$set": stock_info},
                upsert=True
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save cache: {stock_info.get('code')} ({stock_info.get('source')}): {e}")
            return False
    
    def _normalize_stock_info(self, stock_info: Dict, source: str) -> Dict:
        """
        Standardized stock information format
        
        Args:
            stock_info: Original stock information
            source: data source
        
        Returns:
            Standardized stock information
        """
        normalized = {
            "name": stock_info.get("name", ""),
            "currency": stock_info.get("currency", "HKD"),
            "exchange": stock_info.get("exchange", "HKG"),
            "market": stock_info.get("market", "Hong Kong Exchange"),
            "area": stock_info.get("area", "Hong Kong"),
        }
        
        # optional fields
        optional_fields = [
            "industry", "sector", "list_date", "total_mv", "circ_mv",
            "pe", "pb", "ps", "pcf", "market_cap", "shares_outstanding",
            "float_shares", "employees", "website", "description"
        ]
        
        for field in optional_fields:
            if field in stock_info and stock_info[field]:
                normalized[field] = stock_info[field]
        
        return normalized


# ==================== Global instance management ====================

_hk_data_service = None


async def get_hk_data_service() -> HKDataService:
    """Obtain Hong Kong stock data service instance (single case mode)"""
    global _hk_data_service
    if _hk_data_service is None:
        _hk_data_service = HKDataService()
        await _hk_data_service.initialize()
    return _hk_data_service


# === hk_sync_service.py ===
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
try:
    from pymongo import UpdateOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

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


# === us_data_service.py ===
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
U.S. stock data service (available on demand+cache mode)

Function:
1. Obtain US stock information from data sources on demand (yfinance/finnhub)
2. Automatically cache to MongoDB to avoid repeated requests
3. Support multiple data sources: the same stock can have multiple data source records
4. Use (code, source) Union query performs upsert operation

Design description:
- Get on demand+Cache mode to avoid batch sync triggering rate limiting
- Refer to the A-share data source management method (Tushare/AKShare/BaoStock)
- Cache duration is configurable (default 24 hours)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

# Import US stock data provider
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.dataflows.providers.us.optimized import OptimizedUSDataProvider
from app.core.database import get_mongo_db
from app.core.config import settings

logger = logging.getLogger(__name__)


class USDataService:
    """U.S. stock data service (available on demand+cache mode)"""

    def __init__(self):
        self.db = get_mongo_db()
        self.settings = settings

        # Data provider mapping
        self.providers = {
            "yfinance": OptimizedUSDataProvider(),
            # More data sources can be added, such as finnhub
        }
        
        # Cache configuration
        self.cache_hours = getattr(settings, 'US_DATA_CACHE_HOURS', 24)
        self.default_source = getattr(settings, 'US_DEFAULT_DATA_SOURCE', 'yfinance')

    async def initialize(self):
        """Initialize data service"""
        logger.info("✅ US stock data service initialization completed")
    
    async def get_stock_info(
        self, 
        stock_code: str, 
        source: Optional[str] = None,
        force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Obtain basic information on U.S. stocks (obtain on demand+cache)
        
        Args:
            stock_code: Stock code (e.g. "AAPL") 
            source: Data source (yfinance/finnhub), None uses the default data source
            force_refresh: Whether to force refresh (ignore cache)
        
        Returns:
            Stock information dictionary, returned on failure None
        """
        try:
            # Use default data source
            if source is None:
                source = self.default_source
            
            # Standardized stock code (U.S. stock codes are usually capitalized)
            normalized_code = stock_code.upper()
            
            # Check cache
            if not force_refresh:
                cached_info = await self._get_cached_info(normalized_code, source)
                if cached_info:
                    logger.debug(f"✅ Use cached data: {normalized_code} ({source})")
                    return cached_info
            
            # Get from data source
            provider = self.providers.get(source)
            if not provider:
                logger.error(f"❌ Unsupported data source: {source}")
                return None
            
            logger.info(f"🔄 from {source} Get US stock information: {stock_code}")
            stock_info = provider.get_stock_info(stock_code)
            
            if not stock_info or not stock_info.get('name'):
                logger.warning(f"⚠️ Failed to obtain or the data is invalid: {stock_code} ({source})")
                return None
            
            # Normalize and save to cache
            normalized_info = self._normalize_stock_info(stock_info, source)
            normalized_info["code"] = normalized_code
            normalized_info["source"] = source
            normalized_info["updated_at"] = datetime.now()
            
            await self._save_to_cache(normalized_info)
            
            logger.info(f"✅ get success: {normalized_code} - {stock_info.get('name')} ({source})")
            return normalized_info
            
        except Exception as e:
            logger.error(f"❌ Failed to obtain US stock information: {stock_code} ({source}): {e}")
            return None
    
    async def _get_cached_info(self, code: str, source: str) -> Optional[Dict[str, Any]]:
        """Get stock information from cache"""
        try:
            cache_expire_time = datetime.now() - timedelta(hours=self.cache_hours)
            
            cached = await self.db.stock_basic_info_us.find_one({
                "code": code,
                "source": source,
                "updated_at": {"$gte": cache_expire_time}
            })
            
            return cached
            
        except Exception as e:
            logger.error(f"❌ Failed to read cache: {code} ({source}): {e}")
            return None
    
    async def _save_to_cache(self, stock_info: Dict[str, Any]) -> bool:
        """Save stock information to cache"""
        try:
            await self.db.stock_basic_info_us.update_one(
                {"code": stock_info["code"], "source": stock_info["source"]},
                {"$set": stock_info},
                upsert=True
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save cache: {stock_info.get('code')} ({stock_info.get('source')}): {e}")
            return False
    
    def _normalize_stock_info(self, stock_info: Dict, source: str) -> Dict:
        """
        Standardized stock information format
        
        Args:
            stock_info: Original stock information
            source: data source
        
        Returns:
            Standardized stock information
        """
        normalized = {
            "name": stock_info.get("name", ""),
            "currency": stock_info.get("currency", "USD"),
            "exchange": stock_info.get("exchange", "NASDAQ"),
            "market": stock_info.get("market", "US market"),
            "area": stock_info.get("area", "USA"),
        }
        
        # optional fields
        optional_fields = [
            "industry", "sector", "list_date", "total_mv", "circ_mv",
            "pe", "pb", "ps", "pcf", "market_cap", "shares_outstanding",
            "float_shares", "employees", "website", "description"
        ]
        
        for field in optional_fields:
            if field in stock_info and stock_info[field]:
                normalized[field] = stock_info[field]
        
        return normalized


# ==================== Global instance management ====================

_us_data_service = None


async def get_us_data_service() -> USDataService:
    """Obtain US stock data service instance (single case mode)"""
    global _us_data_service
    if _us_data_service is None:
        _us_data_service = USDataService()
        await _us_data_service.initialize()
    return _us_data_service


# === us_sync_service.py ===
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
U.S. stock data synchronization service (supports multiple data sources)

Function:
1. Synchronize basic information and market prices of US stocks from yfinance
2. Supports multiple data source storage: the same stock can have multiple data source records
3. Use (code, source) Union query performs upsert operation

Design description:
- Refer to A-share multi-data source synchronization service design (Tushare/AKShare/BaoStock)
- Mainly use yfinance as the data source
- Batch update operations improve performance
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
try:
    from pymongo import UpdateOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

# Import US stock data provider
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.dataflows.providers.us.yfinance import YFinanceUtils
from app.core.database import get_mongo_db
from app.core.config import settings

logger = logging.getLogger(__name__)


class USSyncService:
    """U.S. stock data synchronization service (supports multiple data sources)"""

    def __init__(self):
        self.db = get_mongo_db()
        self.settings = settings

        # data provider
        self.yfinance_provider = YFinanceUtils()

        # US stock list cache (dynamically obtained from Finnhub)
        self.us_stock_list = []
        self._stock_list_cache_time = None
        self._stock_list_cache_ttl = 3600 * 24  # Cache for 24 hours

        # Finnhub Client (lazy initialization)
        self._finnhub_client = None

    async def initialize(self):
        """Initialize synchronization service"""
        logger.info("✅ US stock synchronization service initialization completed")

    def _get_finnhub_client(self):
        """Get Finnhub client (lazy initialization)"""
        if self._finnhub_client is None:
            try:
                import finnhub
                import os

                api_key = os.getenv('FINNHUB_API_KEY')
                if not api_key:
                    logger.warning("⚠️ FINNHUB_API_KEY is not configured and the Finnhub data source cannot be used")
                    return None

                self._finnhub_client = finnhub.Client(api_key=api_key)
                logger.info("✅ Finnhub Client initialization successful")
            except Exception as e:
                logger.error(f"❌ Finnhub Client initialization failed: {e}")
                return None

        return self._finnhub_client

    def _get_us_stock_list_from_finnhub(self) -> List[str]:
        """
        Get a list of all US stocks from Finnhub

        Returns:
            List[str]: US stock code list
        """
        try:
            from datetime import datetime, timedelta

            # Check if cache is valid
            if (self.us_stock_list and self._stock_list_cache_time and
                datetime.now() - self._stock_list_cache_time < timedelta(seconds=self._stock_list_cache_ttl)):
                logger.debug(f"📦 Use cached US stock list: {len(self.us_stock_list)} only")
                return self.us_stock_list

            logger.info("🔄 Get a list of US stocks from Finnhub...")

            # Get Finnhub client
            client = self._get_finnhub_client()
            if not client:
                logger.warning("⚠️ Finnhub Client unavailable, use backup list")
                return self._get_fallback_stock_list()

            # Get the list of US stocks (US exchange)
            symbols = client.stock_symbols('US')

            if not symbols:
                logger.warning("⚠️ Finnhub Return empty data, use fallback list")
                return self._get_fallback_stock_list()

            # Extract a list of stock symbols (only keep common stocks, filter out ETFs, funds, etc.)
            stock_codes = []
            for symbol_info in symbols:
                symbol = symbol_info.get('symbol', '')
                symbol_type = symbol_info.get('type', '')

                # Only keep common stocks (Common Stock)
                if symbol and symbol_type == 'Common Stock':
                    stock_codes.append(symbol)

            logger.info(f"✅ successfully obtained {len(stock_codes)} Only U.S. stocks (common stocks)")

            # Update cache
            self.us_stock_list = stock_codes
            self._stock_list_cache_time = datetime.now()

            return stock_codes

        except Exception as e:
            logger.error(f"❌ Failed to obtain US stock list from Finnhub: {e}")
            logger.info("📋 Use alternate US stock list")
            return self._get_fallback_stock_list()

    def _get_fallback_stock_list(self) -> List[str]:
        """
        Get the list of backup US stocks (main US stock targets)

        Returns:
            List[str]: US stock code list
        """
        return [
            # tech giants
            "AAPL",   # apple
            "MSFT",   # Microsoft
            "GOOGL",  # Google
            "AMZN",   # Amazon
            "META",   # Meta
            "TSLA",   # Tesla
            "NVDA",   # NVIDIA
            "AMD",    # AMD
            "INTC",   # Intel
            "NFLX",   # Netflix
            # Finance
            "JPM",    # JPMorgan Chase
            "BAC",    # Bank of America
            "WFC",    # Wells Fargo
            "GS",     # Goldman Sachs
            "MS",     # Morgan Stanley
            # consumption
            "KO",     # coca cola
            "PEP",    # Pepsi
            "WMT",    # Walmart
            "HD",     # home depot
            "MCD",    # McDonald's
            # medical
            "JNJ",    # Johnson & Johnson
            "PFE",    # Pfizer
            "UNH",    # UnitedHealth
            "ABBV",   # AbbVie
            # energy
            "XOM",    # Exxon Mobil
            "CVX",    # Chevron
        ]

    async def sync_basic_info_from_source(
        self,
        source: str = "yfinance",
        force_update: bool = False
    ) -> Dict[str, int]:
        """
        Synchronize basic U.S. stock information from specified data source

        Args:
            source: Data source name (Default yfinance)
            force_update: Whether to force update (forcibly refresh the stock list)

        Returns:
            Dict: Sync statistics {updated: int, inserted: int, failed: int}
        """
        if source != "yfinance":
            logger.error(f"❌ Unsupported data source: {source}")
            return {"updated": 0, "inserted": 0, "failed": 0}

        # If update is forced, clear cache
        if force_update:
            self._stock_list_cache_time = None
            logger.info("🔄 Force refresh of US stock list")

        # Get US stock list (from Finnhub or cache)
        stock_list = self._get_us_stock_list_from_finnhub()

        if not stock_list:
            logger.error("❌ Unable to obtain US stock list")
            return {"updated": 0, "inserted": 0, "failed": 0}

        logger.info(f"🇺🇸 Start synchronizing basic information of US stocks (data source: {source})")
        logger.info(f"📊 Number of stocks to be synchronized: {len(stock_list)}")

        operations = []
        failed_count = 0

        for stock_code in stock_list:
            try:
                # Get data from yfinance
                stock_info = self.yfinance_provider.get_stock_info(stock_code)
                
                if not stock_info or not stock_info.get('shortName'):
                    logger.warning(f"⚠️ Skip invalid data: {stock_code}")
                    failed_count += 1
                    continue
                
                # standardized data format
                normalized_info = self._normalize_stock_info(stock_info, source)
                normalized_info["code"] = stock_code.upper()
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
                
                logger.debug(f"✅ Prepare to sync: {stock_code} ({stock_info.get('shortName')}) from {source}")
                
            except Exception as e:
                logger.error(f"❌ Sync failed: {stock_code} from {source}: {e}")
                failed_count += 1
        
        # Perform batch operations
        result = {"updated": 0, "inserted": 0, "failed": failed_count}
        
        if operations:
            try:
                bulk_result = await self.db.stock_basic_info_us.bulk_write(operations)
                result["updated"] = bulk_result.modified_count
                result["inserted"] = bulk_result.upserted_count
                
                logger.info(
                    f"✅ Basic information on U.S. stocks is completed simultaneously ({source}): "
                    f"update {result['updated']} Article, "
                    f"Insert {result['inserted']} Article, "
                    f"failed {result['failed']} Article"
                )
            except Exception as e:
                logger.error(f"❌ Batch write failed: {e}")
                result["failed"] += len(operations)
        
        return result
    
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
            "name": stock_info.get("shortName", ""),
            "name_en": stock_info.get("longName", stock_info.get("shortName", "")),
            "currency": stock_info.get("currency", "USD"),
            "exchange": stock_info.get("exchange", "NASDAQ"),
            "market": stock_info.get("exchange", "NASDAQ"),
            "area": stock_info.get("country", "US"),
        }
        
        # optional fields
        if "marketCap" in stock_info and stock_info["marketCap"]:
            # Convert to billions of dollars
            normalized["total_mv"] = stock_info["marketCap"] / 100000000
        
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
        Synchronize real-time quotes of U.S. stocks from designated data sources
        
        Args:
            source: Data source name (Default yfinance)
        
        Returns:
            Dict: Sync statistics
        """
        if source != "yfinance":
            logger.error(f"❌ Unsupported data source: {source}")
            return {"updated": 0, "inserted": 0, "failed": 0}
        
        logger.info(f"🇺🇸 Start synchronizing real-time quotes of US stocks (data source: {source})")
        
        operations = []
        failed_count = 0
        
        for stock_code in self.us_stock_list:
            try:
                # Get the data of the last 1 day as real-time market price
                import yfinance as yf
                ticker = yf.Ticker(stock_code)
                data = ticker.history(period="1d")
                
                if data.empty:
                    logger.warning(f"⚠️ Skip invalid quotes: {stock_code}")
                    failed_count += 1
                    continue
                
                latest = data.iloc[-1]
                
                # Standardized market data
                normalized_quote = {
                    "code": stock_code.upper(),
                    "close": float(latest['Close']),
                    "open": float(latest['Open']),
                    "high": float(latest['High']),
                    "low": float(latest['Low']),
                    "volume": int(latest['Volume']),
                    "currency": "USD",
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
                
                logger.debug(f"✅ Prepare to sync the market: {stock_code} (price: {normalized_quote['close']} USD)")
                
            except Exception as e:
                logger.error(f"❌ Synchronized market failure: {stock_code}: {e}")
                failed_count += 1
        
        # Perform batch operations
        result = {"updated": 0, "inserted": 0, "failed": failed_count}
        
        if operations:
            try:
                bulk_result = await self.db.market_quotes_us.bulk_write(operations)
                result["updated"] = bulk_result.modified_count
                result["inserted"] = bulk_result.upserted_count
                
                logger.info(
                    f"✅ U.S. stock market trends completed simultaneously: "
                    f"update {result['updated']} Article, "
                    f"Insert {result['inserted']} Article, "
                    f"failed {result['failed']} Article"
                )
            except Exception as e:
                logger.error(f"❌ Batch write failed: {e}")
                result["failed"] += len(operations)
        
        return result


# ==================== Global service instance ====================

_us_sync_service = None

async def get_us_sync_service() -> USSyncService:
    """Get an example of US stock synchronization service"""
    global _us_sync_service
    if _us_sync_service is None:
        _us_sync_service = USSyncService()
        await _us_sync_service.initialize()
    return _us_sync_service


# ==================== APScheduler Compatible task functions ====================

async def run_us_yfinance_basic_info_sync(force_update: bool = False):
    """APScheduler Task: Synchronization of basic information on U.S. stocks (yfinance)"""
    try:
        service = await get_us_sync_service()
        result = await service.sync_basic_info_from_source("yfinance", force_update)
        logger.info(f"✅ Basic information on U.S. stocks is completed simultaneously (yfinance): {result}")
        return result
    except Exception as e:
        logger.error(f"❌ U.S. stock basic information synchronization failed (yfinance): {e}")
        raise


async def run_us_yfinance_quotes_sync():
    """APScheduler Task: Real-time market synchronization of U.S. stocks (yfinance)"""
    try:
        service = await get_us_sync_service()
        result = await service.sync_quotes_from_source("yfinance")
        logger.info(f"✅ U.S. stock real-time quotes are synchronized: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ U.S. stock real-time quotation synchronization failed: {e}")
        raise


async def run_us_status_check():
    """APScheduler Task: Check the status of US stock data source"""
    try:
        service = await get_us_sync_service()
        # Refresh the stock list (if cache expires)
        stock_list = service._get_us_stock_list_from_finnhub()

        # Simple status check: return stock list quantity
        result = {
            "status": "ok",
            "stock_count": len(stock_list),
            "data_source": "yfinance + finnhub",
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"✅ US stock status check completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ US stock status check failed: {e}")
        return {"status": "error", "error": str(e)}


# === qmt_sync_service.py ===
"""
QMT Data synchronization service

Sync QMT data to MongoDB.
Prerequisites:
  1. xtquant Library installed
  2. QMT Client started (Windows only)
  3. Obtaining market data does not require logging into a brokerage account
News is not supported, use AKShare uniformly.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd

from app.core.database import get_mongo_db
from app.core.config import settings
from app.services.historical_data_service import get_historical_data_service
from app.services.financial_data_service import get_financial_data_service
from app.services.data_sources.qmt_adapter import QMTAdapter

logger = logging.getLogger(__name__)

_qmt_sync_service = None


class QMTSyncService:
    """
    QMT Data synchronization service

    Provided by:
    - Synchronization of basic stock information
    - Real-time market synchronization (optional)
    """

    def __init__(self):
        self.adapter = QMTAdapter()
        self.db = None
        self.historical_service = None
        self.financial_service = None
        self.batch_size = 200
        self._current_job_id = None

    async def initialize(self):
        """Initialize synchronization service"""
        try:
            self.db = get_mongo_db()
            self.historical_service = await get_historical_data_service()
            self.financial_service = await get_financial_data_service()
            if not self.adapter.is_available():
                raise RuntimeError("❌ QMT Not available, please make sure the QMT client is started")
            logger.info("✅ QMT Synchronization service initialization completed")
        except Exception as e:
            logger.error(f"❌ QMT Sync service initialization failed: {e}")
            raise

    async def _get_qmt_symbols(self, symbols: Optional[List[str]] = None) -> List[str]:
        if symbols:
            return [str(symbol).zfill(6) for symbol in symbols if str(symbol).strip()]

        db_symbols = []
        cursor = self.db.stock_basic_info.find({"source": "qmt"}, {"code": 1})
        async for doc in cursor:
            code = str(doc.get("code", "")).zfill(6)
            if len(code) == 6:
                db_symbols.append(code)

        if db_symbols:
            return db_symbols

        df = self.adapter.get_stock_list()
        if df is None or df.empty:
            return []

        return [str(code).zfill(6) for code in df["symbol"].tolist() if str(code).strip()]

    def _normalize_period(self, period: str) -> str:
        period_map = {
            "daily": "day",
            "weekly": "week",
            "monthly": "month",
            "day": "day",
            "week": "week",
            "month": "month",
        }
        return period_map.get(period, period)

    def _normalize_financial_period(self, value: Any, fallback_index: Any = None) -> str:
        if value is None or value == "":
            value = fallback_index
        if value is None or value == "":
            return datetime.utcnow().strftime("%Y%m%d")
        try:
            parsed = pd.to_datetime(value)
            return parsed.strftime("%Y%m%d")
        except Exception:
            text = str(value).strip().replace("-", "").replace("/", "")
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) >= 8:
                return digits[:8]
            return datetime.utcnow().strftime("%Y%m%d")

    def _build_financial_payloads(self, symbol: str, financial_tables: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        grouped_payloads: Dict[str, Dict[str, Any]] = {}
        period_fields = [
            "report_period", "report_time", "m_timetag", "endDate", "end_date",
            "REPORT_PERIOD", "REPORT_TIME", "publish_date", "announce_time", "ann_date"
        ]

        for table_name, frame in financial_tables.items():
            if frame is None or frame.empty:
                continue

            normalized_frame = frame.copy()
            for index_value, row in normalized_frame.iterrows():
                row_dict = {}
                for key, value in row.items():
                    if hasattr(value, "item"):
                        try:
                            value = value.item()
                        except Exception:
                            pass
                    if pd.isna(value):
                        continue
                    row_dict[str(key)] = value

                period_value = None
                for field_name in period_fields:
                    if field_name in row_dict and row_dict[field_name] not in (None, ""):
                        period_value = row_dict[field_name]
                        break
                report_period = self._normalize_financial_period(period_value, index_value)

                payload = grouped_payloads.setdefault(
                    report_period,
                    {
                        "symbol": symbol,
                        "report_period": report_period,
                        "report_type": "annual" if report_period.endswith("1231") else "quarterly",
                        "tables": [],
                    },
                )
                payload[table_name] = row_dict
                payload["tables"].append(table_name)

        return list(grouped_payloads.values())

    async def sync_stock_basic_info(
        self,
        force_update: bool = False,
        job_id: str = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize basic stock information to MongoDB

        Args:
            force_update: Whether to force update
            job_id: Task ID (for progress tracking)
            symbols: Optional, synchronizes only the specified stock list; if empty, synchronizes the entire market

        Returns:
            Synchronization result statistics
        """
        self._current_job_id = job_id or "qmt_basic_info_sync"
        logger.info("🔄 Start QMT stock basic information synchronization...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": [],
        }

        try:
            df = self.adapter.get_stock_list()
            if df is None or df.empty:
                logger.warning("⚠️ QMT No stock list obtained")
                return stats

            if symbols:
                symbol_set = {str(s).zfill(6) for s in symbols}
                df = df[df["symbol"].astype(str).str.zfill(6).isin(symbol_set)]
                if df.empty:
                    logger.warning(f"⚠️ QMT Specified stock not found: {symbols}")
                    return stats

            stats["total_processed"] = len(df)

            for i in range(0, len(df), self.batch_size):
                batch = df.iloc[i : i + self.batch_size]
                for _, row in batch.iterrows():
                    try:
                        code = str(row.get("symbol", "")).zfill(6)
                        if not code or len(code) != 6:
                            continue

                        if not force_update:
                            existing = await self.db.stock_basic_info.find_one({"code": code, "source": "qmt"})
                            if existing:
                                stats["skipped_count"] += 1
                                continue

                        doc = {
                            "code": code,
                            "symbol": code,
                            "name": row.get("name") or code,
                            "ts_code": row.get("ts_code", ""),
                            "source": "qmt",
                            "market": row.get("market", ""),
                            "area": row.get("area", ""),
                            "industry": row.get("industry", ""),
                            "list_date": row.get("list_date", ""),
                            "updated_at": datetime.utcnow(),
                        }

                        await self.db.stock_basic_info.update_one(
                            {"code": code, "source": "qmt"},
                            {"$set": doc},
                            upsert=True,
                        )
                        stats["success_count"] += 1
                    except Exception as e:
                        stats["error_count"] += 1
                        stats["errors"].append({"code": code, "error": str(e)})

                if i + self.batch_size < len(df):
                    await asyncio.sleep(0.1)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ QMT Basic stock information synchronization completed: success {stats['success_count']}, skip {stats['skipped_count']}, Error {stats['error_count']}")

            return stats
        except Exception as e:
            logger.error(f"❌ QMT Synchronization of basic stock information failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_stock_basic_info"})
            return stats

    async def sync_realtime_quotes(self, symbols: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
        """
        Synchronize real-time quotes to market_quotes (optional, requires QMT to run)

        Args:
            symbols: Specify a list of stocks, short will mean the entire market
            force: Whether to enforce

        Returns:
            Synchronization results
        """
        if not self.adapter.is_available():
            logger.warning("⚠️ QMT Not available, skip real-time market synchronization")
            return {"success_count": 0, "message": "QMT Not available"}

        try:
            quotes = self.adapter.get_realtime_quotes()
            if not quotes:
                return {"success_count": 0, "message": "Not getting quotes"}

            if symbols:
                quotes = {k: v for k, v in quotes.items() if k in symbols}

            if not quotes:
                return {"success_count": 0, "message": "No matching data"}

            count = 0
            now = datetime.utcnow()
            for code, q in quotes.items():
                try:
                    doc = {
                        "code": code,
                        "symbol": code,
                        "close": q.get("close"),
                        "pct_chg": q.get("pct_chg"),
                        "amount": q.get("amount"),
                        "source": "qmt",
                        "updated_at": now,
                    }
                    await self.db.market_quotes.update_one(
                        {"code": code},
                        {"$set": doc},
                        upsert=True,
                    )
                    count += 1
                except Exception as e:
                    logger.debug(f"QMT Quotation update failed {code}: {e}")

            return {"success_count": count, "total": len(quotes), "message": f"sync {count} only"}
        except Exception as e:
            logger.error(f"QMT Real-time market synchronization failed: {e}")
            return {"success_count": 0, "error": str(e)}

    async def sync_historical_data(
        self,
        days: int = 365,
        batch_size: int = 100,
        period: str = "daily",
        incremental: bool = True,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._current_job_id = self._current_job_id or "qmt_historical_sync"
        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "historical_records": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": [],
        }

        try:
            symbol_list = await self._get_qmt_symbols(symbols)
            if not symbol_list:
                logger.warning("⚠️ QMT Historical synchronization did not obtain the stock list")
                return stats

            stats["total_processed"] = len(symbol_list)
            normalized_period = self._normalize_period(period)
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=max(days, 1))

            for index in range(0, len(symbol_list), batch_size):
                batch = symbol_list[index:index + batch_size]
                for symbol in batch:
                    try:
                        limit = max(days + 5, 30)
                        records = self.adapter.get_kline(symbol, period=normalized_period, limit=limit)
                        if not records:
                            stats["skipped_count"] += 1
                            continue

                        df = pd.DataFrame(records)
                        if df.empty:
                            stats["skipped_count"] += 1
                            continue

                        date_column = "date" if "date" in df.columns else "time" if "time" in df.columns else None
                        if date_column:
                            parsed_dates = pd.to_datetime(df[date_column], errors="coerce")
                            df = df.assign(date=parsed_dates.dt.strftime("%Y-%m-%d"))
                            df = df[parsed_dates.notna()]
                            if incremental:
                                df = df[(parsed_dates.dt.date >= start_date) & (parsed_dates.dt.date <= end_date)]

                        if df.empty:
                            stats["skipped_count"] += 1
                            continue

                        if "pre_close" not in df.columns and "close" in df.columns:
                            df["pre_close"] = pd.to_numeric(df["close"], errors="coerce").shift(1)

                        saved_count = await self.historical_service.save_historical_data(
                            symbol=symbol,
                            data=df,
                            data_source="qmt",
                            market="CN",
                            period=period,
                            overwrite=True,
                        )
                        if saved_count > 0:
                            stats["success_count"] += 1
                            stats["historical_records"] += saved_count
                        else:
                            stats["skipped_count"] += 1
                    except Exception as e:
                        stats["error_count"] += 1
                        stats["errors"].append({"symbol": symbol, "error": str(e), "context": "sync_historical_data"})

                if index + batch_size < len(symbol_list):
                    await asyncio.sleep(0.1)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            return stats
        except Exception as e:
            logger.error(f"❌ QMT Historical data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_historical_data"})
            return stats

    async def sync_financial_data(
        self,
        symbols: Optional[List[str]] = None,
        batch_size: int = 50,
        start_time: str = "",
        end_time: str = "",
    ) -> Dict[str, Any]:
        self._current_job_id = self._current_job_id or "qmt_financial_sync"
        stats = {
            "total_symbols": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "saved_records": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": [],
        }

        try:
            symbol_list = await self._get_qmt_symbols(symbols)
            if not symbol_list:
                logger.warning("⚠️ QMT Financial synchronization did not obtain the stock list")
                return stats

            stats["total_symbols"] = len(symbol_list)
            for index in range(0, len(symbol_list), batch_size):
                batch = symbol_list[index:index + batch_size]
                for symbol in batch:
                    try:
                        financial_tables = self.adapter.get_financial_data(
                            symbol,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        if not financial_tables:
                            stats["skipped_count"] += 1
                            continue

                        payloads = self._build_financial_payloads(symbol, financial_tables)
                        if not payloads:
                            stats["skipped_count"] += 1
                            continue

                        saved_for_symbol = 0
                        for payload in payloads:
                            saved_for_symbol += await self.financial_service.save_financial_data(
                                symbol=symbol,
                                financial_data=payload,
                                data_source="qmt",
                                market="CN",
                                report_period=payload.get("report_period"),
                                report_type=payload.get("report_type", "quarterly"),
                            )

                        if saved_for_symbol > 0:
                            stats["success_count"] += 1
                            stats["saved_records"] += saved_for_symbol
                        else:
                            stats["skipped_count"] += 1
                    except Exception as e:
                        stats["error_count"] += 1
                        stats["errors"].append({"symbol": symbol, "error": str(e), "context": "sync_financial_data"})

                if index + batch_size < len(symbol_list):
                    await asyncio.sleep(0.1)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            return stats
        except Exception as e:
            logger.error(f"❌ QMT Financial data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_financial_data"})
            return stats


async def _check_task_running(job_id: str) -> tuple[bool, Optional[str]]:
    try:
        from pymongo import MongoClient
        from app.services.scheduler_service import get_utc8_now

        sync_client = MongoClient(settings.MONGO_URI)
        sync_db = sync_client[settings.MONGODB_DATABASE]
        threshold_time = get_utc8_now() - timedelta(minutes=30)

        running_instance = sync_db.scheduler_executions.find_one(
            {
                "job_id": job_id,
                "status": "running",
                "timestamp": {"$gte": threshold_time},
            },
            sort=[("timestamp", -1)],
        )

        if running_instance:
            instance_id = str(running_instance.get("_id"))
            sync_client.close()
            return True, instance_id

        sync_client.close()
        return False, None
    except Exception as e:
        logger.warning(f"⚠️ Checking QMT task running status failed {job_id}: {e}")
        return False, None


async def get_qmt_sync_service() -> QMTSyncService:
    """Get the QMT synchronization service singleton"""
    global _qmt_sync_service
    if _qmt_sync_service is None:
        _qmt_sync_service = QMTSyncService()
        await _qmt_sync_service.initialize()
    return _qmt_sync_service


async def run_qmt_basic_info_sync(force_update: bool = False, job_id: str = None) -> Dict[str, Any]:
    """Run QMT stock basic information synchronization"""
    service = await get_qmt_sync_service()
    return await service.sync_stock_basic_info(force_update=force_update, job_id=job_id)


async def run_qmt_quotes_sync(symbols: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
    """Run QMT real-time market synchronization"""
    service = await get_qmt_sync_service()
    return await service.sync_realtime_quotes(symbols=symbols, force=force)


async def run_qmt_historical_sync(incremental: bool = True, **kwargs) -> Dict[str, Any]:
    job_id = "qmt_historical_sync"
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    if not manual_trigger and not force_execute:
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {"skipped": True, "reason": "There is already an instance running", "running_instance_id": instance_id}

    service = await get_qmt_sync_service()
    service._current_job_id = job_id
    return await service.sync_historical_data(
        days=kwargs.get("days", settings.QMT_HISTORICAL_SYNC_DAYS),
        batch_size=kwargs.get("batch_size", settings.QMT_HISTORICAL_BATCH_SIZE),
        period=kwargs.get("period", "daily"),
        incremental=incremental,
        symbols=kwargs.get("symbols"),
    )


async def run_qmt_financial_sync(**kwargs) -> Dict[str, Any]:
    job_id = "qmt_financial_sync"
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    if not manual_trigger and not force_execute:
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {"skipped": True, "reason": "There is already an instance running", "running_instance_id": instance_id}

    service = await get_qmt_sync_service()
    service._current_job_id = job_id
    return await service.sync_financial_data(
        symbols=kwargs.get("symbols"),
        batch_size=kwargs.get("batch_size", settings.QMT_FINANCIAL_BATCH_SIZE),
        start_time=kwargs.get("start_time", ""),
        end_time=kwargs.get("end_time", ""),
    )


async def run_qmt_status_check() -> Dict[str, Any]:
    """Check QMT availability status"""
    adapter = QMTAdapter()
    available = adapter.is_available()
    latest_trade_date = adapter.find_latest_trade_date() if available else None
    result = {
        "available": available,
        "latest_trade_date": latest_trade_date,
        "checked_at": datetime.utcnow().isoformat(),
        "source": "qmt",
    }
    logger.info(f"QMT Status check results: {result}")
    return result

# === example_sdk_sync_service.py ===
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


# === US-Focused Compatibility Shims for Removed CN Sync Workers ===
AKShareSyncService = USSyncService
TushareSyncService = USSyncService
BaoStockSyncService = USSyncService

async def get_akshare_sync_service():
    return get_us_sync_service()

async def get_tushare_sync_service():
    return get_us_sync_service()

async def get_baostock_sync_service():
    return get_us_sync_service()

async def _check_task_running(*args, **kwargs):
    return False

async def run_akshare_basic_info_sync(*args, **kwargs): pass
async def run_akshare_financial_sync(*args, **kwargs): pass
async def run_akshare_historical_sync(*args, **kwargs): pass
async def run_akshare_quotes_sync(*args, **kwargs): pass
async def run_akshare_status_check(*args, **kwargs): pass
async def run_baostock_basic_info_sync(*args, **kwargs): pass
async def run_baostock_daily_quotes_sync(*args, **kwargs): pass
async def run_baostock_historical_sync(*args, **kwargs): pass
async def run_baostock_status_check(*args, **kwargs): pass
async def run_tushare_basic_info_sync(*args, **kwargs): pass
async def run_tushare_financial_sync(*args, **kwargs): pass
async def run_tushare_historical_sync(*args, **kwargs): pass
async def run_tushare_realtime_quotes_hourly(*args, **kwargs): pass
async def run_tushare_status_check(*args, **kwargs): pass
