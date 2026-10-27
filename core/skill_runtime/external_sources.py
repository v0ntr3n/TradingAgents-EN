"""Skill Runtime external data source bridging."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .catalog import SUPPORTED_EXTERNAL_SOURCES, list_configured_external_sources
from .sync_wrappers import normalize_tabular_result, run_async_in_sync

logger = logging.getLogger(__name__)


def _resolve_sources(preferred_source: Optional[str], market_category: str) -> List[str]:
    if preferred_source:
        return [preferred_source]
    configured = list_configured_external_sources(market_category=market_category)
    if configured:
        return configured
    return list(SUPPORTED_EXTERNAL_SOURCES.get(market_category, ()))


def get_external_stock_news(
    symbol: str,
    source: Optional[str] = None,
    limit: int = 10,
    market_category: str = "a_shares",
) -> Dict[str, Any]:
    """Synchronously obtain external news data.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        source: Specify data source (currently only supports "akshare") , Automatically selects the configured source when None
        limit: Returns the upper limit of news items, default 10
        market_category: Market category, default "a_shares"

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            source: Data source identifier: "akshare" | None (None if no source is available or the call fails)
            data: News list, the elements are dict normalized by column (trade_date/title/content and other fields,
                  Depends on the upstream data source); if there is no data, it is an empty list []
    """
    for source_id in _resolve_sources(source, market_category):
        try:
            if source_id == "akshare":
                from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

                provider = get_akshare_provider()
                result = provider.get_stock_news_sync(symbol, limit=limit)
                normalized = normalize_tabular_result(result)
                if normalized:
                    return {"source": source_id, "data": normalized}
        except Exception as exc:
            logger.warning("External news source %s call failed: %s", source_id, exc)

    return {"source": None, "data": []}


def get_external_valuation_data(
    symbol: str,
    start_date: str,
    end_date: str,
    source: Optional[str] = None,
    market_category: str = "a_shares",
) -> Dict[str, Any]:
    """Synchronously obtain external historical valuation data (PE_TTM, PB_MRQ, PS_TTM, PCF_TTM).

    Use Tushare daily_basic date range query to obtain the entire data in one call.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Start date (YYYY-MM-DD or YYYYMMDD)
        end_date: End date (YYYY-MM-DD or YYYYMMDD)
        source: Specify the data source ("tushare" / "baostock") , Automatically selected when None;
                baostock Unstable will automatically downgrade to tushare
        market_category: Market category, default "a_shares"

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            When successful, the dict returned by tushare provider will be transparently transmitted directly. Common fields ——
                source: Data source identifier: "tushare"
                symbol: Standardized stock code
                data: Valuation sequence list, the elements are dict ——
                    trade_date: transaction date
                    pe_ttm: rolling price to earnings ratio
                    pb_mrq: Price to Book Ratio for the Most Recent Reporting Period
                    ps_ttm: rolling price-to-sales ratio
                    pcf_ttm: rolling price to cash ratio
            Returned when downgrade fails ——
                source: None
                data: empty list []
    """
    for source_id in _resolve_sources(source, market_category):
        try:
            if source_id == "baostock":
                # Baostock Unstable, downgraded to Tushare
                pass
            elif source_id == "tushare":
                from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

                provider = get_tushare_provider()
                result = run_async_in_sync(
                    provider.get_valuation_history(symbol, start_date, end_date)
                )
                if result.get("data"):
                    return result
        except Exception as exc:
            logger.warning("Call to external valuation source %s failed: %s", source_id, exc)

    # Downgrade: Just try again Tushare
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        result = run_async_in_sync(
            provider.get_valuation_history(symbol, start_date, end_date)
        )
        if result.get("data"):
            return result
    except Exception:
        pass

    return {"source": None, "data": []}


def get_external_historical_data(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    source: Optional[str] = None,
    market_category: str = "a_shares",
) -> Dict[str, Any]:
    """Synchronously obtain external historical quotes.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        start_date: Start date (YYYY-MM-DD or YYYYMMDD)
        end_date: End date (YYYY-MM-DD or YYYYMMDD)
        period: K Line period, default "daily"; Optional "daily" / "weekly" / "monthly" (Subject to upstream data source support)
        source: Specify the data source ("tushare" / "akshare" / "baostock") , Automatically selected when None
        market_category: Market category, default "a_shares"

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            source: Data source identifier: "tushare" | "akshare" | "baostock" | None (None if no source is available or the call fails)
            data: Quotation sequence list, the elements are column-normalized dict (trade_date/open/high/low/close/volume
                  fields, depending on the upstream data source); if there is no data, it will be an empty list []
    """
    for source_id in _resolve_sources(source, market_category):
        try:
            if source_id == "tushare":
                from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

                provider = get_tushare_provider()
                result = run_async_in_sync(provider.get_historical_data(symbol, start_date, end_date, period=period))
            elif source_id == "akshare":
                from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

                provider = get_akshare_provider()
                result = run_async_in_sync(provider.get_historical_data(symbol, start_date, end_date, period=period))
            elif source_id == "baostock":
                from tradingagents.dataflows.providers.china.baostock import get_baostock_provider

                provider = get_baostock_provider()
                result = run_async_in_sync(provider.get_historical_data(symbol, start_date, end_date, frequency=period))
            else:
                continue

            normalized = normalize_tabular_result(result)
            if normalized:
                return {"source": source_id, "data": normalized}
        except Exception as exc:
            logger.warning("Failed to call external historical market source %s: %s", source_id, exc)

    return {"source": None, "data": []}


def get_external_financial_data(
    symbol: str,
    source: Optional[str] = None,
    market_category: str = "a_shares",
    report_type: str = "quarterly",
    period: Optional[str] = None,
    limit: int = 4,
) -> Dict[str, Any]:
    """Synchronously obtain external financial data.

    Args:
        symbol: A Stock code (6 digits or including exchange suffix and suffix)
        source: Specify the data source ("tushare" / "akshare" / "baostock") , Automatically selected when None
        market_category: Market category, default "a_shares"
        report_type: Financial report type, default "quarterly"; Optional "quarterly" / "annual" etc. (use tushare path)
        period: reporting period (e.g. "20240331") , When None is determined by the upstream default behavior; the baostock path will be resolved to year/quarter
        limit: Return the upper limit of the number of records, the default is 4 (only the tushare path takes effect)

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            source: Data source identifier: "tushare" | "akshare" | "baostock" | None (None if no source is available or the call fails)
            data: Financial data, column-normalized dict (note that on success it is a dict structure, not a list);
                  The fields depend on the upstream data source (such as total assets/net profit/revenue, etc.) and will be empty if there is no data. dict {}
    """
    for source_id in _resolve_sources(source, market_category):
        try:
            if source_id == "tushare":
                from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

                provider = get_tushare_provider()
                result = run_async_in_sync(
                    provider.get_financial_data(
                        symbol,
                        report_type=report_type,
                        period=period,
                        limit=limit,
                    )
                )
            elif source_id == "akshare":
                from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

                provider = get_akshare_provider()
                result = run_async_in_sync(provider.get_financial_data(symbol))
            elif source_id == "baostock":
                from tradingagents.dataflows.providers.china.baostock import get_baostock_provider

                provider = get_baostock_provider()
                year = int(period[:4]) if period and len(period) >= 4 and str(period[:4]).isdigit() else None
                quarter = None
                if period and len(period) >= 6 and str(period[4:6]).isdigit():
                    month = int(period[4:6])
                    quarter = max(1, min(4, (month - 1) // 3 + 1))
                result = run_async_in_sync(provider.get_financial_data(symbol, year=year, quarter=quarter))
            else:
                continue

            normalized = normalize_tabular_result(result)
            if normalized:
                return {"source": source_id, "data": normalized}
        except Exception as exc:
            logger.warning("External financial source %s call failed: %s", source_id, exc)

    return {"source": None, "data": {}}


def get_external_query_news(
    query: str,
    curr_date: str,
    look_back_days: int = 7,
    source: str = "google_news",
) -> Dict[str, Any]:
    """Synchronously obtain external news aggregated by query terms.

    Args:
        query: Search keywords (company name, stock name or subject keyword)
        curr_date: The current date (YYYY-MM-DD), as the right endpoint of the query
        look_back_days: Number of days to look back, default 7
        source: data source, default "google_news"; Optional "google_news" / "finnhub"

    Returns:
        dict: Field description (used in code .get() or [] access these keys)——
            source: Data source identifier: "google_news" | "finnhub" | None (None if no source is available or the call fails)
            data: News aggregation results, the type depends on the upstream return (usually news summary text in the form of a string);
                  No data or empty string when call fails ""
    """
    try:
        if source == "google_news":
            from tradingagents.dataflows.interface import get_google_news

            return {"source": source, "data": get_google_news(query, curr_date, look_back_days)}

        if source == "finnhub":
            from tradingagents.dataflows.interface import get_finnhub_news

            return {"source": source, "data": get_finnhub_news(query, curr_date, look_back_days)}
    except Exception as exc:
        logger.warning("External query news source %s call failed: %s", source, exc)

    return {"source": None, "data": ""}