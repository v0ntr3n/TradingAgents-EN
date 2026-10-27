"""
Sector analysis tools

Provides sector performance analysis, rotation identification, peer comparison and other functions
These tools are for SectorAnalystV2 analysts
"""

import logging
from typing import Annotated
from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_analysis_data_source

logger = logging.getLogger(__name__)


def _resolve_sector_analysis_source() -> str:
    """Get the data sources that current industry analysis tools should use."""
    current_source = get_current_analysis_data_source()
    if current_source == "qmt":
        return "qmt"
    return "tushare"


def _is_tushare_available() -> bool:
    """Check if Tushare data source is available."""
    try:
        from app.services.data_sources.tushare_adapter import TushareAdapter
        return TushareAdapter().is_available()
    except Exception:
        return False


def _is_qmt_available() -> bool:
    """Check if the QMT data source is available."""
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        return QMTAdapter().is_available()
    except Exception:
        return False


def _tushare_unavailable_msg(dimensions: str) -> str:
    """Tushare Unified prompt when QMT is unavailable and cannot be replaced."""
    return (
        f"⚠️ The Tushare data source is currently unavailable,{dimensions}The data is only provided by Tushare, QMT does not support this dimension."
        f"Please give priority to the QMT industry analysis data returned by the get_sector_analysis tool."
    )


