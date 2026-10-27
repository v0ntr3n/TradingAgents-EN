"""Use the Q&A robot tool: query the user s current status.

Provides the ability to query the current user s watch list stocks, historical tasks, recent tasks, scheduled analysis configurations, etc.
Allows using Q&A Assistant to"see"The user s current status, rather than guessing the answer based on the FAQ.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _is_valid_object_id(user_id: str) -> bool:
    if not user_id or not isinstance(user_id, str):
        return False
    try:
        from bson import ObjectId
        ObjectId(user_id)
        return len(user_id) == 24
    except Exception:
        return False


async def _count_user_favorites(db, user_id: str) -> tuple[int, List[Dict[str, Any]]]:
    """Return (Number of stocks on watch list, Top 5 stock names)"""
    try:
        if _is_valid_object_id(user_id):
            from bson import ObjectId
            user = await db.users.find_one({"_id": ObjectId(user_id)}, {"favorite_stocks": 1})
            if user is None:
                user = await db.users.find_one({"_id": user_id}, {"favorite_stocks": 1})
            favorites = (user or {}).get("favorite_stocks", []) or []
        else:
            doc = await db.user_favorites.find_one({"user_id": user_id}, {"favorites": 1})
            favorites = (doc or {}).get("favorites", []) or []

        count = len(favorites)
        preview = [
            f"{f.get('stock_name', '?')}({f.get('stock_code', '?')})"
            for f in favorites[:5]
        ]
        return count, preview
    except Exception as exc:
        logger.warning("[get_user_current_state] Failed to query watchlist: %s", exc)
        return -1, []


async def _count_user_tasks(db, user_id: str) -> tuple[int, int, List[Dict[str, Any]]]:
    """Return (total number of tasks, Number of failed tasks, Summary of the last 5 tasks)"""
    try:
        # unified_analysis_tasks The collection user_id may be a string or ObjectId
        query: Dict[str, Any] = {"user_id": user_id}
        total = await db.unified_analysis_tasks.count_documents(query)
        if total == 0 and _is_valid_object_id(user_id):
            from bson import ObjectId
            total = await db.unified_analysis_tasks.count_documents({"user_id": ObjectId(user_id)})

        recent_cursor = db.unified_analysis_tasks.find(
            query, {"status": 1, "task_params": 1, "created_at": 1, "task_type": 1, "error_message": 1}
        ).sort("created_at", -1).limit(5)
        recent = await recent_cursor.to_list(length=5)

        if not recent and _is_valid_object_id(user_id):
            from bson import ObjectId
            recent_cursor2 = db.unified_analysis_tasks.find(
                {"user_id": ObjectId(user_id)},
                {"status": 1, "task_params": 1, "created_at": 1, "task_type": 1, "error_message": 1}
            ).sort("created_at", -1).limit(5)
            recent = await recent_cursor2.to_list(length=5)
            if total == 0:
                total = await db.unified_analysis_tasks.count_documents({"user_id": ObjectId(user_id)})

        failed = sum(1 for t in recent if t.get("status") == "failed")
        preview = []
        for t in recent:
            params = t.get("task_params") or {}
            symbol = params.get("symbol") or params.get("stock_code") or "?"
            status = t.get("status", "?")
            created = t.get("created_at")
            created_str = created.isoformat()[:19] if isinstance(created, datetime) else (str(created)[:19] if created else "?")
            preview.append({
                "symbol": symbol,
                "status": status,
                "task_type": t.get("task_type", "?"),
                "created_at": created_str,
                "error": (t.get("error_message") or "")[:100] if status == "failed" else None,
            })
        return total, failed, preview
    except Exception as exc:
        logger.warning("[get_user_current_state] Query task failed: %s", exc)
        return -1, 0, []


async def _count_scheduled(db, user_id: str) -> int:
    """Returns the number of enabled scheduled analysis configurations"""
    try:
        count = await db.scheduled_analysis_configs.count_documents({"user_id": user_id, "enabled": True})
        return count
    except Exception as exc:
        logger.warning("[get_user_current_state] Query timing analysis configuration failed: %s", exc)
        return -1


@tool
@register_tool(
    tool_id="get_user_current_state",
    name="获取用户当前状态",
    description="Query the number of stocks in the current user s watch list, the total number of historical tasks, the execution status of recent tasks, and the number of scheduled analysis configurations. When the user asks'where is my mission''How many stocks are on the watch list?''Why is today s task 0'Use it when you have questions.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "user_state", "favorites_count", "task_count", "recent_tasks", "scheduled_analysis"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查询关注列表数量", "查看任务总数", "今日任务为什么是0", "最近任务执行情况"],
    when_to_use="Used when the user asks about his current status (number of watch lists/number of tasks/scheduled analysis configuration).",
    returns="Returns a user status summary in text format, including the number of watch list stocks, total number of tasks, number of failed tasks, the last 5 tasks and the number of scheduled analysis configurations.",
)
async def get_user_current_state() -> str:
    """Get a summary of the current user s system status."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    fav_count, fav_preview = await _count_user_favorites(db, user_id)
    task_total, task_failed, task_recent = await _count_user_tasks(db, user_id)
    scheduled_count = await _count_scheduled(db, user_id)

    lines = ["📊 用户当前状态"]
    if fav_count >= 0:
        lines.append(f"- 关注列表股票数: {fav_count}")
        if fav_preview:
            lines.append(f"  前 5 只: {', '.join(fav_preview)}")
    else:
        lines.append("- Number of stocks on watch list: Query failed")

    if task_total >= 0:
        lines.append(f"- 历史任务总数: {task_total}")
        lines.append(f"- Number of failures in the last 5 tasks: {task_failed}")
        for t in task_recent:
            err_hint = f" ❌错误: {t['error']}" if t.get("error") else ""
            lines.append(f"  • {t['symbol']} | {t['task_type']} | {t['status']} | {t['created_at']}{err_hint}")
    else:
        lines.append("- 历史任务: 查询失败")

    if scheduled_count >= 0:
        lines.append(f"- Enabling scheduled analysis configuration: {scheduled_count}")
    else:
        lines.append("- Timing analysis configuration: Query failed")

    return "\n".join(lines)
