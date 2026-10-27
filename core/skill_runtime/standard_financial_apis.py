"""General financial data processing capabilities.

These functions provide structured and auditable standard data capabilities for reuse by Agents and generated Skills.
Principles: fixed caliber, structured output, explicit coverage and warnings to prevent LLM from picking out numbers and calculations from Markdown text.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
import re
from statistics import mean, median, pstdev
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .data_access import (
    _get_db,
    get_industry_peer_basic_info,
    get_latest_stock_price,
    get_market_quotes,
    get_stock_basic_info,
    get_stock_daily_quotes,
    get_stock_financial_periods,
    get_stock_news_by_date_range,
    summarize_industry_valuation,
)
from .project_access import get_external_historical_data, get_external_valuation_data
from .sync_wrappers import normalize_tabular_result, run_async_in_sync
from .catalog import SUPPORTED_EXTERNAL_SOURCES, list_configured_external_sources


def _normalize_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    for prefix in ("SH", "SZ", "SS", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _resolve_security_query_to_symbol(query: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Parse the stock code or stock name into a 6-digit A-share code and try to return basic information."""
    text = str(query or "").strip()
    if not text:
        return "", None

    normalized_symbol = _normalize_symbol(text)
    if normalized_symbol:
        basic = get_stock_basic_info(normalized_symbol)
        return normalized_symbol, basic

    # Stock name query: reuse the local stock_basic_info collection to avoid LLM guessing codes.
    keyword = re.sub(r"(Change|one|stocks|test|For a moment|retest|Test again|use|of|code|securities)", "", text).strip() or text
    db = _get_db()
    col = db["stock_basic_info"]
    escaped = re.escape(keyword)
    projection = {"_id": 0}
    docs = list(col.find(
        {
            "$or": [
                {"name": keyword},
                {"name": {"$regex": escaped, "$options": "i"}},
                {"code": keyword},
                {"symbol": keyword},
            ]
        },
        projection,
    ).limit(20))
    if not docs:
        return "", None

    def _score(doc: Dict[str, Any]) -> Tuple[int, int]:
        name = str(doc.get("name") or "")
        source = str(doc.get("source") or doc.get("data_source") or "")
        exact = 1 if name == keyword else 0
        preferred_source = 1 if source in ("tushare", "multi_source", "akshare", "baostock") else 0
        return exact, preferred_source

    best = sorted(docs, key=_score, reverse=True)[0]
    code = str(best.get("code") or best.get("symbol") or "").strip()
    match = re.search(r"\d{6}", code)
    return (match.group(0), best) if match else ("", best)


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def _date_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")


def _exchange_suffix(symbol: str) -> Optional[str]:
    if not symbol:
        return None
    if symbol.startswith(("6", "9")):
        return "SH"
    if symbol.startswith(("0", "2", "3")):
        return "SZ"
    if symbol.startswith(("4", "8")):
        return "BJ"
    return None


def _infer_listing_status(basic: Dict[str, Any]) -> str:
    for field in ("list_status", "listing_status", "status"):
        value = str(basic.get(field) or "").strip().upper()
        if value:
            if value in {"L", "LISTED", "Listed"}:
                return "listed"
            if value in {"D", "DELISTED", "delisting"}:
                return "delisted"
            if value in {"P", "PAUSED", "Suspended from listing"}:
                return "paused"
            return value.lower()
    return "listed" if basic else "unknown"


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _pick_number(record: Dict[str, Any], *fields: str) -> Optional[float]:
    for field in fields:
        value = _safe_float(record.get(field))
        if value is not None:
            return value
    return None


def _period_year(period: Any) -> Optional[int]:
    text = "".join(ch for ch in str(period or "") if ch.isdigit())
    if len(text) >= 4:
        try:
            return int(text[:4])
        except ValueError:
            return None
    return None


def _is_annual_record(record: Dict[str, Any]) -> bool:
    period = "".join(ch for ch in str(record.get("report_period") or record.get("report_date") or "") if ch.isdigit())
    return period.endswith("1231") or str(record.get("report_type") or "").lower() == "annual"


