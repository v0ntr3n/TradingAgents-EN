"""
Get Market Snapshot Tool

Obtain market data snapshots during the trading period for review analysis
"""

import logging
from typing import Dict, Any, Optional, Annotated
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    tool_id="get_market_snapshot_for_review",
    name="获取市场快照",
    description="Obtain K-line data and market snapshots during the trading period for review analysis, and return structured data such as K-line sequence, trading volume, technical indicators, and market environment labels during the period.",
    category="trade_review",
    is_online=True,
    data_source_handling="self_contained",
    capability_tags=["market_snapshot", "snapshot", "kline_data", "market_data", "trade_review", "trading", "review_analysis", "复盘"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["trade_review_analysis", "market_context_retrieval", "kline_data_fetch", "trade_period_review"],
)
def get_market_snapshot_for_review(
    code: Annotated[str, "股票代码"],
    market: Annotated[str, "market: 'CN'(A shares) or 'US'(US stocks)"],
    start_date: Annotated[Optional[str], "start date YYYY-MM-DD"] = None,
    end_date: Annotated[Optional[str], "end date YYYY-MM-DD"] = None
) -> Dict[str, Any]:
    """
    Get a market snapshot

    Args:
        code: Stock code
        market: market type
        start_date: start date
        end_date: end date

    Returns:
        Dictionary containing K-line data
    """
    try:
        from tradingagents.dataflows.interface import get_stock_data_unified
        from datetime import datetime, timedelta
        import asyncio

        if not start_date or not end_date:
            # By default, data of the last 3 months is obtained
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        # Extended date range (10 days before and after)
        query_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        query_end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=10)).strftime("%Y-%m-%d")

        async def _fetch_kline():
            # Get K-line data
            return await get_stock_data_unified(
                ticker=code,
                start_date=query_start,
                end_date=query_end,
                market_type=market.lower()
            )

        # Run asynchronous code in a synchronous context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        kline_data = loop.run_until_complete(_fetch_kline())

        logger.info(f"✅ 获取市场快照成功: {code}, {len(kline_data) if isinstance(kline_data, list) else 'N/A'} 条K线")

        return {
            "success": True,
            "data": {
                "code": code,
                "market": market,
                "start_date": start_date,
                "end_date": end_date,
                "kline_data": kline_data
            }
        }

    except Exception as e:
        logger.error(f"❌ 获取市场快照失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }

