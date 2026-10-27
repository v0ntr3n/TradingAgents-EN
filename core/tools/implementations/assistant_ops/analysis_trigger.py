"""
Analysis trigger tools

Provides stock analysis task creation and status query functions.
The analysis task is executed asynchronously, and the tool returns task_id immediately without blocking waiting for results.
"""

import asyncio
import logging
import uuid
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, get_current_im_channel, require_current_user_id

logger = logging.getLogger(__name__)

# ── Depth mapping ──
_DEPTH_MAP = {1: "快速", 2: "基础", 3: "标准", 4: "深度", 5: "全面"}


def _depth_label(depth: int) -> str:
    return _DEPTH_MAP.get(depth, "标准")


def _analysis_models() -> tuple[str, str]:
    """Get the currently configured fast/deep analysis model and write task_params for the report page to display the model name.

    Consistent with the front-end/normal analysis entry (analysis_service also reads from unified_config),
    Prevent analysis reports initiated by smart assistants from displaying Unknown/Unknown.
    """
    try:
        from app.core.unified_config import unified_config
        return (
            unified_config.get_quick_analysis_model(),
            unified_config.get_deep_analysis_model(),
        )
    except Exception as e:
        logger.warning(f"[analysis_trigger] Failed to read analysis model configuration: {e}")
        return "qwen-turbo", "qwen-max"


