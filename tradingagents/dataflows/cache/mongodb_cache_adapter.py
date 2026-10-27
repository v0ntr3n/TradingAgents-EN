#!/usr/bin/env python3
"""
MongoDB cache adapter
According to the TA_USE_APP_CACHE configuration, synchronized data in MongoDB is used first
"""

import pandas as pd
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta, timezone

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# Import configuration
from tradingagents.config.runtime_settings import use_app_cache_enabled

class MongoDBCacheAdapter:
    """MongoDB Cache adapter (reads synchronized data from the app s MongoDB)"""
    
    def __init__(self):
        self.use_app_cache = use_app_cache_enabled(False)
        self.mongodb_client = None
        self.db = None
        
        if self.use_app_cache:
            self._init_mongodb_connection()
            logger.info("🔄 MongoDB Cache Adapter Enabled - Prioritize MongoDB data")
        else:
            logger.info("📁 MongoDB Cache adapter uses legacy cache mode")
    
    def _init_mongodb_connection(self):
        """初始化MongoDB连接"""
        try:
            from tradingagents.config.database_manager import get_mongodb_client
            self.mongodb_client = get_mongodb_client()
            if self.mongodb_client:
                self.db = self.mongodb_client.get_database('tradingagents')
                logger.debug("✅ MongoDB Connection initialization successful")
            else:
                logger.warning("⚠️ MongoDB The client is unavailable and falls back to traditional mode.")
                self.use_app_cache = False
        except Exception as e:
            logger.warning(f"⚠️ MongoDB Connection initialization failed: {e}")
            self.use_app_cache = False
    
    def get_stock_basic_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtain basic stock information (query by data source priority)"""
        if not self.use_app_cache or self.db is None:
            return None

        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.stock_basic_info

            # 🔥 Get data source priority
            source_priority = self._get_data_source_priority(symbol)

            # 🔥 Query by priority
            doc = None
            for src in source_priority:
                doc = collection.find_one({"code": code6, "source": src}, {"_id": 0})
                if doc:
                    logger.debug(f"✅ 从MongoDB获取基础信息: {symbol}, 数据源: {src}")
                    return doc

            # If all data sources are not available, try querying without source conditions (compatible with old data)
            if not doc:
                doc = collection.find_one({"code": code6}, {"_id": 0})
                if doc:
                    logger.debug(f"✅ Get basic information (old data) from MongoDB: {symbol}")
                    return doc
                else:
                    logger.debug(f"📊 MongoDB No basic information found in: {symbol}")
                    return None

        except Exception as e:
            logger.warning(f"⚠️ 获取基础信息失败: {e}")
            return None
    
    def _get_data_source_priority(self, symbol: str) -> list:
        """
        Get data source priority order

        Args:
            symbol: Stock code

        Returns:
            A prioritized list of data sources, e.g.: ["tushare", "akshare", "baostock"]
        """
        try:
            # 1. Identify market segments
            from tradingagents.utils.stock_utils import StockUtils, StockMarket
            market = StockUtils.identify_stock_market(symbol)

            market_mapping = {
                StockMarket.CHINA_A: 'a_shares',
                StockMarket.US: 'us_stocks',
                StockMarket.HONG_KONG: 'hk_stocks',
            }
            market_category = market_mapping.get(market)
            logger.info(f"📊 [数据源优先级] 股票代码: {symbol}, 市场分类: {market_category}")

            # 2. Read configuration from database
            if self.db is not None:
                config_collection = self.db.system_configs
                config_data = config_collection.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )

                if config_data and config_data.get('data_source_configs'):
                    configs = config_data['data_source_configs']
                    logger.info(f"📊 [数据源优先级] 从数据库读取到 {len(configs)} 个数据源配置")

                    # 3. Filter enabled data sources
                    enabled = []
                    for ds in configs:
                        ds_type = ds.get('type', '')
                        ds_enabled = ds.get('enabled', True)
                        ds_priority = ds.get('priority', 0)
                        ds_categories = ds.get('market_categories', [])

                        logger.info(f"📊 [数据源配置] 类型: {ds_type}, 启用: {ds_enabled}, 优先级: {ds_priority}, 市场: {ds_categories}")

                        if not ds_enabled:
                            logger.info(f"⚠️ [数据源优先级] {ds_type} 未启用，跳过")
                            continue

                        # Check market classification
                        if ds_categories and market_category:
                            if market_category not in ds_categories:
                                logger.info(f"⚠️ [数据源优先级] {ds_type} 不支持市场 {market_category}，跳过")
                                continue

                        enabled.append(ds)

                    logger.info(f"📊 [数据源优先级] 过滤后启用的数据源: {len(enabled)} 个")

                    # 4. Sort by priority (larger numbers have higher priority)
                    enabled.sort(key=lambda x: x.get('priority', 0), reverse=True)

                    # 5. Returns a list of data source types
                    result = [ds.get('type', '').lower() for ds in enabled if ds.get('type')]
                    if result:
                        logger.info(f"✅ [数据源优先级] {symbol} ({market_category}): {result}")
                        return result
                    else:
                        logger.warning(f"⚠️ [Data source priority] No data source configuration available, default order used")
                else:
                    logger.warning(f"⚠️ [Data source priority] Data source configuration not found in database")

        except Exception as e:
            logger.error(f"❌ Failed to get data source priority: {e}", exc_info=True)

        # Default order:Tushare > AKShare > BaoStock
        logger.info(f"📊 [Data source priority] Use default order: ['tushare', 'akshare', 'baostock']")
        return ['tushare', 'akshare', 'baostock']

    def get_historical_data(self, symbol: str, start_date: str = None, end_date: str = None,
                          period: str = "daily") -> Optional[pd.DataFrame]:
        """
        Obtain historical data, support multiple cycles, and prioritize queries based on data freshness.

        Query strategy:
        1. Traverse all configured data sources and obtain the latest data from each data source trade_date
        2. Select the latest data source for trade_date (instead of selecting the first one with data in order of priority)
        3. Querying the complete data from this data source returns

        This ensures that new data written synchronously by JIT is used first and will not be used by high-priority data sources.
        Old data exists and is covered.

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            period: Data period (daily/weekly/monthly), default is daily

        Returns:
            DataFrame: Historical data (from data sources with the latest data)
        """
        if not self.use_app_cache or self.db is None:
            return None

        try:
            from tradingagents.utils.stock_utils import StockUtils

            code6 = str(symbol).zfill(6)
            is_fund = StockUtils.is_fund(code6)
            collection = self.db.etf_daily_quotes if is_fund else self.db.stock_daily_quotes
            symbol_field = "code" if is_fund else "symbol"

            # Get the data source priority (as a candidate list, no longer determines the return order)
            priority_order = self._get_data_source_priority(symbol)

            # Step 1: Query the latest trade_date of each data source to find the data source with the latest data
            freshest_source = None
            freshest_date = None

            for data_source in priority_order:
                latest_doc = collection.find_one(
                    {
                        symbol_field: code6,
                        **({"period": period} if not is_fund else {}),
                        "data_source": data_source,
                    },
                    {"trade_date": 1, "_id": 0},
                    sort=[("trade_date", -1)]
                )
                if latest_doc:
                    latest_date = latest_doc.get("trade_date", "")
                    logger.debug(
                        f"🔍 [MongoDB新鲜度检查] {data_source}: symbol={code6}, "
                        f"latest date={latest_date}"
                    )
                    if freshest_date is None or latest_date > freshest_date:
                        freshest_date = latest_date
                        freshest_source = data_source

            if freshest_source is None:
                # All data sources have no data
                logger.warning(
                    f"⚠️ [数据来源: MongoDB] 所有数据源({', '.join(priority_order)})"
                    f"None{period}data: {symbol}, Downgrade to other data sources"
                )
                return None

            logger.info(
                f"📅 [MongoDB新鲜度] {symbol} 最新数据来自 {freshest_source}，"
                f"latest date: {freshest_date}"
            )

            # Step 2: Query complete data from the latest data source
            query = {
                symbol_field: code6,
                "data_source": freshest_source
            }
            if not is_fund:
                query["period"] = period
            if start_date:
                query["trade_date"] = {"$gte": start_date}
            if end_date:
                if "trade_date" in query:
                    query["trade_date"]["$lte"] = end_date
                else:
                    query["trade_date"] = {"$lte": end_date}

            cursor = collection.find(query, {"_id": 0}).sort("trade_date", 1)
            data = list(cursor)

            if data:
                df = pd.DataFrame(data)
                if is_fund:
                    df["symbol"] = code6
                logger.info(
                    f"✅ [数据来源: MongoDB-{freshest_source}] {symbol}, "
                    f"{len(df)}records (period={period}, latest date={freshest_date})"
                )
                return df
            else:
                logger.warning(
                    f"⚠️ [MongoDB-{freshest_source}] No data after filtering by date range: "
                    f"{symbol} [{start_date}, {end_date}]"
                )
                return None

        except Exception as e:
            logger.warning(f"⚠️ 获取历史数据失败: {e}")
            return None
    
    def get_financial_data(self, symbol: str, report_period: str = None) -> Optional[Dict[str, Any]]:
        """Obtain financial data and query according to data source priority"""
        if not self.use_app_cache or self.db is None:
            return None

        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.stock_financial_data

            # Get data source priority
            priority_order = self._get_data_source_priority(symbol)

            # Query by priority
            for data_source in priority_order:
                # Build query conditions
                query = {
                    "code": code6,
                    "data_source": data_source  # Specify data source
                }
                if report_period:
                    query["report_period"] = report_period

                # Get the latest financial data
                doc = collection.find_one(query, {"_id": 0}, sort=[("report_period", -1)])

                if doc:
                    logger.info(f"✅ [数据来源: MongoDB-{data_source}] {symbol}财务数据")
                    logger.debug(f"📊 [financial data] successfully extracted{symbol}financial data, including fields: {list(doc.keys())}")
                    return doc

            # All data sources have no data
            logger.debug(f"📊 [Data source: MongoDB] None of the data sources have financial data: {symbol}")
            return None

        except Exception as e:
            logger.warning(f"⚠️ [Data source: MongoDB-financial data] Failed to get financial data: {e}")
            return None
    
    def get_news_data(self, symbol: str = None, hours_back: int = 24, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """获取新闻数据"""
        if not self.use_app_cache or self.db is None:
            return None

        try:
            collection = self.db.stock_news  # Correct collection name
            
            # Build query conditions
            query = {}
            if symbol:
                code6 = str(symbol).zfill(6)
                query["symbol"] = code6
            
            # time range
            if hours_back:
                start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                query["publish_time"] = {"$gte": start_time}
            
            # Query data
            cursor = collection.find(query, {"_id": 0}).sort("publish_time", -1).limit(limit)
            data = list(cursor)
            
            if data:
                logger.debug(f"✅ [数据来源: MongoDB-新闻数据] 从MongoDB获取新闻数据: {len(data)}条")
                return data
            else:
                logger.debug(f"📊 [Data source: MongoDB-news data] MongoDB News data not found in")
                return None

        except Exception as e:
            logger.warning(f"⚠️ [Data source: MongoDB-news data] Failed to obtain news data: {e}")
            return None
    
    def get_social_media_data(self, symbol: str = None, hours_back: int = 24, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """获取社媒数据"""
        if not self.use_app_cache or self.db is None:
            return None
            
        try:
            collection = self.db.social_media_messages
            
            # Build query conditions
            query = {}
            if symbol:
                code6 = str(symbol).zfill(6)
                query["symbol"] = code6
            
            # time range
            if hours_back:
                start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                query["publish_time"] = {"$gte": start_time}
            
            # Query data
            cursor = collection.find(query, {"_id": 0}).sort("publish_time", -1).limit(limit)
            data = list(cursor)
            
            if data:
                logger.debug(f"✅ 从MongoDB获取社媒数据: {len(data)}条")
                return data
            else:
                logger.debug(f"📊 MongoDB No social media data found in")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取社媒数据失败: {e}")
            return None
    
    def get_market_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情数据"""
        if not self.use_app_cache or self.db is None:
            return None
            
        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.market_quotes
            
            # Get the latest quotes
            doc = collection.find_one({"code": code6}, {"_id": 0}, sort=[("timestamp", -1)])
            
            if doc:
                logger.debug(f"✅ Get market data from MongoDB: {symbol}")
                return doc
            else:
                logger.debug(f"📊 MongoDB No market data found in: {symbol}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取行情数据失败: {e}")
            return None


