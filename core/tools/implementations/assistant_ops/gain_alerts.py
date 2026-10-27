"""
Revenue attention reminder tools

Provides the ability to set, view, and clear revenue attention price (price upper limit) reminders to facilitate users to track, study, and observe prices by themselves.
"""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _normalize_market(market: str) -> str:
    value = (market or "CN").upper()
    if value in ("CN", "A股", "SH", "SZ"):
        return "A股"
    if value in ("HK", "港股"):
        return "港股"
    if value in ("US", "美股"):
        return "美股"
    return "A股"


@tool
@register_tool(
    tool_id="set_stop_gain_alert",
    name="设置收益关注提醒",
    description="Set a price limit (price limit) for stocks to pay attention to, and push notifications through the system when the price is close, making it easier for users to track, research and observe the price. Returns the stock name, symbol, market, and set earnings focus price.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["gain_alerts", "stop_gain", "alert", "set", "assistant_ops", "price_alert", "profit_taking", "notification", "alert_setup", "price_threshold"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["收益关注提醒设置", "收益关注价格配置", "价格上限提醒设置", "价格上限提醒"],
    when_to_use="This is used when the user wants to set a profit follow-up price (price ceiling) for a certain stock, and wants to receive a notification when the price rises to that price, so that he can follow the research and observation price by himself.",
    returns="Returns a text message containing the stock name, symbol, market, and set earnings focus price (price cap).",
)
async def set_stop_gain_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
    gain_price: Annotated[float, "Pay attention to the price limit (remind you when it reaches or approaches this price)"],
    market: Annotated[str, "Market: CN/HK/US, default CN"] = "CN",
) -> str:
    """Set stock earnings watch price (price cap) alerts."""
    try:
        from app.core.database import get_mongo_db
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        market_label = _normalize_market(market)
        db = get_mongo_db()

        name = symbol
        pos = await db.real_positions.find_one({"user_id": user_id, "code": symbol}, {"name": 1})
        if pos and pos.get("name"):
            name = pos["name"]

        exists = await favorites_service.is_favorite(user_id, symbol)
        if not exists:
            await favorites_service.add_favorite(
                user_id=user_id,
                stock_code=symbol,
                stock_name=name,
                market=market_label,
            )

        ok = await favorites_service.update_alert_gain_price(user_id, symbol, gain_price)
        if not ok:
            return f"未找到 {symbol} 的股票关注列表记录，设置收益关注提醒失败。"

        return (
            f"✅ 已设置收益关注提醒（价格上限）\n"
            f"- stocks: {name}({symbol})\n"
            f"- market: {market_label}\n"
            f"- Earnings focus on price: {gain_price:.2f}\n"
            f"When the price approaches or reaches the profit attention price, you will receive a system notification so that you can pay attention to, research and observe the price yourself."
        )
    except Exception as e:
        logger.exception("[set_stop_gain_alert] Failed to set revenue attention reminder: %s", e)
        return f"设置收益关注提醒失败: {e}"


@tool
@register_tool(
    tool_id="list_stop_gain_alerts",
    name="查看收益关注提醒",
    description="View all currently set revenue focus alerts (price caps). Returns the number of alerts and the stock name, symbol, market, and earnings focus price for each alert.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["gain_alerts", "stop_gain", "alert", "list", "query", "assistant_ops", "price_alert", "profit_taking", "alert_query", "notification_list"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["收益关注提醒查看", "收益关注列表查询", "已配置提醒浏览", "价格上限确认"],
    when_to_use="This is used when the user wants to view all currently set earnings focus reminders (price caps) and confirm which stocks have configured earnings focus prices.",
    returns="Returns a text message, including the number of earnings attention reminders and the stock, market, and earnings attention price (price limit) of each reminder.",
)
async def list_stop_gain_alerts() -> str:
    """View a list of configured revenue focus alerts (price caps)."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        items = await favorites_service.get_user_favorites(user_id)
        alerts = [item for item in items if item.get("alert_gain_price") is not None]

        if not alerts:
            return "There are currently no revenue focus alerts (price caps) set."

        lines = [f"共 {len(alerts)} 条收益关注提醒（价格上限）：\n"]
        for item in alerts:
            code = item.get("stock_code", "")
            name = item.get("stock_name", code)
            market = item.get("market", "A股")
            gain = item.get("alert_gain_price")
            lines.append(f"- {name}({code}) | {market} | 收益关注价格: {float(gain):.2f}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_stop_gain_alerts] Failed to view revenue attention reminder: %s", e)
        return f"查看收益关注提醒失败: {e}"


@tool
@register_tool(
    tool_id="clear_stop_gain_alert",
    name="清除收益关注提醒",
    description="Clear the earnings attention reminder price of the specified stock (price limit, only clear the reminder, do not remove the stock attention list). Returns the operation result or a prompt that the configuration is not found.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["gain_alerts", "stop_gain", "alert", "clear", "delete", "assistant_ops", "price_alert", "profit_taking", "alert_removal", "notification_cleanup"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["收益关注提醒清除", "收益关注价格移除", "提醒配置删除", "价格上限取消"],
    when_to_use="It is used when the user wants to clear the earnings attention reminder (price limit) of a certain stock and no longer receive earnings attention notifications for the stock (only clears the reminder, but does not remove the stock watch list).",
    returns="Return a text message to confirm that the revenue attention reminder has been cleared or that the relevant configuration is not found.",
)
async def clear_stop_gain_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
) -> str:
    """Clear earnings attention alerts (price caps) for a stock."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        ok = await favorites_service.update_alert_gain_price(user_id, symbol, None)
        if ok:
            return f"✅ 已清除 {symbol} 的收益关注提醒（价格上限）。"
        return f"未找到 {symbol} 的提醒配置，或该股票不在股票关注列表中。"
    except Exception as e:
        logger.exception("[clear_stop_gain_alert] Failed to clear earnings attention reminder: %s", e)
        return f"清除收益关注提醒失败: {e}"