def _dedupe_by_year(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_year: Dict[int, Dict[str, Any]] = {}
    for record in records:
        year = _period_year(record.get("report_period") or record.get("report_date"))
        if year is None:
            continue
        existing = by_year.get(year)
        if existing is None:
            by_year[year] = record
            continue
        existing_score = sum(1 for value in existing.values() if value not in (None, "", [], {}))
        candidate_score = sum(1 for value in record.values() if value not in (None, "", [], {}))
        if candidate_score >= existing_score:
            by_year[year] = record
    return [by_year[year] for year in sorted(by_year.keys(), reverse=True)]


def _percentile_rank(values: List[float], current: float) -> Optional[float]:
    valid = [value for value in values if value is not None and value > 0]
    if not valid:
        return None
    return sum(1 for value in valid if value <= current) / len(valid) * 100


def _percentile_rank_numeric(values: List[float], current: Optional[float]) -> Optional[float]:
    if current is None:
        return None
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return sum(1 for value in valid if value <= current) / len(valid) * 100


def _growth_rate(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def _series_stats(values: List[Optional[float]]) -> Dict[str, Any]:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "stddev": None, "coefficient_of_variation": None}
    avg = mean(valid)
    std = pstdev(valid) if len(valid) > 1 else 0.0
    return {
        "count": len(valid),
        "mean": avg,
        "median": median(valid),
        "min": min(valid),
        "max": max(valid),
        "stddev": std,
        "coefficient_of_variation": _safe_div(std, abs(avg)) if avg else None,
    }

    logger.info(f"📊 get_pledge_risk_profile Return structure: {list(result.keys())}")
    return result


def _cagr(latest: Optional[float], earliest: Optional[float], periods: int) -> Optional[float]:
    if latest is None or earliest is None or earliest <= 0 or latest <= 0 or periods <= 0:
        return None
    return (latest / earliest) ** (1 / periods) - 1


def _positive_ratio(values: List[Optional[float]]) -> Optional[float]:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return sum(1 for value in valid if value > 0) / len(valid)


def _normalize_metric_key(metric: str) -> str:
    return str(metric or "").strip().lower().replace("-", "_").replace(" ", "_")


def _to_tushare_ts_code(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return ""
    suffix = "SH" if normalized.startswith(("6", "9")) else "SZ"
    return f"{normalized}.{suffix}"


def _load_tushare_moneyflow_rows(symbol: str, start_date: str, end_date: str, limit: int) -> List[Dict[str, Any]]:
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider or not provider.is_available():
            return []
        result = run_async_in_sync(
            provider.get_moneyflow_ths(
                ts_code=_to_tushare_ts_code(symbol),
                start_date=_date_digits(start_date),
                end_date=_date_digits(end_date),
            )
        )
        rows = normalize_tabular_result(result) or []
    except Exception:
        return []

    normalized_symbol = _normalize_symbol(symbol)
    filtered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = _normalize_symbol(row.get("ts_code") or row.get("symbol") or row.get("code"))
        if row_symbol and row_symbol != normalized_symbol:
            continue
        filtered.append(row)

    filtered.sort(key=lambda item: str(item.get("trade_date") or item.get("date") or ""))
    return filtered[:max(1, min(int(limit or 120), 1000))]


def _load_tushare_industry_moneyflow_rows(start_date: str, end_date: str, limit: int) -> List[Dict[str, Any]]:
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider or not provider.is_available():
            return []
        result = run_async_in_sync(
            provider.get_moneyflow_ind_ths(
                start_date=_date_digits(start_date),
                end_date=_date_digits(end_date),
            )
        )
        rows = normalize_tabular_result(result) or []
    except Exception:
        return []

    filtered = [row for row in rows if isinstance(row, dict)]
    filtered.sort(key=lambda item: str(item.get("trade_date") or item.get("date") or ""), reverse=True)
    return filtered[:max(1, min(int(limit or 200), 1000))]


def _load_tushare_dividend_rows(symbol: str, limit: int) -> List[Dict[str, Any]]:
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider or not provider.is_available():
            return []
        result = run_async_in_sync(provider.get_dividend_data(symbol, limit=max(1, min(int(limit or 20), 100))))
        rows = normalize_tabular_result(result) or []
    except Exception:
        return []
    return [row for row in rows if isinstance(row, dict)]


def _read_local_collection_rows(collection_names: List[str], query: Dict[str, Any], limit: int = 200, sort_field: str = "trade_date") -> Tuple[List[Dict[str, Any]], Optional[str]]:
    db = _get_db()
    for collection_name in collection_names:
        try:
            rows = list(db[collection_name].find(query, {"_id": 0}).sort(sort_field, -1).limit(max(1, min(int(limit or 200), 1000))))
            if rows:
                return rows, collection_name
        except Exception:
            continue
    return [], None


def _extract_quote_value(record: Dict[str, Any], *fields: str) -> Optional[float]:
    return _pick_number(record, *fields)


def _sort_price_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda row: _date_digits(row.get("trade_date") or row.get("date") or row.get("datetime") or row.get("index")))


def _normalize_price_row(row: Dict[str, Any]) -> Dict[str, Any]:
    close = _extract_quote_value(row, "close", "price", "last_price")
    pre_close = _extract_quote_value(row, "pre_close", "prev_close")
    pct_chg = _extract_quote_value(row, "pct_chg", "change_pct")
    return {
        "trade_date": _normalize_date(row.get("trade_date") or row.get("date") or row.get("datetime") or row.get("index")),
        "open": _extract_quote_value(row, "open"),
        "high": _extract_quote_value(row, "high"),
        "low": _extract_quote_value(row, "low"),
        "close": close,
        "pre_close": pre_close,
        "volume": _extract_quote_value(row, "volume", "vol"),
        "amount": _extract_quote_value(row, "amount"),
        "turnover_rate": _extract_quote_value(row, "turnover_rate", "turnover"),
        "pct_chg": pct_chg,
        "data_source": row.get("data_source") or row.get("source"),
    }


def get_security_master(symbol: str) -> Dict[str, Any]:
    """Returns unified securities master data, supporting stock code or stock name.

    Args:
        symbol: A Stock stock code (6 digits) or stock name; returned if empty no_data

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            query: Raw input query string
            symbol: Normalized 6-digit stock symbol (None if parsing fails)
            ts_code: tushare format code (e.g. "600519.SH") 
            name: Security name
            exchange: exchange code (e.g. "SH" / "SZ") 
            industry: Industry
            area: area
            list_date: Release date (ISO format string)
            listing_status: Listing status
            is_st: Is ST stock
            market_cap: Total market capitalization
            float_market_cap: Circulation market value
            data_source: Data source name
            coverage: Coverage information — has_basic_info(Is there basic information?), has_market_quote(Is there a market price?),
                     resolved_by_name(Whether to resolve by name)
            warnings: Warning message list
    """
    original_query = str(symbol or "").strip()
    normalized_symbol, resolved_basic = _resolve_security_query_to_symbol(original_query)
    basic = resolved_basic or (get_stock_basic_info(normalized_symbol) if normalized_symbol else {}) or {}
    quote = get_market_quotes(normalized_symbol) if normalized_symbol else {}
    quote = quote or {}
    exchange = basic.get("exchange") or basic.get("market") or _exchange_suffix(normalized_symbol)
    name = basic.get("name") or quote.get("name")
    warnings: List[str] = []
    if not normalized_symbol:
        warnings.append("A valid security code could not be parsed from the input.")
    if normalized_symbol and not basic:
        warnings.append("Security basic information not found in stock_basic_info.")
    return {
        "status": "success" if basic or quote else "no_data",
        "query": original_query,
        "symbol": normalized_symbol,
        "ts_code": basic.get("ts_code") or (f"{normalized_symbol}.{exchange}" if normalized_symbol and exchange else None),
        "name": name,
        "exchange": exchange,
        "industry": basic.get("industry") or basic.get("sw_industry") or basic.get("sector"),
        "area": basic.get("area"),
        "list_date": _normalize_date(basic.get("list_date") or basic.get("listing_date")),
        "listing_status": _infer_listing_status(basic),
        "is_st": bool("ST" in str(name or "").upper()),
        "market_cap": _pick_number(basic, "total_mv", "market_cap", "market_value"),
        "float_market_cap": _pick_number(basic, "circ_mv", "float_market_cap"),
        "data_source": basic.get("source") or basic.get("data_source") or quote.get("source") or quote.get("data_source"),
        "coverage": {
            "has_basic_info": bool(basic),
            "has_market_quote": bool(quote),
            "resolved_by_name": bool(normalized_symbol and original_query and not _normalize_symbol(original_query)),
        },
        "warnings": warnings,
    }


def get_adjusted_price_series(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "daily",
    limit: int = 1000,
) -> Dict[str, Any]:
    """Returns the normalized price series. Currently, priority is given to using the local daily line. If the local market has regained its rights, the restoration price will be transparently transmitted.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), if None, the default is the last 3 years
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        period: cycle: "daily" (default)| "weekly" | "monthly"
        limit: Maximum number of samples (default 1000, will be truncated to [1, 3000]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            period: Actual usage period
            adjustment: Restoration logo: "as_stored" (Transparent transmission according to local storage)
            data_source: Data source: "local" or external data source name
            window: time window — start(start date), end(Deadline)
            records: price series [{"trade_date": ..., "open": ..., "high": ..., "low": ...,
                     "close": ..., "volume": ..., "amount": ..., "turnover_rate": ...,
                     "pct_chg": ..., "data_source": ...}, ...]
            coverage: Coverage information — sample_count(Number of samples)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    end = end_date or _today()
    start = start_date or _days_ago(365 * 3)
    rows = get_stock_daily_quotes(normalized_symbol, start, end, period=period, limit=max(1, min(int(limit or 1000), 3000)))
    data_source = "local"
    if not rows:
        external = get_external_historical_data(normalized_symbol, start, end, period=period)
        external_rows = external.get("data") if isinstance(external, dict) else []
        if isinstance(external_rows, list) and external_rows:
            rows = external_rows[: max(1, min(int(limit or 1000), 3000))]
            data_source = str(external.get("source") or "external")
    records = [_normalize_price_row(row) for row in _sort_price_rows(rows)]
    records = [row for row in records if row.get("trade_date") and row.get("close") is not None]
    warnings: List[str] = []
    if not records:
        warnings.append("No valid price series was obtained.")
    if len(records) >= max(1, min(int(limit or 1000), 3000)):
        warnings.append("Price series may be truncated by limit.")
    return {
        "status": "success" if records else "no_data",
        "symbol": normalized_symbol,
        "period": period,
        "adjustment": "as_stored",
        "data_source": data_source,
        "window": {"start": start, "end": end},
        "records": records,
        "coverage": {"sample_count": len(records)},
        "warnings": warnings,
    }


def _rolling_mean(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    result: List[Optional[float]] = []
    for index in range(len(values)):
        subset = [value for value in values[max(0, index - window + 1): index + 1] if value is not None]
        result.append(mean(subset) if len(subset) >= min(window, index + 1) and subset else None)
    return result


def _rolling_std(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    result: List[Optional[float]] = []
    for index in range(len(values)):
        subset = [value for value in values[max(0, index - window + 1): index + 1] if value is not None]
        result.append(pstdev(subset) if len(subset) >= 2 else None)
    return result


def _ema_series(values: List[Optional[float]], span: int) -> List[Optional[float]]:
    alpha = 2 / (span + 1)
    result: List[Optional[float]] = []
    previous: Optional[float] = None
    for value in values:
        if value is None:
            result.append(previous)
            continue
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        result.append(previous)
    return result


def _latest_valid(records: List[Dict[str, Any]], field: str) -> Optional[float]:
    for row in reversed(records):
        value = _safe_float(row.get(field))
        if value is not None:
            return value
    return None


def get_return_series(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "daily",
    limit: int = 1000,
) -> Dict[str, Any]:
    """Returns a yield series based on a price series.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), if None, the default is the last 3 years
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        period: cycle: "daily" (default)| "weekly" | "monthly"
        limit: Maximum number of samples (default 1000, will be truncated to [1, 3000]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit price series status)
            symbol: Standardized 6-digit stock code
            period: Actual usage period
            window: time window — start(start date), end(Deadline)
            records: return series [{"trade_date": ..., "close": ..., "return": ...,
                     "return_pct": ...}, ...]
            summary: Yield statistics — count(Number of samples), mean(mean), median(median),
                     min(minimum value), max(maximum value), stddev(standard deviation),
                     coefficient_of_variation(coefficient of variation)
            coverage: Coverage information — price_sample_count(Number of price samples), return_sample_count(Return sample number)
            warnings: Warning message list
    """
    price = get_adjusted_price_series(symbol, start_date=start_date, end_date=end_date, period=period, limit=limit)
    records = price.get("records") or []
    returns: List[Dict[str, Any]] = []
    previous_close: Optional[float] = None
    for row in records:
        close = _safe_float(row.get("close"))
        ret = _safe_div(close - previous_close, previous_close) if close is not None and previous_close else None
        returns.append({
            "trade_date": row.get("trade_date"),
            "close": close,
            "return": ret,
            "return_pct": ret * 100 if ret is not None else None,
        })
        if close is not None and close > 0:
            previous_close = close
    valid_returns = [item.get("return") for item in returns if item.get("return") is not None]
    return {
        "status": "success" if valid_returns else price.get("status"),
        "symbol": price.get("symbol"),
        "period": period,
        "window": price.get("window"),
        "records": returns,
        "summary": _series_stats(valid_returns),
        "coverage": {"price_sample_count": len(records), "return_sample_count": len(valid_returns)},
        "warnings": list(price.get("warnings") or []),
    }


def get_technical_indicator_series(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    indicators: Optional[List[str]] = None,
    limit: int = 300,
) -> Dict[str, Any]:
    """Calculate historical series of structured technical indicators based on standard price series.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), if None, the default is the last 3 years
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        indicators: Indicator list, support "ma" / "macd" / "rsi" / "kdj" / "boll" / "atr" /
                    "obv" / "support_resistance"; Returns all if None
        limit: Maximum number of samples (default 300, will be truncated to [80, 1000]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            window: time window — start(start date), end(Deadline)
            data_source: Data source name
            indicators: List of actually calculated indicators (after sorting)
            records: technical indicator series [{"trade_date": ..., "close": ..., "ma5": ..., "ma10": ...,
                     "ma20": ..., "ma60": ..., "dif": ..., "dea": ..., "macd_hist": ...,
                     "rsi14": ..., "kdj_k": ..., "kdj_d": ..., "kdj_j": ...,
                     "boll_mid": ..., "boll_upper": ..., "boll_lower": ...,
                     "atr14": ..., "obv": ..., "support_20": ..., "resistance_20": ...}, ...]
                      (Fields appear dynamically based on requested indicators)
            latest: Latest one-day indicator snapshot (same as records element structure)
            summary: Aggregated information — sample_count(Number of samples), latest_close(latest closing price),
                     latest_ma20(Latest MA20), latest_atr14(Latest ATR14),
                     latest_boll_position(Bollinger Bands Position 0-1),
                     latest_support_20(Latest 20-day support), latest_resistance_20(Latest 20 Day Resistance)
            warnings: Warning message list
    """
    requested = {_normalize_metric_key(item) for item in (indicators or ["ma", "macd", "rsi", "kdj", "boll", "atr", "obv", "support_resistance"])}
    price = get_adjusted_price_series(symbol, start_date=start_date, end_date=end_date, limit=max(80, min(int(limit or 300), 1000)))
    rows = price.get("records") or []
    closes = [_safe_float(row.get("close")) for row in rows]
    highs = [_safe_float(row.get("high")) for row in rows]
    lows = [_safe_float(row.get("low")) for row in rows]
    volumes = [_safe_float(row.get("volume")) for row in rows]

    ma5 = _rolling_mean(closes, 5)
    ma10 = _rolling_mean(closes, 10)
    ma20 = _rolling_mean(closes, 20)
    ma60 = _rolling_mean(closes, 60)
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    dif = [(a - b) if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
    dea = _ema_series(dif, 9)
    macd_hist = [((d - e) * 2) if d is not None and e is not None else None for d, e in zip(dif, dea)]

    returns = [None]
    gains: List[Optional[float]] = [None]
    losses: List[Optional[float]] = [None]
    for index in range(1, len(closes)):
        current = closes[index]
        previous = closes[index - 1]
        change = current - previous if current is not None and previous is not None else None
        returns.append(_safe_div(change, previous) if change is not None and previous else None)
        gains.append(max(change, 0) if change is not None else None)
        losses.append(abs(min(change, 0)) if change is not None else None)
    avg_gain = _rolling_mean(gains, 14)
    avg_loss = _rolling_mean(losses, 14)
    rsi14 = []
    for gain, loss in zip(avg_gain, avg_loss):
        if gain is None or loss is None:
            rsi14.append(None)
        elif loss == 0:
            rsi14.append(100.0)
        else:
            rs = gain / loss
            rsi14.append(100 - 100 / (1 + rs))

    boll_mid = ma20
    boll_std = _rolling_std(closes, 20)
    boll_upper = [(mid + 2 * std) if mid is not None and std is not None else None for mid, std in zip(boll_mid, boll_std)]
    boll_lower = [(mid - 2 * std) if mid is not None and std is not None else None for mid, std in zip(boll_mid, boll_std)]

    kdj_k: List[Optional[float]] = []
    kdj_d: List[Optional[float]] = []
    k_value: Optional[float] = 50.0
    d_value: Optional[float] = 50.0
    for index in range(len(rows)):
        low_window = [value for value in lows[max(0, index - 8): index + 1] if value is not None]
        high_window = [value for value in highs[max(0, index - 8): index + 1] if value is not None]
        close = closes[index]
        if close is None or not low_window or not high_window or max(high_window) == min(low_window):
            kdj_k.append(k_value)
            kdj_d.append(d_value)
            continue
        rsv = (close - min(low_window)) / (max(high_window) - min(low_window)) * 100
        k_value = (2 / 3) * (k_value or 50) + (1 / 3) * rsv
        d_value = (2 / 3) * (d_value or 50) + (1 / 3) * k_value
        kdj_k.append(k_value)
        kdj_d.append(d_value)
    kdj_j = [(3 * k - 2 * d) if k is not None and d is not None else None for k, d in zip(kdj_k, kdj_d)]

    true_ranges: List[Optional[float]] = []
    obv: List[Optional[float]] = []
    running_obv = 0.0
    for index, row in enumerate(rows):
        high = highs[index]
        low = lows[index]
        close = closes[index]
        previous_close = closes[index - 1] if index > 0 else None
        tr_candidates = []
        if high is not None and low is not None:
            tr_candidates.append(high - low)
        if high is not None and previous_close is not None:
            tr_candidates.append(abs(high - previous_close))
        if low is not None and previous_close is not None:
            tr_candidates.append(abs(low - previous_close))
        true_ranges.append(max(tr_candidates) if tr_candidates else None)
        volume = volumes[index] or 0
        if index > 0 and close is not None and previous_close is not None:
            if close > previous_close:
                running_obv += volume
            elif close < previous_close:
                running_obv -= volume
        obv.append(running_obv)
    atr14 = _rolling_mean(true_ranges, 14)
    support_20 = [min([value for value in lows[max(0, index - 19): index + 1] if value is not None], default=None) for index in range(len(rows))]
    resistance_20 = [max([value for value in highs[max(0, index - 19): index + 1] if value is not None], default=None) for index in range(len(rows))]

    records: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        item: Dict[str, Any] = {"trade_date": row.get("trade_date"), "close": closes[index]}
        if "ma" in requested or "moving_average" in requested:
            item.update({"ma5": ma5[index], "ma10": ma10[index], "ma20": ma20[index], "ma60": ma60[index]})
        if "macd" in requested:
            item.update({"dif": dif[index], "dea": dea[index], "macd_hist": macd_hist[index]})
        if "rsi" in requested or "rsi14" in requested:
            item["rsi14"] = rsi14[index]
        if "kdj" in requested:
            item.update({"kdj_k": kdj_k[index], "kdj_d": kdj_d[index], "kdj_j": kdj_j[index]})
        if "boll" in requested or "bollinger" in requested:
            item.update({"boll_mid": boll_mid[index], "boll_upper": boll_upper[index], "boll_lower": boll_lower[index]})
        if "atr" in requested or "atr14" in requested:
            item["atr14"] = atr14[index]
        if "obv" in requested:
            item["obv"] = obv[index]
        if "support_resistance" in requested or "support" in requested or "resistance" in requested:
            item.update({"support_20": support_20[index], "resistance_20": resistance_20[index]})
        records.append(item)

    latest = records[-1] if records else {}
    warnings = list(price.get("warnings") or [])
    if len(records) < 60:
        warnings.append("There are less than 60 price samples, and mid-term indicators such as MA60 have limited reference value.")
    return {
        "status": "success" if records else "no_data",
        "symbol": price.get("symbol"),
        "window": price.get("window"),
        "data_source": price.get("data_source"),
        "indicators": sorted(requested),
        "records": records[-max(1, min(int(limit or 300), 1000)):],
        "latest": latest,
        "summary": {
            "sample_count": len(records),
            "latest_close": latest.get("close"),
            "latest_ma20": latest.get("ma20"),
            "latest_atr14": latest.get("atr14"),
            "latest_boll_position": _safe_div((latest.get("close") - latest.get("boll_lower")) if latest.get("close") is not None and latest.get("boll_lower") is not None else None, (latest.get("boll_upper") - latest.get("boll_lower")) if latest.get("boll_upper") is not None and latest.get("boll_lower") is not None else None),
            "latest_support_20": latest.get("support_20"),
            "latest_resistance_20": latest.get("resistance_20"),
        },
        "warnings": warnings,
    }


def get_volatility_metrics(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "daily",
    limit: int = 1000,
) -> Dict[str, Any]:
    """Returns the yield volatility indicator.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), if None, the default is the last 3 years
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        period: cycle: "daily" (Default, annualization factor 252)| "weekly" (52) | "monthly" (12) 
        limit: Maximum number of samples (default 1000, will be truncated to [1, 3000]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "insufficient_data"
            symbol: Standardized 6-digit stock code
            period: Actual usage period
            window: time window — start(start date), end(Deadline)
            metrics: volatility indicator — volatility(daily volatility), volatility_pct(daily volatility%),
                     annualized_volatility(annualized volatility),
                     annualized_volatility_pct(annualized volatility%), sample_count(Number of samples)
            warnings: Warning message list (additional prompt when valid samples are less than 20)
    """
    returns = get_return_series(symbol, start_date=start_date, end_date=end_date, period=period, limit=limit)
    values = [item.get("return") for item in returns.get("records", []) if item.get("return") is not None]
    valid = [float(value) for value in values]
    trading_days = 252 if period == "daily" else 52 if period == "weekly" else 12
    daily_vol = pstdev(valid) if len(valid) > 1 else None
    annualized = daily_vol * (trading_days ** 0.5) if daily_vol is not None else None
    return {
        "status": "success" if daily_vol is not None else "insufficient_data",
        "symbol": returns.get("symbol"),
        "period": period,
        "window": returns.get("window"),
        "metrics": {
            "volatility": daily_vol,
            "volatility_pct": daily_vol * 100 if daily_vol is not None else None,
            "annualized_volatility": annualized,
            "annualized_volatility_pct": annualized * 100 if annualized is not None else None,
            "sample_count": len(valid),
        },
        "warnings": list(returns.get("warnings") or []) + ([] if len(valid) >= 20 else ["There are less than 20 effective return samples, and the volatility reference value is limited."]),
    }


def get_drawdown_metrics(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "daily",
    limit: int = 1000,
) -> Dict[str, Any]:
    """Returns the maximum retracement and retracement sequence.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), if None, the default is the last 3 years
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        period: cycle: "daily" (default)| "weekly" | "monthly"
        limit: Maximum number of samples (default 1000, will be truncated to [1, 3000]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "insufficient_data"
            symbol: Standardized 6-digit stock code
            period: Actual usage period
            window: time window — start(start date), end(Deadline)
            metrics: retracement indicator — max_drawdown(maximum drawdown), max_drawdown_pct(maximum drawdown%),
                     max_drawdown_start(Retracement starting date), max_drawdown_end(Retracement end date),
                     sample_count(Number of samples)
            drawdown_series: retracement sequence [{"trade_date": ..., "close": ..., "peak": ...,
                              "drawdown": ..., "drawdown_pct": ...}, ...]
            warnings: Warning message list
    """
    price = get_adjusted_price_series(symbol, start_date=start_date, end_date=end_date, period=period, limit=limit)
    peak: Optional[float] = None
    peak_date: Optional[str] = None
    max_drawdown: Optional[float] = None
    max_drawdown_start: Optional[str] = None
    max_drawdown_end: Optional[str] = None
    series: List[Dict[str, Any]] = []
    for row in price.get("records", []):
        close = _safe_float(row.get("close"))
        if close is None or close <= 0:
            continue
        trade_date = row.get("trade_date")
        if peak is None or close > peak:
            peak = close
            peak_date = trade_date
        drawdown = _safe_div(close - peak, peak) if peak else None
        series.append({"trade_date": trade_date, "close": close, "peak": peak, "drawdown": drawdown, "drawdown_pct": drawdown * 100 if drawdown is not None else None})
        if drawdown is not None and (max_drawdown is None or drawdown < max_drawdown):
            max_drawdown = drawdown
            max_drawdown_start = peak_date
            max_drawdown_end = trade_date
    return {
        "status": "success" if max_drawdown is not None else "insufficient_data",
        "symbol": price.get("symbol"),
        "period": period,
        "window": price.get("window"),
        "metrics": {
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown * 100 if max_drawdown is not None else None,
            "max_drawdown_start": max_drawdown_start,
            "max_drawdown_end": max_drawdown_end,
            "sample_count": len(series),
        },
        "drawdown_series": series,
        "warnings": list(price.get("warnings") or []),
    }


def get_historical_financial_annual_series(
    symbol: str,
    years: int = 10,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns the financial sequence of the complete annual reports of a single A-share in the last N years.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            requested_years: Actual number of annual report years requested
            records: annual report financial sequence [{"year": ..., "report_period": ..., "ann_date": ...,
                     "revenue": ..., "net_profit": ..., "roe": ..., "roa": ..., "roic": ...,
                     "gross_margin": ..., "netprofit_margin": ..., "operating_margin": ...,
                     "expense_ratio": ..., "asset_turnover": ..., "equity_multiplier": ...,
                     "operating_cashflow": ..., "free_cashflow": ..., "total_assets": ...,
                     "total_liab": ..., "total_equity": ..., "debt_to_assets": ...,
                     "data_source": ...}, ...] (In descending order of year)
            coverage: Coverage information — requested_years(Number of years requested), available_years(Actual number of years),
                     missing_years(Missing year list)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    requested_years = max(1, min(int(years or 10), 15))
    fetch_limit = max(requested_years * 4 + 8, 40)
    records = get_stock_financial_periods(normalized_symbol, source=source, limit=fetch_limit)
    annual_records = _dedupe_by_year([record for record in records if _is_annual_record(record)])[:requested_years]

    output_records: List[Dict[str, Any]] = []
    for record in annual_records:
        period = str(record.get("report_period") or record.get("report_date") or "")
        year = _period_year(period)
        revenue = _pick_number(record, "revenue", "oper_rev")
        net_profit = _pick_number(record, "net_profit", "n_income_attr_p", "net_income")
        operating_cashflow = _pick_number(record, "n_cashflow_act")
        total_assets = _pick_number(record, "total_assets")
        total_liab = _pick_number(record, "total_liab")
        total_equity = _pick_number(record, "total_equity", "total_hldr_eqy_exc_min_int", "total_hldr_eqy_inc_min_int")
        capex = _pick_number(record, "capex", "c_pay_acq_const_fiolta", "c_pay_acq_const_fiolta")
        free_cashflow = operating_cashflow - capex if operating_cashflow is not None and capex is not None else None
        output_records.append({
            "year": year,
            "report_period": period,
            "ann_date": record.get("ann_date"),
            "revenue": revenue,
            "net_profit": net_profit,
            "roe": _pick_number(record, "roe", "roe_avg", "roe_waa"),
            "roa": _pick_number(record, "roa", "roa2"),
            "roic": _pick_number(record, "roic", "invested_capital_return"),
            "gross_margin": _pick_number(record, "gross_margin", "grossprofit_margin"),
            "netprofit_margin": _pick_number(record, "netprofit_margin"),
            "operating_margin": _pick_number(record, "operating_margin", "operate_profit_margin"),
            "expense_ratio": _pick_number(record, "expense_ratio") or _safe_div(
                sum(value for value in (
                    _pick_number(record, "oper_exp", "sell_exp"),
                    _pick_number(record, "admin_exp"),
                    _pick_number(record, "fin_exp"),
                ) if value is not None),
                revenue,
            ),
            "asset_turnover": _pick_number(record, "asset_turnover", "assets_turn"),
            "equity_multiplier": _safe_div(total_assets, total_equity),
            "operating_cashflow": operating_cashflow,
            "free_cashflow": free_cashflow,
            "total_assets": total_assets,
            "total_liab": total_liab,
            "total_equity": total_equity,
            "debt_to_assets": _pick_number(record, "debt_to_assets") or (_safe_div(total_liab, total_assets) * 100 if _safe_div(total_liab, total_assets) is not None else None),
            "data_source": record.get("source") or record.get("data_source"),
        })

    years_present = [item["year"] for item in output_records if item.get("year")]
    latest_year = max(years_present) if years_present else None
    expected_years = list(range(latest_year, latest_year - requested_years, -1)) if latest_year else []
    missing_years = [year for year in expected_years if year not in years_present]
    warnings: List[str] = []
    if len(output_records) < requested_years:
        warnings.append(f"only get {len(output_records)} annual reporting periods, less than requested {requested_years} years.")
    if missing_years:
        warnings.append(f"Annual report year missing: {missing_years}")

    return {
        "status": "success" if output_records else "no_data",
        "symbol": normalized_symbol,
        "requested_years": requested_years,
        "records": output_records,
        "coverage": {
            "requested_years": requested_years,
            "available_years": len(output_records),
            "missing_years": missing_years,
        },
        "warnings": warnings,
    }


def get_profitability_stability_metrics(symbol: str, years: int = 10, source: Optional[str] = None) -> Dict[str, Any]:
    """Earnings stability indicators are calculated based on the annual report sequence.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit annual report sequence status)
            symbol: Standardized 6-digit stock code
            years_used: Actual number of annual report years used
            coverage: Coverage information (the structure is the same as get_historical_financial_annual_series)
            metrics: stability statistics — revenue(revenue statistics), net_profit(Net profit statistics),
                     roe(ROE statistics), gross_margin(Gross profit margin statistics),
                     revenue_growth_yoy(Year-on-year revenue growth statistics), net_profit_growth_yoy(Net profit year-on-year growth statistics)
                      (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            trend_series: trend sequence — revenue(Revenue list), net_profit(Net profit list),
                     roe(ROE list), gross_margin(Gross profit margin list),
                     revenue_growth_yoy(Revenue growth rate list), net_profit_growth_yoy(Net profit year-on-year growth rate list)
            warnings: Warning information list (additional tips when the annual report sample is less than 5 years old)
    """
    series = get_historical_financial_annual_series(symbol, years=years, source=source)
    records = series.get("records") or []
    revenue_values = [item.get("revenue") for item in records]
    profit_values = [item.get("net_profit") for item in records]
    roe_values = [item.get("roe") for item in records]
    gross_margin_values = [item.get("gross_margin") for item in records]

    revenue_growth: List[Optional[float]] = []
    profit_growth: List[Optional[float]] = []
    for index, current in enumerate(records[:-1]):
        previous = records[index + 1]
        revenue_growth.append(_growth_rate(current.get("revenue"), previous.get("revenue")))
        profit_growth.append(_growth_rate(current.get("net_profit"), previous.get("net_profit")))

    warnings = list(series.get("warnings") or [])
    if len(records) < 5:
        warnings.append("The valid annual report samples are less than 5 years old, and the reference value of stability indicators is limited.")

    return {
        "status": series.get("status"),
        "symbol": series.get("symbol"),
        "years_used": len(records),
        "coverage": series.get("coverage"),
        "metrics": {
            "revenue": _series_stats(revenue_values),
            "net_profit": _series_stats(profit_values),
            "roe": _series_stats(roe_values),
            "gross_margin": _series_stats(gross_margin_values),
            "revenue_growth_yoy": _series_stats(revenue_growth),
            "net_profit_growth_yoy": _series_stats(profit_growth),
        },
        "trend_series": {
            "revenue": revenue_values,
            "net_profit": profit_values,
            "roe": roe_values,
            "gross_margin": gross_margin_values,
            "revenue_growth_yoy": revenue_growth,
            "net_profit_growth_yoy": profit_growth,
        },
        "warnings": warnings,
    }


def get_cashflow_quality_trend(symbol: str, years: int = 10, source: Optional[str] = None) -> Dict[str, Any]:
    """Calculate cash flow quality trends based on annual report series.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit annual report sequence status)
            symbol: Standardized 6-digit stock code
            years_used: Actual number of annual report years used
            coverage: Coverage information (the structure is the same as get_historical_financial_annual_series)
            trend: cash flow trends [{"year": ..., "report_period": ..., "net_profit": ...,
                  "operating_cashflow": ..., "free_cashflow": ...,
                  "ocf_to_net_profit": ..., "fcf_to_net_profit": ...,
                  "ocf_margin": ..., "fcf_margin": ...}, ...]
            summary: Summary statistics — ocf_to_net_profit, fcf_to_net_profit, ocf_margin, fcf_margin
                   (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            warnings: Warning message list
    """
    series = get_historical_financial_annual_series(symbol, years=years, source=source)
    records = series.get("records") or []
    trend: List[Dict[str, Any]] = []
    for item in records:
        net_profit = item.get("net_profit")
        ocf = item.get("operating_cashflow")
        fcf = item.get("free_cashflow")
        revenue = item.get("revenue")
        trend.append({
            "year": item.get("year"),
            "report_period": item.get("report_period"),
            "net_profit": net_profit,
            "operating_cashflow": ocf,
            "free_cashflow": fcf,
            "ocf_to_net_profit": _safe_div(ocf, net_profit),
            "fcf_to_net_profit": _safe_div(fcf, net_profit),
            "ocf_margin": _safe_div(ocf, revenue),
            "fcf_margin": _safe_div(fcf, revenue),
        })

    return {
        "status": series.get("status"),
        "symbol": series.get("symbol"),
        "years_used": len(records),
        "coverage": series.get("coverage"),
        "trend": trend,
        "summary": {
            "ocf_to_net_profit": _series_stats([item.get("ocf_to_net_profit") for item in trend]),
            "fcf_to_net_profit": _series_stats([item.get("fcf_to_net_profit") for item in trend]),
            "ocf_margin": _series_stats([item.get("ocf_margin") for item in trend]),
            "fcf_margin": _series_stats([item.get("fcf_margin") for item in trend]),
        },
        "warnings": list(series.get("warnings") or []),
    }


def get_historical_valuation_percentile(
    symbol: str,
    metrics: Optional[List[str]] = None,
    lookback_years: int = 5,
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns the structured historical valuation quantiles.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        metrics: List of valuation indicators, supported "pe" / "pe_ttm" / "pb" / "pb_mrq" /
                  "ps" / "ps_ttm" / "pcf" / "pcf_ttm"; Default when None ["pe_ttm", "pb", "ps_ttm"]
        lookback_years: Number of years to look back (default 5, will be truncated to [1, 15]) 
        as_of_date: Deadline (YYYY-MM-DD), defaults to today when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "partial_or_no_data"
            symbol: Standardized 6-digit stock code
            window: time window — start(start date), end(Deadline), lookback_years(Look back years)
            data_source: Data source name
            metrics: The results of each indicator {metric_name: {status, field, current_value,
                     current_date, median, average, min, max, percentile, sample_count}}
                      (status possible values: "success" | "insufficient_samples" | "no_data" | "unsupported_metric") 
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    requested_metrics = [str(item).strip().lower() for item in (metrics or ["pe_ttm", "pb", "ps_ttm"]) if str(item).strip()]
    metric_alias = {
        "pe": "pe_ttm",
        "pe_ttm": "pe_ttm",
        "pb": "pb_mrq",
        "pb_mrq": "pb_mrq",
        "ps": "ps_ttm",
        "ps_ttm": "ps_ttm",
        "pcf": "pcf_ttm",
        "pcf_ttm": "pcf_ttm",
    }
    lookback = max(1, min(int(lookback_years or 5), 15))
    end_date = as_of_date or datetime.now().strftime("%Y-%m-%d")
    try:
        end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d")
    except Exception:
        end_dt = datetime.now()
        end_date = end_dt.strftime("%Y-%m-%d")
    start_dt = end_dt - timedelta(days=365 * lookback)
    start_date = start_dt.strftime("%Y-%m-%d")

    valuation_result = get_external_valuation_data(normalized_symbol, start_date, end_date)
    rows = valuation_result.get("data") if isinstance(valuation_result, dict) else []
    if not isinstance(rows, list):
        rows = []
    sorted_rows = sorted([row for row in rows if isinstance(row, dict)], key=lambda row: str(row.get("date") or row.get("trade_date") or ""), reverse=True)

    metric_results: Dict[str, Any] = {}
    warnings: List[str] = []
    for requested_metric in requested_metrics:
        field = metric_alias.get(requested_metric)
        if not field:
            metric_results[requested_metric] = {"status": "unsupported_metric", "field": None}
            warnings.append(f"Unsupported valuation metrics: {requested_metric}")
            continue
        valid_points: List[Dict[str, Any]] = []
        for row in sorted_rows:
            value = _safe_float(row.get(field))
            if value is not None and value > 0:
                valid_points.append({"date": row.get("date") or row.get("trade_date"), "value": value})
        if not valid_points:
            metric_results[requested_metric] = {"status": "no_data", "field": field, "sample_count": 0}
            warnings.append(f"{requested_metric} There is no valid historical valuation sample.")
            continue
        current = valid_points[0]
        values = [point["value"] for point in valid_points]
        percentile = _percentile_rank(values, current["value"])
        metric_results[requested_metric] = {
            "status": "success" if len(valid_points) >= 60 else "insufficient_samples",
            "field": field,
            "current_value": current["value"],
            "current_date": current["date"],
            "median": median(values),
            "average": mean(values),
            "min": min(values),
            "max": max(values),
            "percentile": percentile,
            "sample_count": len(valid_points),
        }
        if len(valid_points) < 60:
            warnings.append(f"{requested_metric} There are less than 60 effective samples, and the reference value of quantiles is limited.")

    return {
        "status": "success" if any(item.get("status") == "success" for item in metric_results.values()) else "partial_or_no_data",
        "symbol": normalized_symbol,
        "window": {"start": start_date, "end": end_date, "lookback_years": lookback},
        "data_source": valuation_result.get("source") if isinstance(valuation_result, dict) else None,
        "metrics": metric_results,
        "warnings": warnings,
    }


def get_current_valuation_snapshot(symbol: str) -> Dict[str, Any]:
    """Returns the current valuation snapshot.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            name: Security name
            industry: Industry
            trade_date: Quote date
            current_price: current price
            metrics: Valuation indicators — pe, pe_ttm, pb, pb_mrq, ps, ps_ttm, peg,
                     dividend_yield(dividend yield), total_mv(Total market capitalization)
            metric_sources: Metric source tag — dividend_yield(Dividend rate data source description)
            raw_metrics: raw indicator — basic_info_dividend_yield(basic_info original dividend rate)
            data_source: Data source name
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    basic = get_stock_basic_info(normalized_symbol) or {}
    quote = get_market_quotes(normalized_symbol) or {}
    current_price = _pick_number(quote, "close", "price", "last_price") or _pick_number(basic, "close", "current_price")

    # The dividend rate uniformly uses the traceability caliber of shareholder_return_metrics:
    # Cash dividends implemented / same current_price. Avoid this tool's use of daily_basic.dv_ratio,
    # The dividend_valuation_context is recalculated using the dividend details, resulting in a difference of 4.36% vs 4.45%.
    raw_dividend_yield = _pick_number(basic, "dividend_yield", "dv_ttm")
    dividend_yield = raw_dividend_yield
    dividend_yield_source = "basic_info.daily_basic"
    try:
        shareholder = get_shareholder_return_metrics(normalized_symbol, years=5)
        canonical_pct = _pick_number(shareholder.get("metrics") or {}, "latest_dividend_yield_pct")
        if canonical_pct is not None:
            dividend_yield = canonical_pct
            dividend_yield_source = "shareholder_return_metrics.implemented_dividend/current_price"
    except Exception:
        pass

    return {
        "status": "success" if basic or quote else "no_data",
        "symbol": normalized_symbol,
        "name": basic.get("name") or quote.get("name"),
        "industry": basic.get("industry"),
        "trade_date": quote.get("trade_date") or basic.get("trade_date"),
        "current_price": current_price,
        "metrics": {
            "pe": _pick_number(basic, "pe", "pe_ttm"),
            "pe_ttm": _pick_number(basic, "pe_ttm", "pe"),
            "pb": _pick_number(basic, "pb", "pb_mrq"),
            "pb_mrq": _pick_number(basic, "pb_mrq", "pb"),
            "ps": _pick_number(basic, "ps", "ps_ttm"),
            "ps_ttm": _pick_number(basic, "ps_ttm", "ps"),
            "peg": _pick_number(basic, "peg"),
            "dividend_yield": dividend_yield,
            "total_mv": _pick_number(basic, "total_mv", "market_cap", "market_value"),
        },
        "metric_sources": {
            "dividend_yield": dividend_yield_source,
        },
        "raw_metrics": {
            "basic_info_dividend_yield": raw_dividend_yield,
        },
        "data_source": basic.get("source") or basic.get("data_source") or quote.get("source") or quote.get("data_source"),
        "warnings": [] if basic else ["Valuation snapshot not found in stock_basic_info."],
    }


def get_debt_solvency_trend(symbol: str, years: int = 10, source: Optional[str] = None) -> Dict[str, Any]:
    """Return to the long-term trend in solvency.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit annual report sequence status)
            symbol: Standardized 6-digit stock code
            years_used: Actual number of annual report years used
            coverage: Coverage information (the structure is the same as get_historical_financial_annual_series)
            trend: Solvency Trends [{"year": ..., "report_period": ..., "total_assets": ...,
                  "total_liab": ..., "total_equity": ..., "debt_to_assets": ...,
                  "current_ratio": ..., "quick_ratio": ..., "cash_ratio": ...,
                  "debt_to_equity": ..., "ocf_to_total_liab": ...}, ...]
            summary: Summary statistics — debt_to_assets, debt_to_equity, ocf_to_total_liab
                   (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            warnings: Warning message list
    """
    series = get_historical_financial_annual_series(symbol, years=years, source=source)
    trend: List[Dict[str, Any]] = []
    raw_records = get_stock_financial_periods(_normalize_symbol(symbol), source=source, limit=max(int(years or 10) * 4 + 8, 40))
    raw_by_period = {str(item.get("report_period") or item.get("report_date") or ""): item for item in raw_records}
    for item in series.get("records") or []:
        raw = raw_by_period.get(str(item.get("report_period") or ""), {})
        total_liab = item.get("total_liab")
        total_equity = item.get("total_equity")
        ocf = item.get("operating_cashflow")
        trend.append({
            "year": item.get("year"),
            "report_period": item.get("report_period"),
            "total_assets": item.get("total_assets"),
            "total_liab": total_liab,
            "total_equity": total_equity,
            "debt_to_assets": item.get("debt_to_assets"),
            "current_ratio": _pick_number(raw, "current_ratio"),
            "quick_ratio": _pick_number(raw, "quick_ratio"),
            "cash_ratio": _pick_number(raw, "cash_ratio"),
            "debt_to_equity": _safe_div(total_liab, total_equity),
            "ocf_to_total_liab": _safe_div(ocf, total_liab),
        })
    debt_values = [item.get("debt_to_assets") for item in trend]
    return {
        "status": series.get("status"),
        "symbol": series.get("symbol"),
        "years_used": len(trend),
        "coverage": series.get("coverage"),
        "trend": trend,
        "summary": {
            "debt_to_assets": _series_stats(debt_values),
            "debt_to_equity": _series_stats([item.get("debt_to_equity") for item in trend]),
            "ocf_to_total_liab": _series_stats([item.get("ocf_to_total_liab") for item in trend]),
        },
        "warnings": list(series.get("warnings") or []),
    }


def get_margin_stability_metrics(symbol: str, years: int = 10, source: Optional[str] = None) -> Dict[str, Any]:
    """Returns the profit margin stability indicator.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit annual report sequence status)
            symbol: Standardized 6-digit stock code
            years_used: Actual number of annual report years used
            coverage: Coverage information (the structure is the same as get_historical_financial_annual_series)
            trend: profit margin trends [{"year": ..., "report_period": ..., "gross_margin": ...,
                  "netprofit_margin": ..., "operating_margin": ..., "expense_ratio": ...}, ...]
            metrics: Profit rate stability statistics — gross_margin, netprofit_margin, operating_margin, expense_ratio
                   (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            warnings: Warning information list (additional tips when the annual report sample is less than 5 years old)
    """
    series = get_historical_financial_annual_series(symbol, years=years, source=source)
    records = series.get("records") or []
    metrics = {
        "gross_margin": _series_stats([item.get("gross_margin") for item in records]),
        "netprofit_margin": _series_stats([item.get("netprofit_margin") for item in records]),
        "operating_margin": _series_stats([item.get("operating_margin") for item in records]),
        "expense_ratio": _series_stats([item.get("expense_ratio") for item in records]),
    }
    trend = [
        {
            "year": item.get("year"),
            "report_period": item.get("report_period"),
            "gross_margin": item.get("gross_margin"),
            "netprofit_margin": item.get("netprofit_margin"),
            "operating_margin": item.get("operating_margin"),
            "expense_ratio": item.get("expense_ratio"),
        }
        for item in records
    ]
    warnings = list(series.get("warnings") or [])
    if len(records) < 5:
        warnings.append("The valid annual report sample is less than 5 years, and the reference value for profit rate stability is limited.")
    return {
        "status": series.get("status"),
        "symbol": series.get("symbol"),
        "years_used": len(records),
        "coverage": series.get("coverage"),
        "trend": trend,
        "metrics": metrics,
        "warnings": warnings,
    }


def get_capital_efficiency_trend(symbol: str, years: int = 10, source: Optional[str] = None) -> Dict[str, Any]:
    """Return to the long-term trend in capital efficiency.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit annual report sequence status)
            symbol: Standardized 6-digit stock code
            years_used: Actual number of annual report years used
            coverage: Coverage information (the structure is the same as get_historical_financial_annual_series)
            trend: Capital efficiency trends [{"year": ..., "report_period": ..., "roe": ...,
                  "roa": ..., "roic": ..., "asset_turnover": ..., "equity_multiplier": ...,
                  "total_assets": ..., "total_equity": ...}, ...]
            summary: Summary statistics — roe, roa, roic, asset_turnover, equity_multiplier
                   (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            warnings: Warning message list
    """
    series = get_historical_financial_annual_series(symbol, years=years, source=source)
    records = series.get("records") or []
    trend: List[Dict[str, Any]] = []
    previous_assets: Optional[float] = None
    for item in records:
        revenue = item.get("revenue")
        total_assets = item.get("total_assets")
        total_equity = item.get("total_equity")
        avg_assets = mean([value for value in (total_assets, previous_assets) if value is not None]) if previous_assets is not None or total_assets is not None else None
        asset_turnover = item.get("asset_turnover") or _safe_div(revenue, avg_assets)
        equity_multiplier = item.get("equity_multiplier") or _safe_div(total_assets, total_equity)
        trend.append({
            "year": item.get("year"),
            "report_period": item.get("report_period"),
            "roe": item.get("roe"),
            "roa": item.get("roa"),
            "roic": item.get("roic"),
            "asset_turnover": asset_turnover,
            "equity_multiplier": equity_multiplier,
            "total_assets": total_assets,
            "total_equity": total_equity,
        })
        if total_assets is not None:
            previous_assets = total_assets
    return {
        "status": series.get("status"),
        "symbol": series.get("symbol"),
        "years_used": len(trend),
        "coverage": series.get("coverage"),
        "trend": trend,
        "summary": {
            "roe": _series_stats([item.get("roe") for item in trend]),
            "roa": _series_stats([item.get("roa") for item in trend]),
            "roic": _series_stats([item.get("roic") for item in trend]),
            "asset_turnover": _series_stats([item.get("asset_turnover") for item in trend]),
            "equity_multiplier": _series_stats([item.get("equity_multiplier") for item in trend]),
        },
        "warnings": list(series.get("warnings") or []),
    }


def get_growth_quality_metrics(symbol: str, years: int = 10, source: Optional[str] = None) -> Dict[str, Any]:
    """Returns the growth quality indicator.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Number of annual report years requested (default 10, will be truncated to [1, 15]) 
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" (Inherit annual report sequence status)
            symbol: Standardized 6-digit stock code
            years_used: Actual number of annual report years used
            coverage: Coverage information (the structure is the same as get_historical_financial_annual_series)
            cagr: compound growth rate — revenue(Revenue CAGR), net_profit(net profit CAGR),
                  operating_cashflow(operating cash flow CAGR), free_cashflow(free cash flow CAGR)
            annual_growth: Year-on-year growth rate [{"year": ..., "report_period": ...,
                  "revenue_growth": ..., "net_profit_growth": ...,
                  "operating_cashflow_growth": ..., "free_cashflow_growth": ...}, ...] (In ascending order by year)
            growth_stability: Growth stability statistics — revenue_growth, net_profit_growth,
                  operating_cashflow_growth, free_cashflow_growth
                   (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            quality_flags: quality mark — revenue_positive_year_ratio(Proportion of years with positive revenue growth),
                  profit_positive_year_ratio(Proportion of years with positive net profit growth),
                  fcf_positive_year_ratio(Proportion of years with positive free cash flow growth),
                  profit_growth_above_revenue_ratio(Proportion of years in which profit growth rate is higher than revenue growth rate)
            warnings: Warning message list
    """
    series = get_historical_financial_annual_series(symbol, years=years, source=source)
    records = series.get("records") or []
    chronological = list(reversed(records))
    annual_growth: List[Dict[str, Any]] = []
    for index in range(1, len(chronological)):
        previous = chronological[index - 1]
        current = chronological[index]
        annual_growth.append({
            "year": current.get("year"),
            "report_period": current.get("report_period"),
            "revenue_growth": _growth_rate(current.get("revenue"), previous.get("revenue")),
            "net_profit_growth": _growth_rate(current.get("net_profit"), previous.get("net_profit")),
            "operating_cashflow_growth": _growth_rate(current.get("operating_cashflow"), previous.get("operating_cashflow")),
            "free_cashflow_growth": _growth_rate(current.get("free_cashflow"), previous.get("free_cashflow")),
        })
    latest = chronological[-1] if chronological else {}
    earliest = chronological[0] if chronological else {}
    periods = max(0, len(chronological) - 1)
    revenue_growth = [item.get("revenue_growth") for item in annual_growth]
    profit_growth = [item.get("net_profit_growth") for item in annual_growth]
    fcf_growth = [item.get("free_cashflow_growth") for item in annual_growth]
    quality_flags = {
        "revenue_positive_year_ratio": _positive_ratio(revenue_growth),
        "profit_positive_year_ratio": _positive_ratio(profit_growth),
        "fcf_positive_year_ratio": _positive_ratio(fcf_growth),
        "profit_growth_above_revenue_ratio": _positive_ratio([
            (p - r) if p is not None and r is not None else None
            for p, r in zip(profit_growth, revenue_growth)
        ]),
    }
    return {
        "status": series.get("status"),
        "symbol": series.get("symbol"),
        "years_used": len(records),
        "coverage": series.get("coverage"),
        "cagr": {
            "revenue": _cagr(latest.get("revenue"), earliest.get("revenue"), periods),
            "net_profit": _cagr(latest.get("net_profit"), earliest.get("net_profit"), periods),
            "operating_cashflow": _cagr(latest.get("operating_cashflow"), earliest.get("operating_cashflow"), periods),
            "free_cashflow": _cagr(latest.get("free_cashflow"), earliest.get("free_cashflow"), periods),
        },
        "annual_growth": annual_growth,
        "growth_stability": {
            "revenue_growth": _series_stats(revenue_growth),
            "net_profit_growth": _series_stats(profit_growth),
            "operating_cashflow_growth": _series_stats([item.get("operating_cashflow_growth") for item in annual_growth]),
            "free_cashflow_growth": _series_stats(fcf_growth),
        },
        "quality_flags": quality_flags,
        "warnings": list(series.get("warnings") or []),
    }


def get_single_stock_risk_profile(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "daily",
    limit: int = 1000,
) -> Dict[str, Any]:
    """Returns a single stock price risk profile.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), if None, the default is the last 3 years
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        period: cycle: "daily" (default)| "weekly" | "monthly"
        limit: Maximum number of samples (default 1000, will be truncated to [1, 3000]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "insufficient_data" (Number of samples >= 20 only success)
            symbol: Standardized 6-digit stock code
            period: Actual usage period
            window: time window — start(start date), end(Deadline)
            metrics: risk indicators — sample_count(Number of samples), average_return(average rate of return),
                     median_return(Median rate of return), best_return(Best rate of return),
                     best_return_pct(Best rate of return%), worst_return(Worst rate of return),
                     worst_return_pct(Worst rate of return%), positive_day_ratio(Proportion of rising days),
                     negative_day_ratio(Proportion of falling days), downside_volatility(downside volatility),
                     downside_volatility_pct(downside volatility%), annualized_volatility(annualized volatility),
                     max_drawdown(maximum drawdown), max_drawdown_start(Retracement starting point),
                     max_drawdown_end(Retracement end point)
            components: Subcomponent status — return_series_status(return series status),
                     volatility_status(volatility status), drawdown_status(retracement status)
            warnings: Warning information list (merged subcomponent warnings)
    """
    returns = get_return_series(symbol, start_date=start_date, end_date=end_date, period=period, limit=limit)
    volatility = get_volatility_metrics(symbol, start_date=start_date, end_date=end_date, period=period, limit=limit)
    drawdown = get_drawdown_metrics(symbol, start_date=start_date, end_date=end_date, period=period, limit=limit)
    values = [item.get("return") for item in returns.get("records", []) if item.get("return") is not None]
    valid = [float(value) for value in values]
    downside = [value for value in valid if value < 0]
    best = max(valid) if valid else None
    worst = min(valid) if valid else None
    positive_days = sum(1 for value in valid if value > 0)
    negative_days = sum(1 for value in valid if value < 0)
    return {
        "status": "success" if len(valid) >= 20 else "insufficient_data",
        "symbol": returns.get("symbol"),
        "period": period,
        "window": returns.get("window"),
        "metrics": {
            "sample_count": len(valid),
            "average_return": mean(valid) if valid else None,
            "median_return": median(valid) if valid else None,
            "best_return": best,
            "best_return_pct": best * 100 if best is not None else None,
            "worst_return": worst,
            "worst_return_pct": worst * 100 if worst is not None else None,
            "positive_day_ratio": positive_days / len(valid) if valid else None,
            "negative_day_ratio": negative_days / len(valid) if valid else None,
            "downside_volatility": pstdev(downside) if len(downside) > 1 else None,
            "downside_volatility_pct": pstdev(downside) * 100 if len(downside) > 1 else None,
            "annualized_volatility": (volatility.get("metrics") or {}).get("annualized_volatility"),
            "max_drawdown": (drawdown.get("metrics") or {}).get("max_drawdown"),
            "max_drawdown_start": (drawdown.get("metrics") or {}).get("max_drawdown_start"),
            "max_drawdown_end": (drawdown.get("metrics") or {}).get("max_drawdown_end"),
        },
        "components": {
            "return_series_status": returns.get("status"),
            "volatility_status": volatility.get("status"),
            "drawdown_status": drawdown.get("status"),
        },
        "warnings": list(returns.get("warnings") or []) + list(volatility.get("warnings") or []) + list(drawdown.get("warnings") or []),
    }


def get_peer_group(symbol: str, limit: int = 50) -> Dict[str, Any]:
    """Returns the standardized peer sample group.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        limit: Maximum number of peer samples (default 50, will be truncated to [1, 300]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            industry: Industry (None if unrecognized)
            peers: Peer sample list [{"symbol": ..., "name": ..., "industry": ...,
                  "total_mv": ..., "pe_ttm": ..., "pb": ..., "roe": ...,
                  "data_source": ...}, ...]
            coverage: Coverage information — peer_count(Number of peers), limit(request cap)
            warnings: Warning message list
    """
    master = get_security_master(symbol)
    industry = master.get("industry")
    warnings: List[str] = []
    if not industry:
        return {"status": "no_data", "symbol": master.get("symbol"), "industry": None, "peers": [], "coverage": {"peer_count": 0}, "warnings": ["Unable to identify industry and build peer group."]}
    peers = get_industry_peer_basic_info(str(industry), exclude_symbol=master.get("symbol"), limit=max(1, min(int(limit or 50), 300)))
    normalized_peers = []
    for item in peers:
        normalized_peers.append({
            "symbol": item.get("symbol") or item.get("code"),
            "name": item.get("name"),
            "industry": item.get("industry"),
            "total_mv": _pick_number(item, "total_mv", "market_cap", "market_value"),
            "pe_ttm": _pick_number(item, "pe_ttm", "pe"),
            "pb": _pick_number(item, "pb", "pb_mrq"),
            "roe": _pick_number(item, "roe"),
            "data_source": item.get("source") or item.get("data_source"),
        })
    if not normalized_peers:
        warnings.append("Peer sample not found.")
    return {
        "status": "success" if normalized_peers else "no_data",
        "symbol": master.get("symbol"),
        "industry": industry,
        "peers": normalized_peers,
        "coverage": {"peer_count": len(normalized_peers), "limit": limit},
        "warnings": warnings,
    }


def get_industry_market_performance(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    lookback_days: int = 20,
    peer_limit: int = 100,
) -> Dict[str, Any]:
    """Returns structured industry market performance.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Starting date (YYYY-MM-DD), default when None lookback_days*2 days ago
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        lookback_days: Number of days to look back (default 20)
        peer_limit: Maximum number of peer samples (default 100, will be truncated to [1, 200]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            industry: Industry
            window: time window — start(start date), end(Deadline), lookback_days(Lookback days)
            summary: Aggregated information — peer_count(Number of peers), industry_return(Industry average revenue),
                     industry_return_pct(Industry average revenue%), industry_return_median(Industry median income),
                     target_return(target stock returns), target_return_pct(target stock returns%),
                     target_return_percentile(Target stock return quantile 0-100),
                     rising_ratio(Proportion of rising stocks), latest_total_amount(Latest total transaction volume),
                     matched_moneyflow_count(Number of matching fund flow records)
            top_gainers: before increase 10 [{"symbol": ..., "name": ..., "first_date": ...,
                       "latest_date": ..., "first_close": ..., "latest_close": ...,
                       "period_return": ..., "period_return_pct": ...,
                       "latest_pct_chg": ..., "amount": ...}, ...]
            top_losers: Top 10 losers (same structure as top_gainers)
            moneyflow: Industry capital flow [{"trade_date": ..., "industry": ..., "pct_change": ...,
                     "net_amount": ..., "net_buy_amount": ..., "net_sell_amount": ...,
                     "company_num": ...}, ...] (Up to 20 items)
            coverage: Coverage information — peer_price_sample_count(Number of price samples), peer_limit(upper limit),
                     moneyflow_sample_count(Number of fund flow records)
            warnings: Warning message list
    """
    master = get_security_master(symbol)
    industry = master.get("industry")
    normalized_symbol = master.get("symbol") or _normalize_symbol(symbol)
    end = end_date or _today()
    start = start_date or _days_ago(max(1, int(lookback_days or 20) * 2))
    peer_group = get_peer_group(normalized_symbol, limit=peer_limit)
    peer_symbols = [peer.get("symbol") for peer in peer_group.get("peers") or [] if peer.get("symbol")]
    rows: List[Dict[str, Any]] = []
    for peer_symbol in peer_symbols[:max(1, min(int(peer_limit or 100), 200))]:
        price = get_adjusted_price_series(str(peer_symbol), start_date=start, end_date=end, limit=max(10, int(lookback_days or 20) + 10))
        records = price.get("records") or []
        if len(records) < 2:
            continue
        first = records[0]
        latest = records[-1]
        first_close = _safe_float(first.get("close"))
        latest_close = _safe_float(latest.get("close"))
        pct_change = _safe_div(latest_close - first_close, first_close) if first_close and latest_close is not None else None
        latest_pct = _safe_float(latest.get("pct_chg"))
        rows.append({
            "symbol": peer_symbol,
            "name": next((peer.get("name") for peer in peer_group.get("peers") or [] if peer.get("symbol") == peer_symbol), None),
            "first_date": first.get("trade_date"),
            "latest_date": latest.get("trade_date"),
            "first_close": first_close,
            "latest_close": latest_close,
            "period_return": pct_change,
            "period_return_pct": pct_change * 100 if pct_change is not None else None,
            "latest_pct_chg": latest_pct,
            "amount": _safe_float(latest.get("amount")),
        })
    valid_returns = [row.get("period_return") for row in rows if row.get("period_return") is not None]
    target_price = get_adjusted_price_series(normalized_symbol, start_date=start, end_date=end, limit=max(10, int(lookback_days or 20) + 10))
    target_records = target_price.get("records") or []
    target_return = None
    if len(target_records) >= 2:
        first_close = _safe_float(target_records[0].get("close"))
        latest_close = _safe_float(target_records[-1].get("close"))
        target_return = _safe_div(latest_close - first_close, first_close) if first_close and latest_close is not None else None
    moneyflow_rows = _load_tushare_industry_moneyflow_rows(start, end, 300)
    matched_flow = []
    if industry:
        for row in moneyflow_rows:
            name = str(row.get("industry") or row.get("name") or "")
            if str(industry) in name or name in str(industry):
                matched_flow.append({
                    "trade_date": _normalize_date(row.get("trade_date") or row.get("date")),
                    "industry": name,
                    "pct_change": _pick_number(row, "pct_change", "pct_chg"),
                    "net_amount": _pick_number(row, "net_amount"),
                    "net_buy_amount": _pick_number(row, "net_buy_amount"),
                    "net_sell_amount": _pick_number(row, "net_sell_amount"),
                    "company_num": _pick_number(row, "company_num"),
                })
    warnings = list(peer_group.get("warnings") or [])
    if not rows:
        warnings.append("Failure to calculate industry market performance from peer price series.")
    if not matched_flow:
        warnings.append("Tushare industry capital flow is not matched, and the capital flow field is empty.")
    return {
        "status": "success" if rows else "no_data",
        "symbol": normalized_symbol,
        "industry": industry,
        "window": {"start": start, "end": end, "lookback_days": lookback_days},
        "summary": {
            "peer_count": len(rows),
            "industry_return": mean(valid_returns) if valid_returns else None,
            "industry_return_pct": mean(valid_returns) * 100 if valid_returns else None,
            "industry_return_median": median(valid_returns) if valid_returns else None,
            "target_return": target_return,
            "target_return_pct": target_return * 100 if target_return is not None else None,
            "target_return_percentile": _percentile_rank_numeric(valid_returns, target_return),
            "rising_ratio": _positive_ratio(valid_returns),
            "latest_total_amount": sum(row.get("amount") or 0 for row in rows),
            "matched_moneyflow_count": len(matched_flow),
        },
        "top_gainers": sorted(rows, key=lambda item: item.get("period_return") if item.get("period_return") is not None else -999, reverse=True)[:10],
        "top_losers": sorted(rows, key=lambda item: item.get("period_return") if item.get("period_return") is not None else 999)[:10],
        "moneyflow": matched_flow[:20],
        "coverage": {"peer_price_sample_count": len(rows), "peer_limit": peer_limit, "moneyflow_sample_count": len(matched_flow)},
        "warnings": warnings,
    }


def get_peer_relative_growth(symbol: str, metrics: Optional[List[str]] = None, years: int = 5, peer_limit: int = 50) -> Dict[str, Any]:
    """Returns the relative quantile of the peer growth indicator.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        metrics: List of growth indicators, supported "revenue" / "revenue_cagr" / "net_profit" /
                  "net_profit_cagr" / "operating_cashflow" / "operating_cashflow_cagr" /
                  "free_cashflow" / "free_cashflow_cagr"; Defaults to all 4 when None CAGR
        years: Number of annual report years requested (default 5)
        peer_limit: Maximum number of peer samples (default 50, will be truncated to [1, 100]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "partial_or_no_data"
            symbol: Standardized 6-digit stock code
            industry: Industry
            years: Actual number of annual report years used
            metrics: Relative ranking of each indicator {metric_name: {current_value, current_value_pct,
                     peer_count, peer_average, peer_median, peer_percentile}}
            samples: Sample list [{"symbol": ..., "is_target": ..., "revenue_cagr": ...,
                  "net_profit_cagr": ..., "operating_cashflow_cagr": ...,
                  "free_cashflow_cagr": ..., "years_used": ..., "status": ...}, ...]
            coverage: Coverage information — sample_count(Number of samples), peer_limit(upper limit)
            warnings: Warning message list
    """
    requested = [_normalize_metric_key(item) for item in (metrics or ["revenue_cagr", "net_profit_cagr", "operating_cashflow_cagr", "free_cashflow_cagr"]) if str(item).strip()]
    metric_alias = {
        "revenue": "revenue_cagr",
        "revenue_cagr": "revenue_cagr",
        "net_profit": "net_profit_cagr",
        "profit_cagr": "net_profit_cagr",
        "net_profit_cagr": "net_profit_cagr",
        "operating_cashflow": "operating_cashflow_cagr",
        "operating_cashflow_cagr": "operating_cashflow_cagr",
        "free_cashflow": "free_cashflow_cagr",
        "free_cashflow_cagr": "free_cashflow_cagr",
    }
    normalized_metrics = [metric_alias.get(metric, metric) for metric in requested]
    master = get_security_master(symbol)
    normalized_symbol = master.get("symbol") or _normalize_symbol(symbol)
    peer_group = get_peer_group(normalized_symbol, limit=peer_limit)
    peer_symbols = [normalized_symbol] + [peer.get("symbol") for peer in peer_group.get("peers") or [] if peer.get("symbol")]
    samples: List[Dict[str, Any]] = []
    for peer_symbol in peer_symbols[:max(1, min(int(peer_limit or 50) + 1, 101))]:
        growth = get_growth_quality_metrics(str(peer_symbol), years=years)
        cagr = growth.get("cagr") or {}
        row = {
            "symbol": peer_symbol,
            "is_target": peer_symbol == normalized_symbol,
            "revenue_cagr": cagr.get("revenue"),
            "net_profit_cagr": cagr.get("net_profit"),
            "operating_cashflow_cagr": cagr.get("operating_cashflow"),
            "free_cashflow_cagr": cagr.get("free_cashflow"),
            "years_used": growth.get("years_used"),
            "status": growth.get("status"),
        }
        samples.append(row)
    target = next((row for row in samples if row.get("is_target")), {})
    result: Dict[str, Any] = {}
    warnings = list(peer_group.get("warnings") or [])
    for metric in normalized_metrics:
        values = [_safe_float(row.get(metric)) for row in samples if not row.get("is_target")]
        valid = [value for value in values if value is not None]
        current = _safe_float(target.get(metric))
        result[metric] = {
            "current_value": current,
            "current_value_pct": current * 100 if current is not None else None,
            "peer_count": len(valid),
            "peer_average": mean(valid) if valid else None,
            "peer_median": median(valid) if valid else None,
            "peer_percentile": _percentile_rank_numeric(valid, current),
        }
        if not valid:
            warnings.append(f"{metric} There is a lack of effective peer growth samples.")
    return {
        "status": "success" if any(item.get("peer_count") for item in result.values()) else "partial_or_no_data",
        "symbol": normalized_symbol,
        "industry": peer_group.get("industry"),
        "years": years,
        "metrics": result,
        "samples": samples,
        "coverage": {"sample_count": len(samples), "peer_limit": peer_limit},
        "warnings": warnings,
    }


def get_peer_relative_valuation(symbol: str, metrics: Optional[List[str]] = None, peer_limit: int = 200) -> Dict[str, Any]:
    """Returns peer relative valuation quantiles and industry statistics.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        metrics: List of valuation indicators, supported "pe" / "pe_ttm" / "pb" / "pb_mrq" / "ps" / "ps_ttm"; 
                  Default when None ["pe", "pb", "ps"]
        peer_limit: Maximum number of peer samples (default 200)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            industry: Industry (None if unrecognized)
            metrics: Relative quantile of each valuation indicator {metric_name: {current_value, industry_average,
                     industry_median, industry_min, industry_max, peer_count, peer_percentile}}
            warnings: Warning message list
    """
    requested = [str(item).lower() for item in (metrics or ["pe", "pb", "ps"]) if str(item).strip()]
    master = get_security_master(symbol)
    snapshot = get_current_valuation_snapshot(symbol)
    industry = master.get("industry")
    result: Dict[str, Any] = {}
    warnings: List[str] = []
    if not industry:
        return {"status": "no_data", "symbol": master.get("symbol"), "industry": None, "metrics": {}, "warnings": ["The industry cannot be identified and peer valuation cannot be calculated."]}
    current_metrics = snapshot.get("metrics") or {}
    for metric in requested:
        metric_key = "pe" if metric in {"pe", "pe_ttm"} else "pb" if metric in {"pb", "pb_mrq"} else "ps" if metric in {"ps", "ps_ttm"} else metric
        stats = summarize_industry_valuation(str(industry), metric=metric_key, exclude_symbol=master.get("symbol"), limit=peer_limit)
        current_value = _safe_float(current_metrics.get(metric_key) or current_metrics.get(f"{metric_key}_ttm") or current_metrics.get(f"{metric_key}_mrq"))
        samples = [item.get(metric_key) for item in stats.get("samples", []) if _safe_float(item.get(metric_key)) is not None]
        percentile = _percentile_rank([float(value) for value in samples], current_value) if current_value is not None and samples else None
        result[metric_key] = {
            "current_value": current_value,
            "industry_average": stats.get("average"),
            "industry_median": stats.get("median"),
            "industry_min": stats.get("min"),
            "industry_max": stats.get("max"),
            "peer_count": stats.get("count"),
            "peer_percentile": percentile,
        }
        if not stats.get("count"):
            warnings.append(f"{metric_key} Lack of valid peer samples.")
    return {
        "status": "success" if result else "no_data",
        "symbol": master.get("symbol"),
        "industry": industry,
        "metrics": result,
        "warnings": warnings,
    }


def get_peer_relative_quality(symbol: str, metrics: Optional[List[str]] = None, peer_limit: int = 200) -> Dict[str, Any]:
    """Returns the relative position of peer quality indicators.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        metrics: List of quality indicators, supported "pe" / "pe_ttm" / "pb" / "roe"; 
                  Default when None ["roe", "pb", "pe_ttm"]
        peer_limit: Maximum number of peer samples (default 200)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "partial_or_no_data"
            symbol: Standardized 6-digit stock code
            industry: Industry
            metrics: Relative ranking of each quality indicator {metric_name: {current_value, peer_count,
                     peer_average, peer_median, peer_percentile}}
            warnings: Warning message list
    """
    requested = [str(item).lower() for item in (metrics or ["roe", "pb", "pe_ttm"]) if str(item).strip()]
    peer_group = get_peer_group(symbol, limit=peer_limit)
    master = get_security_master(symbol)
    basic = get_stock_basic_info(master.get("symbol") or "") or {}
    peers = peer_group.get("peers") or []
    results: Dict[str, Any] = {}
    warnings = list(peer_group.get("warnings") or [])
    field_alias = {"pe": "pe_ttm", "pe_ttm": "pe_ttm", "pb": "pb", "roe": "roe"}
    for metric in requested:
        field = field_alias.get(metric, metric)
        current = _pick_number(basic, field, metric)
        values = [_safe_float(peer.get(field)) for peer in peers]
        valid = [value for value in values if value is not None]
        results[metric] = {
            "current_value": current,
            "peer_count": len(valid),
            "peer_average": mean(valid) if valid else None,
            "peer_median": median(valid) if valid else None,
            "peer_percentile": _percentile_rank(valid, current) if current is not None and valid else None,
        }
        if not valid:
            warnings.append(f"{metric} Lack of valid peer samples.")
    return {
        "status": "success" if any(item.get("peer_count") for item in results.values()) else "partial_or_no_data",
        "symbol": master.get("symbol"),
        "industry": peer_group.get("industry"),
        "metrics": results,
        "warnings": warnings,
    }


def get_industry_fundamental_summary(symbol: str, peer_limit: int = 100) -> Dict[str, Any]:
    """Returns the fundamental sample statistics of the industry where the target stock is located.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        peer_limit: Maximum number of peer samples (default 100)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            industry: Industry
            coverage: Coverage information — peer_count(Number of peers), peer_limit(upper limit)
            metrics: Industry fundamental statistics — total_mv(Total market capitalization), pe_ttm(P/E ratio),
                     pb(price to book ratio), roe(ROE)
                      (Each statistic contains count/mean/median/min/max/stddev/coefficient_of_variation)
            top_market_cap_peers: The top 10 peers by market capitalization (the structure is the same as the peers element of get_peer_group)
            warnings: Warning message list (additional prompt when there are less than 5 peer samples)
    """
    peer_group = get_peer_group(symbol, limit=peer_limit)
    peers = peer_group.get("peers") or []
    requested_fields = ["total_mv", "pe_ttm", "pb", "roe"]
    metrics: Dict[str, Any] = {}
    for field in requested_fields:
        values = [_safe_float(peer.get(field)) for peer in peers]
        valid = [value for value in values if value is not None and (field not in {"pe_ttm", "pb"} or value > 0)]
        metrics[field] = _series_stats(valid)
    warnings = list(peer_group.get("warnings") or [])
    if len(peers) < 5:
        warnings.append("There are less than 5 peer samples, and the statistical reference value of industry fundamentals is limited.")
    return {
        "status": "success" if peers else "no_data",
        "symbol": peer_group.get("symbol"),
        "industry": peer_group.get("industry"),
        "coverage": {"peer_count": len(peers), "peer_limit": peer_limit},
        "metrics": metrics,
        "top_market_cap_peers": sorted(peers, key=lambda item: _safe_float(item.get("total_mv")) or 0, reverse=True)[:10],
        "warnings": warnings,
    }


def get_capital_flow_series(symbol: str, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 120) -> Dict[str, Any]:
    """Returns the individual stock capital flow sequence. Currently, priority is given to reading the local fund flow collection; no_data is explicitly returned when there is no data."""
    normalized_symbol = _normalize_symbol(symbol)
    end = end_date or _today()
    start = start_date or _days_ago(180)
    start_digits = _date_digits(start)
    end_digits = _date_digits(end)
    start_dash = _normalize_date(start)
    end_dash = _normalize_date(end)
    collection_names = ["stock_capital_flow", "stock_fund_flow", "stock_moneyflow", "capital_flow_daily"]
    records: List[Dict[str, Any]] = []
    used_collection: Optional[str] = None
    used_source = "local"
    db = _get_db()
    for collection_name in collection_names:
        try:
            col = db[collection_name]
            query = {
                "$and": [
                    {"$or": [{"symbol": normalized_symbol}, {"code": normalized_symbol}, {"ts_code": {"$regex": normalized_symbol}}]},
                    {"$or": [
                        {"trade_date": {"$gte": start_digits, "$lte": end_digits}},
                        {"trade_date": {"$gte": start_dash, "$lte": end_dash}},
                        {"date": {"$gte": start_digits, "$lte": end_digits}},
                        {"date": {"$gte": start_dash, "$lte": end_dash}},
                    ]},
                ]
            }
            rows = list(col.find(query, {"_id": 0}).sort("trade_date", 1).limit(max(1, min(int(limit or 120), 1000))))
            if rows:
                records = rows
                used_collection = collection_name
                break
        except Exception:
            continue
    if not records:
        records = _load_tushare_moneyflow_rows(normalized_symbol, start, end, limit)
        if records:
            used_source = "tushare"
    normalized_records: List[Dict[str, Any]] = []
    for row in records:
        normalized_records.append({
            "trade_date": _normalize_date(row.get("trade_date") or row.get("date")),
            "main_net_inflow": _pick_number(row, "main_net_inflow", "net_mf_amount", "net_amount", "main_net_amount"),
            "main_net_inflow_pct": _pick_number(row, "main_net_inflow_pct", "net_mf_pct", "net_pct", "net_amount_rate"),
            "extra_large_net_inflow": _pick_number(row, "extra_large_net_inflow", "buy_elg_amount", "elg_net_amount"),
            "large_net_inflow": _pick_number(row, "large_net_inflow", "buy_lg_amount", "lg_net_amount"),
            "medium_net_inflow": _pick_number(row, "medium_net_inflow", "buy_md_amount", "md_net_amount"),
            "small_net_inflow": _pick_number(row, "small_net_inflow", "buy_sm_amount", "sm_net_amount"),
            "amount": _pick_number(row, "amount", "turnover"),
            "data_source": row.get("source") or row.get("data_source") or used_source,
        })
    valid_main = [item.get("main_net_inflow") for item in normalized_records if item.get("main_net_inflow") is not None]
    return {
        "status": "success" if normalized_records else "no_data",
        "symbol": normalized_symbol,
        "window": {"start": start, "end": end},
        "data_source": used_collection or used_source,
        "records": normalized_records,
        "summary": {
            "main_net_inflow": _series_stats(valid_main),
            "positive_flow_ratio": _positive_ratio(valid_main),
        },
        "coverage": {"sample_count": len(normalized_records)},
        "warnings": [] if normalized_records else ["The individual stock money flow sequence was not found either locally or by Tushare; please check the local sync or Tushare moneyflow_ths permissions."],
    }


def get_chip_distribution_context(symbol: str, trade_date: Optional[str] = None) -> Dict[str, Any]:
    """Returns the structured chip distribution context.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        trade_date: Transaction date (YYYY-MM-DD), defaults to today when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data" | "error"
            symbol: Standardized 6-digit stock code
            trade_date: Actual transaction date used
            message: Error message (only status="error" exist)
            data_source: Data source name
            metrics: Chip indicator — profit_ratio(Profit ratio 0-1), avg_cost(average cost),
                     cost_90_low(90% cost lower edge), cost_90_high(90% cost upper edge),
                     cost_90_width(90% cost width), concentration_90(90% Concentration),
                     cost_70_low(70% cost lower edge), cost_70_high(70% cost upper edge),
                     cost_70_width(70% cost width), concentration_70(70% Concentration)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    target_date = trade_date or _today()
    try:
        from core.tools.chip_distribution_tools import get_chip_distribution_akshare, get_chip_distribution_tushare
        data = get_chip_distribution_akshare(normalized_symbol, target_date) or get_chip_distribution_tushare(normalized_symbol, target_date)
    except Exception as exc:
        return {
            "status": "error",
            "symbol": normalized_symbol,
            "trade_date": target_date,
            "message": str(exc),
            "warnings": ["The chip distribution data source call failed."],
        }
    if not data:
        return {
            "status": "no_data",
            "symbol": normalized_symbol,
            "trade_date": target_date,
            "metrics": {},
            "warnings": ["No chip distribution data was obtained; this data relies on the external AkShare/Tushare interface."],
        }
    avg_cost = _safe_float(data.get("avg_cost"))
    cost_90_low = _safe_float(data.get("cost_90_low"))
    cost_90_high = _safe_float(data.get("cost_90_high"))
    cost_70_low = _safe_float(data.get("cost_70_low"))
    cost_70_high = _safe_float(data.get("cost_70_high"))
    profit_ratio = _safe_float(data.get("profit_ratio"))
    if profit_ratio is not None and profit_ratio > 1:
        profit_ratio = profit_ratio / 100
    return {
        "status": "success",
        "symbol": normalized_symbol,
        "trade_date": _normalize_date(data.get("date") or target_date),
        "data_source": data.get("source"),
        "metrics": {
            "profit_ratio": profit_ratio,
            "avg_cost": avg_cost,
            "cost_90_low": cost_90_low,
            "cost_90_high": cost_90_high,
            "cost_90_width": cost_90_high - cost_90_low if cost_90_high is not None and cost_90_low is not None else None,
            "concentration_90": _safe_float(data.get("concentration_90")),
            "cost_70_low": cost_70_low,
            "cost_70_high": cost_70_high,
            "cost_70_width": cost_70_high - cost_70_low if cost_70_high is not None and cost_70_low is not None else None,
            "concentration_70": _safe_float(data.get("concentration_70")),
        },
        "warnings": [],
    }


def get_company_event_timeline(symbol: str, lookback_days: int = 365, event_types: Optional[List[str]] = None, limit: int = 100) -> Dict[str, Any]:
    """Return to the first version of the structured timeline of formal announcements/regulatory events.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        lookback_days: Number of days to look back (default 365)
        event_types: Event type filter list, support "financial_report" / "dividend_plan" /
                  "shareholder_reduction" / "shareholder_increase" / "pledge" /
                  "litigation" / "regulatory_inquiry" / "regulatory_penalty" /
                  "major_restructuring" / "performance_forecast" / "management_change"；
                  Returns all if None
        limit: Maximum number of events (default 100, will be truncated to [1, 300]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            window: time window — start(start date), end(Deadline), lookback_days(Lookback days)
            data_source: Data source collection name (None if there is no data)
            events: event list [{"event_date": ..., "publish_date": ..., "event_types": [...],
                  "title": ..., "summary": ..., "source": ..., "url": ...,
                  "severity": ...}, ...] (severity 1-3, 3 (the most serious)
            summary: Aggregated information — event_count(total number of events), type_counts(Count of various types dict),
                  high_severity_count(Number of high severity events)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    end = _today()
    start = _days_ago(lookback_days)
    start_digits = _date_digits(start)
    end_digits = _date_digits(end)
    query = {
        "$and": [
            {"$or": [{"symbol": normalized_symbol}, {"code": normalized_symbol}, {"ts_code": {"$regex": normalized_symbol}}]},
            {"$or": [
                {"publish_date": {"$gte": start_digits, "$lte": end_digits}},
                {"publish_date": {"$gte": start, "$lte": end}},
                {"ann_date": {"$gte": start_digits, "$lte": end_digits}},
                {"ann_date": {"$gte": start, "$lte": end}},
                {"event_date": {"$gte": start_digits, "$lte": end_digits}},
                {"event_date": {"$gte": start, "$lte": end}},
            ]},
        ]
    }
    rows, source_collection = _read_local_collection_rows(
        ["company_announcements", "stock_announcements", "regulatory_events", "company_events"],
        query,
        limit=max(limit * 3, 100),
        sort_field="publish_date",
    )
    if not rows:
        news = get_stock_news_by_date_range(normalized_symbol, start, end, limit=max(1, min(int(limit or 100), 200)))
        rows = [row for row in news if any(word in " ".join(str(row.get(field) or "") for field in ("title", "summary", "content", "category")) for word in ["Announcement", "supervision", "Inquiry letter", "warning letter", "punishment", "Reduce holdings", "pledge", "Reorganization", "litigation", "dividend"])]
        source_collection = "stock_news_proxy" if rows else None

    event_rules = {
        "financial_report": ["annual report", "quarterly report", "semi-annual report", "financial report"],
        "dividend_plan": ["dividend", "dividend", "Equity distribution"],
        "shareholder_reduction": ["Reduce holdings", "Passive reduction"],
        "shareholder_increase": ["Overweight"],
        "pledge": ["pledge", "Freeze"],
        "litigation": ["litigation", "Arbitration", "judgment"],
        "regulatory_inquiry": ["Inquiry letter", "Supervision letter"],
        "regulatory_penalty": ["punishment", "warning letter", "File a case", "Investigate"],
        "major_restructuring": ["Reorganization", "mergers and acquisitions", "asset sale"],
        "performance_forecast": ["Performance forecast", "Pre-loss", "performance revision"],
        "management_change": ["resign", "Resign", "Chairman", "general manager"],
    }
    requested = {_normalize_metric_key(item) for item in event_types or [] if str(item).strip()}
    events: List[Dict[str, Any]] = []
    for row in rows:
        text = " ".join(str(row.get(field) or "") for field in ("title", "summary", "content", "category", "event_type"))
        matched_types = [event_type for event_type, keywords in event_rules.items() if any(keyword in text for keyword in keywords)]
        explicit_type = _normalize_metric_key(row.get("event_type") or row.get("type") or "")
        if explicit_type and explicit_type not in matched_types:
            matched_types.append(explicit_type)
        if not matched_types:
            matched_types = ["other_announcement"]
        if requested and not any(item in requested for item in matched_types):
            continue
        severity = 1
        if any(item in matched_types for item in ["regulatory_penalty", "litigation"]):
            severity = 3
        elif any(item in matched_types for item in ["regulatory_inquiry", "shareholder_reduction", "pledge", "performance_forecast", "major_restructuring"]):
            severity = 2
        events.append({
            "event_date": _normalize_date(row.get("event_date") or row.get("publish_date") or row.get("ann_date") or row.get("publish_time") or row.get("pub_date")),
            "publish_date": _normalize_date(row.get("publish_date") or row.get("ann_date") or row.get("publish_time") or row.get("pub_date")),
            "event_types": matched_types,
            "title": row.get("title") or row.get("name"),
            "summary": row.get("summary") or row.get("content"),
            "source": row.get("source") or row.get("data_source") or source_collection,
            "url": row.get("url"),
            "severity": severity,
        })
    events.sort(key=lambda item: str(item.get("publish_date") or item.get("event_date") or ""), reverse=True)
    type_counts: Dict[str, int] = {}
    for item in events:
        for event_type in item.get("event_types") or []:
            type_counts[event_type] = type_counts.get(event_type, 0) + 1
    return {
        "status": "success" if events else "no_data",
        "symbol": normalized_symbol,
        "window": {"start": start, "end": end, "lookback_days": lookback_days},
        "data_source": source_collection,
        "events": events[:max(1, min(int(limit or 100), 300))],
        "summary": {"event_count": len(events), "type_counts": type_counts, "high_severity_count": sum(1 for item in events if item.get("severity", 0) >= 3)},
        "warnings": [] if events and source_collection != "stock_news_proxy" else (["Currently, a news agent is used to identify announcement/regulatory events. It is recommended to access the dedicated data source for official announcement in the future."] if events else ["No announcement/regulatory event data found."]),
    }


def get_business_segment_trend(symbol: str, years: int = 5, segment_type: str = "product") -> Dict[str, Any]:
    """Return to the first edition of Main Business Structural Trends.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Requested number of years (default 5, will be truncated to [1, 10]) 
        segment_type: Branch type: "product" (product, default)| "region" (region)| "all" (all)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            segment_type: Actual branch type used
            periods: Summary of segments for each period [{"report_period": ..., "segment_count": ...,
                  "total_segment_revenue": ..., "top_segments": [{"report_period": ...,
                  "year": ..., "segment_name": ..., "segment_type": ..., "revenue": ...,
                  "cost": ..., "gross_profit": ..., "gross_margin": ...,
                  "revenue_share": ..., "revenue_share_pct": ..., "source": ...}, ...],
                  "concentration": {"top1_share": ..., "top3_share": ..., "hhi": ...}}]
                   (In descending order of reporting period, up to 10 periods)
            coverage: Coverage information — period_count(Period), raw_segment_count(Original number of branch records)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    records = get_stock_financial_periods(normalized_symbol, source=None, limit=max(int(years or 5) * 6, 40))
    segments: List[Dict[str, Any]] = []
    for record in records:
        raw = record.get("raw_data") or {}
        candidates = record.get("main_business") or raw.get("main_business") or []
        if isinstance(candidates, dict):
            candidates = [candidates]
        for item in candidates or []:
            if not isinstance(item, dict):
                continue
            bz_item = str(item.get("bz_item") or item.get("item") or item.get("segment") or item.get("name") or "").strip()
            bz_type = str(item.get("bz_type") or item.get("type") or segment_type or "").lower()
            if segment_type and segment_type.lower() not in bz_type and bz_type and segment_type.lower() not in {"all", "All"}:
                if segment_type.lower() == "product" and "Products" not in bz_type and "product" not in bz_type:
                    continue
                if segment_type.lower() == "region" and "area" not in bz_type and "region" not in bz_type:
                    continue
            revenue = _pick_number(item, "bz_sales", "revenue", "sales")
            cost = _pick_number(item, "bz_cost", "cost")
            profit = _pick_number(item, "bz_profit", "profit", "gross_profit")
            if profit is None and revenue is not None and cost is not None:
                profit = revenue - cost
            segments.append({
                "report_period": str(item.get("end_date") or item.get("report_period") or record.get("report_period") or record.get("report_date") or ""),
                "year": _period_year(item.get("end_date") or item.get("report_period") or record.get("report_period") or record.get("report_date")),
                "segment_name": bz_item,
                "segment_type": bz_type or segment_type,
                "revenue": revenue,
                "cost": cost,
                "gross_profit": profit,
                "gross_margin": _pick_number(item, "bz_profit_rate", "gross_margin") or (_safe_div(profit, revenue) * 100 if profit is not None and revenue else None),
                "source": item.get("source") or record.get("source") or record.get("data_source"),
            })
    by_period: Dict[str, List[Dict[str, Any]]] = {}
    for item in segments:
        period = str(item.get("report_period") or "")
        if period:
            by_period.setdefault(period, []).append(item)
    period_summaries = []
    for period, items in sorted(by_period.items(), reverse=True)[:max(1, min(int(years or 5), 10))]:
        valid_revenue = [item.get("revenue") for item in items if item.get("revenue") is not None and item.get("revenue") > 0]
        total_revenue = sum(valid_revenue)
        enriched = []
        for item in items:
            share = _safe_div(item.get("revenue"), total_revenue) if total_revenue else None
            enriched.append({**item, "revenue_share": share, "revenue_share_pct": share * 100 if share is not None else None})
        enriched.sort(key=lambda item: item.get("revenue_share") or 0, reverse=True)
        shares = [item.get("revenue_share") for item in enriched if item.get("revenue_share") is not None]
        period_summaries.append({
            "report_period": period,
            "segment_count": len(enriched),
            "total_segment_revenue": total_revenue,
            "top_segments": enriched[:10],
            "concentration": {
                "top1_share": shares[0] if shares else None,
                "top3_share": sum(shares[:3]) if shares else None,
                "hhi": sum(value * value for value in shares) if shares else None,
            },
        })
    return {
        "status": "success" if period_summaries else "no_data",
        "symbol": normalized_symbol,
        "segment_type": segment_type,
        "periods": period_summaries,
        "coverage": {"period_count": len(period_summaries), "raw_segment_count": len(segments)},
        "warnings": [] if period_summaries else ["No main business segment data found; Tushare fina_mainbz or financial reporting segment data needs to be synchronized."],
    }


def get_shareholder_return_metrics(
    symbol: str, years: int = 5, allow_remote_fetch: bool = True
) -> Dict[str, Any]:
    """Return to the first edition of the Shareholder Return Metrics.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        years: Requested number of years (default 5)
        allow_remote_fetch: Whether to pull Tushare on-site when there is no local dividend details.
            Analysis-period tool calls (which the user has expected to take a long time) can remain True;
            Interactive interfaces (immediate response scenarios such as data inspection/factor preview) must pass False,
            Otherwise the external pull will be triggered for about 20 seconds each time when the local collection is always empty.

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            data_source: Data source name ("tushare" or local collection name)
            current_price: Current price used to calculate dividend yield
            records: Dividend record [{"end_date": ..., "ann_date": ..., "ex_date": ...,
                  "cash_div_tax": ..., "cash_div": ..., "div_proc": ...}, ...]
            annual: Yearly Aggregation [{"year": ..., "cash_dividend_per_share": ...,
                  "dividend_yield": ...}, ...] (In descending order of year)
            metrics: Shareholder Return Metrics — latest_cash_dividend_per_share(Latest dividend per share),
                     latest_dividend_yield(Latest dividend yield), latest_dividend_yield_pct(Latest dividend yield%),
                     average_cash_dividend_per_share(average dividend per share),
                     dividend_positive_years(Number of years with dividends),
                     dividend_continuity_ratio(Dividend continuity ratio),
                     fcf_positive_ratio(Free cash flow is positive)
            coverage: Coverage information — dividend_record_count(Number of dividend records),
                     annual_count(number of years), financial_years(Financial years)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    rows, source = _read_local_collection_rows(
        ["stock_dividend", "stock_dividends", "dividend_data"],
        {"$or": [{"symbol": normalized_symbol}, {"code": normalized_symbol}, {"ts_code": {"$regex": normalized_symbol}}]},
        limit=max(20, int(years or 5) * 4),
        sort_field="end_date",
    )
    if not rows and allow_remote_fetch:
        rows = _load_tushare_dividend_rows(normalized_symbol, max(20, int(years or 5) * 4))
        source = "tushare" if rows else None
    # Tushare The dividend table returns multiple stages (plan/approval/implementation of shareholders' meeting) for the same dividend event.
    # Each item comes with cash_div_tax. Without filtering, multiple stages of the same dividend distribution will be accumulated repeatedly.
    # As a result, the dividend per share and dividend rate are magnified several times (for example, Moutai is calculated as 183.94 yuan in 2025, but is actually about 52 yuan).
    # Therefore, only statistics"implement"The record of the stage, and cash_div (implementation amount received) takes precedence.
    IMPLEMENTED_STATUS = {"implement", "implemented", "implement allocation"}
    implemented = [
        row for row in rows
        if str(row.get("div_proc") or row.get("status") or "").strip() in IMPLEMENTED_STATUS
    ]
    # Bottom line: If the data source does not have a div_proc stage mark (such as some local tables), fall back to the original relaxed approach.
    # But press (end_date, ann_date) Remove duplicates and avoid repeated accumulation.
    if not implemented:
        seen_keys = set()
        for row in rows:
            cash = _pick_number(row, "cash_div", "cash_div_tax", "dividend_per_share")
            if cash is None or cash <= 0:
                continue
            key = (str(row.get("end_date") or ""), str(row.get("ann_date") or ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            implemented.append(row)
    implemented.sort(key=lambda item: str(item.get("end_date") or item.get("ann_date") or ""), reverse=True)
    implemented = implemented[:max(1, min(int(years or 5) * 3, 50))]
    annual_cash: Dict[int, float] = {}
    records = []
    seen_event_keys = set()
    for row in implemented:
        year = _period_year(row.get("end_date") or row.get("ann_date"))
        # When implementing records, cash_div (actual arrival) will be used first, and then fall back. cash_div_tax
        cash = _pick_number(row, "cash_div", "cash_div_tax", "dividend_per_share")
        # The same dividend event (end_date + ann_date) Only counts once to prevent repeated accumulation
        event_key = (str(row.get("end_date") or ""), str(row.get("ann_date") or ""))
        if year and cash is not None and cash > 0 and event_key not in seen_event_keys:
            seen_event_keys.add(event_key)
            annual_cash[year] = annual_cash.get(year, 0.0) + cash
        records.append({
            "end_date": _normalize_date(row.get("end_date")),
            "ann_date": _normalize_date(row.get("ann_date")),
            "ex_date": _normalize_date(row.get("ex_date")),
            "cash_div_tax": cash,
            "cash_div": _pick_number(row, "cash_div"),
            "div_proc": row.get("div_proc") or row.get("status"),
        })
    current_price = get_latest_stock_price(normalized_symbol)
    if current_price is None or current_price <= 0:
        basic = get_stock_basic_info(normalized_symbol) or {}
        current_price = _pick_number(basic, "close", "current_price")
    latest_year = max(annual_cash.keys()) if annual_cash else None
    latest_cash = annual_cash.get(latest_year) if latest_year else None
    dividend_yield = _safe_div(latest_cash, current_price)
    annual_values = [{"year": year, "cash_dividend_per_share": cash, "dividend_yield": _safe_div(cash, current_price)} for year, cash in sorted(annual_cash.items(), reverse=True)]
    financial = get_historical_financial_annual_series(normalized_symbol, years=years)
    fcf_values = [row.get("free_cashflow") for row in financial.get("records") or [] if row.get("free_cashflow") is not None]
    return {
        "status": "success" if records else "no_data",
        "symbol": normalized_symbol,
        "data_source": source,
        "current_price": current_price,
        "records": records,
        "annual": annual_values,
        "metrics": {
            "latest_cash_dividend_per_share": latest_cash,
            "latest_dividend_yield": dividend_yield,
            "latest_dividend_yield_pct": dividend_yield * 100 if dividend_yield is not None else None,
            "average_cash_dividend_per_share": mean(list(annual_cash.values())) if annual_cash else None,
            "dividend_positive_years": sum(1 for value in annual_cash.values() if value > 0),
            "dividend_continuity_ratio": sum(1 for value in annual_cash.values() if value > 0) / max(1, min(int(years or 5), len(annual_cash))) if annual_cash else None,
            "fcf_positive_ratio": _positive_ratio(fcf_values),
        },
        "coverage": {"dividend_record_count": len(records), "annual_count": len(annual_cash), "financial_years": len(financial.get("records") or [])},
        "warnings": [] if records else [
            "The dividend details are not synchronized locally, and the dividend rate will be downgraded using the basic information snapshot caliber (dv_ratio)."
            if not allow_remote_fetch
            else "Dividend data not found; Tushare dividend permission or local dividend synchronization required."
        ],
    }


def get_portfolio_risk_profile(positions: List[Dict[str, Any]], start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 300) -> Dict[str, Any]:
    """Return to the risk profile of the position portfolio.

    Args:
        positions: Position list, each element contains symbol/code, market_value or quantity+price; 
                   Such as [{"symbol": "600519", "market_value": 100000}, ...]
        start_date: Starting date (YYYY-MM-DD), defaults to 1 year ago when None
        end_date: Deadline (YYYY-MM-DD), defaults to today when None
        limit: Maximum number of samples for a single stock (default 300)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "insufficient_data" | "no_data"
            window: time window — start(start date), end(Deadline)
            positions: List of positions (in descending order of weight)[{"symbol": ..., "name": ...,
                  "market_value": ..., "weight": ..., "industry": ...}, ...]
            metrics: portfolio risk indicators — total_market_value(Total market capitalization), sample_count(Number of samples),
                     annualized_volatility(annualized volatility), max_drawdown(maximum drawdown),
                     var_95(95% VaR), cvar_95(95% CVaR), top1_weight(Maximum position weight),
                     top3_weight(The total weight of the top 3 positions), concentration_hhi(Herfindahl index)
            exposure: Industry exposure — industry_weights(Industry weight dict)
            return_series: portfolio return series [{"trade_date": ..., "return": ...}, ...]
            coverage: Coverage information — position_count(Number of positions), sample_counts(Number of samples for each stock dict)
            warnings: Warning message list (additional prompt when the number of samples is less than 20)
    """
    normalized_positions = []
    for item in positions or []:
        symbol = _normalize_symbol(item.get("symbol") or item.get("code"))
        if not symbol:
            continue
        market_value = _safe_float(item.get("market_value"))
        quantity = _safe_float(item.get("quantity") or item.get("shares"))
        price = _safe_float(item.get("price") or item.get("current_price") or item.get("cost_price"))
        if market_value is None and quantity is not None and price is not None:
            market_value = quantity * price
        if market_value is None or market_value <= 0:
            continue
        normalized_positions.append({"symbol": symbol, "name": item.get("name"), "market_value": market_value})
    total_value = sum(item["market_value"] for item in normalized_positions)
    if total_value <= 0:
        return {"status": "no_data", "positions": [], "metrics": {}, "warnings": ["No valid position market value is provided."]}
    for item in normalized_positions:
        item["weight"] = item["market_value"] / total_value
        master = get_security_master(item["symbol"])
        item["industry"] = master.get("industry")
        item["name"] = item.get("name") or master.get("name")
    end = end_date or _today()
    start = start_date or _days_ago(365)
    return_by_date: Dict[str, float] = {}
    sample_counts: Dict[str, int] = {}
    for item in normalized_positions:
        ret = get_return_series(item["symbol"], start_date=start, end_date=end, limit=limit)
        sample_counts[item["symbol"]] = ret.get("coverage", {}).get("return_sample_count", 0)
        for row in ret.get("records") or []:
            value = row.get("return")
            date = row.get("trade_date")
            if value is not None and date:
                return_by_date[date] = return_by_date.get(date, 0.0) + item["weight"] * value
    series = [{"trade_date": date, "return": value} for date, value in sorted(return_by_date.items())]
    values = [item["return"] for item in series]
    nav = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        nav *= 1 + value
        peak = max(peak, nav)
        max_drawdown = min(max_drawdown, nav / peak - 1)
    sorted_returns = sorted(values)
    var_95 = sorted_returns[int(len(sorted_returns) * 0.05)] if len(sorted_returns) >= 20 else None
    cvar_95 = mean([value for value in sorted_returns if var_95 is not None and value <= var_95]) if var_95 is not None else None
    industry_weights: Dict[str, float] = {}
    for item in normalized_positions:
        industry = item.get("industry") or "unknown"
        industry_weights[industry] = industry_weights.get(industry, 0.0) + item["weight"]
    weights = [item["weight"] for item in normalized_positions]
    return {
        "status": "success" if len(values) >= 20 else "insufficient_data",
        "window": {"start": start, "end": end},
        "positions": sorted(normalized_positions, key=lambda item: item["weight"], reverse=True),
        "metrics": {
            "total_market_value": total_value,
            "sample_count": len(values),
            "annualized_volatility": pstdev(values) * (252 ** 0.5) if len(values) > 1 else None,
            "max_drawdown": max_drawdown if values else None,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "top1_weight": max(weights) if weights else None,
            "top3_weight": sum(sorted(weights, reverse=True)[:3]),
            "concentration_hhi": sum(weight * weight for weight in weights),
        },
        "exposure": {"industry_weights": industry_weights},
        "return_series": series,
        "coverage": {"position_count": len(normalized_positions), "sample_counts": sample_counts},
        "warnings": [] if len(values) >= 20 else ["There are less than 20 portfolio return samples, and the reference value of risk indicators is limited."],
    }


def get_risk_event_flags(symbol: str, lookback_days: int = 180, limit: int = 50) -> Dict[str, Any]:
    """Extract risk event flags based on recent news titles/summaries.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        lookback_days: Number of days to look back (default 180)
        limit: Maximum number of news items (default 50, will be truncated to [1, 200]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_news"
            symbol: Standardized 6-digit stock code
            window: time window — start(start date), end(Deadline), lookback_days(Lookback days)
            news_count: Total number of news
            hit_flags: A list of hit risk event types (e.g. ["litigation", "pledge", ...]) 
            flags: Details of various risk events {flag_name: {"hit": bool, "count": int,
                  "examples": [{"title": ..., "publish_time": ..., "url": ...}, ...]}}
                   (flag_name possible values: regulatory_penalty / litigation /
                  shareholder_reduction / pledge / performance_warning /
                  major_restructuring / management_change）
            warnings: Warning information list (additional prompt when there is no news)
    """
    normalized_symbol = _normalize_symbol(symbol)
    end = _today()
    start = _days_ago(lookback_days)
    news = get_stock_news_by_date_range(normalized_symbol, start, end, limit=max(1, min(int(limit or 50), 200)))
    risk_keywords = {
        "regulatory_penalty": ["punishment", "supervision", "File a case", "Investigate", "warning letter", "Inquiry letter"],
        "litigation": ["litigation", "Arbitration", "dispute", "judgment"],
        "shareholder_reduction": ["Reduce holdings", "Passive reduction"],
        "pledge": ["pledge", "Freeze"],
        "performance_warning": ["Pre-loss", "performance decline", "Loss", "Thunderstorm"],
        "major_restructuring": ["Reorganization", "mergers and acquisitions", "asset sale", "major contracts"],
        "management_change": ["resign", "Resign", "Chairman", "general manager"],
    }
    flags = {key: {"hit": False, "count": 0, "examples": []} for key in risk_keywords}
    for item in news:
        text = " ".join(str(item.get(field) or "") for field in ("title", "summary", "content", "category"))
        for key, keywords in risk_keywords.items():
            if any(keyword in text for keyword in keywords):
                flags[key]["hit"] = True
                flags[key]["count"] += 1
                if len(flags[key]["examples"]) < 3:
                    flags[key]["examples"].append({
                        "title": item.get("title"),
                        "publish_time": str(item.get("publish_time") or item.get("pub_date") or ""),
                        "url": item.get("url"),
                    })
    hit_flags = [key for key, value in flags.items() if value.get("hit")]
    return {
        "status": "success" if news else "no_news",
        "symbol": normalized_symbol,
        "window": {"start": start, "end": end, "lookback_days": lookback_days},
        "news_count": len(news),
        "hit_flags": hit_flags,
        "flags": flags,
        "warnings": [] if news else ["Without recent news, risk event flags may be incomplete."],
    }


def get_company_announcements(symbol: str, lookback_days: int = 365, limit: int = 50) -> Dict[str, Any]:
    """Returns a structured list of company announcements/announcement news.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        lookback_days: Number of days to look back (default 365)
        limit: Maximum number of announcements (default 50, will be truncated to [1, 200]) 

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_data"
            symbol: Standardized 6-digit stock code
            window: time window — start(start date), end(Deadline), lookback_days(Lookback days)
            announcements: Announcement list [{"title": ..., "publish_time": ..., "category": ...,
                  "summary": ..., "url": ..., "source": ...}, ...] (Maximum limit items)
            coverage: Coverage information — source_news_count(Original news count),
                     announcement_count(The quantity identified as an announcement)
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    end = _today()
    start = _days_ago(lookback_days)
    news = get_stock_news_by_date_range(normalized_symbol, start, end, limit=max(1, min(int(limit or 50), 200)))
    announcement_keywords = ["Announcement", "Disclosure", "annual report", "quarterly report", "semi-annual report", "dividend", "Reduce holdings", "Overweight", "Reorganization", "trading suspension", "Resumption of trading"]
    announcements = []
    for item in news:
        text = " ".join(str(item.get(field) or "") for field in ("title", "summary", "content", "category"))
        if any(keyword in text for keyword in announcement_keywords):
            announcements.append({
                "title": item.get("title"),
                "publish_time": str(item.get("publish_time") or item.get("pub_date") or ""),
                "category": item.get("category"),
                "summary": item.get("summary") or item.get("content"),
                "url": item.get("url"),
                "source": item.get("source") or item.get("data_source"),
            })
    return {
        "status": "success" if announcements else "no_data",
        "symbol": normalized_symbol,
        "window": {"start": start, "end": end, "lookback_days": lookback_days},
        "announcements": announcements[:limit],
        "coverage": {"source_news_count": len(news), "announcement_count": len(announcements[:limit])},
        "warnings": [] if announcements else ["No announcement records have been identified in recent news; if a formal announcement is required, the announcement-specific data source should be accessed."],
    }


def get_pledge_risk_profile(symbol: str, source: Optional[str] = None) -> Dict[str, Any]:
    """Equity pledge risk portrait: obtain pledge ratio, unreleased pledge size, pledge situation of top shareholders, and risk level.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        source: Specify the data source ("tushare" / "akshare") , Automatically selected when None

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: Status: "success" | "no_pledge" | "no_data" | "error"
            symbol: Standardized 6-digit stock code
            data_source: The actual data source name used, if there is no data None
            metrics: aggregated metrics — total_pledge_ratio(Total pledge ratio%), outstanding_pledge_amount_wan(Ten thousand shares not released),
                     total_share_wan(Total share capital: 10,000 shares), pledger_count(Number of shareholders), total_pledge_events(number of events),
                     recent_pledge_events_30d(Number of events in the past 30 days)
            top_pledgers: List of top undeposited shareholders [{"holder_name": ..., "shares_wan": ..., "ratio_pct": ...}, ...]
            recent_pledges: List of recent staking events (up to 20 items)
            risk_level: risk level: "high" | "medium_high" | "medium" | "low" | "none"
            warnings: Warning message list
            data_source_status: Call status of each data source
    """
    normalized_symbol = _normalize_symbol(symbol)
    ts_code = _to_ts_code(normalized_symbol)
    rows = []
    data_source = None

    def _resolve_sources(preferred_source: Optional[str], market_category: str) -> List[str]:
        if preferred_source:
            return [preferred_source]
        configured = list_configured_external_sources(market_category=market_category)
        if configured:
            return configured
        return list(SUPPORTED_EXTERNAL_SOURCES.get(market_category, ()))

    # Record the specific status of each data source to distinguish"No pledge"(business correct) vs "Data source error"
    source_call_status: Dict[str, str] = {}  # source_id -> "success_empty" | "success_with_data" | "error"
    source_call_errors: Dict[str, str] = {}

    resolved_sources = _resolve_sources(source, "a_shares")
    logger.info(f"🔬 [get_pledge_risk_profile] _resolve_sources Return: {resolved_sources} (source={source!r}, symbol={normalized_symbol}) | PID={os.getpid()}")
    for source_id in resolved_sources:
        try:
            if source_id == "tushare":
                logger.info(f"🔬 [get_pledge_risk_profile] try tushare | PID={os.getpid()}")
                from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
                from .sync_wrappers import run_async_in_sync

                provider = get_tushare_provider()
                df = run_async_in_sync(provider.get_pledge_detail(ts_code=ts_code))
                if df is not None and not df.empty:
                    rows = df.to_dict("records")
                    data_source = "tushare"
                    source_call_status[source_id] = "success_with_data"
                    logger.info(f"🔬 [get_pledge_risk_profile] tushare ✅ Return {len(rows)} OK | PID={os.getpid()}")
                    break
                else:
                    # Tushare The call was successful but returned empty DataFrame —— The stock may really be unsecured
                    source_call_status[source_id] = "success_empty"
                    logger.info(f"🔬 [get_pledge_risk_profile] tushare ⚠️ Return empty (success_empty) | PID={os.getpid()}")
            elif source_id == "akshare":
                logger.info(f"🔬 [get_pledge_risk_profile] try akshare | PID={os.getpid()}")
                from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
                from .sync_wrappers import run_async_in_sync

                provider = get_akshare_provider()
                df = run_async_in_sync(provider.get_pledge_detail(symbol=normalized_symbol))
                if df is not None and not df.empty:
                    rows = df.to_dict("records")
                    data_source = "akshare"
                    source_call_status[source_id] = "success_with_data"
                    break
                else:
                    source_call_status[source_id] = "success_empty"
        except Exception as exc:
            logger.error("🔬 [get_pledge_risk_profile] Data source %s call exception: %s | PID=%s", source_id, exc, os.getpid())
            source_call_status[source_id] = "error"
            source_call_errors[source_id] = str(exc)

    # Final summary log (printed out regardless of level to facilitate troubleshooting)
    logger.info(
        f"🔬 [get_pledge_risk_profile] final result: status={source_call_status}, "
        f"rows={len(rows)} | PID={os.getpid()}"
    )

    if not rows:
        # Distinguish between two no_data situations:
        # 1. The data source call was successful but returned empty → The stock may truly be unsecured (business correct)
        # 2. All exceptions in data source calls → Data source error (needs fix)
        has_success_empty = any(s == "success_empty" for s in source_call_status.values())
        has_error = any(s == "error" for s in source_call_status.values())
        tried_sources = list(source_call_status.keys())

        if has_success_empty and not has_error:
            # The data source is normal, but there is no pledge record for the stock (the business is correct)
            return {
                "status": "no_pledge",
                "symbol": normalized_symbol,
                "data_source": None,
                "metrics": {},
                "top_pledgers": [],
                "recent_pledges": [],
                "risk_level": "none",
                "warnings": [
                    f"There is no equity pledge record for this stock (data source {tried_sources} The call succeeds but returns 0 rows)."
                    "It may be unpledged stocks such as bank stocks/blue chip stocks, which is a correct business situation."
                ],
                "data_source_status": source_call_status,
            }
        elif has_success_empty and has_error:
            # Some data sources are successful but empty, and some are abnormal.
            error_details = "; ".join(f"{k}: {v}" for k, v in source_call_errors.items())
            return {
                "status": "no_data",
                "symbol": normalized_symbol,
                "data_source": None,
                "metrics": {},
                "top_pledgers": [],
                "recent_pledges": [],
                "risk_level": "unknown",
                "warnings": [
                    f"Some data source calls are abnormal ({error_details}) , "
                    f"A successfully called data source returns null (the stock may not be pledged, or the data source may have insufficient permissions)."
                ],
                "data_source_status": source_call_status,
            }
        else:
            # All data sources are abnormal
            error_details = "; ".join(f"{k}: {v}" for k, v in source_call_errors.items())
            return {
                "status": "error",
                "symbol": normalized_symbol,
                "data_source": None,
                "metrics": {},
                "top_pledgers": [],
                "recent_pledges": [],
                "risk_level": "unknown",
                "warnings": [
                    f"All data source calls failed: {error_details}. "
                    "Please check Tushare pledge_detail permission or akshare pledge interface availability."
                ],
                "data_source_status": source_call_status,
            }

    # 🔍 Debug log: print the fields and values of the first 3 pieces of raw data
    logger.info(f"🔍 [Pledge debugging] data source: {data_source}, Number of data items: {len(rows)}")
    if rows:
        logger.info(f"🔍 [Pledge debugging] Available fields: {list(rows[0].keys())}")
        for i, row in enumerate(rows[:3]):
            is_release_val = row.get("is_release")
            pledge_amt = row.get("pledge_amount")
            p_total_ratio = row.get("p_total_ratio")
            logger.info(f"🔍 [Pledge debugging] record#{i+1}: is_release={is_release_val!r}, pledge_amount={pledge_amt!r}, p_total_ratio={p_total_ratio!r}")

    total_pledge_ratio = 0.0
    outstanding_amount = 0.0
    pledger_map: Dict[str, Dict[str, Any]] = {}
    recent_events = []

    for idx, row in enumerate(rows):
        pledge_amt = _pick_number(row, "pledge_amount", "Number of pledged shares", "Pledge quantity") or 0.0
        ratio = _pick_number(row, "p_total_ratio", "Proportion of total share capital", "Proportion of total share capital(%)") or 0.0
        holder = str(row.get("holder_name") or row.get("股东名称") or row.get("holder") or "unknown")
        is_released = str(row.get("is_release") or row.get("是否解押") or "").strip() in {"1", "Yes", "Released", "True", "true"}
        ann_date = str(row.get("ann_date") or row.get("公告日期") or "")

        # 🔍 Only print the first 5 debugging logs
        if idx < 5:
            logger.info(
                f"🔍 [Pledge debugging] record#{idx+1}: is_released={is_released}, "
                f"pledge_amt={pledge_amt}, ratio={ratio}, holder={holder[:10]}"
            )

        if not is_released:
            outstanding_amount += pledge_amt
            total_pledge_ratio += ratio


        if holder not in pledger_map:
            pledger_map[holder] = {
                "holder_name": holder,
                "total_pledged": 0.0,
                "outstanding": 0.0,
                "holding_amount": _pick_number(row, "holding_amount", "Total number of shares held", "Number of shares held") or 0.0,
                "holding_ratio": _pick_number(row, "h_total_ratio", "Shareholding ratio to total share capital") or 0.0,
                "pledge_count": 0,
                "release_count": 0,
            }
        pledger_map[holder]["total_pledged"] += pledge_amt
        pledger_map[holder]["pledge_count"] += 1
        if not is_released:
            pledger_map[holder]["outstanding"] += pledge_amt
        else:
            pledger_map[holder]["release_count"] += 1

        if ann_date:
            recent_events.append({
                "ann_date": _normalize_date(ann_date),
                "holder_name": holder,
                "pledge_amount": pledge_amt,
                "is_release": is_released,
                "start_date": _normalize_date(row.get("start_date") or row.get("质押开始日期") or ""),
                "end_date": _normalize_date(row.get("end_date") or row.get("质押结束日期") or ""),
                "pledgor": row.get("pledgor") or row.get("质押方") or "",
            })

    top_pledgers = sorted(
        pledger_map.values(),
        key=lambda x: x["outstanding"],
        reverse=True
    )[:10]

    recent_events.sort(key=lambda x: x["ann_date"] or "", reverse=True)
    recent_pledges = recent_events[:20]

    if total_pledge_ratio >= 50:
        risk_level = "high"
    elif total_pledge_ratio >= 30:
        risk_level = "medium_high"
    elif total_pledge_ratio >= 15:
        risk_level = "medium"
    elif total_pledge_ratio > 0:
        risk_level = "low"
    else:
        risk_level = "none"

    basic = get_stock_basic_info(normalized_symbol) or {}
    total_share = _pick_number(basic, "total_share", "total share capital")

    # 🔍 Debug log: print final aggregation results
    logger.info(
        f"\n{'='*80}\n"
        f"🔍 [Pledge debugging] get_pledge_risk_profile final aggregation result\n"
        f"   Stock code: {normalized_symbol}\n"
        f"   Total number of outstanding shares: {outstanding_amount:.2f} 10,000 shares\n"
        f"   Total pledge ratio: {total_pledge_ratio:.2f}%\n"
        f"   Number of undeposited shareholders: {len(pledger_map)}\n"
        f"   Top 10 undeposited shareholders: {[p['holder_name'][:10] for p in top_pledgers[:5]]}...\n"
        f"   risk level: {risk_level}\n"
        f"{'='*80}"
    )

    # 🔑 Key: Output the field names of the return structure for use in code generation feedback
    result = {
        "status": "success",
        "symbol": normalized_symbol,
        "data_source": data_source,
        "metrics": {
            "total_pledge_ratio": round(total_pledge_ratio, 2),
            "outstanding_pledge_amount_wan": round(outstanding_amount, 2),
            "total_share_wan": total_share,
            "pledger_count": len(pledger_map),
            "total_pledge_events": len(rows),
            "recent_pledge_events_30d": sum(
                1 for e in recent_events
                if e["ann_date"] and _days_between(e["ann_date"], _today()) <= 30
            ),
        },
        "_readme": {
            "total_pledge_ratio": f"Total pledge ratio = {round(total_pledge_ratio, 2)}% (The value of this field is the percentage itself: 0.37 means 0.37%, not 37%)",
            "outstanding_pledge_amount_wan": f"Number of unreleased pledged shares = {round(outstanding_amount, 2)} Ten thousand shares (the unit is ten thousand shares, not ten thousand yuan; converted to market value = 10,000 shares × stock price ÷ 10000 100 million yuan)",
            "total_share_wan": "Total share capital, unit 10,000 shares",
            "holding_ratio": "The proportion of shareholdings in total share capital, the value is the percentage itself (38.19 = 38.19%) ",
        },
        "top_pledgers": top_pledgers,
        "recent_pledges": recent_pledges,
        "risk_level": risk_level,
        "warnings": [],
    }

    logger.info(f"📊 get_pledge_risk_profile Return structure: {list(result.keys())}")
    return result


def get_pledge_historical_series(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    years: Optional[int] = None,
    period: str = "year",
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Equity pledge historical sequence: Returns trend data such as pledge ratio and number of pledged shares within a specified time period.

    Based on the start/end date of the pledge details, the unreleased balance at the end of each cycle is calculated according to the specified cycle.
    Used to evaluate the direction of change (improvement/deterioration) of pledge risk.

    Args:
        symbol: A stock ticker code
        start_date: Start date in YYYY-MM-DD format. Choose one of two options: years.
        end_date: End date, YYYY-MM-DD format. Default is today.
        years: Last N years, convenience parameter, alternative to start_date. Default is 3 years.
        period: Statistical period, support 'year' (year),'quarter' (quarter),'month' (month). Default 'year'. 
        source: Data source, automatically selected by default.

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            status: "success" | "no_data" | "error"
            symbol: Standardized 6-digit stock code
            data_source: The actual data source name used
            period: statistical period "year" | "quarter" | "month"
            start_date: start date "YYYY-MM-DD"
            end_date: end date "YYYY-MM-DD"
            period_count: Total number of cycles
            series: Historical trend array [{"period": "2024", "period_label": "2024 year", "as_of_date": "2024-12-31",
                     "outstanding_pledge_amount_wan": Ten thousand shares not released, "pledge_ratio": Pledge ratio%,
                     "active_pledge_count": Number of active transactions, "total_share_wan": Total share capital: 10,000 shares}, ...]
            trend_assessment: Trend assessment {"direction": "stable"|"improving"|"deteriorating"|"fluctuating"|"insufficient_data",
                             "change_pct": % change or None, "summary": "text description"}
            warnings: Warning message list
    """
    normalized_symbol = _normalize_symbol(symbol)
    ts_code = _to_ts_code(normalized_symbol)
    rows = []
    data_source = None

    def _resolve_sources(preferred_source: Optional[str], market_category: str) -> List[str]:
        if preferred_source:
            return [preferred_source]
        configured = list_configured_external_sources(market_category=market_category)
        if configured:
            return configured
        return list(SUPPORTED_EXTERNAL_SOURCES.get(market_category, ()))

    # Record the specific status of each data source (consistent with get_pledge_risk_profile)
    source_call_status: Dict[str, str] = {}
    source_call_errors: Dict[str, str] = {}

    resolved_sources = _resolve_sources(source, "a_shares")
    logger.info(f"🔬 [get_pledge_historical_series] _resolve_sources Return: {resolved_sources} (source={source!r}, symbol={normalized_symbol}) | PID={os.getpid()}")
    for source_id in resolved_sources:
        try:
            if source_id == "tushare":
                logger.info(f"🔬 [get_pledge_historical_series] try tushare | PID={os.getpid()}")
                from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
                from .sync_wrappers import run_async_in_sync

                provider = get_tushare_provider()
                df = run_async_in_sync(provider.get_pledge_detail(ts_code=ts_code))
                if df is not None and not df.empty:
                    rows = df.to_dict("records")
                    data_source = "tushare"
                    source_call_status[source_id] = "success_with_data"
                    logger.info(f"🔬 [get_pledge_historical_series] tushare ✅ Return {len(rows)} OK | PID={os.getpid()}")
                    break
                else:
                    source_call_status[source_id] = "success_empty"
                    logger.info(f"🔬 [get_pledge_historical_series] tushare ⚠️ Return empty (success_empty) | PID={os.getpid()}")
            elif source_id == "akshare":
                logger.info(f"🔬 [get_pledge_historical_series] try akshare | PID={os.getpid()}")
                from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
                from .sync_wrappers import run_async_in_sync

                provider = get_akshare_provider()
                df = run_async_in_sync(provider.get_pledge_detail(symbol=normalized_symbol))
                if df is not None and not df.empty:
                    rows = df.to_dict("records")
                    data_source = "akshare"
                    source_call_status[source_id] = "success_with_data"
                    break
                else:
                    source_call_status[source_id] = "success_empty"
        except Exception as exc:
            logger.error("🔬 [get_pledge_historical_series] Data source %s call exception: %s | PID=%s", source_id, exc, os.getpid())
            source_call_status[source_id] = "error"
            source_call_errors[source_id] = str(exc)

    # Final summary log (printed out regardless of level to facilitate troubleshooting)
    logger.info(
        f"🔬 [get_pledge_historical_series] final result: status={source_call_status}, "
        f"rows={len(rows)} | PID={os.getpid()}"
    )

    if not rows:
        # Distinguish between two no_data cases (consistent with get_pledge_risk_profile)
        has_success_empty = any(s == "success_empty" for s in source_call_status.values())
        has_error = any(s == "error" for s in source_call_status.values())
        tried_sources = list(source_call_status.keys())

        if has_success_empty and not has_error:
            return {
                "status": "no_pledge",
                "symbol": normalized_symbol,
                "data_source": None,
                "series": [],
                "warnings": [
                    f"There is no equity pledge record for this stock (data source {tried_sources} The call succeeds but returns 0 rows)."
                    "It may be unpledged stocks such as bank stocks/blue chip stocks, which is a correct business situation."
                ],
                "data_source_status": source_call_status,
            }
        elif has_success_empty and has_error:
            error_details = "; ".join(f"{k}: {v}" for k, v in source_call_errors.items())
            return {
                "status": "no_data",
                "symbol": normalized_symbol,
                "data_source": None,
                "series": [],
                "warnings": [
                    f"Some data source calls are abnormal ({error_details}) , "
                    f"A successfully called data source returns null (the stock may not be pledged, or the data source may have insufficient permissions)."
                ],
                "data_source_status": source_call_status,
            }
        else:
            error_details = "; ".join(f"{k}: {v}" for k, v in source_call_errors.items())
            return {
                "status": "error",
                "symbol": normalized_symbol,
                "data_source": None,
                "series": [],
                "warnings": [
                    f"All data source calls failed: {error_details}. "
                    "Please check Tushare pledge_detail permission or akshare pledge interface availability."
                ],
                "data_source_status": source_call_status,
            }

    from datetime import datetime, date

    def _parse_date(date_val: Any) -> Optional[datetime]:
        if not date_val:
            return None
        # First format it into a date string with dashes
        normalized = _normalize_date(date_val)
        try:
            return datetime.strptime(normalized, "%Y-%m-%d")
        except Exception:
            return None

    today = datetime.now()

    if end_date:
        end_dt = _parse_date(end_date) or today
    else:
        end_dt = today

    if start_date:
        start_dt = _parse_date(start_date)
        if start_dt is None:
            start_dt = datetime(end_dt.year - 3, 1, 1)
    elif years is not None:
        n = max(1, min(int(years), 10))
        start_dt = datetime(end_dt.year - n + 1, 1, 1)
    else:
        start_dt = datetime(end_dt.year - 2, 1, 1)

    period = period.lower()
    if period not in ("year", "quarter", "month", "y", "q", "m"):
        period = "year"
    period_map = {"y": "year", "q": "quarter", "m": "month"}
    period = period_map.get(period, period)

    pledge_events = []
    for row in rows:
        pledge_amt = _pick_number(row, "pledge_amount", "Number of pledged shares", "Pledge quantity") or 0.0
        ratio = _pick_number(row, "p_total_ratio", "Proportion of total share capital", "Proportion of total share capital(%)") or 0.0
        s_date = _parse_date(row.get("start_date") or row.get("质押开始日期") or row.get("ann_date"))
        e_date = _parse_date(row.get("end_date") or row.get("质押结束日期"))
        is_released = str(row.get("is_release") or row.get("是否解押") or "").strip() in {"1", "Yes", "Released", "True", "true"}

        if is_released and e_date is None:
            e_date = _parse_date(row.get("ann_date"))

        pledge_events.append({
            "amount": pledge_amt,
            "ratio": ratio,
            "start_date": s_date,
            "end_date": e_date if is_released else None,
            "holder": str(row.get("holder_name") or row.get("股东名称") or "unknown"),
        })

    def _period_key(dt: datetime, ptype: str) -> str:
        if ptype == "year":
            return str(dt.year)
        elif ptype == "quarter":
            q = (dt.month - 1) // 3 + 1
            return f"{dt.year}Q{q}"
        else:
            return f"{dt.year}-{dt.month:02d}"

    def _period_end(dt: datetime, ptype: str) -> datetime:
        if ptype == "year":
            return datetime(dt.year, 12, 31)
        elif ptype == "quarter":
            q = (dt.month - 1) // 3 + 1
            if q == 1:
                return datetime(dt.year, 3, 31)
            elif q == 2:
                return datetime(dt.year, 6, 30)
            elif q == 3:
                return datetime(dt.year, 9, 30)
            else:
                return datetime(dt.year, 12, 31)
        else:
            if dt.month == 12:
                return datetime(dt.year, 12, 31)
            else:
                import calendar
                last_day = calendar.monthrange(dt.year, dt.month)[1]
                return datetime(dt.year, dt.month, last_day)

    period_ends = []
    cursor = start_dt
    while cursor <= end_dt:
        pe = _period_end(cursor, period)
        if pe > end_dt:
            pe = end_dt
        if pe >= start_dt:
            key = _period_key(pe, period)
            if not period_ends or period_ends[-1]["key"] != key:
                period_ends.append({"key": key, "date": pe, "label": key})
        if period == "year":
            cursor = datetime(cursor.year + 1, 1, 1)
        elif period == "quarter":
            if cursor.month >= 10:
                cursor = datetime(cursor.year + 1, 1, 1)
            else:
                cursor = datetime(cursor.year, cursor.month + 3, 1)
        else:
            if cursor.month >= 12:
                cursor = datetime(cursor.year + 1, 1, 1)
            else:
                cursor = datetime(cursor.year, cursor.month + 1, 1)

    basic = get_stock_basic_info(normalized_symbol) or {}
    total_share = _pick_number(basic, "total_share", "total share capital")

    series: List[Dict[str, Any]] = []
    for p in period_ends:
        as_of = p["date"]
        period_amount = 0.0
        period_ratio = 0.0
        event_count = 0

        for event in pledge_events:
            if event["start_date"] is None:
                continue
            if event["start_date"] > as_of:
                continue
            if event["end_date"] is not None and event["end_date"] <= as_of:
                continue
            period_amount += event["amount"]
            period_ratio += event["ratio"]
            event_count += 1

        calc_ratio = None
        if total_share and total_share > 0 and period_amount > 0:
            calc_ratio = round((period_amount / total_share) * 100, 2)

        item = {
            "period": p["key"],
            "period_label": p["label"],
            "as_of_date": as_of.strftime("%Y-%m-%d"),
            "outstanding_pledge_amount_wan": round(period_amount, 2),
            "pledge_ratio": round(period_ratio, 2) if period_ratio > 0 else (calc_ratio if calc_ratio is not None else 0.0),
            "active_pledge_count": event_count,
            "total_share_wan": total_share,
        }
        if period == "year":
            item["year"] = int(p["key"])
        series.append(item)

    series.sort(key=lambda x: x["as_of_date"], reverse=True)

    # 🔍 Debug log: print the statistical results of each cycle
    logger.info(f"\n{'='*80}")
    logger.info(f"🔍 [Staking trend debugging] Statistical results for each cycle:")
    for item in series:
        logger.info(
            f"   {item.get('period')}: "
            f"Not released={item['outstanding_pledge_amount_wan']:.2f}10,000 shares, "
            f"Proportion={item['pledge_ratio']:.2f}%, "
            f"Number of active transactions={item['active_pledge_count']}"
        )

    valid_periods = [s for s in series if s.get("outstanding_pledge_amount_wan", 0) > 0]

    warnings: List[str] = []
    if len(valid_periods) < len(period_ends):
        warnings.append(f"There is no valid pledge data in some cycles, a total of {len(period_ends)} cycles, valid {len(valid_periods)} a")
    if len(rows) < 20 and data_source == "akshare":
        warnings.append("AKShare The data source may only return recent data, and the historical period may be incomplete; it is recommended to use Tushare to obtain the complete history")

    trend_result = _assess_pledge_trend(series, period)

    result = {
        "status": "success",
        "symbol": normalized_symbol,
        "data_source": data_source,
        "period": period,
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "period_count": len(period_ends),
        "series": series,
        "trend_assessment": trend_result,
        "warnings": warnings,
    }

    logger.info(f"📊 get_pledge_historical_series Return structure: {list(result.keys())}")
    return result


def _assess_pledge_trend(series: List[Dict[str, Any]], period: str = "year") -> Dict[str, Any]:
    """Evaluate staking trend direction based on historical sequences."""
    if len(series) < 2:
        return {"direction": "insufficient_data", "change_pct": None, "summary": "Insufficient data to determine trends"}

    valid = [s for s in series if s.get("pledge_ratio", 0) > 0]
    if len(valid) < 2:
        return {"direction": "insufficient_data", "change_pct": None, "summary": "Insufficient valid data to determine trends"}

    latest = valid[0]
    oldest = valid[-1]

    latest_ratio = latest.get("pledge_ratio", 0)
    oldest_ratio = oldest.get("pledge_ratio", 0)

    latest_label = latest.get("period_label") or latest.get("year") or ""
    oldest_label = oldest.get("period_label") or oldest.get("year") or ""

    if oldest_ratio == 0:
        change_pct = None
    else:
        change_pct = round(((latest_ratio - oldest_ratio) / oldest_ratio) * 100, 1)

    diff = latest_ratio - oldest_ratio
    if abs(diff) < 1.0:
        direction = "stable"
        summary = f"The pledge ratio is basically stable.{oldest_label} {oldest_ratio}% → {latest_label} {latest_ratio}%"
    elif diff > 0:
        direction = "worsening"
        summary = f"The pledge ratio increases (risk worsens),{oldest_label} {oldest_ratio}% → {latest_label} {latest_ratio}%, rise {round(diff, 2)} percentage points"
    else:
        direction = "improving"
        summary = f"The pledge ratio decreases (the risk improves),{oldest_label} {oldest_ratio}% → {latest_label} {latest_ratio}%, fall {round(abs(diff), 2)} percentage points"

    return {
        "direction": direction,
        "change_pct": change_pct,
        "summary": summary,
        "latest_period": latest.get("period") or latest.get("year"),
        "latest_ratio": latest_ratio,
        "oldest_period": oldest.get("period") or oldest.get("year"),
        "oldest_ratio": oldest_ratio,
        "period": period,
    }


def _to_ts_code(symbol: str) -> str:
    if "." in symbol:
        return symbol
    if symbol.startswith("6"):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _days_between(date_str: str, today_str: str) -> int:
    try:
        from datetime import datetime
        # Uniformly formatted as a date string with dashes
        d1 = datetime.strptime(_normalize_date(date_str), "%Y-%m-%d")
        d2 = datetime.strptime(_normalize_date(today_str), "%Y-%m-%d")
        return abs((d2 - d1).days)
    except Exception:
        return 999

