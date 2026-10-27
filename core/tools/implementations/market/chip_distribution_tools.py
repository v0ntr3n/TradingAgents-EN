"""
Chip distribution analysis tool

Provides chip distribution data acquisition function and supports AkShare (preferred) and Tushare (backup) data sources.
These tools are used with ChipDistributionAnalystV2 analysts.
"""

import logging
from typing import Annotated
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_chip_distribution",
    name="筹码分布",
    description="Obtain stock chip distribution data and analyze profit ratio, average cost and chip concentration (AkShare is preferred, Tushare is backup)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["chip_distribution", "cost_distribution", "profit_ratio", "chip_concentration", "holder_cost"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["chip_distribution_analysis", "cost_structure_analysis", "support_resistance_identification"],
)
def get_chip_distribution(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Obtain stock chip distribution data (unified interface)

    Analyze the chip distribution of stocks, including:
    - Profit ratio: the proportion of chips that make a profit at the current price
    - Average cost: the average holding cost of all position holders
    - 90%/70%Chip cost range: the cost range of concentrated positions
    - Chip concentration: the degree of concentration of chip distribution

    Data source priority: AkShare (东财) → Tushare (Official API)

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution analysis report
    """
    try:
        from core.tools.chip_distribution_tools import get_chip_distribution_sync
        return get_chip_distribution_sync(ticker, trade_date)
    except Exception as e:
        logger.error(f"获取筹码分布失败: {e}")
        return f"❌ 获取筹码分布失败: {e}"


@tool
@register_tool(
    tool_id="get_chip_distribution_akshare",
    name="Chip distribution(AkShare)",
    description="Obtain stock chip distribution data through AkShare (Oriental Fortune Data Source, free)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["chip_distribution", "akshare", "cost_distribution", "profit_ratio", "eastmoney"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["chip_distribution_via_akshare", "cost_structure_analysis", "free_data_source_chip"],
)
def get_chip_distribution_akshare_tool(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Get stock chip distribution data through AkShare

    Use the Oriental Fortune data interface to obtain A-share chip distribution information for free.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution data (JSON format) or error message
    """
    try:
        import json
        from core.tools.chip_distribution_tools import get_chip_distribution_akshare
        data = get_chip_distribution_akshare(ticker, trade_date)
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return f"❌ AkShare未能获取 {ticker} 的筹码分布数据"
    except Exception as e:
        logger.error(f"AkShare Failed to obtain chip distribution: {e}")
        return f"❌ AkShare Failed to obtain chip distribution: {e}"


@tool
@register_tool(
    tool_id="get_chip_distribution_tushare",
    name="Chip distribution(Tushare)",
    description="Obtain stock chip distribution data through Tushare (official API, requires 5,000 points)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["chip_distribution", "tushare", "cost_distribution", "cyq_perf", "profit_ratio"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["chip_distribution_via_tushare", "cost_structure_analysis", "official_api_chip"],
)
def get_chip_distribution_tushare_tool(
    ticker: Annotated[str, "Stock code (such as 000001 or 000001.SZ)"],
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
) -> str:
    """
    Obtain stock chip distribution data through Tushare (cyq_perf interface)

    Using Tushare s official API to obtain chip analysis data requires 5,000 points permission.
    Including: profit ratio (winner_rate), weighted average cost (weight_avg), each percentile cost price, etc.

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution data (JSON format) or error message
    """
    try:
        import json
        from core.tools.chip_distribution_tools import get_chip_distribution_tushare
        data = get_chip_distribution_tushare(ticker, trade_date)
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return f"❌ Tushare Failed to obtain {ticker} Chip distribution data (may require 5000 points permission)"
    except Exception as e:
        logger.error(f"Tushare Failed to obtain chip distribution: {e}")
        return f"❌ Tushare Failed to obtain chip distribution: {e}"

