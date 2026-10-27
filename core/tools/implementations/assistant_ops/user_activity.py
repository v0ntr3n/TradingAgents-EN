"""Use the Q&A robot tool: query the user s recent tasks and error logs.

Provides the ability to query the user s recent N tasks, failed task error information, etc.
Allows using Q&A Assistant to"see"The true status of the user s recent operations for easy troubleshooting"Why is the error reported?""Where did the mission go?"etc. questions.
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


async def _query_recent_tasks(db, user_id: str, limit: int) -> List[Dict[str, Any]]:
    """Query the user s recent tasks (compatible with ObjectId and string user_id)"""
    queries = [{"user_id": user_id}]
    if _is_valid_object_id(user_id):
        from bson import ObjectId
        queries.append({"user_id": ObjectId(user_id)})

    for query in queries:
        try:
            cursor = db.unified_analysis_tasks.find(
                query,
                {
                    "task_id": 1, "task_type": 1, "status": 1, "task_params": 1,
                    "created_at": 1, "started_at": 1, "completed_at": 1,
                    "execution_time": 1, "error_message": 1, "current_step": 1,
                }
            ).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            if docs:
                return docs
        except Exception as exc:
            logger.warning("[get_user_recent_activity] Query failed query=%s: %s", query, exc)
    return []


def _format_task_line(t: Dict[str, Any]) -> str:
    """格式化单条任务"""
    params = t.get("task_params") or {}
    symbol = params.get("symbol") or params.get("stock_code") or params.get("analysis_target") or "?"
    status = t.get("status", "?")
    task_type = t.get("task_type", "?")
    task_id = t.get("task_id", "?")

    # time field
    created = t.get("created_at")
    started = t.get("started_at")
    completed = t.get("completed_at")
    created_str = created.isoformat()[:19] if isinstance(created, datetime) else (str(created)[:19] if created else "?")
    completed_str = completed.isoformat()[:19] if isinstance(completed, datetime) else (str(completed)[:19] if completed else "")

    # Execution time
    exec_time = t.get("execution_time") or 0
    exec_hint = f" | 耗时 {exec_time:.1f}s" if isinstance(exec_time, (int, float)) and exec_time > 0 else ""

    # error message
    error_hint = ""
    if status == "failed":
        err_msg = (t.get("error_message") or "无错误信息")[:200]
        error_hint = f"\n      ❌ 错误: {err_msg}"

    # Progress
    progress_hint = ""
    if status == "running" and t.get("current_step"):
        progress_hint = f" | 当前步骤: {t['current_step']}"

    completed_part = f" | 完成于 {completed_str}" if completed_str else ""
    return f"  • [{task_type}] {symbol} | {status}{progress_hint}{exec_hint}{completed_part} | 创建于 {created_str} | task_id={task_id}{error_hint}"


@tool
@register_tool(
    tool_id="get_user_recent_activity",
    name="获取用户最近活动",
    description="Query the execution status of the most recent N tasks (default 10) of the current user, including status, time consumption, and error information. When the user asks'Where did my mission go?''Why the task failed''What was executed recently'Use it when you have questions.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "user_activity", "recent_tasks", "error_log", "task_history"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["最近任务执行情况", "为什么任务失败", "任务去哪了", "排查报错"],
    when_to_use="Used when users ask about their recent task execution status, error reasons, or task history.",
    returns="Returns a list of recent tasks in text format, including task type, goal, status, time taken, and error information.",
)
async def get_user_recent_activity(
    limit: Annotated[int, "Return the most recent N tasks, default 10, maximum 30"] = 10,
) -> str:
    """Get the current user s recent task execution records."""
    from app.core.database import get_mongo_db

    if limit < 1:
        limit = 1
    if limit > 30:
        limit = 30

    user_id = require_current_user_id()
    db = get_mongo_db()

    tasks = await _query_recent_tasks(db, user_id, limit)

    if not tasks:
        return f"📭 There are no recent task records (queried {limit} Article upper limit,user_id={user_id}) . Possible reasons:\n  - You have not initiated any analysis tasks yet\n  - Database connection exception\n  - user_id Fields do not match (try Ctrl+F5 Refresh the page)"

    failed_count = sum(1 for t in tasks if t.get("status") == "failed")
    success_count = sum(1 for t in tasks if t.get("status") == "completed")
    running_count = sum(1 for t in tasks if t.get("status") == "running")
    pending_count = sum(1 for t in tasks if t.get("status") == "pending")

    lines = [
        f"📋 最近 {len(tasks)} 条任务（成功 {success_count} | 失败 {failed_count} | 运行中 {running_count} | 排队 {pending_count}）",
        "",
    ]
    for t in tasks:
        lines.append(_format_task_line(t))

    if failed_count > 0:
        lines.append("")
        lines.append(f"💡 失败任务 {failed_count} 条，请查看上方每条任务的错误信息。常见原因：")
        lines.append("  - Data source token is not configured or invalid")
        lines.append("  - LLM Call timeout or insufficient quota")
        lines.append("  - Stock code error or data does not exist")

    return "\n".join(lines)
