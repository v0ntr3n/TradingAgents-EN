#!/usr/bin/env python3
"""
MongoDB + Redis Database cache manager
Provide high-performance stock data caching and persistent storage
"""

import os
import json
import pickle
import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tradingagents.config.runtime_settings import get_timezone_name

from typing import Optional, Dict, Any, List, Union
import pandas as pd

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# MongoDB
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    logger.warning(f"⚠️ pymongo Not installed, MongoDB functionality is not available")

# Redis
try:
    import redis
    from redis.exceptions import ConnectionError as RedisConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning(f"⚠️ redis Not installed, Redis function is not available")


class DatabaseCacheManager:
    """MongoDB + Redis Database cache manager"""

    def __init__(self,
                 mongodb_url: Optional[str] = None,
                 redis_url: Optional[str] = None,
                 mongodb_db: str = "tradingagents",
                 redis_db: int = 0):
        """
        Initialize the database cache manager

        Args:
            mongodb_url: MongoDB Connection URL, default configuration file port
            redis_url: Redis Connection URL, default configuration file port
            mongodb_db: MongoDB Database name
            redis_db: Redis database number
        """
        # Get the correct port from the config file
        mongodb_port = os.getenv("MONGODB_PORT", "27018")
        redis_port = os.getenv("REDIS_PORT", "6380")
        mongodb_password = os.getenv("MONGODB_PASSWORD", "tradingagents123")
        redis_password = os.getenv("REDIS_PASSWORD", "tradingagents123")

        # Build connection strings using unity tool functions
        from tradingagents.config.mongodb_utils import build_mongodb_connection_string, build_redis_connection_string

        # MongoDB URL
        if mongodb_url:
            self.mongodb_url = mongodb_url
        else:
            # Prioritize using the MONGODB_URL environment variable, otherwise use tool functions to build
            self.mongodb_url = os.getenv("MONGODB_URL") or build_mongodb_connection_string()

        # Redis URL
        if redis_url:
            self.redis_url = redis_url
        else:
            # Build using tool functions (the REDIS_URL environment variable will be automatically processed)
            self.redis_url = build_redis_connection_string()
        self.mongodb_db_name = mongodb_db
        self.redis_db = redis_db

        # Initialize connection
        self.mongodb_client = None
        self.mongodb_db = None
        self.redis_client = None

        self._init_mongodb()
        self._init_redis()

        logger.info(f"🗄️ Database cache manager initialization completed")
        logger.error(f"   MongoDB: {'✅ Connected' if self.mongodb_client else '❌ Not connected'}")
        logger.error(f"   Redis: {'✅ Connected' if self.redis_client else '❌ Not connected'}")

    def _init_mongodb(self):
        """初始化MongoDB连接"""
        if not MONGODB_AVAILABLE:
            return

        try:
            # Read timeout configuration from environment variables, using sensible defaults
            import os
            connect_timeout = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "30000"))
            socket_timeout = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "60000"))
            server_selection_timeout = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))

            self.mongodb_client = MongoClient(
                self.mongodb_url,
                serverSelectionTimeoutMS=server_selection_timeout,
                connectTimeoutMS=connect_timeout,
                socketTimeoutMS=socket_timeout
            )
            # test connection
            self.mongodb_client.admin.command('ping')
            self.mongodb_db = self.mongodb_client[self.mongodb_db_name]

            # Create index
            self._create_mongodb_indexes()

            logger.info(f"✅ MongoDB Connection successful: {self.mongodb_url}")
            logger.info(f"⏱️  Timeout configuration: connectTimeout={connect_timeout}ms, socketTimeout={socket_timeout}ms")

        except Exception as e:
            logger.error(f"❌ MongoDB Connection failed: {e}")
            self.mongodb_client = None
            self.mongodb_db = None

    def _init_redis(self):
        """初始化Redis连接"""
        if not REDIS_AVAILABLE:
            return

        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                db=self.redis_db,
                socket_timeout=5,
                socket_connect_timeout=5,
                decode_responses=True
            )
            # test connection
            self.redis_client.ping()

            logger.info(f"✅ Redis连接成功: {self.redis_url}")

        except Exception as e:
            logger.error(f"❌ Redis连接失败: {e}")
            self.redis_client = None

    def _create_mongodb_indexes(self):
        """创建MongoDB索引"""
        if self.mongodb_db is None:
            return

        try:
            # Stock data collection index
            stock_collection = self.mongodb_db.stock_data
            stock_collection.create_index([
                ("symbol", 1),
                ("data_source", 1),
                ("start_date", 1),
                ("end_date", 1)
            ])
            stock_collection.create_index([("created_at", 1)])

            # News data collection index
            news_collection = self.mongodb_db.news_data
            news_collection.create_index([
                ("symbol", 1),
                ("data_source", 1),
                ("date_range", 1)
            ])
            news_collection.create_index([("created_at", 1)])

            # Fundamental Data Collection Index
            fundamentals_collection = self.mongodb_db.fundamentals_data
            fundamentals_collection.create_index([
                ("symbol", 1),
                ("data_source", 1),
                ("analysis_date", 1)
            ])
            fundamentals_collection.create_index([("created_at", 1)])

            logger.info(f"✅ MongoDB Index creation completed")

        except Exception as e:
            logger.error(f"⚠️ MongoDB Index creation failed: {e}")

    def _generate_cache_key(self, data_type: str, symbol: str, **kwargs) -> str:
        """生成缓存键"""
        params_str = f"{data_type}_{symbol}"
        for key, value in sorted(kwargs.items()):
            params_str += f"_{key}_{value}"

        cache_key = hashlib.md5(params_str.encode()).hexdigest()[:16]
        return f"{data_type}:{symbol}:{cache_key}"

    def save_stock_data(self, symbol: str, data: Union[pd.DataFrame, str],
                       start_date: str = None, end_date: str = None,
                       data_source: str = "unknown", market_type: str = None) -> str:
        """
        Save stock data to MongoDB and Redis

        Args:
            symbol: Stock code
            data: stock data
            start_date: start date
            end_date: end date
            data_source: data source
            market_type: market type (us/china)

        Returns:
            cache_key: cache key
        """
        cache_key = self._generate_cache_key("stock", symbol,
                                           start_date=start_date,
                                           end_date=end_date,
                                           source=data_source)

        # Automatically infer market type
        if market_type is None:
            # Infer market type based on ticker format
            import re

            if re.match(r'^\d{6}$', symbol):  # 6 Digits for A shares
                market_type = "china"
            else:  # Other formats are US stocks
                market_type = "us"

        # Prepare document data
        doc = {
            "_id": cache_key,
            "symbol": symbol,
            "market_type": market_type,
            "data_type": "stock_data",
            "start_date": start_date,
            "end_date": end_date,
            "data_source": data_source,
            "created_at": datetime.now(ZoneInfo(get_timezone_name())),
            "updated_at": datetime.now(ZoneInfo(get_timezone_name()))
        }

        # Handling data formats
        if isinstance(data, pd.DataFrame):
            doc["data"] = data.to_json(orient='records', date_format='iso')
            doc["data_format"] = "dataframe_json"
        else:
            doc["data"] = str(data)
            doc["data_format"] = "text"

        # Save to MongoDB (persistence)
        if self.mongodb_db is not None:
            try:
                collection = self.mongodb_db.stock_data
                collection.replace_one({"_id": cache_key}, doc, upsert=True)
                logger.info(f"💾 Stock data has been saved to MongoDB: {symbol} -> {cache_key}")
            except Exception as e:
                logger.error(f"⚠️ MongoDB Save failed: {e}")

        # Save to Redis (fast cache, expires in 6 hours)
        if self.redis_client:
            try:
                redis_data = {
                    "data": doc["data"],
                    "data_format": doc["data_format"],
                    "symbol": symbol,
                    "data_source": data_source,
                    "created_at": doc["created_at"].isoformat()
                }
                self.redis_client.setex(
                    cache_key,
                    6 * 3600,  # 6 hour expires
                    json.dumps(redis_data, ensure_ascii=False)
                )
                logger.info(f"⚡ Stock data has been cached to Redis: {symbol} -> {cache_key}")
            except Exception as e:
                logger.error(f"⚠️ Redis Caching failed: {e}")

        return cache_key

    def load_stock_data(self, cache_key: str) -> Optional[Union[pd.DataFrame, str]]:
        """Load stock data from Redis or MongoDB"""

        # First try loading from Redis (faster)
        if self.redis_client:
            try:
                redis_data = self.redis_client.get(cache_key)
                if redis_data:
                    data_dict = json.loads(redis_data)
                    logger.info(f"⚡ Load data from Redis: {cache_key}")

                    if data_dict["data_format"] == "dataframe_json":
                        return pd.read_json(data_dict["data"], orient='records')
                    else:
                        return data_dict["data"]
            except Exception as e:
                logger.error(f"⚠️ Redis Loading failed: {e}")

        # If Redis is not available, load it from MongoDB
        if self.mongodb_db is not None:
            try:
                collection = self.mongodb_db.stock_data
                doc = collection.find_one({"_id": cache_key})

                if doc:
                    logger.info(f"💾 Load data from MongoDB: {cache_key}")

                    # Update to Redis cache at the same time
                    if self.redis_client:
                        try:
                            redis_data = {
                                "data": doc["data"],
                                "data_format": doc["data_format"],
                                "symbol": doc["symbol"],
                                "data_source": doc["data_source"],
                                "created_at": doc["created_at"].isoformat()
                            }
                            self.redis_client.setex(
                                cache_key,
                                6 * 3600,
                                json.dumps(redis_data, ensure_ascii=False)
                            )
                            logger.info(f"⚡ Data has been synchronized to Redis cache")
                        except Exception as e:
                            logger.error(f"⚠️ Redis Sync failed: {e}")

                    if doc["data_format"] == "dataframe_json":
                        return pd.read_json(doc["data"], orient='records')
                    else:
                        return doc["data"]

            except Exception as e:
                logger.error(f"⚠️ MongoDB Loading failed: {e}")

        return None

    def find_cached_stock_data(self, symbol: str, start_date: str = None,
                              end_date: str = None, data_source: str = None,
                              max_age_hours: int = 6) -> Optional[str]:
        """查找匹配的缓存数据"""

        # Generate exact match cache keys
        exact_key = self._generate_cache_key("stock", symbol,
                                           start_date=start_date,
                                           end_date=end_date,
                                           source=data_source)

        # Check if there is an exact match in Redis
        if self.redis_client and self.redis_client.exists(exact_key):
            logger.info(f"⚡ Redis Exact match found in: {symbol} -> {exact_key}")
            return exact_key

        # Check for matches in MongoDB
        if self.mongodb_db is not None:
            try:
                collection = self.mongodb_db.stock_data
                cutoff_time = datetime.now(ZoneInfo(get_timezone_name())) - timedelta(hours=max_age_hours)

                query = {
                    "symbol": symbol,
                    "created_at": {"$gte": cutoff_time}
                }

                if data_source:
                    query["data_source"] = data_source
                if start_date:
                    query["start_date"] = start_date
                if end_date:
                    query["end_date"] = end_date

                doc = collection.find_one(query, sort=[("created_at", -1)])

                if doc:
                    cache_key = doc["_id"]
                    logger.info(f"💾 MongoDB Match found in: {symbol} -> {cache_key}")
                    return cache_key

            except Exception as e:
                logger.error(f"⚠️ MongoDB Query failed: {e}")

        logger.error(f"❌ 未找到有效缓存: {symbol}")
        return None

    def save_news_data(self, symbol: str, news_data: str,
                      start_date: str = None, end_date: str = None,
                      data_source: str = "unknown") -> str:
        """Save news data to MongoDB and Redis"""
        cache_key = self._generate_cache_key("news", symbol,
                                           start_date=start_date,
                                           end_date=end_date,
                                           source=data_source)

        doc = {
            "_id": cache_key,
            "symbol": symbol,
            "data_type": "news_data",
            "date_range": f"{start_date}_{end_date}",
            "start_date": start_date,
            "end_date": end_date,
            "data_source": data_source,
            "data": news_data,
            "created_at": datetime.now(ZoneInfo(get_timezone_name())),
            "updated_at": datetime.now(ZoneInfo(get_timezone_name()))
        }

        # save to MongoDB
        if self.mongodb_db is not None:
            try:
                collection = self.mongodb_db.news_data
                collection.replace_one({"_id": cache_key}, doc, upsert=True)
                logger.info(f"📰 News data has been saved to MongoDB: {symbol} -> {cache_key}")
            except Exception as e:
                logger.error(f"⚠️ MongoDB Save failed: {e}")

        # Save to Redis (expires in 24 hours)
        if self.redis_client:
            try:
                redis_data = {
                    "data": news_data,
                    "symbol": symbol,
                    "data_source": data_source,
                    "created_at": doc["created_at"].isoformat()
                }
                self.redis_client.setex(
                    cache_key,
                    24 * 3600,  # 24 hour expires
                    json.dumps(redis_data, ensure_ascii=False)
                )
                logger.info(f"⚡ News data has been cached to Redis: {symbol} -> {cache_key}")
            except Exception as e:
                logger.error(f"⚠️ Redis Caching failed: {e}")

        return cache_key

    def save_fundamentals_data(self, symbol: str, fundamentals_data: str,
                              analysis_date: str = None,
                              data_source: str = "unknown") -> str:
        """Save fundamental data to MongoDB and Redis"""
        if not analysis_date:
            analysis_date = datetime.now(ZoneInfo(get_timezone_name())).strftime("%Y-%m-%d")

        cache_key = self._generate_cache_key("fundamentals", symbol,
                                           date=analysis_date,
                                           source=data_source)

        doc = {
            "_id": cache_key,
            "symbol": symbol,
            "data_type": "fundamentals_data",
            "analysis_date": analysis_date,
            "data_source": data_source,
            "data": fundamentals_data,
            "created_at": datetime.now(ZoneInfo(get_timezone_name())),
            "updated_at": datetime.now(ZoneInfo(get_timezone_name()))
        }

        # save to MongoDB
        if self.mongodb_db is not None:
            try:
                collection = self.mongodb_db.fundamentals_data
                collection.replace_one({"_id": cache_key}, doc, upsert=True)
                logger.info(f"💼 Fundamental data has been saved to MongoDB: {symbol} -> {cache_key}")
            except Exception as e:
                logger.error(f"⚠️ MongoDB Save failed: {e}")

        # Save to Redis (expires in 24 hours)
        if self.redis_client:
            try:
                redis_data = {
                    "data": fundamentals_data,
                    "symbol": symbol,
                    "data_source": data_source,
                    "analysis_date": analysis_date,
                    "created_at": doc["created_at"].isoformat()
                }
                self.redis_client.setex(
                    cache_key,
                    24 * 3600,  # 24 hour expires
                    json.dumps(redis_data, ensure_ascii=False)
                )
                logger.info(f"⚡ Fundamental data has been cached to Redis: {symbol} -> {cache_key}")
            except Exception as e:
                logger.error(f"⚠️ Redis Caching failed: {e}")

        return cache_key

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        # Standard statistics format (consistent with file_cache)
        stats = {
            'total_files': 0,
            'stock_data_count': 0,
            'news_count': 0,
            'fundamentals_count': 0,
            'total_size': 0,  # Bytes
            'total_size_mb': 0,  # MB
            'skipped_count': 0
        }

        # Detailed backend information
        backend_info = {
            "mongodb": {"available": self.mongodb_db is not None, "collections": {}},
            "redis": {"available": self.redis_client is not None, "keys": 0, "memory_usage": "N/A"}
        }

        # MongoDB statistics
        total_size_bytes = 0
        if self.mongodb_db is not None:
            try:
                for collection_name in ["stock_data", "news_data", "fundamentals_data"]:
                    collection = self.mongodb_db[collection_name]
                    count = collection.count_documents({})
                    size = self.mongodb_db.command("collStats", collection_name).get("size", 0)
                    backend_info["mongodb"]["collections"][collection_name] = {
                        "count": count,
                        "size_mb": round(size / (1024 * 1024), 2)
                    }

                    # Accumulate to standard statistics
                    total_size_bytes += size
                    stats['total_files'] += count

                    # Classified by type
                    if collection_name == "stock_data":
                        stats['stock_data_count'] += count
                    elif collection_name == "news_data":
                        stats['news_count'] += count
                    elif collection_name == "fundamentals_data":
                        stats['fundamentals_count'] += count

            except Exception as e:
                logger.error(f"⚠️ MongoDB Failed to obtain statistics: {e}")

        # Redis statistics
        if self.redis_client:
            try:
                info = self.redis_client.info()
                backend_info["redis"]["keys"] = info.get("db0", {}).get("keys", 0)
                backend_info["redis"]["memory_usage"] = f"{info.get('used_memory_human', 'N/A')}"
            except Exception as e:
                logger.error(f"⚠️ Redis Failed to obtain statistics: {e}")

        # Set total size
        stats['total_size'] = total_size_bytes
        stats['total_size_mb'] = round(total_size_bytes / (1024 * 1024), 2)

        # Add backend details
        stats['backend_info'] = backend_info

        return stats

    def clear_old_cache(self, max_age_days: int = 7):
        """清理过期缓存"""
        cutoff_time = datetime.now(ZoneInfo(get_timezone_name())) - timedelta(days=max_age_days)
        cleared_count = 0

        # clean up MongoDB
        if self.mongodb_db is not None:
            try:
                for collection_name in ["stock_data", "news_data", "fundamentals_data"]:
                    collection = self.mongodb_db[collection_name]
                    result = collection.delete_many({"created_at": {"$lt": cutoff_time}})
                    cleared_count += result.deleted_count
                    logger.info(f"🧹 MongoDB {collection_name} 清理了 {result.deleted_count} 条记录")
            except Exception as e:
                logger.error(f"⚠️ MongoDB Cleanup failed: {e}")

        # Redis It will automatically expire and no manual cleaning is required.
        logger.info(f"🧹 总共清理了 {cleared_count} 条过期记录")
        return cleared_count

    def close(self):
        """关闭数据库连接"""
        if self.mongodb_client:
            self.mongodb_client.close()
            logger.info(f"🔒 MongoDB connection closed")

        if self.redis_client:
            self.redis_client.close()
            logger.info(f"🔒 Redis连接已关闭")


# Global database cache instance
_db_cache_instance = None

def get_db_cache() -> DatabaseCacheManager:
    """获取全局数据库缓存实例"""
    global _db_cache_instance
    if _db_cache_instance is None:
        _db_cache_instance = DatabaseCacheManager()
    return _db_cache_instance
