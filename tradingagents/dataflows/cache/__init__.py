"""
Cache management module

Supports multiple caching strategies:
- File cache (default) - simple and stable, does not rely on external services
- Database cache (optional)- MongoDB + Redis, Better performance
- Adaptive caching (recommended) - automatically selects the best backend

How to use:
    from tradingagents.dataflows.cache import get_cache
    cache = get_cache()  # Automatically select the best caching strategy

Configure cache policy:
    export TA_CACHE_STRATEGY=integrated  # Enable integrated cache (MongoDB/Redis)
    export TA_CACHE_STRATEGY=file        # Use file cache (default)
"""

import os
from typing import Union

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# Import file cache
try:
    from .file_cache import StockDataCache
    FILE_CACHE_AVAILABLE = True
except ImportError:
    StockDataCache = None
    FILE_CACHE_AVAILABLE = False

# Import database cache
try:
    from .db_cache import DatabaseCacheManager
    DB_CACHE_AVAILABLE = True
except ImportError:
    DatabaseCacheManager = None
    DB_CACHE_AVAILABLE = False

# Import adaptive cache
try:
    from .adaptive import AdaptiveCacheSystem
    ADAPTIVE_CACHE_AVAILABLE = True
except ImportError:
    AdaptiveCacheSystem = None
    ADAPTIVE_CACHE_AVAILABLE = False

# Import integrated cache
try:
    from .integrated import IntegratedCacheManager
    INTEGRATED_CACHE_AVAILABLE = True
except ImportError:
    IntegratedCacheManager = None
    INTEGRATED_CACHE_AVAILABLE = False

# Import App Cache Adapter (function, not class)
try:
    from .app_adapter import get_basics_from_cache, get_market_quote_dataframe
    APP_CACHE_AVAILABLE = True
except ImportError:
    get_basics_from_cache = None
    get_market_quote_dataframe = None
    APP_CACHE_AVAILABLE = False

# Import the MongoDB cache adapter
try:
    from .mongodb_cache_adapter import MongoDBCacheAdapter
    MONGODB_CACHE_ADAPTER_AVAILABLE = True
except ImportError:
    MongoDBCacheAdapter = None
    MONGODB_CACHE_ADAPTER_AVAILABLE = False

# Global cache instance
_cache_instance = None

# Default cache strategy (changed to integrated, giving priority to MongoDB/Redis cache)
DEFAULT_CACHE_STRATEGY = os.getenv("TA_CACHE_STRATEGY", "integrated")

def get_cache() -> Union[StockDataCache, IntegratedCacheManager]:
    """
    Get cache instance (unified entrance)

    Choose a cache strategy based on the environment variable TA_CACHE_STRATEGY:
    - "file" (Default): Use file caching
    - "integrated": Use integrated cache (MongoDB/Redis/File automatically selected)
    - "adaptive": Use adaptive caching (same as integrated)

    Environment variable settings:
        export TA_CACHE_STRATEGY=integrated  # Linux/Mac
        set TA_CACHE_STRATEGY=integrated     # Windows

    Return:
        StockDataCache or IntegratedCacheManager instance
    """
    global _cache_instance

    if _cache_instance is None:
        if DEFAULT_CACHE_STRATEGY in ["integrated", "adaptive"]:
            if INTEGRATED_CACHE_AVAILABLE:
                try:
                    _cache_instance = IntegratedCacheManager()
                    logger.info("✅ Use integrated caching system (supports automatic selection of MongoDB/Redis/File)")
                except Exception as e:
                    logger.warning(f"⚠️ Integrated cache initialization failed, downgraded to file cache: {e}")
                    _cache_instance = StockDataCache()
            else:
                logger.warning("⚠️ Integrated cache is not available, use file cache")
                _cache_instance = StockDataCache()
        else:
            _cache_instance = StockDataCache()
            logger.info("✅ 使用文件缓存系统")

    return _cache_instance

__all__ = [
    # Unified entrance (recommended)
    'get_cache',

    # Cache class (for direct use by advanced users)
    'StockDataCache',
    'IntegratedCacheManager',
    'DatabaseCacheManager',
    'AdaptiveCacheSystem',

    # Availability flag
    'FILE_CACHE_AVAILABLE',
    'DB_CACHE_AVAILABLE',
    'ADAPTIVE_CACHE_AVAILABLE',
    'INTEGRATED_CACHE_AVAILABLE',

    # Application cache adapter
    'get_basics_from_cache',
    'get_market_quote_dataframe',
    'APP_CACHE_AVAILABLE',

    # MongoDB cache adapter
    'MongoDBCacheAdapter',
    'MONGODB_CACHE_ADAPTER_AVAILABLE',
]