@tool
@register_tool(
    tool_id="trigger_stock_analysis",
    name="触发股票分析",
    description="Create a new multi-agent in-depth analysis task, with multiple AI agents collaborating in the background to generate a new analysis report (taking 2-5 minutes).",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["analysis_trigger", "stock_analysis", "trigger", "create", "assistant_ops", "multi_agent_analysis", "async_task", "analysis_task", "deep_analysis"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["stock_analysis_trigger", "deep_analysis_initiation", "multi_agent_analysis", "async_analysis_task_creation"],
    returns="Returns a text message containing the task ID, ticker, depth of analysis, and estimated completion time.",
    when_to_use="It is used when the user requests to initiate in-depth analysis of a certain stock and generate an analysis report. The task is executed asynchronously in the background.",
)
async def trigger_stock_analysis(
    symbol: Annotated[str, "Stock code, 6 digits, such as 000001,600519"],
    depth: Annotated[int, "Analysis Depth 1-5 (1=fast 2=Basics 3=Standard 4=Depth 5=Comprehensive), default 3"] = 3,
    workflow_id: Annotated[Optional[str], "Specify workflow ID, leave blank to automatically select"] = None,
) -> str:
    """Launch a new stock analysis task. The task is executed asynchronously in the background (usually takes 2-5 minutes), and the task ID is returned for subsequent status query or reporting."""
    try:
        from bson import ObjectId
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType

        user_id = require_current_user_id()
        logger.info("[trigger_stock_analysis] Start creating tasks: symbol=%s, depth=%s, user_id=%s", symbol, depth, user_id)

        service = get_task_analysis_service()

        # Construct task parameters, and append callback channel information if triggered on the IM channel (used for push notifications after task completion)
        quick_model, deep_model = _analysis_models()
        task_params: dict = {
            "symbol": symbol,
            "market_type": "cn",
            "research_depth": _depth_label(depth),
            "quick_analysis_model": quick_model,
            "deep_analysis_model": deep_model,
        }
        im_channel = get_current_im_channel()
        if im_channel:
            task_params["_im_channel"] = im_channel
            logger.info("[trigger_stock_analysis] IM Channel callback: %s", im_channel)
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        if current_thread_id:
            task_params["_assistant_thread_id"] = current_thread_id

        task = await service.create_task(
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params=task_params,
            engine_type="auto",
            workflow_id=workflow_id,
        )
        logger.info("[trigger_stock_analysis] ✅ Task has been created: task_id=%s", task.task_id)

        # Background execution, no blocking
        bg_task = asyncio.create_task(service.execute_task(task.task_id))
        bg_task.add_done_callback(
            lambda t: logger.error("[trigger_stock_analysis] ❌ Background execution exception: %s", t.exception())
            if not t.cancelled() and t.exception() else None
        )
        logger.info("[trigger_stock_analysis] The background execution task has been submitted")

        return (
            f"✅ 分析任务已创建\n"
            f"- Task ID: {task.task_id}\n"
            f"- stocks: {symbol}\n"
            f"- Depth: {_depth_label(depth)}\n"
            f"- It is expected to take 2-5 minutes to complete. At that time, you can use the View Report function to view the results."
        )
    except Exception as e:
        logger.exception("[trigger_stock_analysis] ❌ Failed to create task: %s", e)
        return f"❌ 创建分析任务失败: {e}"


@tool
@register_tool(
    tool_id="trigger_batch_analysis",
    name="触发批量分析",
    description="Create analysis tasks (batch version of trigger_stock_analysis) for multiple stocks at the same time, returning the batch ID and each task ID. It is suitable for scenarios where users require to analyze multiple stocks at one time.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["analysis_trigger", "batch_analysis", "trigger", "create", "assistant_ops", "multi_stock_analysis", "async_task", "batch_task", "multi_agent_analysis", "batch_create"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["批量股票分析触发", "多只股票同时分析", "批量分析任务创建", "组合分析快速发起"],
    when_to_use="It is used when the user requires to analyze multiple stocks at one time and initiate analysis tasks in batches. Each stock will create a separate background asynchronous task.",
    returns="Returns a text message containing the batch ID, each stock task ID, analysis depth and estimated completion time.",
)
async def trigger_batch_analysis(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as 000001,600519,000858"],
    depth: Annotated[int, "Analysis depth 1-5, default 3"] = 3,
) -> str:
    """Trigger analysis tasks for multiple stocks in batches. Each stock creates a separate task, and all tasks are executed asynchronously in the background."""
    from bson import ObjectId
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType

    user_id = require_current_user_id()
    service = get_task_analysis_service()
    batch_id = str(uuid.uuid4())

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return "❌ Please provide at least one ticker symbol"
    if len(symbol_list) > 10:
        return "❌ A single batch analysis supports up to 10 stocks"

    task_ids = []
    for sym in symbol_list:
        quick_model, deep_model = _analysis_models()
        task_params = {
            "symbol": sym,
            "market_type": "cn",
            "research_depth": _depth_label(depth),
            "quick_analysis_model": quick_model,
            "deep_analysis_model": deep_model,
        }
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        if current_thread_id:
            task_params["_assistant_thread_id"] = current_thread_id
        task = await service.create_task(
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params=task_params,
            engine_type="auto",
            batch_id=batch_id,
        )
        asyncio.create_task(service.execute_task(task.task_id))
        task_ids.append(f"  - {sym}: {task.task_id}")

    return (
        f"✅ 批量分析已创建（{len(symbol_list)} 只股票）\n"
        f"- batch ID: {batch_id}\n"
        f"- Depth: {_depth_label(depth)}\n"
        + "\n".join(task_ids)
        + "\n- Expect 2-5 minutes per stock to complete."
    )


@tool
@register_tool(
    tool_id="get_analysis_status",
    name="查询分析状态",
    description="Query and analyze the execution status and progress of the task (queuing/running/completed/failed) based on the task ID. Used to know whether a previously initiated analysis is complete.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["analysis_trigger", "status_query", "query", "assistant_ops", "task_status", "analysis_progress", "task_tracking", "async_task", "monitor", "progress_check"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["分析任务状态查询", "分析进度跟踪", "任务完成确认", "异步分析结果检查"],
    when_to_use="Used when the user wants to know whether a previously initiated analysis task has been completed, the current progress, or the cause of failure.",
    returns="Returns a text message containing task status, progress percentage, current step, and (if completed) a summary of the research conclusion tendencies.",
)
async def get_analysis_status(
    task_id: Annotated[str, "分析任务ID"],
) -> str:
    """Query the status, progress, and result summary of a specified analysis task."""
    from app.services.task_analysis_service import get_task_analysis_service

    service = get_task_analysis_service()
    task = await service.get_task(task_id)

    if not task:
        return f"❌ 未找到任务: {task_id}"

    status_emoji = {"pending": "⏳", "processing": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
    emoji = status_emoji.get(task.status, "❓")
    lines = [
        f"{emoji} 任务状态: {task.status}",
        f"- 任务ID: {task.task_id}",
        f"- 类型: {task.task_type}",
        f"- 进度: {task.progress}%",
    ]
    if task.current_step:
        lines.append(f"- 当前步骤: {task.current_step}")
    if task.status == "completed" and task.result:
        recommendation = task.result.get("recommendation", "")
        if recommendation:
            lines.append(f"- 研究结论倾向: {recommendation[:200]}")
    if task.status == "failed" and task.error_message:
        lines.append(f"- 错误: {task.error_message[:200]}")
    if task.execution_time > 0:
        lines.append(f"- 耗时: {task.execution_time:.1f}s")

    return "\n".join(lines)

