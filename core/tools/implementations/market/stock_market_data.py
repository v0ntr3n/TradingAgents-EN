"""
Unified stock market data tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources
"""

import asyncio
import concurrent.futures
import json
import logging
import re
from datetime import datetime
from typing import Annotated, Optional, Tuple
from zoneinfo import ZoneInfo
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)
_CHINA_TZ = ZoneInfo("Asia/Shanghai")


def _get_china_now() -> datetime:
    return datetime.now(_CHINA_TZ)


def _normalize_trade_date(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"

    return text


def _resolve_china_actual_data_date(
    ticker: str,
    requested_end_date: str,
    now: Optional[datetime] = None,
    db_latest_trade_date: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    requested_date = _normalize_trade_date(requested_end_date) or requested_end_date
    latest_trade_date = _normalize_trade_date(db_latest_trade_date or _get_db_latest_trade_date_sync(ticker))

    if not latest_trade_date:
        return requested_date, None, None

    if latest_trade_date >= requested_date:
        return requested_date, requested_date, None

    current_time = now or _get_china_now()
    current_date = current_time.strftime("%Y-%m-%d")
    trading_status = None

    try:
        from app.utils.trading_time import get_trading_status

        trading_status = get_trading_status(current_time)
    except Exception as exc:
        logger.debug(f"[market tools] Failed to read session status (non-fatal): {exc}")

    if requested_date == current_date:
        status_messages = {
            "pre_market": "It is currently in the pre-market period and the daily data for the day has not yet been formed.",
            "morning_session": "It is currently in the trading session, and the daily closing price of the day has not yet been finalized.",
            "noon_break": "The market is currently closed at noon, and the daily closing price has not yet been finalized.",
            "afternoon_session": "It is currently in the trading session, and the daily closing price of the day has not yet been finalized.",
            "after_market": "Currently in the after-hours buffer period, the daily data may not have been completed yet.",
        }
        reason = status_messages.get(trading_status, "There is no complete daily data for the current requested date.")
        note = (
            f"请求分析日期为 {requested_date}，但{reason}；"
            f"The following prices and technical indicators are based on the most recent completed trading days {latest_trade_date} shall prevail."
        )
    else:
        note = (
            f"请求分析日期为 {requested_date}，但工具可用的最近完整日线数据截至 {latest_trade_date}；"
            f"The following prices and technical indicators are based on {latest_trade_date} shall prevail."
        )

    return latest_trade_date, latest_trade_date, note


def _get_last_trade_date_sync() -> Optional[str]:
    """Synchronously read the latest trading day (from TradingCalendarService) from Redis.

    Returns:
        String of the latest trading day in the format YYYY-MM-DD; if read fails, None is returned.
    """
    try:
        from app.core.database import get_redis_sync_client
        redis_client = get_redis_sync_client()
        raw = redis_client.get("trading_calendar:last_trade_date")
        if raw:
            data = json.loads(raw)
            return data.get("last_trade_date")
    except Exception as e:
        logger.debug(f"[JIT-Tool] Failed to read Redis transaction calendar (non-fatal): {e}")
    return None


def _get_db_latest_trade_date_sync(symbol: str, data_source: Optional[str] = None) -> Optional[str]:
    """Query the latest trade_date of a security from MongoDB.

    Args:
        symbol: Securities code (6 digits or suffix is acceptable)
        data_source: Specify the data source (such as "tushare") ; When None, query the latest date in all data sources.

    Returns:
        Latest date string in the format YYYY-MM-DD; if it does not exist, None is returned.
    """
    try:
        from app.core.database import get_mongo_db_sync
        from tradingagents.utils.stock_utils import StockUtils

        db = get_mongo_db_sync()
        code6 = str(symbol).zfill(6)
        is_fund = StockUtils.is_fund(code6)
        collection = db.etf_daily_quotes if is_fund else db.stock_daily_quotes
        symbol_field = "code" if is_fund else "symbol"
        query: dict = {symbol_field: code6}
        if data_source:
            query["data_source"] = data_source

        doc = collection.find_one(
            query,
            {"trade_date": 1, "_id": 0},
            sort=[("trade_date", -1)]
        )
        if doc:
            raw_date = doc.get("trade_date", "")
            # uniformly converted to YYYY-MM-DD
            s = str(raw_date).replace("-", "")
            if len(s) == 8:
                return f"{s[:4]}-{s[4:6]}-{s[6:]}"
            return str(raw_date)
    except Exception as e:
        logger.debug(f"[JIT-Tool] Failed to read MongoDB latest trading day (non-fatal): {e}")
    return None


def _trigger_jit_sync_in_thread(stock_code: str) -> None:
    """Run JIT asynchronous synchronization in a separate thread to avoid nested event loop issues.

    Because the agent tool runs in a thread that already has an event loop (ThreadWorker s async context),
    not directly asyncio.run(), An independent event loop needs to be created with the help of a new thread.

    An independent asynchronous MongoDB connection is initialized in the new thread to avoid sharing event loop-bound clients across threads.
    """
    async def _do_sync():
        # 🔥 Initialize a standalone asynchronous MongoDB connection in a new event loop
        from motor.motor_asyncio import AsyncIOMotorClient
        from app.core.config import settings

        mongo_client = None
        try:
            # Create a new asynchronous MongoDB client (bound to the current thread's event loop)
            mongo_client = AsyncIOMotorClient(
                settings.MONGO_URI,
                maxPoolSize=10,
                minPoolSize=2,
                serverSelectionTimeoutMS=5000
            )
            mongo_db = mongo_client[settings.MONGO_DB]  # Use MONGO_DB instead MONGO_DB_NAME

            # Temporarily injected into global variables for use by jit_sync_stock_data
            import app.core.database as db_module
            original_db = db_module.mongo_db
            db_module.mongo_db = mongo_db

            try:
                from app.worker.analysis_worker import jit_sync_stock_data
                result = await jit_sync_stock_data(
                    stock_code=stock_code,
                    parameters_dict={"market_type": "cn"}
                )
                return result
            finally:
                # Restore original global variables
                db_module.mongo_db = original_db
        finally:
            # Close the newly created MongoDB connection
            if mongo_client:
                mongo_client.close()

    def _run_in_new_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_do_sync())
        finally:
            loop.close()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_in_new_loop)
            result = future.result(timeout=120)  # Wait up to 2 minutes
            if result and hasattr(result, "is_valid"):
                if result.is_valid:
                    logger.info(f"✅ [JIT-Tool] {stock_code} 数据同步完成: {getattr(result, 'message', '')}")
                else:
                    logger.warning(f"⚠️ [JIT-Tool] {stock_code} Data synchronization failed (continue using existing data): {getattr(result, 'message', '')}")
    except concurrent.futures.TimeoutError:
        logger.warning(f"⚠️ [JIT-Tool] {stock_code} JIT Synchronization timeout (120s), continue to use existing data")
    except Exception as e:
        logger.warning(f"⚠️ [JIT-Tool] {stock_code} JIT Synchronization exception (continue using existing data): {e}")


