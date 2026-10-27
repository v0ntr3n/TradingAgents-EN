"""
Multi-source stock basics synchronization service
- Supports multiple data sources with fallback mechanism
- Priority: Tushare > AKShare > BaoStock 
- Fetches A-share stock basic info with extended financial metrics
- Upserts into MongoDB collection `stock_basic_info`
- Provides unified interface for different data sources
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.core.database import get_mongo_db
from app.services.basics_sync import add_financial_metrics as _add_financial_metrics_util


logger = logging.getLogger(__name__)

# Collection names
COLLECTION_NAME = "stock_basic_info"
STATUS_COLLECTION = "sync_status"
JOB_KEY = "stock_basics_multi_source"
STOCK_LIST_FETCH_TIMEOUT_SECONDS = 45


class DataSourcePriority(Enum):
    """数据源优先级枚举"""
    TUSHARE = 1
    AKSHARE = 2
    BAOSTOCK = 3


@dataclass
class SyncStats:
    """同步统计信息"""
    job: str = JOB_KEY
    data_type: str = "stock_basics"  # Add data_type field to comply with database indexing requirements
    status: str = "idle"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    last_trade_date: Optional[str] = None
    data_sources_used: List[str] = field(default_factory=list)
    source_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    message: Optional[str] = None


class MultiSourceBasicsSyncService:
    """Multi-data source stock basic information synchronization service"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running = False
        self._last_status: Optional[Dict[str, Any]] = None
        self._current_task: Optional[asyncio.Task] = None

    async def start_background_sync(self, force: bool = False, preferred_sources: List[str] = None) -> Dict[str, Any]:
        """Start the synchronization task in the background and immediately return to the current state to avoid blocking front-end requests."""
        async with self._lock:
            if self._running:
                status = await self.get_status()
                status["launch_mode"] = "already_running"
                return status

            loop = asyncio.get_running_loop()
            self._current_task = loop.create_task(
                self.run_full_sync(force=force, preferred_sources=preferred_sources)
            )

        status = {
            "job": JOB_KEY,
            "status": "queued",
            "message": "同步任务已提交到后台执行",
            "started_at": datetime.now().isoformat(),
            "launch_mode": "background",
            "preferred_sources": preferred_sources or [],
        }
        self._last_status = status
        return status

    async def _try_mark_running(self, force: bool = False) -> bool:
        async with self._lock:
            if self._running and not force:
                return False
            self._running = True
            return True

    async def start_full_sync(
        self,
        force: bool = False,
        preferred_sources: List[str] = None,
    ) -> Dict[str, Any]:
        """Starts a background sync task and returns it to running status immediately."""
        if not await self._try_mark_running(force=force):
            logger.info("Multi-source stock basics sync already running; skip start")
            return await self.get_status()

        db = get_mongo_db()
        stats = SyncStats()
        stats.started_at = datetime.now().isoformat()
        stats.status = "running"
        stats.message = "Synchronization task started"
        await self._persist_status(db, stats.__dict__.copy())

        asyncio.create_task(self._run_full_sync_impl(db, stats, preferred_sources))
        return stats.__dict__.copy()

    async def get_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        if self._last_status and self._last_status.get("status") == "queued":
            return self._last_status

        db = get_mongo_db()
        doc = await db[STATUS_COLLECTION].find_one({"job": JOB_KEY})
        
        if doc:
            # Remove MongoDB's _id field to avoid serialization issues
            doc.pop("_id", None)
            
            # 🔥 Detect zombie tasks: If the status is running but it has been more than 30 minutes, it will be automatically marked as timed out.
            if doc.get("status") == "running":
                started_at_str = doc.get("started_at")
                if started_at_str:
                    try:
                        started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                        # If started_at has zone information, convert to local time
                        if started_at.tzinfo:
                            started_at = started_at.astimezone().replace(tzinfo=None)
                        
                        # Check if more than 30 minutes have passed
                        elapsed = datetime.now() - started_at
                        if elapsed > timedelta(minutes=30):
                            logger.warning(
                                f"⚠️ 检测到僵尸任务: {JOB_KEY} 已运行 {elapsed.total_seconds() / 60:.1f} 分钟，"
                                f"Automatically marked as timeout failure"
                            )
                            # Update status is failed
                            doc["status"] = "failed"
                            doc["message"] = f"任务超时（运行时间超过30分钟，实际运行 {elapsed.total_seconds() / 60:.1f} 分钟）"
                            doc["finished_at"] = datetime.now().isoformat()
                            
                            # Save updated status
                            await self._persist_status(db, doc)
                    except Exception as e:
                        logger.error(f"❌ 检测僵尸任务时出错: {e}")
            
            # Update memory cache
            self._last_status = doc
            return doc
        
        return {"job": JOB_KEY, "status": "never_run"}

    async def _persist_status(self, db: AsyncIOMotorDatabase, stats: Dict[str, Any]) -> None:
        """持久化同步状态"""
        stats["job"] = JOB_KEY

        # Use upsert to avoid duplicate key errors
        # Update or insert based on data_type and job
        filter_query = {
            "data_type": stats.get("data_type", "stock_basics"),
            "job": JOB_KEY
        }

        await db[STATUS_COLLECTION].update_one(
            filter_query,
            {"$set": stats},
            upsert=True
        )

        self._last_status = {k: v for k, v in stats.items() if k != "_id"}

    async def _execute_bulk_write_with_retry(
        self,
        db: AsyncIOMotorDatabase,
        operations: List,
        max_retries: int = 3
    ) -> Tuple[int, int]:
        """
        Perform batch writes with retry mechanism (thread-safe)

        Args:
            db: MongoDB Database instance
            operations: Bulk operation list
            max_retries: Maximum number of retries

        Returns:
            (New quantity, Update quantity)
        """
        try:
            # 🔥 Use thread-safe bulk_write
            from app.utils.thread_safe_db import safe_bulk_write

            result = await safe_bulk_write(
                collection_name=COLLECTION_NAME,
                operations=operations,
                ordered=False,
                async_db=db,
                max_retries=max_retries
            )

            inserted = result.upserted_count
            updated = result.modified_count
            logger.debug(f"✅ 批量写入成功: 新增 {inserted}, 更新 {updated}")
            return inserted, updated

        except Exception as e:
            logger.error(f"❌ 批量写入失败: {e}")
            return 0, 0

    async def run_full_sync(self, force: bool = False, preferred_sources: List[str] = None) -> Dict[str, Any]:
        """
        Run a full sync

        Args:
            force: Whether to force it to run (even if it is already running)
            preferred_sources: List of preferred data sources to use
        """
        if not await self._try_mark_running(force=force):
            logger.info("Multi-source stock basics sync already running; skip start")
            return await self.get_status()

        db = get_mongo_db()
        stats = SyncStats()
        stats.started_at = datetime.now().isoformat()
        stats.status = "running"
        await self._persist_status(db, stats.__dict__.copy())

        return await self._run_full_sync_impl(db, stats, preferred_sources)

    @staticmethod
    def _normalize_preferred_sources(preferred_sources: Optional[List[str]]) -> Optional[List[str]]:
        if not preferred_sources:
            return preferred_sources

        normalized: List[str] = []
        removed_sources: List[str] = []
        for source in preferred_sources:
            source_name = str(source or "").strip().lower()
            if not source_name:
                continue
            if source_name == "qmt":
                removed_sources.append(source_name)
                continue
            if source_name not in normalized:
                normalized.append(source_name)

        if removed_sources:
            logger.info(
                "🧹 [Synchronization of basic information from multiple data sources] Sources unsuitable for underlying information to initiate synchronization have been excluded from priority data sources: %s",
                removed_sources,
            )
        return normalized or None

    async def _fetch_stock_list_with_retry(
        self,
        manager,
        preferred_sources: Optional[List[str]],
    ) -> Tuple[Any, Optional[str]]:
        async def _fetch_once(sources: Optional[List[str]], attempt_label: str) -> Tuple[Any, Optional[str]]:
            start = time.perf_counter()
            logger.info(
                "📥 [Synchronization of basic information from multiple data sources] Start getting stock list: attempt=%s, preferred_sources=%s, timeout=%ss",
                attempt_label,
                sources or [],
                STOCK_LIST_FETCH_TIMEOUT_SECONDS,
            )
            stock_df, source_used = await asyncio.wait_for(
                asyncio.to_thread(manager.get_stock_list_with_fallback, sources, True),
                timeout=STOCK_LIST_FETCH_TIMEOUT_SECONDS,
            )
            elapsed = time.perf_counter() - start
            logger.info(
                "📥 [Synchronization of basic information from multiple data sources] Stock list acquisition completed: attempt=%s, source=%s, records=%s, elapsed=%.2fs",
                attempt_label,
                source_used,
                0 if stock_df is None else len(stock_df),
                elapsed,
            )
            return stock_df, source_used

        try:
            return await _fetch_once(preferred_sources, "primary")
        except asyncio.TimeoutError:
            logger.warning(
                "⏱ [Synchronization of basic information from multiple data sources] Stock list retrieval timed out: preferred_sources=%s, timeout=%ss",
                preferred_sources or [],
                STOCK_LIST_FETCH_TIMEOUT_SECONDS,
            )
            retry_sources = [source for source in (preferred_sources or []) if source != "qmt"]
            if retry_sources:
                logger.warning(
                    "↩️ [Synchronization of basic information from multiple data sources] Retry stock list retrieval and postpone QMT: retry_sources=%s",
                    retry_sources,
                )
                return await _fetch_once(retry_sources, "retry_without_qmt")
            raise

    async def _run_full_sync_impl(
        self,
        db: AsyncIOMotorDatabase,
        stats: SyncStats,
        preferred_sources: List[str] = None,
    ) -> Dict[str, Any]:
        """Execute real synchronization logic; reused by synchronization entrance or background task entrance."""

        try:
            preferred_sources = self._normalize_preferred_sources(preferred_sources)
            sync_start = time.perf_counter()
            logger.info(
                "🚀 [Synchronization of basic information from multiple data sources] Start execution: preferred_sources=%s",
                preferred_sources or [],
            )

            # Step 1: Get data source manager
            from app.services.data_sources.manager import DataSourceManager
            step_start = time.perf_counter()
            manager = DataSourceManager()
            available_adapters = manager.get_available_adapters()

            if not available_adapters:
                raise RuntimeError("No available data sources found")

            logger.info(
                "✅ [Synchronization of basic information from multiple data sources] Available data sources=%s, Time consuming=%.2fs",
                [adapter.name for adapter in available_adapters],
                time.perf_counter() - step_start,
            )

            # If a preferred data source is specified, log
            if preferred_sources:
                logger.info(f"Using preferred data sources: {preferred_sources}")

            # Step 2: Trying to get a list of stocks from a data source (excluding local data sources)
            stock_df, source_used = await self._fetch_stock_list_with_retry(manager, preferred_sources)
            if stock_df is None or getattr(stock_df, "empty", True):
                raise RuntimeError("All data sources failed to provide stock list")

            stats.data_sources_used.append(f"stock_list:{source_used}")
            logger.info(f"Successfully fetched {len(stock_df)} stocks from {source_used}")

            # Step 3: Get the latest trading dates and financial data
            step_start = time.perf_counter()
            latest_trade_date = await asyncio.to_thread(
                manager.find_latest_trade_date_with_fallback, preferred_sources
            )
            stats.last_trade_date = latest_trade_date
            logger.info(
                "🗓️ [Synchronization of basic information from multiple data sources] Latest trading day=%s, Time consuming=%.2fs",
                latest_trade_date,
                time.perf_counter() - step_start,
            )

            daily_data_map = {}
            daily_source = ""
            if latest_trade_date:
                step_start = time.perf_counter()
                daily_df, daily_source = await asyncio.to_thread(
                    manager.get_daily_basic_with_fallback, latest_trade_date, preferred_sources
                )
                if daily_df is not None and not daily_df.empty:
                    for _, row in daily_df.iterrows():
                        ts_code = row.get("ts_code")
                        if ts_code:
                            daily_data_map[ts_code] = row.to_dict()
                    stats.data_sources_used.append(f"daily_data:{daily_source}")
                logger.info(
                    "📈 [Synchronization of basic information from multiple data sources] daily_basic source=%s, records=%s, elapsed=%.2fs",
                    daily_source or "-",
                    0 if daily_df is None else len(daily_df),
                    time.perf_counter() - step_start,
                )

            from app.services.official_industry_service import (
                INDUSTRY_SOURCE_SYSTEM,
                fetch_industry_mapping,
            )

            step_start = time.perf_counter()
            industry_mapping = await fetch_industry_mapping(refresh_if_empty=True)
            use_system_industry_mapping = bool(industry_mapping)
            if use_system_industry_mapping:
                stats.data_sources_used.append(f"industry_mapping:{INDUSTRY_SOURCE_SYSTEM}")
                logger.info(f"📊 使用系统行业映射集合: {len(industry_mapping)} 只股票")
            logger.info(
                "🏷️ [Synchronization of basic information from multiple data sources] Industry mapping loading completed: enabled=%s, elapsed=%.2fs",
                use_system_industry_mapping,
                time.perf_counter() - step_start,
            )

            # Step 5: Process and update data (batch processing)
            ops = []
            inserted = updated = errors = 0
            batch_size = 500  # 🔥 Process 500 stocks per batch to avoid timeouts
            total_stocks = len(stock_df)

            logger.info(f"🚀 开始处理 {total_stocks} 只股票，数据源: {source_used}")

            for idx, (_, row) in enumerate(stock_df.iterrows(), 1):
                try:
                    # Extract basic information
                    name = row.get("name") or ""
                    area = row.get("area") or ""
                    industry = row.get("industry") or ""
                    market = row.get("market") or ""
                    list_date = row.get("list_date") or ""
                    ts_code = row.get("ts_code") or ""

                    # Extract 6-digit stock code
                    if isinstance(ts_code, str) and "." in ts_code:
                        code = ts_code.split(".")[0]
                    else:
                        symbol = row.get("symbol") or ""
                        code = str(symbol).zfill(6) if symbol else ""

                    mapped_industry = industry_mapping.get(code, "") if use_system_industry_mapping else ""
                    resolved_industry = mapped_industry or industry or "未知"

                    # Determine the exchange based on ts_code
                    if isinstance(ts_code, str):
                        if ts_code.endswith(".SH"):
                            sse = "上海证券交易所"
                        elif ts_code.endswith(".SZ"):
                            sse = "深圳证券交易所"
                        elif ts_code.endswith(".BJ"):
                            sse = "北京证券交易所"
                        else:
                            sse = "未知"
                    else:
                        sse = "未知"

                    category = "stock_cn"

                    # Get financial data
                    daily_metrics = {}
                    if isinstance(ts_code, str) and ts_code in daily_data_map:
                        daily_metrics = daily_data_map[ts_code]

                    # Generate full_symbol (make sure it is not empty)
                    full_symbol = ts_code if ts_code else self._generate_full_symbol(code)

                    # 🔥 Determine data source identification
                    # Set the source field according to the actual data source used
                    # NOTE: No longer used "multi_source" As default, there must be an explicit data source
                    if not source_used:
                        logger.warning(f"⚠️ 股票 {code} 没有明确的数据源，跳过")
                        errors += 1
                        continue
                    data_source = source_used

                    # Build documentation
                    doc = {
                        "code": code,
                        "symbol": code,  # Add symbol field (standardized field)
                        "name": name,
                        "area": area,
                        "industry": resolved_industry,
                        "market": market,
                        "list_date": list_date,
                        "sse": sse,
                        "full_symbol": full_symbol,  # Add full_symbol field
                        "category": category,
                        "source": data_source,  # 🔥 Use actual data sources
                        "updated_at": datetime.now(),
                    }

                    if mapped_industry:
                        doc["industry_source"] = INDUSTRY_SOURCE_SYSTEM

                    # Add financial metrics
                    self._add_financial_metrics(doc, daily_metrics)

                    # 🔥 Use (code, source) Union query conditions
                    ops.append(UpdateOne({"code": code, "source": data_source}, {"$set": doc}, upsert=True))

                except Exception as e:
                    logger.error(f"Error processing stock {row.get('ts_code', 'unknown')}: {e}")
                    errors += 1

                # 🔥 Perform database operations in batches
                if len(ops) >= batch_size or idx == total_stocks:
                    if ops:
                        progress_pct = (idx / total_stocks) * 100
                        logger.info(f"📝 执行批量写入: {len(ops)} 条记录 ({idx}/{total_stocks}, {progress_pct:.1f}%)")

                        batch_inserted, batch_updated = await self._execute_bulk_write_with_retry(db, ops)

                        if batch_inserted > 0 or batch_updated > 0:
                            inserted += batch_inserted
                            updated += batch_updated
                            logger.info(f"✅ 批量写入完成: 新增 {batch_inserted}, 更新 {batch_updated} | 累计: 新增 {inserted}, 更新 {updated}, 错误 {errors}")
                        else:
                            errors += len(ops)
                            logger.warning(f"⚠️ 批量写入失败，标记 {len(ops)} 条记录为错误")

                        ops = []  # Clear operation list

            # Step 7: Update statistics
            stats.total = total_stocks  # 🔥 Use total number of shares
            stats.inserted = inserted
            stats.updated = updated
            stats.errors = errors
            stats.status = "success" if errors == 0 else "success_with_errors"
            stats.finished_at = datetime.now().isoformat()

            try:
                await self._persist_status(db, stats.__dict__.copy())
                logger.info(
                    f"✅ Multi-source sync finished: total={stats.total} inserted={inserted} "
                    f"updated={updated} errors={errors} sources={stats.data_sources_used}"
                )
                logger.info(
                    "✅ [Synchronization of basic information from multiple data sources] Total time spent %.2fs",
                    time.perf_counter() - sync_start,
                )
            except Exception as persist_error:
                logger.error(f"❌ 保存成功状态时出错: {persist_error}")
                # Return results even if saving fails
            finally:
                # 🔥 Clear the memory cache to ensure that the latest status is read from the database the next time you query
                self._last_status = None
            
            return stats.__dict__

        except Exception as e:
            stats.status = "failed"
            stats.message = str(e)
            stats.finished_at = datetime.now().isoformat()
            try:
                await self._persist_status(db, stats.__dict__.copy())
            except Exception as persist_error:
                logger.error(f"❌ 保存失败状态时出错: {persist_error}")
            logger.exception(f"Multi-source sync failed: {e}")
            return stats.__dict__
        finally:
            # 🔥 Ensure that both the running status and the final status are updated regardless of success or failure
            async with self._lock:
                self._running = False
                # Clear the memory cache and force the latest status to be read from the database next time
                self._last_status = None



    def _add_financial_metrics(self, doc: Dict, daily_metrics: Dict) -> None:
        """entrusted to basics_sync.processing.add_financial_metrics"""
        return _add_financial_metrics_util(doc, daily_metrics)

    def _generate_full_symbol(self, code: str) -> str:
        """
        Generate complete standardized code based on stock symbol

        Args:
            code: 6 stock code

        Returns:
            Full normalized code, or original code if unrecognized (make sure not empty)
        """
        # Make sure code is not empty
        if not code:
            return ""

        # Normalize to string and remove spaces
        code = str(code).strip()

        # If the length is not 6, return the original code
        if len(code) != 6:
            return code

        # Determine the exchange based on the code prefix
        if code.startswith(('60', '68', '90')):  # Shanghai Stock Exchange
            return f"{code}.SS"
        elif code.startswith(('00', '30', '20')):  # Shenzhen Stock Exchange
            return f"{code}.SZ"
        elif code.startswith(('8', '4', '92')):  # Beijing Stock Exchange (92 is the unified number range starting from 2025-10)
            return f"{code}.BJ"
        else:
            # Unrecognized code, return original code (make sure it is not empty)
            return code if code else ""


# Global service instance
_multi_source_sync_service = None

def get_multi_source_sync_service() -> MultiSourceBasicsSyncService:
    """获取多数据源同步服务实例"""
    global _multi_source_sync_service
    if _multi_source_sync_service is None:
        _multi_source_sync_service = MultiSourceBasicsSyncService()
    return _multi_source_sync_service
