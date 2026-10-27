"""
News data service
Provide unified news data storage, query and management functions
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
from pymongo import ReplaceOne
from pymongo.errors import BulkWriteError
from bson import ObjectId

from app.core.database import get_database

logger = logging.getLogger(__name__)


def convert_objectid_to_str(data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """
    Convert MongoDB ObjectId to string to avoid JSON serialization errors

    Args:
        data: Single document or list of documents

    Returns:
        converted data
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and '_id' in item:
                item['_id'] = str(item['_id'])
        return data
    elif isinstance(data, dict):
        if '_id' in data:
            data['_id'] = str(data['_id'])
        return data
    return data


@dataclass
class NewsQueryParams:
    """新闻查询参数"""
    symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    importance: Optional[str] = None
    data_source: Optional[str] = None
    keywords: Optional[List[str]] = None
    limit: int = 50
    skip: int = 0
    sort_by: str = "publish_time"
    sort_order: int = -1  # -1 for desc, 1 for asc


@dataclass
class NewsStats:
    """新闻统计信息"""
    total_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    high_importance_count: int = 0
    medium_importance_count: int = 0
    low_importance_count: int = 0
    categories: Dict[str, int] = None
    sources: Dict[str, int] = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = {}
        if self.sources is None:
            self.sources = {}


