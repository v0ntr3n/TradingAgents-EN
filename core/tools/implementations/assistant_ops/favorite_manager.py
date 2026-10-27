"""
Stock watchlist list management tool

Provides the ability to add stocks to the stock watch list in batches, suitable for linking with intelligent stock selection results.
"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _normalize_market(market: str) -> str:
    value = (market or "A股").strip().upper()
    if value in ("A股", "CN", "SH", "SZ", "SSE", "SZSE", "BJ", "BSE"):
        return "A股"
    if value in ("港股", "HK", "HKEX"):
        return "港股"
    if value in ("美股", "US", "NASDAQ", "NYSE", "AMEX"):
        return "美股"
    return "A股"


def _parse_tags(tags: str) -> list[str]:
    raw = (tags or "").replace("，", ",").replace("、", ",")
    parsed = []
    seen = set()
    for item in raw.split(","):
        tag = item.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        parsed.append(tag)
    return parsed


@tool
@register_tool(
    tool_id="list_favorite_stocks",
    name="查看股票关注列表",
    description="View the user s stock watch list (that is, the stock watch list list), optionally filtering by tag. The ticker, name, market and existing tags are returned.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["favorite_management", "watchlist", "query", "list", "assistant_ops", "stock_favorites", "stock_watchlist", "tag_filter", "favorites_view", "self_selected_stocks"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看股票关注列表列表", "浏览关注的股票", "按标签筛选股票关注列表", "确认已关注的股票"],
    when_to_use="It is used when users want to view their own stock watch list, stock watch list, or filter the stocks they have followed by tags.",
    returns="Returns a list of stock watchlists in text format, containing stock name, symbol, market, and existing tags.",
)
async def list_favorite_stocks(
    tag: Annotated[str, "Optional, filter by tag, such as Buffett; leave blank to view all stocks of interest"] = "",
) -> str:
    """View the current user s stock watch list (i.e. stock watch list), and supports filtering by tags."""
    from app.services.favorites_service import favorites_service

    user_id = require_current_user_id()
    favorites = await favorites_service.get_user_favorites(user_id)

    normalized_tag = str(tag or "").strip()
    if normalized_tag:
        favorites = [
            item for item in favorites
            if normalized_tag in list(item.get("tags") or [])
        ]

    if not favorites:
        if normalized_tag:
            return f"📂 There are no stocks in your watchlist tagged {normalized_tag}] of stocks."
        return "📂 Your stock watchlist is currently empty, no stocks have been added to your watchlist yet."

    lines = []
    for item in favorites:
        code = item.get("stock_code") or "-"
        name = item.get("stock_name") or code
        market = item.get("market") or "A股"
        tags = list(item.get("tags") or [])
        tag_text = f" | 标签: {', '.join(tags)}" if tags else ""
        lines.append(f"- {name} ({code}) | {market}{tag_text}")

    header = (
        f"📂 你的股票关注列表（标签：{normalized_tag}，共 {len(favorites)} 只）"
        if normalized_tag else
        f"📂 你的股票关注列表（共 {len(favorites)} 只）"
    )
    return header + "\n" + "\n".join(lines)


@tool
@register_tool(
    tool_id="add_stocks_to_favorites",
    name="Add stocks to stock watchlist in batches",
    description="Add one or more stocks to the user s stock watch list in batches, which is suitable for saving the recommendation results once after the intelligent stock selection is completed; it supports tagging these stocks at the same time through the tags parameter, and adding tags to the stocks already in the stock watch list.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["favorite_management", "watchlist", "add", "batch_add", "assistant_ops", "stock_favorites", "tag_assignment", "bulk_add", "favorites_update", "self_selected_stocks"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["批量添加股票关注列表", "保存智能选股结果", "给关注股票打标签", "补充已有股票关注列表标签"],
    when_to_use="It is used when the user wants to add one or more stocks to the stock watch list, or save the recommendation results in batches after the intelligent stock selection is completed.",
    returns="Returns a text message with statistics for new, skipped, supplementary tags, and failed tickers.",
)
async def add_stocks_to_favorites(
    stocks_json: Annotated[
        str,
        "Stocks JSON array, e.g. [{\"code\":\"600519\",\"name\":\"Kweichow Moutai\",\"market\":\"A shares\"}]",
    ],
    tags: Annotated[
        str,
        "Optional, tags to be given to these stocks at the same time, separated by commas, for example, Buffett,High dividends",
    ] = "",
) -> str:
    """Add stocks in batches to the current user s stock watch list, and add tags at the same time."""
    from app.services.favorites_service import favorites_service
    from app.services.tags_service import tags_service

    user_id = require_current_user_id()
    parsed_tags = _parse_tags(tags)

    try:
        items = json.loads(stocks_json)
    except json.JSONDecodeError:
        return "❌ The parameter format is wrong, please pass in the stock JSON array."

    if not isinstance(items, list) or not items:
        return "❌ Please provide at least one stock to be added to the stock watchlist."

    normalized_items = []
    seen_codes = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("symbol") or item.get("stock_code") or "").strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        normalized_items.append({
            "code": code,
            "name": str(item.get("name") or item.get("stock_name") or code).strip() or code,
            "market": _normalize_market(str(item.get("market") or "A股")),
        })

    if not normalized_items:
        return "❌ No valid stock symbol was parsed."

    existing_favorites = await favorites_service.get_user_favorites(user_id)
    existing_map = {
        str(item.get("stock_code") or item.get("symbol") or "").strip(): item
        for item in existing_favorites
        if str(item.get("stock_code") or item.get("symbol") or "").strip()
    }

    if parsed_tags:
        try:
            existing_tags = {
                tag.get("name")
                for tag in await tags_service.list_tags(user_id)
                if tag.get("name")
            }
            for tag_name in parsed_tags:
                if tag_name in existing_tags:
                    continue
                try:
                    await tags_service.create_tag(user_id=user_id, name=tag_name)
                    existing_tags.add(tag_name)
                except Exception:
                    logger.debug("[add_stocks_to_favorites] Failed to create tags, continue to use favorite tag aggregation: %s", tag_name, exc_info=True)
        except Exception:
            logger.debug("[add_stocks_to_favorites] Failed to read/create tags, continue to perform collection update", exc_info=True)

    added_codes = []
    skipped_codes = []
    tagged_codes = []
    failed_codes = []

    for item in normalized_items:
        code = item["code"]
        try:
            existing = existing_map.get(code)
            if existing:
                current_tags = list(existing.get("tags") or [])
                merged_tags = current_tags
                if parsed_tags:
                    merged_tags = list(dict.fromkeys([*current_tags, *parsed_tags]))

                if merged_tags != current_tags:
                    await favorites_service.update_favorite(
                        user_id=user_id,
                        stock_code=code,
                        tags=merged_tags,
                    )
                    tagged_codes.append(code)
                else:
                    skipped_codes.append(code)
                continue

            await favorites_service.add_favorite(
                user_id=user_id,
                stock_code=code,
                stock_name=item["name"],
                market=item["market"],
                tags=parsed_tags,
            )
            added_codes.append(code)
        except Exception as e:
            logger.warning("[add_stocks_to_favorites] Failed to add stock watchlist: %s %s", code, e)
            failed_codes.append(code)

    lines = [
        f"✅ 已添加 {len(added_codes)} 只股票到股票关注列表" if added_codes else "✅ There are no new stocks to watch this time",
    ]
    if added_codes:
        lines.append(f"- 新增: {', '.join(added_codes)}")
    if parsed_tags:
        lines.append(f"- 标签: {', '.join(parsed_tags)}")
    if tagged_codes:
        lines.append(f"- 已补充标签 {len(tagged_codes)} 只: {', '.join(tagged_codes)}")
    if skipped_codes:
        lines.append(f"- 已存在 {len(skipped_codes)} 只: {', '.join(skipped_codes)}")
    if failed_codes:
        lines.append(f"- 失败 {len(failed_codes)} 只: {', '.join(failed_codes)}")

    return "\n".join(lines)