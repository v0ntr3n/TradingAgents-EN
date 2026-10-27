"""QMT Market and sector analysis tools in mode."""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced, get_sector_analysis_qmt_enhanced

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_market_overview_qmt",
    name="QMT 大盘概览",
    description="Based on QMT index prices, market-wide snapshots and activity proxy indicators, a broad market analysis report is generated.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_overview", "qmt", "index_data", "market_breadth", "market_activity"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["qmt_market_overview", "market_breadth_analysis", "market_activity_assessment"],
)
def get_market_overview_qmt(
    trade_date: Annotated[str, "Analysis date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60,
) -> str:
    """Based on QMT index prices, market-wide snapshots and activity proxy indicators, a broad market analysis report is generated.

    Args:
        trade_date: Analysis date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 60 days)

    Returns:
        str: Market analysis report
    """
    try:
        return get_market_overview_qmt_enhanced(trade_date, lookback_days)
    except Exception as exc:
        logger.error(f"QMT 大盘概览失败: {exc}")
        return f"❌ QMT Market overview failed: {exc}"


@tool
@register_tool(
    tool_id="get_sector_analysis_qmt",
    name="QMT 板块分析",
    description="Based on QMT individual stock prices and local industry mapping, analyze the strength, weakness, leadership and diffusion within the industry.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["sector_analysis", "qmt", "industry_rotation", "peer_comparison", "sector_strength"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["qmt_sector_analysis", "industry_strength_comparison", "sector_leader_identification"],
)
def get_sector_analysis_qmt(
    ticker: Annotated[str, "Stock code (e.g. 600519, 000001)"],
    trade_date: Annotated[str, "Analysis date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 20 days"] = 20,
    top_n: Annotated[int, "Display the top N strong constituent stocks, default 10"] = 10,
) -> str:
    """Based on QMT individual stock prices and local industry mapping, analyze the strength, weakness, leadership and diffusion within the industry.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        trade_date: Analysis date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 20 days)
        top_n: Display the top N strong constituent stocks (default 10)

    Returns:
        str: Sector analysis report
    """
    try:
        return get_sector_analysis_qmt_enhanced(ticker, trade_date, lookback_days, top_n)
    except Exception as exc:
        logger.error(f"QMT 板块分析失败: {exc}")
        return f"❌ QMT Sector analysis failed: {exc}"
