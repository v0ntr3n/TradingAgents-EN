"""Skill Runtime capability catalog and metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from app.core.data_source_priority import get_enabled_data_sources_sync


SUPPORTED_COLLECTIONS = {
    "stock_basic_info",
    "market_quotes",
    "stock_daily_quotes",
    "stock_financial_data",
    "stock_financial_periods",
    "stock_news",
}

SUPPORTED_EXTERNAL_SOURCES: Dict[str, Sequence[str]] = {
    "a_shares": ("tushare", "akshare", "baostock"),
    "hk_stocks": ("akshare",),
    "us_stocks": ("google_news", "finnhub"),
}

STOCK_COLLECTION_SUMMARY: List[Dict[str, Any]] = [
    {
        "collection": "stock_basic_info",
        "purpose": "Basic stock information, industry affiliation, static valuation and some trading indicators.",
        "preferred_access": ["get_stock_basic_info", "get_industry_peer_basic_info", "summarize_industry_valuation"],
        "query_keys": ["symbol", "code", "source"],
    },
    {
        "collection": "market_quotes",
        "purpose": "Fields related to near-real-time market conditions, rise and fall, turnover and market opening.",
        "preferred_access": ["get_market_quotes"],
        "query_keys": ["symbol", "code"],
    },
    {
        "collection": "stock_daily_quotes",
        "purpose": "Historical daily/K lines are used for price trends, interval statistics, and technical indicator calculations.",
        "preferred_access": ["get_stock_daily_quotes"],
        "query_keys": ["symbol", "trade_date", "period", "data_source"],
    },
    {
        "collection": "stock_financial_data",
        "purpose": "Financial statements and key financial indicators for use in fundamental analysis and valuation calculations.",
        "preferred_access": ["get_stock_financial_data"],
        "query_keys": ["symbol", "report_period", "data_source", "report_type"],
    },
    {
        "collection": "stock_financial_periods",
        "purpose": "Based on standardized financial records after the reporting period, it is suitable for year-on-year, month-on-month, and multi-period quality and growth factor calculations.",
        "preferred_access": ["get_stock_financial_periods"],
        "query_keys": ["symbol", "report_period", "ann_date", "source"],
    },
    {
        "collection": "stock_news",
        "purpose": "Stock-related news, announcements, research reports and event streams.",
        "preferred_access": ["get_stock_news", "get_stock_news_by_date_range"],
        "query_keys": ["symbol", "publish_time", "source"],
    },
]


def list_supported_stock_collections() -> List[Dict[str, Any]]:
    """Returns the local collection directory that the Skill is allowed to access.

    Returns:
        list[dict]: Collection description list, each element field description——
            collection: Collection name (such as "stock_basic_info" / "market_quotes" / "stock_daily_quotes" /
                "stock_financial_data" / "stock_financial_periods" / "stock_news"）
            purpose: Collection purpose description
            preferred_access: List of helper function names recommended for accessing this collection
            query_keys: A list of query key names supported by this collection (such as ["symbol", "code", "source"]) 
    """
    return list(STOCK_COLLECTION_SUMMARY)


def list_supported_external_sources(market_category: str = "a_shares") -> List[str]:
    """Returns supported external data sources for a market.

    Args:
        market_category: Market category, default is "a_shares". Optional values:"a_shares" / "hk_stocks" / "us_stocks"

    Returns:
        list[str]: List of supported external data source names (such as ["tushare", "akshare", "baostock"]) ; 
            Unconfigured market categories return empty list
    """
    return list(SUPPORTED_EXTERNAL_SOURCES.get(market_category, ()))


def list_configured_external_sources(market_category: str = "a_shares") -> List[str]:
    """Returns the external data sources enabled by the current configuration, filtering local and unsupported data sources.

    Args:
        market_category: Market category, default is "a_shares". Optional values:"a_shares" / "hk_stocks" / "us_stocks"

    Returns:
        list[str]: List of currently enabled and supported external data source names, the element is a data source name string
    """
    configured = get_enabled_data_sources_sync(market_category=market_category)
    allowed = set(list_supported_external_sources(market_category))
    return [item for item in configured if item in allowed]