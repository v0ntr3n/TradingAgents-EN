"""Use the Q&A bot tool: Query running and queued tasks.

Allows using Q&A Assistant to"see"Tasks currently running and queued include:
- Running tasks, current steps, progress, elapsed time
- Queued tasks and estimated start times
- Recently completed tasks (used as contextual reference)

Avoid robot encounters"Where did the mission go?"You can only guess the answer based on the FAQ.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _format_duration(seconds: Optional[float]) -> str:
    """Format seconds into a human-readable duration."""
    if seconds is None or seconds < 0:
        return "未知"
    try:
        s = int(seconds)
        if s < 60:
            return f"{s} 秒"
        if s < 3600:
            return f"{s // 60} 分 {s % 60} 秒"
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h} 时 {m} 分"
    except Exception:
        return str(seconds)


def _format_time_ago(dt_value: Any) -> str:
    """Format a datetime or ISO string as'X minutes ago'format."""
    if not dt_value:
        return "未知"
    try:
        if isinstance(dt_value, str):
            normalized = dt_value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        elif isinstance(dt_value, datetime):
            dt = dt_value
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        else:
            return str(dt_value)[:19]
        diff = (datetime.now() - dt).total_seconds()
        if diff < 0:
            return dt.strftime("%Y-%m-%d %H:%M")
        if diff < 60:
            return "刚刚"
        if diff < 3600:
            return f"{int(diff / 60)} 分钟前"
        if diff < 86400:
            return f"{int(diff / 3600)} 小时前"
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt_value)[:19]


def _calc_elapsed(started_at: Any) -> Optional[float]:
    """Calculates the number of seconds elapsed."""
    if not started_at:
        return None
    try:
        if isinstance(started_at, str):
            normalized = started_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        elif isinstance(started_at, datetime):
            dt = started_at
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        else:
            return None
        return (datetime.now() - dt).total_seconds()
    except Exception:
        return None


def _estimate_remaining(progress: int, elapsed_seconds: Optional[float]) -> Optional[float]:
    """Estimate remaining seconds based on progress and elapsed time."""
    if not elapsed_seconds or elapsed_seconds <= 0:
        return None
    if progress <= 0:
        return None
    if progress >= 100:
        return 0
    # Estimated total duration = Time spent / (Progress / 100)
    estimated_total = elapsed_seconds / (progress / 100)
    remaining = estimated_total - elapsed_seconds
    return max(0, remaining)


def _resolve_symbol(task_params: Dict[str, Any]) -> str:
    """Extract symbol/stock_code/analysis_target from task_params."""
    if not task_params:
        return "?"
    return (
        task_params.get("symbol")
        or task_params.get("stock_code")
        or task_params.get("code")
        or task_params.get("analysis_target")
        or "?"
    )


def _map_task_type_label(task_type: str) -> str:
    """Map task types to Chinese labels."""
    mapping = {
        "stock_analysis": "单股分析",
        "etf_analysis": "ETF 分析",
        "position_analysis": "持仓分析",
        "trade_review": "操作复盘",
        "portfolio_health": "组合健康度",
        "risk_assessment": "风险评估",
        "market_overview": "市场概览",
        "sector_analysis": "板块分析",
        "general": "通用研究",
    }
    return mapping.get(task_type, task_type or "未知")


def _map_status_label(status: str) -> tuple[str, str]:
    """Map the status to (emoji, Chinese description). """
    mapping = {
        "pending": ("⏳", "排队中"),
        "running": ("🔄", "运行中"),
        "processing": ("🔄", "运行中"),
        "completed": ("✅", "已完成"),
        "failed": ("❌", "失败"),
        "cancelled": ("⚪", "已取消"),
    }
    return mapping.get(status, ("❓", status or "未知"))


async def _query_active_tasks(db, user_id: str) -> List[Dict[str, Any]]:
    """Query running and queued tasks."""
    try:
        from bson import ObjectId
        # user_id May be ObjectId or string, for compatibility
        uid_variants = [user_id]
        try:
            uid_obj = ObjectId(user_id)
            uid_variants.append(uid_obj)
        except Exception:
            pass

        query = {
            "user_id": {"$in": uid_variants},
            "status": {"$in": ["pending", "running", "processing"]},
        }

        cursor = db["unified_analysis_tasks"].find(query).sort("created_at", -1).limit(20)
        docs = await cursor.to_list(length=20)
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception as exc:
        logger.warning("[get_running_tasks] Query running task failed: %s", exc)
        return []


async def _query_recent_completed(db, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Query recently completed tasks (used as a contextual reference)."""
    try:
        from bson import ObjectId
        uid_variants = [user_id]
        try:
            uid_obj = ObjectId(user_id)
            uid_variants.append(uid_obj)
        except Exception:
            pass

        query = {
            "user_id": {"$in": uid_variants},
            "status": {"$in": ["completed", "failed", "cancelled"]},
        }

        cursor = db["unified_analysis_tasks"].find(query).sort("completed_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception as exc:
        logger.warning("[get_running_tasks] Failed to query recently completed tasks: %s", exc)
        return []


@tool
@register_tool(
    tool_id="get_running_tasks",
    name="查询运行中和排队的任务",
    description="Query the current user s running and queued analysis tasks: current step, progress percentage, elapsed time, estimated remaining time, and queue position. When the user asks'Where did the mission go?''How long will it take''There are several tasks queued''When will the analysis be completed?'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "running_tasks", "task_progress", "pending_tasks", "task_status", "queue", "active_tasks"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "任务跑到哪一步了",
        "分析进度怎么样",
        "还要多久才能完成",
        "有几个任务在排队",
        "我的任务完成了吗",
        "任务什么时候结束",
        "正在运行的任务",
    ],
    when_to_use="Used when the user asks about the progress, remaining time, and queue status of running tasks. Returns a list of currently running, queued, and recently completed tasks.",
    returns="Returns a summary of the task running status in text format, including running tasks, queued tasks, recently completed tasks, and comprehensive judgments.",
)
async def get_running_tasks() -> str:
    """Query running and queued tasks."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    active_tasks = await _query_active_tasks(db, user_id)
    recent_completed = await _query_recent_completed(db, user_id, limit=3)

    lines = ["📊 任务运行状态"]

    if not active_tasks:
        lines.append("")
        lines.append("💤 There are currently no tasks running or queued")
    else:
        # Group by status: running first, pending next
        running = [t for t in active_tasks if t.get("status") in ("running", "processing")]
        pending = [t for t in active_tasks if t.get("status") == "pending"]

        # 1) Running tasks
        lines.append("")
        lines.append(f"【1】运行中任务（共 {len(running)} 个）")
        if not running:
            lines.append("- 无")
        else:
            for i, t in enumerate(running[:5], 1):
                task_type = t.get("task_type", "?")
                type_label = _map_task_type_label(task_type)
                symbol = _resolve_symbol(t.get("task_params") or {})
                progress = int(t.get("progress") or 0)
                current_step = t.get("current_step") or t.get("message") or "处理中"
                started_at = t.get("started_at") or t.get("created_at")
                elapsed = _calc_elapsed(started_at)
                remaining = _estimate_remaining(progress, elapsed)

                emoji, _ = _map_status_label(t.get("status", "running"))
                lines.append(
                    f"  {i}. {emoji} [{type_label}] {symbol}"
                )
                lines.append(f"      进度: {progress}%")
                lines.append(f"      当前步骤: {current_step}")
                lines.append(f"      已耗时: {_format_duration(elapsed)}")
                if remaining is not None:
                    lines.append(f"      预计剩余: {_format_duration(remaining)}")
                started_ago = _format_time_ago(started_at)
                lines.append(f"      开始时间: {started_ago}")

        # 2) Tasks in queue
        lines.append("")
        lines.append(f"【2】排队中任务（共 {len(pending)} 个）")
        if not pending:
            lines.append("- 无")
        else:
            for i, t in enumerate(pending[:5], 1):
                task_type = t.get("task_type", "?")
                type_label = _map_task_type_label(task_type)
                symbol = _resolve_symbol(t.get("task_params") or {})
                created_at = t.get("created_at")
                lines.append(
                    f"  {i}. ⏳ [{type_label}] {symbol} (排队位置: #{i})"
                )
                lines.append(f"      提交时间: {_format_time_ago(created_at)}")

    # 3) Recently completed tasks (contextual reference)
    lines.append("")
    lines.append(f"【3】最近完成的任务（{len(recent_completed)} 条，作上下文参考）")
    if not recent_completed:
        lines.append("- 暂无历史任务")
    else:
        for t in recent_completed[:3]:
            task_type = t.get("task_type", "?")
            type_label = _map_task_type_label(task_type)
            symbol = _resolve_symbol(t.get("task_params") or {})
            status = t.get("status", "?")
            emoji, status_cn = _map_status_label(status)
            completed_at = t.get("completed_at") or t.get("updated_at")
            execution_time = t.get("execution_time")

            # Analysis takes time
            if execution_time:
                duration_str = _format_duration(float(execution_time))
            else:
                # Calculated from started_at and completed_at
                started_at = t.get("started_at")
                if started_at and completed_at:
                    try:
                        if isinstance(started_at, str):
                            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                            if started_at.tzinfo:
                                started_at = started_at.astimezone().replace(tzinfo=None)
                        if isinstance(completed_at, str):
                            completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                            if completed_dt.tzinfo:
                                completed_dt = completed_dt.astimezone().replace(tzinfo=None)
                        else:
                            completed_dt = completed_at
                        duration_str = _format_duration((completed_dt - started_at).total_seconds())
                    except Exception:
                        duration_str = "未知"
                else:
                    duration_str = "未知"

            err_hint = ""
            if status == "failed" and t.get("error_message"):
                err_hint = f" | 错误: {str(t['error_message'])[:80]}"

            lines.append(
                f"  • {emoji} [{type_label}] {symbol} | {status_cn} | "
                f"Time consuming {duration_str} | Complete {_format_time_ago(completed_at)}{err_hint}"
            )

    # 4) Comprehensive judgment
    lines.append("")
    lines.append("💡 综合判断")
    running_count = sum(1 for t in active_tasks if t.get("status") in ("running", "processing"))
    pending_count = sum(1 for t in active_tasks if t.get("status") == "pending")

    if running_count == 0 and pending_count == 0:
        lines.append("- There are currently no running tasks, new analysis can be submitted")
        # Check if there are any recent failed tasks
        failed_recent = [t for t in recent_completed if t.get("status") == "failed"]
        if failed_recent:
            latest_failed = failed_recent[0]
            symbol = _resolve_symbol(latest_failed.get("task_params") or {})
            lines.append(f"- ⚠️ 最近一次 {symbol} 任务失败，建议查看错误原因后重试")
    else:
        if running_count > 0:
            # Get the first running task
            first_running = next((t for t in active_tasks if t.get("status") in ("running", "processing")), None)
            if first_running:
                symbol = _resolve_symbol(first_running.get("task_params") or {})
                progress = int(first_running.get("progress") or 0)
                started_at = first_running.get("started_at") or first_running.get("created_at")
                elapsed = _calc_elapsed(started_at)
                remaining = _estimate_remaining(progress, elapsed)
                lines.append(
                    f"- 正在分析 {symbol}，进度 {progress}%，已运行 {_format_duration(elapsed)}"
                )
                if remaining is not None and remaining > 0:
                    lines.append(f"- 预计还需 {_format_duration(remaining)} 完成")

        if pending_count > 0:
            lines.append(f"- 还有 {pending_count} 个任务在排队等待")

        # JD Cloud Edition: Force single concurrency, remind users
        import os
        is_jdyun = os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes")
        if is_jdyun and (running_count + pending_count) > 1:
            lines.append("- 📌 Jingdong Cloud version forces single concurrency, multiple tasks will be executed serially, and the waiting time will be long.")

    return "\n".join(lines)
