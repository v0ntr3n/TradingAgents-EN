"""
Report query tools

Provides functions for searching analysis reports, viewing details, and obtaining the latest reports.
The query scope is limited to the current user s reports.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, require_current_user_id

logger = logging.getLogger(__name__)

# ── Date range shortcut ──
_DATE_SHORTCUTS = {
    "today": 0,
    "yesterday": 1,
    "last_week": 7,
    "last_month": 30,
    "last_quarter": 90,
}


def _resolve_date_range(date_range: Optional[str]):
    """Convert natural language date range to (start, end) datetime. """
    if not date_range:
        return None, None
    key = date_range.strip().lower().replace(" ", "_")
    days = _DATE_SHORTCUTS.get(key)
    if days is not None:
        end = datetime.now()
        start = end - timedelta(days=days)
        return start, end
    # try to parse YYYY-MM-DD ~ YYYY-MM-DD
    if "~" in date_range:
        parts = date_range.split("~")
        try:
            return datetime.strptime(parts[0].strip(), "%Y-%m-%d"), datetime.strptime(parts[1].strip(), "%Y-%m-%d")
        except ValueError:
            pass
    return None, None


@tool
@register_tool(
    tool_id="search_reports",
    name="搜索分析报告",
    description="Search the user s existing historical analysis reports in the database, and support filtering by stock code, keywords, and date range. Returns a list of report summaries (title, stock, date, conclusion) without full text.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "search", "query", "assistant_ops", "report_search", "report_history", "report_filtering", "stock_report"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["report_search", "report_history_query", "analysis_report_filtering", "stock_report_lookup", "report_summary_viewing"],
    returns="Returns a list of report summaries in text format, containing task ID, ticker, date, and conclusion summary.",
    when_to_use="Used when users want to search, find or filter historical analysis reports, supporting filtering by stock code, keywords or date range.",
)
async def search_reports(
    symbol: Annotated[Optional[str], "Stock code screening, such as 600519"] = None,
    keyword: Annotated[Optional[str], "Search keywords to match report content"] = None,
    date_range: Annotated[Optional[str], "date range: today / last_week / last_month or YYYY-MM-DD~YYYY-MM-DD"] = None,
    limit: Annotated[int, "Returns the upper limit of quantity, default 5"] = 5,
) -> str:
    """Searching the list of analysis reports returns a condensed summary (title, stock, date, conclusion) without full content."""
    try:
        from bson import ObjectId
        from app.core.database import get_mongo_db

        user_id = require_current_user_id()
        db = get_mongo_db()

        query = {"user_id": ObjectId(user_id), "status": "completed"}

        if symbol:
            query["task_params.symbol"] = symbol
        if keyword:
            query["$or"] = [
                {"task_params.symbol": {"$regex": keyword, "$options": "i"}},
                {"result.recommendation": {"$regex": keyword, "$options": "i"}},
                {"result.summary": {"$regex": keyword, "$options": "i"}},
            ]
        start, end = _resolve_date_range(date_range)
        if start or end:
            date_q = {}
            if start:
                date_q["$gte"] = start
            if end:
                date_q["$lte"] = end
            query["created_at"] = date_q

        cursor = db.unified_analysis_tasks.find(
            query,
            {"task_id": 1, "task_type": 1, "task_params": 1, "created_at": 1, "result.recommendation": 1, "result.summary": 1, "execution_time": 1},
        ).sort("created_at", -1).limit(limit)

        results = []
        async for doc in cursor:
            sym = doc.get("task_params", {}).get("symbol", "N/A")
            created = doc.get("created_at")
            date_str = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else (str(created)[:16] if created else "未知")
            rec = (doc.get("result") or {}).get("recommendation", "")
            summary = (doc.get("result") or {}).get("summary", "")
            brief = (rec or summary or "无摘要")[:120]
            results.append(f"  [{doc['task_id'][:8]}] {sym} | {date_str} | {brief}")

        if not results:
            return "No matching analysis reports were found."
        return f"📊 找到 {len(results)} 条报告：\n" + "\n".join(results) + "\n\n💡 Use View Report Details to get the complete content."
    except Exception as e:
        logger.exception("[search_reports] Query report failed: %s", e)
        return f"查询报告时出错: {str(e)}"


@tool
@register_tool(
    tool_id="get_report_detail",
    name="查看报告详情",
    description="Get the analysis report content based on the task ID. Two modes are supported:1) If module_key is not passed, the top-level summary (research conclusion tendency, key points, summary) will be returned;2) Passing module_key returns the complete text content of the specified submodule (such as market_report/fundamentals_report/news_report/sentiment_report/trader_investment_plan/research_team_decision/risk_management_decision/final_trade_decision, etc.). It is recommended to obtain specified modules on demand based on user issues to avoid pulling too much content at once.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "detail", "query", "assistant_ops", "report_detail", "report_content", "full_report", "markdown_report", "report_module"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["report_detail_viewing", "full_report_reading", "report_content_retrieval", "analysis_report_detail", "report_module_reading"],
    returns="Returns a formatted Markdown report. If module_key is not passed, the top-level summary is returned; if module_key is passed, the complete text of the specified module is returned.",
    when_to_use="Used when the user wants to view the content of the analysis report. Simple questions (such as overall conclusions) do not pass module_key; specific dimensional questions (such as technical aspects/fundamentals/news) pass the corresponding module_key to obtain the complete content.",
)
async def get_report_detail(
    task_id: Annotated[str, "分析任务ID"],
    module_key: Annotated[Optional[str], "Specify the submodule key to obtain the complete text. Optional values:market_report(Market technical analysis)/fundamentals_report(fundamental research)/news_report(Journalism Research)/sentiment_report(sentiment analysis)/trader_investment_plan(Research and integrate opinions)/research_team_decision(Research team conclusion)/risk_management_decision(Risk review conclusion)/final_trade_decision(Comprehensive research conclusion)/index_report(Market environment)/sector_report(Industry sector). If not passed, the top-level summary will be returned."] = None,
) -> str:
    """Get the report content of the specified analysis task. Passing module_key returns the complete text of the module, otherwise it returns the top-level summary."""
    try:
        from app.core.database import get_mongo_db
        from app.services.task_analysis_service import get_task_analysis_service
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread

        user_id = require_current_user_id()
        service = get_task_analysis_service()
        task = await service.get_task(task_id)
        if not task:
            return f"❌ 未找到任务: {task_id}"
        if task.status != "completed":
            return f"⏳ The task has not yet been completed (current status: {task.status}, Progress: {task.progress}%) "
        if not task.result:
            return "⚠️ The task was completed but no report data was generated."

        r = task.result
        sym = task.task_params.get("symbol", "未知")

        # ── Module mode: Return the complete text of the specified submodule ──
        if module_key:
            module_key_clean = module_key.strip()
            reports_dict = r.get("reports") or {}
            if not isinstance(reports_dict, dict) or not reports_dict:
                return f"⚠️ 任务 {task_id} 的报告中未找到任何子模块数据。"
            content = reports_dict.get(module_key_clean)
            if not content or (isinstance(content, str) and not content.strip()):
                available = ", ".join(reports_dict.keys())
                return (
                    f"⚠️ 未找到模块 `{module_key_clean}`。\n"
                    f"The report contains the following modules available:{available}\n"
                    f"Please choose one of the above modules to call again."
                )
            label = _ANALYST_LABELS.get(module_key_clean, module_key_clean)
            # Compatible when content is a dictionary (for example, final_trade_decision may be structured data)
            if isinstance(content, dict):
                content_text = content.get("content") or content.get("report") or content.get("text") or content.get("markdown") or ""
                if not content_text:
                    content_text = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                content_text = str(content)
            return f"# {label}\n\n{content_text}"

        # ── Top-level summary mode: Returns the overall summary of the report ──
        lines = [f"# 📈 {sym} 分析报告"]
        if r.get("recommendation"):
            lines.append(f"\n## 研究结论倾向\n{r['recommendation']}")
        if r.get("confidence_score"):
            lines.append(f"\n**置信度**: {r['confidence_score']}")
        if r.get("risk_level"):
            lines.append(f"**风险等级**: {r['risk_level']}")
        if r.get("key_points"):
            kps = r["key_points"] if isinstance(r["key_points"], list) else [r["key_points"]]
            lines.append("\n## 关键要点\n" + "\n".join(f"- {kp}" for kp in kps))
        if r.get("summary"):
            lines.append(f"\n## 摘要\n{r['summary']}")

        # Lists available submodules, directing LLM to get full content on demand
        reports_dict = r.get("reports") or {}
        if isinstance(reports_dict, dict) and reports_dict:
            available_lines = []
            for k in reports_dict.keys():
                label = _ANALYST_LABELS.get(k, k)
                available_lines.append(f"  • {k}（{label}）")
            lines.append("\n## 可用子模块")
            lines.append("To view the complete content of a module, call this tool again and pass in the module_key parameter:")
            lines.extend(available_lines)

        db = get_mongo_db()
        await attach_report_ref_to_thread(
            db,
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "stock_report",
                "report_key": task.task_id,
                "source_collection": "unified_analysis_tasks",
                "title": f"{sym} 分析报告",
                "symbol": sym,
                "summary": (r.get("summary") or r.get("recommendation") or "")[:400],
                "status": task.status,
                "task_id": task.task_id,
                "created_at": getattr(task, "created_at", None),
            },
        )

        lines.append(f"\n---\n_任务ID: {task.task_id} | 耗时: {task.execution_time:.1f}s_")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_report_detail] Failed to get report details: %s", e)
        return f"获取报告详情时出错: {str(e)}"



# ── Chinese labels for each analyst role ──
# Covers all submodules that may appear in the reports dictionary of single stock analysis reports
_ANALYST_LABELS = {
    # core decision-making
    "final_trade_decision":   "综合研究结论",
    "research_team_decision": "研究团队结论",
    "risk_management_decision": "风险审阅结论",
    "trader_investment_plan": "研究整合意见",
    "investment_plan":        "投资计划",
    # Researcher Debate Class
    "bull_researcher":        "乐观情景论证",
    "bear_researcher":        "审慎情景论证",
    "neutral_analyst":        "基准情景评估",
    "risky_analyst":          "高弹性情景评估",
    "safe_analyst":           "防御情景评估",
    # Individual stock analysis module
    "fundamentals_report":    "基本面研究",
    "market_report":          "市场技术分析",
    "news_report":            "新闻研究",
    "sentiment_report":       "情绪分析",
    "chip_report":            "筹码分布分析",
    # Macro analysis module
    "index_report":           "大盘环境研究",
    "sector_report":          "行业板块研究",
    # Position analysis module (some reports may be reused)
    "company_overview":       "公司概况",
    "financial_analysis":     "财务分析",
    "technical_analysis":     "技术分析",
    "market_analysis":        "市场分析",
    "risk_analysis":          "风险分析",
    "valuation_analysis":     "估值分析",
    "investment_recommendation": "研究结论摘要",
}
# Sort by importance and prioritize core decisions
_REPORT_PRIORITY = [
    "final_trade_decision",
    "research_team_decision",
    "risk_management_decision",
    "bull_researcher",
    "bear_researcher",
    "fundamentals_report",
    "market_report",
    "news_report",
    "sentiment_report",
    "investment_plan",
    "trader_investment_plan",
]
_MAX_TOTAL_CHARS = 6000   # Tool returns cap, controls LLM context
_EXCERPT_CHARS = 500      # Word count of excerpts per analyst report


@tool
@register_tool(
    tool_id="get_latest_report",
    name="获取最新报告",
    description="Read the summary of the latest completed analysis report for the specified stock (core conclusions of each analyst)+final research conclusion). No new tasks will be created. When symbol is empty, the user s most recent report is returned.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "latest", "query", "assistant_ops", "latest_report", "recent_report", "stock_report", "analyst_summary"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["latest_report_viewing", "recent_report_query", "stock_analysis_summary", "analyst_report_summary"],
    returns="Returns a formatted text report containing investment views, price range, decision rationale, key takeaways and individual analyst excerpts.",
    when_to_use="Used when the user wants to quickly view a summary of the latest completed analysis report for a certain stock. No new task will be created.",
)
async def get_latest_report(
    symbol: Annotated[str, "Stock code, such as 600519. If the user does not specify an empty string, the latest report for any stock will be returned."],
) -> str:
    """Read the summary of the latest completed analysis report for a certain stock without creating a new task. When symbol is empty, the user s latest report is returned."""
    try:
        from bson import ObjectId
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread

        user_id = require_current_user_id()
        db = get_mongo_db()

        # ── Construct query: No limit on stock code when symbol is empty ──
        query: dict = {"user_id": ObjectId(user_id), "status": "completed"}
        sym_clean = (symbol or "").strip()
        if sym_clean:
            query["task_params.symbol"] = sym_clean

        doc = await db.unified_analysis_tasks.find_one(query, sort=[("created_at", -1)])
        if not doc:
            hint = f"{sym_clean} 的" if sym_clean else "任何"
            return (
                f"未找到{hint}分析报告。"
                f"{'You can use Trigger Stock Analysis to initiate analysis.' if sym_clean else 'Please trigger a stock analysis first.'}"
            )

        r = doc.get("result") or {}
        actual_symbol = doc.get("task_params", {}).get("symbol", sym_clean or "未知")
        created = doc.get("created_at")
        date_str = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else (str(created)[:16] if created else "未知")
        task_id = doc.get("task_id", "")

        # ── Part One: Structured Summary (required) ──
        lines: list[str] = [f"📈 {actual_symbol} 分析报告（{date_str}）"]

        decision = r.get("decision") or {}
        action = decision.get("action") or decision.get("analysis_view", "")
        confidence = decision.get("confidence")
        risk_score = decision.get("risk_score")
        price_range = decision.get("price_analysis_range")
        reasoning = (decision.get("reasoning") or "")[:400]

        if action:
            conf_str = f"  置信度: {confidence:.0%}" if confidence is not None else ""
            risk_str = f"  风险分: {risk_score:.0%}" if risk_score is not None else ""
            lines.append(f"\n【投资观点】{action}{conf_str}{risk_str}")
        if price_range and isinstance(price_range, (list, tuple)) and len(price_range) == 2:
            lines.append(f"【价格区间参考】{price_range[0]} ~ {price_range[1]}")
        if reasoning:
            lines.append(f"【决策依据】\n{reasoning}")

        rec = (r.get("recommendation") or "")[:300]
        if rec and rec != action:
            lines.append(f"\n【建议摘要】\n{rec}")

        risk_level = r.get("risk_level", "")
        if risk_level:
            lines.append(f"【风险等级】{risk_level}")

        key_points = r.get("key_points") or []
        if key_points:
            kp_text = "\n".join(f"  • {kp}" for kp in key_points[:5])
            lines.append(f"\n【关键要点】\n{kp_text}")

        summary = (r.get("summary") or "")[:400]
        if summary:
            lines.append(f"\n【综合摘要】\n{summary}")

        await attach_report_ref_to_thread(
            db,
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "stock_report",
                "report_key": task_id,
                "source_collection": "unified_analysis_tasks",
                "title": f"{actual_symbol} 分析报告",
                "symbol": actual_symbol,
                "summary": (summary or rec or reasoning or "")[:400],
                "status": doc.get("status") or "completed",
                "task_id": task_id,
                "created_at": created,
            },
        )

        # ── Part 2: Excerpts by analysts (by priority, subject to total word limit) ──
        reports: dict = r.get("reports") or {}
        if reports:
            lines.append("\n─── Excerpts from various analysts ───")
            current_len = sum(len(l) for l in lines)
            for key in _REPORT_PRIORITY:
                if current_len >= _MAX_TOTAL_CHARS:
                    lines.append(" (More content has been omitted, you can use View Report Details to get the full version)")
                    break
                text = reports.get(key)
                if not text or not isinstance(text, str) or len(text.strip()) < 20:
                    continue
                label = _ANALYST_LABELS.get(key, key)
                excerpt = text.strip()[:_EXCERPT_CHARS]
                if len(text.strip()) > _EXCERPT_CHARS:
                    excerpt += "…"
                snippet = f"\n[{label}]\n{excerpt}"
                lines.append(snippet)
                current_len += len(snippet)

        lines.append(f"\n─\n Task ID: {task_id[:12]}…")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_latest_report] Failed to get latest report: %s", e)
        return f"获取最新报告时出错: {str(e)}"


@tool
@register_tool(
    tool_id="search_attachable_reports",
    name="搜索可关联旧报告",
    description="Search for old reports under the current topic that can be manually linked. Suitable for users to say Before linking old CATL reports to the current topic, first check what old reports are available. . ",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "search", "attachable", "assistant_ops", "report_attachment", "topic_report_linking", "report_search"],
    tool_role_hint="specialized",
    output_shape="text",
    preferred_for=["attachable_report_search", "report_attachment_query", "topic_report_linking_prep"],
    returns="Returns a text list containing the title, ticker, creation time, and report ID of the old report that can be associated.",
    when_to_use="This is used when the user wants to see what optional reports are available before linking an old report on a certain stock to the current topic.",
)
async def search_attachable_reports(
    keyword: Annotated[Optional[str], "Stock code, company name or report keywords, such as CATL/BYD / 300750"] = None,
    report_type: Annotated[str, "Report type: stock_report single stock report; position_report position report"] = "stock_report",
    limit: Annotated[int, "Returns the upper limit of quantity, default 5"] = 5,
) -> str:
    """Searches for old reports that can be associated with the current topic."""
    try:
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import search_assistant_attachable_reports

        user_id = require_current_user_id()
        thread_id = get_current_assistant_thread_id()
        if not thread_id:
            return "There is currently no selected research topic to search for related reports."

        db = get_mongo_db()
        items = await search_assistant_attachable_reports(
            db,
            user_id,
            thread_id,
            ref_type=(report_type or "stock_report").strip() or "stock_report",
            keyword=(keyword or "").strip() or None,
            limit=max(1, min(limit, 10)),
        )
        if not items:
            target = (keyword or "历史报告").strip() or "历史报告"
            return f"未找到与“{target}”匹配的可关联旧报告。"

        lines = [f"找到 {len(items)} 条可关联旧报告："]
        for item in items:
            title = item.get("title") or "未命名报告"
            symbol = item.get("symbol") or ""
            created_at = item.get("created_at")
            if hasattr(created_at, "strftime"):
                created_text = created_at.strftime("%Y-%m-%d %H:%M")
            else:
                created_text = str(created_at)[:16] if created_at else "未知时间"
            report_key = item.get("report_key") or ""
            lines.append(f"- {title} | {symbol} | {created_text} | key={report_key}")
        lines.append("If you want to link directly to the current topic, you can continue to say: Link this old report to the current topic.")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[search_attachable_reports] Search for relatable old reports failed: %s", e)
        return f"搜索可关联旧报告时出错: {str(e)}"


@tool
@register_tool(
    tool_id="attach_existing_report_to_current_topic",
    name="关联旧报告到当前主题",
    description="Directly link old reports that have been generated by the user to the current research topic. Suitable for users to say Relate old CATL reports to current topics . The latest matching copy is associated by default.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "attach", "link", "assistant_ops", "report_attachment", "topic_report_linking", "report_binding"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["report_attachment", "topic_report_linking", "historical_report_binding", "report_to_topic_association"],
    returns="Returns a text message containing correlation results and report identification.",
    when_to_use="It is used when the user requests to directly link the historical reports of a certain stock to the current research topic.",
)
async def attach_existing_report_to_current_topic(
    keyword: Annotated[str, "Stock code, company name or report keywords, such as CATL/BYD / 300750"],
    report_type: Annotated[str, "Report type: stock_report single stock report; position_report position report"] = "stock_report",
) -> str:
    """Hang the latest matching old reports to the current topic based on keywords."""
    try:
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import (
            attach_existing_report_to_thread,
            search_assistant_attachable_reports,
        )

        user_id = require_current_user_id()
        thread_id = get_current_assistant_thread_id()
        if not thread_id:
            return "There is currently no research topic selected and old reports cannot be associated."

        keyword_clean = (keyword or "").strip()
        if not keyword_clean:
            return "Please provide stock code, company name or report keywords, for example: CATL, BYD, 300750."

        db = get_mongo_db()
        matches = await search_assistant_attachable_reports(
            db,
            user_id,
            thread_id,
            ref_type=(report_type or "stock_report").strip() or "stock_report",
            keyword=keyword_clean,
            limit=3,
        )
        if not matches:
            return f"未找到与“{keyword_clean}”匹配的旧报告，暂时无法关联。"

        target = matches[0]
        attached_ref = await attach_existing_report_to_thread(
            db,
            user_id,
            thread_id,
            target.get("ref_type") or report_type,
            target.get("report_key") or "",
        )
        if not attached_ref:
            return f"找到了“{keyword_clean}”的旧报告，但关联失败。"

        title = attached_ref.get("title") or keyword_clean
        report_key = attached_ref.get("report_key") or ""
        extra = ""
        if len(matches) > 1:
            extra = f"\n另外还找到 {len(matches) - 1} 条相近历史报告，如需可继续指定日期或让我继续关联。"
        return f"已将旧报告《{title}》关联到当前主题。\n报告标识: {report_key}{extra}"
    except Exception as e:
        logger.exception("[attach_existing_report_to_current_topic] Failed to associate old reports: %s", e)
        return f"关联旧报告时出错: {str(e)}"
