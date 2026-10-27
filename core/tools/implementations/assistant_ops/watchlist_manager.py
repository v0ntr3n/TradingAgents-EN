"""
Stock watch list management tools

Provides functions for querying, adding stocks, and removing stocks grouped by stock watchlists.
User identity is obtained through core.tools.context.
"""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_watchlist_groups",
    name="查看股票关注列表分组",
    description="Lists the user s stock watchlist groups, showing the group name, stock number, and stock symbol preview. Note: This is a grouped view, which is not equal to the complete stock watch list itself, nor is it equal to the scheduled analysis configuration.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["watchlist", "group", "list", "query", "assistant_ops", "stock_group", "watchlist_group", "stock_watchlist", "portfolio_group", "self_selected", "watchlist_query"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看股票关注列表分组", "股票关注列表列表", "分组查询", "股票池查看"],
    when_to_use="Used when users want to view their own stock watch list group list and understand which stocks are included in each group.",
    returns="Returns a grouped list of stock watchlists in text format, each containing group ID, name, stock number and stock code preview.",
)
async def list_watchlist_groups() -> str:
    """Lists the current user s stock watch list groups and the number of stocks in each group."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    cursor = db.watchlist_groups.find({"user_id": user_id}).sort("sort_order", 1)

    groups = []
    async for doc in cursor:
        gid = str(doc["_id"])
        name = doc.get("name", "未命名")
        stocks = doc.get("stock_codes", [])
        active = "✅" if doc.get("is_active", True) else "⏸️"
        preview = ", ".join(stocks[:5])
        if len(stocks) > 5:
            preview += f" +{len(stocks) - 5}"
        groups.append(f"  {active} [{gid[:8]}] {name}（{len(stocks)}只）: {preview}")

    if not groups:
        return "📂 There is currently no stock watch list grouping. You can ask me to create one for you.\n\n Tip: Grouping is just a way of organizing; to see the full stock watchlist, use View stock watchlist . "
    return (
        f"📂 共 {len(groups)} 个股票关注列表分组：\n"
        + "\n".join(groups)
        + "\n\n Note: The above is the group view of your stock watch list, which is not equal to the complete stock watch list, nor is it equal to the scheduled analysis configuration."
        + "To see the full list of stocks to watch, call View stock watchlist ; To view the automated analysis schedule, call View scheduled analysis configuration . "
    )


@tool
@register_tool(
    tool_id="add_stock_to_watchlist",
    name="Add a stock to a stock watchlist group",
    description="Adds one or more stocks to the specified named Stock Watchlist group. Automatically create a new group if the group does not exist. Note: This is only group management and does not mean that it will automatically enter scheduled analysis.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["watchlist", "group", "add", "stock", "assistant_ops", "stock_add", "watchlist_add", "portfolio_management", "self_selected", "stock_code", "watchlist_management"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["添加股票关注列表", "加入股票分组", "股票关注列表管理", "新建股票分组"],
    when_to_use="This is used when the user wants to add one or more stocks to a stock watch list group, or needs to create a new group and add stocks.",
    returns="Returns a text message, prompting the number of new stocks and the total number of current stocks in the group; when creating a new group, returns the group creation result.",
)
async def add_stock_to_watchlist(
    group_name: Annotated[str, "Stock watch list group name, such as Technology stocks "],
    symbols: Annotated[str, "Stock codes to add, separated by commas, such as 000001,600519"],
) -> str:
    """Adds one or more stocks to the specified named Stock Watchlist group. The group is automatically created if it does not exist."""
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return "❌ Please provide at least one ticker symbol."

    # Find groups by name
    group = await db.watchlist_groups.find_one({"user_id": user_id, "name": group_name})

    if group:
        # Already grouped, add stocks (remove duplicates)
        current = set(group.get("stock_codes", []))
        new_codes = set(symbol_list) - current
        if not new_codes:
            return f"ℹ️ 这些股票已在分组「{group_name}」中，无需重复添加。"
        updated = list(current | set(symbol_list))
        await db.watchlist_groups.update_one(
            {"_id": group["_id"]},
            {"$set": {"stock_codes": updated, "updated_at": now_tz()}},
        )
        return (
            f"✅ 已添加 {len(new_codes)} 只股票到「{group_name}」\n"
            f"- New: {', '.join(sorted(new_codes))}\n"
            f"- The group currently has a total of {len(updated)} only stocks"
        )
    else:
        # Automatically create groups
        max_sort_doc = await db.watchlist_groups.find_one(
            {"user_id": user_id}, sort=[("sort_order", -1)]
        )
        next_sort = (max_sort_doc["sort_order"] + 1) if max_sort_doc else 0

        new_doc = {
            "user_id": user_id,
            "name": group_name,
            "description": "",
            "color": "#409EFF",
            "icon": "folder",
            "stock_codes": symbol_list,
            "analysis_depth": None,
            "quick_analysis_model": None,
            "deep_analysis_model": None,
            "prompt_template_id": None,
            "sort_order": next_sort,
            "is_active": True,
            "created_at": now_tz(),
            "updated_at": now_tz(),
        }
        await db.watchlist_groups.insert_one(new_doc)
        return (
            f"✅ 已自动创建分组「{group_name}」并添加 {len(symbol_list)} 只股票\n"
            f"- stocks: {', '.join(symbol_list)}"
        )


@tool
@register_tool(
    tool_id="remove_stock_from_watchlist",
    name="Remove a stock from a stock watchlist group",
    description="Removes one or more stocks from the specified stock watchlist grouping. The group itself will not be deleted, nor will existing scheduled analysis configurations be affected.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["watchlist", "group", "remove", "stock", "assistant_ops", "stock_remove", "watchlist_remove", "portfolio_management", "self_selected", "stock_delete", "watchlist_management"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["移除股票关注列表", "删除股票分组中的股票", "股票关注列表管理", "清理股票池"],
    when_to_use="Used when the user wants to remove one or more stocks from the stock watch list group and clear out stocks that are no longer followed.",
    returns="Returns a text message indicating the number of shares to remove and the number of shares remaining in the group.",
)
async def remove_stock_from_watchlist(
    group_name: Annotated[str, "股票关注列表分组名称"],
    symbols: Annotated[str, "Stock symbols to remove, comma separated"],
) -> str:
    """Removes one or more stocks from the specified stock watchlist grouping."""
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return "❌ Please provide at least one ticker symbol."

    group = await db.watchlist_groups.find_one({"user_id": user_id, "name": group_name})
    if not group:
        return f"❌ 未找到分组「{group_name}」。可以用「查看股票关注列表分组」查看现有分组。"

    current = set(group.get("stock_codes", []))
    to_remove = set(symbol_list) & current
    if not to_remove:
        return f"ℹ️ 这些股票不在分组「{group_name}」中。"

    remaining = list(current - to_remove)
    await db.watchlist_groups.update_one(
        {"_id": group["_id"]},
        {"$set": {"stock_codes": remaining, "updated_at": now_tz()}},
    )
    return (
        f"✅ 已从「{group_name}」移除 {len(to_remove)} 只股票\n"
        f"- Remove: {', '.join(sorted(to_remove))}\n"
        f"- Group remaining {len(remaining)} only stocks"
    )

