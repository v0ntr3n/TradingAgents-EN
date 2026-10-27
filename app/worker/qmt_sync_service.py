"""
QMT Data synchronization service

Sync QMT data to MongoDB.
Prerequisites:
  1. xtquant Library installed
  2. QMT Client started (Windows only)
  3. Obtaining market data does not require logging into a brokerage account
News is not supported, use AKShare uniformly.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd

from app.core.database import get_mongo_db
from app.core.config import settings
from app.services.historical_data_service import get_historical_data_service
from app.services.financial_data_service import get_financial_data_service
from app.services.data_sources.qmt_adapter import QMTAdapter

logger = logging.getLogger(__name__)

_qmt_sync_service = None


class QMTSyncService:
    """
    QMT Data synchronization service

    Provided by:
    - Synchronization of basic stock information
    - Real-time market synchronization (optional)
    """

    def __init__(self):
        self.adapter = QMTAdapter()
        self.db = None
        self.historical_service = None
        self.financial_service = None
        self.batch_size = 200
        self._current_job_id = None

    async def initialize(self):
        """Initialize synchronization service"""
        try:
            self.db = get_mongo_db()
            self.historical_service = await get_historical_data_service()
            self.financial_service = await get_financial_data_service()
            if not self.adapter.is_available():
                raise RuntimeError("❌ QMT Not available, please make sure the QMT client is started")
            logger.info("✅ QMT Synchronization service initialization completed")
        except Exception as e:
            logger.error(f"❌ QMT Sync service initialization failed: {e}")
            raise

    async def _get_qmt_symbols(self, symbols: Optional[List[str]] = None) -> List[str]:
        if symbols:
            return [str(symbol).zfill(6) for symbol in symbols if str(symbol).strip()]

        db_symbols = []
        cursor = self.db.stock_basic_info.find({"source": "qmt"}, {"code": 1})
        async for doc in cursor:
            code = str(doc.get("code", "")).zfill(6)
            if len(code) == 6:
                db_symbols.append(code)

        if db_symbols:
            return db_symbols

        df = self.adapter.get_stock_list()
        if df is None or df.empty:
            return []

        return [str(code).zfill(6) for code in df["symbol"].tolist() if str(code).strip()]

    def _normalize_period(self, period: str) -> str:
        period_map = {
            "daily": "day",
            "weekly": "week",
            "monthly": "month",
            "day": "day",
            "week": "week",
            "month": "month",
        }
        return period_map.get(period, period)

    def _normalize_financial_period(self, value: Any, fallback_index: Any = None) -> str:
        if value is None or value == "":
            value = fallback_index
        if value is None or value == "":
            return datetime.utcnow().strftime("%Y%m%d")
        try:
            parsed = pd.to_datetime(value)
            return parsed.strftime("%Y%m%d")
        except Exception:
            text = str(value).strip().replace("-", "").replace("/", "")
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) >= 8:
                return digits[:8]
            return datetime.utcnow().strftime("%Y%m%d")

    def _build_financial_payloads(self, symbol: str, financial_tables: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        grouped_payloads: Dict[str, Dict[str, Any]] = {}
        period_fields = [
            "report_period", "report_time", "m_timetag", "endDate", "end_date",
            "REPORT_PERIOD", "REPORT_TIME", "publish_date", "announce_time", "ann_date"
        ]

        for table_name, frame in financial_tables.items():
            if frame is None or frame.empty:
                continue

            normalized_frame = frame.copy()
            for index_value, row in normalized_frame.iterrows():
                row_dict = {}
                for key, value in row.items():
                    if hasattr(value, "item"):
                        try:
                            value = value.item()
                        except Exception:
                            pass
                    if pd.isna(value):
                        continue
                    row_dict[str(key)] = value

                period_value = None
                for field_name in period_fields:
                    if field_name in row_dict and row_dict[field_name] not in (None, ""):
                        period_value = row_dict[field_name]
                        break
                report_period = self._normalize_financial_period(period_value, index_value)

                payload = grouped_payloads.setdefault(
                    report_period,
                    {
                        "symbol": symbol,
                        "report_period": report_period,
                        "report_type": "annual" if report_period.endswith("1231") else "quarterly",
                        "tables": [],
                    },
                )
                payload[table_name] = row_dict
                payload["tables"].append(table_name)

        return list(grouped_payloads.values())

    async def sync_stock_basic_info(
        self,
        force_update: bool = False,
        job_id: str = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize basic stock information to MongoDB

        Args:
            force_update: Whether to force update
            job_id: Task ID (for progress tracking)
            symbols: Optional, synchronizes only the specified stock list; if empty, synchronizes the entire market

        Returns:
            Synchronization result statistics
        """
        self._current_job_id = job_id or "qmt_basic_info_sync"
        logger.info("🔄 Start QMT stock basic information synchronization...")

        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": [],
        }

        try:
            df = self.adapter.get_stock_list()
            if df is None or df.empty:
                logger.warning("⚠️ QMT No stock list obtained")
                return stats

            if symbols:
                symbol_set = {str(s).zfill(6) for s in symbols}
                df = df[df["symbol"].astype(str).str.zfill(6).isin(symbol_set)]
                if df.empty:
                    logger.warning(f"⚠️ QMT Specified stock not found: {symbols}")
                    return stats

            stats["total_processed"] = len(df)

            for i in range(0, len(df), self.batch_size):
                batch = df.iloc[i : i + self.batch_size]
                for _, row in batch.iterrows():
                    try:
                        code = str(row.get("symbol", "")).zfill(6)
                        if not code or len(code) != 6:
                            continue

                        if not force_update:
                            existing = await self.db.stock_basic_info.find_one({"code": code, "source": "qmt"})
                            if existing:
                                stats["skipped_count"] += 1
                                continue

                        doc = {
                            "code": code,
                            "symbol": code,
                            "name": row.get("name") or code,
                            "ts_code": row.get("ts_code", ""),
                            "source": "qmt",
                            "market": row.get("market", ""),
                            "area": row.get("area", ""),
                            "industry": row.get("industry", ""),
                            "list_date": row.get("list_date", ""),
                            "updated_at": datetime.utcnow(),
                        }

                        await self.db.stock_basic_info.update_one(
                            {"code": code, "source": "qmt"},
                            {"$set": doc},
                            upsert=True,
                        )
                        stats["success_count"] += 1
                    except Exception as e:
                        stats["error_count"] += 1
                        stats["errors"].append({"code": code, "error": str(e)})

                if i + self.batch_size < len(df):
                    await asyncio.sleep(0.1)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()

            logger.info(f"✅ QMT Basic stock information synchronization completed: success {stats['success_count']}, skip {stats['skipped_count']}, Error {stats['error_count']}")

            return stats
        except Exception as e:
            logger.error(f"❌ QMT Synchronization of basic stock information failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_stock_basic_info"})
            return stats

    async def sync_realtime_quotes(self, symbols: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
        """
        Synchronize real-time quotes to market_quotes (optional, requires QMT to run)

        Args:
            symbols: Specify a list of stocks, short will mean the entire market
            force: Whether to enforce

        Returns:
            Synchronization results
        """
        if not self.adapter.is_available():
            logger.warning("⚠️ QMT Not available, skip real-time market synchronization")
            return {"success_count": 0, "message": "QMT Not available"}

        try:
            quotes = self.adapter.get_realtime_quotes()
            if not quotes:
                return {"success_count": 0, "message": "Not getting quotes"}

            if symbols:
                quotes = {k: v for k, v in quotes.items() if k in symbols}

            if not quotes:
                return {"success_count": 0, "message": "No matching data"}

            count = 0
            now = datetime.utcnow()
            for code, q in quotes.items():
                try:
                    doc = {
                        "code": code,
                        "symbol": code,
                        "close": q.get("close"),
                        "pct_chg": q.get("pct_chg"),
                        "amount": q.get("amount"),
                        "source": "qmt",
                        "updated_at": now,
                    }
                    await self.db.market_quotes.update_one(
                        {"code": code},
                        {"$set": doc},
                        upsert=True,
                    )
                    count += 1
                except Exception as e:
                    logger.debug(f"QMT Quotation update failed {code}: {e}")

            return {"success_count": count, "total": len(quotes), "message": f"sync {count} only"}
        except Exception as e:
            logger.error(f"QMT Real-time market synchronization failed: {e}")
            return {"success_count": 0, "error": str(e)}

    async def sync_historical_data(
        self,
        days: int = 365,
        batch_size: int = 100,
        period: str = "daily",
        incremental: bool = True,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._current_job_id = self._current_job_id or "qmt_historical_sync"
        stats = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "historical_records": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": [],
        }

        try:
            symbol_list = await self._get_qmt_symbols(symbols)
            if not symbol_list:
                logger.warning("⚠️ QMT Historical synchronization did not obtain the stock list")
                return stats

            stats["total_processed"] = len(symbol_list)
            normalized_period = self._normalize_period(period)
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=max(days, 1))

            for index in range(0, len(symbol_list), batch_size):
                batch = symbol_list[index:index + batch_size]
                for symbol in batch:
                    try:
                        limit = max(days + 5, 30)
                        records = self.adapter.get_kline(symbol, period=normalized_period, limit=limit)
                        if not records:
                            stats["skipped_count"] += 1
                            continue

                        df = pd.DataFrame(records)
                        if df.empty:
                            stats["skipped_count"] += 1
                            continue

                        date_column = "date" if "date" in df.columns else "time" if "time" in df.columns else None
                        if date_column:
                            parsed_dates = pd.to_datetime(df[date_column], errors="coerce")
                            df = df.assign(date=parsed_dates.dt.strftime("%Y-%m-%d"))
                            df = df[parsed_dates.notna()]
                            if incremental:
                                df = df[(parsed_dates.dt.date >= start_date) & (parsed_dates.dt.date <= end_date)]

                        if df.empty:
                            stats["skipped_count"] += 1
                            continue

                        if "pre_close" not in df.columns and "close" in df.columns:
                            df["pre_close"] = pd.to_numeric(df["close"], errors="coerce").shift(1)

                        saved_count = await self.historical_service.save_historical_data(
                            symbol=symbol,
                            data=df,
                            data_source="qmt",
                            market="CN",
                            period=period,
                            overwrite=True,
                        )
                        if saved_count > 0:
                            stats["success_count"] += 1
                            stats["historical_records"] += saved_count
                        else:
                            stats["skipped_count"] += 1
                    except Exception as e:
                        stats["error_count"] += 1
                        stats["errors"].append({"symbol": symbol, "error": str(e), "context": "sync_historical_data"})

                if index + batch_size < len(symbol_list):
                    await asyncio.sleep(0.1)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            return stats
        except Exception as e:
            logger.error(f"❌ QMT Historical data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_historical_data"})
            return stats

    async def sync_financial_data(
        self,
        symbols: Optional[List[str]] = None,
        batch_size: int = 50,
        start_time: str = "",
        end_time: str = "",
    ) -> Dict[str, Any]:
        self._current_job_id = self._current_job_id or "qmt_financial_sync"
        stats = {
            "total_symbols": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "saved_records": 0,
            "start_time": datetime.utcnow(),
            "end_time": None,
            "duration": 0,
            "errors": [],
        }

        try:
            symbol_list = await self._get_qmt_symbols(symbols)
            if not symbol_list:
                logger.warning("⚠️ QMT Financial synchronization did not obtain the stock list")
                return stats

            stats["total_symbols"] = len(symbol_list)
            for index in range(0, len(symbol_list), batch_size):
                batch = symbol_list[index:index + batch_size]
                for symbol in batch:
                    try:
                        financial_tables = self.adapter.get_financial_data(
                            symbol,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        if not financial_tables:
                            stats["skipped_count"] += 1
                            continue

                        payloads = self._build_financial_payloads(symbol, financial_tables)
                        if not payloads:
                            stats["skipped_count"] += 1
                            continue

                        saved_for_symbol = 0
                        for payload in payloads:
                            saved_for_symbol += await self.financial_service.save_financial_data(
                                symbol=symbol,
                                financial_data=payload,
                                data_source="qmt",
                                market="CN",
                                report_period=payload.get("report_period"),
                                report_type=payload.get("report_type", "quarterly"),
                            )

                        if saved_for_symbol > 0:
                            stats["success_count"] += 1
                            stats["saved_records"] += saved_for_symbol
                        else:
                            stats["skipped_count"] += 1
                    except Exception as e:
                        stats["error_count"] += 1
                        stats["errors"].append({"symbol": symbol, "error": str(e), "context": "sync_financial_data"})

                if index + batch_size < len(symbol_list):
                    await asyncio.sleep(0.1)

            stats["end_time"] = datetime.utcnow()
            stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
            return stats
        except Exception as e:
            logger.error(f"❌ QMT Financial data synchronization failed: {e}")
            stats["errors"].append({"error": str(e), "context": "sync_financial_data"})
            return stats


async def _check_task_running(job_id: str) -> tuple[bool, Optional[str]]:
    try:
        from pymongo import MongoClient
        from app.services.scheduler_service import get_utc8_now

        sync_client = MongoClient(settings.MONGO_URI)
        sync_db = sync_client[settings.MONGODB_DATABASE]
        threshold_time = get_utc8_now() - timedelta(minutes=30)

        running_instance = sync_db.scheduler_executions.find_one(
            {
                "job_id": job_id,
                "status": "running",
                "timestamp": {"$gte": threshold_time},
            },
            sort=[("timestamp", -1)],
        )

        if running_instance:
            instance_id = str(running_instance.get("_id"))
            sync_client.close()
            return True, instance_id

        sync_client.close()
        return False, None
    except Exception as e:
        logger.warning(f"⚠️ Checking QMT task running status failed {job_id}: {e}")
        return False, None


async def get_qmt_sync_service() -> QMTSyncService:
    """Get the QMT synchronization service singleton"""
    global _qmt_sync_service
    if _qmt_sync_service is None:
        _qmt_sync_service = QMTSyncService()
        await _qmt_sync_service.initialize()
    return _qmt_sync_service


async def run_qmt_basic_info_sync(force_update: bool = False, job_id: str = None) -> Dict[str, Any]:
    """Run QMT stock basic information synchronization"""
    service = await get_qmt_sync_service()
    return await service.sync_stock_basic_info(force_update=force_update, job_id=job_id)


async def run_qmt_quotes_sync(symbols: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
    """Run QMT real-time market synchronization"""
    service = await get_qmt_sync_service()
    return await service.sync_realtime_quotes(symbols=symbols, force=force)


async def run_qmt_historical_sync(incremental: bool = True, **kwargs) -> Dict[str, Any]:
    job_id = "qmt_historical_sync"
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    if not manual_trigger and not force_execute:
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {"skipped": True, "reason": "There is already an instance running", "running_instance_id": instance_id}

    service = await get_qmt_sync_service()
    service._current_job_id = job_id
    return await service.sync_historical_data(
        days=kwargs.get("days", settings.QMT_HISTORICAL_SYNC_DAYS),
        batch_size=kwargs.get("batch_size", settings.QMT_HISTORICAL_BATCH_SIZE),
        period=kwargs.get("period", "daily"),
        incremental=incremental,
        symbols=kwargs.get("symbols"),
    )


async def run_qmt_financial_sync(**kwargs) -> Dict[str, Any]:
    job_id = "qmt_financial_sync"
    manual_trigger = kwargs.get("_manual_trigger", False)
    force_execute = kwargs.get("_force_execute", False)
    if not manual_trigger and not force_execute:
        is_running, instance_id = await _check_task_running(job_id)
        if is_running:
            logger.warning(f"⚠️ Task {job_id} There is already an instance running (_id={instance_id}) , Skip this execution")
            return {"skipped": True, "reason": "There is already an instance running", "running_instance_id": instance_id}

    service = await get_qmt_sync_service()
    service._current_job_id = job_id
    return await service.sync_financial_data(
        symbols=kwargs.get("symbols"),
        batch_size=kwargs.get("batch_size", settings.QMT_FINANCIAL_BATCH_SIZE),
        start_time=kwargs.get("start_time", ""),
        end_time=kwargs.get("end_time", ""),
    )


async def run_qmt_status_check() -> Dict[str, Any]:
    """Check QMT availability status"""
    adapter = QMTAdapter()
    available = adapter.is_available()
    latest_trade_date = adapter.find_latest_trade_date() if available else None
    result = {
        "available": available,
        "latest_trade_date": latest_trade_date,
        "checked_at": datetime.utcnow().isoformat(),
        "source": "qmt",
    }
    logger.info(f"QMT Status check results: {result}")
    return result
