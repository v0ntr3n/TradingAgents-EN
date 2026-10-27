#!/usr/bin/env python3
"""
Data source manager
Unified management of the selection and switching of Chinese stock data sources, supporting Tushare, AKShare, BaoStock, etc.
"""

import os
import time
from typing import Dict, List, Optional, Any
from enum import Enum
import warnings
import pandas as pd
import numpy as np

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')
warnings.filterwarnings('ignore')

# Import unified log system
from tradingagents.utils.logging_init import setup_dataflow_logging
logger = setup_dataflow_logging()

# Import unified data source encoding
from tradingagents.constants import DataSourceCode


class ChinaDataSource(Enum):
    """
    China stock data source enumeration

    NOTE: This enum is kept in sync with tradingagents.constants.DataSourceCode
    Values use unified data source encoding
    """
    MONGODB = DataSourceCode.MONGODB  # MongoDB Database cache (highest priority)
    LOCAL = "local"  # Local data imported by users
    TUSHARE = DataSourceCode.TUSHARE
    AKSHARE = DataSourceCode.AKSHARE
    BAOSTOCK = DataSourceCode.BAOSTOCK


class USDataSource(Enum):
    """
    U.S. stock data source enumeration

    NOTE: This enum is kept in sync with tradingagents.constants.DataSourceCode
    Values use unified data source encoding
    """
    MONGODB = DataSourceCode.MONGODB  # MongoDB Database cache (highest priority)
    YFINANCE = DataSourceCode.YFINANCE  # Yahoo Finance (Free, stock prices and technical indicators)
    ALPHA_VANTAGE = DataSourceCode.ALPHA_VANTAGE  # Alpha Vantage (fundamentals and news)
    FINNHUB = DataSourceCode.FINNHUB  # Finnhub (Alternate data source)





class DataSourceManager:
    """数据源管理器"""

    @staticmethod
    def _normalize_stock_data_result(result: Any) -> tuple[str, Optional[str]]:
        """Compatible history return `(result, source)` The branches uniformly converge to string results."""
        actual_source = None
        normalized_result = result

        if isinstance(result, tuple):
            normalized_result = result[0] if result else ""
            if len(result) > 1 and isinstance(result[1], str):
                actual_source = result[1]

        if normalized_result is None:
            normalized_result = ""
        elif not isinstance(normalized_result, str):
            normalized_result = str(normalized_result)

        return normalized_result, actual_source

    def __init__(self):
        """初始化数据源管理器"""
        # Check if MongoDB caching is enabled
        self.use_mongodb_cache = self._check_mongodb_enabled()

        self.default_source = self._get_default_source()
        self.available_sources = self._check_available_sources()
        self.current_source = self.default_source

        # Initialize the unified cache manager
        self.cache_manager = None
        self.cache_enabled = False
        try:
            from .cache import get_cache
            self.cache_manager = get_cache()
            self.cache_enabled = True
            logger.info(f"✅ 统一缓存管理器已启用")
        except Exception as e:
            logger.warning(f"⚠️ Unified Cache Manager initialization failed: {e}")

        logger.info(f"📊 Data source manager initialization completed")
        logger.info(f"   MongoDB缓存: {'✅ 已启用' if self.use_mongodb_cache else '❌ 未启用'}")
        logger.info(f"   统一缓存: {'✅ 已启用' if self.cache_enabled else '❌ 未启用'}")
        logger.info(f"   默认数据源: {self.default_source.value}")
        logger.info(f"   可用数据源: {[s.value for s in self.available_sources]}")

    def _check_mongodb_enabled(self) -> bool:
        """Check if MongoDB caching is enabled"""
        from tradingagents.config.runtime_settings import use_app_cache_enabled
        return use_app_cache_enabled()

    def _get_data_source_priority_order(self, symbol: Optional[str] = None) -> List[ChinaDataSource]:
        """
        Get data source priority order from database (for demotion)

        Args:
            symbol: Stock code, used to identify market type (A shares/US stocks/Hong Kong stocks)

        Returns:
            List of data sources sorted by priority (excluding MongoDB because MongoDB is the highest priority)
        """
        # 🔥 Identify market type
        market_category = self._identify_market_category(symbol)

        try:
            # 🔥 Read data source configuration from database (using sync client)
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            config_collection = db.system_configs

            # Get the latest activation configuration
            config_data = config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data and config_data.get('data_source_configs'):
                data_source_configs = config_data.get('data_source_configs', [])

                # 🔥 Filter out enabled data sources and filter by market category
                enabled_sources = []
                for ds in data_source_configs:
                    if not ds.get('enabled', True):
                        continue

                    # Check if the data source belongs to the current market classification
                    market_categories = ds.get('market_categories', [])
                    if market_categories and market_category:
                        # If the data source is configured with market classification, only matching data sources are selected
                        if market_category not in market_categories:
                            continue

                    enabled_sources.append(ds)

                # Sort by priority (larger numbers have higher priority)
                enabled_sources.sort(key=lambda x: x.get('priority', 0), reverse=True)

                # Convert to ChinaDataSource enum (using unified encoding)
                source_mapping = {
                    "local": ChinaDataSource.LOCAL,
                    DataSourceCode.TUSHARE: ChinaDataSource.TUSHARE,
                    DataSourceCode.AKSHARE: ChinaDataSource.AKSHARE,
                    DataSourceCode.BAOSTOCK: ChinaDataSource.BAOSTOCK,
                }

                result = []
                for ds in enabled_sources:
                    ds_type = ds.get('type', '').lower()
                    if ds_type in source_mapping:
                        source = source_mapping[ds_type]
                        # Exclude MongoDB (MongoDB is the highest priority and does not participate in downgrade)
                        if source != ChinaDataSource.MONGODB and source in self.available_sources:
                            result.append(source)

                if result:
                    logger.info(f"✅ [数据源优先级] 市场={market_category or '全部'}, 从数据库读取: {[s.value for s in result]}")
                else:
                    logger.warning(f"⚠️ [Data source priority] market={market_category or 'All'}, No data source available in database configuration, default order used")

                # 🔥 Additional reading of MCP data sources in datasource_groupings (source_type=mcp) 
                # MCP The data source participates in the downgrade chain indirectly through MongoDB:
                # MCP Tool call → MCPDatasourceAdapter Persist to MongoDB standard collections (tagged data_source="mcp:{server}") 
                # → MCP data is naturally obtained when reading from the LOCAL/MONGODB source in the downgrade chain.
                try:
                    mc_id = market_category or "a_shares"
                    mcp_groupings = list(db.datasource_groupings.find({
                        "market_category_id": mc_id,
                        "enabled": True,
                        "source_type": "mcp",
                    }).sort("priority", 1))
                    if mcp_groupings:
                        mcp_names = [g.get("data_source_name") for g in mcp_groupings]
                        logger.info(
                            f"🔌 [Data source priority] detected {len(mcp_names)} MCP data source (the data has participated in the downgrade chain through MongoDB): {mcp_names}"
                        )
                except Exception as mcp_e:
                    logger.debug(f"⚠️ [Data source priority] Failed to read MCP datasource_groupings: {mcp_e}")

                if result:
                    return result
            else:
                logger.warning("⚠️ [Data source priority] There is no data source configuration in the database, the default order is used")
        except Exception as e:
            logger.warning(f"⚠️ [Data source priority] Failed to read from database: {e}, Use default order")

        # 🔥 Fallback to default order (compatibility)
        # Default order:LOCAL > AKShare > Tushare > BaoStock
        default_order = [
            ChinaDataSource.LOCAL,
            ChinaDataSource.AKSHARE,
            ChinaDataSource.TUSHARE,
            ChinaDataSource.BAOSTOCK,
        ]
        # Only return available data sources
        return [s for s in default_order if s in self.available_sources]

    def _identify_market_category(self, symbol: Optional[str]) -> Optional[str]:
        """
        Identify the market classification to which the stock symbol belongs

        Args:
            symbol: Stock code

        Returns:
            Market category ID (a_shares/us_stocks/hk_stocks), returned if unrecognized None
        """
        if not symbol:
            return None

        try:
            from tradingagents.utils.stock_utils import StockUtils, StockMarket

            market = StockUtils.identify_stock_market(symbol)

            # Map to market categories ID
            market_mapping = {
                StockMarket.CHINA_A: 'a_shares',
                StockMarket.US: 'us_stocks',
                StockMarket.HONG_KONG: 'hk_stocks',
            }

            category = market_mapping.get(market)
            if category:
                logger.debug(f"🔍 [市场识别] {symbol} → {category}")
            return category
        except Exception as e:
            logger.warning(f"⚠️ [market identification] Recognition failed: {e}")
            return None

    def _get_default_source(self) -> ChinaDataSource:
        """获取默认数据源"""
        # If MongoDB caching is enabled, MongoDB acts as the highest priority data source
        if self.use_mongodb_cache:
            return ChinaDataSource.MONGODB

        # Obtained from environment variables, using AKShare as the first priority data source by default
        env_source = os.getenv('DEFAULT_CHINA_DATA_SOURCE', DataSourceCode.AKSHARE).lower()

        # Map to enum (using uniform encoding)
        source_mapping = {
            DataSourceCode.TUSHARE: ChinaDataSource.TUSHARE,
            DataSourceCode.AKSHARE: ChinaDataSource.AKSHARE,
            DataSourceCode.BAOSTOCK: ChinaDataSource.BAOSTOCK,
        }

        return source_mapping.get(env_source, ChinaDataSource.AKSHARE)

    # ==================== Tushare Data interface ====================

    def get_china_stock_data_tushare(self, symbol: str, start_date: str, end_date: str) -> str:
        """
        Use Tushare to obtain China A-share historical data

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date

        Returns:
            str: Formatted stock data reports
        """
        # Temporarily switch to Tushare data source
        original_source = self.current_source
        self.current_source = ChinaDataSource.TUSHARE

        try:
            result = self._get_tushare_data(symbol, start_date, end_date)
            return result
        finally:
            # Restore original data source
            self.current_source = original_source

    def get_fundamentals_data(self, symbol: str) -> str:
        """
        Obtain fundamental data, support multiple data sources and automatic downgrade
        Priority:MongoDB → Tushare → AKShare → Generate analysis

        Args:
            symbol: Stock code

        Returns:
            str: Fundamental Analysis Report
        """
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取基本面数据: {symbol}",
                   extra={
                       'symbol': symbol,
                       'data_source': self.current_source.value,
                       'event_type': 'fundamentals_fetch_start'
                   })

        start_time = time.time()

        try:
            # Call the corresponding acquisition method according to the data source
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_fundamentals(symbol)
            elif self.current_source == ChinaDataSource.LOCAL:
                result = self._get_local_fundamentals(symbol)
            elif self.current_source == ChinaDataSource.TUSHARE:
                result = self._get_tushare_fundamentals(symbol)
            elif self.current_source == ChinaDataSource.AKSHARE:
                result = self._get_akshare_fundamentals(symbol)
            else:
                # Other data sources do not currently support fundamental data and generate basic analysis.
                result = self._generate_fundamentals_analysis(symbol)

            # Check results
            duration = time.time() - start_time
            result_length = len(result) if result else 0

            if result and "❌" not in result:
                logger.info(f"✅ [数据来源: {self.current_source.value}] 成功获取基本面数据: {symbol} ({result_length}字符, 耗时{duration:.2f}秒)",
                           extra={
                               'symbol': symbol,
                               'data_source': self.current_source.value,
                               'duration': duration,
                               'result_length': result_length,
                               'event_type': 'fundamentals_fetch_success'
                           })
                return result
            else:
                logger.warning(f"⚠️ [数据来源: {self.current_source.value}失败] 基本面数据质量异常，尝试降级: {symbol}",
                              extra={
                                  'symbol': symbol,
                                  'data_source': self.current_source.value,
                                  'event_type': 'fundamentals_fetch_fallback'
                              })
                return self._try_fallback_fundamentals(symbol)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [数据来源: {self.current_source.value}异常] 获取基本面数据失败: {symbol} - {e}",
                        extra={
                            'symbol': symbol,
                            'data_source': self.current_source.value,
                            'duration': duration,
                            'error': str(e),
                            'event_type': 'fundamentals_fetch_exception'
                        }, exc_info=True)
            return self._try_fallback_fundamentals(symbol)

    def get_china_stock_fundamentals_tushare(self, symbol: str) -> str:
        """
        Use Tushare to obtain fundamental data of Chinese stocks (compatible with old interface)

        Args:
            symbol: Stock code

        Returns:
            str: Fundamental Analysis Report
        """
        # Redirect to unified interface
        return self._get_tushare_fundamentals(symbol)

    def get_news_data(self, symbol: str = None, hours_back: int = 24, limit: int = 20) -> List[Dict[str, Any]]:
        """
        A unified interface for obtaining news data, supporting multiple data sources and automatic degradation
        Priority:MongoDB → Tushare → AKShare

        Args:
            symbol: Stock code, if empty, get market news
            hours_back: Lookback hours
            limit: Return quantity limit

        Returns:
            List[Dict]: News data list
        """
        logger.info(f"📰 [数据来源: {self.current_source.value}] 开始获取新闻数据: {symbol or '市场新闻'}, 回溯{hours_back}小时",
                   extra={
                       'symbol': symbol,
                       'hours_back': hours_back,
                       'limit': limit,
                       'data_source': self.current_source.value,
                       'event_type': 'news_fetch_start'
                   })

        start_time = time.time()

        try:
            # Call the corresponding acquisition method according to the data source
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_news(symbol, hours_back, limit)
            elif self.current_source == ChinaDataSource.TUSHARE:
                result = self._get_tushare_news(symbol, hours_back, limit)
            elif self.current_source == ChinaDataSource.AKSHARE:
                result = self._get_akshare_news(symbol, hours_back, limit)
            else:
                # Other data sources do not currently support news data
                logger.warning(f"⚠️ 数据源 {self.current_source.value} 不支持新闻数据")
                result = []

            # Check results
            duration = time.time() - start_time
            result_count = len(result) if result else 0

            if result and result_count > 0:
                logger.info(f"✅ [数据来源: {self.current_source.value}] 成功获取新闻数据: {symbol or '市场新闻'} ({result_count}条, 耗时{duration:.2f}秒)",
                           extra={
                               'symbol': symbol,
                               'data_source': self.current_source.value,
                               'news_count': result_count,
                               'duration': duration,
                               'event_type': 'news_fetch_success'
                           })
                return result
            else:
                logger.warning(f"⚠️ [数据来源: {self.current_source.value}] 未获取到新闻数据: {symbol or '市场新闻'}，尝试降级",
                              extra={
                                  'symbol': symbol,
                                  'data_source': self.current_source.value,
                                  'duration': duration,
                                  'event_type': 'news_fetch_fallback'
                              })
                return self._try_fallback_news(symbol, hours_back, limit)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [数据来源: {self.current_source.value}异常] 获取新闻数据失败: {symbol or '市场新闻'} - {e}",
                        extra={
                            'symbol': symbol,
                            'data_source': self.current_source.value,
                            'duration': duration,
                            'error': str(e),
                            'event_type': 'news_fetch_exception'
                        }, exc_info=True)
            return self._try_fallback_news(symbol, hours_back, limit)

    def _check_available_sources(self) -> List[ChinaDataSource]:
        """
        Check available data sources

        Check logic:
        1. Check whether dependent packages are installed (technical availability)
        2. Check whether it is enabled in the database configuration (Business Availability)

        Returns:
            List of available and enabled data sources
        """
        available = []

        # 🔥 Read the data source configuration from the database and obtain the enabled status
        enabled_sources_in_db = set()
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            config_collection = db.system_configs

            # Get the latest activation configuration
            config_data = config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data and config_data.get('data_source_configs'):
                data_source_configs = config_data.get('data_source_configs', [])

                # Extract enabled data source types
                for ds in data_source_configs:
                    if ds.get('enabled', True):
                        ds_type = ds.get('type', '').lower()
                        enabled_sources_in_db.add(ds_type)

                logger.info(f"✅ [Data source configuration] Read from database to enabled data source: {enabled_sources_in_db}")
            else:
                logger.warning("⚠️ [Data source configuration] There is no data source configuration in the database, all installed data sources will be checked")
                # If there is no configuration in the database, all data sources are enabled by default.
                enabled_sources_in_db = {'mongodb', 'local', 'tushare', 'akshare', 'baostock'}
        except Exception as e:
            logger.warning(f"⚠️ [Data source configuration] Failed to read from database: {e}, All installed data sources will be checked")
            # If the read fails, all data sources are enabled by default
            enabled_sources_in_db = {'mongodb', 'local', 'tushare', 'akshare', 'baostock'}

        # Check MongoDB (highest priority)
        if self.use_mongodb_cache and 'mongodb' in enabled_sources_in_db:
            try:
                from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
                adapter = get_mongodb_cache_adapter()
                if adapter.use_app_cache and adapter.db is not None:
                    available.append(ChinaDataSource.MONGODB)
                    logger.info("✅ MongoDB Data source is available and enabled (highest priority)")
                else:
                    logger.warning("⚠️ MongoDB Data source is not available: Database not connected")
            except Exception as e:
                logger.warning(f"⚠️ MongoDB Data source is not available: {e}")
        elif self.use_mongodb_cache and 'mongodb' not in enabled_sources_in_db:
            logger.info("ℹ️ MongoDB The data source has been disabled in the database")

        # Check LOCAL data source (local data imported by user)
        if 'local' in enabled_sources_in_db:
            # LOCAL The data source depends on MongoDB. If MongoDB is available, LOCAL is also available.
            if self.use_mongodb_cache:
                try:
                    from app.core.database import get_mongo_db_sync
                    db = get_mongo_db_sync()
                    # Check if stock_daily_quotes and stock_basic_info collections exist
                    if 'stock_daily_quotes' in db.list_collection_names() and 'stock_basic_info' in db.list_collection_names():
                        available.append(ChinaDataSource.LOCAL)
                        logger.info("✅ LOCAL The data source is available and enabled (depends on MongoDB)")
                    else:
                        logger.warning("⚠️ LOCAL Data source is not available: A required collection is missing (stock_daily_quotes or stock_basic_info)")
                except Exception as e:
                    logger.warning(f"⚠️ LOCAL Data source is not available: {e}")
            else:
                logger.warning("⚠️ LOCAL Data source is not available: MongoDB Not enabled")
        else:
            logger.info("ℹ️ LOCAL The data source has been disabled in the database")

        # Read data source configuration from database
        datasource_configs = self._get_datasource_configs_from_db()

        # Check Tushare
        if 'tushare' in enabled_sources_in_db:
            try:
                import tushare as ts
                # The API Key is read from the database configuration first, and then read from the environment variables.
                token = datasource_configs.get('tushare', {}).get('api_key') or os.getenv('TUSHARE_TOKEN')
                if token:
                    available.append(ChinaDataSource.TUSHARE)
                    source = "数据库配置" if datasource_configs.get('tushare', {}).get('api_key') else "环境变量"
                    logger.info(f"✅ Tushare Data source is available and enabled (API Key Source: {source})")
                else:
                    logger.warning("⚠️ Tushare Data source is not available: API Key Not configured (neither database nor environment variables found)")
            except ImportError:
                logger.warning("⚠️ Tushare Data source is not available: Library not installed")
        else:
            logger.info("ℹ️ Tushare The data source has been disabled in the database")

        # Check AKShare
        if 'akshare' in enabled_sources_in_db:
            try:
                import akshare as ak
                available.append(ChinaDataSource.AKSHARE)
                logger.info("✅ AKShare Data source is available and enabled")
            except ImportError:
                logger.warning("⚠️ AKShare Data source is not available: Library not installed")
        else:
            logger.info("ℹ️ AKShare The data source has been disabled in the database")

        # Check BaoStock
        if 'baostock' in enabled_sources_in_db:
            try:
                import baostock as bs
                available.append(ChinaDataSource.BAOSTOCK)
                logger.info(f"✅ BaoStock Data source is available and enabled")
            except ImportError:
                logger.warning(f"⚠️ BaoStock Data source is not available: Library not installed")
        else:
            logger.info("ℹ️ BaoStock The data source has been disabled in the database")

        # TDX (Tong Da Xin) Removed
        # TDX data sources are no longer checked and supported

        return available

    def _get_datasource_configs_from_db(self) -> dict:
        """Read data source configuration (including API Key) from the database"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()

            # Read activated configuration from system_configs collection
            config = db.system_configs.find_one({"is_active": True})
            if not config:
                return {}

            # Extract data source configuration
            datasource_configs = config.get('data_source_configs', [])

            # Build configuration dictionary {Data source name: {api_key, api_secret, ...}}
            result = {}
            for ds_config in datasource_configs:
                name = ds_config.get('name', '').lower()
                result[name] = {
                    'api_key': ds_config.get('api_key', ''),
                    'api_secret': ds_config.get('api_secret', ''),
                    'config_params': ds_config.get('config_params', {})
                }

            return result
        except Exception as e:
            logger.warning(f"⚠️ Failed to read data source configuration from database: {e}")
            return {}

    def get_current_source(self) -> ChinaDataSource:
        """获取当前数据源"""
        return self.current_source

    def set_current_source(self, source: ChinaDataSource) -> bool:
        """设置当前数据源"""
        if source in self.available_sources:
            self.current_source = source
            logger.info(f"✅ 数据源已切换到: {source.value}")
            return True
        else:
            logger.error(f"❌ 数据源不可用: {source.value}")
            return False

    def get_data_adapter(self):
        """获取当前数据源的适配器"""
        if self.current_source == ChinaDataSource.MONGODB:
            return self._get_mongodb_adapter()
        elif self.current_source == ChinaDataSource.TUSHARE:
            return self._get_tushare_adapter()
        elif self.current_source == ChinaDataSource.AKSHARE:
            return self._get_akshare_adapter()
        elif self.current_source == ChinaDataSource.BAOSTOCK:
            return self._get_baostock_adapter()
        # TDX Removed
        else:
            raise ValueError(f"不支持的数据源: {self.current_source}")

    def _get_mongodb_adapter(self):
        """获取MongoDB适配器"""
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
            return get_mongodb_cache_adapter()
        except ImportError as e:
            logger.error(f"❌ MongoDB Adapter import failed: {e}")
            return None

    def _get_tushare_adapter(self):
        """Get the Tushare provider (the original adapter has been abandoned, now use the provider directly)"""
        try:
            from .providers.china.tushare import get_tushare_provider
            return get_tushare_provider()
        except ImportError as e:
            logger.error(f"❌ Tushare Provider import failed: {e}")
            return None

    def _get_akshare_adapter(self):
        """获取AKShare适配器"""
        try:
            from .providers.china.akshare import get_akshare_provider
            return get_akshare_provider()
        except ImportError as e:
            logger.error(f"❌ AKShare Adapter import failed: {e}")
            return None

    def _get_baostock_adapter(self):
        """Get BaoStock Adapter"""
        try:
            from .providers.china.baostock import get_baostock_provider
            return get_baostock_provider()
        except ImportError as e:
            logger.error(f"❌ BaoStock Adapter import failed: {e}")
            return None

    # TDX Adapter removed
    # def _get_tdx_adapter(self):
    #     """Get TDX adapter (Removed)"""
    #     logger.error(f"❌ TDX The data source is no longer supported")
    #     return None

    def _get_cached_data(self, symbol: str, start_date: str = None, end_date: str = None, max_age_hours: int = 24) -> Optional[pd.DataFrame]:
        """
        Get data from cache

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            max_age_hours: Maximum cache time (hours)

        Returns:
            DataFrame: Cached data, returned if not available None
        """
        if not self.cache_enabled or not self.cache_manager:
            return None

        try:
            cache_key = self.cache_manager.find_cached_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                max_age_hours=max_age_hours
            )

            if cache_key:
                cached_data = self.cache_manager.load_stock_data(cache_key)
                if cached_data is not None and hasattr(cached_data, 'empty') and not cached_data.empty:
                    logger.debug(f"📦 从缓存获取{symbol}数据: {len(cached_data)}条")
                    return cached_data
        except Exception as e:
            logger.warning(f"⚠️ Failed to read data from cache: {e}")

        return None

    def _save_to_cache(self, symbol: str, data: pd.DataFrame, start_date: str = None, end_date: str = None):
        """
        Save data to cache

        Args:
            symbol: Stock code
            data: data
            start_date: start date
            end_date: end date
        """
        if not self.cache_enabled or not self.cache_manager:
            return

        try:
            if data is not None and hasattr(data, 'empty') and not data.empty:
                self.cache_manager.save_stock_data(symbol, data, start_date, end_date)
                logger.debug(f"💾 保存{symbol}数据到缓存: {len(data)}条")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save data to cache: {e}")

    def _get_volume_series_safely(self, data: pd.DataFrame) -> tuple[Optional[str], Optional[pd.Series]]:
        """Get volume series safely, only real volume columns are accepted."""
        try:
            volume_columns = ['volume', 'vol', 'trade_volume', '成交量']

            for col in volume_columns:
                if col in data.columns:
                    logger.info(f"✅ 找到成交量列: {col}")
                    volume_series = pd.to_numeric(data[col], errors='coerce')
                    if volume_series.notna().any():
                        return col, volume_series

            logger.warning(f"⚠️ No valid volume column found, available columns are available: {list(data.columns)}")
            return None, None
        except Exception as e:
            logger.error(f"❌ 获取成交量序列失败: {e}")
            return None, None

    def _get_volume_safely(self, data: pd.DataFrame) -> Optional[float]:
        """Safely get the average volume for the most recent window."""
        _, volume_series = self._get_volume_series_safely(data)
        if volume_series is None:
            return None

        valid_volume_series = volume_series.dropna()
        if valid_volume_series.empty:
            return None

        return float(valid_volume_series.mean())

    def _format_stock_data_response(self, data: pd.DataFrame, symbol: str, stock_name: str,
                                    start_date: str, end_date: str) -> str:
        """
        Formatted stock data response (contains technical indicators)

        Args:
            data: stock data DataFrame
            symbol: Stock code
            stock_name: Stock name
            start_date: start date
            end_date: end date

        Returns:
            str: Formatted data reports (including technical indicators)
        """
        try:
            def _format_trade_date(value: Any) -> str:
                if value is None:
                    return ""
                try:
                    if pd.isna(value):
                        return ""
                except Exception:
                    pass

                try:
                    return pd.to_datetime(value).strftime("%Y-%m-%d")
                except Exception:
                    return str(value)

            original_data_count = len(data)
            logger.info(f"📊 [技术指标] 开始计算技术指标，原始数据: {original_data_count}条")

            # 🔧 Calculate technical indicators (using complete data)
            sort_column = 'date' if 'date' in data.columns else ('trade_date' if 'trade_date' in data.columns else None)
            if sort_column:
                data = data.sort_values(sort_column)

            # Calculate moving average
            data['ma5'] = data['close'].rolling(window=5, min_periods=1).mean()
            data['ma10'] = data['close'].rolling(window=10, min_periods=1).mean()
            data['ma20'] = data['close'].rolling(window=20, min_periods=1).mean()
            data['ma60'] = data['close'].rolling(window=60, min_periods=1).mean()

            # Calculate RSI (Relative Strength Index) - Flush style: using Chinese SMA (EMA with adjust=True) 
            # Reference:https://blog.csdn.net/u011218867/article/details/117427927
            # Flush/Tongdaxin's RSI uses the SMA function, which is equivalent to pandas's ewm(com=N-1, adjust=True)
            delta = data['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # RSI6 - Use Chinese style SMA
            avg_gain6 = gain.ewm(com=5, adjust=True).mean()  # com = N - 1
            avg_loss6 = loss.ewm(com=5, adjust=True).mean()
            rs6 = avg_gain6 / avg_loss6.replace(0, np.nan)
            data['rsi6'] = 100 - (100 / (1 + rs6))

            # RSI12 - Use Chinese style SMA
            avg_gain12 = gain.ewm(com=11, adjust=True).mean()
            avg_loss12 = loss.ewm(com=11, adjust=True).mean()
            rs12 = avg_gain12 / avg_loss12.replace(0, np.nan)
            data['rsi12'] = 100 - (100 / (1 + rs12))

            # RSI24 - Use Chinese style SMA
            avg_gain24 = gain.ewm(com=23, adjust=True).mean()
            avg_loss24 = loss.ewm(com=23, adjust=True).mean()
            rs24 = avg_gain24 / avg_loss24.replace(0, np.nan)
            data['rsi24'] = 100 - (100 / (1 + rs24))

            # Keep RSI14 as international standard reference (using simple moving average)
            gain14 = gain.rolling(window=14, min_periods=1).mean()
            loss14 = loss.rolling(window=14, min_periods=1).mean()
            rs14 = gain14 / loss14.replace(0, np.nan)
            data['rsi14'] = 100 - (100 / (1 + rs14))

            # Calculate MACD
            ema12 = data['close'].ewm(span=12, adjust=False).mean()
            ema26 = data['close'].ewm(span=26, adjust=False).mean()
            data['macd_dif'] = ema12 - ema26
            data['macd_dea'] = data['macd_dif'].ewm(span=9, adjust=False).mean()
            data['macd'] = (data['macd_dif'] - data['macd_dea']) * 2

            # Calculate Bollinger Bands
            data['boll_mid'] = data['close'].rolling(window=20, min_periods=1).mean()
            std = data['close'].rolling(window=20, min_periods=1).std()
            data['boll_upper'] = data['boll_mid'] + 2 * std
            data['boll_lower'] = data['boll_mid'] - 2 * std

            logger.info(f"✅ [Technical indicators] Technical indicator calculation completed")

            # 🔧 Only retain the last 3-5 days of data for display (reduce token consumption)
            display_rows = min(5, len(data))
            display_data = data.tail(display_rows)
            latest_data = data.iloc[-1]
            latest_trade_date = _format_trade_date(latest_data.get('date') or latest_data.get('trade_date'))
            requested_end_date = _format_trade_date(end_date) or str(end_date)

            # The tool end directly calculates the moving average direction and turning point conclusion to avoid secondary derivation by LLM.
            def _compute_ma_conclusion(df: pd.DataFrame, ma_col: str, price_col: str = 'close') -> Dict[str, Any]:
                valid_df = df[[ma_col, price_col]].dropna()
                sample_size = min(5, len(valid_df))

                if sample_size < 2:
                    return {
                        'sample_size': sample_size,
                        'slope_abs': None,
                        'slope_pct_per_day': None,
                        'direction': '样本不足',
                        'turning_signal': '样本不足'
                    }

                recent = valid_df.tail(sample_size)
                y = recent[ma_col].astype(float).to_numpy()
                x = np.arange(sample_size, dtype=float)
                slope_abs = float(np.polyfit(x, y, 1)[0])

                latest_close = float(recent[price_col].iloc[-1]) if recent[price_col].iloc[-1] else 0.0
                slope_pct_per_day = (slope_abs / latest_close * 100.0) if latest_close != 0 else 0.0

                # The threshold is characterized by the daily rate of change to avoid incomparability between stocks at different prices based solely on absolute values.
                if slope_pct_per_day > 0.02:
                    direction = '上行'
                elif slope_pct_per_day < -0.02:
                    direction = '下行'
                else:
                    direction = '走平'

                turning_signal = '未出现拐头'
                if sample_size >= 3:
                    prev_diff = y[-2] - y[-3]
                    curr_diff = y[-1] - y[-2]
                    if prev_diff <= 0 < curr_diff:
                        turning_signal = '拐头向上'
                    elif prev_diff >= 0 > curr_diff:
                        turning_signal = '拐头向下'
                    elif curr_diff > 0:
                        turning_signal = '延续上行'
                    elif curr_diff < 0:
                        turning_signal = '延续下行'
                    else:
                        turning_signal = '短期走平'

                return {
                    'sample_size': sample_size,
                    'slope_abs': slope_abs,
                    'slope_pct_per_day': slope_pct_per_day,
                    'direction': direction,
                    'turning_signal': turning_signal
                }

            ma5_conclusion = _compute_ma_conclusion(data, 'ma5')
            ma10_conclusion = _compute_ma_conclusion(data, 'ma10')
            ma20_conclusion = _compute_ma_conclusion(data, 'ma20')
            ma60_conclusion = _compute_ma_conclusion(data, 'ma60')

            ma_conclusions = {
                'ma5': ma5_conclusion,
                'ma10': ma10_conclusion,
                'ma20': ma20_conclusion,
                'ma60': ma60_conclusion,
            }

            # 🔍 [debug log] Print raw data and technical indicators for the last 5 days
            logger.info(f"🔍 [技术指标详情] ===== 最近{display_rows}个交易日数据 =====")
            for i, (idx, row) in enumerate(display_data.iterrows(), 1):
                logger.info(f"🔍 [技术指标详情] 第{i}天 ({row.get('date', 'N/A')}):")
                logger.info(f"   价格: 开={row.get('open', 0):.2f}, 高={row.get('high', 0):.2f}, 低={row.get('low', 0):.2f}, 收={row.get('close', 0):.2f}")
                logger.info(f"   MA: MA5={row.get('ma5', 0):.2f}, MA10={row.get('ma10', 0):.2f}, MA20={row.get('ma20', 0):.2f}, MA60={row.get('ma60', 0):.2f}")
                logger.info(f"   MACD: DIF={row.get('macd_dif', 0):.4f}, DEA={row.get('macd_dea', 0):.4f}, MACD={row.get('macd', 0):.4f}")
                logger.info(f"   RSI: RSI6={row.get('rsi6', 0):.2f}, RSI12={row.get('rsi12', 0):.2f}, RSI24={row.get('rsi24', 0):.2f} (同花顺风格)")
                logger.info(f"   RSI14: {row.get('rsi14', 0):.2f} (国际标准)")
                logger.info(f"   BOLL: 上={row.get('boll_upper', 0):.2f}, 中={row.get('boll_mid', 0):.2f}, 下={row.get('boll_lower', 0):.2f}")

            logger.info(f"🔍 [Technical indicator details] ===== end of data details =====")

            # Calculate the latest price and percentage change
            latest_price = latest_data.get('close', 0)
            prev_close = data.iloc[-2].get('close', latest_price) if len(data) > 1 else latest_price
            change = latest_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0

            # Format data report
            result = f"📊 {stock_name}({symbol}) - 技术分析数据\n"
            result += f"请求分析日期: {requested_end_date}\n"
            if latest_trade_date:
                result += f"实际数据日期: {latest_trade_date}\n"
            if latest_trade_date and latest_trade_date != requested_end_date:
                result += (
                    f"日期说明: 请求分析日期 {requested_end_date} 暂无完整日线数据，"
                    f"The following prices and technical indicators are based on {latest_trade_date} Subject to\n"
                )
            result += f"数据期间: {start_date} 至 {end_date}\n"
            result += f"数据条数: {original_data_count}条 (展示最近{display_rows}个交易日)\n\n"

            result += f"💰 最新价格: ¥{latest_price:.2f}\n"
            result += f"📈 涨跌额: {change:+.2f} ({change_pct:+.2f}%)\n\n"

            # Add technical indicators
            result += f"📊 moving average (MA):\n"
            result += f"   MA5:  ¥{latest_data['ma5']:.2f}"
            if latest_price > latest_data['ma5']:
                result += " (价格在MA5上方 ↑)\n"
            else:
                result += " (价格在MA5下方 ↓)\n"

            result += f"   MA10: ¥{latest_data['ma10']:.2f}"
            if latest_price > latest_data['ma10']:
                result += " (Price is above MA10 ↑)\n"
            else:
                result += " (Price is below MA10 ↓)\n"

            result += f"   MA20: ¥{latest_data['ma20']:.2f}"
            if latest_price > latest_data['ma20']:
                result += " (Price is above MA20 ↑)\n"
            else:
                result += " (Price is below MA20 ↓)\n"

            result += f"   MA60: ¥{latest_data['ma60']:.2f}"
            if latest_price > latest_data['ma60']:
                result += " (Price is above MA60 ↑)\n\n"
            else:
                result += " (Price is below MA60 ↓)\n\n"

            result += f"📐 Moving average direction conclusion (deterministic calculation on tool end):\n"
            for ma_name, ma_result in ma_conclusions.items():
                ma_label = ma_name.upper()
                if ma_result['slope_abs'] is not None:
                    result += (
                        f"   {ma_label}斜率: {ma_result['slope_abs']:+.4f}/日 "
                        f"({ma_result['slope_pct_per_day']:+.3f}%/day), "
                        f"direction: {ma_result['direction']}, "
                        f"Turn head recognition: {ma_result['turning_signal']}, "
                        f"sample: {ma_result['sample_size']}day\n"
                    )
                else:
                    result += f"   {ma_label}slope: Insufficient samples, unable to judge yet\n"
            result += "\n"

            # Machine-readable conclusion block: directly referenced by downstream components and LLM to avoid secondary calculations
            result += "🧾 MACHINE_READABLE_MA_CONCLUSIONS:\n"
            for ma_name, ma_result in ma_conclusions.items():
                slope_abs = "null" if ma_result['slope_abs'] is None else f"{ma_result['slope_abs']:.6f}"
                slope_pct = "null" if ma_result['slope_pct_per_day'] is None else f"{ma_result['slope_pct_per_day']:.6f}"
                result += (
                    f"   {ma_name}.sample_size={ma_result['sample_size']};"
                    f"{ma_name}.slope_abs={slope_abs};"
                    f"{ma_name}.slope_pct_per_day={slope_pct};"
                    f"{ma_name}.direction={ma_result['direction']};"
                    f"{ma_name}.turning_signal={ma_result['turning_signal']}\n"
                )
            result += "\n"

            # MACD indicator
            result += f"📈 MACD指标:\n"
            result += f"   DIF:  {latest_data['macd_dif']:.3f}\n"
            result += f"   DEA:  {latest_data['macd_dea']:.3f}\n"
            result += f"   MACD: {latest_data['macd']:.3f}"
            if latest_data['macd'] > 0:
                result += " (多头 ↑)\n"
            else:
                result += " (空头 ↓)\n"

            # The tool side determines MACD crossover deterministically to avoid LLM inferring on its own.
            macd_cross_signal = "样本不足"
            dif_dea_relation = "未知"
            macd_hist_trend = "样本不足"

            if len(data) > 1:
                prev_dif = data.iloc[-2]['macd_dif']
                prev_dea = data.iloc[-2]['macd_dea']
                curr_dif = latest_data['macd_dif']
                curr_dea = latest_data['macd_dea']
                prev_hist = data.iloc[-2]['macd']
                curr_hist = latest_data['macd']

                dif_dea_relation = "DIF>DEA" if curr_dif > curr_dea else ("DIF<DEA" if curr_dif < curr_dea else "DIF=DEA")

                if curr_hist > prev_hist:
                    macd_hist_trend = "柱状图走强"
                elif curr_hist < prev_hist:
                    macd_hist_trend = "柱状图走弱"
                else:
                    macd_hist_trend = "柱状图持平"

                if prev_dif <= prev_dea and curr_dif > curr_dea:
                    macd_cross_signal = "金叉"
                elif prev_dif >= prev_dea and curr_dif < curr_dea:
                    macd_cross_signal = "死叉"
                else:
                    macd_cross_signal = "无交叉"

            result += (
                f"   MACD交叉识别: {macd_cross_signal}; 当前关系: {dif_dea_relation}; "
                f"Histogram changes: {macd_hist_trend}\n\n"
            )

            result += "🧾 MACHINE_READABLE_MACD_CONCLUSIONS:\n"
            result += (
                f"   macd.cross_signal={macd_cross_signal};"
                f"macd.dif_dea_relation={dif_dea_relation};"
                f"macd.hist_trend={macd_hist_trend};"
                f"macd.dif={float(latest_data['macd_dif']):.6f};"
                f"macd.dea={float(latest_data['macd_dea']):.6f};"
                f"macd.hist={float(latest_data['macd']):.6f}\n\n"
            )

            # RSI Indicator - Flush Style (6, 12, 24)
            rsi6 = latest_data['rsi6']
            rsi12 = latest_data['rsi12']
            rsi24 = latest_data['rsi24']
            result += f"📉 RSI indicator (Flush style):\n"
            result += f"   RSI6:  {rsi6:.2f}"
            if rsi6 >= 80:
                result += " (超买 ⚠️)\n"
            elif rsi6 <= 20:
                result += " (超卖 ⚠️)\n"
            else:
                result += "\n"

            result += f"   RSI12: {rsi12:.2f}"
            if rsi12 >= 80:
                result += " (超买 ⚠️)\n"
            elif rsi12 <= 20:
                result += " (超卖 ⚠️)\n"
            else:
                result += "\n"

            result += f"   RSI24: {rsi24:.2f}"
            if rsi24 >= 80:
                result += " (超买 ⚠️)\n"
            elif rsi24 <= 20:
                result += " (超卖 ⚠️)\n"
            else:
                result += "\n"

            # Determine RSI trend
            if rsi6 > rsi12 > rsi24:
                result += "   趋势: 多头排列 ↑\n\n"
            elif rsi6 < rsi12 < rsi24:
                result += "   趋势: 空头排列 ↓\n\n"
            else:
                result += "   趋势: 震荡整理 ↔\n\n"

            # Bollinger Bands
            result += f"📊 Bollinger Bands (BOLL):\n"
            result += f"   上轨: ¥{latest_data['boll_upper']:.2f}\n"
            result += f"   中轨: ¥{latest_data['boll_mid']:.2f}\n"
            result += f"   下轨: ¥{latest_data['boll_lower']:.2f}\n"

            # Determine the position of price in Bollinger Bands
            boll_position = (latest_price - latest_data['boll_lower']) / (latest_data['boll_upper'] - latest_data['boll_lower']) * 100
            result += f"   价格位置: {boll_position:.1f}%"
            if boll_position >= 80:
                result += " (Close to upper limit, may be overbought ⚠️)\n\n"
            elif boll_position <= 20:
                result += " (Close to the lower track, may be oversold ⚠️)\n\n"
            else:
                result += " (中性区域)\n\n"

            # price statistics
            result += f"📊 价格统计 (最近{display_rows}个交易日):\n"
            result += f"   最高价: ¥{display_data['high'].max():.2f}\n"
            result += f"   最低价: ¥{display_data['low'].min():.2f}\n"
            result += f"   平均价: ¥{display_data['close'].mean():.2f}\n"

            _, volume_series = self._get_volume_series_safely(display_data)
            if volume_series is None:
                result += f"   最近{display_rows}日成交量明细: 工具结果未提供\n"
                result += "   average trading volume: Tool results not provided\n"
            else:
                result += f"   最近{display_rows}日成交量明细:\n"
                valid_volume_count = 0
                for idx, row in display_data.iterrows():
                    trade_date = _format_trade_date(row.get('date') or row.get('trade_date')) or 'N/A'
                    volume_value = volume_series.loc[idx]
                    if pd.isna(volume_value):
                        result += f"      {trade_date}: 工具结果未提供\n"
                    else:
                        valid_volume_count += 1
                        result += f"      {trade_date}: {float(volume_value):,.0f}股\n"

                average_volume = self._get_volume_safely(display_data)
                if average_volume is None:
                    result += "   average trading volume: Tool results not provided\n"
                elif valid_volume_count == display_rows:
                    result += f"   平均成交量: {average_volume:,.0f}股\n"
                else:
                    result += (
                        f"   平均成交量(基于{valid_volume_count}/{display_rows}个有效交易日): "
                        f"{average_volume:,.0f}shares\n"
                    )

            return result

        except Exception as e:
            logger.error(f"❌ 格式化数据响应失败: {e}", exc_info=True)
            return f"❌ 格式化{symbol}数据失败: {e}"

    def get_stock_dataframe(self, symbol: str, start_date: str = None, end_date: str = None, period: str = "daily") -> pd.DataFrame:
        """
        DataFrame interface for obtaining stock data, supporting multiple data sources and automatic degradation

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            period: Data period (daily/weekly/monthly), default is daily

        Returns:
            pd.DataFrame: Stock data DataFrame, column criteria:open, high, low, close, vol, amount, date
        """
        logger.info(f"📊 [DataFrame接口] 获取股票数据: {symbol} ({start_date} 到 {end_date})")

        try:
            # Try the current data source
            df = None
            if self.current_source == ChinaDataSource.MONGODB:
                from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
                adapter = get_mongodb_cache_adapter()
                df = adapter.get_historical_data(symbol, start_date, end_date, period=period)
            elif self.current_source == ChinaDataSource.TUSHARE:
                from .providers.china.tushare import get_tushare_provider
                provider = get_tushare_provider()
                df = provider.get_daily_data(symbol, start_date, end_date)
            elif self.current_source == ChinaDataSource.AKSHARE:
                from .providers.china.akshare import get_akshare_provider
                provider = get_akshare_provider()
                df = provider.get_stock_data(symbol, start_date, end_date)
            elif self.current_source == ChinaDataSource.BAOSTOCK:
                from .providers.china.baostock import get_baostock_provider
                provider = get_baostock_provider()
                df = provider.get_stock_data(symbol, start_date, end_date)

            if df is not None and not df.empty:
                logger.info(f"✅ [DataFrame接口] 从 {self.current_source.value} 获取成功: {len(df)}条")
                return self._standardize_dataframe(df)

            # Downgrade to other data sources
            logger.warning(f"⚠️ [DataFrame interface] {self.current_source.value} Failed, try downgrading")
            for source in self.available_sources:
                if source == self.current_source:
                    continue
                try:
                    if source == ChinaDataSource.MONGODB:
                        from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
                        adapter = get_mongodb_cache_adapter()
                        df = adapter.get_historical_data(symbol, start_date, end_date, period=period)
                    elif source == ChinaDataSource.TUSHARE:
                        from .providers.china.tushare import get_tushare_provider
                        provider = get_tushare_provider()
                        df = provider.get_daily_data(symbol, start_date, end_date)
                    elif source == ChinaDataSource.AKSHARE:
                        from .providers.china.akshare import get_akshare_provider
                        provider = get_akshare_provider()
                        df = provider.get_stock_data(symbol, start_date, end_date)
                    elif source == ChinaDataSource.BAOSTOCK:
                        from .providers.china.baostock import get_baostock_provider
                        provider = get_baostock_provider()
                        df = provider.get_stock_data(symbol, start_date, end_date)

                    if df is not None and not df.empty:
                        logger.info(f"✅ [DataFrame接口] 降级到 {source.value} 成功: {len(df)}条")
                        return self._standardize_dataframe(df)
                except Exception as e:
                    logger.warning(f"⚠️ [DataFrame接口] {source.value} 失败: {e}")
                    continue

            logger.error(f"❌ [DataFrame interface] All data sources fail: {symbol}")
            return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ [DataFrame interface] Failed to obtain: {e}", exc_info=True)
            return pd.DataFrame()

    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize DataFrame column names and formats

        Args:
            df: original DataFrame

        Returns:
            pd.DataFrame: standardized DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        out = df.copy()

        # Column name mapping
        colmap = {
            # English
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
            'Volume': 'vol', 'Amount': 'amount', 'symbol': 'code', 'Symbol': 'code',
            # Already lower
            'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
            'vol': 'vol', 'volume': 'vol', 'amount': 'amount', 'code': 'code',
            'date': 'date', 'trade_date': 'date',
            # Chinese (AKShare common)
            '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close',
            '成交量': 'vol', '成交额': 'amount', '涨跌幅': 'pct_change', '涨跌额': 'change',
        }
        out = out.rename(columns={c: colmap.get(c, c) for c in out.columns})

        # Make sure dates are sorted
        if 'date' in out.columns:
            try:
                out['date'] = pd.to_datetime(out['date'])
                out = out.sort_values('date')
            except Exception:
                pass

        # Calculate the increase and decrease (if missing)
        if 'pct_change' not in out.columns and 'close' in out.columns:
            out['pct_change'] = out['close'].pct_change() * 100.0

        return out

    def get_stock_data(self, symbol: str, start_date: str = None, end_date: str = None, period: str = "daily") -> str:
        """
        A unified interface for obtaining stock data, supporting multi-period data

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            period: Data period (daily/weekly/monthly), default is daily

        Returns:
            str: Formatted stock data
        """
        # Record detailed input parameters
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取{period}数据: {symbol}",
                   extra={
                       'symbol': symbol,
                       'start_date': start_date,
                       'end_date': end_date,
                       'period': period,
                       'data_source': self.current_source.value,
                       'event_type': 'data_fetch_start'
                   })

        # Add detailed ticker tracking logs
        logger.info(f"🔍 [股票代码追踪] DataSourceManager.get_stock_data 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
        logger.info(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(symbol))}")
        logger.info(f"🔍 [Stock symbol tracking] ticker character: {list(str(symbol))}")
        logger.info(f"🔍 [Stock symbol tracking] Current data source: {self.current_source.value}")

        start_time = time.time()

        try:
            # Call the corresponding acquisition method according to the data source
            actual_source = None  # Actual data source used

            if self.current_source == ChinaDataSource.MONGODB:
                result, actual_source = self._get_mongodb_data(symbol, start_date, end_date, period)
            elif self.current_source == ChinaDataSource.LOCAL:
                result = self._get_local_data(symbol, start_date, end_date, period)
                actual_source = "local"
            elif self.current_source == ChinaDataSource.TUSHARE:
                logger.info(f"🔍 [Stock symbol tracking] Call the Tushare data source and pass in parameters: symbol='{symbol}', period='{period}'")
                result = self._get_tushare_data(symbol, start_date, end_date, period)
                actual_source = "tushare"
            elif self.current_source == ChinaDataSource.AKSHARE:
                result = self._get_akshare_data(symbol, start_date, end_date, period)
                actual_source = "akshare"
            elif self.current_source == ChinaDataSource.BAOSTOCK:
                result = self._get_baostock_data(symbol, start_date, end_date, period)
                actual_source = "baostock"
            # TDX Removed
            else:
                result = f"❌ 不支持的数据源: {self.current_source.value}"
                actual_source = None

            result, normalized_source = self._normalize_stock_data_result(result)
            if normalized_source:
                actual_source = normalized_source

            # Record detailed output results
            duration = time.time() - start_time
            result_length = len(result) if result else 0
            is_success = result and "❌" not in result and "错误" not in result

            # Use actual data source name or use if none current_source
            display_source = actual_source or self.current_source.value

            if is_success:
                logger.info(f"✅ [数据来源: {display_source}] 成功获取股票数据: {symbol} ({result_length}字符, 耗时{duration:.2f}秒)",
                           extra={
                               'symbol': symbol,
                               'start_date': start_date,
                               'end_date': end_date,
                               'data_source': display_source,
                               'actual_source': actual_source,
                               'requested_source': self.current_source.value,
                               'duration': duration,
                               'result_length': result_length,
                               'result_preview': result[:200] + '...' if result_length > 200 else result,
                               'event_type': 'data_fetch_success'
                           })
                return result
            else:
                logger.warning(f"⚠️ [数据来源: {self.current_source.value}失败] 数据质量异常，尝试降级到其他数据源: {symbol}",
                              extra={
                                  'symbol': symbol,
                                  'start_date': start_date,
                                  'end_date': end_date,
                                  'data_source': self.current_source.value,
                                  'duration': duration,
                                  'result_length': result_length,
                                  'result_preview': result[:200] + '...' if result_length > 200 else result,
                                  'event_type': 'data_fetch_warning'
                              })

                # Also try to downgrade to other data sources when data quality is abnormal.
                fallback_result = self._try_fallback_sources(symbol, start_date, end_date)
                fallback_result, fallback_source = self._normalize_stock_data_result(fallback_result)
                if fallback_result and "❌" not in fallback_result and "错误" not in fallback_result:
                    logger.info(f"✅ [数据来源: {fallback_source or '备用数据源'}] 降级成功获取数据: {symbol}")
                    return fallback_result
                else:
                    logger.error(f"❌ [Data source: All data sources failed] All data sources cannot obtain valid data: {symbol}")
                    return result  # Return the original result (with error information)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [data acquisition] Failed with exception: {e}",
                        extra={
                            'symbol': symbol,
                            'start_date': start_date,
                            'end_date': end_date,
                            'data_source': self.current_source.value,
                            'duration': duration,
                            'error': str(e),
                            'event_type': 'data_fetch_exception'
                        }, exc_info=True)
            fallback_result, _ = self._normalize_stock_data_result(
                self._try_fallback_sources(symbol, start_date, end_date)
            )
            return fallback_result

    def _get_mongodb_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> tuple[str, str | None]:
        """
        Get multi-period data from MongoDB - including technical indicator calculations

        Returns:
            tuple[str, str | None]: (Result string, The actual data source name used)
        """
        logger.debug(f"📊 [MongoDB] Call parameters: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
            adapter = get_mongodb_cache_adapter()

            # Get historical data for a specified period from MongoDB
            df = adapter.get_historical_data(symbol, start_date, end_date, period=period)

            if df is not None and not df.empty:
                logger.info(f"✅ [数据来源: MongoDB缓存] 成功获取{period}数据: {symbol} ({len(df)}条记录)")

                # 🔧 Fix: Use unified formatting method, including technical indicator calculations
                # Get the stock name (extract from DataFrame or use default value)
                stock_name = f'股票{symbol}'
                if 'name' in df.columns and not df['name'].empty:
                    stock_name = df['name'].iloc[0]

                # Call a unified formatting method (including technical indicator calculation)
                result = self._format_stock_data_response(df, symbol, stock_name, start_date, end_date)

                logger.info(f"✅ [MongoDB] Calculated technical indicators: MA5/10/20/60, MACD, RSI, BOLL")
                return result, "mongodb"
            else:
                # MongoDB No data (detailed data source information has been recorded internally in the adapter), downgrade to other data sources
                logger.info(f"🔄 [MongoDB] 未找到{period}数据: {symbol}，开始尝试备用数据源")
                return self._try_fallback_sources(symbol, start_date, end_date, period)

        except Exception as e:
            logger.error(f"❌ [数据来源: MongoDB异常] 获取{period}数据失败: {symbol}, 错误: {e}")
            # MongoDB Exception, downgrade to other data sources
            return self._try_fallback_sources(symbol, start_date, end_date, period)

    def _get_local_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """
        Get historical data from MongoDB local cache collection.

        Args:
            symbol: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            period: data period (daily/weekly/monthly)

        Returns:
            str: Formatted stock data reports
        """
        logger.debug(f"📊 [LOCAL] Call parameters: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        try:
            from app.core.database import get_mongo_db_sync
            from tradingagents.utils.stock_utils import StockUtils

            db = get_mongo_db_sync()
            code6 = str(symbol).zfill(6)
            is_fund = StockUtils.is_fund(code6)
            collection = db.etf_daily_quotes if is_fund else db.stock_daily_quotes
            symbol_field = "code" if is_fund else "symbol"

            # Query conditions
            query = {
                symbol_field: code6,
            }

            if not is_fund:
                query["data_source"] = "local"
                query["period"] = period

            # Add date range filtering (if provided)
            if start_date and end_date:
                start_date_str = start_date if is_fund else start_date.replace("-", "")
                end_date_str = end_date if is_fund else end_date.replace("-", "")
                query["trade_date"] = {
                    "$gte": start_date_str,
                    "$lte": end_date_str
                }

            # Query data and sort by date
            cursor = collection.find(query).sort("trade_date", 1)
            records = list(cursor)

            if not records:
                logger.info(f"🔄 [LOCAL] 未找到{period}数据: {symbol}，尝试备用数据源")
                return f"❌ 本地数据源没有 {symbol} 的{period}数据"

            logger.info(f"✅ [数据来源: LOCAL] 成功获取{period}数据: {symbol} ({len(records)}条记录)")

            # Convert to DataFrame
            df = pd.DataFrame(records)

            if is_fund:
                df["symbol"] = code6

            # Standardize column names (ensure consistency with other data sources)
            column_mapping = {
                "trade_date": "date",
                "open_price": "open",
                "high_price": "high",
                "low_price": "low",
                "close_price": "close",
                "volume": "volume",
                "amount": "amount"
            }

            # Rename the column if it exists
            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    df.rename(columns={old_col: new_col}, inplace=True)

            # Make sure required columns exist
            required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"⚠️ [LOCAL] Missing required column: {missing_columns}")
                return f"❌ The local data source data format is incomplete and columns are missing.: {missing_columns}"

            # Get stock name
            stock_name = f'股票{symbol}'
            if 'name' in df.columns and not df['name'].empty:
                stock_name = df['name'].iloc[0]
            elif records and 'name' in records[0]:
                stock_name = records[0]['name']
            elif is_fund:
                etf_info = db.etf_basic_info.find_one(
                    {"code": code6},
                    {"name": 1, "fund_name": 1, "etf_name": 1, "_id": 0}
                )
                if etf_info:
                    stock_name = (
                        etf_info.get("name")
                        or etf_info.get("fund_name")
                        or etf_info.get("etf_name")
                        or stock_name
                    )

            # Call a unified formatting method (including technical indicator calculation)
            result = self._format_stock_data_response(df, code6, stock_name, start_date, end_date)

            logger.info(f"✅ [LOCAL] Calculated technical indicators: MA5/10/20/60, MACD, RSI, BOLL")
            return result

        except Exception as e:
            logger.error(f"❌ [数据来源: LOCAL异常] 获取{period}数据失败: {symbol}, 错误: {e}")
            return f"❌ Failed to get data from local data source: {e}"

    def _get_tushare_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """Get multi-period data using Tushare - use provider + unified cache"""
        logger.debug(f"📊 [Tushare] Call parameters: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        # Add detailed ticker tracking logs
        logger.info(f"🔍 [股票代码追踪] _get_tushare_data 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
        logger.info(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(symbol))}")
        logger.info(f"🔍 [Stock symbol tracking] ticker character: {list(str(symbol))}")
        logger.info(f"🔍 [DataSourceManager Detailed log] _get_tushare_data Start execution")
        logger.info(f"🔍 [DataSourceManager Detailed log] Current data source: {self.current_source.value}")

        start_time = time.time()
        try:
            # 1. Try to get it from cache first
            cached_data = self._get_cached_data(symbol, start_date, end_date, max_age_hours=24)
            if cached_data is not None and not cached_data.empty:
                logger.info(f"✅ [缓存命中] 从缓存获取{symbol}数据")
                # Get basic stock information
                provider = self._get_tushare_adapter()
                if provider:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_closed():
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                    except RuntimeError:
                        # There is no event loop in the thread pool, create a new
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    stock_info = loop.run_until_complete(provider.get_stock_basic_info(symbol))
                    stock_name = stock_info.get('name', f'股票{symbol}') if stock_info else f'股票{symbol}'
                else:
                    stock_name = f'股票{symbol}'

                # Formatted return
                return self._format_stock_data_response(cached_data, symbol, stock_name, start_date, end_date)

            # 2. Cache miss, obtained from provider
            logger.info(f"🔍 [Stock symbol tracking] Call tushare_provider, passing in parameters: symbol='{symbol}'")
            logger.info(f"🔍 [DataSourceManager Detailed log] Start calling tushare_provider...")

            provider = self._get_tushare_adapter()
            if not provider:
                return f"❌ Tushare Provider is unavailable"

            # Use asynchronous methods to obtain historical data
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # There is no event loop in the thread pool, create a new
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            data = loop.run_until_complete(provider.get_historical_data(symbol, start_date, end_date))

            if data is not None and not data.empty:
                # Save to cache
                self._save_to_cache(symbol, data, start_date, end_date)

                # Get basic stock information (asynchronous)
                stock_info = loop.run_until_complete(provider.get_stock_basic_info(symbol))
                stock_name = stock_info.get('name', f'股票{symbol}') if stock_info else f'股票{symbol}'

                # Formatted return
                result = self._format_stock_data_response(data, symbol, stock_name, start_date, end_date)

                duration = time.time() - start_time
                logger.info(f"🔍 [DataSourceManager详细日志] 调用完成，耗时: {duration:.3f}秒")
                logger.info(f"🔍 [Stock symbol tracking] Return the first 200 characters of the result: {result[:200] if result else 'None'}")
                logger.debug(f"📊 [Tushare] 调用完成: 耗时={duration:.2f}s, 结果长度={len(result) if result else 0}")

                return result
            else:
                result = f"❌ 未获取到{symbol}的有效数据"
                duration = time.time() - start_time
                logger.warning(f"⚠️ [Tushare] No data was obtained, time consuming={duration:.2f}s")
                return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [Tushare] 调用失败: {e}, 耗时={duration:.2f}s", exc_info=True)
            logger.error(f"❌ [DataSourceManager Detailed log] Exception type: {type(e).__name__}")
            logger.error(f"❌ [DataSourceManager Detailed log] Exception information: {str(e)}")
            import traceback
            logger.error(f"❌ [DataSourceManager Detailed log] exception stack: {traceback.format_exc()}")
            raise

    def _get_akshare_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """Use AKShare to obtain multi-period data - including technical indicator calculations"""
        logger.debug(f"📊 [AKShare] Call parameters: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        start_time = time.time()
        try:
            # Using AKShare's unified interface
            from .providers.china.akshare import get_akshare_provider
            provider = get_akshare_provider()

            # Use asynchronous methods to obtain historical data
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # There is no event loop in the thread pool, create a new
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            data = loop.run_until_complete(provider.get_historical_data(symbol, start_date, end_date, period))

            duration = time.time() - start_time

            if data is not None and not data.empty:
                # 🔧 Fix: Use unified formatting method, including technical indicator calculations
                # Get basic stock information
                stock_info = loop.run_until_complete(provider.get_stock_basic_info(symbol))
                stock_name = stock_info.get('name', f'股票{symbol}') if stock_info else f'股票{symbol}'

                # Call a unified formatting method (including technical indicator calculation)
                result = self._format_stock_data_response(data, symbol, stock_name, start_date, end_date)

                logger.debug(f"📊 [AKShare] 调用成功: 耗时={duration:.2f}s, 数据条数={len(data)}, 结果长度={len(result)}")
                logger.info(f"✅ [AKShare] Calculated technical indicators: MA5/10/20/60, MACD, RSI, BOLL")
                return result
            else:
                result = f"❌ 未能获取{symbol}的股票数据"
                logger.warning(f"⚠️ [AKShare] Data is empty: Time consuming={duration:.2f}s")
                return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [AKShare] 调用失败: {e}, 耗时={duration:.2f}s", exc_info=True)
            return f"❌ AKShare获取{symbol}数据失败: {e}"

    def _get_baostock_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """Use BaoStock to obtain multi-period data - including technical indicator calculations"""
        # Use BaoStock's unified interface
        from .providers.china.baostock import get_baostock_provider
        provider = get_baostock_provider()

        # Use asynchronous methods to obtain historical data
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # There is no event loop in the thread pool, create a new
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        data = loop.run_until_complete(provider.get_historical_data(symbol, start_date, end_date, period))

        if data is not None and not data.empty:
            # 🔧 Fix: Use unified formatting method, including technical indicator calculations
            # Get basic stock information
            stock_info = loop.run_until_complete(provider.get_stock_basic_info(symbol))
            stock_name = stock_info.get('name', f'股票{symbol}') if stock_info else f'股票{symbol}'

            # Call a unified formatting method (including technical indicator calculation)
            result = self._format_stock_data_response(data, symbol, stock_name, start_date, end_date)

            logger.info(f"✅ [BaoStock] Calculated technical indicators: MA5/10/20/60, MACD, RSI, BOLL")
            return result
        else:
            return f"❌ 未能获取{symbol}的股票数据"

    # TDX Data retrieval method has been removed
    # def _get_tdx_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
    #     """Using TDX to obtain multi-period data (Removed)"""
    #     logger.error(f"❌ TDX The data source is no longer supported")
    #     return f"❌ TDX The data source is no longer supported"

    def _try_fallback_sources(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> tuple[str, str | None]:
        """
        Try alternative data sources - avoid recursive calls

        Returns:
            tuple[str, str | None]: (Result string, The actual data source name used)
        """
        logger.info(f"🔄 [{self.current_source.value}] 失败，尝试备用数据源获取{period}数据: {symbol}")

        # 🔥 Get data source priority order from database (identify markets based on ticker)
        # Note: MongoDB is not included because MongoDB has the highest priority and will not be tried again if it fails.
        fallback_order = self._get_data_source_priority_order(symbol)

        for source in fallback_order:
            if source != self.current_source and source in self.available_sources:
                try:
                    logger.info(f"🔄 [备用数据源] 尝试 {source.value} 获取{period}数据: {symbol}")

                    # Directly call specific data source methods to avoid recursion
                    if source == ChinaDataSource.TUSHARE:
                        result = self._get_tushare_data(symbol, start_date, end_date, period)
                    elif source == ChinaDataSource.AKSHARE:
                        result = self._get_akshare_data(symbol, start_date, end_date, period)
                    elif source == ChinaDataSource.BAOSTOCK:
                        result = self._get_baostock_data(symbol, start_date, end_date, period)
                    # TDX Removed
                    else:
                        logger.warning(f"⚠️ 未知数据源: {source.value}")
                        continue

                    if "❌" not in result:
                        logger.info(f"✅ [备用数据源-{source.value}] 成功获取{period}数据: {symbol}")
                        return result, source.value  # Return results and the actual data source used
                    else:
                        logger.warning(f"⚠️ [备用数据源-{source.value}] 返回错误结果: {symbol}")

                except Exception as e:
                    logger.error(f"❌ [备用数据源-{source.value}] 获取失败: {symbol}, 错误: {e}")
                    continue

        logger.error(f"❌ [所有数据源失败] 无法获取{period}数据: {symbol}")
        return f"❌ 所有数据源都无法获取{symbol}的{period}数据", None

    def get_stock_info(self, symbol: str) -> Dict:
        """
        Obtain basic stock information, support multiple data sources and automatic downgrade
        Priority:MongoDB → Tushare → AKShare → BaoStock
        """
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取股票信息: {symbol}")

        # Prefer using App Mongo cache (when ta_use_app_cache=True) 
        try:
            from tradingagents.config.runtime_settings import use_app_cache_enabled  # type: ignore
            use_cache = use_app_cache_enabled(False)
            logger.info(f"🔧 [Configuration check] use_app_cache_enabled() return value: {use_cache}")
        except Exception as e:
            logger.error(f"❌ [Configuration check] use_app_cache_enabled() call failed: {e}", exc_info=True)
            use_cache = False

        logger.info(f"🔧 [Configuration] ta_use_app_cache={use_cache}, current_source={self.current_source.value}")

        if use_cache:

            try:
                from .cache.app_adapter import get_basics_from_cache, get_market_quote_dataframe
                doc = get_basics_from_cache(symbol)
                if doc:
                    name = doc.get('name') or doc.get('stock_name') or ''
                    # Standardize industries and sectors (avoid"Small and medium-sized board/GEM"Segment values are mistakenly used as industries)
                    board_labels = {'主板', '中小板', '创业板', '科创板'}
                    raw_industry = (doc.get('industry') or doc.get('industry_name') or '').strip()
                    sec_or_cat = (doc.get('sec') or doc.get('category') or '').strip()
                    market_val = (doc.get('market') or '').strip()
                    industry_val = raw_industry or sec_or_cat or '未知'
                    changed = False
                    if raw_industry in board_labels:
                        # If industry is the sector name, use it for market; use industry instead for a more detailed classification (sec/category)
                        if not market_val:
                            market_val = raw_industry
                            changed = True
                        if sec_or_cat:
                            industry_val = sec_or_cat
                            changed = True
                    if changed:
                        try:
                            logger.debug(f"🔧 [字段归一化] industry原值='{raw_industry}' → 行业='{industry_val}', 市场/板块='{market_val or doc.get('market', '未知')}'")
                        except Exception:
                            pass

                    result = {
                        'symbol': symbol,
                        'name': name or f'股票{symbol}',
                        'area': doc.get('area', '未知'),
                        'industry': industry_val or '未知',
                        'market': market_val or doc.get('market', '未知'),
                        'list_date': doc.get('list_date', '未知'),
                        'source': 'app_cache'
                    }
                    # Add snapshot quotes (if existing)
                    try:
                        df = get_market_quote_dataframe(symbol)
                        if df is not None and not df.empty:
                            row = df.iloc[-1]
                            result['current_price'] = row.get('close')
                            result['change_pct'] = row.get('pct_chg')
                            result['volume'] = row.get('volume')
                            result['quote_date'] = row.get('date')
                            result['quote_source'] = 'market_quotes'
                            logger.info(f"✅ [stock information] Additional quotes | price={result['current_price']} pct={result['change_pct']} vol={result['volume']} code={symbol}")
                    except Exception as _e:
                        logger.debug(f"Attaching quotes failed (ignored):{_e}")

                    if name:
                        logger.info(f"✅ [Data source: MongoDB-stock_basic_info] successfully obtained: {symbol}")
                        return result
                    else:
                        logger.warning(f"⚠️ [Data source: MongoDB] No valid name found: {symbol}, Downgrade to other data sources")
            except Exception as e:
                logger.error(f"❌ [Data source: MongoDB Abnormal] Failed to obtain stock information: {e}", exc_info=True)


        # Try the current data source first
        try:
            if self.current_source == ChinaDataSource.TUSHARE:
                from .interface import get_china_stock_info_tushare
                info_str = get_china_stock_info_tushare(symbol)
                result = self._parse_stock_info_string(info_str, symbol)

                # Check whether valid information is obtained
                if result.get('name') and result['name'] != f'股票{symbol}':
                    logger.info(f"✅ [Data source: Tushare-stock information] successfully obtained: {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ [Data source: Tushare failed] Return invalid information, try to downgrade: {symbol}")
                    return self._try_fallback_stock_info(symbol)
            else:
                # LOCAL / Unknown data source: Read basic information directly from MongoDB without calling get_data_adapter()
                try:
                    from app.core.database import get_mongo_db_sync
                    from tradingagents.utils.stock_utils import StockUtils
                    db = get_mongo_db_sync()
                    code6 = str(symbol).zfill(6)
                    is_fund = StockUtils.is_fund(code6)
                    if is_fund:
                        doc = db.etf_basic_info.find_one(
                            {"$or": [{"symbol": code6}, {"code": code6}]},
                            {"_id": 0}
                        )
                        if doc:
                            return {
                                'symbol': symbol,
                                'name': doc.get('name') or doc.get('fund_name') or f'ETF{symbol}',
                                'area': '未知',
                                'industry': 'ETF基金',
                                'market': 'ETF',
                                'list_date': doc.get('list_date', '未知'),
                                'source': 'etf_basic_info'
                            }
                    else:
                        doc = db.stock_basic_info.find_one(
                            {"$or": [{"symbol": code6}, {"code": code6}]},
                            {"_id": 0}
                        )
                        if doc:
                            return {
                                'symbol': symbol,
                                'name': doc.get('name') or doc.get('stock_name') or f'股票{symbol}',
                                'area': doc.get('area', '未知'),
                                'industry': doc.get('industry', '未知'),
                                'market': doc.get('market', '未知'),
                                'list_date': doc.get('list_date', '未知'),
                                'source': 'local_mongo'
                            }
                except Exception as db_e:
                    logger.warning(f"⚠️ [LOCAL] Direct reading of MongoDB failed: {db_e}")

                return self._try_fallback_stock_info(symbol)

        except Exception as e:
            logger.error(f"❌ [数据来源: {self.current_source.value}异常] 获取股票信息失败: {e}", exc_info=True)
            return self._try_fallback_stock_info(symbol)

    def get_stock_basic_info(self, stock_code: str = None) -> Optional[Dict[str, Any]]:
        """
        Get basic stock information (compatible with stock_data_service interface)

        Args:
            stock_code: Stock code, if None returns a list of all stocks

        Returns:
            Dict: A dictionary of stock information, or an error dictionary containing an error field
        """
        if stock_code is None:
            # Return to all stocks list
            logger.info("📊 获取所有股票列表")
            try:
                # Try to get from MongoDB
                from tradingagents.config.database_manager import get_database_manager
                db_manager = get_database_manager()
                if db_manager and db_manager.is_mongodb_available():
                    collection = db_manager.mongodb_db['stock_basic_info']
                    stocks = list(collection.find({}, {'_id': 0}))
                    if stocks:
                        logger.info(f"✅ 从MongoDB获取所有股票: {len(stocks)}条")
                        return stocks
            except Exception as e:
                logger.warning(f"⚠️ Failed to get all stocks from MongoDB: {e}")

            # Downgrade: Return empty list
            return []

        # Get individual stock information
        try:
            result = self.get_stock_info(stock_code)
            if result and result.get('name'):
                return result
            else:
                return {'error': f'未找到股票 {stock_code} 的信息'}
        except Exception as e:
            logger.error(f"❌ 获取股票信息失败: {e}")
            return {'error': str(e)}

    def get_stock_data_with_fallback(self, stock_code: str, start_date: str, end_date: str) -> str:
        """
        Get stock data (compatible with stock_data_service interface)

        Args:
            stock_code: Stock code
            start_date: start date
            end_date: end date

        Returns:
            str: Formatted stock data reports
        """
        logger.info(f"📊 获取股票数据: {stock_code} ({start_date} 到 {end_date})")

        try:
            # Use a unified data acquisition interface
            return self.get_stock_data(stock_code, start_date, end_date)
        except Exception as e:
            logger.error(f"❌ 获取股票数据失败: {e}")
            return f"❌ 获取股票数据失败: {str(e)}\n\n💡 建议：\n1. 检查网络连接\n2. 确认股票代码格式正确\n3. 检查数据源配置"

    def _try_fallback_stock_info(self, symbol: str) -> Dict:
        """Try using alternate data sources to get basic stock information"""
        logger.error(f"🔄 {self.current_source.value}Failure, try alternative data sources to obtain stock information...")

        # Get all available data sources (list of enumerated objects)
        available_sources = [s for s in self.available_sources if s != self.current_source]

        # Try all alternative data sources
        for source in available_sources:
            try:
                logger.info(f"🔄 Try alternate data sources for stock information: {source}")

                # Get stock information based on data source type
                if source == ChinaDataSource.TUSHARE:
                    # Reuse AKShare paths (Tushare does not have independent stock_info helper)
                    result = self._get_akshare_stock_info(symbol)
                elif source == ChinaDataSource.AKSHARE:
                    result = self._get_akshare_stock_info(symbol)
                elif source == ChinaDataSource.BAOSTOCK:
                    result = self._get_baostock_stock_info(symbol)
                elif source == ChinaDataSource.LOCAL:
                    # LOCAL Branch: Direct reading of MongoDB basic information collection
                    try:
                        from app.core.database import get_mongo_db_sync
                        from tradingagents.utils.stock_utils import StockUtils
                        _db = get_mongo_db_sync()
                        _code6 = str(symbol).zfill(6)
                        _is_fund = StockUtils.is_fund(_code6)
                        _col = _db.etf_basic_info if _is_fund else _db.stock_basic_info
                        _doc = _col.find_one({"$or": [{"symbol": _code6}, {"code": _code6}]}, {"_id": 0})
                        result = {
                            'symbol': symbol,
                            'name': (_doc or {}).get('name') or f'股票{symbol}',
                            'source': 'local_mongo'
                        } if _doc else {'symbol': symbol, 'name': f'股票{symbol}'}
                    except Exception as _le:
                        result = {'symbol': symbol, 'name': f'股票{symbol}'}
                else:
                    logger.warning(f"⚠️ [股票信息] {source}不支持股票信息获取")
                    continue

                # Check whether valid information is obtained
                if result.get('name') and result['name'] != f'股票{symbol}':
                    logger.info(f"✅ [Data source: Alternate data source] Downgraded successfully to obtain stock information: {source.value}")
                    return result
                else:
                    logger.warning(f"⚠️ [数据来源: {source.value}] 返回无效信息")

            except Exception as e:
                logger.error(f"❌ 备用数据源{source}失败: {e}")
                continue

        # All data sources fail, returning default values
        logger.error(f"❌ 所有数据源都无法获取{symbol}的股票信息")
        return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'unknown'}

    def _get_akshare_stock_info(self, symbol: str) -> Dict:
        """Use AKShare to get basic stock information

        🔥 Important: AKShare needs to distinguish between stocks and indices
        - For 000001, if no suffix is added, it will be recognized as"Shenzhen Component Index" (Index)
        - For stocks, the full code is required (such as sz000001 or sh600000)
        """
        try:
            import akshare as ak

            # 🔥 Convert stock symbol to AKShare format
            # AKShare The stock_individual_info_em needs to be used "sz000001" or "sh600000" Format
            if symbol.startswith('6'):
                # Shanghai stocks:600000 -> sh600000
                akshare_symbol = f"sh{symbol}"
            elif symbol.startswith(('0', '3', '2')):
                # Shenzhen stocks:000001 -> sz000001
                akshare_symbol = f"sz{symbol}"
            elif symbol.startswith(('8', '4', '92')):
                # Beijing stocks:830000/920985 -> bj830000/bj920985 (920 Unified number segment starting from 2025-10)
                akshare_symbol = f"bj{symbol}"
            else:
                # In other cases, use the original code directly
                akshare_symbol = symbol

            logger.debug(f"📊 [AKShare股票信息] 原始代码: {symbol}, AKShare格式: {akshare_symbol}")

            # Try to get individual stock information
            stock_info = ak.stock_individual_info_em(symbol=akshare_symbol)

            if stock_info is not None and not stock_info.empty:
                # Convert to dictionary format
                info = {'symbol': symbol, 'source': 'akshare'}

                # Extract stock name
                name_row = stock_info[stock_info['item'] == '股票简称']
                if not name_row.empty:
                    stock_name = name_row['value'].iloc[0]
                    info['name'] = stock_name
                    logger.info(f"✅ [AKShare stock information] {symbol} -> {stock_name}")
                else:
                    info['name'] = f'股票{symbol}'
                    logger.warning(f"⚠️ [AKShare stock information] Stock short name not found: {symbol}")

                # Extract additional information
                info['area'] = '未知'  # AKShare No region information
                info['industry'] = '未知'  # Can be obtained through other APIs
                info['market'] = '未知'  # Can be inferred based on stock code
                info['list_date'] = '未知'  # Can be obtained through other APIs

                return info
            else:
                logger.warning(f"⚠️ [AKShare stock information] Return empty data: {symbol}")
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'akshare'}

        except Exception as e:
            logger.error(f"❌ [股票信息] AKShare获取失败: {symbol}, 错误: {e}")
            return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'akshare', 'error': str(e)}

    def _get_baostock_stock_info(self, symbol: str) -> Dict:
        """Use BaoStock to obtain basic stock information"""
        try:
            import baostock as bs

            # Convert stock symbol format
            if symbol.startswith('6'):
                bs_code = f"sh.{symbol}"
            else:
                bs_code = f"sz.{symbol}"

            # Login BaoStock
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"❌ [stock information] BaoStock Login failed: {lg.error_msg}")
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock'}

            # Query basic stock information
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code != '0':
                bs.logout()
                logger.error(f"❌ [stock information] BaoStock Query failed: {rs.error_msg}")
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock'}

            # Parse results
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())

            # Log out
            bs.logout()

            if data_list:
                # BaoStock Return format: [code, code_name, ipoDate, outDate, type, status]
                info = {'symbol': symbol, 'source': 'baostock'}
                info['name'] = data_list[0][1]  # code_name
                info['area'] = '未知'  # BaoStock No region information
                info['industry'] = '未知'  # BaoStock No industry information
                info['market'] = '未知'  # Can be inferred based on stock code
                info['list_date'] = data_list[0][2]  # ipoDate

                return info
            else:
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock'}

        except Exception as e:
            logger.error(f"❌ [stock information] BaoStock Failed to obtain: {e}")
            return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock', 'error': str(e)}

    def _parse_stock_info_string(self, info_str: str, symbol: str) -> Dict:
        """解析股票信息字符串为字典"""
        try:
            info = {'symbol': symbol, 'source': self.current_source.value}
            lines = info_str.split('\n')

            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    if '股票名称' in key:
                        info['name'] = value
                    elif '所属行业' in key:
                        info['industry'] = value
                    elif '所属地区' in key:
                        info['area'] = value
                    elif '上市市场' in key:
                        info['market'] = value
                    elif '上市日期' in key:
                        info['list_date'] = value

            return info

        except Exception as e:
            logger.error(f"⚠️ 解析股票信息失败: {e}")
            return {'symbol': symbol, 'name': f'股票{symbol}', 'source': self.current_source.value}

    # ==================== How to obtain fundamental data ====================

    def _get_mongodb_fundamentals(self, symbol: str) -> str:
        """Get financial data from MongoDB"""
        logger.debug(f"📊 [MongoDB] Call parameters: symbol={symbol}")

        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
            import pandas as pd
            adapter = get_mongodb_cache_adapter()

            # Get financial data from MongoDB
            financial_data = adapter.get_financial_data(symbol)

            # Check data type and content
            if financial_data is not None:
                # If it is a DataFrame, convert to a list of dictionaries
                if isinstance(financial_data, pd.DataFrame):
                    if not financial_data.empty:
                        logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} ({len(financial_data)}条记录)")
                        # Convert to list of dictionaries
                        financial_dict_list = financial_data.to_dict('records')
                        # Format financial data for reports
                        return self._format_financial_data(symbol, financial_dict_list)
                    else:
                        logger.warning(f"⚠️ [Data source: MongoDB] Financial data is empty: {symbol}, Downgrade to other data sources")
                        return self._try_fallback_fundamentals(symbol)
                # if it is a list
                elif isinstance(financial_data, list) and len(financial_data) > 0:
                    logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} ({len(financial_data)}条记录)")
                    return self._format_financial_data(symbol, financial_data)
                # If it's a single dictionary (this is the format MongoDB actually returns)
                elif isinstance(financial_data, dict):
                    logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} (单条记录)")
                    # Wrap a single dictionary into a list
                    financial_dict_list = [financial_data]
                    return self._format_financial_data(symbol, financial_dict_list)
                else:
                    logger.warning(f"⚠️ [Data source: MongoDB] No financial data found: {symbol}, Downgrade to other data sources")
                    return self._try_fallback_fundamentals(symbol)
            else:
                logger.warning(f"⚠️ [Data source: MongoDB] No financial data found: {symbol}, Downgrade to other data sources")
                # MongoDB No data, downgrade to other data sources
                return self._try_fallback_fundamentals(symbol)

        except Exception as e:
            logger.error(f"❌ [Data source: MongoDB Abnormal] Failed to get financial data: {e}", exc_info=True)
            # MongoDB Exception, downgrade to other data sources
            return self._try_fallback_fundamentals(symbol)

    def _get_local_fundamentals(self, symbol: str) -> str:
        """
        Get fundamental data from local data source from MongoDB stock_basic_info collection

        Args:
            symbol: Stock code

        Returns:
            str: Fundamental Analysis Report
        """
        logger.debug(f"📊 [LOCAL] Call parameters: symbol={symbol}")

        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_basic_info

            # Query conditions
            query = {
                "symbol": symbol,
                "source": "local"
            }

            # Query data
            record = collection.find_one(query)

            if not record:
                logger.info(f"🔄 [LOCAL] Fundamental data not found: {symbol}, Try alternative data sources")
                return f"❌ 本地数据源没有 {symbol} 的基本面数据"

            logger.info(f"✅ [Data source: LOCAL] Successfully obtained fundamental data: {symbol}")

            # Format fundamental data for reporting
            return self._format_local_fundamentals_report(symbol, record)

        except Exception as e:
            logger.error(f"❌ [数据来源: LOCAL异常] 获取基本面数据失败: {symbol}, 错误: {e}")
            return f"❌ Failed to obtain fundamental data from local data source: {e}"

    def _format_local_fundamentals_report(self, symbol: str, record: dict) -> str:
        """
        Formatting fundamental data from local data sources for reports

        Args:
            symbol: Stock code
            record: database records

        Returns:
            str: Formatted fundamental reports
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from tradingagents.config.runtime_settings import get_timezone_name

        # Extract basic information
        name = record.get('name', f'股票{symbol}')
        area = record.get('area', 'N/A')
        industry = record.get('industry', 'N/A')
        list_date = record.get('list_date', 'N/A')

        # Extract financial data
        total_mv = record.get('total_mv', 0)  # Total market value (100 million yuan)
        circ_mv = record.get('circ_mv', 0)    # Circulation market value (100 million yuan)
        pe_ttm = record.get('pe_ttm', 0)      # P/E ratio TTM
        pb = record.get('pb', 0)              # price to book ratio
        ps_ttm = record.get('ps_ttm', 0)      # price to sales ratio TTM

        # Extract equity data
        total_share = record.get('total_share', 0)  # Total share capital (10,000 shares)
        float_share = record.get('float_share', 0)  # Circulating share capital (10,000 shares)

        # Generate report
        report = f"""# {name} ({symbol}) 基本面分析

## 📊 基本信息
- **股票代码**: {symbol}
- **股票名称**: {name}
- **所属地域**: {area}
- **所属行业**: {industry}
- **上市日期**: {list_date}

## 💰 市值数据
- **总市值**: {total_mv:.2f} 亿元
- **流通市值**: {circ_mv:.2f} 亿元

## 📈 估值指标
- **市盈率(TTM)**: {pe_ttm:.2f}
- **市净率**: {pb:.2f}
- **市销率(TTM)**: {ps_ttm:.2f}

## 📊 股本结构
- **总股本**: {total_share:.2f} 万股
- **流通股本**: {float_share:.2f} 万股
- **流通比例**: {(float_share / total_share * 100) if total_share > 0 else 0:.2f}%

---
*数据来源: 本地数据源 (local)*
*生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}*
"""

        return report

    def _get_tushare_fundamentals(self, symbol: str) -> str:
        """Get fundamental data from Tushare - temporarily unavailable, needs to be implemented"""
        logger.warning(f"⚠️ Tushare Fundamental data function is temporarily unavailable")
        return f"⚠️ Tushare Fundamental data function is temporarily unavailable, please use other data sources"

    def _get_akshare_fundamentals(self, symbol: str) -> str:
        """Generate fundamental analysis from AKShare"""
        logger.debug(f"📊 [AKShare] Call parameters: symbol={symbol}")

        try:
            # AKShare No direct interface to fundamental data, use generative analysis
            logger.info(f"📊 [Data source: AKShare-Generate analysis] Generate fundamental analysis: {symbol}")
            return self._generate_fundamentals_analysis(symbol)

        except Exception as e:
            logger.error(f"❌ [Data source: AKShare Abnormal] Failed to generate fundamental analysis: {e}")
            return f"❌ 生成{symbol}基本面分析失败: {e}"

    def _get_valuation_indicators(self, symbol: str) -> Dict:
        """Get valuation metrics from stock_basic_info collection"""
        try:
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                return {}
                
            client = db_manager.get_mongodb_client()
            db = client[db_manager.config.mongodb_config.database_name]
            
            # Get valuation metrics from stock_basic_info collection
            collection = db['stock_basic_info']
            result = collection.find_one({'ts_code': symbol})
            
            if result:
                return {
                    'pe': result.get('pe'),
                    'pb': result.get('pb'),
                    'pe_ttm': result.get('pe_ttm'),
                    'total_mv': result.get('total_mv'),
                    'circ_mv': result.get('circ_mv')
                }
            return {}
            
        except Exception as e:
            logger.error(f"获取{symbol}估值指标失败: {e}")
            return {}

    def _format_financial_data(self, symbol: str, financial_data: List[Dict]) -> str:
        """格式化财务数据为报告"""
        try:
            if not financial_data or len(financial_data) == 0:
                return f"❌ 未找到{symbol}的财务数据"

            # Get the latest financial data
            latest = financial_data[0]

            # Build report
            report = f"📊 {symbol} Fundamental data (from MongoDB)\n\n"

            # Basic information
            report += f"📅 报告期: {latest.get('report_period', latest.get('end_date', '未知'))}\n"
            report += f"📈 Data source: MongoDB financial database\n\n"

            # financial indicators
            report += "💰 财务指标:\n"
            revenue = latest.get('revenue') or latest.get('total_revenue')
            if revenue is not None:
                report += f"   营业总收入: {revenue:,.2f}\n"
            
            net_profit = latest.get('net_profit') or latest.get('net_income')
            if net_profit is not None:
                report += f"   净利润: {net_profit:,.2f}\n"
                
            total_assets = latest.get('total_assets')
            if total_assets is not None:
                report += f"   总资产: {total_assets:,.2f}\n"
                
            total_liab = latest.get('total_liab')
            if total_liab is not None:
                report += f"   总负债: {total_liab:,.2f}\n"
                
            total_equity = latest.get('total_equity')
            if total_equity is not None:
                report += f"   股东权益: {total_equity:,.2f}\n"

            # Valuation metrics - obtained from the stock_basic_info collection
            report += "\n📊 估值指标:\n"
            valuation_data = self._get_valuation_indicators(symbol)
            if valuation_data:
                pe = valuation_data.get('pe')
                if pe is not None:
                    report += f"   市盈率(PE): {pe:.2f}\n"
                    
                pb = valuation_data.get('pb')
                if pb is not None:
                    report += f"   市净率(PB): {pb:.2f}\n"
                    
                pe_ttm = valuation_data.get('pe_ttm')
                if pe_ttm is not None:
                    report += f"   P/E ratio TTM(PE_TTM): {pe_ttm:.2f}\n"
                    
                total_mv = valuation_data.get('total_mv')
                if total_mv is not None:
                    report += f"   总市值: {total_mv:.2f}亿元\n"
                    
                circ_mv = valuation_data.get('circ_mv')
                if circ_mv is not None:
                    report += f"   流通市值: {circ_mv:.2f}亿元\n"
            else:
                # If not available from stock_basic_info, try calculating from financial data
                pe = latest.get('pe')
                if pe is not None:
                    report += f"   市盈率(PE): {pe:.2f}\n"
                    
                pb = latest.get('pb')
                if pb is not None:
                    report += f"   市净率(PB): {pb:.2f}\n"
                    
                ps = latest.get('ps')
                if ps is not None:
                    report += f"   市销率(PS): {ps:.2f}\n"

            # Profitability
            report += "\n💹 盈利能力:\n"
            roe = latest.get('roe')
            if roe is not None:
                report += f"   净资产收益率(ROE): {roe:.2f}%\n"
                
            roa = latest.get('roa')
            if roa is not None:
                report += f"   总资产收益率(ROA): {roa:.2f}%\n"
                
            gross_margin = latest.get('gross_margin')
            if gross_margin is not None:
                report += f"   毛利率: {gross_margin:.2f}%\n"
                
            netprofit_margin = latest.get('netprofit_margin') or latest.get('net_margin')
            if netprofit_margin is not None:
                report += f"   净利率: {netprofit_margin:.2f}%\n"

            # cash flow
            n_cashflow_act = latest.get('n_cashflow_act')
            if n_cashflow_act is not None:
                report += "\n💰 现金流:\n"
                report += f"   经营活动现金流: {n_cashflow_act:,.2f}\n"
                
                n_cashflow_inv_act = latest.get('n_cashflow_inv_act')
                if n_cashflow_inv_act is not None:
                    report += f"   投资活动现金流: {n_cashflow_inv_act:,.2f}\n"
                    
                c_cash_equ_end_period = latest.get('c_cash_equ_end_period')
                if c_cash_equ_end_period is not None:
                    report += f"   期末现金及等价物: {c_cash_equ_end_period:,.2f}\n"

            report += f"\n📝 共有 {len(financial_data)} 期财务数据\n"

            return report

        except Exception as e:
            logger.error(f"❌ 格式化财务数据失败: {e}")
            return f"❌ 格式化{symbol}财务数据失败: {e}"

    def _generate_fundamentals_analysis(self, symbol: str) -> str:
        """生成基本的基本面分析"""
        try:
            # Get basic stock information
            stock_info = self.get_stock_info(symbol)

            report = f"📊 {symbol} 基本面分析（生成）\n\n"
            report += f"📈 股票名称: {stock_info.get('name', '未知')}\n"
            report += f"🏢 所属行业: {stock_info.get('industry', '未知')}\n"
            report += f"📍 所属地区: {stock_info.get('area', '未知')}\n"
            report += f"📅 上市日期: {stock_info.get('list_date', '未知')}\n"
            report += f"🏛️ 交易所: {stock_info.get('exchange', '未知')}\n\n"

            report += "⚠️ Note: Detailed financial data needs to be obtained from the data source\n"
            report += "💡 Suggestions: Enable MongoDB caching for complete financial data\n"

            return report

        except Exception as e:
            logger.error(f"❌ 生成基本面分析失败: {e}")
            return f"❌ 生成{symbol}基本面分析失败: {e}"

    def _try_fallback_fundamentals(self, symbol: str) -> str:
        """基本面数据降级处理"""
        logger.error(f"🔄 {self.current_source.value}Failure, try alternative data sources to obtain fundamentals...")

        # 🔥 Get data source priority order from database (identify markets based on ticker)
        fallback_order = self._get_data_source_priority_order(symbol)

        for source in fallback_order:
            if source != self.current_source and source in self.available_sources:
                try:
                    logger.info(f"🔄 Try alternative data sources for fundamentals: {source.value}")

                    # Directly call specific data source methods to avoid recursion
                    if source == ChinaDataSource.TUSHARE:
                        result = self._get_tushare_fundamentals(symbol)
                    elif source == ChinaDataSource.AKSHARE:
                        result = self._get_akshare_fundamentals(symbol)
                    else:
                        continue

                    if result and "❌" not in result:
                        logger.info(f"✅ [Data source: Alternate data source] Downgrade successfully to obtain fundamentals: {source.value}")
                        return result
                    else:
                        logger.warning(f"⚠️ 备用数据源{source.value}返回错误结果")

                except Exception as e:
                    logger.error(f"❌ 备用数据源{source.value}异常: {e}")
                    continue

        # All data sources fail, generating basic analysis
        logger.warning(f"⚠️ [Data source: Generate analysis] All data sources failed, generating basic analysis: {symbol}")
        return self._generate_fundamentals_analysis(symbol)

    def _get_mongodb_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """Get news data from MongoDB"""
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
            adapter = get_mongodb_cache_adapter()

            # Get news data from MongoDB
            news_data = adapter.get_news_data(symbol, hours_back=hours_back, limit=limit)

            if news_data and len(news_data) > 0:
                logger.info(f"✅ [数据来源: MongoDB-新闻] 成功获取: {symbol or '市场新闻'} ({len(news_data)}条)")
                return news_data
            else:
                logger.warning(f"⚠️ [Data source: MongoDB] News not found: {symbol or 'market news'}, Downgrade to other data sources")
                return self._try_fallback_news(symbol, hours_back, limit)

        except Exception as e:
            logger.error(f"❌ [Data source: MongoDB] Failed to get news: {e}")
            return self._try_fallback_news(symbol, hours_back, limit)

    def _get_tushare_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """Get news data from Tushare"""
        try:
            # Tushare The news function is temporarily unavailable and returns an empty list.
            logger.warning(f"⚠️ [Data source: Tushare] Tushare News function is temporarily unavailable")
            return []

        except Exception as e:
            logger.error(f"❌ [Data source: Tushare] Failed to get news: {e}")
            return []

    def _get_akshare_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """Get news data from AKShare"""
        try:
            # AKShare The news function is temporarily unavailable and returns an empty list.
            logger.warning(f"⚠️ [Data source: AKShare] AKShare News function is temporarily unavailable")
            return []

        except Exception as e:
            logger.error(f"❌ [Data source: AKShare] Failed to get news: {e}")
            return []

    def _try_fallback_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """新闻数据降级处理"""
        logger.error(f"🔄 {self.current_source.value}Failed, try alternate data sources for news...")

        # 🔥 Get data source priority order from database (identify markets based on ticker)
        fallback_order = self._get_data_source_priority_order(symbol)

        for source in fallback_order:
            if source != self.current_source and source in self.available_sources:
                try:
                    logger.info(f"🔄 Try alternative data sources for news: {source.value}")

                    # Directly call specific data source methods to avoid recursion
                    if source == ChinaDataSource.TUSHARE:
                        result = self._get_tushare_news(symbol, hours_back, limit)
                    elif source == ChinaDataSource.AKSHARE:
                        result = self._get_akshare_news(symbol, hours_back, limit)
                    else:
                        continue

                    if result and len(result) > 0:
                        logger.info(f"✅ [Data source: Alternate data source] Get news about downgrade successfully: {source.value}")
                        return result
                    else:
                        logger.warning(f"⚠️ 备用数据源{source.value}未返回新闻")

                except Exception as e:
                    logger.error(f"❌ 备用数据源{source.value}异常: {e}")
                    continue

        # All data sources fail
        logger.warning(f"⚠️ [Data source: All data sources failed] Unable to get news: {symbol or 'market news'}")
        return []


# Global data source manager instance
_data_source_manager = None

def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager


def get_china_stock_data_unified(symbol: str, start_date: str, end_date: str) -> str:
    """
    Unified Chinese stock data acquisition interface
    Automatically use configured data sources and support alternative data sources

    Args:
        symbol: Stock code
        start_date: start date
        end_date: end date

    Returns:
        str: Formatted stock data
    """
    from tradingagents.utils.logging_init import get_logger


    # Add detailed ticker tracking logs
    logger.info(f"🔍 [股票代码追踪] data_source_manager.get_china_stock_data_unified 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
    logger.info(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(symbol))}")
    logger.info(f"🔍 [Stock symbol tracking] ticker character: {list(str(symbol))}")

    manager = get_data_source_manager()
    logger.info(f"🔍 [Stock symbol tracking] Call manager.get_stock_data, passing in parameters: symbol='{symbol}', start_date='{start_date}', end_date='{end_date}'")
    result = manager.get_stock_data(symbol, start_date, end_date)
    # Analyze the details of the returned results
    if result:
        lines = result.split('\n')
        data_lines = [line for line in lines if '2025-' in line and symbol in line]
        logger.info(f"🔍 [股票代码追踪] 返回结果统计: 总行数={len(lines)}, 数据行数={len(data_lines)}, 结果长度={len(result)}字符")
        logger.info(f"🔍 [Stock symbol tracking] Return the first 500 characters of the result: {result[:500]}")
        if len(data_lines) > 0:
            logger.info(f"🔍 [股票代码追踪] 数据行示例: 第1行='{data_lines[0][:100]}', 最后1行='{data_lines[-1][:100]}'")
    else:
        logger.info(f"🔍 [Stock symbol tracking] Return results: None")
    return result


