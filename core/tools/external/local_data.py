"""
local data access module — For the generated Skill to get data from the database

The generated Skill can be imported from this module to directly query the stock data synchronized by the system.
No need to call external API. Suitable for data combination, secondary processing and other scenarios.

Usage examples:
    from core.tools.external.local_data import (
        get_stock_basic_info,
        get_stock_daily_quotes,
        get_stock_news,
        get_market_quotes,
        get_etf_basic_info,
        get_etf_daily_quotes,
    )
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Collection name (A shares)
_COL_BASIC = "stock_basic_info"
_COL_DAILY = "stock_daily_quotes"
_COL_NEWS = "stock_news"
_COL_QUOTES = "market_quotes"
_COL_FINANCIAL = "stock_financial_data"

# Collection name (ETF)
_COL_ETF_BASIC = "etf_basic_info"
_COL_ETF_DAILY = "etf_daily_quotes"


def _get_db():
    """Get a synchronous MongoDB connection"""
    from app.core.database import get_mongo_db_sync
    return get_mongo_db_sync()


def _get_sources(market: str = "a_shares") -> List[str]:
    """获取数据源优先级列表"""
    try:
        from app.core.data_source_priority import get_enabled_data_sources_sync
        return get_enabled_data_sources_sync(market_category=market)
    except Exception:
        return ["local", "tushare", "akshare", "baostock"]


def get_stock_basic_info(symbol: str, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get basic stock information (from local database)

    Args:
        symbol: 6 digit stock code, such as 600519
        source: Specify the data source (optional). If not passed, the query will be based on system priority.

    Returns:
        Dictionary of basic stock information, including name, industry, total_mv, pe_ttm, etc.; no data returned None
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_BASIC]
    query = {"$or": [{"symbol": symbol}, {"code": symbol}]}
    if source:
        query["source"] = source
        doc = col.find_one(query, {"_id": 0})
    else:
        for src in _get_sources():
            q = {**query, "source": src}
            doc = col.find_one(q, {"_id": 0})
            if doc:
                break
        if not doc:
            doc = col.find_one(query, {"_id": 0})
    return doc


def get_stock_daily_quotes(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    source: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Get stock daily/K line data (from local database)

    Args:
        symbol: 6 stock code
        start_date: Start date in the format YYYYMMDD or YYYY-MM-DD
        end_date: End date, the format is the same as above
        period: Period, daily/weekly/monthly, default daily
        source: Specify data source (optional)
        limit: Maximum number of entries, default 1000

    Returns:
        Daily list, in ascending order by trade_date
    """
    symbol = str(symbol).strip().zfill(6)
    start = start_date.replace("-", "")[:8]
    end = end_date.replace("-", "")[:8]
    db = _get_db()
    col = db[_COL_DAILY]
    query = {
        "symbol": symbol,
        "trade_date": {"$gte": start, "$lte": end},
        "period": period,
    }
    if source:
        query["data_source"] = source
    else:
        for src in _get_sources():
            q = {**query, "data_source": src}
            cursor = col.find(q, {"_id": 0}).sort("trade_date", 1).limit(limit)
            items = list(cursor)
            if items:
                return items
        cursor = col.find(query, {"_id": 0}).sort("trade_date", 1).limit(limit)
        return list(cursor)
    cursor = col.find(query, {"_id": 0}).sort("trade_date", 1).limit(limit)
    return list(cursor)


def get_stock_news(
    symbol: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get stock news (from local database)

    Args:
        symbol: 6 stock code
        start_date: Start time (optional)
        end_date: End time (optional)
        limit: Maximum number of entries, default 20

    Returns:
        News list, including title, content, publish_time, url, etc.
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_NEWS]
    query: Dict[str, Any] = {"symbol": symbol}
    if start_date or end_date:
        q: Dict[str, datetime] = {}
        if start_date:
            q["$gte"] = start_date
        if end_date:
            q["$lte"] = end_date
        query["$or"] = [{"publish_time": q}, {"pub_date": q}]
    try:
        cursor = col.find(query, {"_id": 0}).sort("publish_time", -1).limit(limit)
        return list(cursor)
    except Exception:
        cursor = col.find(query, {"_id": 0}).sort("pub_date", -1).limit(limit)
        return list(cursor)


