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
from pymongo import UpdateOne

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

