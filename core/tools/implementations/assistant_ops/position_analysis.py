"""
Position analysis tools

Provides the functions of viewing the position list, querying the position analysis report, and initiating the position analysis.
"""

import asyncio
import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_positions",
    name="查看持仓列表",
    description="Lists all stock positions currently held by the user, including cost price, current price, profit and loss and other information. Supports filtering by data source (real/simulated).",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["position_analysis", "position", "list", "query", "assistant_ops", "portfolio", "holdings", "position_query", "real_position", "paper_position", "portfolio_view"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["持仓列表查看", "持仓股票查询", "实盘持仓浏览", "模拟持仓查看", "持仓盈亏查询"],
    when_to_use="It is used when the user wants to view all the stocks currently held and understand the holding cost, current price and floating profit and loss. Filtering by real offer/simulation is supported.",
    returns="Returns a text message, including the position quantity and the code, name, quantity, cost price, current price, market value and floating profit and loss of each stock.",
)
async def list_positions(
    source: Annotated[str, "Data source:all=All, real=Firm position, paper=Simulated position"] = "all",
) -> str:
    """List all current positions of the user and return the code, name, quantity, cost price, current price, floating profit and loss, etc. of each stock."""
    try:
        from app.services.portfolio_service import get_portfolio_service

        user_id = require_current_user_id()
        service = get_portfolio_service()
        positions = await service.get_positions(user_id, source=source, include_market_data=True)

        if not positions:
            source_label = {"all": "", "real": "实盘", "paper": "模拟"}.get(source, "")
            return f"当前没有{source_label}持仓记录。"

        lines = [f"共 {len(positions)} 只持仓：\n"]
        for p in positions:
            pnl_str = ""
            if p.unrealized_pnl is not None:
                sign = "+" if p.unrealized_pnl >= 0 else ""
                pct = f"{p.unrealized_pnl_pct:+.2f}%" if p.unrealized_pnl_pct is not None else ""
                pnl_str = f"  浮动盈亏: {sign}{p.unrealized_pnl:.2f} ({pct})"

            src_label = "实盘" if p.source == "real" else "模拟"
            price_str = f"现价: {p.current_price:.2f}" if p.current_price else "现价: --"
            mv_str = f"{p.market_value:.2f}" if p.market_value is not None else "--"
            lines.append(
                f"[{src_label}] {p.code} {p.name or ''} | "
                f"Quantity: {p.quantity} | cost: {p.cost_price:.2f} | {price_str} | "
                f"Market value: {mv_str}{pnl_str}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_positions] Failed to obtain position list: %s", e)
        return f"获取持仓列表时出错: {e}"


@tool
@register_tool(
    tool_id="get_position_analysis",
    name="获取持仓分析报告",
    description="Get the latest AI research analysis report on a certain stock, including research observation tendencies, key verification prices, risk review points, etc.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["position_analysis", "position", "query", "report", "assistant_ops", "ai_analysis", "position_report", "action_suggestion", "price_target", "risk_assessment", "holdings_analysis"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["持仓分析报告查看", "研究观察查询", "关键价位确认", "持仓风险审阅"],
    when_to_use="It is used when the user wants to view the latest AI research analysis report of a certain stock, obtain research observations and risk review references.",
    returns="Returns a text report, including research observation tendency, confidence level, position summary, key verification price, risk concern price and analysis details.",
)
async def get_position_analysis(
    code: Annotated[str, "Stock code, such as 600519,00700"],
    market: Annotated[str, "Market code:CN=A shares, HK=Hong Kong stocks, US=US stocks"] = "CN",
    position_type: Annotated[str, "Position type:real=firm offer, simulated=Simulation"] = "real",
) -> str:
    """Get the latest AI analysis report on specified stock positions."""
    try:
        from app.services.portfolio_service import get_portfolio_service
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread
        from app.core.database import get_mongo_db

        user_id = require_current_user_id()
        service = get_portfolio_service()
        report = await service.get_latest_position_analysis(user_id, code, market, position_type)

        if not report:
            return f"未找到 {code} 的持仓分析报告。可以先发起一次持仓分析。"

        # Build summary
        lines = []
        name = report.get("name") or code
        action = report.get("action") or "未知"
        confidence = report.get("confidence")
        status = report.get("status", "")
        created = report.get("created_at", "")

        lines.append(f"{name}({code}) 持仓分析报告")
        lines.append(f"状态: {status} | 研究观察: {action}" + (f" | 置信度: {confidence}%" if confidence else ""))

        # Position summary
        summary = report.get("summary") or {}
        if summary.get("quantity"):
            cost = summary.get("cost_price", 0)
            cur = summary.get("current_price", 0)
            pnl = summary.get("unrealized_pnl")
            pnl_pct = summary.get("unrealized_pnl_pct")
            lines.append(f"持仓: {summary['quantity']}股 | 成本: {cost:.2f} | 现价: {cur:.2f}")
            if pnl is not None:
                lines.append(f"浮动盈亏: {pnl:+.2f}" + (f" ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""))

        # Key verification price
        pt = report.get("price_targets") or {}
        if pt.get("target_price") or pt.get("stop_loss"):
            tp = pt.get("target_price")
            sl = pt.get("stop_loss")
            lines.append(f"关键验证价位: {tp}" + (f" | 风险关注价格: {sl}" if sl else ""))

        # Reason for operation
        reason = report.get("action_reason")
        if reason:
            lines.append(f"\n分析详情:\n{reason}")

        if created:
            lines.append(f"\n报告时间: {created[:16] if isinstance(created, str) else created}")

        await attach_report_ref_to_thread(
            get_mongo_db(),
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "position_report",
                "report_key": (report.get("analysis_id") or report.get("task_id") or f"{code}_{market}_{position_type}"),
                "source_collection": "position_analysis_reports",
                "title": f"{name}({code}) 持仓分析报告",
                "symbol": code,
                "summary": (reason or report.get("summary") or "")[:400],
                "status": status or "completed",
                "task_id": report.get("task_id"),
                "analysis_id": report.get("analysis_id"),
                "created_at": report.get("created_at"),
            },
        )

        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_position_analysis] Failed to obtain position analysis report: %s", e)
        return f"获取持仓分析报告时出错: {e}"


