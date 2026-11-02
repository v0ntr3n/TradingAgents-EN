from __future__ import annotations
import sys as _sys
import types as _types
import app.routers as _routers_pkg
_self_mod = _sys.modules[__name__]
_snapshots = {}

# === sync.py ===
"""
Sync router for stock basics and ETF synchronization
- POST /api/sync/stock_basics/run -> trigger full sync
- GET  /api/sync/stock_basics/status -> get last status
- POST /api/sync/etf/run -> trigger ETF sync (etf_basic_info + etf_daily_quotes)
Requires MongoDB initialized by app lifespan.
"""

from fastapi import APIRouter, HTTPException, Query

from app.services.basics_sync_service import get_basics_sync_service

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/stock_basics/run")
async def run_stock_basics_sync(force: bool = False):
    try:
        service = get_basics_sync_service()
        result = await service.start_full_sync(force=force)
        return {
            "success": True,
            "message": result.get("message") or "Synchronization task started",
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock_basics/status")
async def get_stock_basics_status():
    service = get_basics_sync_service()
    status = await service.get_status()
    return {"success": True, "data": status}


@router.post("/etf/run")
async def trigger_etf_sync(
    force: bool = Query(False, description="Whether to force overwriting of existing data"),
    days: int = Query(30, ge=1, le=365, description="Number of days to force synchronization back (force=false Ignored, the first full amount/subsequent increments will be automatically executed)"),
):
    """Trigger ETF data synchronization (etf_basic_info + etf_daily_quotes) """
    try:
        from app.worker.etf_sync_service import run_etf_sync
        result = await run_etf_sync(force_update=force, days=days)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

_snapshots['sync'] = dict(globals())

# === stock_sync.py ===
"""
Stock data synchronization API routing
Supports synchronization of historical and financial data for individual stocks or batches of stocks
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.response import ok
from app.core.database import get_mongo_db
from app.worker.tushare_sync_service import get_tushare_sync_service
from app.worker.akshare_sync_service import get_akshare_sync_service
from app.worker.financial_data_sync_service import get_financial_sync_service
from app.worker.etf_sync_service import get_etf_sync_service
from app.services.data_validation_service import get_data_validation_service
import logging
import asyncio
from datetime import datetime, timedelta
from fastapi import Query

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/api/stock-sync", tags=["Stock data synchronization"])

STOCK_SYNC_TASKS_COLLECTION = "stock_sync_tasks"
TASK_TERMINAL_STATUSES = {"success", "success_with_errors", "failed"}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _request_to_dict(request: BaseModel) -> Dict[str, Any]:
    if hasattr(request, "model_dump"):
        return request.model_dump()
    return request.dict()


def _serialize_task_doc(task_doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not task_doc:
        return None
    serialized = dict(task_doc)
    serialized.pop("_id", None)
    return serialized


def _get_single_task_message(symbol: str, result: Dict[str, Any]) -> str:
    if result.get("overall_success"):
        return f"stocks {symbol} Data synchronization successful"
    return f"stocks {symbol} Data sync partially failed"


def _get_batch_task_status(request: "BatchStockSyncRequest", result: Dict[str, Any]) -> str:
    total_symbols = len(request.symbols)
    if total_symbols <= 0:
        return "failed"

    section_success_flags: List[bool] = []
    section_has_success = False

    if request.sync_historical:
        success_count = (result.get("historical_sync") or {}).get("success_count", 0)
        section_success_flags.append(success_count >= total_symbols)
        section_has_success = section_has_success or success_count > 0

    if request.sync_financial:
        success_count = (result.get("financial_sync") or {}).get("success_count", 0)
        section_success_flags.append(success_count >= total_symbols)
        section_has_success = section_has_success or success_count > 0

    if request.sync_basic:
        success_count = (result.get("basic_sync") or {}).get("success_count", 0)
        section_success_flags.append(success_count >= total_symbols)
        section_has_success = section_has_success or success_count > 0

    if section_success_flags and all(section_success_flags):
        return "success"
    if section_has_success:
        return "success_with_errors"
    return "failed"


def _get_batch_task_message(result: Dict[str, Any]) -> str:
    total_symbols = result.get("total_symbols") or len(result.get("symbols") or [])
    total_success = result.get("total_success", 0)
    if total_success >= total_symbols and total_symbols > 0:
        return f"Batch synchronization completed: {total_success}/{total_symbols} Only stocks are successful"
    if total_success > 0:
        return f"Batch sync partially completed: {total_success}/{total_symbols} Only stocks are successful"
    return "Batch sync failed"


async def _create_stock_sync_task(
    task_type: str,
    payload: Dict[str, Any],
    current_user: dict,
) -> Dict[str, Any]:
    db = get_mongo_db()
    task_id = uuid4().hex
    now_iso = _utc_now_iso()
    task_doc = {
        "task_id": task_id,
        "task_type": task_type,
        "status": "pending",
        "message": "The synchronization task has been submitted",
        "payload": payload,
        "symbol": payload.get("symbol"),
        "symbols": payload.get("symbols"),
        "created_at": now_iso,
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
        "submitted_by": str(
            current_user.get("username")
            or current_user.get("user_id")
            or current_user.get("id")
            or "unknown"
        ),
    }
    await db[STOCK_SYNC_TASKS_COLLECTION].insert_one(task_doc)
    return _serialize_task_doc(task_doc) or {}


async def _update_stock_sync_task(task_id: str, updates: Dict[str, Any]) -> None:
    db = get_mongo_db()
    await db[STOCK_SYNC_TASKS_COLLECTION].update_one(
        {"task_id": task_id},
        {"$set": updates},
        upsert=False,
    )


async def _get_stock_sync_task(task_id: str) -> Optional[Dict[str, Any]]:
    db = get_mongo_db()
    task_doc = await db[STOCK_SYNC_TASKS_COLLECTION].find_one({"task_id": task_id})
    return _serialize_task_doc(task_doc)


async def _execute_stock_sync_task(task_id: str, task_type: str, payload: Dict[str, Any]) -> None:
    await _update_stock_sync_task(
        task_id,
        {
            "status": "running",
            "message": "Synchronization task in progress",
            "started_at": _utc_now_iso(),
            "error": None,
        },
    )

    try:
        if task_type == "single":
            request = SingleStockSyncRequest(**payload)
            result = await run_single_stock_sync(request)
            status = "success" if result.get("overall_success") else "success_with_errors"
            message = _get_single_task_message(request.symbol, result)
        elif task_type == "batch":
            request = BatchStockSyncRequest(**payload)
            result = await run_batch_stock_sync(request)
            status = _get_batch_task_status(request, result)
            message = _get_batch_task_message(result)
        else:
            raise RuntimeError(f"Unknown sync task type: {task_type}")

        await _update_stock_sync_task(
            task_id,
            {
                "status": status,
                "message": message,
                "result": result,
                "finished_at": _utc_now_iso(),
                "error": None,
            },
        )
    except Exception as e:
        logger.error(f"❌ Sync tasks {task_id} Execution failed: {e}", exc_info=True)
        await _update_stock_sync_task(
            task_id,
            {
                "status": "failed",
                "message": f"Sync failed: {str(e)}",
                "finished_at": _utc_now_iso(),
                "error": str(e),
            },
        )


ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


def _is_cn_etf_symbol(symbol: str) -> bool:
    text = str(symbol or "").strip()
    return len(text) == 6 and text.isdigit() and text.startswith(ETF_CODE_PREFIXES)


async def _sync_latest_to_market_quotes(symbol: str) -> None:
    """
    Synchronize the latest data in stock_daily_quotes to market_quotes

    Intelligent judgment logic:
    - If there is already updated data in market_quotes (trade_date update), it will not be overwritten.
    - Update if there is no data in market_quotes or the data is older

    Args:
        symbol: Stock code (6 digits)
    """
    db = get_mongo_db()
    symbol6 = str(symbol).zfill(6)

    # Get the latest data from stock_daily_quotes
    latest_doc = await db.stock_daily_quotes.find_one(
        {"symbol": symbol6},
        sort=[("trade_date", -1)]
    )

    if not latest_doc:
        logger.warning(f"⚠️ {symbol6}: stock_daily_quotes There is no data in")
        return

    historical_trade_date = latest_doc.get("trade_date")

    # 🔥 Check if there is updated data in market_quotes
    existing_quote = await db.market_quotes.find_one({"code": symbol6})

    if existing_quote:
        existing_trade_date = existing_quote.get("trade_date")

        # If the data date in market_quotes is newer or the same, it is not overwritten
        if existing_trade_date and historical_trade_date:
            # Compare date strings (format: YYYY-MM-DD or YYYYMMDD)
            existing_date_str = str(existing_trade_date).replace("-", "")
            historical_date_str = str(historical_trade_date).replace("-", "")

            if existing_date_str >= historical_date_str:
                # 🔥 When the dates are the same or updated, they will not be overwritten (to avoid overwriting real-time data with historical data)
                logger.info(
                    f"⏭️ {symbol6}: market_quotes data date in >= Historical data date "
                    f"(market_quotes: {existing_trade_date}, historical: {historical_trade_date}), Skip coverage"
                )
                return

    # Extract required fields
    quote_data = {
        "code": symbol6,
        "symbol": symbol6,
        "close": latest_doc.get("close"),
        "price": latest_doc.get("close"),
        "current_price": latest_doc.get("close"),
        "open": latest_doc.get("open"),
        "high": latest_doc.get("high"),
        "low": latest_doc.get("low"),
        "volume": latest_doc.get("volume"),  # Units have been converted
        "amount": latest_doc.get("amount"),  # Units have been converted
        "pct_chg": latest_doc.get("pct_chg"),
        "pre_close": latest_doc.get("pre_close"),
        "trade_date": latest_doc.get("trade_date"),
        "updated_at": datetime.utcnow()
    }

    # 🔥 Log: record synchronized trading volume
    logger.info(
        f"📊 [Sync to market_quotes] {symbol6} - "
        f"volume={quote_data['volume']}, amount={quote_data['amount']}, trade_date={quote_data['trade_date']}"
    )

    # update market_quotes
    await db.market_quotes.update_one(
        {"code": symbol6},
        {"$set": quote_data},
        upsert=True
    )


class SingleStockSyncRequest(BaseModel):
    """Single stock sync request"""
    symbol: str = Field(..., description="Stock code (6 digits)")
    sync_realtime: bool = Field(False, description="Whether to synchronize real-time quotes")
    sync_historical: bool = Field(True, description="Whether to synchronize historical data")
    sync_financial: bool = Field(True, description="Whether to synchronize financial data")
    sync_basic: bool = Field(False, description="Whether to synchronize basic data")
    data_source: str = Field("tushare", description="data source: tushare/akshare/qmt")
    days: int = Field(30, description="Historical data days", ge=1, le=3650)


class BatchStockSyncRequest(BaseModel):
    """Bulk stock sync request"""
    symbols: List[str] = Field(..., description="Stock code list")
    sync_historical: bool = Field(True, description="Whether to synchronize historical data")
    sync_financial: bool = Field(True, description="Whether to synchronize financial data")
    sync_basic: bool = Field(False, description="Whether to synchronize basic data")
    data_source: str = Field("tushare", description="data source: tushare/akshare/qmt")
    days: int = Field(30, description="Historical data days", ge=1, le=3650)


async def run_single_stock_sync(request: SingleStockSyncRequest) -> dict:
    """Execute single stock data synchronization and return the original synchronization result dictionary."""
    logger.info(f"📊 Start syncing a single stock: {request.symbol} (data source: {request.data_source})")
    is_etf = _is_cn_etf_symbol(request.symbol)
    if is_etf:
        logger.info(f"📈 {request.symbol} Identified as ETF, historical/basic synchronization will use ETF-specific synchronization service")

    result = {
        "symbol": request.symbol,
        "realtime_sync": None,
        "historical_sync": None,
        "financial_sync": None,
        "basic_sync": None
    }

    # Synchronize real-time quotes
    if request.sync_realtime:
        try:
            # 🔥 Single stock real-time quotation synchronization: use AKShare first (to avoid Tushare interface restrictions)
            actual_data_source = request.data_source
            if request.data_source == "tushare":
                logger.info("💡 Synchronize real-time quotes of individual stocks and automatically switch to AKShare data source (avoiding Tushare interface limitations)")
                actual_data_source = "akshare"

            if actual_data_source == "tushare":
                service = await get_tushare_sync_service()
            elif actual_data_source == "akshare":
                service = await get_akshare_sync_service()
            elif actual_data_source == "qmt":
                from app.worker.qmt_sync_service import get_qmt_sync_service

                service = await get_qmt_sync_service()
            else:
                raise ValueError(f"Unsupported data source: {actual_data_source}")

            # Synchronize real-time quotes (only synchronize specified stocks)
            if actual_data_source == "akshare":
                realtime_result = await service.sync_realtime_quotes(
                    symbols=[request.symbol],
                    force=True,
                    manual_mode=True  # Manual interface should not inherit scheduled task cancellation status
                )
            elif actual_data_source == "qmt":
                realtime_result = await service.sync_realtime_quotes(
                    symbols=[str(request.symbol).zfill(6)],
                    force=True
                )
            else:
                realtime_result = await service.sync_realtime_quotes(
                    symbols=[request.symbol],
                    force=True  # Enforce execution, skip transaction time check
                )

            success = realtime_result.get("success_count", 0) > 0

            message = f"Real-time market synchronization{'success' if success else 'failed'}"
            if request.data_source == "tushare" and actual_data_source == "akshare":
                message += " (Automatically switched to AKShare data source)"

            result["realtime_sync"] = {
                "success": success,
                "message": message,
                "data_source_used": actual_data_source
            }
            logger.info(f"✅ {request.symbol} Real-time market synchronization completed: {success}")

        except Exception as e:
            logger.error(f"❌ {request.symbol} Real-time market synchronization failed: {e}")
            result["realtime_sync"] = {
                "success": False,
                "error": str(e)
            }

    # Synchronize historical data
    if request.sync_historical:
        try:
            if is_etf:
                etf_service = await get_etf_sync_service()
                hist_result = await etf_service._sync_daily_by_source(
                    request.data_source,
                    [request.symbol],
                    request.days,
                    True
                )

                result["historical_sync"] = {
                    "success": hist_result.get("success_count", 0) > 0,
                    "records": hist_result.get("records_inserted", 0),
                    "message": f"Synced {hist_result.get('records_inserted', 0)} ETF history"
                }
                logger.info(f"✅ {request.symbol} ETF Historical data synchronization completed: {hist_result.get('records_inserted', 0)} records")
            else:
                if request.data_source == "tushare":
                    service = await get_tushare_sync_service()
                elif request.data_source == "akshare":
                    service = await get_akshare_sync_service()
                elif request.data_source == "qmt":
                    from app.worker.qmt_sync_service import get_qmt_sync_service

                    service = await get_qmt_sync_service()
                else:
                    raise ValueError(f"Unsupported data source: {request.data_source}")

                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=request.days)).strftime('%Y-%m-%d')

                if request.data_source == "akshare":
                    hist_result = await service.sync_historical_data(
                        symbols=[request.symbol],
                        start_date=start_date,
                        end_date=end_date,
                        incremental=False,
                        manual_mode=True,
                    )
                elif request.data_source == "qmt":
                    hist_result = await service.sync_historical_data(
                        symbols=[str(request.symbol).zfill(6)],
                        days=request.days,
                        period="daily",
                        incremental=False,
                    )
                else:
                    hist_result = await service.sync_historical_data(
                        symbols=[request.symbol],
                        start_date=start_date,
                        end_date=end_date,
                        incremental=False
                    )

                result["historical_sync"] = {
                    "success": hist_result.get("success_count", 0) > 0,
                    "records": hist_result.get("total_records", hist_result.get("historical_records", 0)),
                    "message": (
                        f"Synced {hist_result.get('total_records', hist_result.get('historical_records', 0))} history records"
                    )
                }
                logger.info(
                    f"✅ {request.symbol} Historical data synchronization completed: "
                    f"{hist_result.get('total_records', hist_result.get('historical_records', 0))} records"
                )

                if hist_result.get("success_count", 0) > 0:
                    try:
                        await _sync_latest_to_market_quotes(request.symbol)
                        logger.info(f"✅ {request.symbol} The latest data has been synced to market_quotes")
                    except Exception as e:
                        logger.warning(f"⚠️ {request.symbol} Sync to market_quotes failed: {e}")

        except Exception as e:
            logger.error(f"❌ {request.symbol} Historical data synchronization failed: {e}")
            result["historical_sync"] = {
                "success": False,
                "error": str(e)
            }

    # Sync financial data
    if request.sync_financial:
        try:
            if request.data_source == "qmt":
                from app.worker.qmt_sync_service import get_qmt_sync_service

                qmt_service = await get_qmt_sync_service()
                fin_result = await qmt_service.sync_financial_data(symbols=[str(request.symbol).zfill(6)])
                success = fin_result.get("success_count", 0) > 0
            else:
                financial_service = await get_financial_sync_service()

                fin_result = await financial_service.sync_single_stock(
                    symbol=request.symbol,
                    data_sources=[request.data_source]
                )

                success = fin_result.get(request.data_source, False)
            result["financial_sync"] = {
                "success": success,
                "message": "Financial data synchronization successful" if success else "Financial data synchronization failed"
            }
            logger.info(f"✅ {request.symbol} Financial data synchronization completed: {success}")

        except Exception as e:
            logger.error(f"❌ {request.symbol} Financial data synchronization failed: {e}")
            result["financial_sync"] = {
                "success": False,
                "error": str(e)
            }

    # Synchronize basic data
    if request.sync_basic:
        try:
            # 🔥 Synchronize basic data of a single stock
            # Refer to the implementation logic of basics_sync_service
            if is_etf:
                etf_service = await get_etf_sync_service()
                basic_result = await etf_service._sync_basic_by_source(
                    request.data_source,
                    True,
                    [request.symbol],
                )
                success = basic_result.get("success_count", 0) > 0
                result["basic_sync"] = {
                    "success": success,
                    "message": "ETF Basic data synchronization successful" if success else "ETF Basic data synchronization failed",
                    "error": None if success else "; ".join(item.get("error", "unknown error") for item in basic_result.get("errors", [])[:3])
                }
                logger.info(f"✅ {request.symbol} ETF Basic data synchronization completed: {success}")
            elif request.data_source == "tushare":
                from app.services.basics_sync import (
                    fetch_stock_basic_df,
                    find_latest_trade_date,
                    fetch_daily_basic_mv_map,
                    fetch_latest_roe_map,
                )

                db = get_mongo_db()
                symbol6 = str(request.symbol).zfill(6)

                stock_df = await asyncio.to_thread(fetch_stock_basic_df)
                if stock_df is None or stock_df.empty:
                    result["basic_sync"] = {
                        "success": False,
                        "error": "Tushare Return empty data"
                    }
                else:
                    stock_row = None
                    for _, row in stock_df.iterrows():
                        ts_code = row.get("ts_code", "")
                        if isinstance(ts_code, str) and ts_code.startswith(symbol6):
                            stock_row = row
                            break

                    if stock_row is None:
                        result["basic_sync"] = {
                            "success": False,
                            "error": f"No stock found {symbol6} basic information"
                        }
                    else:
                        latest_trade_date = await asyncio.to_thread(find_latest_trade_date)
                        daily_data_map = await asyncio.to_thread(fetch_daily_basic_mv_map, latest_trade_date)
                        roe_map = await asyncio.to_thread(fetch_latest_roe_map)

                        now_iso = datetime.utcnow().isoformat()

                        name = stock_row.get("name") or ""
                        area = stock_row.get("area") or ""
                        industry = stock_row.get("industry") or ""
                        market = stock_row.get("market") or ""
                        list_date = stock_row.get("list_date") or ""
                        ts_code = stock_row.get("ts_code") or ""

                        if isinstance(ts_code, str) and "." in ts_code:
                            code = ts_code.split(".")[0]
                        else:
                            code = symbol6

                        if isinstance(ts_code, str):
                            if ts_code.endswith(".SH"):
                                sse = "Shanghai Stock Exchange"
                            elif ts_code.endswith(".SZ"):
                                sse = "Shenzhen Stock Exchange"
                            elif ts_code.endswith(".BJ"):
                                sse = "Beijing Stock Exchange"
                            else:
                                sse = "unknown"
                        else:
                            sse = "unknown"

                        full_symbol = ts_code

                        daily_metrics = {}
                        if isinstance(ts_code, str) and ts_code in daily_data_map:
                            daily_metrics = daily_data_map[ts_code]

                        total_mv_yi = None
                        circ_mv_yi = None
                        if "total_mv" in daily_metrics:
                            try:
                                total_mv_yi = float(daily_metrics["total_mv"]) / 10000.0
                            except Exception:
                                pass
                        if "circ_mv" in daily_metrics:
                            try:
                                circ_mv_yi = float(daily_metrics["circ_mv"]) / 10000.0
                            except Exception:
                                pass

                        doc = {
                            "code": code,
                            "symbol": code,
                            "name": name,
                            "area": area,
                            "industry": industry,
                            "market": market,
                            "list_date": list_date,
                            "sse": sse,
                            "sec": "stock_cn",
                            "source": "tushare",
                            "updated_at": now_iso,
                            "full_symbol": full_symbol,
                        }

                        if total_mv_yi is not None:
                            doc["total_mv"] = total_mv_yi
                        if circ_mv_yi is not None:
                            doc["circ_mv"] = circ_mv_yi

                        for field in ["pe", "pb", "ps", "pe_ttm", "pb_mrq", "ps_ttm"]:
                            if field in daily_metrics:
                                doc[field] = daily_metrics[field]

                        if isinstance(ts_code, str) and ts_code in roe_map:
                            roe_val = roe_map[ts_code].get("roe")
                            if roe_val is not None:
                                doc["roe"] = roe_val

                        for field in ["turnover_rate", "volume_ratio"]:
                            if field in daily_metrics:
                                doc[field] = daily_metrics[field]

                        for field in ["total_share", "float_share"]:
                            if field in daily_metrics:
                                doc[field] = daily_metrics[field]

                        await db.stock_basic_info.update_one(
                            {"code": code, "source": "tushare"},
                            {"$set": doc},
                            upsert=True
                        )

                        result["basic_sync"] = {
                            "success": True,
                            "message": "Basic data synchronization successful"
                        }
                        logger.info(f"✅ {request.symbol} Basic data synchronization completed")

            elif request.data_source == "qmt":
                from app.worker.qmt_sync_service import get_qmt_sync_service

                qmt_service = await get_qmt_sync_service()
                sync_result = await qmt_service.sync_stock_basic_info(
                    force_update=True,
                    symbols=[request.symbol],
                )
                success_count = sync_result.get("success_count", 0)
                result["basic_sync"] = {
                    "success": success_count > 0,
                    "message": f"Basic data synchronization{'success' if success_count > 0 else 'failed'}" + (
                        " (QMT Requires trading terminal to run)" if success_count == 0 else ""
                    ),
                }
                logger.info(f"✅ {request.symbol} Basic data synchronization completed (QMT): {success_count}")

            elif request.data_source == "akshare":
                db = get_mongo_db()
                symbol6 = str(request.symbol).zfill(6)

                existing_stock = await db.stock_basic_info.find_one(
                    {"code": symbol6},
                    {"name": 1}
                )
                fallback_name = existing_stock.get("name") if existing_stock and existing_stock.get("name") else f"stocks{symbol6}"

                service = await get_akshare_sync_service()
                from app.services.official_industry_service import (
                    INDUSTRY_SOURCE_SYSTEM,
                    fetch_industry_mapping,
                )

                industry_mapping = await fetch_industry_mapping(refresh_if_empty=True)
                mapped_industry = industry_mapping.get(symbol6, "") if industry_mapping else ""

                # Single-share synchronization allows the combination of multiple interfaces, avoiding complete dependence on the Dongcai details interface.
                basic_info = await service.provider.get_stock_basic_info_for_single_sync(symbol6)
                if not basic_info:
                    basic_info = await service.provider.get_stock_basic_info(symbol6)

                if basic_info:
                    if hasattr(basic_info, 'model_dump'):
                        basic_data = basic_info.model_dump()
                    elif hasattr(basic_info, 'dict'):
                        basic_data = basic_info.dict()
                    else:
                        basic_data = basic_info

                    if basic_data.get("name") == f"stocks{symbol6}" and fallback_name != f"stocks{symbol6}":
                        basic_data["name"] = fallback_name
                        logger.debug(f"📝 Use the stock name from the database: {fallback_name}")

                    if mapped_industry:
                        raw_industry = str(basic_data.get("industry") or "").strip()
                        basic_data["industry"] = mapped_industry
                        basic_data["industry_source"] = INDUSTRY_SOURCE_SYSTEM
                        if raw_industry and raw_industry != mapped_industry:
                            logger.info(
                                f"🔁 {symbol6} AK Original industries have been replaced with system industry mappings: {raw_industry} -> {mapped_industry}"
                            )

                    detail_fetch_error = basic_data.pop("detail_fetch_error", None)
                    detail_fetch_symbol = basic_data.pop("detail_fetch_symbol", None)
                    degraded_sync = basic_data.get("sync_status") == "degraded"

                    basic_data["code"] = symbol6
                    basic_data["symbol"] = symbol6
                    basic_data["source"] = "akshare"
                    basic_data["updated_at"] = datetime.utcnow().isoformat()

                    await db.stock_basic_info.update_one(
                        {"code": symbol6, "source": "akshare"},
                        {"$set": basic_data},
                        upsert=True
                    )

                    if degraded_sync:
                        result["basic_sync"] = {
                            "success": False,
                            "degraded": True,
                            "message": "The basic data has been downgraded and written, and the AKShare stock details interface failed.",
                            "error": detail_fetch_error or "AKShare Individual stock details interface failed",
                            "detail_symbol": detail_fetch_symbol,
                        }
                        logger.warning(
                            f"⚠️ {request.symbol} Basic data only completes downgrade synchronization (AKShare): {detail_fetch_error or 'Individual stock details interface failed'}"
                        )
                    else:
                        result["basic_sync"] = {
                            "success": True,
                            "message": "Basic data synchronization successful"
                        }
                        logger.info(f"✅ {request.symbol} Basic data synchronization completed (AKShare)")
                else:
                    result["basic_sync"] = {
                        "success": False,
                        "error": "Basic data not obtained"
                    }
            else:
                result["basic_sync"] = {
                    "success": False,
                    "error": f"Basic data synchronization only supports Tushare/AKShare/QMT data sources, the current data source: {request.data_source}"
                }

        except Exception as e:
            logger.error(f"❌ {request.symbol} Basic data synchronization failed: {e}")
            result["basic_sync"] = {
                "success": False,
                "error": str(e)
            }

    overall_success = (
        (not request.sync_realtime or result["realtime_sync"].get("success", False)) and
        (not request.sync_historical or result["historical_sync"].get("success", False)) and
        (not request.sync_financial or result["financial_sync"].get("success", False)) and
        (not request.sync_basic or result["basic_sync"].get("success", False))
    )

    result["overall_success"] = overall_success
    return result


@router.post("/single")
async def sync_single_stock(
    request: SingleStockSyncRequest,
    current_user: dict = Depends(get_current_user)
):
    """Submit a single synchronization task and return to the task status immediately."""
    try:
        payload = _request_to_dict(request)
        task_doc = await _create_stock_sync_task("single", payload, current_user)
        asyncio.create_task(_execute_stock_sync_task(task_doc["task_id"], "single", payload))
        return ok(data=task_doc, message="Stock synchronization task has been submitted")
    except Exception as e:
        logger.error(f"❌ Failed to submit single-strand synchronization task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit synchronization task: {str(e)}")


async def run_batch_stock_sync(request: BatchStockSyncRequest) -> dict:
    """
    Batch sync historical data and financial data of multiple stocks

    - **symbols**: Stock code list
    - **sync_historical**: Whether to synchronize historical data
    - **sync_financial**: Whether to synchronize financial data
    - **data_source**: Data source (tushare/akshare)
    - **days**: Historical data days
    """
    try:
        logger.info(f"📊 Start batch sync {len(request.symbols)} only stocks (data source: {request.data_source})")

        result = {
            "total": len(request.symbols),
            "symbols": request.symbols,
            "historical_sync": None,
            "financial_sync": None,
            "basic_sync": None
        }

        if request.sync_historical:
            try:
                if request.data_source == "tushare":
                    service = await get_tushare_sync_service()
                elif request.data_source == "akshare":
                    service = await get_akshare_sync_service()
                elif request.data_source == "qmt":
                    from app.worker.qmt_sync_service import get_qmt_sync_service

                    service = await get_qmt_sync_service()
                else:
                    raise ValueError(f"Unsupported data source: {request.data_source}")

                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=request.days)).strftime('%Y-%m-%d')

                if request.data_source == "qmt":
                    hist_result = await service.sync_historical_data(
                        symbols=[str(symbol).zfill(6) for symbol in request.symbols],
                        days=request.days,
                        period="daily",
                        incremental=False,
                    )
                else:
                    hist_result = await service.sync_historical_data(
                        symbols=request.symbols,
                        start_date=start_date,
                        end_date=end_date,
                        incremental=False
                    )

                result["historical_sync"] = {
                    "success_count": hist_result.get("success_count", 0),
                    "error_count": hist_result.get("error_count", 0),
                    "total_records": hist_result.get("total_records", hist_result.get("historical_records", 0)),
                    "message": (
                        f"Synced successfully {hist_result.get('success_count', 0)}/{len(request.symbols)} only stocks,"
                        f"total {hist_result.get('total_records', hist_result.get('historical_records', 0))} records"
                    )
                }
                logger.info(f"✅ Batch historical data synchronization completed: {hist_result.get('success_count', 0)}/{len(request.symbols)}")

            except Exception as e:
                logger.error(f"❌ Batch historical data synchronization failed: {e}")
                result["historical_sync"] = {
                    "success_count": 0,
                    "error_count": len(request.symbols),
                    "error": str(e)
                }

        if request.sync_financial:
            try:
                if request.data_source == "qmt":
                    from app.worker.qmt_sync_service import get_qmt_sync_service

                    qmt_service = await get_qmt_sync_service()
                    fin_results = await qmt_service.sync_financial_data(
                        symbols=[str(symbol).zfill(6) for symbol in request.symbols]
                    )
                    result["financial_sync"] = {
                        "success_count": fin_results.get("success_count", 0),
                        "error_count": fin_results.get("error_count", 0),
                        "total_symbols": fin_results.get("total_symbols", len(request.symbols)),
                        "message": (
                            f"Synced successfully {fin_results.get('success_count', 0)}/"
                            f"{fin_results.get('total_symbols', len(request.symbols))} Financial data for only stocks"
                        )
                    }
                else:
                    financial_service = await get_financial_sync_service()

                    fin_results = await financial_service.sync_financial_data(
                        symbols=request.symbols,
                        data_sources=[request.data_source],
                        batch_size=10
                    )

                    source_stats = fin_results.get(request.data_source)
                    if source_stats:
                        result["financial_sync"] = {
                            "success_count": source_stats.success_count,
                            "error_count": source_stats.error_count,
                            "total_symbols": source_stats.total_symbols,
                            "message": f"Synced successfully {source_stats.success_count}/{source_stats.total_symbols} Financial data for only stocks"
                        }
                    else:
                        result["financial_sync"] = {
                            "success_count": 0,
                            "error_count": len(request.symbols),
                            "message": "Financial data synchronization failed"
                        }

                logger.info(f"✅ Batch financial data synchronization completed: {result['financial_sync']['success_count']}/{len(request.symbols)}")

            except Exception as e:
                logger.error(f"❌ Batch financial data synchronization failed: {e}")
                result["financial_sync"] = {
                    "success_count": 0,
                    "error_count": len(request.symbols),
                    "error": str(e)
                }

        if request.sync_basic:
            try:
                if request.data_source == "tushare":
                    from tradingagents.dataflows.providers.china.tushare import TushareProvider

                    tushare_provider = TushareProvider()
                    if tushare_provider.is_available():
                        success_count = 0
                        error_count = 0

                        for symbol in request.symbols:
                            try:
                                basic_info = await tushare_provider.get_stock_basic_info(symbol)

                                if basic_info:
                                    db = get_mongo_db()
                                    symbol6 = str(symbol).zfill(6)

                                    basic_info["code"] = symbol6
                                    basic_info["source"] = "tushare"
                                    basic_info["updated_at"] = datetime.utcnow()

                                    await db.stock_basic_info.update_one(
                                        {"code": symbol6, "source": "tushare"},
                                        {"$set": basic_info},
                                        upsert=True
                                    )

                                    success_count += 1
                                    logger.info(f"✅ {symbol} Basic data synchronization successful")
                                else:
                                    error_count += 1
                                    logger.warning(f"⚠️ {symbol} Basic data not obtained")
                            except Exception as e:
                                error_count += 1
                                logger.error(f"❌ {symbol} Basic data synchronization failed: {e}")

                        result["basic_sync"] = {
                            "success_count": success_count,
                            "error_count": error_count,
                            "total_symbols": len(request.symbols),
                            "message": f"Synced successfully {success_count}/{len(request.symbols)} Basic data of only stocks"
                        }
                        logger.info(f"✅ Batch basic data synchronization completed: {success_count}/{len(request.symbols)}")
                    else:
                        result["basic_sync"] = {
                            "success_count": 0,
                            "error_count": len(request.symbols),
                            "error": "Tushare Data source is not available"
                        }
                elif request.data_source == "qmt":
                    from app.worker.qmt_sync_service import get_qmt_sync_service

                    qmt_service = await get_qmt_sync_service()
                    sync_result = await qmt_service.sync_stock_basic_info(
                        force_update=True,
                        symbols=request.symbols,
                    )
                    success_count = sync_result.get("success_count", 0)
                    error_count = sync_result.get("error_count", 0)
                    result["basic_sync"] = {
                        "success_count": success_count,
                        "error_count": error_count,
                        "total_symbols": len(request.symbols),
                        "message": f"Synced successfully {success_count}/{len(request.symbols)} Basic data of only stocks (QMT)",
                    }
                    logger.info(f"✅ Batch basic data synchronization completed (QMT): {success_count}/{len(request.symbols)}")
                else:
                    result["basic_sync"] = {
                        "success_count": 0,
                        "error_count": len(request.symbols),
                        "error": f"Basic data synchronization only supports Tushare/QMT data source, the current data source: {request.data_source}"
                    }

            except Exception as e:
                logger.error(f"❌ Batch basic data synchronization failed: {e}")
                result["basic_sync"] = {
                    "success_count": 0,
                    "error_count": len(request.symbols),
                    "error": str(e)
                }

        hist_success = result["historical_sync"].get("success_count", 0) if request.sync_historical else 0
        fin_success = result["financial_sync"].get("success_count", 0) if request.sync_financial else 0
        basic_success = result["basic_sync"].get("success_count", 0) if request.sync_basic else 0
        total_success = max(hist_success, fin_success, basic_success)

        result["total_success"] = total_success
        result["total_symbols"] = len(request.symbols)

        return result

    except Exception as e:
        logger.error(f"❌ Batch sync failed: {e}")
        raise RuntimeError(f"Batch sync failed: {str(e)}") from e


@router.post("/batch")
async def sync_batch_stocks(
    request: BatchStockSyncRequest,
    current_user: dict = Depends(get_current_user)
):
    """Submit a batch synchronization task and return the task status immediately."""
    try:
        payload = _request_to_dict(request)
        task_doc = await _create_stock_sync_task("batch", payload, current_user)
        asyncio.create_task(_execute_stock_sync_task(task_doc["task_id"], "batch", payload))
        return ok(data=task_doc, message="Batch synchronization task has been submitted")
    except Exception as e:
        logger.error(f"❌ Failed to submit batch synchronization task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit batch synchronization task: {str(e)}")


@router.get("/tasks/{task_id}")
async def get_stock_sync_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Query the status and results of manual stock synchronization tasks."""
    try:
        task_doc = await _get_stock_sync_task(task_id)
        if not task_doc:
            raise HTTPException(status_code=404, detail="Synchronization task does not exist")
        return ok(data=task_doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to obtain synchronization task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to obtain synchronization task status: {str(e)}")


@router.get("/status/{symbol}")
async def get_sync_status(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get the sync status of a stock
    
    Returns information such as the last synchronization time, number of data items, etc.
    """
    try:
        from app.core.database import get_mongo_db
        
        db = get_mongo_db()
        
        # Query the last synchronization time of historical data
        hist_doc = await db.historical_data.find_one(
            {"symbol": symbol},
            sort=[("date", -1)]
        )
        
        # Query the last synchronization time of financial data
        fin_doc = await db.stock_financial_data.find_one(
            {"symbol": symbol},
            sort=[("updated_at", -1)]
        )
        
        # Statistics of historical data items
        hist_count = await db.historical_data.count_documents({"symbol": symbol})
        
        # Statistical financial data items
        fin_count = await db.stock_financial_data.count_documents({"symbol": symbol})
        
        return ok(data={
            "symbol": symbol,
            "historical_data": {
                "last_sync": hist_doc.get("updated_at") if hist_doc else None,
                "last_date": hist_doc.get("date") if hist_doc else None,
                "total_records": hist_count
            },
            "financial_data": {
                "last_sync": fin_doc.get("updated_at") if fin_doc else None,
                "last_report_period": fin_doc.get("report_period") if fin_doc else None,
                "total_records": fin_count
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.get("/validate", response_model=dict)
async def validate_stock_data(
    symbol: str = Query(..., description="Stock code (6 digits)"),
    analysis_date: Optional[str] = Query(None, description="Analysis date (YYYY-MM-DD), default is today"),
    market_type: str = Query("cn", description="Market type:cn/hk/us"),
    check_basic_info: bool = Query(True, description="Whether to check basic information"),
    check_historical_data: bool = Query(True, description="Whether to check historical data"),
    check_financial_data: bool = Query(False, description="Whether to check financial data"),
    check_realtime_quotes: bool = Query(False, description="Whether to check real-time market conditions"),
    current_user: dict = Depends(get_current_user)
):
    """
    Data verification interface
    Verify the integrity and validity of stock data
    
    Args:
        symbol: Stock code
        analysis_date: Analysis date (YYYY-MM-DD), default is today
        market_type: Market type (cn/hk/us)
        check_basic_info: Whether to check basic information
        check_historical_data: Whether to check historical data
        check_financial_data: Whether to check financial data
        check_realtime_quotes: Whether to check real-time market conditions
        
    Returns:
        Verification results, including is_valid, message, missing_data, details
    """
    try:
        # If no analysis date is specified, today is used
        if not analysis_date:
            analysis_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get data verification service
        validation_service = get_data_validation_service()
        
        # Perform verification
        result = await validation_service.validate_stock_data(
            symbol=symbol,
            analysis_date=analysis_date,
            market_type=market_type,
            check_basic_info=check_basic_info,
            check_historical_data=check_historical_data,
            check_financial_data=check_financial_data,
            check_realtime_quotes=check_realtime_quotes
        )
        
        return ok(data={
            "is_valid": result.is_valid,
            "message": result.message,
            "missing_data": result.missing_data,
            "details": result.details
        })
        
    except Exception as e:
        logger.error(f"❌ Data verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Data verification failed: {str(e)}")


@router.post("/industry-from-official", response_model=dict)
async def sync_industry_from_official(current_user: dict = Depends(get_current_user)):
    """
    Synchronize industry data from the official website URL to stock_basic_info
    Need to configure OFFICIAL_INDUSTRY_DATA_URL, format: {"600519":"Liquor","000001":"bank"}
    """
    try:
        from app.services.official_industry_service import sync_industry_to_stock_basic_info, get_official_industry_url
        if not get_official_industry_url():
            raise HTTPException(
                status_code=400,
                detail="OFFICIAL_INDUSTRY_DATA_URL is not configured, please set the official website industry data JSON in .env URL"
            )
        result = await sync_industry_to_stock_basic_info()
        return ok(data=result, message=f"Industry data synchronization completed and updated {result.get('updated', 0)} Article")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Industry data synchronization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Industry data synchronization failed: {str(e)}")

_snapshots['stock_sync'] = dict(globals())

# === multi_source_sync.py ===
"""
Multi-source synchronization API routes
Provides endpoints for multi-source stock data synchronization
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
from app.services.data_sources.manager import DataSourceManager

logger = logging.getLogger(__name__)

DATA_SOURCE_STATUS_TIMEOUT_SECONDS = 8

router = APIRouter(prefix="/api/sync/multi-source", tags=["Multi-Source Sync"])


async def _get_available_adapters_async(manager: DataSourceManager):
    return await asyncio.wait_for(
        asyncio.to_thread(manager.get_available_adapters),
        timeout=DATA_SOURCE_STATUS_TIMEOUT_SECONDS,
    )


class SyncRequest(BaseModel):
    """Synchronous request model"""
    force: bool = False
    preferred_sources: Optional[List[str]] = None


class SyncResponse(BaseModel):
    """Synchronous response model"""
    success: bool
    message: str
    data: Union[Dict[str, Any], List[Any], Any]


class DataSourceStatus(BaseModel):
    """Data source state model"""
    name: str
    priority: int
    available: bool
    description: str


@router.get("/sources/status")
async def get_data_sources_status():
    """Get the status of all data sources"""
    try:
        manager = DataSourceManager()
        available_adapters = await _get_available_adapters_async(manager)
        all_adapters = manager.adapters

        status_list = []
        for adapter in all_adapters:
            is_available = adapter in available_adapters

            # Provide description based on data source type
            descriptions = {
                "tushare": "Professional financial data API, providing high-quality A-share data and financial indicators",
                "akshare": "Open source financial database, providing basic stock information",
                "baostock": "Free and open source securities data platform, providing historical data"
            }

            status_item = {
                "name": adapter.name,
                "priority": adapter.priority,
                "available": is_available,
                "description": descriptions.get(adapter.name, f"{adapter.name}data source")
            }

            # Add Token source information (Tushare only)
            if adapter.name == "tushare" and is_available and hasattr(adapter, 'get_token_source'):
                token_source = adapter.get_token_source()
                if token_source:
                    status_item["token_source"] = token_source
                    if token_source == 'database':
                        status_item["description"] += " (Token Source: database)"
                    elif token_source == 'env':
                        status_item["description"] += " (Token Source: .env)"

            status_list.append(status_item)

        return SyncResponse(
            success=True,
            message="Data sources status retrieved successfully",
            data=status_list
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get data sources status: {str(e)}")


@router.get("/sources/current")
async def get_current_data_source():
    """Get the data source currently in use (the one with the highest priority and available)"""
    try:
        manager = DataSourceManager()
        available_adapters = await _get_available_adapters_async(manager)

        if not available_adapters:
            return SyncResponse(
                success=False,
                message="No available data sources",
                data={"name": None, "priority": None}
            )

        # Get the highest priority available data source (the higher the priority number, the higher)
        current_adapter = max(available_adapters, key=lambda x: x.priority)

        # Provide description based on data source type
        descriptions = {
            "tushare": "Professional financial data API",
            "akshare": "Open source financial database",
            "baostock": "Free securities data platform"
        }

        result = {
            "name": current_adapter.name,
            "priority": current_adapter.priority,
            "description": descriptions.get(current_adapter.name, current_adapter.name)
        }

        # Add Token source information (Tushare only)
        if current_adapter.name == "tushare" and hasattr(current_adapter, 'get_token_source'):
            token_source = current_adapter.get_token_source()
            if token_source:
                result["token_source"] = token_source
                if token_source == 'database':
                    result["token_source_display"] = "Database configuration"
                elif token_source == 'env':
                    result["token_source_display"] = ".env Configuration"

        return SyncResponse(
            success=True,
            message="Current data source retrieved successfully",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current data source: {str(e)}")


@router.get("/status")
async def get_sync_status():
    """Get synchronization status of multiple data sources"""
    try:
        service = get_multi_source_sync_service()
        status = await service.get_status()
        
        return SyncResponse(
            success=True,
            message="Status retrieved successfully",
            data=status
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.post("/stock_basics/run")
async def run_stock_basics_sync(
    force: bool = Query(False, description="Whether to force synchronization to run"),
    preferred_sources: Optional[str] = Query(None, description="Preferred data sources, separated by commas")
):
    """Run multi-data source stock basic information synchronization"""
    try:
        service = get_multi_source_sync_service()

        # Parse priority data sources
        sources_list = None
        if preferred_sources and isinstance(preferred_sources, str):
            sources_list = [s.strip() for s in preferred_sources.split(",") if s.strip()]

        # Change to background execution to avoid long-term blocking of front-end requests
        result = await service.start_background_sync(force=force, preferred_sources=sources_list)

        success = result.get("status") in ["queued", "running", "success", "success_with_errors"]
        message = "Synchronization task accepted"

        if result.get("launch_mode") == "already_running":
            message = result.get("message") or "Synchronization is already running"
        elif result.get("status") == "queued":
            message = result.get("message") or "Synchronization started in background"

        return SyncResponse(
            success=success,
            message=message,
            data=result
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run synchronization: {str(e)}")


async def _test_single_adapter(adapter) -> dict:
    """
    Test connectivity for a single data source adapter
    Only perform lightweight connectivity tests without obtaining complete data
    """
    result = {
        "name": adapter.name,
        "priority": adapter.priority,
        "available": False,
        "message": "Connection failed"
    }

    # Connectivity test timeout (seconds)
    test_timeout = 10

    try:
        # Test connectivity - force reconnect to use latest configuration
        logger.info(f"🧪 test {adapter.name} connectivity (timeout: {test_timeout}seconds)...")

        try:
            # For Tushare, force reconnect to use latest database configuration
            if adapter.name == "tushare" and hasattr(adapter, '_provider'):
                logger.info(f"🔄 force {adapter.name} Reconnect to use latest configuration...")
                provider = adapter._provider
                if provider:
                    # Reset connection status
                    provider.connected = False
                    provider.token_source = None
                    # Reconnect
                    await asyncio.wait_for(
                        asyncio.to_thread(provider.connect_sync),
                        timeout=test_timeout
                    )

            # Run in thread pool is_available() Check
            is_available = await asyncio.wait_for(
                asyncio.to_thread(adapter.is_available),
                timeout=test_timeout
            )

            if is_available:
                result["available"] = True

                # Get Token source (Tushare only)
                token_source = None
                if adapter.name == "tushare" and hasattr(adapter, 'get_token_source'):
                    token_source = adapter.get_token_source()

                if token_source == 'database':
                    result["message"] = "✅ Connection successful (Token Source: database)"
                    result["token_source"] = "database"
                elif token_source == 'env':
                    result["message"] = "✅ Connection successful (Token Source: .env)"
                    result["token_source"] = "env"
                else:
                    result["message"] = "✅ Connection successful"

                logger.info(f"✅ {adapter.name} Connectivity test successful, Token source: {token_source}")
            else:
                result["available"] = False
                result["message"] = "❌ Data source is not available"
                logger.warning(f"⚠️ {adapter.name} Not available")
        except asyncio.TimeoutError:
            result["available"] = False
            result["message"] = f"❌ Connection timeout ({test_timeout}seconds)"
            logger.warning(f"⚠️ {adapter.name} Connection timeout")
        except Exception as e:
            result["available"] = False
            result["message"] = f"❌ Connection failed: {str(e)}"
            logger.error(f"❌ {adapter.name} Connection failed: {e}")

    except Exception as e:
        result["available"] = False
        result["message"] = f"❌ Test exception: {str(e)}"
        logger.error(f"❌ test {adapter.name} error: {e}")

    return result


class TestSourceRequest(BaseModel):
    """Test data source request"""
    source_name: str | None = None


@router.post("/test-sources")
async def test_data_sources(request: TestSourceRequest = TestSourceRequest()):
    """
    Test connectivity to data sources

    parameters:
    - source_name: Optionally, specify the name of the data source to test. If not specified, all data sources are tested

    Only perform lightweight connectivity tests without obtaining complete data
    - test timeout: 10 seconds
    - Only obtain 1 data verification connection
    - Return results quickly
    """
    try:
        manager = DataSourceManager()
        all_adapters = manager.adapters

        # Get the data source name from the request body
        source_name = request.source_name
        logger.info(f"📥 Test request received,source_name={source_name}")

        # If a data source name is specified, only that data source is tested
        if source_name:
            adapters_to_test = [a for a in all_adapters if a.name.lower() == source_name.lower()]
            if not adapters_to_test:
                raise HTTPException(
                    status_code=400,
                    detail=f"Data source '{source_name}' not found"
                )
            logger.info(f"🧪 Start testing the data source: {source_name}")
        else:
            adapters_to_test = all_adapters
            logger.info(f"🧪 Start testing {len(all_adapters)} data source connectivity...")

        # Concurrent test adapter (executes in background thread)
        test_tasks = [_test_single_adapter(adapter) for adapter in adapters_to_test]
        test_results = await asyncio.gather(*test_tasks, return_exceptions=True)

        # Handle abnormal results
        final_results = []
        for i, result in enumerate(test_results):
            if isinstance(result, Exception):
                logger.error(f"❌ test adapter {adapters_to_test[i].name} error: {result}")
                final_results.append({
                    "name": adapters_to_test[i].name,
                    "priority": adapters_to_test[i].priority,
                    "available": False,
                    "message": f"❌ Test exception: {str(result)}"
                })
            else:
                final_results.append(result)

        # Statistical results
        available_count = sum(1 for r in final_results if r.get("available"))
        if source_name:
            logger.info(f"✅ data source {source_name} Test completed: {'Available' if available_count > 0 else 'Not available'}")
        else:
            logger.info(f"✅ Data source connectivity test completed: {available_count}/{len(final_results)} Available")

        return SyncResponse(
            success=True,
            message=f"Tested {len(final_results)} data sources, {available_count} available",
            data={"test_results": final_results}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error while testing data source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test data sources: {str(e)}")


@router.get("/recommendations")
async def get_sync_recommendations():
    """Get data source usage suggestions"""
    try:
        manager = DataSourceManager()
        available_adapters = await _get_available_adapters_async(manager)
        
        recommendations = {
            "primary_source": None,
            "fallback_sources": [],
            "suggestions": [],
            "warnings": []
        }
        
        if available_adapters:
            # Recommend the highest priority available data source as the primary data source
            primary = available_adapters[0]
            recommendations["primary_source"] = {
                "name": primary.name,
                "priority": primary.priority,
                "reason": "Highest priority available data source"
            }
            
            # Other available data sources as backup
            for adapter in available_adapters[1:]:
                recommendations["fallback_sources"].append({
                    "name": adapter.name,
                    "priority": adapter.priority
                })
        
        # Generate suggestions
        if not available_adapters:
            recommendations["warnings"].append("No data sources are available. Please check your configuration.")
        elif len(available_adapters) == 1:
            recommendations["suggestions"].append("Consider configuring additional data sources for redundancy.")
        else:
            recommendations["suggestions"].append(f"You have {len(available_adapters)} data sources available, which provides good redundancy.")
        
        # Recommendations for specific data sources
        tushare_available = any(a.name == "tushare" for a in available_adapters)
        if not tushare_available:
            recommendations["suggestions"].append("Consider configuring Tushare for the most comprehensive financial data.")
        
        return SyncResponse(
            success=True,
            message="Recommendations generated successfully",
            data=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


@router.get("/history")
async def get_sync_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="page size"),
    status: Optional[str] = Query(None, description="status filter")
):
    """Get sync history"""
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        # Build query conditions
        query = {"job": "stock_basics_multi_source"}
        if status:
            query["status"] = status

        # Count the number of skipped records
        skip = (page - 1) * page_size

        # Query history
        cursor = db.sync_status.find(query).sort("started_at", -1).skip(skip).limit(page_size)
        history_records = await cursor.to_list(length=page_size)

        # Get total
        total = await db.sync_status.count_documents(query)

        # Clean _id field in record
        for record in history_records:
            record.pop("_id", None)

        return SyncResponse(
            success=True,
            message="History retrieved successfully",
            data={
                "records": history_records,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": skip + len(history_records) < total
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync history: {str(e)}")


@router.delete("/cache")
async def clear_sync_cache():
    """Clear synchronization related cache"""
    try:
        service = get_multi_source_sync_service()

        # Clear sync status cache
        cleared_items = 0

        # 1. Clear sync status
        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()

            # Delete sync status record
            result = await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
            cleared_items += result.deleted_count

            # Reset service status
            service._running = False

        except Exception as e:
            logger.warning(f"Failed to clear sync status cache: {e}")

        # 2. Clear the data source cache (if any)
        try:
            manager = DataSourceManager()
            # Here you can add data source specific cache cleaning logic
            # Currently the data source adapter does not have a persistent cache, so skip
        except Exception as e:
            logger.warning(f"Failed to clear data source cache: {e}")

        return SyncResponse(
            success=True,
            message=f"Cache cleared successfully, {cleared_items} items removed",
            data={"cleared": True, "items_cleared": cleared_items}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
_snapshots['multi_source_sync'] = dict(globals())

# === multi_period_sync.py ===
#!/usr/bin/env python3
"""
Multi-cycle data synchronization API
Provides synchronization management interface for daily, weekly and monthly data
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.worker.multi_period_sync_service import get_multi_period_sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multi-period-sync", tags=["Multi-cycle synchronization"])


class MultiPeriodSyncRequest(BaseModel):
    """Multi-cycle synchronization request"""
    symbols: Optional[List[str]] = Field(None, description="List of stock codes, None means all stocks")
    periods: Optional[List[str]] = Field(["daily"], description="period list (daily/weekly/monthly)")
    data_sources: Optional[List[str]] = Field(["tushare", "akshare", "baostock"], description="Data source list")
    start_date: Optional[str] = Field(None, description="start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="end date (YYYY-MM-DD)")
    all_history: Optional[bool] = Field(False, description="Whether to synchronize all historical data (ignore time range)")


class MultiPeriodSyncResponse(BaseModel):
    """Multi-cycle synchronous response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post("/start", response_model=MultiPeriodSyncResponse)
async def start_multi_period_sync(
    request: MultiPeriodSyncRequest,
    background_tasks: BackgroundTasks
):
    """
    Start multi-cycle data synchronization
    """
    try:
        service = await get_multi_period_sync_service()
        
        # Background task execution synchronization
        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=request.symbols,
            periods=request.periods,
            data_sources=request.data_sources,
            start_date=request.start_date,
            end_date=request.end_date,
            all_history=request.all_history
        )
        
        return MultiPeriodSyncResponse(
            success=True,
            message="Multi-cycle data synchronization has started",
            data={
                "request_params": request.dict(),
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start multi-cycle synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {e}")


@router.post("/start-daily", response_model=MultiPeriodSyncResponse)
async def start_daily_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start daily data synchronization"""
    try:
        service = await get_multi_period_sync_service()
        
        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=["daily"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"]
        )
        
        return MultiPeriodSyncResponse(
            success=True,
            message="Daily data synchronization has started",
            data={
                "period": "daily",
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start daily synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start daily synchronization: {e}")


@router.post("/start-weekly", response_model=MultiPeriodSyncResponse)
async def start_weekly_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start weekly data synchronization"""
    try:
        service = await get_multi_period_sync_service()
        
        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=["weekly"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"]
        )
        
        return MultiPeriodSyncResponse(
            success=True,
            message="Weekly data synchronization has started",
            data={
                "period": "weekly",
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start weekly synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start weekly synchronization: {e}")


@router.post("/start-monthly", response_model=MultiPeriodSyncResponse)
async def start_monthly_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start monthly data synchronization"""
    try:
        service = await get_multi_period_sync_service()

        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=["monthly"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"]
        )

        return MultiPeriodSyncResponse(
            success=True,
            message="Monthly data synchronization has started",
            data={
                "period": "monthly",
                "start_time": datetime.utcnow().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"Failed to start monthly synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start monthly synchronization: {e}")


@router.post("/start-all-history", response_model=MultiPeriodSyncResponse)
async def start_all_history_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    periods: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None
):
    """Start full historical data synchronization (starting in 1990)"""
    try:
        service = await get_multi_period_sync_service()

        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=periods or ["daily", "weekly", "monthly"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"],
            all_history=True
        )

        return MultiPeriodSyncResponse(
            success=True,
            message="Full historical data synchronization started (from 1990)",
            data={
                "sync_type": "all_history",
                "periods": periods or ["daily", "weekly", "monthly"],
                "data_sources": data_sources or ["tushare", "akshare", "baostock"],
                "date_range": "1990-01-01 to today",
                "start_time": datetime.utcnow().isoformat(),
                "warning": "Full historical data synchronization may take a long time, please be patient."
            }
        )

    except Exception as e:
        logger.error(f"Failed to start full history synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start full history synchronization: {e}")


@router.post("/start-incremental", response_model=MultiPeriodSyncResponse)
async def start_incremental_sync(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = None,
    periods: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None,
    days_back: Optional[int] = 30
):
    """Start incremental data synchronization (last N days)"""
    try:
        from datetime import datetime, timedelta

        service = await get_multi_period_sync_service()

        # Calculate date range for incremental synchronization
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        background_tasks.add_task(
            service.sync_multi_period_data,
            symbols=symbols,
            periods=periods or ["daily"],
            data_sources=data_sources or ["tushare", "akshare", "baostock"],
            start_date=start_date,
            end_date=end_date
        )

        return MultiPeriodSyncResponse(
            success=True,
            message=f"Incremental data synchronization started (recently{days_back}days)",
            data={
                "sync_type": "incremental",
                "periods": periods or ["daily"],
                "data_sources": data_sources or ["tushare", "akshare", "baostock"],
                "date_range": f"{start_date} Arrive {end_date}",
                "days_back": days_back,
                "start_time": datetime.utcnow().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"Failed to start incremental sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start incremental sync: {e}")


@router.get("/statistics")
async def get_sync_statistics():
    """Get multi-cycle synchronization statistics"""
    try:
        service = await get_multi_period_sync_service()
        stats = await service.get_sync_statistics()
        
        return {
            "success": True,
            "data": stats,
            "message": "Statistics obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to obtain synchronization statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain statistics: {e}")


@router.get("/period-comparison/{symbol}")
async def compare_period_data(
    symbol: str,
    trade_date: str,
    data_source: str = "tushare"
):
    """
    Compare data from different periods for the same stock
    """
    try:
        from app.services.historical_data_service import get_historical_data_service
        service = await get_historical_data_service()
        
        periods = ["daily", "weekly", "monthly"]
        comparison = {}
        
        for period in periods:
            results = await service.get_historical_data(
                symbol=symbol,
                start_date=trade_date,
                end_date=trade_date,
                data_source=data_source,
                period=period,
                limit=1
            )
            
            if results:
                comparison[period] = results[0]
            else:
                comparison[period] = None
        
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "trade_date": trade_date,
                "data_source": data_source,
                "comparison": comparison,
                "available_periods": [k for k, v in comparison.items() if v is not None]
            },
            "message": "Cycle data comparison completed"
        }
        
    except Exception as e:
        logger.error(f"Period data comparison failed {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Period data comparison failed: {e}")


@router.get("/supported-periods")
async def get_supported_periods():
    """Get supported data periods"""
    return {
        "success": True,
        "data": {
            "periods": [
                {
                    "code": "daily",
                    "name": "daily line",
                    "description": "Daily transaction data",
                    "supported_sources": ["tushare", "akshare", "baostock"]
                },
                {
                    "code": "weekly",
                    "name": "perimeter",
                    "description": "Weekly transaction data",
                    "supported_sources": ["tushare", "akshare", "baostock"]
                },
                {
                    "code": "monthly",
                    "name": "monthly line",
                    "description": "monthly transaction data",
                    "supported_sources": ["tushare", "akshare", "baostock"]
                }
            ],
            "data_sources": [
                {
                    "code": "tushare",
                    "name": "Tushare",
                    "description": "Professional financial data services",
                    "supported_periods": ["daily", "weekly", "monthly"]
                },
                {
                    "code": "akshare",
                    "name": "AKShare",
                    "description": "Free open source financial data",
                    "supported_periods": ["daily", "weekly", "monthly"]
                },
                {
                    "code": "baostock",
                    "name": "BaoStock",
                    "description": "Free securities data platform",
                    "supported_periods": ["daily", "weekly", "monthly"]
                }
            ]
        },
        "message": "Supported cycle information is obtained successfully"
    }


@router.get("/health")
async def health_check():
    """health check"""
    try:
        service = await get_multi_period_sync_service()
        stats = await service.get_sync_statistics()
        
        return {
            "success": True,
            "data": {
                "service": "Multi-cycle synchronization service",
                "status": "healthy",
                "statistics": stats,
                "last_check": datetime.utcnow().isoformat()
            },
            "message": "Service is normal"
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "data": {
                "service": "Multi-cycle synchronization service",
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            },
            "message": "Service exception"
        }
_snapshots['multi_period_sync'] = dict(globals())

# === tushare_init.py ===
"""
Tushare Data initialization API routing
Provides data initialization function for Web interface
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.worker.tushare_init_service import get_tushare_init_service
from app.core.response import ok

router = APIRouter(prefix="/api/tushare-init", tags=["Tushare initialization"])


class InitializationRequest(BaseModel):
    """Initialize request model"""
    historical_days: int = Field(default=365, ge=1, le=3650, description="Historical data days")
    skip_if_exists: bool = Field(default=True, description="Whether to skip if the data already exists")
    force_update: bool = Field(default=False, description="Force update of existing data")


class DatabaseStatusResponse(BaseModel):
    """Database status response model"""
    basic_info_count: int = Field(description="Amount of basic information")
    quotes_count: int = Field(description="Quantity of market data")
    extended_coverage: float = Field(description="Extended field coverage")
    latest_basic_update: Optional[datetime] = Field(description="Basic information latest update time")
    latest_quotes_update: Optional[datetime] = Field(description="Latest update time of market data")
    needs_initialization: bool = Field(description="Whether initialization is required")


class InitializationStatusResponse(BaseModel):
    """Initialize state response model"""
    is_running: bool = Field(description="Is it running")
    current_step: Optional[str] = Field(description="current step")
    progress: Optional[str] = Field(description="Progress")
    started_at: Optional[datetime] = Field(description="start time")
    estimated_completion: Optional[datetime] = Field(description="Estimated completion time")


# Global initialization status tracking
_initialization_status = {
    "is_running": False,
    "current_step": None,
    "progress": None,
    "started_at": None,
    "task": None
}


@router.get("/status", response_model=dict)
async def get_database_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get database status
    Check the data situation in the current database to determine whether initialization is needed
    """
    try:
        db = get_mongo_db()
        
        # Check the status of each collection
        basic_count = await db.stock_basic_info.count_documents({})
        quotes_count = await db.market_quotes.count_documents({})
        
        # Check extension field coverage
        extended_count = 0
        extended_coverage = 0.0
        if basic_count > 0:
            extended_count = await db.stock_basic_info.count_documents({
                "full_symbol": {"$exists": True},
                "market_info": {"$exists": True}
            })
            extended_coverage = extended_count / basic_count
        
        # Check the latest update time
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        # Determine whether initialization is required
        needs_initialization = (
            basic_count == 0 or 
            extended_coverage < 0.5
        )
        
        status = DatabaseStatusResponse(
            basic_info_count=basic_count,
            quotes_count=quotes_count,
            extended_coverage=extended_coverage,
            latest_basic_update=latest_basic.get("updated_at") if latest_basic else None,
            latest_quotes_update=latest_quotes.get("updated_at") if latest_quotes else None,
            needs_initialization=needs_initialization
        )
        
        return ok(data=status,
            message="Database status obtained successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get database status: {str(e)}")


@router.get("/initialization-status", response_model=dict)
async def get_initialization_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get initialization status
    Check if there are any initialization tasks currently running
    """
    try:
        # Estimate completion time based on progress
        estimated_completion = None
        if (_initialization_status["is_running"]
            and _initialization_status["started_at"]
            and _initialization_status["progress"]):
            try:
                parts = _initialization_status["progress"].split("/")
                completed = int(parts[0])
                total = int(parts[1])
                if completed > 0 and total > 0:
                    elapsed = (datetime.utcnow() - _initialization_status["started_at"]).total_seconds()
                    estimated_total = elapsed / (completed / total)
                    remaining = estimated_total - elapsed
                    estimated_completion = (datetime.utcnow() + timedelta(seconds=remaining)).isoformat()
            except (ValueError, IndexError, ZeroDivisionError):
                pass

        status = InitializationStatusResponse(
            is_running=_initialization_status["is_running"],
            current_step=_initialization_status["current_step"],
            progress=_initialization_status["progress"],
            started_at=_initialization_status["started_at"],
            estimated_completion=estimated_completion
        )
        
        return ok(data=status,
            message="Initialization status obtained successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain initialization status: {str(e)}")


@router.post("/start-basic", response_model=dict)
async def start_basic_initialization(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start basic information initialization
    Only basic stock information is synchronized, suitable for quick initialization
    """
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="The initialization task is already running")
    
    try:
        # Start background task
        background_tasks.add_task(_run_basic_initialization)
        
        return ok(data={"message": "Basic information initialization has started"},
            message="The basic information initialization task has been started in the background"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize basic startup information: {str(e)}")


@router.post("/start-full", response_model=dict)
async def start_full_initialization(
    request: InitializationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start full data initialization
    Including complete synchronization of basic information, historical data, financial data, and market data
    """
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="The initialization task is already running")
    
    try:
        # Start background task
        background_tasks.add_task(
            _run_full_initialization,
            request.historical_days,
            not request.skip_if_exists or request.force_update
        )
        
        return ok(data={
                "message": "Full data initialization started",
                "historical_days": request.historical_days,
                "force_update": not request.skip_if_exists or request.force_update
            },
            message="The complete data initialization task has been started in the background"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Start full data initialization failed: {str(e)}")


@router.post("/stop", response_model=dict)
async def stop_initialization(
    current_user: dict = Depends(get_current_user)
):
    """
    Stop initialization task
    Try to cancel a running initialization task
    """
    if not _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="There are no initialization tasks running")
    
    try:
        # Try to cancel the task
        if _initialization_status["task"]:
            _initialization_status["task"].cancel()
        
        # reset state
        _initialization_status.update({
            "is_running": False,
            "current_step": None,
            "progress": None,
            "started_at": None,
            "task": None
        })
        
        return ok(data={"message": "The initialization task has stopped"},
            message="Initialization task stopped successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stop initialization task failed: {str(e)}")


async def _run_basic_initialization():
    """Run basic information initialization (background task)"""
    _initialization_status.update({
        "is_running": True,
        "current_step": "Basic information initialization",
        "progress": "0/1",
        "started_at": datetime.utcnow()
    })
    
    try:
        service = await get_tushare_init_service()
        result = await service.sync_service.sync_stock_basic_info(force_update=True)
        
        _initialization_status.update({
            "is_running": False,
            "current_step": "Complete",
            "progress": "1/1"
        })
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "current_step": f"failed: {str(e)}",
            "progress": "Error"
        })


async def _run_full_initialization(historical_days: int, force_update: bool):
    """Run full data initialization (background task)"""
    _initialization_status.update({
        "is_running": True,
        "current_step": "ready to initialize",
        "progress": "0/6",
        "started_at": datetime.utcnow()
    })
    
    try:
        service = await get_tushare_init_service()
        
        # Create a task to track progress
        async def progress_tracker():
            while _initialization_status["is_running"]:
                if hasattr(service, 'stats') and service.stats:
                    _initialization_status.update({
                        "current_step": service.stats.current_step,
                        "progress": f"{service.stats.completed_steps}/{service.stats.total_steps}"
                    })
                await asyncio.sleep(1)
        
        # Start progress tracking
        tracker_task = asyncio.create_task(progress_tracker())
        _initialization_status["task"] = tracker_task
        
        # Run initialization
        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force_update
        )
        
        # Stop progress tracking
        tracker_task.cancel()
        
        _initialization_status.update({
            "is_running": False,
            "current_step": "Complete" if result["success"] else "partially completed",
            "progress": result["progress"],
            "task": None
        })
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "current_step": f"failed: {str(e)}",
            "progress": "Error",
            "task": None
        })
_snapshots['tushare_init'] = dict(globals())

# === akshare_init.py ===
"""
AKShare Data initialization API routing
Provides a web interface for AKShare data initialization and management
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db
from app.worker.akshare_init_service import get_akshare_init_service
from app.worker.akshare_sync_service import get_akshare_sync_service
from app.routers.auth_db import get_current_user
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/akshare-init", tags=["AKShare initialization"])

# Global task state storage
_initialization_status = {
    "is_running": False,
    "current_task": None,
    "start_time": None,
    "progress": None,
    "result": None
}


class InitializationRequest(BaseModel):
    """Initialize request model"""
    historical_days: int = Field(default=365, ge=1, le=3650, description="Historical data days")
    force: bool = Field(default=False, description="Whether to force reinitialization")
    skip_if_exists: bool = Field(default=True, description="Whether to skip if data exists")


class SyncRequest(BaseModel):
    """Synchronous request model"""
    force_update: bool = Field(default=False, description="Whether to force update")
    symbols: Optional[list] = Field(default=None, description="Specify stock code list")


@router.get("/status")
async def get_database_status():
    """
    Get database status
    
    Returns:
        Database status information
    """
    try:
        db = get_mongo_db()
        
        # Check basic information
        basic_count = await db.stock_basic_info.count_documents({})
        extended_count = await db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        # Get the latest update time
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        # Check market data
        quotes_count = await db.market_quotes.count_documents({})
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        # Data quality assessment
        data_quality = "excellent"
        if basic_count == 0:
            data_quality = "empty"
        elif extended_count / basic_count < 0.5:
            data_quality = "poor"
        elif extended_count / basic_count < 0.9:
            data_quality = "good"
        
        return {
            "success": True,
            "data": {
                "basic_info": {
                    "total_count": basic_count,
                    "extended_count": extended_count,
                    "coverage_rate": round(extended_count / basic_count * 100, 2) if basic_count > 0 else 0,
                    "latest_update": latest_basic.get("updated_at") if latest_basic else None
                },
                "market_quotes": {
                    "total_count": quotes_count,
                    "latest_update": latest_quotes.get("updated_at") if latest_quotes else None
                },
                "data_quality": data_quality,
                "check_time": now_tz()
            },
            "message": "Database status check completed"
        }
        
    except Exception as e:
        logger.error(f"Failed to get database status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get database status: {str(e)}")


@router.get("/connection-test")
async def test_akshare_connection():
    """
    Test AKShare connection status
    
    Returns:
        Connection test results
    """
    try:
        service = await get_akshare_sync_service()
        connected = await service.provider.test_connection()
        
        result = {
            "connected": connected,
            "test_time": now_tz()
        }
        
        if connected:
            # Test to get the stock list
            try:
                stock_list = await service.provider.get_stock_list()
                result["stock_count"] = len(stock_list) if stock_list else 0
                result["sample_stocks"] = stock_list[:5] if stock_list else []
            except Exception as e:
                result["stock_list_error"] = str(e)
        
        return {
            "success": True,
            "data": result,
            "message": "AKShare Connection test completed"
        }
        
    except Exception as e:
        logger.error(f"AKShare Connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.post("/start-full")
async def start_full_initialization(
    request: InitializationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start full data initialization
    
    Args:
        request: Initialize request parameters
        background_tasks: Background task manager
        current_user: Current user information
        
    Returns:
        Initialization startup results
    """
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="Initialization task is running")
    
    try:
        # Set task status
        _initialization_status.update({
            "is_running": True,
            "current_task": "full_initialization",
            "start_time": now_tz(),
            "progress": {"current_step": "In preparation", "completed_steps": 0, "total_steps": 6},
            "result": None
        })
        
        # Start background task
        background_tasks.add_task(
            _run_full_initialization_background,
            request.historical_days,
            not request.skip_if_exists
        )
        
        return {
            "success": True,
            "data": {
                "task_id": "full_initialization",
                "start_time": _initialization_status["start_time"],
                "parameters": {
                    "historical_days": request.historical_days,
                    "force": not request.skip_if_exists
                }
            },
            "message": "The full initialization task has been started, please use /initialization-status to view the progress"
        }
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Start full initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup initialization failed: {str(e)}")


@router.post("/start-basic-sync")
async def start_basic_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start basic information synchronization
    
    Args:
        request: Synchronous request parameters
        background_tasks: Background task manager
        current_user: Current user information
        
    Returns:
        Synchronous startup results
    """
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="Sync task is running")
    
    try:
        # Set task status
        _initialization_status.update({
            "is_running": True,
            "current_task": "basic_sync",
            "start_time": now_tz(),
            "progress": {"current_step": "Synchronize basic information", "completed_steps": 0, "total_steps": 1},
            "result": None
        })
        
        # Start background task
        background_tasks.add_task(
            _run_basic_sync_background,
            request.force_update
        )
        
        return {
            "success": True,
            "data": {
                "task_id": "basic_sync",
                "start_time": _initialization_status["start_time"],
                "parameters": {
                    "force_update": request.force_update
                }
            },
            "message": "Basic information synchronization task has been started"
        }
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Failed to start basic information synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {str(e)}")


@router.get("/initialization-status")
async def get_initialization_status():
    """
    Get initialization task status
    
    Returns:
        Current task status
    """
    global _initialization_status
    
    return {
        "success": True,
        "data": {
            "is_running": _initialization_status["is_running"],
            "current_task": _initialization_status["current_task"],
            "start_time": _initialization_status["start_time"],
            "progress": _initialization_status["progress"],
            "result": _initialization_status["result"],
            "duration": (
                (now_tz() - _initialization_status["start_time"]).total_seconds()
                if _initialization_status["start_time"] else 0
            )
        },
        "message": "Task status obtained successfully"
    }


@router.post("/stop")
async def stop_initialization(current_user: dict = Depends(get_current_user)):
    """
    Stop the current initialization task
    
    Args:
        current_user: Current user information
        
    Returns:
        Stop results
    """
    global _initialization_status
    
    if not _initialization_status["is_running"]:
        raise HTTPException(status_code=400, detail="No tasks running")
    
    try:
        # Reset task status
        _initialization_status.update({
            "is_running": False,
            "current_task": None,
            "start_time": None,
            "progress": None,
            "result": {"stopped": True, "stop_time": datetime.utcnow()}
        })
        
        return {
            "success": True,
            "data": {
                "stopped": True,
                "stop_time": datetime.utcnow()
            },
            "message": "The initialization task has stopped"
        }
        
    except Exception as e:
        logger.error(f"Stop initialization task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stop task failed: {str(e)}")


async def _run_full_initialization_background(historical_days: int, force: bool):
    """Run full initialization in the background"""
    global _initialization_status
    
    try:
        service = await get_akshare_init_service()
        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force
        )
        
        _initialization_status.update({
            "is_running": False,
            "result": result
        })
        
        logger.info(f"Complete initialization background task completed: {result}")
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "result": {"success": False, "error": str(e)}
        })
        logger.error(f"Complete initialization of background task failed: {e}")


async def _run_basic_sync_background(force_update: bool):
    """Basic information synchronization running in the background"""
    global _initialization_status
    
    try:
        service = await get_akshare_sync_service()
        result = await service.sync_stock_basic_info(
            force_update=force_update,
            manual_mode=True  # Manual initialization should not inherit scheduled task cancellation status
        )
        
        _initialization_status.update({
            "is_running": False,
            "result": result
        })
        
        logger.info(f"Basic information synchronization background task completed: {result}")
        
    except Exception as e:
        _initialization_status.update({
            "is_running": False,
            "result": {"success": False, "error": str(e)}
        })
        logger.error(f"Basic information synchronization background task failed: {e}")
_snapshots['akshare_init'] = dict(globals())

# === baostock_init.py ===
#!/usr/bin/env python3
"""
BaoStock Initialize API routing
Provides RESTful API interface for BaoStock data initialization
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.worker.baostock_init_service import BaoStockInitService
from app.worker.baostock_sync_service import BaoStockSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/baostock-init", tags=["BaoStock initialization"])

# Global state management
_initialization_status = {
    "is_running": False,
    "current_task": None,
    "stats": None,
    "start_time": None,
    "last_update": None
}


class InitializationRequest(BaseModel):
    """Initialize request model"""
    historical_days: int = Field(default=365, ge=1, le=3650, description="Historical data days")
    force: bool = Field(default=False, description="Whether to force reinitialization")


class InitializationResponse(BaseModel):
    """Initialize response model"""
    success: bool
    message: str
    task_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.get("/status", response_model=Dict[str, Any])
async def get_database_status():
    """Get database status"""
    try:
        service = BaoStockInitService()
        status = await service.check_database_status()
        
        return {
            "success": True,
            "data": status,
            "message": "Database status obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to get database status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get database status: {e}")


@router.get("/connection-test", response_model=Dict[str, Any])
async def test_baostock_connection():
    """Test BaoStock connection"""
    try:
        service = BaoStockSyncService()
        connected = await service.provider.test_connection()
        
        return {
            "success": connected,
            "data": {
                "connected": connected,
                "test_time": datetime.now().isoformat()
            },
            "message": "BaoStock The connection is normal" if connected else "BaoStock Connection failed"
        }
        
    except Exception as e:
        logger.error(f"BaoStock Connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connection test failed: {e}")


@router.post("/start-full", response_model=InitializationResponse)
async def start_full_initialization(
    request: InitializationRequest,
    background_tasks: BackgroundTasks
):
    """Start full initialization"""
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(
            status_code=409, 
            detail="The initialization task is running, please wait for completion and try again."
        )
    
    try:
        # Generate tasks ID
        task_id = f"baostock_full_init_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # update status
        _initialization_status.update({
            "is_running": True,
            "current_task": "full_initialization",
            "stats": None,
            "start_time": datetime.now(),
            "last_update": datetime.now()
        })
        
        # Start background task
        background_tasks.add_task(
            _run_full_initialization_task,
            request.historical_days,
            request.force,
            task_id
        )
        
        return InitializationResponse(
            success=True,
            message="Full initialization task started",
            task_id=task_id,
            data={
                "historical_days": request.historical_days,
                "force": request.force,
                "estimated_duration": "30-60 minutes"
            }
        )
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Start full initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup initialization failed: {e}")


@router.post("/start-basic", response_model=InitializationResponse)
async def start_basic_initialization(background_tasks: BackgroundTasks):
    """Start basic initialization"""
    global _initialization_status
    
    if _initialization_status["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="The initialization task is running, please wait for completion and try again."
        )
    
    try:
        # Generate tasks ID
        task_id = f"baostock_basic_init_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # update status
        _initialization_status.update({
            "is_running": True,
            "current_task": "basic_initialization",
            "stats": None,
            "start_time": datetime.now(),
            "last_update": datetime.now()
        })
        
        # Start background task
        background_tasks.add_task(_run_basic_initialization_task, task_id)
        
        return InitializationResponse(
            success=True,
            message="Basic initialization tasks have been started",
            task_id=task_id,
            data={
                "estimated_duration": "10-20 minutes"
            }
        )
        
    except Exception as e:
        _initialization_status["is_running"] = False
        logger.error(f"Startup basic initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup initialization failed: {e}")


@router.get("/initialization-status", response_model=Dict[str, Any])
async def get_initialization_status():
    """Get initialization status"""
    global _initialization_status
    
    try:
        status = _initialization_status.copy()
        
        # Calculate running time
        if status["start_time"]:
            if status["is_running"]:
                duration = (datetime.now() - status["start_time"]).total_seconds()
            else:
                duration = (status["last_update"] - status["start_time"]).total_seconds() if status["last_update"] else 0
            status["duration"] = duration
        
        # Format statistics
        if status["stats"]:
            stats = status["stats"]
            status["progress"] = {
                "completed_steps": stats.completed_steps,
                "total_steps": stats.total_steps,
                "current_step": stats.current_step,
                "progress_percent": (stats.completed_steps / stats.total_steps) * 100
            }
            status["data_summary"] = {
                "basic_info_count": stats.basic_info_count,
                "quotes_count": stats.quotes_count,
                "historical_records": stats.historical_records,
                "financial_records": stats.financial_records,
                "error_count": len(stats.errors)
            }
        
        return {
            "success": True,
            "data": status,
            "message": "Status obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to obtain initialization status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@router.post("/stop", response_model=Dict[str, Any])
async def stop_initialization():
    """Stop initialization task"""
    global _initialization_status
    
    if not _initialization_status["is_running"]:
        return {
            "success": True,
            "message": "There are no initialization tasks running",
            "data": {"was_running": False}
        }
    
    try:
        # update status
        _initialization_status.update({
            "is_running": False,
            "current_task": None,
            "last_update": datetime.now()
        })
        
        return {
            "success": True,
            "message": "The initialization task has stopped",
            "data": {"was_running": True}
        }
        
    except Exception as e:
        logger.error(f"Stop initialization task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stop task failed: {e}")


async def _run_full_initialization_task(historical_days: int, force: bool, task_id: str):
    """Run full initialization task"""
    global _initialization_status
    
    try:
        logger.info(f"🚀 Start BaoStock complete initialization task: {task_id}")
        
        service = BaoStockInitService()
        stats = await service.full_initialization(
            historical_days=historical_days,
            force=force
        )
        
        # update status
        _initialization_status.update({
            "is_running": False,
            "stats": stats,
            "last_update": datetime.now()
        })
        
        if stats.completed_steps == stats.total_steps:
            logger.info(f"✅ BaoStock Complete initialization task completed: {task_id}")
        else:
            logger.warning(f"⚠️ BaoStock Complete initialization task partially completed: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ BaoStock Complete initialization task failed: {task_id}, Error: {e}")
        _initialization_status.update({
            "is_running": False,
            "last_update": datetime.now()
        })


async def _run_basic_initialization_task(task_id: str):
    """Run basic initialization tasks"""
    global _initialization_status
    
    try:
        logger.info(f"🚀 Start BaoStock basic initialization task: {task_id}")
        
        service = BaoStockInitService()
        stats = await service.basic_initialization()
        
        # update status
        _initialization_status.update({
            "is_running": False,
            "stats": stats,
            "last_update": datetime.now()
        })
        
        if stats.completed_steps == stats.total_steps:
            logger.info(f"✅ BaoStock Basic initialization tasks completed: {task_id}")
        else:
            logger.warning(f"⚠️ BaoStock Basic initialization tasks partially completed: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ BaoStock Basic initialization task failed: {task_id}, Error: {e}")
        _initialization_status.update({
            "is_running": False,
            "last_update": datetime.now()
        })


@router.get("/service-status", response_model=Dict[str, Any])
async def get_service_status():
    """Get BaoStock service status"""
    try:
        service = BaoStockSyncService()
        status = await service.check_service_status()
        
        return {
            "success": True,
            "data": status,
            "message": "Service status obtained successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to get service status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get service status: {e}")
_snapshots['baostock_init'] = dict(globals())

for _stem, _snap in _snapshots.items():
    _vmod = _types.ModuleType(f"app.routers.{_stem}")
    _vmod.__dict__.update(_snap)
    _sys.modules[f"app.routers.{_stem}"] = _vmod
    setattr(_routers_pkg, _stem, _vmod)
    setattr(_self_mod, _stem, _vmod)