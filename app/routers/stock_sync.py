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
                logger.info(f"💡 Synchronize real-time quotes of individual stocks and automatically switch to AKShare data source (avoiding Tushare interface limitations)")
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
                        f" (QMT Requires trading terminal to run)" if success_count == 0 else ""
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

