"""
Risk reminder tools

Provides the ability to set, view, and clear price lower limit reminders to facilitate users to track risks by themselves.
"""

import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _normalize_market(market: str) -> str:
    m = (market or "CN").upper()
    if m in ("CN", "A股", "SH", "SZ"):
        return "A股"
    if m in ("HK", "港股"):
        return "港股"
    if m in ("US", "美股"):
        return "美股"
    return "A股"


@tool
@register_tool(
    tool_id="set_stop_loss_alert",
    name="设置价格下限提醒",
    description="Set a lower price limit reminder for a stock, and push notifications through the system when the price is close to or falls below, making it easier for users to track risks on their own. Returns the stock name, symbol, market and alert price.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["risk_alerts", "stop_loss", "alert", "set", "assistant_ops", "price_alert", "risk_management", "notification", "alert_setup", "price_threshold", "loss_prevention"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["价格下限提醒设置", "风险关注价格配置", "风险控制提醒", "价格下限提醒"],
    when_to_use="It is used when users want to set a lower price limit for a certain stock and want to be notified when the price falls below the threshold so that they can pay attention to the risk themselves.",
    returns="Returns a text message containing the stock name, symbol, market, and the price floor that has been set.",
)
async def set_stop_loss_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
    stop_loss_price: Annotated[float, "Price lower limit (alert when it is below or close to this price)"],
    market: Annotated[str, "Market: CN/HK/US, default CN"] = "CN",
) -> str:
    """Set a stock price floor reminder."""
    try:
        from app.services.favorites_service import favorites_service
        from app.core.database import get_mongo_db

        user_id = require_current_user_id()
        market_label = _normalize_market(market)
        db = get_mongo_db()

        # Try to complete the stock name from the position
        name = symbol
        pos = await db.real_positions.find_one({"user_id": user_id, "code": symbol}, {"name": 1})
        if pos and pos.get("name"):
            name = pos["name"]

        # If it does not exist, it will automatically be added to the stock watch list, and then the reminder threshold will be written.
        exists = await favorites_service.is_favorite(user_id, symbol)
        if not exists:
            await favorites_service.add_favorite(
                user_id=user_id,
                stock_code=symbol,
                stock_name=name,
                market=market_label,
                alert_price_low=stop_loss_price,
            )
        else:
            await favorites_service.update_favorite(
                user_id=user_id,
                stock_code=symbol,
                alert_price_low=stop_loss_price,
            )

        return (
            f"✅ 已设置价格下限提醒\n"
            f"- stocks: {name}({symbol})\n"
            f"- market: {market_label}\n"
            f"- price floor: {stop_loss_price:.2f}\n"
            f"When the price approaches or falls below the lower limit, you will receive a system notification so that you can pay attention to the risk yourself."
        )
    except Exception as e:
        logger.exception("[set_stop_loss_alert] Failed to set price minimum reminder: %s", e)
        return f"设置价格下限提醒失败: {e}"


@tool
@register_tool(
    tool_id="list_stop_loss_alerts",
    name="查看价格下限提醒",
    description="View all price floor alerts currently set. Returns the number of alerts and the stock name, symbol, market, and alert price for each alert.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["risk_alerts", "stop_loss", "alert", "list", "query", "assistant_ops", "price_alert", "risk_management", "alert_query", "notification_list"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["价格下限提醒查看", "价格下限列表查询", "已配置提醒浏览", "风险控制确认"],
    when_to_use="This is used when the user wants to view all currently set price lower limit reminders and confirm which stocks have configured price lower limits.",
    returns="Returns a text message, including the number of price lower limit reminders and the stock, market, and reminder price of each reminder.",
)
async def list_stop_loss_alerts() -> str:
    """View a list of configured price floor alerts."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        items = await favorites_service.get_user_favorites(user_id)
        alerts = [x for x in items if x.get("alert_price_low") is not None]

        if not alerts:
            return "There are currently no price floor alerts set."

        lines = [f"共 {len(alerts)} 条价格下限提醒：\n"]
        for it in alerts:
            code = it.get("stock_code", "")
            name = it.get("stock_name", code)
            market = it.get("market", "A股")
            low = it.get("alert_price_low")
            lines.append(f"- {name}({code}) | {market} | 价格下限: {float(low):.2f}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_stop_loss_alerts] Failed to check price lower limit reminder: %s", e)
        return f"查看价格下限提醒失败: {e}"


@tool
@register_tool(
    tool_id="clear_stop_loss_alert",
    name="清除价格下限提醒",
    description="Clear the lower price limit reminder for the specified stock (only clears the reminder, does not remove the stock watch list). Returns the operation result or a prompt that the configuration is not found.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["risk_alerts", "stop_loss", "alert", "clear", "delete", "assistant_ops", "price_alert", "risk_management", "alert_removal", "notification_cleanup"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["价格下限提醒清除", "风险关注价格移除", "提醒配置删除", "风险提醒取消"],
    when_to_use="It is used when the user wants to clear the price lower limit reminder of a certain stock and no longer receive the price lower limit notification of the stock (only clears the reminder and does not remove the stock watch list).",
    returns="Return a text message to confirm that the price lower limit reminder has been cleared or that the relevant configuration is not found.",
)
async def clear_stop_loss_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
) -> str:
    """Clear the price floor alert for a stock."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        ok = await favorites_service.update_favorite(
            user_id=user_id,
            stock_code=symbol,
            clear_alert_price_low=True,
        )
        if ok:
            return f"✅ 已清除 {symbol} 的价格下限提醒。"
        return f"未找到 {symbol} 的价格下限提醒配置，或该股票不在股票关注列表中。"
    except Exception as e:
        logger.exception("[clear_stop_loss_alert] Failed to clear price floor reminder: %s", e)
        return f"清除价格下限提醒失败: {e}"