def get_china_stock_info_unified(symbol: str) -> Dict:
    """
    Unified Chinese stock information acquisition interface

    Args:
        symbol: Stock code

    Returns:
        Dict: Basic stock information
    """
    manager = get_data_source_manager()
    return manager.get_stock_info(symbol)


# Global data source manager instance
_data_source_manager = None

def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager

# ==================== Compatibility interface ====================
# In order to be compatible with stock_data_service, the same interface is provided

def get_stock_data_service() -> DataSourceManager:
    """
    Get the stock data service instance (compatible with the stock_data_service interface)

    ⚠️ This function is a compatibility interface and actually returns a DataSourceManager instance
    Recommended to use directly get_data_source_manager()
    """
    return get_data_source_manager()


# ==================== US stock data source manager ====================

class USDataSourceManager:
    """
    US stock data source manager

    Supported data sources:
    - yfinance: Stock Prices and Technical Indicators (Free)
    - alpha_vantage: Fundamental and news data (requires API Key)
    - finnhub: Alternate data source (requires API Key)
    - mongodb: Caching data sources (highest priority)
    """

    def __init__(self):
        """初始化美股数据源管理器"""
        # Check if MongoDB caching is enabled
        self.use_mongodb_cache = self._check_mongodb_enabled()

        # Check available data sources
        self.available_sources = self._check_available_sources()

        # Set default data source
        self.default_source = self._get_default_source()
        self.current_source = self.default_source

        logger.info(f"📊 US stock data source manager initialization completed")
        logger.info(f"   MongoDB缓存: {'✅ 已启用' if self.use_mongodb_cache else '❌ 未启用'}")
        logger.info(f"   默认数据源: {self.default_source.value}")
        logger.info(f"   可用数据源: {[s.value for s in self.available_sources]}")

    def _check_mongodb_enabled(self) -> bool:
        """Check if MongoDB caching is enabled"""
        from tradingagents.config.runtime_settings import use_app_cache_enabled
        return use_app_cache_enabled()

    def _get_data_source_priority_order(self, symbol: Optional[str] = None) -> List[USDataSource]:
        """
        Get the priority order of US stock data sources from the database (for downgrade)

        Args:
            symbol: Stock code

        Returns:
            List of data sources ordered by priority (excluding MongoDB)
        """
        try:
            # Read data source configuration from database
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()

            # method 1: Read from the datasource_groupings collection (recommended)
            groupings_collection = db.datasource_groupings
            groupings = list(groupings_collection.find({
                "market_category_id": "us_stocks",
                "enabled": True
            }).sort("priority", -1))  # Sort in descending order, with higher priority first

            if groupings:
                # Convert to USDataSource enumeration
                # 🔥 Data source name mapping (database name → USDataSource enum)
                source_mapping = {
                    'yfinance': USDataSource.YFINANCE,
                    'yahoo_finance': USDataSource.YFINANCE,  # Alias
                    'alpha_vantage': USDataSource.ALPHA_VANTAGE,
                    'finnhub': USDataSource.FINNHUB,
                }

                result = []
                mcp_names = []
                for grouping in groupings:
                    ds_name = grouping.get('data_source_name', '')
                    source_type = grouping.get('source_type', 'builtin')
                    if source_type == 'mcp':
                        # 🔌 MCP Data source: record but do not join the synchronization degradation cycle yet
                        mcp_names.append(ds_name)
                        continue
                    if ds_name.lower() in source_mapping:
                        source = source_mapping[ds_name.lower()]
                        # Exclude MongoDB (MongoDB is the highest priority and does not participate in downgrade)
                        if source != USDataSource.MONGODB and source in self.available_sources:
                            result.append(source)

                if mcp_names:
                    logger.info(
                        f"🔌 [U.S. stock data source priority] detected {len(mcp_names)} MCP data source (the data has participated in the downgrade chain through MongoDB): {mcp_names}"
                    )

                if result:
                    logger.info(f"✅ [U.S. stock data source priority] Read from database: {[s.value for s in result]}")
                    return result

            logger.warning("⚠️ [U.S. stock data source priority] There is no configuration in the database, the default order is used")
        except Exception as e:
            logger.warning(f"⚠️ [U.S. stock data source priority] Failed to read from database: {e}, Use default order")

        # fallback to default order
        # Default order:yfinance > Alpha Vantage > Finnhub
        default_order = [
            USDataSource.YFINANCE,
            USDataSource.ALPHA_VANTAGE,
            USDataSource.FINNHUB,
        ]
        # Only return available data sources
        return [s for s in default_order if s in self.available_sources]

    def _get_default_source(self) -> USDataSource:
        """获取默认数据源"""
        # If MongoDB caching is enabled, MongoDB acts as the highest priority data source
        if self.use_mongodb_cache:
            return USDataSource.MONGODB

        # Obtained from environment variables, used by default yfinance
        env_source = os.getenv('DEFAULT_US_DATA_SOURCE', DataSourceCode.YFINANCE).lower()

        # map to enum
        source_mapping = {
            DataSourceCode.YFINANCE: USDataSource.YFINANCE,
            DataSourceCode.ALPHA_VANTAGE: USDataSource.ALPHA_VANTAGE,
            DataSourceCode.FINNHUB: USDataSource.FINNHUB,
        }

        return source_mapping.get(env_source, USDataSource.YFINANCE)

    def _check_available_sources(self) -> List[USDataSource]:
        """
        Check available data sources

        Read the enabled status from the database and check whether the dependencies are met
        """
        available = []

        # MongoDB cache
        if self.use_mongodb_cache:
            available.append(USDataSource.MONGODB)
            logger.info("✅ MongoDB Cached data sources are available")

        # Read enabled data source list and configuration from database
        enabled_sources_in_db = self._get_enabled_sources_from_db()
        datasource_configs = self._get_datasource_configs_from_db()

        # Check yfinance
        if 'yfinance' in enabled_sources_in_db:
            try:
                import yfinance
                available.append(USDataSource.YFINANCE)
                logger.info("✅ yfinance Data source is available and enabled")
            except ImportError:
                logger.warning("⚠️ yfinance Data source is not available: yfinance library is not installed")
        else:
            logger.info("ℹ️ yfinance The data source has been disabled in the database")

        # Check Alpha Vantage
        if 'alpha_vantage' in enabled_sources_in_db:
            try:
                # The API Key is read from the database configuration first, and then read from the environment variables.
                api_key = datasource_configs.get('alpha_vantage', {}).get('api_key') or os.getenv("ALPHA_VANTAGE_API_KEY")
                if api_key:
                    available.append(USDataSource.ALPHA_VANTAGE)
                    source = "数据库配置" if datasource_configs.get('alpha_vantage', {}).get('api_key') else "环境变量"
                    logger.info(f"✅ Alpha Vantage Data source is available and enabled (API Key Source: {source})")
                else:
                    logger.warning("⚠️ Alpha Vantage Data source is not available: API Key Not configured (neither database nor environment variables found)")
            except Exception as e:
                logger.warning(f"⚠️ Alpha Vantage Data source check failed: {e}")
        else:
            logger.info("ℹ️ Alpha Vantage The data source has been disabled in the database")

        # Check Finnhub
        if 'finnhub' in enabled_sources_in_db:
            try:
                # The API Key is read from the database configuration first, and then read from the environment variables.
                api_key = datasource_configs.get('finnhub', {}).get('api_key') or os.getenv("FINNHUB_API_KEY")
                if api_key:
                    available.append(USDataSource.FINNHUB)
                    source = "数据库配置" if datasource_configs.get('finnhub', {}).get('api_key') else "环境变量"
                    logger.info(f"✅ Finnhub Data source is available and enabled (API Key Source: {source})")
                else:
                    logger.warning("⚠️ Finnhub Data source is not available: API Key Not configured (neither database nor environment variables found)")
            except Exception as e:
                logger.warning(f"⚠️ Finnhub Data source check failed: {e}")
        else:
            logger.info("ℹ️ Finnhub The data source has been disabled in the database")

        return available

    def _get_enabled_sources_from_db(self) -> List[str]:
        """Read the list of enabled data sources from the database"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()

            # Read from datasource_groupings collection
            groupings = list(db.datasource_groupings.find({
                "market_category_id": "us_stocks",
                "enabled": True
            }))

            # 🔥 Data source name mapping (database name → name used in the code)
            name_mapping = {
                'alpha vantage': 'alpha_vantage',
                'yahoo finance': 'yfinance',
                'finnhub': 'finnhub',
            }

            result = []
            for g in groupings:
                db_name = g.get('data_source_name', '').lower()
                # Convert names using a mapping table
                code_name = name_mapping.get(db_name, db_name)
                result.append(code_name)
                logger.debug(f"🔄 数据源名称映射: '{db_name}' → '{code_name}'")

            return result
        except Exception as e:
            logger.warning(f"⚠️ Reading enabled data source from database failed: {e}")
            # All enabled by default
            return ['yfinance', 'alpha_vantage', 'finnhub']

    def _get_datasource_configs_from_db(self) -> dict:
        """Read data source configuration (including API Key) from the database"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()

            # Read activated configuration from system_configs collection
            config = db.system_configs.find_one({"is_active": True})
            if not config:
                return {}

            # Extract data source configuration
            datasource_configs = config.get('data_source_configs', [])

            # Build configuration dictionary {Data source name: {api_key, api_secret, ...}}
            result = {}
            for ds_config in datasource_configs:
                name = ds_config.get('name', '').lower()
                result[name] = {
                    'api_key': ds_config.get('api_key', ''),
                    'api_secret': ds_config.get('api_secret', ''),
                    'config_params': ds_config.get('config_params', {})
                }

            return result
        except Exception as e:
            logger.warning(f"⚠️ Failed to read data source configuration from database: {e}")
            return {}

    def get_current_source(self) -> USDataSource:
        """获取当前数据源"""
        return self.current_source

    def set_current_source(self, source: USDataSource) -> bool:
        """设置当前数据源"""
        if source in self.available_sources:
            self.current_source = source
            logger.info(f"✅ 美股数据源已切换到: {source.value}")
            return True
        else:
            logger.error(f"❌ 美股数据源不可用: {source.value}")
            return False


# Global US stock data source manager example
_us_data_source_manager = None

def get_us_data_source_manager() -> USDataSourceManager:
    """Get the global US stock data source manager instance"""
    global _us_data_source_manager
    if _us_data_source_manager is None:
        _us_data_source_manager = USDataSourceManager()
    return _us_data_source_manager
