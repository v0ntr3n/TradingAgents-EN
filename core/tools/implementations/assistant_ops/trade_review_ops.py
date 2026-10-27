"""
Trading review tools

Provides the functions of querying review history, obtaining review report details, and initiating transaction review.
"""

import asyncio
import logging
from typing import Annotated, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_trade_reviews",
    name="查看复盘历史",
    description="Lists users transaction review records, and supports filtering by stock code, data source (simulated/real), and time range.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_review", "review", "history", "list", "query", "assistant_ops", "trade_history", "review_records", "trade_analysis", "backtesting", "review_filtering"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看复盘历史", "复盘记录查询", "交易复盘列表", "按股票查复盘"],
    when_to_use="It is used when users want to view their own transaction review record list and filter review history by stock code or data source.",
    returns="Returns a list of review records in text format, each containing stock code, name, review type, profit and loss, score, status and review ID.",
)
async def list_trade_reviews(
    code: Annotated[Optional[str], "Stock code screening, such as 600519, leave blank for no limit"] = None,
    source: Annotated[Optional[str], "Data source filter:paper=simulated trading, position=Position operation, Leave blank for all"] = None,
    page: Annotated[int, "Page number, default 1"] = 1,
    page_size: Annotated[int, "Number per page, default 10"] = 10,
) -> str:
    """List the user s transaction review history."""
    try:
        from app.services.trade_review_service import get_trade_review_service

        user_id = require_current_user_id()
        service = get_trade_review_service()
        result = await service.get_review_history(
            user_id=user_id,
            page=page,
            page_size=page_size,
            code=code,
            source=source,
        )

        items = result.get("items", [])
        total = result.get("total", 0)

        if not items:
            filter_desc = ""
            if code:
                filter_desc += f" {code}"
            if source:
                filter_desc += f" ({source})"
            return f"没有找到{filter_desc}的复盘记录。"

        lines = [f"共 {total} 条复盘记录（第 {page} 页）：\n"]
        for item in items:
            code_str = item.get("code", "")
            name_str = item.get("name", "")
            review_type = item.get("review_type", "")
            status = item.get("status", "")
            score = item.get("overall_score", 0)
            pnl = item.get("realized_pnl", 0)
            created = item.get("created_at", "")
            review_id = item.get("review_id", "")

            # Format time
            if isinstance(created, str) and len(created) > 16:
                created = created[:16]

            pnl_str = f"{pnl:+.2f}" if pnl else "0"
            score_str = f"评分: {score}" if score else ""
            type_label = {"complete_trade": "完整交易", "holding_trade": "持仓中"}.get(review_type, review_type)

            lines.append(
                f"{code_str} {name_str} | {type_label} | 盈亏: {pnl_str} | {score_str} | {status} | {created}"
            )
            lines.append(f"  复盘ID: {review_id}")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_trade_reviews] Failed to obtain review history: %s", e)
        return f"获取复盘历史时出错: {e}"


@tool
@register_tool(
    tool_id="get_trade_review_detail",
    name="获取复盘报告详情",
    description="Get a complete report of a transaction review based on the review ID, including AI evaluation, ratings, improvement suggestions, etc.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_review", "review", "detail", "report", "query", "assistant_ops", "review_detail", "ai_review", "review_report", "trade_analysis", "review_suggestions"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["复盘报告详情", "查看复盘结果", "AI评价查看", "复盘改进建议"],
    when_to_use="When the user wants to view the complete report details of a certain transaction review, obtain AI evaluation and improvement suggestions, the review ID needs to be provided.",
    returns="Returns the formatted review report text, including basic information, comprehensive score, summary, advantages, shortcomings and specific suggestions.",
)
async def get_trade_review_detail(
    review_id: Annotated[str, "Review ID, obtained from the review history list"],
) -> str:
    """Get the complete report details of the specified review ID."""
    try:
        from app.services.trade_review_service import get_trade_review_service

        user_id = require_current_user_id()
        service = get_trade_review_service()
        report = await service.get_review_detail(user_id, review_id)

        if not report:
            return f"未找到复盘报告（ID: {review_id}）。请检查 ID 是否正确。"

        lines = []
        trade_info = report.trade_info
        ai_review = report.ai_review

        # Basic information
        code = trade_info.code if trade_info else ""
        name = trade_info.name if trade_info and trade_info.name else ""
        lines.append(f"{name}({code}) 交易复盘报告")
        lines.append(f"复盘类型: {report.review_type} | 状态: {report.status}")

        if trade_info:
            pnl = trade_info.realized_pnl
            if pnl is not None:
                lines.append(f"已实现盈亏: {pnl:+.2f}")
            if trade_info.is_holding:
                lines.append("当前状态: 持仓中")

        # AI Evaluation
        if ai_review:
            if hasattr(ai_review, "overall_score") and ai_review.overall_score:
                lines.append(f"\n综合评分: {ai_review.overall_score}/100")
            if hasattr(ai_review, "summary") and ai_review.summary:
                lines.append(f"\n总结:\n{ai_review.summary}")
            if hasattr(ai_review, "strengths") and ai_review.strengths:
                lines.append("\n做得好的地方:")
                for s in ai_review.strengths:
                    lines.append(f"  ✅ {s}")
            if hasattr(ai_review, "weaknesses") and ai_review.weaknesses:
                lines.append("\n需要改进:")
                for w in ai_review.weaknesses:
                    lines.append(f"  ⚠️ {w}")
            if hasattr(ai_review, "suggestions") and ai_review.suggestions:
                lines.append("\n具体建议:")
                for sg in ai_review.suggestions:
                    lines.append(f"  💡 {sg}")

        created = report.created_at
        if created:
            ts = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else str(created)[:16]
            lines.append(f"\n报告时间: {ts}")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_trade_review_detail] Failed to obtain review report: %s", e)
        return f"获取复盘报告时出错: {e}"


