#!/usr/bin/env python3
"""
Integrated cache manager
Combines legacy caching system with new adaptive database support
Provides a backward-compatible interface
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Union
import pandas as pd

# Import unified log system
from tradingagents.utils.logging_init import setup_dataflow_logging

# Import the original cache system
from .file_cache import StockDataCache

# Import adaptive caching system
try:
    from .adaptive import AdaptiveCacheSystem
    from tradingagents.config.database_manager import get_database_manager
    ADAPTIVE_CACHE_AVAILABLE = True
except ImportError as e:
    ADAPTIVE_CACHE_AVAILABLE = False
    import logging
    logging.getLogger(__name__).debug(f"自适应缓存不可用: {e}")

class IntegratedCacheManager:
    """Integrated cache manager - intelligent selection of cache strategies"""
    
    def __init__(self, cache_dir: str = None):
        self.logger = setup_dataflow_logging()
        
        # Initialize the original cache system (as a backup)
        self.legacy_cache = StockDataCache(cache_dir)
        
        # Try to initialize the adaptive caching system
        self.adaptive_cache = None
        self.use_adaptive = False
        
        if ADAPTIVE_CACHE_AVAILABLE:
            try:
                self.adaptive_cache = AdaptiveCacheSystem(cache_dir)
                self.db_manager = get_database_manager()
                self.use_adaptive = True
                self.logger.info("✅ 自适应缓存系统已启用")
            except Exception as e:
                self.logger.warning(f"Adaptive cache system initialization failed, using legacy cache: {e}")
                self.use_adaptive = False
        else:
            self.logger.info("Adaptive caching system is not available, use traditional file caching")
        
        # Show current configuration
        self._log_cache_status()
    
    def _log_cache_status(self):
        """记录缓存状态"""
        if self.use_adaptive:
            backend = self.adaptive_cache.primary_backend
            mongodb_available = self.db_manager.is_mongodb_available()
            redis_available = self.db_manager.is_redis_available()
            
            self.logger.info(f"📊 缓存配置:")
            self.logger.info(f"  主要后端: {backend}")
            self.logger.info(f"  MongoDB: {'✅ Available' if mongodb_available else '❌ Not available'}")
            self.logger.info(f"  Redis: {'✅ Available' if redis_available else '❌ Not available'}")
            self.logger.info(f"  降级支持: {'✅ 启用' if self.adaptive_cache.fallback_enabled else '❌ 禁用'}")
        else:
            self.logger.info("📁 使用传统文件缓存系统")
    
    def save_stock_data(self, symbol: str, data: Any, start_date: str = None, 
                       end_date: str = None, data_source: str = "default") -> str:
        """
        Save stock data to cache
        
        Args:
            symbol: Stock code
            data: stock data
            start_date: start date
            end_date: end date
            data_source: data source
            
        Returns:
            cache key
        """
        if self.use_adaptive:
            # Use an adaptive caching system
            return self.adaptive_cache.save_data(
                symbol=symbol,
                data=data,
                start_date=start_date or "",
                end_date=end_date or "",
                data_source=data_source,
                data_type="stock_data"
            )
        else:
            # Use a traditional caching system
            return self.legacy_cache.save_stock_data(
                symbol=symbol,
                data=data,
                start_date=start_date,
                end_date=end_date,
                data_source=data_source
            )
    
    def load_stock_data(self, cache_key: str) -> Optional[Any]:
        """
        Load stock data from cache
        
        Args:
            cache_key: cache key
            
        Returns:
            stock data or None
        """
        if self.use_adaptive:
            # Use an adaptive caching system
            return self.adaptive_cache.load_data(cache_key)
        else:
            # Use a traditional caching system
            return self.legacy_cache.load_stock_data(cache_key)
    
    def find_cached_stock_data(self, symbol: str, start_date: str = None, 
                              end_date: str = None, data_source: str = "default",
                              max_age_hours: int = None) -> Optional[str]:
        """
        Find cached stock data
        
        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            data_source: data source
            max_age_hours: Maximum cache time (hours), use the cache system default when None TTL
            
        Returns:
            cache key or None
        """
        if self.use_adaptive:
            # Use an adaptive caching system
            cache_key = self.adaptive_cache.find_cached_data(
                symbol=symbol,
                start_date=start_date or "",
                end_date=end_date or "",
                data_source=data_source,
                data_type="stock_data"
            )

            if not cache_key:
                return None

            if max_age_hours is not None and not self._is_adaptive_cache_within_age(cache_key, max_age_hours):
                self.logger.info(f"⌛ Adaptive cache exceeds max_age_hours limit: {symbol} -> {cache_key}")
                return None

            return cache_key
        else:
            # Use a traditional caching system
            return self.legacy_cache.find_cached_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                data_source=data_source,
                max_age_hours=max_age_hours
            )

    def find_cacched_stock_data(self, symbol: str, start_date: str = None,
                               end_date: str = None, data_source: str = "default",
                               max_age_hours: int = None) -> Optional[str]:
        """Cache lookup interface compatible with historical misspellings."""
        return self.find_cached_stock_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            data_source=data_source,
            max_age_hours=max_age_hours
        )

    def _load_adaptive_cache_entry(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Read the adaptive cache underlying entry for additional TTL checking."""
        loaders = []

        if self.adaptive_cache.primary_backend == "redis":
            loaders.append(self.adaptive_cache._load_from_redis)
        elif self.adaptive_cache.primary_backend == "mongodb":
            loaders.append(self.adaptive_cache._load_from_mongodb)
        elif self.adaptive_cache.primary_backend == "file":
            loaders.append(self.adaptive_cache._load_from_file)

        if self.adaptive_cache.fallback_enabled:
            loaders.append(self.adaptive_cache._load_from_file)

        seen = set()
        for loader in loaders:
            if loader in seen:
                continue
            seen.add(loader)

            try:
                cache_entry = loader(cache_key)
            except Exception as e:
                self.logger.debug(f"⚠️ Failed to read adaptive cache metadata: {cache_key}, error={e}")
                continue

            if cache_entry:
                return cache_entry

        return None

    def _is_adaptive_cache_within_age(self, cache_key: str, max_age_hours: int) -> bool:
        """Check whether the adaptive cache falls within the time window required by the caller."""
        cache_entry = self._load_adaptive_cache_entry(cache_key)
        if not cache_entry:
            return False

        cache_timestamp = cache_entry.get("timestamp")
        if not isinstance(cache_timestamp, datetime):
            return False

        return cache_timestamp >= datetime.now() - timedelta(hours=max_age_hours)
    
    def save_news_data(self, symbol: str, data: Any, data_source: str = "default") -> str:
        """保存新闻数据"""
        if self.use_adaptive:
            return self.adaptive_cache.save_data(
                symbol=symbol,
                data=data,
                data_source=data_source,
                data_type="news_data"
            )
        else:
            return self.legacy_cache.save_news_data(symbol, data, data_source)
    
    def load_news_data(self, cache_key: str) -> Optional[Any]:
        """加载新闻数据"""
        if self.use_adaptive:
            return self.adaptive_cache.load_data(cache_key)
        else:
            return self.legacy_cache.load_news_data(cache_key)
    
    def save_fundamentals_data(self, symbol: str, data: Any, data_source: str = "default") -> str:
        """保存基本面数据"""
        if self.use_adaptive:
            return self.adaptive_cache.save_data(
                symbol=symbol,
                data=data,
                data_source=data_source,
                data_type="fundamentals_data"
            )
        else:
            return self.legacy_cache.save_fundamentals_data(symbol, data, data_source)
    
    def load_fundamentals_data(self, cache_key: str) -> Optional[Any]:
        """加载基本面数据"""
        if self.use_adaptive:
            return self.adaptive_cache.load_data(cache_key)
        else:
            return self.legacy_cache.load_fundamentals_data(cache_key)

    def find_cached_fundamentals_data(self, symbol: str, data_source: str = None,
                                     max_age_hours: int = None) -> Optional[str]:
        """
        Find matching fundamental cache data

        Args:
            symbol: Stock code
            data_source: data source (e.g. "openai", "finnhub") 
            max_age_hours: Maximum cache time (hours), use smart configuration when None

        Returns:
            cache_key: Returns the cache key if a valid cache is found, otherwise None
        """
        if self.use_adaptive:
            # Adaptive cache does not currently support search function and is downgraded to file cache.
            return self.legacy_cache.find_cached_fundamentals_data(symbol, data_source, max_age_hours)
        else:
            return self.legacy_cache.find_cached_fundamentals_data(symbol, data_source, max_age_hours)

    def is_fundamentals_cache_valid(self, symbol: str, data_source: str = None,
                                   max_age_hours: int = None) -> bool:
        """
        Check if fundamental cache is valid

        Args:
            symbol: Stock code
            data_source: data source
            max_age_hours: Maximum cache time (hours)

        Returns:
            bool: Is the cache valid?
        """
        cache_key = self.find_cached_fundamentals_data(symbol, data_source, max_age_hours)
        return cache_key is not None

    # ========== Analysis report cache ==========

    def save_analysis_report(self, report_type: str, report_data: str,
                            symbol: str = None, trade_date: str = None,
                            data_source: str = "llm") -> str:
        """
        Save analysis report to cache

        Args:
            report_type: Report type (e.g. "sector_report", "index_report") 
            report_data: Report content
            symbol: Stock code (can be empty for market analysis)
            trade_date: transaction date
            data_source: data source (default is "llm") 

        Returns:
            cache_key: cache key
        """
        # Build cache key:report_type_symbol_trade_date_data_source
        key_parts = [report_type]
        if symbol:
            key_parts.append(symbol)
        if trade_date:
            # Make sure trade_date is in string format
            if hasattr(trade_date, 'strftime'):
                # datetime object
                trade_date_str = trade_date.strftime("%Y%m%d")
            else:
                # String, remove delimiter
                trade_date_str = str(trade_date).split()[0].replace("-", "")
            key_parts.append(trade_date_str)
        key_parts.append(data_source)
        cache_key = "_".join(key_parts)

        # Make sure the date is in string format (for adaptive_cache)
        if trade_date:
            if hasattr(trade_date, 'strftime'):
                trade_date_str_for_cache = trade_date.strftime("%Y-%m-%d")
            else:
                trade_date_str_for_cache = str(trade_date).split()[0]
        else:
            trade_date_str_for_cache = ""

        # 🔍 Debug log: record and save parameters
        self.logger.debug(f"💾 [IntegratedCache] save_analysis_report: report_type={report_type}, "
                          f"symbol={symbol}, trade_date={trade_date}, use_adaptive={self.use_adaptive}")

        if self.use_adaptive:
            return self.adaptive_cache.save_data(
                symbol=symbol or "market",
                data=report_data,
                start_date=trade_date_str_for_cache,
                end_date=trade_date_str_for_cache,
                data_source=data_source,
                data_type=report_type
            )
        else:
            # Universal save method using file cache
            return self.legacy_cache.save_fundamentals_data(
                symbol=cache_key,
                fundamentals_data=report_data,
                data_source=data_source
            )

    def load_analysis_report(self, cache_key: str) -> Optional[str]:
        """
        Load analysis reports from cache

        Args:
            cache_key: cache key

        Returns:
            Report content, returned if cache does not exist or is invalid None
        """
        if self.use_adaptive:
            return self.adaptive_cache.load_data(cache_key)
        else:
            return self.legacy_cache.load_fundamentals_data(cache_key)

    def find_cached_analysis_report(self, report_type: str, symbol: str = None,
                                   trade_date: str = None, data_source: str = "llm",
                                   max_age_hours: int = 12) -> Optional[str]:
        """
        Find cached analytics reports

        Args:
            report_type: Report type (e.g. "sector_report", "index_report") 
            symbol: Stock code (can be empty for market analysis)
            trade_date: transaction date
            data_source: data source
            max_age_hours: Maximum cache time (hours), default 12 hours

        Returns:
            cache_key: Returns the cache key if a valid cache is found, otherwise None
        """
        if self.use_adaptive:
            # Lookup method using adaptive cache
            # Parameters match the saving method of save_analysis_report
            cache_key = self.adaptive_cache.find_cached_data(
                symbol=symbol or "market",
                start_date=trade_date or "",
                end_date=trade_date or "",
                data_source=data_source,
                data_type=report_type  # report_type as data_type
            )
            if cache_key:
                self.logger.info(f"🎯 找到{report_type}缓存: {symbol or 'market'} @ {trade_date}")
                return cache_key
            else:
                self.logger.info(f"📭 未找到{report_type}缓存: {symbol or 'market'} @ {trade_date}")
                return None
        else:
            # For file caching, build the cache key and lookup
            key_parts = [report_type]
            if symbol:
                key_parts.append(symbol)
            if trade_date:
                key_parts.append(trade_date.replace("-", ""))
            key_parts.append(data_source)
            cache_key = "_".join(key_parts)
            return self.legacy_cache.find_cached_fundamentals_data(cache_key, data_source, max_age_hours)

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if self.use_adaptive:
            # Get adaptive cache statistics (already in standard format)
            stats = self.adaptive_cache.get_cache_stats()

            # Add cache system information
            stats['cache_system'] = 'adaptive'

            # Make sure the backend information exists
            if 'backend_info' not in stats:
                stats['backend_info'] = {}

            stats['backend_info']['database_available'] = self.db_manager.is_database_available()
            stats['backend_info']['mongodb_available'] = self.db_manager.is_mongodb_available()
            stats['backend_info']['redis_available'] = self.db_manager.is_redis_available()

            return stats
        else:
            # Return traditional cache statistics (already in standard format)
            stats = self.legacy_cache.get_cache_stats()

            # Add cache system information
            stats['cache_system'] = 'legacy'

            # Make sure the backend information exists
            if 'backend_info' not in stats:
                stats['backend_info'] = {}

            stats['backend_info']['database_available'] = False
            stats['backend_info']['mongodb_available'] = False
            stats['backend_info']['redis_available'] = False

            return stats
    
    def clear_expired_cache(self):
        """清理过期缓存"""
        if self.use_adaptive:
            self.adaptive_cache.clear_expired_cache()

        # Always clear legacy cache
        self.legacy_cache.clear_expired_cache()

    def clear_old_cache(self, max_age_days: int = 7):
        """
        Clean expired cache (compatible with old interface)

        Args:
            max_age_days: How many days ago to clear the cache, 0 means clear all caches

        Returns:
            Number of records cleared
        """
        cleared_count = 0

        # 1. Clean Redis cache
        if self.use_adaptive and self.db_manager.is_redis_available():
            try:
                redis_client = self.db_manager.get_redis_client()
                if max_age_days == 0:
                    # Clear all cache
                    redis_client.flushdb()
                    self.logger.info(f"🧹 Redis All caches have been cleared")
                else:
                    # Redis It will expire automatically. Only logs will be recorded here.
                    self.logger.info(f"🧹 Redis The cache will automatically expire (TTL mechanism)")
            except Exception as e:
                self.logger.error(f"⚠️ Redis Cache cleanup failed: {e}")

        # 2. Clean MongoDB cache
        if self.use_adaptive and self.db_manager.is_mongodb_available():
            try:
                from datetime import datetime, timedelta
                from zoneinfo import ZoneInfo
                from tradingagents.config.runtime_settings import get_timezone_name

                mongodb_db = self.db_manager.get_mongodb_db()

                if max_age_days == 0:
                    # Clear all cache collections
                    for collection_name in ["stock_data", "news_data", "fundamentals_data"]:
                        result = mongodb_db[collection_name].delete_many({})
                        cleared_count += result.deleted_count
                        self.logger.info(f"🧹 MongoDB {collection_name} 清空了 {result.deleted_count} 条记录")
                else:
                    # Clean up expired data
                    cutoff_time = datetime.now(ZoneInfo(get_timezone_name())) - timedelta(days=max_age_days)
                    for collection_name in ["stock_data", "news_data", "fundamentals_data"]:
                        result = mongodb_db[collection_name].delete_many({"created_at": {"$lt": cutoff_time}})
                        cleared_count += result.deleted_count
                        self.logger.info(f"🧹 MongoDB {collection_name} 清理了 {result.deleted_count} 条记录")
            except Exception as e:
                self.logger.error(f"⚠️ MongoDB Cache cleanup failed: {e}")

        # 3. Clean file cache
        try:
            file_cleared = self.legacy_cache.clear_old_cache(max_age_days)
            # File cache may return None and needs to be processed
            if file_cleared is not None:
                cleared_count += file_cleared
                self.logger.info(f"🧹 文件缓存清理了 {file_cleared} 个文件")
            else:
                self.logger.info(f"🧹 File cache cleanup completed (return value is None)")
        except Exception as e:
            self.logger.error(f"⚠️ 文件缓存清理失败: {e}")

        self.logger.info(f"🧹 总共清理了 {cleared_count} 条缓存记录")
        return cleared_count
    
    def get_cache_backend_info(self) -> Dict[str, Any]:
        """获取缓存后端信息"""
        if self.use_adaptive:
            return {
                "system": "adaptive",
                "primary_backend": self.adaptive_cache.primary_backend,
                "fallback_enabled": self.adaptive_cache.fallback_enabled,
                "mongodb_available": self.db_manager.is_mongodb_available(),
                "redis_available": self.db_manager.is_redis_available()
            }
        else:
            return {
                "system": "legacy",
                "primary_backend": "file",
                "fallback_enabled": False,
                "mongodb_available": False,
                "redis_available": False
            }
    
    def is_database_available(self) -> bool:
        """检查数据库是否可用"""
        if self.use_adaptive:
            return self.db_manager.is_database_available()
        return False
    
    def get_performance_mode(self) -> str:
        """获取性能模式"""
        if not self.use_adaptive:
            return "基础模式 (文件缓存)"
        
        mongodb_available = self.db_manager.is_mongodb_available()
        redis_available = self.db_manager.is_redis_available()
        
        if redis_available and mongodb_available:
            return "High performance mode (Redis + MongoDB + File)"
        elif redis_available:
            return "Quick mode (Redis + File)"
        elif mongodb_available:
            return "persistence mode (MongoDB + File)"
        else:
            return "Standard mode (Smart file caching)"


# Global Integrated Cache Manager Example
_integrated_cache = None

def get_cache() -> IntegratedCacheManager:
    """Get global integrated cache manager instance"""
    global _integrated_cache
    if _integrated_cache is None:
        _integrated_cache = IntegratedCacheManager()
    return _integrated_cache

# backward compatible functions
def get_stock_cache():
    """Backwards Compatibility: Get Stock Cache"""
    return get_cache()

def create_cache_manager(cache_dir: str = None):
    """Backwards Compatibility: Creating a Cache Manager"""
    return IntegratedCacheManager(cache_dir)