# global instance
_mongodb_cache_adapter = None

def get_mongodb_cache_adapter() -> MongoDBCacheAdapter:
    """Get a MongoDB cache adapter instance"""
    global _mongodb_cache_adapter
    if _mongodb_cache_adapter is None:
        _mongodb_cache_adapter = MongoDBCacheAdapter()
    return _mongodb_cache_adapter

# Backwards compatible aliases
def get_enhanced_data_adapter() -> MongoDBCacheAdapter:
    """Get an enhanced data adapter instance (for backward compatibility, get_mongodb_cache_adapter is recommended)"""
    return get_mongodb_cache_adapter()


def get_stock_data_with_fallback(symbol: str, start_date: str = None, end_date: str = None, 
                                fallback_func=None) -> Union[pd.DataFrame, str, None]:
    """
    Stock data acquisition with downgrade
    
    Args:
        symbol: Stock code
        start_date: start date
        end_date: end date
        fallback_func: downgrade function
    
    Returns:
        MongoDB data is returned first, and the downgrade function is called when failure occurs.
    """
    adapter = get_enhanced_data_adapter()
    
    # Try to get from MongoDB
    if adapter.use_app_cache:
        df = adapter.get_historical_data(symbol, start_date, end_date)
        if df is not None and not df.empty:
            logger.info(f"📊 Using MongoDB historical data: {symbol}")
            return df
    
    # Downgrade to legacy
    if fallback_func:
        logger.info(f"🔄 降级到传统数据源: {symbol}")
        return fallback_func(symbol, start_date, end_date)
    
    return None


def get_financial_data_with_fallback(symbol: str, fallback_func=None) -> Union[Dict[str, Any], str, None]:
    """
    Financial data acquisition with downgrade
    
    Args:
        symbol: Stock code
        fallback_func: downgrade function
    
    Returns:
        MongoDB data is returned first, and the downgrade function is called when failure occurs.
    """
    adapter = get_enhanced_data_adapter()
    
    # Try to get from MongoDB
    if adapter.use_app_cache:
        data = adapter.get_financial_data(symbol)
        if data:
            logger.info(f"💰 Using MongoDB financial data: {symbol}")
            return data
    
    # Downgrade to legacy
    if fallback_func:
        logger.info(f"🔄 降级到传统数据源: {symbol}")
        return fallback_func(symbol)
    
    return None