def _ensure_fresh_china_data(ticker: str, data_source: Optional[str] = None) -> None:
    """Check the freshness of A-share data and trigger JIT synchronization if it is stale.

    freshness**Highest priority real API data source**Subject to:
    - If data_source is not specified, the first non-local data source in the database configuration is automatically taken.
    - If data_source is specified, the data source is directly used for checking.

    This function is completely synchronous, and internally handles asynchronous JIT synchronous calls through independent threads.
    Will not block the current event loop, and will not cause nested event loop conflicts.
    """
    # 1. Get the latest trading day from Redis (Trading Calendar Service Maintenance)
    last_trade_date = _get_last_trade_date_sync()
    if not last_trade_date:
        logger.debug("[JIT-Tool] The Redis transaction calendar was not obtained, so the freshness check was skipped and the existing data was used directly.")
        return

    # 2. Determine the data source to check: the caller-specified value is used first; otherwise, the real API source with the highest priority is used
    check_source = data_source
    if not check_source:
        try:
            from app.core.data_source_priority import get_enabled_data_sources_sync
            all_sources = get_enabled_data_sources_sync("a_shares")
            # Exclude cache layers such as local/mongodb and only take the real API data source
            api_sources = [s for s in all_sources if s not in ("local", "mongodb", "local_file")]
            check_source = api_sources[0] if api_sources else None
        except Exception as _e:
            logger.debug(f"[JIT-Tool] Failed to get data source priority (non-fatal): {_e}")

    # 3. Check the latest data date of MongoDB (filter by specified data source)
    db_latest = _get_db_latest_trade_date_sync(ticker, data_source=check_source)

    logger.info(
        f"🔍 [JIT-Tool] {ticker} 新鲜度检查 [数据源={check_source or '全部'}]: "
        f"DB latest day={db_latest or 'No data'}, Last trading day={last_trade_date}"
    )

    # 4. Determine whether synchronization is required
    if db_latest is None or db_latest < last_trade_date:
        logger.info(
            f"📡 [JIT-Tool] {ticker} 数据陈旧，触发 JIT 同步 "
            f"[{check_source or 'All'}] (DB={db_latest or 'N/A'} < Last trading day={last_trade_date})"
        )
        _trigger_jit_sync_in_thread(ticker)
    else:
        logger.info(
            f"✅ [JIT-Tool] {ticker} 数据已是最新 [{check_source or '全部'}]"
            f" ({db_latest} >= {last_trade_date}) , Skip sync"
        )


