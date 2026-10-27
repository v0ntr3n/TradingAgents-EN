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

