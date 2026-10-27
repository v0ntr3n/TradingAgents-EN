"""Use the Q&A robot tool: Check the status of your demo trading account.

Allows using Q&A Assistant to"see"The user s current simulated trading account status, including:
- Total assets, available funds, position market value
- Realized profit and loss, floating profit and loss
- Number of stocks held, number of profitable/losing stocks
- Position details (up to 10 stocks)

Avoid robots guessing answers based on FAQs, and when encountering problems related to simulated trading, directly adjust the tool to see the real status.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _format_money(value: Optional[float]) -> str:
    """Format the amount as a Chinese readable string."""
    if value is None:
        return "未知"
    try:
        v = float(value)
        if abs(v) >= 100_000_000:
            return f"{v / 100_000_000:.2f} 亿"
        if abs(v) >= 10_000:
            return f"{v / 10_000:.2f} 万"
        return f"{v:.2f} 元"
    except Exception:
        return str(value)


def _format_pnl(value: Optional[float]) -> str:
    """Format profit and loss amount (with sign)."""
    if value is None:
        return "未知"
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{_format_money(v)}"
    except Exception:
        return str(value)


async def _get_paper_account(db, user_id: str) -> Optional[Dict[str, Any]]:
    """Get or create a paper trading account."""
    try:
        # Compatible user_id is ObjectId or string
        from bson import ObjectId
        uid = user_id
        try:
            uid = ObjectId(user_id)
        except Exception:
            pass

        acc = await db["paper_accounts"].find_one({"user_id": uid})
        if not acc:
            # Try the string form
            acc = await db["paper_accounts"].find_one({"user_id": user_id})
        if not acc:
            # Check whether there is an initialized account
            acc = await db["paper_accounts"].find_one({"user_id": uid, "status": "active"})
        return acc
    except Exception as exc:
        logger.warning("[get_paper_trading_status] Failed to query demo account: %s", exc)
        return None


async def _get_paper_positions(db, user_id: str) -> List[Dict[str, Any]]:
    """Get the list of positions."""
    try:
        from bson import ObjectId
        uid = user_id
        try:
            uid = ObjectId(user_id)
        except Exception:
            pass

        cursor = db["paper_positions"].find({"user_id": uid})
        docs = await cursor.to_list(length=50)
        if not docs:
            docs = await db["paper_positions"].find({"user_id": user_id}).to_list(length=50)
        return docs or []
    except Exception as exc:
        logger.warning("[get_paper_trading_status] Failed to query position: %s", exc)
        return []


async def _get_latest_prices(db, codes: List[str]) -> Dict[str, Optional[float]]:
    """Get the latest prices in batches (from the market_quotes or historical_data collection)."""
    prices: Dict[str, Optional[float]] = {}
    if not codes:
        return prices
    try:
        for code in codes:
            # Take priority from the market_quotes collection
            quote = await db["market_quotes"].find_one({"code": code}, sort=[("updated_at", -1)])
            if quote and quote.get("last_price"):
                prices[code] = float(quote["last_price"])
                continue
            # Go back to historical_data and get the latest one
            hist = await db["historical_data"].find_one({"symbol": code}, sort=[("date", -1)])
            if hist and hist.get("close"):
                prices[code] = float(hist["close"])
            else:
                prices[code] = None
    except Exception as exc:
        logger.warning("[get_paper_trading_status] Failed to get latest price: %s", exc)
    return prices


@tool
@register_tool(
    tool_id="get_paper_trading_status",
    name="查询模拟交易账户状态",
    description="Query the current user s simulated trading account status: total assets, available funds, market value of positions, realized profit and loss, floating profit and loss, number of stocks held, and number of stocks with profits and losses. When the user asks'How much does a demo account cost?''What s the profit and loss today?''How much money is left''How many stocks are held?''Which one loses the most?'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "paper_trading", "portfolio", "account_balance", "pnl", "positions", "virtual_trading"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "模拟账户多少钱",
        "模拟交易总资产",
        "今天盈亏多少",
        "可用资金还有多少",
        "持仓几只股票",
        "哪只股票亏得最多",
        "持仓股票盈亏情况",
        "模拟交易账户状态",
    ],
    when_to_use="It is used when the user asks about the simulated trading account balance, available funds, number of positions, and profit and loss.",
    returns="Returns a simulated trading account summary in text format, including total assets, available funds, market value of positions, profit and loss, and list of stocks held.",
)
async def get_paper_trading_status() -> str:
    """Check the status of simulated trading account."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    acc = await _get_paper_account(db, user_id)
    if not acc:
        return (
            "📊 Demo trading account status\n"
            "\n"
            "❌ You have not opened a demo trading account yet\n"
            "\n"
            "💡 Tip: You can go to the dashboard and click the Simulated Trading Total Assets card, or select the Simulated Trading menu in the sidebar."
            "When you enter for the first time, a virtual account will be automatically opened for you (initial capital is 1 million)."
        )

    positions = await _get_paper_positions(db, user_id)

    # Parse funds information (multi-currency format)
    cash_dict = acc.get("cash", {})
    realized_pnl_dict = acc.get("realized_pnl", {})

    # Compatible with old formats (single cash)
    if not isinstance(cash_dict, dict):
        cash_dict = {"CNY": float(cash_dict or 0)}
    if not isinstance(realized_pnl_dict, dict):
        realized_pnl_dict = {"CNY": float(realized_pnl_dict or 0)}

    # Get the latest price of the held stock
    codes = [p.get("code") for p in positions if p.get("code")]
    prices = await _get_latest_prices(db, codes)

    # Calculate the market value of positions (simplified in CNY)
    positions_value_cny = 0.0
    floating_pnl_cny = 0.0
    enriched_positions: List[Dict[str, Any]] = []

    for p in positions:
        code = p.get("code", "?")
        name = p.get("name", "") or code
        qty = int(p.get("quantity", 0) or 0)
        avg_cost = float(p.get("avg_cost", 0) or 0.0)
        last_price = prices.get(code)
        mkt_value = (last_price or 0.0) * qty
        floating = (last_price - avg_cost) * qty if last_price is not None else None

        positions_value_cny += mkt_value
        if floating is not None:
            floating_pnl_cny += floating

        enriched_positions.append({
            "code": code,
            "name": name,
            "quantity": qty,
            "avg_cost": avg_cost,
            "last_price": last_price,
            "market_value": round(mkt_value, 2),
            "floating_pnl": round(floating, 2) if floating is not None else None,
            "floating_pnl_pct": (
                round(((last_price - avg_cost) / avg_cost) * 100, 2)
                if last_price is not None and avg_cost > 0 else None
            ),
        })

    cash_cny = float(cash_dict.get("CNY", 0) or 0)
    realized_pnl_cny = float(realized_pnl_dict.get("CNY", 0) or 0)
    total_assets = cash_cny + positions_value_cny
    total_pnl = realized_pnl_cny + floating_pnl_cny

    # Profit and loss statistics of held stocks
    profit_count = sum(1 for p in enriched_positions if (p.get("floating_pnl") or 0) > 0)
    loss_count = sum(1 for p in enriched_positions if (p.get("floating_pnl") or 0) < 0)
    flat_count = sum(1 for p in enriched_positions if (p.get("floating_pnl") or 0) == 0)

    # Find the stocks with the most losses and profits
    worst_position = None
    best_position = None
    if enriched_positions:
        with_pnl = [p for p in enriched_positions if p.get("floating_pnl") is not None]
        if with_pnl:
            worst_position = min(with_pnl, key=lambda x: x["floating_pnl"])
            best_position = max(with_pnl, key=lambda x: x["floating_pnl"])

    # Formatted output
    lines = ["📊 模拟交易账户状态"]
    lines.append("")
    lines.append("【1】资产概览")
    lines.append(f"- 总资产: {_format_money(total_assets)}")
    lines.append(f"- 可用资金: {_format_money(cash_cny)}")
    lines.append(f"- 持仓市值: {_format_money(positions_value_cny)}")
    lines.append("")
    lines.append("【2】盈亏情况")
    lines.append(f"- Total profit and loss(Realized+float): {_format_pnl(total_pnl)}")
    lines.append(f"- 已实现盈亏: {_format_pnl(realized_pnl_cny)}")
    lines.append(f"- 浮动盈亏: {_format_pnl(floating_pnl_cny)}")
    lines.append("")
    lines.append("【3】持仓统计")
    lines.append(f"- 持仓股票数: {len(enriched_positions)}")
    lines.append(f"- 盈利/亏损/持平: {profit_count}/{loss_count}/{flat_count}")

    if best_position and (best_position.get("floating_pnl") or 0) > 0:
        lines.append(
            f"- 盈利最多: {best_position['name']}({best_position['code']}) "
            f"{_format_pnl(best_position['floating_pnl'])} "
            f"({best_position.get('floating_pnl_pct', 0):+}%)"
        )
    if worst_position and (worst_position.get("floating_pnl") or 0) < 0:
        lines.append(
            f"- 亏损最多: {worst_position['name']}({worst_position['code']}) "
            f"{_format_pnl(worst_position['floating_pnl'])} "
            f"({worst_position.get('floating_pnl_pct', 0):+}%)"
        )

    # Position details (up to 10 stocks)
    if enriched_positions:
        lines.append("")
        lines.append(" [4] Position details (up to 10 stocks)")
        sorted_positions = sorted(
            enriched_positions,
            key=lambda x: abs(x.get("market_value") or 0),
            reverse=True,
        )
        for p in sorted_positions[:10]:
            pnl_str = (
                f"{_format_pnl(p['floating_pnl'])} ({p.get('floating_pnl_pct', 0):+}%)"
                if p.get("floating_pnl") is not None else "无最新价"
            )
            last_price_str = f"{p['last_price']:.2f}" if p.get("last_price") is not None else "无"
            lines.append(
                f"  • {p['name']}({p['code']}) 数量 {p['quantity']} | "
                f"cost {p['avg_cost']:.2f} | latest price {last_price_str} | "
                f"Market value {_format_money(p['market_value'])} | float {pnl_str}"
            )

    # Account update time
    updated_at = acc.get("updated_at") or acc.get("created_at")
    if updated_at:
        if isinstance(updated_at, datetime):
            updated_str = updated_at.strftime("%Y-%m-%d %H:%M")
        else:
            updated_str = str(updated_at)[:19]
        lines.append("")
        lines.append(f"📌 账户最近更新: {updated_str}")

    # Comprehensive suggestions
    lines.append("")
    lines.append("💡 综合判断")
    if not enriched_positions:
        lines.append("- Currently short position, sufficient funds available. You can go to the Simulated Trading page to practice virtual operations")
    else:
        if floating_pnl_cny > 0:
            lines.append(f"- 当前持仓整体浮盈 {_format_pnl(floating_pnl_cny)}，可关注收益关注价位")
        elif floating_pnl_cny < 0:
            lines.append(f"- 当前持仓整体浮亏 {_format_pnl(floating_pnl_cny)}，可关注风险关注价位")
        else:
            lines.append("- 当前持仓整体持平")

        if cash_cny / max(total_assets, 1) < 0.1:
            lines.append("- ⚠️ Percentage of available funds < 10%, High capital utilization rate, pay attention to risks")
        elif cash_cny / max(total_assets, 1) > 0.9 and positions_value_cny > 0:
            lines.append("- Percentage of available funds > 90%, Low capital utilization rate")

    return "\n".join(lines)