@tool
@register_tool(
    tool_id="get_stock_market_data_unified",
    name="统一股票市场数据",
    description="Obtain stock market data and technical indicators, support A-shares, Hong Kong stocks, and US stocks, and return data such as K-line data, trading volume, technical indicators, and basic market snapshots.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["stock_market_data", "market_data", "stock_price", "price_history", "market_quote", "technical_indicators"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["stock_market_data_retrieval", "price_history_analysis", "multi_market_data_query"],
)
def get_stock_market_data_unified(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    start_date: Annotated[str, "Start date, format: YYYY-MM-DD. Note: The system automatically expands to the configured number of lookback days (usually 365 days), you only need to pass the analysis date"],
    end_date: Annotated[str, "End date, format: YYYY-MM-DD. Usually the same as start_date, just pass the current analysis date"]
) -> str:
    """
    Unified stock market data tool
    Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources to obtain price and technical indicator data

    ⚠️ Important: The system automatically extends the date range to the configured number of lookback days (usually 365 days) to ensure there is sufficient historical data for technical indicator calculations.
    You only need to pass the current analysis date as start_date and end_date, no need to manually calculate the historical date range.

    Args:
        ticker: Stock code (such as: 000001, 0700.HK, AAPL)
        start_date: Start date (format: YYYY-MM-DD). Just pass the current analysis date and the system will automatically expand it.
        end_date: End date (format: YYYY-MM-DD). Just pass the current analysis date

    Returns:
        str: Market data and technical analysis reports

    Example:
        If the analysis date is 2025-11-09, pass:
        - ticker: "00700.HK"
        - start_date: "2025-11-09"
        - end_date: "2025-11-09"
        The system will automatically obtain 365 days of historical data from 2024-11-09 to 2025-11-09
    """
    # Standardized A-share code: remove the .SZ/.SH/.BJ suffix (the front and back ends use pure 6-digit numbers uniformly)
    original_ticker = ticker
    ticker = re.sub(r'\.(SZ|SH|BJ|sz|sh|bj)$', '', ticker.strip())
    if original_ticker != ticker:
        logger.info(f"📈 [unified market tools] Standardized stock code: {original_ticker} -> {ticker}")

    logger.info(f"📈 [unified market tools] Analyze stocks: {ticker}")

    try:
        from tradingagents.utils.stock_utils import StockUtils

        # Automatically identify stock types
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        logger.info(f"📈 [unified market tools] Stock type: {market_info['market_name']}")
        logger.info(f"📈 [unified market tools] Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")

        result_data = []

        if is_china:
            # China A Shares: Using China Stock Data Sources
            logger.info(f"🇨🇳 [unified market tools] Process A-share market data...")

            requested_start_date = _normalize_trade_date(start_date) or start_date
            requested_end_date = _normalize_trade_date(end_date) or end_date
            effective_start_date = start_date
            effective_end_date = end_date
            actual_data_date = None
            date_note = None

            # ===== JIT Freshness check: Ensure MongoDB data covers the most recent trading day =====
            # First check whether the DB data has overwritten the latest trading day cached by Redis;
            # If it is stale, asynchronously pull the latest market data in a separate thread and write it to MongoDB.
            # Then get_china_stock_data_unified can read the latest data.
            try:
                _ensure_fresh_china_data(ticker)
            except Exception as _jit_err:
                logger.warning(f"⚠️ [JIT-Tool] An exception occurred in the freshness check (does not affect analysis): {_jit_err}")
            # ============================================================

            try:
                effective_end_date, actual_data_date, date_note = _resolve_china_actual_data_date(
                    ticker,
                    requested_end_date,
                )
                if requested_start_date == requested_end_date:
                    effective_start_date = effective_end_date
                logger.info(
                    f"📅 [统一市场工具] A股日期语义: 请求日期={requested_end_date}, "
                    f"actual data date={actual_data_date or 'unknown'}, Inquiry deadline={effective_end_date}"
                )
            except Exception as date_err:
                logger.warning(f"⚠️ [unified market tools] Failed to parse the actual data date of A shares (continue to request according to the original date): {date_err}")

            try:
                from tradingagents.dataflows.interface import get_china_stock_data_unified
                stock_data = get_china_stock_data_unified(ticker, effective_start_date, effective_end_date)

                # 🔍 Debugging: Print the first 500 characters of the returned data
                logger.info(f"🔍 [Market tool debugging] A Stock data return length: {len(stock_data)}")
                logger.info(f"🔍 [Market tool debugging] A The first 500 characters of stock data:\n{stock_data[:500]}")

                date_context_lines = [f"**请求分析日期**: {requested_end_date}"]
                if actual_data_date:
                    date_context_lines.append(f"**实际数据日期**: {actual_data_date}")
                if date_note:
                    date_context_lines.append(f"**日期说明**: {date_note}")

                result_data.append(
                    "## A股市场数据\n"
                    + "\n".join(date_context_lines)
                    + f"\n\n{stock_data}"
                )
            except Exception as e:
                logger.error(f"❌ [Market tool debugging] A Failed to obtain stock data: {e}")
                result_data.append(f"## A stock market data\n Failed to obtain: {e}")

        elif is_hk:
            # Hong Kong stocks: using AKShare data source
            logger.info(f"🇭🇰 [unified market tools] Process Hong Kong stock market data...")

            try:
                from tradingagents.dataflows.interface import get_hk_stock_data_unified
                hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                # 🔍 Debugging: Print the first 500 characters of the returned data
                logger.info(f"🔍 [Market tool debugging] Hong Kong stock data return length: {len(hk_data)}")
                logger.info(f"🔍 [Market tool debugging] The first 500 characters of Hong Kong stock data:\n{hk_data[:500]}")

                result_data.append(f"## 港股市场数据\n{hk_data}")
            except Exception as e:
                logger.error(f"❌ [Market tool debugging] Failed to obtain Hong Kong stock data: {e}")
                result_data.append(f"## Hong Kong stock market data\n Failed to obtain: {e}")

        else:
            # US stocks: Prioritize the use of FINNHUB API data sources
            logger.info(f"🇺🇸 [unified market tools] Process U.S. stock market data...")

            try:
                from tradingagents.dataflows.providers.us.optimized import get_us_stock_data_cached
                us_data = get_us_stock_data_cached(ticker, start_date, end_date)
                result_data.append(f"## 美股市场数据\n{us_data}")
            except Exception as e:
                result_data.append(f"## US stock market data\n Failed to obtain: {e}")

        # Combine all data
        combined_result = f"""# {ticker} 市场数据分析

**股票类型**: {market_info['market_name']}
**货币**: {market_info['currency_name']} ({market_info['currency_symbol']})
    **请求分析期间**: {start_date} 至 {end_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

        logger.info(f"📈 [unified market tools] Data acquisition completed, total length: {len(combined_result)}")
        return combined_result

    except Exception as e:
        error_msg = f"Unified market data tool execution failed: {str(e)}"
        logger.error(f"❌ [统一市场工具] {error_msg}")
        return error_msg

