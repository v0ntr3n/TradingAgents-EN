"""
Get account information tool

Obtain the user s capital account information for position analysis
"""

import asyncio
import logging
from typing import Any, Annotated, Dict

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _sum_currencies(d: Dict[str, float]) -> float:
    """Aggregate multi-currency dictionaries into a single value (simplified presentation)"""
    return round(sum(v for v in d.values() if isinstance(v, (int, float))), 2)


@register_tool(
    tool_id="get_account_info",
    name="获取账户信息",
    description="Obtain user fund account information and return account snapshots such as total assets, cash, position market value, profit and loss and percentage, initial funds, accumulated deposits and withdrawals, and multi-currency summary.",
    category="trade_review",
    is_online=False,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["account_info", "account_balance", "portfolio", "trade_review", "trading", "cash", "positions_value", "total_assets", "profit"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["account_balance_query", "portfolio_analysis", "position_value_check", "capital_summary"],
)
def get_account_info(
    user_id: Annotated[str, "用户ID"]
) -> Dict[str, Any]:
    """
    Get account information

    Args:
        user_id: User ID

    Returns:
        Dictionary containing account information
    """
    try:
        from app.services.portfolio_service import get_portfolio_service

        async def _fetch_account():
            service = get_portfolio_service()
            return await service.get_account_summary(user_id)

        import threading

        container = {}

        def _run_in_thread():
            try:
                container["result"] = asyncio.run(_fetch_account())
            except Exception as exc:
                container["error"] = exc

        t = threading.Thread(target=_run_in_thread)
        t.start()
        t.join(timeout=30)
        if "error" in container:
            raise container["error"]
        account_summary = container["result"]

        account_info = {
            "total_assets": account_summary.total_assets,
            "cash": account_summary.cash,
            "positions_value": account_summary.positions_value,
            "profit": account_summary.profit,
            "profit_pct": account_summary.profit_pct,
            "initial_capital": account_summary.initial_capital,
            "total_deposit": account_summary.total_deposit,
            "total_withdraw": account_summary.total_withdraw,
            "total_assets_sum": _sum_currencies(account_summary.total_assets),
            "cash_sum": _sum_currencies(account_summary.cash),
            "positions_value_sum": _sum_currencies(account_summary.positions_value),
            "profit_sum": _sum_currencies(account_summary.profit),
        }

        logger.info("✅ Obtained account information successfully: total assets=%s", account_info["total_assets"])

        return {
            "success": True,
            "data": account_info
        }

    except Exception as e:
        logger.error(f"❌ 获取账户信息失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }

