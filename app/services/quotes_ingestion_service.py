import asyncio
import logging
from datetime import datetime, time as dtime, timedelta
from typing import Dict, Optional, Tuple, List
from zoneinfo import ZoneInfo
from collections import deque

from pymongo import UpdateOne

from app.core.config import settings
from app.core.database import get_mongo_db
from app.services.data_sources.manager import DataSourceManager

logger = logging.getLogger(__name__)


REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS = 8


class QuotesIngestionService:
    """
    Regularly obtain near-real-time market information from the data source adaptation layer and store it in a MongoDB collection `market_quotes`. 

    Core features:
    - Scheduling frequency: controlled by settings.QUOTES_INGEST_INTERVAL_SECONDS (default 360 seconds=6 minutes)
    - Interface rotation:Tushare → AKShare Oriental Fortune → AKShare Sina Finance (to avoid a single interface being restricted)
    - Intelligent current limit: Tushare free users can use up to 2 times per hour, and paid users automatically switch to high-frequency mode (5 seconds)
    - Close time: Skip the task and keep the last closing data; perform a one-time bottom-up if necessary
    - Fields:code(6 Bit), close, pct_chg, amount, open, high, low, pre_close, trade_date, updated_at
    """

    def __init__(self, collection_name: str = "market_quotes") -> None:
        from collections import deque

        self.collection_name = collection_name
        self.status_collection_name = "quotes_ingestion_status"  # Status record collection
        self.tz = ZoneInfo(settings.TIMEZONE)

        # Tushare Permission detection related attributes
        self._tushare_permission_checked = False  # Have permissions been checked?
        self._tushare_has_premium = False  # Is there paid permission?
        self._tushare_last_call_time = None  # Last call time (for free user current limit)
        self._tushare_hourly_limit = 2  # Maximum number of calls per hour for free users
        self._tushare_call_count = 0  # Number of calls in the current hour
        self._tushare_call_times = deque()  # Queue that records call time (used for current limiting)

        # Interface rotation related properties
        self._rotation_sources = ["tushare", "akshare_eastmoney", "akshare_sina"]
        self._rotation_index = 0  # Current rotation index

        # Caching DataSourceManager instances (lazy loading, reuse throughout the service life cycle, avoiding rebuilding each time)
        self._dsm: Optional[DataSourceManager] = None

    def _get_dsm(self) -> DataSourceManager:
        """Return cached DataSourceManager instance (lazy loading)"""
        if self._dsm is None:
            self._dsm = DataSourceManager()
        return self._dsm

    @staticmethod
    def _normalize_stock_code(code: str) -> str:
        """
        Standardized stock code is 6 digits

        Handle the following situations:
        - sz000001 -> 000001
        - sh600036 -> 600036
        - 000001 -> 000001
        - 1 -> 000001

        Args:
            code: Original stock symbol

        Returns:
            str: Standardized 6-digit stock code
        """
        if not code:
            return ""

        code_str = str(code).strip()

        # If the code length exceeds 6 characters, remove the previous exchange prefix (such as sz, sh) 
        if len(code_str) > 6:
            # Extract all numeric characters
            code_str = ''.join(filter(str.isdigit, code_str))

        # If it is a pure number, complete it to 6 digits
        if code_str.isdigit():
            code_clean = code_str.lstrip('0') or '0'  # Remove leading 0s, if all 0s, keep one 0
            return code_clean.zfill(6)  # Complete to 6 digits

        # If it's not purely numeric, try to extract the numeric part
        code_digits = ''.join(filter(str.isdigit, code_str))
        if code_digits:
            return code_digits.zfill(6)

        # Unable to extract valid code, returns empty string
        return ""

    async def ensure_indexes(self) -> None:
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            await coll.create_index("code", unique=True)
            await coll.create_index("updated_at")
        except Exception as e:
            logger.warning(f"Failed to create market index (ignored): {e}")

    async def _record_sync_status(
        self,
        success: bool,
        source: Optional[str] = None,
        records_count: int = 0,
        error_msg: Optional[str] = None
    ) -> None:
        """
        Record sync status

        Args:
            success: Is it successful?
            source: Data source name
            records_count: Record quantity
            error_msg: error message
        """
        try:
            db = get_mongo_db()
            status_coll = db[self.status_collection_name]

            now = datetime.now(self.tz)

            status_doc = {
                "job": "quotes_ingestion",
                "last_sync_time": now,
                "last_sync_time_iso": now.isoformat(),
                "success": success,
                "data_source": source,
                "records_count": records_count,
                "interval_seconds": settings.QUOTES_INGEST_INTERVAL_SECONDS,
                "error_message": error_msg,
                "updated_at": now,
            }

            await status_coll.update_one(
                {"job": "quotes_ingestion"},
                {"$set": status_doc},
                upsert=True
            )

        except Exception as e:
            logger.warning(f"Logging sync status failed (ignored): {e}")

    async def get_sync_status(self) -> Dict[str, any]:
        """
        Get sync status

        Returns:
            {
                "last_sync_time": "2025-10-28 15:06:00",
                "last_sync_time_iso": "2025-10-28T15:06:00+08:00",
                "interval_seconds": 360,
                "interval_minutes": 6,
                "data_source": "tushare",
                "success": True,
                "records_count": 5440,
                "error_message": None
            }
        """
        try:
            db = get_mongo_db()
            status_coll = db[self.status_collection_name]

            doc = await status_coll.find_one({"job": "quotes_ingestion"})

            if not doc:
                return {
                    "last_sync_time": None,
                    "last_sync_time_iso": None,
                    "interval_seconds": settings.QUOTES_INGEST_INTERVAL_SECONDS,
                    "interval_minutes": settings.QUOTES_INGEST_INTERVAL_SECONDS / 60,
                    "data_source": None,
                    "success": None,
                    "records_count": 0,
                    "error_message": "尚未执行过同步"
                }

            # Remove _id field
            doc.pop("_id", None)
            doc.pop("job", None)

            # Add minutes
            doc["interval_minutes"] = doc.get("interval_seconds", 0) / 60

            # 🔥 Format time (make sure to convert to local time zone)
            if "last_sync_time" in doc and doc["last_sync_time"]:
                dt = doc["last_sync_time"]
                # MongoDB Returns a datetime object in UTC time (aware or naive)
                # If it is naive, add UTC time zone; if it is aware, convert to local time zone
                if dt.tzinfo is None:
                    # naive datetime, Assume that UTC
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                # Convert to local time zone
                dt_local = dt.astimezone(self.tz)
                doc["last_sync_time"] = dt_local.strftime("%Y-%m-%d %H:%M:%S")

            return doc

        except Exception as e:
            logger.error(f"获取同步状态失败: {e}")
            return {
                "last_sync_time": None,
                "last_sync_time_iso": None,
                "interval_seconds": settings.QUOTES_INGEST_INTERVAL_SECONDS,
                "interval_minutes": settings.QUOTES_INGEST_INTERVAL_SECONDS / 60,
                "data_source": None,
                "success": None,
                "records_count": 0,
                "error_message": f"获取状态失败: {str(e)}"
            }

    def _check_tushare_permission(self) -> bool:
        """
        Detect Tushare rt_k interface permissions

        Returns:
            True: There is paid permission (can be called frequently)
            False: Free users (max 2 times per hour)
        """
        if self._tushare_permission_checked:
            return self._tushare_has_premium or False

        try:
            from app.services.data_sources.tushare_adapter import TushareAdapter
            adapter = TushareAdapter()

            if not adapter.is_available():
                logger.info("Tushare Not available, skip permission check")
                self._tushare_has_premium = False
                self._tushare_permission_checked = True
                return False

            # Try calling the rt_k interface to test permissions
            try:
                df = adapter._provider.api.rt_k(ts_code='000001.SZ')
                if df is not None and not getattr(df, 'empty', True):
                    logger.info("✅ Tushare rt_k interface permission detected (paid users)")
                    self._tushare_has_premium = True
                else:
                    logger.info("⚠️ Tushare rt_k The interface returns empty data (maybe free users or interface restrictions)")
                    self._tushare_has_premium = False
            except Exception as e:
                error_msg = str(e).lower()
                if "权限" in error_msg or "permission" in error_msg or "没有访问" in error_msg:
                    logger.info("⚠️ Tushare rt_k The interface has no permissions (free users)")
                    self._tushare_has_premium = False
                else:
                    logger.warning(f"⚠️ Tushare rt_k Interface test failed: {e}")
                    self._tushare_has_premium = False

            self._tushare_permission_checked = True
            return self._tushare_has_premium or False

        except Exception as e:
            logger.warning(f"Tushare Permission check failed: {e}")
            self._tushare_has_premium = False
            self._tushare_permission_checked = True
            return False

    async def _check_tushare_permission_async(self) -> bool:
        return await asyncio.to_thread(self._check_tushare_permission)

    async def _find_latest_trade_date_async(
        self,
        manager: DataSourceManager,
        preferred_sources: Optional[List[str]] = None,
    ) -> Optional[str]:
        return await asyncio.to_thread(manager.find_latest_trade_date_with_fallback, preferred_sources)

    async def _get_realtime_quotes_with_fallback_async(
        self,
        manager: DataSourceManager,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        return await asyncio.to_thread(manager.get_realtime_quotes_with_fallback)

    def _can_call_tushare(self) -> bool:
        """
        Determine whether the Tushare rt_k interface can be called

        Returns:
            True: Can be called
            False: Exceeds the limit and cannot be called
        """
        # If you are a paid user, there is no limit on the number of calls
        if self._tushare_has_premium:
            return True

        # Free users: Check the number of calls per hour
        now = datetime.now(self.tz)
        one_hour_ago = now - timedelta(hours=1)

        # Clear records from 1 hour ago
        while self._tushare_call_times and self._tushare_call_times[0] < one_hour_ago:
            self._tushare_call_times.popleft()

        # Check if limit is exceeded
        if len(self._tushare_call_times) >= self._tushare_hourly_limit:
            logger.warning(
                f"⚠️ Tushare rt_k The interface has reached the hourly call limit ({self._tushare_hourly_limit}times), "
                f"Skip this call and use the AKShare alternative interface"
            )
            return False

        return True

    def _record_tushare_call(self) -> None:
        """Record Tushare call time"""
        self._tushare_call_times.append(datetime.now(self.tz))

    def _get_next_source(self) -> Tuple[str, Optional[str]]:
        """
        Get the next data source (rotation mechanism)

        Returns:
            (source_type, akshare_api):
                - source_type: "tushare" | "akshare"
                - akshare_api: "eastmoney" | "sina" (only if source_type="akshare" valid when)
        """
        if not settings.QUOTES_ROTATION_ENABLED:
            # Rotation is not enabled, using default priority (AKShare Eastern Fortune)
            return "akshare", "eastmoney"

        # Rotation logic: AKShare Oriental Fortune ↔ AKShare Sina Finance (Tushare has been removed)
        current_source = self._rotation_sources[self._rotation_index]

        # Update rotation index (use next interface next time)
        self._rotation_index = (self._rotation_index + 1) % len(self._rotation_sources)

        if current_source == "akshare_eastmoney":
            return "akshare", "eastmoney"
        else:  # akshare_sina
            return "akshare", "sina"

    def _is_trading_time(self, now: Optional[datetime] = None) -> bool:
        """
        Determine whether it is during trading hours or post-closing buffer period

        Trading hours:
        - Morning:9:30-11:30
        - Afternoon:13:00-15:00
        - Post-closing buffer period:15:00-15:30 (Make sure to get the closing price)

        Description of the post-closing buffer period:
        - Continue to obtain for 30 minutes after the trading time ends
        - Assuming once every 6 minutes, 3 more synchronization opportunities can be added (15:06, 15:12, 15:18) 
        - Greatly reduces the risk of missing the closing price
        """
        now = now or datetime.now(self.tz)
        # working day Mon-Fri
        if now.weekday() > 4:
            return False
        t = now.time()
        # Shanghai Stock Exchange/Shenzhen Stock Exchange regular trading hours
        morning = dtime(9, 30)
        noon = dtime(11, 30)
        afternoon_start = dtime(13, 0)
        # Post-closing buffer period (extended by 30 minutes to 15:30) 
        buffer_end = dtime(15, 30)

        return (morning <= t <= noon) or (afternoon_start <= t <= buffer_end)

    async def _collection_empty(self) -> bool:
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            count = await coll.estimated_document_count()
            return count == 0
        except Exception:
            return True

    async def _collection_stale(self, latest_trade_date: Optional[str]) -> bool:
        if not latest_trade_date:
            return False
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            cursor = coll.find({}, {"trade_date": 1}).sort("trade_date", -1).limit(1)
            docs = await cursor.to_list(length=1)
            if not docs:
                return True
            doc_td = str(docs[0].get("trade_date") or "")
            return doc_td < str(latest_trade_date)
        except Exception:
            return True

    async def _bulk_upsert(self, quotes_map: Dict[str, Dict], trade_date: str, source: Optional[str] = None) -> None:
        db = get_mongo_db()
        coll = db[self.collection_name]
        ops = []
        updated_at = datetime.now(self.tz)
        for code, q in quotes_map.items():
            if not code:
                continue
            # Use a standardized approach to stock symbols (removing the exchange prefix, e.g. sz000001 -> 000001) 
            code6 = self._normalize_stock_code(code)
            if not code6:
                continue

            # 🔥 Log: record the written volume value
            volume = q.get("volume")
            if code6 in ["300750", "000001", "600000"]:  # Only record a few example stocks
                logger.info(f"📊 [write market_quotes] {code6} - volume={volume}, amount={q.get('amount')}, source={source}")

            ops.append(
                UpdateOne(
                    {"code": code6},
                    {"$set": {
                        "code": code6,
                        "symbol": code6,  # Add symbol field to be consistent with code
                        "close": q.get("close"),
                        "pct_chg": q.get("pct_chg"),
                        "amount": q.get("amount"),
                        "volume": volume,
                        "open": q.get("open"),
                        "high": q.get("high"),
                        "low": q.get("low"),
                        "pre_close": q.get("pre_close"),
                        "trade_date": trade_date,
                        "updated_at": updated_at,
                    }},
                    upsert=True,
                )
            )
        if not ops:
            logger.info("No data to write, skip")
            return
        result = await coll.bulk_write(ops, ordered=False)
        logger.info(
            f"✅ Quotation storage completed source={source}, matched={result.matched_count}, upserted={len(result.upserted_ids) if result.upserted_ids else 0}, modified={result.modified_count}"
        )

    async def backfill_from_historical_data(self) -> None:
        """
        Import the previous day s closing data from the historical data collection to market_quotes
        - If the market_quotes collection is empty, import all data
        - If market_quotes collection is not empty, check and fix missing volume field
        """
        try:
            # Check if market_quotes is empty
            is_empty = await self._collection_empty()

            if not is_empty:
                # The collection is not empty, check whether there are records with missing trading volume
                logger.info("✅ market_quotes The collection is not empty, check if the volume needs to be fixed...")
                await self._fix_missing_volume()
                return

            logger.info("📊 market_quotes The collection is empty, start importing from historical data")

            db = get_mongo_db()
            manager = self._get_dsm()

            # Get the latest trading day
            try:
                latest_trade_date = await self._find_latest_trade_date_async(manager)
                if not latest_trade_date:
                    logger.warning("⚠️ Unable to obtain the latest trading day, skipping historical data import")
                    return
            except Exception as e:
                logger.warning(f"⚠️ Failed to get latest trading day: {e}, Skip historical data import")
                return

            logger.info(f"📊 从历史数据集合导入 {latest_trade_date} 的收盘数据到 market_quotes")

            # Query the latest trading day data from the stock_daily_quotes collection
            daily_quotes_collection = db["stock_daily_quotes"]
            cursor = daily_quotes_collection.find({
                "trade_date": latest_trade_date,
                "period": "daily"
            })

            docs = await cursor.to_list(length=None)

            if not docs:
                logger.warning(f"⚠️ 历史数据集合中未找到 {latest_trade_date} 的数据")
                logger.warning("⚠️ market_quotes and historical data collections are empty, please synchronize historical data or real-time quotes first")
                return

            logger.info(f"✅ 从历史数据集合找到 {len(docs)} 条记录")

            # Convert to quotes_map format
            quotes_map = {}
            for doc in docs:
                code = doc.get("symbol") or doc.get("code")
                if not code:
                    continue
                code6 = str(code).zfill(6)

                # 🔥 To get the trading volume, use the volume field first
                volume_value = doc.get("volume") or doc.get("vol")
                data_source = doc.get("data_source", "")

                # 🔥 Log: record the original volume value
                if code6 in ["300750", "000001", "600000"]:  # Only record a few example stocks
                    logger.info(f"📊 [回填] {code6} - volume={doc.get('volume')}, vol={doc.get('vol')}, data_source={data_source}")

                quotes_map[code6] = {
                    "close": doc.get("close"),
                    "pct_chg": doc.get("pct_chg"),
                    "amount": doc.get("amount"),
                    "volume": volume_value,
                    "open": doc.get("open"),
                    "high": doc.get("high"),
                    "low": doc.get("low"),
                    "pre_close": doc.get("pre_close"),
                }

            if quotes_map:
                await self._bulk_upsert(quotes_map, latest_trade_date, "historical_data")
                logger.info(f"✅ 成功从历史数据导入 {len(quotes_map)} 条收盘数据到 market_quotes")
            else:
                logger.warning("⚠️ Historical data is empty after conversion and cannot be imported.")

        except Exception as e:
            logger.error(f"❌ 从历史数据导入失败: {e}")
            import traceback
            logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")

    async def backfill_last_close_snapshot(self) -> None:
        """Complement the last closing snapshot at once (for cold start or data staleness). Calls are allowed during the off-market period."""
        try:
            manager = self._get_dsm()
            # Use near-real-time snapshots as a back-up, and the last closing data returned during the off-market period is
            quotes_map, source = await self._get_realtime_quotes_with_fallback_async(manager)
            if not quotes_map:
                logger.warning("backfill: Market data not obtained, skip")
                return
            try:
                trade_date = await self._find_latest_trade_date_async(manager) or datetime.now(self.tz).strftime("%Y%m%d")
            except Exception:
                trade_date = datetime.now(self.tz).strftime("%Y%m%d")
            await self._bulk_upsert(quotes_map, trade_date, source)
        except Exception as e:
            logger.error(f"❌ backfill Quotation replenishment failed: {e}")

    async def backfill_last_close_snapshot_if_needed(self) -> None:
        """If the set is empty or trade_date lags behind the latest trading day, execute once backfill"""
        try:
            is_empty = await self._collection_empty()

            # If the collection is empty, priority is given to importing from historical data.
            if is_empty:
                logger.info("🔁 market_quotes The collection is empty, try to import from historical data")
                await self.backfill_from_historical_data()
                return

            # If the collection is not empty but the data is stale, use the real-time interface to update
            manager = self._get_dsm()
            latest_td = await self._find_latest_trade_date_async(manager)
            if await self._collection_stale(latest_td):
                logger.info("🔁 Trigger off/start period backfill to populate latest closing data")
                await self.backfill_last_close_snapshot()
        except Exception as e:
            logger.warning(f"backfill Trigger check failed (ignored): {e}")

    def _fetch_quotes_from_source(self, source_type: str, akshare_api: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get quotes from specified data source

        Args:
            source_type: "tushare" | "akshare"
            akshare_api: "eastmoney" | "sina" (only if source_type="akshare" valid when)

        Returns:
            (quotes_map, source_name)
        """
        try:
            if source_type == "tushare":
                # 🔥 The Tushare real-time market interface call has been disabled and is managed by the scheduled task run_tushare_realtime_quotes_hourly
                # Avoid conflict with the scheduled task of 31 minutes per hour (free users can only call it once per hour)
                logger.info("⏸️ Tushare The real-time market interface has been disabled and the call is skipped (managed by scheduled tasks)")
                return None, None

            elif source_type == "akshare":
                from app.services.data_sources.akshare_adapter import AKShareAdapter
                adapter = AKShareAdapter()

                if not adapter.is_available():
                    logger.warning("AKShare 不可用")
                    return None, None

                api_name = akshare_api or "eastmoney"
                logger.info(f"📊 使用 AKShare {api_name} 接口获取实时行情")
                quotes_map = adapter.get_realtime_quotes(source=api_name)

                if quotes_map:
                    return quotes_map, f"akshare_{api_name}"
                else:
                    logger.warning(f"AKShare {api_name} 返回空数据")
                    return None, None

            else:
                logger.error(f"未知数据源类型: {source_type}")
                return None, None

        except Exception as e:
            logger.error(f"从 {source_type} 获取行情失败: {e}")
            return None, None

    async def run_once(self) -> None:
        """
        Execute one collection and storage

        Core logic:
        1. Detecting Tushare permissions (first run)
        2. Try to get quotes in rotating order:Tushare → AKShare Oriental Fortune → AKShare Sina Finance
        3. If any interface succeeds, it will be included in the database. If it fails, the collection will be skipped.
        """
        # Processing during non-trading hours
        if not self._is_trading_time():
            if settings.QUOTES_BACKFILL_ON_OFFHOURS:
                await self.backfill_last_close_snapshot_if_needed()
            else:
                logger.info("⏭️ During non-trading hours, skip market collection")
            return

        try:
            # First run: Detecting Tushare permissions
            if settings.QUOTES_AUTO_DETECT_TUSHARE_PERMISSION and not self._tushare_permission_checked:
                logger.info("🔍 First run, check Tushare rt_k interface permissions...")
                has_premium = await self._check_tushare_permission_async()

                if has_premium:
                    logger.info(
                        "✅ Tushare paid permission detected! It is recommended to set QUOTES_INGEST_INTERVAL_SECONDS to 5-60 seconds to fully utilize the permissions"
                    )
                else:
                    logger.info(
                        f"ℹ️ Tushare 免费用户，每小时最多调用 {self._tushare_hourly_limit} 次 rt_k 接口。"
                        f"Current collection interval: {settings.QUOTES_INGEST_INTERVAL_SECONDS} seconds"
                    )

            # Get next data source
            source_type, akshare_api = self._get_next_source()

            # Synchronizing the third-party market interface may block for a long time; put it in a thread and add a timeout to avoid blocking the entire event loop.
            try:
                quotes_map, source_name = await asyncio.wait_for(
                    asyncio.to_thread(self._fetch_quotes_from_source, source_type, akshare_api),
                    timeout=REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                source_hint = source_type if source_type != "akshare" else f"akshare_{akshare_api or 'eastmoney'}"
                logger.error(
                    "❌ Timeout for obtaining real-time quotes: source=%s, timeout=%ss",
                    source_hint,
                    REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS,
                )
                await self._record_sync_status(
                    success=False,
                    source=source_hint,
                    records_count=0,
                    error_msg=f"获取实时行情超时（>{REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS}s）",
                )
                return

            if not quotes_map:
                logger.warning(f"⚠️ {source_name or source_type} No market data was obtained, skip this warehousing.")
                # Logging failure status
                await self._record_sync_status(
                    success=False,
                    source=source_name or source_type,
                    records_count=0,
                    error_msg="未获取到行情数据"
                )
                return

            # Get trading day
            try:
                manager = self._get_dsm()
                trade_date = await self._find_latest_trade_date_async(manager) or datetime.now(self.tz).strftime("%Y%m%d")
            except Exception:
                trade_date = datetime.now(self.tz).strftime("%Y%m%d")

            # Warehouse
            await self._bulk_upsert(quotes_map, trade_date, source_name)

            # Record success status
            await self._record_sync_status(
                success=True,
                source=source_name,
                records_count=len(quotes_map),
                error_msg=None
            )

        except Exception as e:
            logger.error(f"❌ 行情入库失败: {e}")
            # Logging failure status
            await self._record_sync_status(
                success=False,
                source=None,
                records_count=0,
                error_msg=str(e)
            )

