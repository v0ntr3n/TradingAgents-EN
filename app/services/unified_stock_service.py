#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified stock data service (cross-market, supports multiple data sources)

Function:
1. Cross-market data access (A shares/Hong Kong stocks/US stocks)
2. Multiple data source priority query
3. Unified query interface

Design description:
- Reference A-share multi-data source design
- The same stock can have multiple data source records
- Pass (code, source) Union query
- Data source priority is read from database configuration
"""

import logging
from typing import Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("webapi")


class UnifiedStockService:
    """Unified stock data service (cross-market, supports multiple data sources)"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Collection mapping
        self.collection_map = {
            "CN": {
                "basic_info": "stock_basic_info",
                "quotes": "market_quotes",
                "daily": "stock_daily_quotes",
                "financial": "stock_financial_data",
                "news": "stock_news"
            },
            "HK": {
                "basic_info": "stock_basic_info_hk",
                "quotes": "market_quotes_hk",
                "daily": "stock_daily_quotes_hk",
                "financial": "stock_financial_data_hk",
                "news": "stock_news_hk"
            },
            "US": {
                "basic_info": "stock_basic_info_us",
                "quotes": "market_quotes_us",
                "daily": "stock_daily_quotes_us",
                "financial": "stock_financial_data_us",
                "news": "stock_news_us"
            },
            "ETF": {
                "basic_info": "etf_basic_info",
                "quotes": "market_quotes",  # ETF Share real-time quotes with A-shares
                "daily": "etf_daily_quotes",
                "financial": None,  # ETF None PE/PB/ROE
                "news": "stock_news"
            }
        }

    async def get_stock_info(
        self, 
        market: str, 
        code: str, 
        source: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Obtain basic stock information (supports multiple data sources)
        
        Args:
            market: market type (CN/HK/US)
            code: Stock code
            source: Specify data source (optional)
        
        Returns:
            Dictionary of basic stock information
        """
        collection_name = self.collection_map[market]["basic_info"]
        collection = self.db[collection_name]
        
        if source:
            # Specify data source
            query = {"code": code, "source": source}
            doc = await collection.find_one(query, {"_id": 0})
            if doc:
                logger.debug(f"✅ 使用指定数据源: {source}")
        else:
            # 🔥 Query by priority (refer to A-share design)
            source_priority = await self._get_source_priority(market)
            doc = None
            
            for src in source_priority:
                query = {"code": code, "source": src}
                doc = await collection.find_one(query, {"_id": 0})
                if doc:
                    logger.debug(f"✅ 使用数据源: {src} (优先级查询)")
                    break
            
            # If not found, try query without specifying source (compatible with old data)
            if not doc:
                doc = await collection.find_one({"code": code}, {"_id": 0})
                if doc:
                    logger.debug(f"✅ Use default data source (compatibility mode)")
        
        return doc

    async def _get_source_priority(self, market: str) -> List[str]:
        """
        Get data source priority from database
        
        Args:
            market: market type (CN/HK/US/ETF)
        
        Returns:
            Data source priority list
        """
        if market == "ETF":
            return ["akshare"]

        market_category_map = {
            "CN": "a_shares",
            "HK": "hk_stocks",
            "US": "us_stocks"
        }

        market_category_id = market_category_map.get(market)
        
        try:
            # Query from datasource_groupings collection
            groupings = await self.db.datasource_groupings.find({
                "market_category_id": market_category_id,
                "enabled": True
            }).sort("priority", -1).to_list(length=None)
            
            if groupings:
                priority_list = [g["data_source_name"] for g in groupings]
                logger.debug(f"📊 {market} Data source priority (from database): {priority_list}")
                return priority_list
        except Exception as e:
            logger.warning(f"⚠️ Failed to read data source priority from database: {e}")
        
        # Default priority
        default_priority = {
            "CN": ["tushare", "akshare", "baostock"],
            "HK": ["yfinance_hk", "akshare_hk"],
            "US": ["yfinance_us"]
        }
        priority_list = default_priority.get(market, [])
        logger.debug(f"📊 {market} 数据源优先级（默认）: {priority_list}")
        return priority_list

    async def get_stock_quote(self, market: str, code: str) -> Optional[Dict]:
        """
        Get real-time quotes
        
        Args:
            market: market type (CN/HK/US)
            code: Stock code
        
        Returns:
            Real-time Quote Dictionary
        """
        collection_name = self.collection_map[market]["quotes"]
        collection = self.db[collection_name]
        return await collection.find_one({"code": code}, {"_id": 0})

    async def search_stocks(
        self, 
        market: str, 
        query: str, 
        limit: int = 20
    ) -> List[Dict]:
        """
        Search for stocks (remove duplication, only return the optimal data source for each stock)
        
        Args:
            market: market type (CN/HK/US)
            query: Search keywords
            limit: Return quantity limit
        
        Returns:
            stock list
        """
        collection_name = self.collection_map[market]["basic_info"]
        collection = self.db[collection_name]

        # Supports code and name search
        filter_query = {
            "$or": [
                {"code": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
                {"name_en": {"$regex": query, "$options": "i"}}
            ]
        }

        # Query all matching records
        cursor = collection.find(filter_query)
        all_results = await cursor.to_list(length=None)
        
        if not all_results:
            return []
        
        # Grouped by code, each code only retains the highest priority data source
        source_priority = await self._get_source_priority(market)
        unique_results = {}
        
        for doc in all_results:
            code = doc.get("code")
            source = doc.get("source")
            
            if code not in unique_results:
                unique_results[code] = doc
            else:
                # Compare priorities
                current_source = unique_results[code].get("source")
                try:
                    if source in source_priority and current_source in source_priority:
                        if source_priority.index(source) < source_priority.index(current_source):
                            unique_results[code] = doc
                except ValueError:
                    # If the source is not in the priority list, keep the current record
                    pass
        
        # Return to the previous limit bar
        result_list = list(unique_results.values())[:limit]
        logger.info(f"🔍 搜索 {market} 市场: '{query}' -> {len(result_list)} 条结果（已去重）")
        return result_list

    async def get_daily_quotes(
        self,
        market: str,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get historical K-line data
        
        Args:
            market: market type (CN/HK/US)
            code: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            limit: Return quantity limit
        
        Returns:
            K Line data list
        """
        collection_name = self.collection_map[market]["daily"]
        collection = self.db[collection_name]
        
        query = {"code": code}
        if start_date or end_date:
            query["trade_date"] = {}
            if start_date:
                query["trade_date"]["$gte"] = start_date
            if end_date:
                query["trade_date"]["$lte"] = end_date
        
        cursor = collection.find(query, {"_id": 0}).sort("trade_date", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_supported_markets(self) -> List[Dict]:
        """
        Get a list of supported markets
        
        Returns:
            Market list
        """
        return [
            {
                "code": "CN",
                "name": "A股",
                "name_en": "China A-Share",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            },
            {
                "code": "HK",
                "name": "港股",
                "name_en": "Hong Kong Stock",
                "currency": "HKD",
                "timezone": "Asia/Hong_Kong"
            },
            {
                "code": "US",
                "name": "美股",
                "name_en": "US Stock",
                "currency": "USD",
                "timezone": "America/New_York"
            }
        ]