@tool
@register_tool(
    tool_id="trigger_position_analysis",
    name="发起持仓分析",
    description="Initiate a new AI position research and analysis task for a certain stock position, and generate research observations, key verification prices and risk reviews based on information such as position costs, profits and losses, etc. The task is executed asynchronously in the background (about 2-5 minutes) and the task ID is returned.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["position_analysis", "position", "trigger", "create", "assistant_ops", "ai_analysis", "async_task", "position_analysis_task", "action_suggestion", "deep_analysis", "holdings_analysis"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["持仓分析触发", "持仓 AI 分析发起", "研究观察生成", "持仓深度分析"],
    when_to_use="It is used when the user requests to initiate AI research analysis on a certain stock position, generate research observations and key verification prices, and the task is executed asynchronously in the background (about 2-5 minutes).",
    returns="Returns a text message containing task ID, stock code, market, position type, analysis focus and estimated completion time.",
)
async def trigger_position_analysis(
    code: Annotated[str, "Stock code, such as 600519,00700"],
    market: Annotated[str, "Market code:CN=A shares, HK=Hong Kong stocks, US=US stocks"] = "CN",
    position_type: Annotated[str, "Position type:real=firm offer, simulated=Simulation"] = "real",
    analysis_focus: Annotated[str, "Analysis focus:technical=technical aspect, fundamental=Fundamentals, comprehensive=Comprehensive"] = "comprehensive",
) -> str:
    """Initiate a new AI analysis on a certain held stock, execute it asynchronously in the background, and return the task ID."""
    try:
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread
        from app.services.unified_analysis_service import get_unified_analysis_service

        user_id = require_current_user_id()
        logger.info("[trigger_position_analysis] Start creating a position analysis task: code=%s, market=%s, user_id=%s", code, market, user_id)

        unified_service = get_unified_analysis_service()

        task_params = {
            "research_depth": "标准",
            "include_add_position": True,
            "target_profit_pct": 20.0,
            "max_position_pct": 30.0,
            "max_loss_pct": 10.0,
            "risk_tolerance": "medium",
            "investment_horizon": "medium",
            "analysis_focus": analysis_focus,
            "position_type": position_type,
        }
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        if current_thread_id:
            task_params["_assistant_thread_id"] = current_thread_id

        result = await unified_service.create_position_analysis_task(
            user_id=user_id,
            code=code,
            market=market,
            task_params=task_params,
        )
        task_id = result["task_id"]
        logger.info("[trigger_position_analysis] ✅ Task has been created: task_id=%s", task_id)

        # Background execution, no blocking
        bg_task = asyncio.create_task(
            unified_service.execute_position_analysis(
                task_id=task_id,
                user_id=user_id,
                code=code,
                market=market,
                task_params=task_params,
            )
        )
        bg_task.add_done_callback(
            lambda t: logger.error("[trigger_position_analysis] ❌ Background execution exception: %s", t.exception())
            if not t.cancelled() and t.exception() else None
        )

        await attach_report_ref_to_thread(
            get_mongo_db(),
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "position_task",
                "report_key": task_id,
                "source_collection": "position_analysis_reports",
                "title": f"{code} 持仓分析任务",
                "symbol": code,
                "summary": f"已发起 {code} 的持仓分析任务，等待生成正式报告。",
                "status": "running",
                "task_id": task_id,
            },
        )

        return (
            f"✅ 持仓分析任务已创建\n"
            f"- Task ID: {task_id}\n"
            f"- stocks: {code} ({market}) \n"
            f"- Position type: {'firm offer' if position_type == 'real' else 'Simulation'}\n"
            f"- Analysis focus: {analysis_focus}\n"
            f"- It is expected to take 2-5 minutes to complete. At that time, you can use Get Position Analysis Report to view the results."
        )
    except Exception as e:
        logger.exception("[trigger_position_analysis] ❌ Failed to create task: %s", e)
        return f"❌ Failed to create position analysis task: {e}"