@tool
@register_tool(
    tool_id="get_sector_data",
    name="板块数据",
    description="Obtain the performance data of the sector to which the stock belongs and analyze industry trends, and return sector trend data information such as sector gains and losses, turnover, leading stocks, capital flows, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_data", "sector_performance", "industry_trend", "sector_ranking", "industry_analysis"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_performance_analysis", "industry_trend_evaluation", "sector_ranking_review"],
)
def get_sector_data(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20
) -> str:
    """
    Get performance data for the sector to which a stock belongs

    Analyze the recent performance of the industry sector to which the stock belongs, including gains and losses, capital flows, sector rankings, etc.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 20 days)

    Returns:
        str: Sector performance analysis report
    """
    try:
        from core.tools.sector_tools import get_sector_performance_sync
        return get_sector_performance_sync(ticker, trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取板块数据失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to obtain sector data, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
                report = get_sector_analysis_qmt_enhanced(ticker, trade_date, lookback_days)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取板块数据失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取板块数据失败: {e}"


@tool
@register_tool(
    tool_id="get_fund_flow_data",
    name="资金流向",
    description=(
        "Obtain sector fund flow data and analyze main fund trends, sector net fund inflows/outflows, and sector rotations."
        "Here s Fund flow It refers to the capital side of the trading market, not operating cash flow, investment cash flow, financing cash flow or free cash flow in financial statements."
    ),
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["fund_flow", "capital_flow", "sector_rotation", "main_capital", "liquidity_flow"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_capital_flow_analysis", "sector_rotation_identification", "main_capital_tracking"],
    when_to_use="Use it when you need evidence of sector capital flows, main capital inflows and outflows, and industry rotation capital.",
    when_not_to_use="It is not used for cash flow statement analysis, cash flow deterioration, profit content, financial risk or individual stock financial cash flow quality judgment; these needs should use cash flow/financial risk tools.",
)
def get_fund_flow_data(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    top_n: Annotated[int, "Returns the first N sections, default 10"] = 10,
    lookback_days: Annotated[int, "Looking back the number of days,1=On that day only,30=Accumulated in the last month, default 1"] = 1
) -> str:
    """
    Obtain sector fund flow data

    Analyze the inflow and outflow of funds in each sector, and identify the main capital trends and sector rotation trends.
    Supports single-day snapshots (lookback_days=1) and multi-day cumulative aggregation (lookback_days>1) Two modes.

    Args:
        trade_date: Closing transaction date (format: YYYY-MM-DD)
        top_n: Return the first N sections (default 10)
        lookback_days: Looking back the number of days,1=On that day only,30=Accumulated in the last month (default 1)

    Returns:
        str: Sector capital flow analysis report
    """
    try:
        from core.tools.sector_tools import get_sector_rotation_sync
        return get_sector_rotation_sync(trade_date, top_n, lookback_days)
    except Exception as e:
        logger.error(f"获取资金流向失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("板块资金流向")
        return f"❌ 获取资金流向失败: {e}"


@tool
@register_tool(
    tool_id="get_peer_comparison",
    name="同业对比",
    description="Obtain comparative data of stocks in the same industry to analyze the position of individual stocks in the industry, and return to peer comparison tables such as market capitalization, PE, PB, ROE, increase and decrease rankings, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["peer_comparison", "industry_ranking", "competitor_analysis", "competitive_positioning"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["peer_comparison_analysis", "industry_ranking_evaluation", "competitive_positioning"],
)
def get_peer_comparison(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    top_n: Annotated[int, "Returns the top N peer stocks, default 10"] = 10
) -> str:
    """
    Get comparative data on stocks in the same industry

    Analyze the performance ranking of target stocks in the same industry, including comparisons in terms of increase and decrease, market value, valuation and other dimensions.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)
        top_n: Returns the top N peer stocks (default 10)

    Returns:
        str: Comparative analysis report of peers
    """
    try:
        from core.tools.sector_tools import get_peer_comparison_sync
        return get_peer_comparison_sync(ticker, trade_date, top_n)
    except Exception as e:
        logger.error(f"获取同业对比失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to obtain peer comparison, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
                report = get_sector_analysis_qmt_enhanced(ticker, trade_date, 20, top_n)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取同业对比失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取同业对比失败: {e}"


@tool
@register_tool(
    tool_id="get_industry_top_companies",
    name="同行业TOP公司",
    description="Obtain a list of the top N companies in the same industry by market capitalization, suitable for quickly understanding the industry competition landscape and peer comparison.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["industry_top_companies", "industry_leaders", "competitive_landscape", "market_cap_ranking", "moat_analysis"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["industry_leader_identification", "competitive_landscape_overview", "market_cap_ranking_review"],
)
def get_industry_top_companies(
    ticker: Annotated[str, "Stock code (such as 600519 or 600519.SH)"],
    top_n: Annotated[int, "Returns the top N companies in the same industry, default 5"] = 5
) -> str:
    """
    Get the list of TOP N companies in the same industry (light version)

    Automatically identify the industry to which the stock belongs, and return the top N companies in the same industry sorted by market value.
    Contains key indicators such as code, name, market capitalization, PE, PB, etc.
    There is no need to enter the transaction date, and the latest transaction day data will be automatically obtained.

    Args:
        ticker: Stock code (such as 600519 or 600519.SH)
        top_n: Return the top N companies in the same industry (default 5)

    Returns:
        str: Brief list of TOP N companies in the same industry
    """
    try:
        from core.tools.sector_tools import get_industry_top_companies_sync
        return get_industry_top_companies_sync(ticker, top_n)
    except Exception as e:
        logger.error(f"Failed to obtain TOP company in the same industry: {e}")
        return f"❌ Failed to obtain TOP company in the same industry: {e}"


@tool
@register_tool(
    tool_id="analyze_sector",
    name="综合板块分析",
    description="Comprehensive analysis of the sector to which the stock belongs includes performance rotation, peer comparison, etc. Returns comprehensive analysis reports on sector performance, rotation signals, peer comparison, capital flow, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "sector_performance", "sector_rotation", "peer_comparison", "comprehensive_sector"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["comprehensive_sector_analysis", "multi_dimension_sector_evaluation", "integrated_industry_review"],
)
def analyze_sector(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Comprehensive sector analysis

    Integrate multi-dimensional data such as sector performance, capital flow, and peer comparison to provide a comprehensive sector analysis report.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Comprehensive sector analysis report
    """
    try:
        from core.tools.sector_tools import analyze_sector_sync
        return analyze_sector_sync(ticker, trade_date)
    except Exception as e:
        logger.error(f"综合板块分析失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Comprehensive sector analysis failed, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
                report = get_sector_analysis_qmt_enhanced(ticker, trade_date, 20, 10)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 综合板块分析失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 综合板块分析失败: {e}"


@tool
@register_tool(
    tool_id="get_sector_analysis",
    name="统一行业分析",
    description="Automatically select the QMT or Tushare path based on the current analysis data source and return unified industry analysis results.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "unified_analysis", "sector_performance", "data_source_routing", "comprehensive_industry"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["unified_sector_analysis", "multi_source_sector_evaluation", "comprehensive_industry_report"],
)
def get_sector_analysis(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20,
    top_n: Annotated[int, "Returns the first N results, default 10"] = 10
) -> str:
    """A unified industry analysis tool that automatically routes according to the current data source (QMT or Tushare) and returns integrated industry analysis reports.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: transaction date, format YYYY-MM-DD
        lookback_days: Number of days to look back, default 20
        top_n: Returns the first N results, default 10

    Returns:
        str: Markdown Format industry analysis report, composed of multiple sections, including —
            ## Sector performance: sector trends and rise and fall performance
            ## Sector Fund Flow Direction: Ranking of Sector Fund Inflows and Outflows
            ## Comparison with peers: Comparison of stocks in the same industry
        QMT Or when Tushare fails, it returns "❌" Error description string at the beginning
    """
    source = _resolve_sector_analysis_source()

    if source == "qmt":
        try:
            from core.tools.qmt_market_tools import get_sector_analysis_qmt_enhanced
            return get_sector_analysis_qmt_enhanced(ticker, trade_date, lookback_days, top_n)
        except Exception as e:
            logger.error(f"QMT 行业分析失败: {e}")
            # QMT try when failed Tushare
            if _is_tushare_available():
                logger.info("QMT Industry analysis failed, try Tushare downgrade")
                try:
                    from core.tools.sector_tools import analyze_sector_sync
                    return analyze_sector_sync(ticker, trade_date)
                except Exception as ts_e:
                    return f"❌ Industry analysis failed: QMT={e}, Tushare={ts_e}"
            return f"❌ QMT Industry analysis failed: {e}"

    sections = []
    tool_calls = [
        ("板块表现", lambda: get_sector_data.invoke({"ticker": ticker, "trade_date": trade_date, "lookback_days": lookback_days})),
        ("板块资金流向", lambda: get_fund_flow_data.invoke({"trade_date": trade_date, "top_n": top_n, "lookback_days": 1})),
        ("同业对比", lambda: get_peer_comparison.invoke({"ticker": ticker, "trade_date": trade_date, "top_n": top_n})),
    ]

    for title, producer in tool_calls:
        try:
            content = producer()
        except Exception as exc:
            logger.error(f"统一行业分析组装失败 [{title}]: {exc}")
            content = f"❌ {title} 获取失败: {exc}"
        sections.append(f"## {title}\n{content}")

    return "\n\n".join(sections)


# ============================================================
# Section level tools (use the section name as the entry, no ticker required)
# ============================================================

@tool
@register_tool(
    tool_id="search_sector",
    name="板块搜索",
    description="Search A-share sectors (industry/concept/region) by name keywords and return a list of matching sectors",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_search", "sector_lookup", "industry_classification", "concept_classification"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_lookup", "industry_classification_search", "sector_code_discovery"],
    when_to_use="Used when the user mentions keywords such as sector, industry, concept, etc. and needs to find the sector code first.",
)
def search_sector_tool(
    keyword: Annotated[str, "Sector name keywords (such as photovoltaic, semiconductor, liquor, new energy)"],
    sector_type: Annotated[str, "Section type: N=Industry sector I=Industry Index S=concept R=Region, default N"] = "N",
) -> str:
    """
    Search the Flush section by name and keywords

    Returns a list of matching sectors, including sector code, name, and number of constituent stocks.

    Args:
        keyword: Section name keywords
        sector_type: Section type (N=Industry, S=concept, R=region)

    Returns:
        str: Section search results
    """
    try:
        from core.tools.sector_tools import search_sector_sync
        return search_sector_sync(keyword, sector_type)
    except Exception as e:
        logger.error(f"板块搜索失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("Section search (flush section list)")
        return f"❌ 板块搜索失败: {e}"


@tool
@register_tool(
    tool_id="get_sector_daily",
    name="板块行情",
    description="Obtain the daily market data of the sector index, including rise and fall, trading volume, turnover rate, market value, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_daily", "sector_quote", "sector_index", "sector_trend", "sector_volume"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_index_quote", "sector_daily_performance", "sector_trend_review"],
    when_to_use="Used when users want to know the recent trend, rise and fall of a certain sector",
)
def get_sector_daily_tool(
    sector_name: Annotated[str, "Sector name keywords (such as photovoltaic, semiconductor, liquor)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20,
) -> str:
    """
    Get daily quotes of sector indexes

    Args:
        sector_name: Section name keywords
        trade_date: transaction date
        lookback_days: Number of days to look back

    Returns:
        str: Sector market report
    """
    try:
        from core.tools.sector_tools import get_sector_daily_sync
        return get_sector_daily_sync(sector_name, trade_date, lookback_days)
    except Exception as e:
        logger.error(f"板块行情获取失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("Sector Quotes (Daily Flush Sector Index)")
        return f"❌ 板块行情获取失败: {e}"


@tool
@register_tool(
    tool_id="get_sector_constituents",
    name="板块成分股",
    description="Obtain the list of constituent stocks of the sector and its market value and valuation ranking, and return the sorting table data information such as constituent stock code, name, market value, PE, PB, increase and decrease, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_constituents", "sector_members", "sector_leaders", "constituent_ranking"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sector_member_listing", "sector_leader_identification", "constituent_ranking_review"],
    when_to_use="Used when users want to know which stocks are in a certain sector and which are the leading stocks.",
)
def get_sector_constituents_tool(
    sector_name: Annotated[str, "Sector name keywords (such as photovoltaic, semiconductor, liquor)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    top_n: Annotated[int, "Returns the top N constituent stocks, default 15"] = 15,
) -> str:
    """
    Get the list of sector constituent stocks and their performance

    Args:
        sector_name: Section name keywords
        trade_date: transaction date
        top_n: Return the top N constituent stocks

    Returns:
        str: Sector constituent stock report
    """
    try:
        from core.tools.sector_tools import get_sector_constituents_sync
        return get_sector_constituents_sync(sector_name, trade_date, top_n)
    except Exception as e:
        logger.error(f"板块成分股获取失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("Sector constituent stocks (flush sector constituent list)")
        return f"❌ 板块成分股获取失败: {e}"


@tool
@register_tool(
    tool_id="analyze_sector_by_name",
    name="板块综合分析",
    description="Comprehensive analysis by sector name, integrating sector market conditions, leading constituent stocks, and market-wide capital flows",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "sector_comprehensive", "sector_performance", "fund_flow", "sector_leaders"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["sector_comprehensive_analysis", "sector_investment_opportunity", "multi_dimension_sector_review"],
    when_to_use="Used when users ask about investment opportunities, sector analysis, and industry prospects of a certain sector.",
)
def analyze_sector_by_name_tool(
    sector_name: Annotated[str, "Sector name keywords (such as photovoltaics, semiconductors, liquor, new energy vehicles)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Comprehensive analysis of sectors (use sector name as entry)

    Args:
        sector_name: Section name keywords
        trade_date: transaction date

    Returns:
        str: Comprehensive sector analysis report
    """
    try:
        from core.tools.sector_tools import analyze_sector_by_name_sync
        return analyze_sector_by_name_sync(sector_name, trade_date)
    except Exception as e:
        logger.error(f"板块综合分析失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("Comprehensive analysis of sectors (flush sector system)")
        return f"❌ 板块综合分析失败: {e}"
