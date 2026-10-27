#!/usr/bin/env python3
"""
Unified historical data management service
Provide a unified historical data storage and query interface for three data sources
"""
import asyncio
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Union
import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """统一历史数据管理服务"""
    
    def __init__(self):
        """初始化服务"""
        self.db = None
        self.collection = None
        
    async def initialize(self):
        """初始化数据库连接"""
        try:
            # 🔥 If db already exists (possibly set externally), it will not be re-created
            # 🔥 This can avoid being re-created after replacing the connection in UnifiedThreadPoolSyncService
            if self.db is None:
                self.db = get_database()
            
            # 🔥 Set collection if it is not already set
            if self.collection is None:
                self.collection = self.db.stock_daily_quotes

            # 🔥 Make sure the index exists (improves query and upsert performance)
            await self._ensure_indexes()

            logger.info("✅ Historical data service initialization successful")
        except Exception as e:
            logger.error(f"❌ Historical data service initialization failed: {e}")
            raise

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        try:
            # 🔥 Key fix: Re-fetch collection from self.db, make sure to use correct connection
            if self.db is None:
                await self.initialize()
            collection = self.db.stock_daily_quotes
            
            logger.info("📊 Check and create historical data index...")

            # 1. Composite unique index: ticker symbol+transaction date+data source+period (for upsert)
            await collection.create_index([
                ("symbol", 1),
                ("trade_date", 1),
                ("data_source", 1),
                ("period", 1)
            ], unique=True, name="symbol_date_source_period_unique", background=True)

            # 2. Stock code index (query historical data of a single stock)
            await collection.create_index([("symbol", 1)], name="symbol_index", background=True)

            # 3. Transaction date index (query by date range)
            await collection.create_index([("trade_date", -1)], name="trade_date_index", background=True)

            # 4. Composite Index: Stock Symbol+Transaction date (common inquiries)
            await collection.create_index([
                ("symbol", 1),
                ("trade_date", -1)
            ], name="symbol_date_index", background=True)

            logger.info("✅ 历史数据索引检查完成")
        except Exception as e:
            # Index creation failure should not prevent the service from starting
            logger.warning(f"⚠️ Warning when creating index (may already exist): {e}")
    
    async def save_historical_data(
        self,
        symbol: str,
        data: pd.DataFrame,
        data_source: str,
        market: str = "CN",
        period: str = "daily",
        overwrite: bool = True
    ) -> int:
        """
        Save historical data to database

        Args:
            symbol: Stock code
            data: historical data DataFrame
            data_source: data source (tushare/akshare/baostock/local)
            market: market type (CN/HK/US)
            period: data period (daily/weekly/monthly)
            overwrite: Whether to overwrite existing data (default True, maintain backward compatibility)

        Returns:
            Number of records saved
        """
        # 🔥 Critical fix: reacquire database connection on every use, ensure correct event loop is used
        # 🔥 This avoids event loop conflicts when asyncio.gather is executed in parallel
        from app.core.database import get_mongo_db
        self.db = get_mongo_db()
        
        # 🔥 Critical fix: re-fetch from self.db on every use collection
        # 🔥 This ensures that the latest db connection is used (bound to the correct event loop)
        collection = self.db.stock_daily_quotes
        
        try:
            if data is None or data.empty:
                logger.warning(f"⚠️ {symbol} Historical data is empty, skip saving")
                return 0

            from datetime import datetime
            total_start = datetime.now()

            logger.info(f"💾 开始保存 {symbol} 历史数据: {len(data)}条记录 (数据源: {data_source})")

            # ⏱️ Performance Monitoring: Unit Conversion
            convert_start = datetime.now()
            # 🔥 Do unit conversion at the DataFrame level (vectorization operation, much faster than row-by-row)
            if data_source == "tushare":
                # Turnover: thousand yuan -> Yuan
                if 'amount' in data.columns:
                    data['amount'] = data['amount'] * 1000
                elif 'turnover' in data.columns:
                    data['turnover'] = data['turnover'] * 1000

                # Volume: Lots -> shares
                if 'volume' in data.columns:
                    data['volume'] = data['volume'] * 100
                elif 'vol' in data.columns:
                    data['vol'] = data['vol'] * 100

            # 🔥 Hong Kong stock/US stock data: Add pre_close field (obtained from the previous day's close)
            if market in ["HK", "US"] and 'pre_close' not in data.columns and 'close' in data.columns:
                # Use shift(1) Move the close column down one row to get the previous day's closing price
                data['pre_close'] = data['close'].shift(1)
                logger.debug(f"✅ {symbol} Add pre_close field (taken from previous day s close)")

            convert_duration = (datetime.now() - convert_start).total_seconds()

            # ⏱️ Performance Monitoring: Building Action Lists
            prepare_start = datetime.now()
            # Prepare for batch operations
            operations = []
            saved_count = 0
            batch_size = 200  # Further reduce batch size to avoid timeouts (from 500 to 200)

            # 🔥 Reduce log output: only print progress when processing large amounts of data
            processed_count = 0

            for date_index, row in data.iterrows():
                processed_count += 1
                try:
                    # Normalize data (pass date index)
                    doc = self._standardize_record(symbol, row, data_source, market, period, date_index)

                    # Determine the operation type based on the overwrite parameter
                    filter_doc = {
                        "symbol": doc["symbol"],
                        "trade_date": doc["trade_date"],
                        "data_source": doc["data_source"],
                        "period": doc["period"]
                    }

                    from pymongo import ReplaceOne, UpdateOne
                    if overwrite:
                        # Override mode: use ReplaceOne with upsert
                        operations.append(ReplaceOne(
                            filter=filter_doc,
                            replacement=doc,
                            upsert=True
                        ))
                    else:
                        # No overwrite mode: use UpdateOne with setOnInsert (only insert if not present)
                        operations.append(UpdateOne(
                            filter=filter_doc,
                            update={"$setOnInsert": doc},
                            upsert=True
                        ))

                    # Batch execution (every 200 items)
                    if len(operations) >= batch_size:
                        batch_saved = await self._execute_bulk_write_with_retry(symbol, operations)
                        saved_count += batch_saved
                        operations = []

                except Exception as e:
                    # Get date information for error logs
                    date_str = str(date_index) if hasattr(date_index, '__str__') else 'unknown'
                    logger.error(f"❌ 处理记录失败 {symbol} {date_str}: {e}")
                    continue

            # Perform remaining operations
            if operations:
                final_batch_saved = await self._execute_bulk_write_with_retry(
                    symbol, operations
                )
                saved_count += final_batch_saved

            total_duration = (datetime.now() - total_start).total_seconds()
            logger.info(f"✅ {symbol} 历史数据保存完成: {saved_count}条记录，耗时 {total_duration:.2f}秒")
            return saved_count
            
        except Exception as e:
            logger.error(f"❌ 保存历史数据失败 {symbol}: {e}")
            return 0

    async def _execute_bulk_write_with_retry(
        self,
        symbol: str,
        operations: List,
        max_retries: int = 5  # Increase the number of retries: from 3 to 5
    ) -> int:
        """
        Perform batch writes with retry mechanism

        Args:
            symbol: Stock code
            operations: Bulk operation list
            max_retries: Maximum number of retries

        Returns:
            Number of records successfully saved
        """
        saved_count = 0
        retry_count = 0

        while retry_count < max_retries:
            try:
                # 🔥 Detect whether running in the thread pool (by checking the current event loop)
                import threading
                current_thread = threading.current_thread()
                is_in_thread_pool = not isinstance(current_thread, threading._MainThread)

                if is_in_thread_pool:
                    # 🔥 In a thread pool: Using a synchronous MongoDB client
                    from app.core.database import get_mongo_db_sync
                    sync_db = get_mongo_db_sync()
                    sync_collection = sync_db.stock_daily_quotes
                    result = sync_collection.bulk_write(operations, ordered=False)
                else:
                    # 🔥 In the main thread: Using an asynchronous MongoDB client
                    # 🔥 Key fix: Re-fetch collection from self.db on every use, make sure to use correct connection
                    if self.db is None:
                        await self.initialize()
                    collection = self.db.stock_daily_quotes
                    result = await collection.bulk_write(operations, ordered=False)
                saved_count = result.upserted_count + result.modified_count
                # 🔥 Reduce logging: only print details if there are errors or retries
                return saved_count

            except asyncio.TimeoutError as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 3 ** retry_count  # Longer exponential backoff: 3 seconds, 9 seconds, 27 seconds, 81 seconds
                    logger.warning(f"⚠️ {symbol} 批量写入超时 (第{retry_count}/{max_retries}次重试)，等待{wait_time}秒后重试...")
                    # 🔥 Choose the sleep mode according to the operating environment
                    if is_in_thread_pool:
                        import time
                        time.sleep(wait_time)
                    else:
                        await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ {symbol} 批量写入失败，已重试{max_retries}次: {e}")
                    return 0

            except Exception as e:
                # Check if it is a timeout related error
                error_msg = str(e).lower()
                if 'timeout' in error_msg or 'timed out' in error_msg:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 3 ** retry_count
                        logger.warning(f"⚠️ {symbol} 批量写入超时 (第{retry_count}/{max_retries}次重试)，等待{wait_time}秒后重试... 错误: {e}")
                        # 🔥 Choose the sleep mode according to the operating environment
                        if is_in_thread_pool:
                            import time
                            time.sleep(wait_time)
                        else:
                            await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ {symbol} 批量写入失败，已重试{max_retries}次: {e}")
                        return 0
                else:
                    logger.error(f"❌ {symbol} 批量写入失败: {e}")
                    return 0

        return saved_count

    def _standardize_record(
        self,
        symbol: str,
        row: pd.Series,
        data_source: str,
        market: str,
        period: str = "daily",
        date_index = None
    ) -> Dict[str, Any]:
        """标准化单条记录"""
        now = datetime.utcnow()

        # Get the date - first get it from the column, only use the index if the index is of date type
        trade_date = None

        # First try to get the date from the column
        date_from_column = row.get('date') or row.get('trade_date')

        # If there is a date in the column, the date in the column is used first
        if date_from_column is not None:
            trade_date = self._format_date(date_from_column)
        # Only use the index if there is no date in the column and the index is a date/time/date string
        # Note: The DataFrame index passed in by batch-import is in the form "20240101" string, explicit support is required here str
        elif date_index is not None and isinstance(date_index, (date, datetime, pd.Timestamp, str)):
            trade_date = self._format_date(date_index)
        # Otherwise use the current date
        else:
            trade_date = self._format_date(None)

        # Basic field mapping
        doc = {
            "symbol": symbol,
            "code": symbol,  # Add code field to be consistent with symbol (backwards compatible)
            "full_symbol": self._get_full_symbol(symbol, market),
            "market": market,
            "trade_date": trade_date,
            "period": period,
            "data_source": data_source,
            "created_at": now,
            "updated_at": now,
            "version": 1
        }
        
        # OHLCV Data (unit conversion is done at the DataFrame level)
        amount_value = self._safe_float(row.get('amount') or row.get('turnover'))
        volume_value = self._safe_float(row.get('volume') or row.get('vol'))

        doc.update({
            "open": self._safe_float(row.get('open')),
            "high": self._safe_float(row.get('high')),
            "low": self._safe_float(row.get('low')),
            "close": self._safe_float(row.get('close')),
            "pre_close": self._safe_float(row.get('pre_close') or row.get('preclose')),
            "volume": volume_value,
            "amount": amount_value
        })
        
        # Calculate rise and fall data
        if doc["close"] and doc["pre_close"]:
            doc["change"] = round(doc["close"] - doc["pre_close"], 4)
            doc["pct_chg"] = round((doc["change"] / doc["pre_close"]) * 100, 4)
        else:
            doc["change"] = self._safe_float(row.get('change'))
            doc["pct_chg"] = self._safe_float(row.get('pct_chg') or row.get('change_percent'))
        
        # optional fields
        optional_fields = {
            "turnover_rate": row.get('turnover_rate') or row.get('turn'),
            "volume_ratio": row.get('volume_ratio'),
            "pe": row.get('pe'),
            "pb": row.get('pb'),
            "ps": row.get('ps'),
            "adjustflag": row.get('adjustflag') or row.get('adj_factor'),
            "tradestatus": row.get('tradestatus'),
            "isST": row.get('isST')
        }
        
        for key, value in optional_fields.items():
            if value is not None:
                doc[key] = self._safe_float(value)
        
        return doc
    
    def _get_full_symbol(self, symbol: str, market: str) -> str:
        """生成完整股票代码"""
        if market == "CN":
            if symbol.startswith('6'):
                return f"{symbol}.SH"
            elif symbol.startswith(('0', '3')):
                return f"{symbol}.SZ"
            else:
                return f"{symbol}.SZ"  # Default Shenzhen
        elif market == "HK":
            return f"{symbol}.HK"
        elif market == "US":
            return symbol
        else:
            return symbol
    
    def _format_date(self, date_value) -> str:
        """格式化日期"""
        if date_value is None:
            return datetime.now().strftime('%Y-%m-%d')

        if isinstance(date_value, str):
            # 🔥 Process "20160704 00:00:00" Format (index format passed in by batch-import)
            if ' ' in date_value:
                date_value = date_value.split(' ')[0]  # Get only the date part

            # Handle different date formats
            if len(date_value) == 8:  # YYYYMMDD
                return f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}"
            elif len(date_value) == 10:  # YYYY-MM-DD
                return date_value
            else:
                # Try parsing other formats
                try:
                    parsed_date = pd.to_datetime(date_value)
                    return parsed_date.strftime('%Y-%m-%d')
                except:
                    return date_value
        elif isinstance(date_value, (date, datetime)):
            return date_value.strftime('%Y-%m-%d')
        elif isinstance(date_value, pd.Timestamp):
            return date_value.strftime('%Y-%m-%d')
        else:
            return str(date_value)
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == '' or pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        data_source: str = None,
        period: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query historical data

        Args:
            symbol: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            data_source: Data source filtering
            period: Data cycle filtering (daily/weekly/monthly)
            limit: Limit the number of returns

        Returns:
            Historical data list
        """
        # 🔥 Key fix: check self.db instead self.collection
        if self.db is None:
            await self.initialize()
        
        # 🔥 Re-fetch the collection from self.db, making sure to use the correct connection
        collection = self.db.stock_daily_quotes
        
        try:
            # Build query conditions
            query = {"symbol": symbol}
            
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter["$gte"] = start_date
                if end_date:
                    date_filter["$lte"] = end_date
                query["trade_date"] = date_filter
            
            if data_source:
                query["data_source"] = data_source

            if period:
                query["period"] = period
            
            # Execute query
            cursor = collection.find(query).sort("trade_date", -1)
            
            if limit:
                cursor = cursor.limit(limit)
            
            results = await cursor.to_list(length=None)
            
            logger.info(f"📊 查询历史数据: {symbol} 返回 {len(results)} 条记录")
            return results
            
        except Exception as e:
            logger.error(f"❌ 查询历史数据失败 {symbol}: {e}")
            return []
    
    async def get_latest_date(self, symbol: str, data_source: str) -> Optional[str]:
        """获取最新数据日期"""
        # 🔥 Key fix: check self.db instead self.collection
        if self.db is None:
            await self.initialize()
        
        # 🔥 Re-fetch the collection from self.db, making sure to use the correct connection
        collection = self.db.stock_daily_quotes
        
        try:
            result = await collection.find_one(
                {"symbol": symbol, "data_source": data_source},
                sort=[("trade_date", -1)]
            )
            
            if result:
                return result["trade_date"]
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取最新日期失败 {symbol}: {e}")
            return None
    
    async def get_data_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        # 🔥 Key fix: check self.db instead self.collection
        if self.db is None:
            await self.initialize()
        
        # 🔥 Re-fetch the collection from self.db, making sure to use the correct connection
        collection = self.db.stock_daily_quotes
        
        try:
            # Total number of records
            total_count = await collection.count_documents({})
            
            # Statistics by data source
            source_stats = await collection.aggregate([
                {"$group": {
                    "_id": "$data_source",
                    "count": {"$sum": 1},
                    "latest_date": {"$max": "$trade_date"}
                }}
            ]).to_list(length=None)
            
            # Statistics by market
            market_stats = await collection.aggregate([
                {"$group": {
                    "_id": "$market",
                    "count": {"$sum": 1}
                }}
            ]).to_list(length=None)
            
            # Stock quantity statistics
            symbol_count = len(await collection.distinct("symbol"))
            
            return {
                "total_records": total_count,
                "total_symbols": symbol_count,
                "by_source": {item["_id"]: {
                    "count": item["count"],
                    "latest_date": item.get("latest_date")
                } for item in source_stats},
                "by_market": {item["_id"]: item["count"] for item in market_stats},
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {}


# Global service instance
_historical_data_service = None


async def get_historical_data_service() -> HistoricalDataService:
    """获取历史数据服务实例"""
    global _historical_data_service
    if _historical_data_service is None:
        _historical_data_service = HistoricalDataService()
        await _historical_data_service.initialize()
    return _historical_data_service