def get_stock_news_by_date_range(
    symbol: str,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get stock news by date range (from local database)

    Args:
        symbol: 6 stock code
        start_date: start date YYYY-MM-DD
        end_date: end date YYYY-MM-DD
        limit: Maximum number of items

    Returns:
        News list
    """
    symbol = str(symbol).strip().zfill(6)
    try:
        start_dt = datetime.strptime(start_date[:10], "%Y-%m-%d")
        end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d")
    except ValueError:
        return []
    return get_stock_news(symbol, start_date=start_dt, end_date=end_dt, limit=limit)


def get_market_quotes(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get real-time stock quotes (from local database)

    Args:
        symbol: 6 stock code

    Returns:
        Quote dictionary, including close, pct_chg, volume, amount, etc.; no data returned None
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_QUOTES]
    doc = col.find_one({"$or": [{"symbol": symbol}, {"code": symbol}]}, {"_id": 0})
    return doc


def get_latest_stock_price(symbol: str) -> Optional[float]:
    """
    Get the latest available price for a stock.

    Use market_quotes first, then fall back to close/current_price/pre_close in stock_basic_info.
    If there is no positive price, None is returned.
    """
    symbol = str(symbol).strip().zfill(6)

    quotes = get_market_quotes(symbol) or {}
    for field in ("current_price", "close", "pre_close", "open"):
        value = quotes.get(field)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    basic_info = get_stock_basic_info(symbol) or {}
    for field in ("current_price", "close", "pre_close", "open"):
        value = basic_info.get(field)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    return None


def get_stock_financial_data(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get stock financial data (from local database)

    Args:
        symbol: 6 stock code
        start_date: Start date YYYYMMDD (optional)
        end_date: End date YYYYMMDD (optional)
        limit: Maximum number of items

    Returns:
        Financial data list
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_FINANCIAL]
    query: Dict[str, Any] = {"$or": [{"symbol": symbol}, {"code": symbol}]}
    if start_date or end_date:
        q: Dict[str, str] = {}
        if start_date:
            q["$gte"] = start_date.replace("-", "")[:8]
        if end_date:
            q["$lte"] = end_date.replace("-", "")[:8]
        query["$and"] = [{"$or": [{"report_period": q}, {"report_date": q}]}]

    # Historically, financial data has existed in two calibers: report_period / report_date.
    # After unified pulling, the sorting is compatible on the Python side to prevent the generated Skill from getting wrong records due to field differences.
    items = list(col.find(query, {"_id": 0}).limit(max(limit * 3, 50)))
    items.sort(
        key=lambda item: str(item.get("report_period") or item.get("report_date") or ""),
        reverse=True,
    )
    return items[:limit]


def get_stock_valuation_context(symbol: str, financial_limit: int = 8) -> Dict[str, Any]:
    """
    Gets the standard input context of the valuation scenario.

    The return value contains:
    - basic_info: Basic information
    - market_quotes: Real-time quotes
    - current_price: Latest available prices
    - pe_ttm / pb / ps_ttm: Common valuation indicators
    - financial_data: Financial data for the most recent periods
    """
    symbol = str(symbol).strip().zfill(6)
    basic_info = get_stock_basic_info(symbol) or {}
    market_quotes = get_market_quotes(symbol) or {}
    financial_data = get_stock_financial_data(symbol, limit=financial_limit)
    current_price = get_latest_stock_price(symbol)

    return {
        "basic_info": basic_info,
        "market_quotes": market_quotes,
        "current_price": current_price,
        "pe_ttm": basic_info.get("pe_ttm") or basic_info.get("pe"),
        "pb": basic_info.get("pb") or basic_info.get("pb_mrq"),
        "ps_ttm": basic_info.get("ps_ttm") or basic_info.get("ps"),
        "financial_data": financial_data,
    }


# ─── ETF data access ──────────────────────────────────────────────


def get_etf_basic_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get underlying ETF information (from local database)

    Args:
        symbol: 6 Bit ETF code, such as 510050,159919

    Returns:
        ETF Basic information dictionary, including name, fund_type, track_index, fund_scale,
        management_fee, unit_nav, accum_nav Wait; no data returned None
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    doc = db[_COL_ETF_BASIC].find_one({"code": symbol}, {"_id": 0})
    return doc


def get_etf_daily_quotes(
    symbol: str,
    start_date: str,
    end_date: str,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Get ETF daily data (from local database)

    Args:
        symbol: 6 Bit ETF ticker
        start_date: Start date in the format YYYYMMDD or YYYY-MM-DD
        end_date: End date, the format is the same as above
        limit: Maximum number of entries, default 1000

    Returns:
        Daily list, in ascending order by trade_date; including close, pct_chg, volume, amount, unit_nav,accum_nav
    """
    symbol = str(symbol).strip().zfill(6)
    start = start_date.replace("-", "")[:8]
    end = end_date.replace("-", "")[:8]
    db = _get_db()
    col = db[_COL_ETF_DAILY]
    cursor = (
        col.find(
            {"code": symbol, "trade_date": {"$gte": start, "$lte": end}},
            {"_id": 0},
        )
        .sort("trade_date", 1)
        .limit(limit)
    )
    return list(cursor)


# ─── API Documentation (for reference by code generators)────────────────────────────────


# Documentation referenced by the code generator Prompt
LOCAL_DATA_API_DOC = """
 [local data access — Existing data can be obtained from the database]

The synchronized stock data of this system is stored in MongoDB, and the generated Skill can be queried directly without calling external API.
Prioritize obtaining local data before considering external data sources. When there is insufficient data, call akshare, tushare, etc.

Allow import:from core.tools.external.local_data import ...

Available functions (all are synchronous functions, just call them directly):

1. get_stock_basic_info(symbol: str, source=None) -> dict | None
   - Basic stock information: name, industry, total_mv, pe_ttm, pb, etc.
   - symbol: 6 bit code

2. get_stock_daily_quotes(symbol, start_date, end_date, period="daily", source=None, limit=1000) -> list
   - Daily/K line data: open, high, low, close, volume, etc.
   - Date format: YYYYMMDD or YYYY-MM-DD

3. get_stock_news(symbol, start_date=None, end_date=None, limit=20) -> list
   or get_stock_news_by_date_range(symbol, start_date, end_date, limit=20) -> list
   - Stock news: title, content, publish_time,url

4. get_market_quotes(symbol) -> dict | None
   - Real-time quotes: close, pct_chg, volume,amount

5. get_latest_stock_price(symbol) -> float | None
   - Standard price entry: give priority to market_quotes, then fall back basic_info
   - Valuation Skills should first use this function to get current_price. Do not set the price silently to 0

6. get_stock_financial_data(symbol, start_date=None, end_date=None, limit=20) -> list
   - Financial data: compatible with report_period / report_date two reporting period fields

7. get_stock_valuation_context(symbol, financial_limit=8) -> dict
   - Valuation scenario standard entry: return basic_info, market_quotes, current_price, pe_ttm, pb, ps_ttm,financial_data

8. get_etf_basic_info(symbol: str) -> dict | None
   - ETF Basic information: name, fund_type, track_index, fund_scale, management_fee, unit_nav, accumulate_nav, etc.
   - symbol: 6 Bit ETF code, such as 510050,159919

9. get_etf_daily_quotes(symbol, start_date, end_date, limit=1000) -> list
   - ETF Daily data: close, pct_chg, volume, amount, unit_nav,accum_nav
   - Date format: YYYYMMDD or YYYY-MM-DD

Example 1: Check local first, if there is no data, then transfer externally API
    from core.tools.external.local_data import get_stock_basic_info, get_stock_daily_quotes
    info = get_stock_basic_info("600519")
    if info:
        ...
    else:
        ...

Example 2: Recommended writing method for valuation skills
    from core.tools.external.local_data import get_stock_valuation_context
    ctx = get_stock_valuation_context("600519")
    current_price = ctx["current_price"]
    if current_price is None or current_price <= 0:
        return {"status": "error", "message": "No effective current price has been obtained and cannot be valued."}

    pe_ttm = ctx["pe_ttm"]
    pb = ctx["pb"]
    ps_ttm = ctx["ps_ttm"]
    financial_data = ctx["financial_data"]

Hard rules:
- Valuation skills do not allow silently setting current_price to 0 and then continuing the calculation.
- fair_value, valuation_range If necessary input is missing, invalid / error should be returned instead of output 0
- When sorting financial data, use report_period first, followed by compatibility. report_date
"""