class NewsDataService:
    """新闻数据服务"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._db = None
        self._collection = None
        self._indexes_ensured = False

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        if self._indexes_ensured:
            return

        try:
            collection = self._get_collection()
            self.logger.info("📊 Check and create index of news data...")

            # 1. Unique index: prevent duplicate news (URL+Title+Release time)
            await collection.create_index([
                ("url", 1),
                ("title", 1),
                ("publish_time", 1)
            ], unique=True, name="url_title_time_unique", background=True)

            # 2. Stock code index (query news about a single stock)
            await collection.create_index([("symbol", 1)], name="symbol_index", background=True)

            # 3. Multi-stock code index (query news involving multiple stocks)
            await collection.create_index([("symbols", 1)], name="symbols_index", background=True)

            # 4. Release time index (query by time range)
            await collection.create_index([("publish_time", -1)], name="publish_time_desc", background=True)

            # 5. Composite Index: Stock Symbol+Release time (common queries)
            await collection.create_index([
                ("symbol", 1),
                ("publish_time", -1)
            ], name="symbol_time_index", background=True)

            # 6. Data source index (filter by data source)
            await collection.create_index([("data_source", 1)], name="data_source_index", background=True)

            # 7. Category index (filter by news category)
            await collection.create_index([("category", 1)], name="category_index", background=True)

            # 8. Sentiment index (filter by sentiment)
            await collection.create_index([("sentiment", 1)], name="sentiment_index", background=True)

            # 9. Importance index (filter by importance)
            await collection.create_index([("importance", 1)], name="importance_index", background=True)

            # 10. Update time index (data maintenance)
            await collection.create_index([("updated_at", -1)], name="updated_at_index", background=True)

            self._indexes_ensured = True
            self.logger.info("✅ 新闻数据索引检查完成")
        except Exception as e:
            # Index creation failure should not prevent the service from starting
            self.logger.warning(f"⚠️ Warning when creating index (may already exist): {e}")

    def _get_collection(self):
        """获取新闻数据集合"""
        if self._collection is None:
            self._db = get_database()
            self._collection = self._db.stock_news
        return self._collection
    
    @property
    def db(self):
        """Get database connection (compatibility properties)"""
        if self._db is None:
            self._db = get_database()
        return self._db
    
    async def save_news_data(
        self,
        news_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        data_source: str,
        market: str = "CN"
    ) -> int:
        """
        Save news data

        Args:
            news_data: News data (single or multiple items)
            data_source: Data source identifier
            market: market identification

        Returns:
            Number of records saved
        """
        try:
            # 🔥 Make sure the index exists (created on first call)
            await self._ensure_indexes()

            collection = self._get_collection()
            now = datetime.utcnow()
            
            # normalized data
            if isinstance(news_data, dict):
                news_list = [news_data]
            else:
                news_list = news_data
            
            if not news_list:
                return 0
            
            # Prepare for batch operations
            operations = []

            for i, news in enumerate(news_list):
                # Standardized news data
                standardized_news = self._standardize_news_data(
                    news, data_source, market, now
                )

                # 🔍 Record the details of the first 3 pieces of data
                if i < 3:
                    self.logger.info(f"   📝 标准化后的新闻 {i+1}:")
                    self.logger.info(f"      symbol: {standardized_news.get('symbol')}")
                    self.logger.info(f"      title: {standardized_news.get('title', '')[:50]}...")
                    self.logger.info(f"      publish_time: {standardized_news.get('publish_time')} (type: {type(standardized_news.get('publish_time'))})")
                    self.logger.info(f"      url: {standardized_news.get('url', '')[:80]}...")

                # Use URL, title and publication time as unique identifiers
                filter_query = {
                    "url": standardized_news["url"],
                    "title": standardized_news["title"],
                    "publish_time": standardized_news["publish_time"]
                }

                operations.append(
                    ReplaceOne(
                        filter_query,
                        standardized_news,
                        upsert=True
                    )
                )
            
            # Perform batch operations (thread-safe)
            if operations:
                # 🔥 Use thread-safe bulk_write
                from app.utils.thread_safe_db import safe_bulk_write

                result = await safe_bulk_write(
                    collection_name=collection.name,
                    operations=operations,
                    ordered=False,
                    async_db=self.db,
                    max_retries=3
                )
                saved_count = result.upserted_count + result.modified_count

                self.logger.info(f"💾 新闻数据保存完成: {saved_count}条记录 (数据源: {data_source})")
                return saved_count

            return 0

        except BulkWriteError as e:
            # Handle batch write errors without outright failure
            write_errors = e.details.get('writeErrors', [])
            error_count = len(write_errors)
            self.logger.warning(f"⚠️ 部分新闻数据保存失败: {error_count}条错误")

            # Log detailed error information
            for i, error in enumerate(write_errors[:3], 1):  # Only log the first 3 errors
                error_msg = error.get('errmsg', 'Unknown error')
                error_code = error.get('code', 'N/A')
                self.logger.warning(f"   错误 {i}: [Code {error_code}] {error_msg}")

            # Count the number of successful saves
            success_count = len(operations) - error_count
            if success_count > 0:
                self.logger.info(f"💾 成功保存 {success_count} 条新闻数据")

            return success_count
            
        except Exception as e:
            self.logger.error(f"❌ 保存新闻数据失败: {e}")
            return 0

    def save_news_data_sync(
        self,
        news_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        data_source: str,
        market: str = "CN"
    ) -> int:
        """
        Save news data (synchronized version)
        For non-async context, use the synchronous PyMongo client

        Args:
            news_data: News data (single or multiple items)
            data_source: Data source identifier
            market: market identification

        Returns:
            Number of records saved
        """
        try:
            from app.core.database import get_mongo_db_sync

            # Get sync database connection
            db = get_mongo_db_sync()
            collection = db.stock_news
            now = datetime.utcnow()

            # normalized data
            if isinstance(news_data, dict):
                news_list = [news_data]
            else:
                news_list = news_data

            if not news_list:
                return 0

            # Prepare for batch operations
            operations = []

            self.logger.info(f"📝 开始标准化 {len(news_list)} 条新闻数据...")

            for i, news in enumerate(news_list, 1):
                # Standardized news data
                standardized_news = self._standardize_news_data(news, data_source, market, now)

                # Record the details of the first 3 news items
                if i <= 3:
                    self.logger.info(f"   📝 标准化后的新闻 {i}:")
                    self.logger.info(f"      symbol: {standardized_news.get('symbol')}")
                    self.logger.info(f"      title: {standardized_news.get('title', '')[:50]}...")
                    publish_time = standardized_news.get('publish_time')
                    self.logger.info(f"      publish_time: {publish_time} (type: {type(publish_time)})")
                    self.logger.info(f"      url: {standardized_news.get('url', '')[:60]}...")

                # Use URL+Title+Release time as unique identifier
                filter_query = {
                    "url": standardized_news.get("url"),
                    "title": standardized_news.get("title"),
                    "publish_time": standardized_news.get("publish_time")
                }

                operations.append(
                    ReplaceOne(
                        filter_query,
                        standardized_news,
                        upsert=True
                    )
                )

            # Perform batch operations (synchronous mode)
            if operations:
                result = collection.bulk_write(operations)
                saved_count = result.upserted_count + result.modified_count

                self.logger.info(f"💾 新闻数据保存完成: {saved_count}条记录 (数据源: {data_source})")
                return saved_count

            return 0

        except BulkWriteError as e:
            # Handle batch write errors without outright failure
            write_errors = e.details.get('writeErrors', [])
            error_count = len(write_errors)
            self.logger.warning(f"⚠️ 部分新闻数据保存失败: {error_count}条错误")

            # Log detailed error information
            for i, error in enumerate(write_errors[:3], 1):  # Only log the first 3 errors
                error_msg = error.get('errmsg', 'Unknown error')
                error_code = error.get('code', 'N/A')
                self.logger.warning(f"   错误 {i}: [Code {error_code}] {error_msg}")

            # Count the number of successful saves
            success_count = len(operations) - error_count
            if success_count > 0:
                self.logger.info(f"💾 成功保存 {success_count} 条新闻数据")

            return success_count

        except Exception as e:
            self.logger.error(f"❌ 保存新闻数据失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return 0

    def _standardize_news_data(
        self,
        news_data: Dict[str, Any],
        data_source: str,
        market: str,
        now: datetime
    ) -> Dict[str, Any]:
        """标准化新闻数据"""
        
        # Extract basic information
        symbol = news_data.get("symbol")
        symbols = news_data.get("symbols", [])
        
        # If there is a main stock symbol but symbols is empty, add to symbols
        if symbol and symbol not in symbols:
            symbols = [symbol] + symbols
        
        # standardized data structures
        standardized = {
            # Basic information
            "symbol": symbol,
            "full_symbol": self._get_full_symbol(symbol, market) if symbol else None,
            "market": market,
            "symbols": symbols,
            
            # News content
            "title": news_data.get("title", ""),
            "content": news_data.get("content", ""),
            "summary": news_data.get("summary", ""),
            "url": news_data.get("url", ""),
            "source": news_data.get("source", ""),
            "author": news_data.get("author", ""),
            
            # time information
            "publish_time": self._parse_datetime(news_data.get("publish_time")),
            
            # Categories and tags
            "category": news_data.get("category", "general"),
            "sentiment": news_data.get("sentiment", "neutral"),
            "sentiment_score": self._safe_float(news_data.get("sentiment_score")),
            "keywords": news_data.get("keywords", []),
            "importance": news_data.get("importance", "medium"),
            # Note: Do not include the language field to avoid conflict with MongoDB text index

            # metadata
            "data_source": data_source,
            "created_at": now,
            "updated_at": now,
            "version": 1
        }
        
        return standardized
    
    def _get_full_symbol(self, symbol: str, market: str) -> str:
        """获取完整股票代码"""
        if not symbol:
            return None
        
        if market == "CN":
            if len(symbol) == 6:
                if symbol.startswith(('60', '68')):
                    return f"{symbol}.SH"
                elif symbol.startswith(('00', '30')):
                    return f"{symbol}.SZ"
        
        return symbol
    
    def _parse_datetime(self, dt_value) -> Optional[datetime]:
        """解析日期时间"""
        if dt_value is None:
            return None
        
        if isinstance(dt_value, datetime):
            return dt_value
        
        if isinstance(dt_value, str):
            try:
                # Try multiple date formats
                formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d",
                ]
                
                for fmt in formats:
                    try:
                        return datetime.strptime(dt_value, fmt)
                    except ValueError:
                        continue
                
                # If all else fails, return the current time
                self.logger.warning(f"⚠️ 无法解析日期时间: {dt_value}")
                return datetime.utcnow()
                
            except Exception:
                return datetime.utcnow()
        
        return datetime.utcnow()
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    async def query_news(self, params: NewsQueryParams) -> List[Dict[str, Any]]:
        """
        Query news data
        
        Args:
            params: query parameters
            
        Returns:
            News data list
        """
        try:
            collection = self._get_collection()

            self.logger.info(f"🔍 [query_news] Start querying news data")
            self.logger.info(f"   参数: symbol={params.symbol}, start_time={params.start_time}, end_time={params.end_time}, limit={params.limit}")

            # Build query conditions
            query = {}

            if params.symbol:
                query["symbol"] = params.symbol
                self.logger.info(f"   Add query conditions: symbol={params.symbol}")

            if params.symbols:
                query["symbols"] = {"$in": params.symbols}
                self.logger.info(f"   Add query conditions: symbols in {params.symbols}")

            if params.start_time or params.end_time:
                time_query = {}
                if params.start_time:
                    time_query["$gte"] = params.start_time
                if params.end_time:
                    time_query["$lte"] = params.end_time
                query["publish_time"] = time_query
                self.logger.info(f"   Add query conditions: publish_time between {params.start_time} and {params.end_time}")

            if params.category:
                query["category"] = params.category
                self.logger.info(f"   Add query conditions: category={params.category}")

            if params.sentiment:
                query["sentiment"] = params.sentiment
                self.logger.info(f"   Add query conditions: sentiment={params.sentiment}")

            if params.importance:
                query["importance"] = params.importance
                self.logger.info(f"   Add query conditions: importance={params.importance}")

            if params.data_source:
                query["data_source"] = params.data_source
                self.logger.info(f"   Add query conditions: data_source={params.data_source}")

            if params.keywords:
                # Text search
                query["$text"] = {"$search": " ".join(params.keywords)}
                self.logger.info(f"   Add query conditions: text search={params.keywords}")

            self.logger.info(f"   最终查询条件: {query}")

            # Count the total first
            total_count = await collection.count_documents(query)
            self.logger.info(f"   The total number of records in the database that meet the criteria: {total_count}")

            # Execute query
            cursor = collection.find(query)

            # sort
            cursor = cursor.sort(params.sort_by, params.sort_order)
            self.logger.info(f"   排序: {params.sort_by} ({params.sort_order})")

            # Pagination
            cursor = cursor.skip(params.skip).limit(params.limit)
            self.logger.info(f"   分页: skip={params.skip}, limit={params.limit}")

            # Get results
            results = await cursor.to_list(length=None)
            self.logger.info(f"   查询返回: {len(results)} 条记录")

            # 🔧 Convert ObjectId to string to avoid JSON serialization errors
            results = convert_objectid_to_str(results)

            if results:
                self.logger.info(f"   前3条预览:")
                for i, r in enumerate(results[:3], 1):
                    self.logger.info(f"      {i}. symbol={r.get('symbol')}, title={r.get('title', 'N/A')[:50]}..., publish_time={r.get('publish_time')}")
            else:
                self.logger.warning(f"   ⚠️ 查询结果为空")

            self.logger.info(f"✅ [query_news] 查询完成，返回 {len(results)} 条记录")
            return results

        except Exception as e:
            self.logger.error(f"❌ 查询新闻数据失败: {e}", exc_info=True)
            return []
    
    async def get_latest_news(
        self,
        symbol: str = None,
        limit: int = 10,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get the latest news
        
        Args:
            symbol: Stock code, if empty, get all news
            limit: Return quantity limit
            hours_back: Lookback hours
            
        Returns:
            Latest news list
        """
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        params = NewsQueryParams(
            symbol=symbol,
            start_time=start_time,
            limit=limit,
            sort_by="publish_time",
            sort_order=-1
        )
        
        return await self.query_news(params)
    
    async def get_news_statistics(
        self,
        symbol: str = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> NewsStats:
        """
        Get news statistics
        
        Args:
            symbol: Stock code
            start_time: start time
            end_time: end time
            
        Returns:
            News statistics
        """
        try:
            collection = self._get_collection()
            
            # Build matching conditions
            match_stage = {}
            
            if symbol:
                match_stage["symbol"] = symbol
            
            if start_time or end_time:
                time_query = {}
                if start_time:
                    time_query["$gte"] = start_time
                if end_time:
                    time_query["$lte"] = end_time
                match_stage["publish_time"] = time_query
            
            # aggregation pipeline
            pipeline = []
            
            if match_stage:
                pipeline.append({"$match": match_stage})
            
            pipeline.extend([
                {
                    "$group": {
                        "_id": None,
                        "total_count": {"$sum": 1},
                        "positive_count": {
                            "$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}
                        },
                        "negative_count": {
                            "$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}
                        },
                        "neutral_count": {
                            "$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}
                        },
                        "high_importance_count": {
                            "$sum": {"$cond": [{"$eq": ["$importance", "high"]}, 1, 0]}
                        },
                        "medium_importance_count": {
                            "$sum": {"$cond": [{"$eq": ["$importance", "medium"]}, 1, 0]}
                        },
                        "low_importance_count": {
                            "$sum": {"$cond": [{"$eq": ["$importance", "low"]}, 1, 0]}
                        },
                        "categories": {"$push": "$category"},
                        "sources": {"$push": "$data_source"}
                    }
                }
            ])
            
            # Perform aggregation
            result = await collection.aggregate(pipeline).to_list(length=1)
            
            if result:
                data = result[0]
                
                # Statistical categories and sources
                categories = {}
                for cat in data.get("categories", []):
                    categories[cat] = categories.get(cat, 0) + 1
                
                sources = {}
                for src in data.get("sources", []):
                    sources[src] = sources.get(src, 0) + 1
                
                return NewsStats(
                    total_count=data.get("total_count", 0),
                    positive_count=data.get("positive_count", 0),
                    negative_count=data.get("negative_count", 0),
                    neutral_count=data.get("neutral_count", 0),
                    high_importance_count=data.get("high_importance_count", 0),
                    medium_importance_count=data.get("medium_importance_count", 0),
                    low_importance_count=data.get("low_importance_count", 0),
                    categories=categories,
                    sources=sources
                )
            
            return NewsStats()
            
        except Exception as e:
            self.logger.error(f"❌ 获取新闻统计失败: {e}")
            return NewsStats()
    
    async def delete_old_news(self, days_to_keep: int = 90) -> int:
        """
        Delete expired news
        
        Args:
            days_to_keep: retention days
            
        Returns:
            Number of records deleted
        """
        try:
            collection = self._get_collection()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            result = await collection.delete_many({
                "publish_time": {"$lt": cutoff_date}
            })
            
            deleted_count = result.deleted_count
            self.logger.info(f"🗑️ 删除过期新闻: {deleted_count}条记录")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"❌ 删除过期新闻失败: {e}")
            return 0

    async def search_news(
        self,
        query_text: str,
        symbol: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search news in full text

        Args:
            query_text: Search text
            symbol: Stock code filter
            limit: Return quantity limit

        Returns:
            Search result list
        """
        try:
            collection = self._get_collection()

            # Build query conditions
            query = {"$text": {"$search": query_text}}

            if symbol:
                query["symbol"] = symbol

            # Perform a search, sorted by relevance
            cursor = collection.find(
                query,
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})])

            cursor = cursor.limit(limit)
            results = await cursor.to_list(length=None)

            # 🔧 Convert ObjectId to string to avoid JSON serialization errors
            results = convert_objectid_to_str(results)

            self.logger.info(f"🔍 全文搜索返回 {len(results)} 条结果")
            return results

        except Exception as e:
            self.logger.error(f"❌ 全文搜索失败: {e}")
            return []


# Global service instance
_service_instance = None

async def get_news_data_service() -> NewsDataService:
    """获取新闻数据服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = NewsDataService()
        logger.info("✅ News data service initialization successful")
    return _service_instance
