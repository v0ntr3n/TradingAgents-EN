"""
Skill Runtime local data access module.

The generated Skill should only import the database access helper from this module,
Avoid triggering initialization side effects of Skill generation pipeline packages.
"""

import logging
import re
from statistics import median
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_COL_BASIC = "stock_basic_info"
_COL_DAILY = "stock_daily_quotes"
_COL_NEWS = "stock_news"
_COL_QUOTES = "market_quotes"
_COL_FINANCIAL = "stock_financial_data"
_COL_FINANCIAL_PERIODS = "stock_financial_periods"


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _normalize_date_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _determine_report_type(period: str) -> str:
    normalized = _normalize_date_digits(period)
    if normalized.endswith("1231"):
        return "annual"
    if normalized:
        return "quarterly"
    return "unknown"


def _normalize_statement_list(section_data: Any) -> List[Dict[str, Any]]:
    if isinstance(section_data, list):
        return [dict(item) for item in section_data if isinstance(item, dict)]
    if isinstance(section_data, dict):
        return [dict(section_data)]
    return []


def _statement_quality_score(record: Dict[str, Any]) -> int:
    return sum(1 for value in record.values() if value not in (None, "", [], {}))


def _prefer_statement(existing: Optional[Dict[str, Any]], candidate: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return dict(candidate)
    if _statement_quality_score(candidate) >= _statement_quality_score(existing):
        merged = dict(existing)
        merged.update(candidate)
        return merged
    merged = dict(candidate)
    merged.update(existing)
    return merged


def _extract_from_candidates(record: Dict[str, Any], *field_names: str) -> Optional[float]:
    for field_name in field_names:
        value = _safe_float(record.get(field_name))
        if value is not None:
            return value
    return None


def _flatten_financial_period_record(period_record: Dict[str, Any]) -> Dict[str, Any]:
    income = dict(period_record.get("income_statement") or {})
    balance = dict(period_record.get("balance_sheet") or {})
    cashflow = dict(period_record.get("cashflow_statement") or {})
    indicators = dict(period_record.get("financial_indicators") or {})

    period_record.update({
        "revenue": _extract_from_candidates(income, "revenue", "oper_rev"),
        "oper_rev": _extract_from_candidates(income, "oper_rev", "revenue"),
        "net_income": _extract_from_candidates(income, "n_income", "net_income"),
        "net_profit": _extract_from_candidates(income, "n_income_attr_p", "net_profit", "n_income"),
        "oper_profit": _extract_from_candidates(income, "operate_profit", "oper_profit"),
        "operating_profit": _extract_from_candidates(income, "operate_profit", "oper_profit"),
        "ebit": _extract_from_candidates(income, "ebit", "operate_profit", "oper_profit"),
        "total_profit": _extract_from_candidates(income, "total_profit"),
        "oper_cost": _extract_from_candidates(income, "oper_cost"),
        "oper_exp": _extract_from_candidates(income, "oper_exp", "sell_exp"),
        "admin_exp": _extract_from_candidates(income, "admin_exp"),
        "fin_exp": _extract_from_candidates(income, "fin_exp"),
        "rd_exp": _extract_from_candidates(income, "rd_exp", "r_and_d"),
        "total_assets": _extract_from_candidates(balance, "total_assets"),
        "total_liab": _extract_from_candidates(balance, "total_liab"),
        "total_equity": _extract_from_candidates(balance, "total_hldr_eqy_exc_min_int", "total_equity", "total_hldr_eqy_inc_min_int"),
        "total_cur_assets": _extract_from_candidates(balance, "total_cur_assets"),
        "total_nca": _extract_from_candidates(balance, "total_nca"),
        "total_cur_liab": _extract_from_candidates(balance, "total_cur_liab"),
        "total_ncl": _extract_from_candidates(balance, "total_ncl"),
        "money_cap": _extract_from_candidates(balance, "money_cap"),
        "accounts_receiv": _extract_from_candidates(balance, "accounts_receiv", "acct_receiv", "acc_receivable"),
        "inventories": _extract_from_candidates(balance, "inventories"),
        "fix_assets": _extract_from_candidates(balance, "fix_assets"),
        "n_cashflow_act": _extract_from_candidates(cashflow, "n_cashflow_act"),
        "n_cashflow_inv_act": _extract_from_candidates(cashflow, "n_cashflow_inv_act"),
        "n_cashflow_fin_act": _extract_from_candidates(cashflow, "n_cashflow_fin_act"),
        "c_cash_equ_end_period": _extract_from_candidates(cashflow, "c_cash_equ_end_period", "end_bal_cash"),
        "c_cash_equ_beg_period": _extract_from_candidates(cashflow, "c_cash_equ_beg_period", "beg_bal_cash"),
        "roe": _extract_from_candidates(indicators, "roe", "roe_avg", "roe_waa"),
        "roa": _extract_from_candidates(indicators, "roa", "roa2"),
        "gross_margin": _extract_from_candidates(indicators, "grossprofit_margin", "gross_margin"),
        "netprofit_margin": _extract_from_candidates(indicators, "netprofit_margin"),
        "debt_to_assets": _extract_from_candidates(indicators, "debt_to_assets"),
        "assets_to_eqt": _extract_from_candidates(indicators, "assets_to_eqt"),
        "current_ratio": _extract_from_candidates(indicators, "current_ratio"),
        "quick_ratio": _extract_from_candidates(indicators, "quick_ratio"),
        "cash_ratio": _extract_from_candidates(indicators, "cash_ratio"),
    })

    period_record["raw_data"] = {
        "income_statement": income,
        "balance_sheet": balance,
        "cashflow_statement": cashflow,
        "financial_indicators": indicators,
    }
    return period_record


def expand_financial_document_to_periods(document: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Expand a single financial snapshot document into multi-period standard financial records by reporting period.

    Args:
        document: Financial snapshot document dict, which must contain raw_data (including income_statement/balance_sheet/
                  cashflow_statement/financial_indicators/main_business subsection) and
                  symbol/code/name/data_source/report_period Equivalent information; returns an empty list if None or empty

    Returns:
        list[dict]: Standard list of financial records in descending order by reporting period (returned if no data is available []) , Each field ——
            symbol: Stock code (take document.symbol or document.code)
            code: Stock code (take document.code or document.symbol)
            name: Stock name
            data_source: Data source name
            source: Data source name (same as data_source)
            report_period: Reporting period 8-digit date string (YYYYMMDD)
            report_date: Report date 8-digit date string (same as report_period)
            report_type: report type: "annual"(annual report) | "quarterly"(quarterly report) | "unknown"
            ann_date: Announcement date 8-digit date string
            updated_at: Original document update time
            income_statement: Income statement breakdown dict
            balance_sheet: Balance Sheet Items dict
            cashflow_statement: Cash Flow Statement Items dict
            financial_indicators: Financial indicator breakdown dict
            main_business: Main business sub-item dict (if exists)
            revenue: Operating income (extracted from income_statement)
            oper_rev: Operating Income (Alternate Field)
            net_income: net profit
            net_profit: Net profit attributable to parent company
            oper_profit: operating profit
            operating_profit: Operating profit (same as oper_profit)
            ebit: EBIT
            total_profit: total profit
            oper_cost: operating costs
            oper_exp: operating expenses
            admin_exp: overhead
            fin_exp: financial charges
            rd_exp: R&D expenses
            total_assets: total assets
            total_liab: total liabilities
            total_equity: Shareholders equity
            total_cur_assets: current assets
            total_nca: non-current assets
            total_cur_liab: current liabilities
            total_ncl: non-current liabilities
            money_cap: Monetary funds
            accounts_receiv: Accounts receivable
            inventories: Inventory
            fix_assets: fixed assets
            n_cashflow_act: Net cash flow from operating activities
            n_cashflow_inv_act: Net cash flow from investing activities
            n_cashflow_fin_act: Net cash flow from financing activities
            c_cash_equ_end_period: Closing cash and equivalents
            c_cash_equ_beg_period: Opening cash and equivalents
            roe: ROE
            roa: return on total assets
            gross_margin: Gross profit margin
            netprofit_margin: net profit margin
            debt_to_assets: Asset-liability ratio
            assets_to_eqt: equity multiplier
            current_ratio: current ratio
            quick_ratio: quick ratio
            cash_ratio: cash ratio
            raw_data: Original breakdown dict — income_statement, balance_sheet, cashflow_statement, financial_indicators
    """
    if not document:
        return []

    raw_data = document.get("raw_data") or {}
    grouped: Dict[str, Dict[str, Any]] = {}
    section_names = [
        "income_statement",
        "balance_sheet",
        "cashflow_statement",
        "financial_indicators",
        "main_business",
    ]

    for section_name in section_names:
        for entry in _normalize_statement_list(raw_data.get(section_name)):
            period = _normalize_date_digits(
                _pick_first(entry.get("end_date"), entry.get("report_period"), document.get("report_period"), document.get("report_date"))
            )
            if not period:
                continue
            period_entry = grouped.setdefault(period, {
                "symbol": document.get("symbol") or document.get("code"),
                "code": document.get("code") or document.get("symbol"),
                "name": document.get("name"),
                "data_source": document.get("data_source") or document.get("source"),
                "source": document.get("data_source") or document.get("source"),
                "report_period": period,
                "report_date": period,
                "report_type": _determine_report_type(period),
                "ann_date": _normalize_date_digits(_pick_first(entry.get("ann_date"), entry.get("f_ann_date"), document.get("ann_date"))),
                "updated_at": document.get("updated_at"),
            })
            period_entry[section_name] = _prefer_statement(period_entry.get(section_name), entry)
            ann_date = _normalize_date_digits(_pick_first(entry.get("ann_date"), entry.get("f_ann_date"), document.get("ann_date")))
            if ann_date and ann_date > str(period_entry.get("ann_date") or ""):
                period_entry["ann_date"] = ann_date

    latest_period = _normalize_date_digits(_pick_first(document.get("report_period"), document.get("report_date")))
    if latest_period:
        snapshot_entry = grouped.setdefault(latest_period, {
            "symbol": document.get("symbol") or document.get("code"),
            "code": document.get("code") or document.get("symbol"),
            "name": document.get("name"),
            "data_source": document.get("data_source") or document.get("source"),
            "source": document.get("data_source") or document.get("source"),
            "report_period": latest_period,
            "report_date": latest_period,
            "report_type": document.get("report_type") or _determine_report_type(latest_period),
            "ann_date": _normalize_date_digits(document.get("ann_date")),
            "updated_at": document.get("updated_at"),
        })
        for field_name in [
            "revenue", "revenue_ttm", "oper_rev", "net_income", "net_profit", "net_profit_ttm", "oper_profit", "operating_profit", "ebit",
            "total_profit", "oper_cost", "oper_exp", "admin_exp", "fin_exp", "rd_exp", "total_assets", "total_liab", "total_equity",
            "total_cur_assets", "total_nca", "total_cur_liab", "total_ncl", "money_cap", "accounts_receiv", "inventories", "fix_assets",
            "n_cashflow_act", "n_cashflow_inv_act", "n_cashflow_fin_act", "c_cash_equ_end_period", "c_cash_equ_beg_period", "roe", "roa",
            "gross_margin", "netprofit_margin", "debt_to_assets", "assets_to_eqt", "current_ratio", "quick_ratio", "cash_ratio"
        ]:
            value = document.get(field_name)
            if value is not None and snapshot_entry.get(field_name) is None:
                snapshot_entry[field_name] = value

    if not grouped:
        fallback_period = _normalize_date_digits(_pick_first(document.get("report_period"), document.get("report_date")))
        if fallback_period:
            fallback = dict(document)
            fallback["report_period"] = fallback_period
            fallback["report_date"] = fallback_period
            fallback["source"] = fallback.get("data_source") or fallback.get("source")
            grouped[fallback_period] = fallback

    records = [_flatten_financial_period_record(record) for record in grouped.values()]
    records.sort(
        key=lambda item: (
            str(item.get("report_period") or item.get("report_date") or ""),
            str(item.get("ann_date") or ""),
        ),
        reverse=True,
    )
    return records


def _query_financial_period_documents(symbol: str, source: Optional[str], limit: int) -> List[Dict[str, Any]]:
    db = _get_db()
    col = db[_COL_FINANCIAL_PERIODS]
    query: Dict[str, Any] = {"$or": [{"symbol": symbol}, {"code": symbol}]}
    if source:
        query["source"] = source
    cursor = col.find(query, {"_id": 0}).sort([
        ("report_period", -1),
        ("ann_date", -1),
        ("updated_at", -1),
    ]).limit(limit)
    return list(cursor)


def _query_financial_snapshot_documents(symbol: str, source: Optional[str], limit: int) -> List[Dict[str, Any]]:
    db = _get_db()
    col = db[_COL_FINANCIAL]
    query: Dict[str, Any] = {"$or": [{"symbol": symbol}, {"code": symbol}]}
    if source:
        query["data_source"] = source
    items = list(col.find(query, {"_id": 0}).limit(max(limit * 3, 50)))
    items.sort(
        key=lambda item: str(item.get("report_period") or item.get("report_date") or ""),
        reverse=True,
    )
    return items[:limit]


def _get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _get_sources(market: str = "a_shares") -> List[str]:
    """Get a prioritized list of data sources."""
    try:
        from app.core.data_source_priority import get_enabled_data_sources_sync

        return get_enabled_data_sources_sync(market_category=market)
    except Exception:
        return ["local", "tushare", "akshare", "baostock"]


def get_stock_basic_info(symbol: str, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get basic stock information.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        source: Specify the data source (such as "tushare" / "akshare") , When None, press _get_sources() Try in order of priority

    Returns:
        dict | None: Stock basic information document, returns None if there is no match. Field (based on stock_basic_info collection storage)——
            symbol: 6 stock code
            code: 6 Bit stock code (alternate field)
            name: Stock name
            industry: Industry classification
            area: area
            list_date: Listing date
            total_mv: Total market value (10,000 yuan)
            circ_mv: Circulation market value (10,000 yuan)
            pe_ttm: rolling price to earnings ratio
            pb: price to book ratio
            pb_mrq: Price to Book Ratio for the Most Recent Reporting Period
            ps_ttm: rolling price-to-sales ratio
            source: Data source name
            Other possible fields: close/current_price/pre_close/open and other market snapshot fields
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_BASIC]
    query = {"$or": [{"symbol": symbol}, {"code": symbol}]}
    if source:
        query["source"] = source
        doc = col.find_one(query, {"_id": 0})
    else:
        doc = None
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
    """Get daily stock or K-line data.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        start_date: Starting date in the format YYYYMMDD or YYYY-MM-DD
        end_date: End date in the format YYYYMMDD or YYYY-MM-DD
        period: K Line period (default "daily") , Optional "daily"/"weekly"/"monthly" Wait for the period value stored in the database
        source: Specify the data source (such as "tushare" / "akshare") , When None, press _get_sources() Try in order of priority,
                Return the first data source with data first
        limit: Maximum number of records returned (default 1000)

    Returns:
        list[dict]: List of daily/K-line records sorted by trade_date in ascending order (returned when there is no data []) , Each field ——
            symbol: 6 stock code
            period: K line period
            trade_date: Transaction date (YYYYMMDD or YYYY-MM-DD, consistent with database storage)
            open: opening price
            high: highest price
            low: lowest price
            close: closing price
            pre_close: previous closing price
            volume: Volume
            amount: Turnover
            pct_chg: Increase or decrease (%)
            change: Changes
            turnover: turnover rate
            data_source: Data source name
            Other fields are stored in the database stock_daily_quotes collection.
    """
    symbol = str(symbol).strip().zfill(6)
    start = start_date.replace("-", "")[:8]
    end = end_date.replace("-", "")[:8]
    start_dash = f"{start[:4]}-{start[4:6]}-{start[6:8]}" if len(start) == 8 else start_date
    end_dash = f"{end[:4]}-{end[4:6]}-{end[6:8]}" if len(end) == 8 else end_date
    db = _get_db()
    col = db[_COL_DAILY]
    date_filter = {
        "$or": [
            {"trade_date": {"$gte": start, "$lte": end}},
            {"trade_date": {"$gte": start_dash, "$lte": end_dash}},
        ]
    }
    query = {
        "symbol": symbol,
        "period": period,
        **date_filter,
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
    """Get stock news.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        start_date: Starting time (datetime object, no limit to the starting point when None), and also matches the publish_time / pub_date fields
        end_date: End time (datetime object, no end point when None)
        limit: Maximum number of records returned (default 20)

    Returns:
        list[dict]: List of news records sorted in descending order by publish_time (or pub_date) (returned when no data is available []) , Each field ——
            symbol: 6 stock code
            title: News headline
            content: News text
            publish_time: Release time (datetime, priority field)
            pub_date: Release time (alternative field)
            url: News link
            source: news source
            Other fields are stored in the database stock_news collection.
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
    """Get stock news by date range.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        start_date: Starting date string, format YYYY-MM-DD (only the first 10 digits are parsed)
        end_date: End date string, format YYYY-MM-DD
        limit: Maximum number of records returned (default 20)

    Returns:
        list[dict]: List of news records sorted in descending order by publication time (returned when there is no data or date parsing fails []) , Each field ——
            symbol: 6 stock code
            title: News headline
            content: News text
            publish_time: Release time (datetime, priority field)
            pub_date: Release time (alternative field)
            url: News link
            source: news source
            Other fields are stored in the database stock_news collection.
    """
    symbol = str(symbol).strip().zfill(6)
    try:
        start_dt = datetime.strptime(start_date[:10], "%Y-%m-%d")
        end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d")
    except ValueError:
        return []
    return get_stock_news(symbol, start_date=start_dt, end_date=end_dt, limit=limit)


def get_market_quotes(symbol: str) -> Optional[Dict[str, Any]]:
    """Get real-time stock quotes.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)

    Returns:
        dict | None: Real-time quotation document, returns None when there is no match. Field (based on market_quotes collection storage)——
            symbol: 6 stock code
            code: 6 Bit stock code (alternate field)
            name: Stock name
            close: Closing price/Latest price
            current_price: latest price
            pre_close: previous closing price
            open: opening price
            high: highest price
            low: lowest price
            volume: Volume
            amount: Turnover
            pct_chg: Increase or decrease (%)
            change: Changes
            turnover: turnover rate
            trade_date: transaction date
            Other fields are stored in the market_quotes collection of the database.
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_QUOTES]
    return col.find_one({"$or": [{"symbol": symbol}, {"code": symbol}]}, {"_id": 0})


def get_latest_stock_price(symbol: str) -> Optional[float]:
    """Get the latest available price for a stock.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)

    Returns:
        float | None: Standard price entry, returns the first valid positive value according to the following priorities ——
            1. get_market_quotes() Returned close / current_price / pre_close / open fields
            2. get_stock_basic_info() Returned close / current_price / pre_close / open fields
            If none of the above are valid positive values, return None
    """
    symbol = str(symbol).strip().zfill(6)

    quotes = get_market_quotes(symbol) or {}
    for field in ("close", "current_price", "pre_close", "open"):
        value = quotes.get(field)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    basic_info = get_stock_basic_info(symbol) or {}
    for field in ("close", "current_price", "pre_close", "open"):
        value = basic_info.get(field)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    return None


def get_stock_financial_data(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get stock financial data.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        start_date: Starting date (YYYYMMDD or YYYY-MM-DD, no starting point is required when None),
                    Match report_period / report_date fields at the same time
        end_date: End date (YYYYMMDD or YYYY-MM-DD, no limit to the end date when None)
        limit: Maximum number of records returned (default 20, the actual query will be enlarged 3 times to ensure sufficient samples after sorting)
        source: Specify the data source (such as "tushare" / "akshare") , When None, do not filter by source

    Returns:
        list[dict]: List of financial records in descending order by report_period (or report_date) (returned when no data is available []) , 
                    Each field ——
            symbol: 6 stock code
            code: 6 Bit stock code (alternate field)
            name: Stock name
            data_source: Data source name
            source: Data source name (same as data_source)
            report_period: reporting period
            report_date: Report date (alternative field)
            ann_date: Announcement date
            updated_at: Update time
            raw_data: Raw itemized data dict (if present)— income_statement, balance_sheet,
                      cashflow_statement, financial_indicators, main_business
            Other fields are stored in the database stock_financial_data collection (which may include revenue/net_profit/
                      total_assets/roe flat fields, the structure varies depending on the data source)
    """
    symbol = str(symbol).strip().zfill(6)
    db = _get_db()
    col = db[_COL_FINANCIAL]
    query: Dict[str, Any] = {"$or": [{"symbol": symbol}, {"code": symbol}]}
    if source:
        query["data_source"] = source
    if start_date or end_date:
        q: Dict[str, str] = {}
        if start_date:
            q["$gte"] = start_date.replace("-", "")[:8]
        if end_date:
            q["$lte"] = end_date.replace("-", "")[:8]
        query["$and"] = [{"$or": [{"report_period": q}, {"report_date": q}]}]

    items = list(col.find(query, {"_id": 0}).limit(max(limit * 3, 50)))
    items.sort(
        key=lambda item: str(item.get("report_period") or item.get("report_date") or ""),
        reverse=True,
    )
    return items[:limit]


def get_stock_financial_periods(
    symbol: str,
    source: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get standard financial records expanded by reporting period.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        source: Specify the data source (such as "tushare" / "akshare") , When None, press _get_sources() Try in order of priority,
                Return the first data source with data first
        limit: Maximum number of records returned (default 20)

    Returns:
        list[dict]: Standard list of financial records in descending order by reporting period (returned if no data is available []) , Each field ——
            symbol: Stock code
            code: Stock code (alternative field)
            name: Stock name
            data_source: Data source name
            source: Data source name (same as data_source)
            report_period: Reporting period 8-digit date string (YYYYMMDD)
            report_date: Report date 8-digit date string (same as report_period)
            report_type: report type: "annual"(annual report) | "quarterly"(quarterly report) | "unknown"
            ann_date: Announcement date 8-digit date string
            updated_at: Update time
            income_statement: Income statement breakdown dict
            balance_sheet: Balance Sheet Items dict
            cashflow_statement: Cash Flow Statement Items dict
            financial_indicators: Financial indicator breakdown dict
            main_business: Main business sub-item dict (if exists)
            raw_data: Original breakdown dict — income_statement, balance_sheet, cashflow_statement, financial_indicators
            and flattened fields extracted by _flatten_financial_period_record —
                revenue, oper_rev, net_income, net_profit, oper_profit, operating_profit, ebit,
                total_profit, oper_cost, oper_exp, admin_exp, fin_exp, rd_exp, total_assets,
                total_liab, total_equity, total_cur_assets, total_nca, total_cur_liab, total_ncl,
                money_cap, accounts_receiv, inventories, fix_assets, n_cashflow_act, n_cashflow_inv_act,
                n_cashflow_fin_act, c_cash_equ_end_period, c_cash_equ_beg_period, roe, roa,
                gross_margin, netprofit_margin, debt_to_assets, assets_to_eqt, current_ratio,
                quick_ratio, cash_ratio
    """
    symbol = str(symbol).strip().zfill(6)

    candidate_sources = [source] if source else _get_sources()
    for candidate_source in candidate_sources:
        period_docs = _query_financial_period_documents(symbol, candidate_source, limit)
        if period_docs:
            return period_docs

        snapshot_docs = _query_financial_snapshot_documents(symbol, candidate_source, max(limit, 8))
        expanded: List[Dict[str, Any]] = []
        for document in snapshot_docs:
            expanded.extend(expand_financial_document_to_periods(document))
        if expanded:
            deduped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
            for item in expanded:
                key = (
                    str(item.get("source") or item.get("data_source") or candidate_source or ""),
                    str(item.get("report_period") or item.get("report_date") or ""),
                    str(item.get("ann_date") or ""),
                )
                existing = deduped.get(key)
                if existing is None or _statement_quality_score(item) >= _statement_quality_score(existing):
                    deduped[key] = item
            records = list(deduped.values())
            records.sort(
                key=lambda item: (
                    str(item.get("report_period") or item.get("report_date") or ""),
                    str(item.get("ann_date") or ""),
                ),
                reverse=True,
            )
            return records[:limit]

    fallback_docs = _query_financial_period_documents(symbol, None, limit)
    if fallback_docs:
        return fallback_docs

    snapshot_docs = _query_financial_snapshot_documents(symbol, None, max(limit, 8))
    expanded: List[Dict[str, Any]] = []
    for document in snapshot_docs:
        expanded.extend(expand_financial_document_to_periods(document))
    expanded.sort(
        key=lambda item: (
            str(item.get("report_period") or item.get("report_date") or ""),
            str(item.get("ann_date") or ""),
        ),
        reverse=True,
    )
    return expanded[:limit]


def get_industry_peer_basic_info(
    industry: str,
    exclude_symbol: Optional[str] = None,
    limit: int = 200,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get basic information on peer stocks by industry.

    Args:
        industry: Industry name keywords (case insensitive, use regex substring matching, for example "bank" / "Semiconductor") 
        exclude_symbol: Stock code to be excluded (6 digits, not excluded if None)
        limit: Maximum number of records returned (default 200)
        source: Specify the data source (such as "tushare" / "akshare") , When None, do not filter by source

    Returns:
        list[dict]: Peer stock basic information list (returned when industry is empty []) , Each field ——
            symbol: 6 stock code
            code: 6 Bit stock code (alternate field)
            name: Stock name
            industry: Industry classification
            area: area
            list_date: Listing date
            total_mv: Total market value (10,000 yuan)
            circ_mv: Circulation market value (10,000 yuan)
            pe_ttm: rolling price to earnings ratio
            pb: price to book ratio
            pb_mrq: Price to Book Ratio for the Most Recent Reporting Period
            ps_ttm: rolling price-to-sales ratio
            source: Data source name
            Other fields are stored in the database stock_basic_info collection.
    """
    industry_text = str(industry or "").strip()
    if not industry_text:
        return []

    db = _get_db()
    col = db[_COL_BASIC]
    query: Dict[str, Any] = {
        "industry": {"$regex": re.escape(industry_text), "$options": "i"}
    }

    normalized_exclude = str(exclude_symbol or "").strip().zfill(6) if exclude_symbol else ""
    if normalized_exclude:
        query["$and"] = [{"symbol": {"$ne": normalized_exclude}}, {"code": {"$ne": normalized_exclude}}]

    if source:
        query["source"] = source

    cursor = col.find(query, {"_id": 0}).limit(max(limit, 1))
    return list(cursor)


def summarize_industry_valuation(
    industry: str,
    metric: str = "pb",
    exclude_symbol: Optional[str] = None,
    limit: int = 200,
    source: Optional[str] = None,
    min_value: float = 0.0,
    max_value: float = 1000.0,
) -> Dict[str, Any]:
    """Summarize the statistical results of industry valuation indicators.

    Args:
        industry: Industry name keyword (same as get_industry_peer_basic_info)
        metric: Valuation metric (default "pb") , Optional "pb" / "pe" / "ps" Or custom field name;
                "pb" Take pb/pb_mrq,"pe" Take pe_ttm/pe,"ps" take ps_ttm/ps
        exclude_symbol: Stock code to be excluded (6 digits, not excluded if None)
        limit: Maximum number of peer samples (default 200)
        source: Specify the data source (same as get_industry_peer_basic_info, no filtering by source when None)
        min_value: Indicator lower bound (default 0.0), samples lower than this value will be eliminated
        max_value: Indicator upper bound (default 1000.0), samples higher than this value will be eliminated

    Returns:
        dict: Industry valuation statistical results, fields (used in the code .get() or [] access these keys)——
            industry: The original value of the input industry keyword
            metric: Standardized indicator name (lowercase)
            count: Number of valid samples (int, 0 when no sample)
            average: Mean (float, None when there is no sample)
            median: Median (float, None if no sample)
            min: Minimum value (float, None if no sample)
            max: Maximum value (float, None if no sample)
            samples: Sample list (up to 20 items), each structure —
                {"symbol": 6 bit code, "name": Stock name, <metric_key>: indicator value}
                 (When there is no sample, it is []) 
    """
    metric_key = str(metric or "pb").strip().lower()
    metric_fields = {
        "pb": ("pb", "pb_mrq"),
        "pe": ("pe_ttm", "pe"),
        "ps": ("ps_ttm", "ps"),
    }
    candidate_fields = metric_fields.get(metric_key, (metric_key,))

    peers = get_industry_peer_basic_info(
        industry=industry,
        exclude_symbol=exclude_symbol,
        limit=limit,
        source=source,
    )

    values: List[float] = []
    samples: List[Dict[str, Any]] = []
    for item in peers:
        raw_value = None
        for field_name in candidate_fields:
            candidate = item.get(field_name)
            if isinstance(candidate, (int, float)):
                raw_value = float(candidate)
                break

        if raw_value is None or raw_value <= min_value or raw_value >= max_value:
            continue

        values.append(raw_value)
        if len(samples) < 20:
            samples.append(
                {
                    "symbol": item.get("symbol") or item.get("code"),
                    "name": item.get("name"),
                    metric_key: raw_value,
                }
            )

    if not values:
        return {
            "industry": industry,
            "metric": metric_key,
            "count": 0,
            "average": None,
            "median": None,
            "min": None,
            "max": None,
            "samples": [],
        }

    return {
        "industry": industry,
        "metric": metric_key,
        "count": len(values),
        "average": sum(values) / len(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
        "samples": samples,
    }


def get_stock_valuation_context(symbol: str, financial_limit: int = 8) -> Dict[str, Any]:
    """Gets the valuation scenario standard input context.

    Args:
        symbol: A Stock stock code (6 digits or including exchange prefix and suffix, will be zfilled to 6 digits)
        financial_limit: Financial record period number (default 8), passed to get_stock_financial_periods(limit=...)

    Returns:
        dict: Valuation scenario standard input context, field (used in code .get() or [] access these keys)——
            basic_info: Basic stock information dict (if no data is available) {}) , field see get_stock_basic_info
            market_quotes: Real-time market quotation dict (when there is no data, it is {}) , field see get_market_quotes
            current_price: Latest available prices (float | None, See get_latest_stock_price for details)
            pe_ttm: Rolling P/E ratio (takes basic_info.pe_ttm or basic_info.pe, may be None)
            pb: Price-to-book ratio (takes basic_info.pb or basic_info.pb_mrq, may be None)
            ps_ttm: Rolling price-to-sales ratio (takes basic_info.ps_ttm or basic_info.ps, may be None)
            financial_data: List of standard financial records (list[dict], See get_stock_financial_periods for each field)
    """
    symbol = str(symbol).strip().zfill(6)
    basic_info = get_stock_basic_info(symbol) or {}
    market_quotes = get_market_quotes(symbol) or {}
    financial_data = get_stock_financial_periods(symbol, limit=financial_limit)
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


LOCAL_DATA_API_DOC = """
 [local data access — Existing data can be obtained from the database]

The synchronized stock data of this system is stored in MongoDB, and the generated Skill can be queried directly without calling external API.
Prioritize obtaining local data before considering external data sources. When there is insufficient data, call akshare, tushare, etc.

Allow import:from core.skill_runtime.data_access import ...

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

6. get_stock_financial_data(symbol, start_date=None, end_date=None, limit=20, source=None) -> list
   - Financial data: compatible with report_period / report_date two reporting period fields

7. get_stock_financial_periods(symbol, source=None, limit=20) -> list
    - Standard financial records after the reporting period is expanded, suitable for year-on-year, CAGR and multi-period quality factor calculations

8. get_stock_valuation_context(symbol, financial_limit=8) -> dict
   - Valuation scenario standard entry: return basic_info, market_quotes, current_price, pe_ttm, pb, ps_ttm,financial_data

9. get_industry_peer_basic_info(industry, exclude_symbol=None, limit=200, source=None) -> list
   - Sample peers by industry from local stock_basic_info
   - Suitable for PB/PE/PS relative valuation, industry comparison, and sample screening

10. summarize_industry_valuation(industry, metric="pb", exclude_symbol=None, limit=200, source=None, min_value=0.0, max_value=1000.0) -> dict
   - Based on local peer samples, return average / median / min / max / count
   - Relative valuation skills use this function first, do not write Mongo aggregation by yourself

 [Standard structured financial data capabilities — Recommend Agent/Skill to be reused first]
Allow import:from core.skill_runtime.standard_financial_apis import ...

11. get_historical_financial_annual_series(symbol, years=10, source=None) -> dict
   - Return the last N years of annual report series with one click, with fields including revenue, net_profit, roe, gross_margin, operating_cashflow, free_cashflow, debt_to_assets, etc.
   - Suitable for Buffett s in-depth analysis, long-term financial ledgers, and 5-10 year trends. Do not use get_income_analysis s Markdown table instead.

12. get_profitability_stability_metrics(symbol, years=10, source=None) -> dict
   - Calculate the mean, median, volatility, and coefficient of variation of revenue/net profit/ROE/gross profit margin and year-on-year growth based on the annual report sequence
   - This function is preferred for profitability stability, moat financial evidence, and quality analysis.

13. get_cashflow_quality_trend(symbol, years=10, source=None) -> dict
   - Returns the annual trend and statistical summary of OCF/net profit, FCF/net profit, OCF margin, and FCF margin based on the annual report sequence
   - This function is preferred for cash flow quality, profit content, and free cash flow analysis.

14. get_historical_valuation_percentile(symbol, metrics=None, lookback_years=5, as_of_date=None) -> dict
   - Structured returns the historical quantile, current value, median, sample number and window of pe_ttm / pb / ps_ttm / pcf_ttm
   - Replaces the hidden 3-year text quantile output in get_stock_fundamentals_unified

⚠️ Note: The above functions 4-5 (get_market_quotes, get_latest_stock_price) and 8 (get_stock_valuation_context) can only get the current PE/PB snapshot.
need **Structured historical PE/PB quantiles** (Such as historical quantile, PE channel, safety margin), the standard function is preferred:

    from core.skill_runtime.standard_financial_apis import get_historical_valuation_percentile
    result = get_historical_valuation_percentile("600519", metrics=["pe_ttm", "pb"], lookback_years=5)

If you only need the original historical valuation series, you can use the dedicated function of project_access:

    from core.skill_runtime.project_access import get_external_valuation_data
    result = get_external_valuation_data("600519", "2020-01-01", "2025-06-01")
    # Return {source: "baostock", data: [{date, close, pe_ttm, pb_mrq, ps_ttm, pcf_ttm}, ...]}

Do not use get_external_historical_data instead——It contains only OHLCV prices and no PE/PB fields.

Example 1: Check local first, if there is no data, then transfer externally API
    from core.skill_runtime.data_access import get_stock_basic_info, get_stock_daily_quotes
    info = get_stock_basic_info("600519")
    if info:
        ...
    else:
        ...

Example 2: Recommended writing method for valuation skills
    from core.skill_runtime.data_access import get_stock_valuation_context
    ctx = get_stock_valuation_context("600519")
    current_price = ctx["current_price"]
    if current_price is None or current_price <= 0:
        return {"status": "error", "message": "No effective current price has been obtained and cannot be valued."}

    pe_ttm = ctx["pe_ttm"]
    pb = ctx["pb"]
    ps_ttm = ctx["ps_ttm"]
    financial_data = ctx["financial_data"]

Example 3: Recommended way to write relative valuation of industry PB
    from core.skill_runtime.data_access import get_stock_valuation_context, summarize_industry_valuation

    ctx = get_stock_valuation_context(symbol)
    industry = (ctx["basic_info"] or {}).get("industry")
    industry_pb = summarize_industry_valuation(industry, metric="pb", exclude_symbol=symbol)
"""