@tool
@register_tool(
    tool_id="trigger_trade_review",
    name="发起交易复盘",
    description="Initiate a new AI review analysis task for the specified transaction record. A list of transaction IDs is required (can be obtained from position change records or simulated transaction records). Asynchronous execution in the background (about 1-3 minutes), generating AI evaluations, ratings and improvement suggestions.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_review", "review", "trigger", "create", "assistant_ops", "ai_review", "review_task", "trade_analysis", "backtesting", "async_task", "review_creation"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["发起交易复盘", "创建复盘任务", "AI交易分析", "交易记录复盘"],
    when_to_use="It is used when the user wants to initiate a new AI review analysis task for the specified transaction record, obtain transaction evaluation and improvement suggestions.",
    returns="Returns a text message, including task ID, number of transactions, data source and estimated completion time, and is executed asynchronously in the background.",
)
async def trigger_trade_review(
    trade_ids: Annotated[str, "Transaction ID to be reviewed, separate multiples with commas"],
    code: Annotated[Optional[str], "Stock code, such as 600519. Leave blank to automatically infer from transaction records"] = None,
    source: Annotated[str, "Data source:paper=simulated trading, position=Position operation"] = "paper",
) -> str:
    """Initiate a new AI review analysis on the specified transaction record, execute it asynchronously in the background, and return the task ID."""
    try:
        from app.services.unified_analysis_service import get_unified_analysis_service
        from app.models.review import CreateTradeReviewRequest

        user_id = require_current_user_id()
        id_list = [tid.strip() for tid in trade_ids.split(",") if tid.strip()]
        if not id_list:
            return "❌ Please provide at least one transaction ID."

        logger.info("[trigger_trade_review] Start creating a review task: trade_ids=%s, code=%s, user_id=%s", id_list, code, user_id)

        request = CreateTradeReviewRequest(
            trade_ids=id_list,
            code=code,
            source=source,
        )

        unified_service = get_unified_analysis_service()
        result = await unified_service.create_trade_review_task(
            user_id=user_id,
            request=request,
        )
        task_id = result["task_id"]
        logger.info("[trigger_trade_review] ✅ Task has been created: task_id=%s", task_id)

        # Background execution, no blocking
        bg_task = asyncio.create_task(
            unified_service.execute_trade_review(
                task_id=task_id,
                user_id=user_id,
                request=request,
            )
        )
        bg_task.add_done_callback(
            lambda t: logger.error("[trigger_trade_review] ❌ Background execution exception: %s", t.exception())
            if not t.cancelled() and t.exception() else None
        )

        code_str = f"（{code}）" if code else ""
        source_label = "模拟交易" if source == "paper" else "持仓操作"
        return (
            f"✅ 交易复盘任务已创建\n"
            f"- Task ID: {task_id}\n"
            f"- Number of transactions: {len(id_list)}{code_str}\n"
            f"- Data source: {source_label}\n"
            f"- It is expected to take 1-3 minutes to complete. At that time, you can use Get review report details to view the results."
        )
    except Exception as e:
        logger.exception("[trigger_trade_review] ❌ Failed to create task: %s", e)
        return f"❌ Failed to create transaction review task: {e}"

