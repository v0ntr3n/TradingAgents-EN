"""Use the Q&A bot tool: Query the data synchronization status.

Provides the ability to query the synchronization status of tushare/akshare s historical market prices, financial data, and basic stock data.
Allows using Q&A Assistant to"see"Whether data source synchronization is normal and whether new synchronization needs to be triggered?
Instead of guessing the answer based on the FAQ.

Covered query dimensions:
1. Stock basic data (stock_basic_info / sync_status collection)——Overall status of multi-source synchronization tasks
2. Historical market data (historical_data collection)——Number of stocks covered, date of latest data, number of records
3. Financial data (stock_financial_data collection)——Number of stocks covered, latest update time, number of records
4. Single stock synchronization status (when passing symbol)——The stock s historical/financial/basic data synchronization
5. Running synchronization tasks (stock_sync_tasks collection)——Are there any tasks running?
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# Synchronization status collection and task identification (consistent with app/services/multi_source_basics_sync_service.py)
_SYNC_STATUS_COLLECTION = "sync_status"
_STOCK_BASICS_JOB_KEY = "stock_basics_multi_source"
_STOCK_SYNC_TASKS_COLLECTION = "stock_sync_tasks"

# data collection
_HISTORICAL_DATA_COLLECTION = "historical_data"
_FINANCIAL_DATA_COLLECTION = "stock_financial_data"
_STOCK_BASIC_INFO_COLLECTION = "stock_basic_info"


def _format_time_ago(iso_str: Optional[str]) -> str:
    """Format ISO time string to human readable'X hours ago'format."""
    if not iso_str:
        return "从未"
    try:
        # Compatible with time strings with Z and time zone
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        now = datetime.now()
        diff = now - dt
        if diff.total_seconds() < 0:
            return dt.strftime("%Y-%m-%d %H:%M")
        if diff.total_seconds() < 60:
            return "刚刚"
        if diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() / 60)} 分钟前"
        if diff.total_seconds() < 86400:
            return f"{int(diff.total_seconds() / 3600)} 小时前"
        days = int(diff.total_seconds() / 86400)
        if days < 30:
            return f"{days} 天前"
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso_str)[:19]


def _summarize_status(status: str) -> tuple[str, str]:
    """Map the internal status field to (emoji, Chinese description). """
    mapping = {
        "success": ("✅", "成功"),
        "success_with_errors": ("⚠️", "成功（含部分错误）"),
        "running": ("🔄", "运行中"),
        "queued": ("⏳", "排队中"),
        "failed": ("❌", "失败"),
        "idle": ("💤", "空闲"),
        "never_run": ("⚪", "从未运行"),
    }
    return mapping.get(status, ("❓", status or "未知"))


async def _query_stock_basics_sync(db) -> Dict[str, Any]:
    """Query the synchronization status of basic stock data (multi-source synchronization task)."""
    try:
        doc = await db[_SYNC_STATUS_COLLECTION].find_one({"job": _STOCK_BASICS_JOB_KEY})
        if not doc:
            return {"available": False}
        doc.pop("_id", None)
        return {"available": True, "doc": doc}
    except Exception as exc:
        logger.warning("[get_data_sync_status] Failed to query basic stock data synchronization status: %s", exc)
        return {"available": False, "error": str(exc)}


async def _query_historical_overview(db) -> Dict[str, Any]:
    """Query the overall situation of historical market data: number of stocks covered, latest data date, and total number of records."""
    try:
        total_records = await db[_HISTORICAL_DATA_COLLECTION].count_documents({})
        distinct_symbols = await db[_HISTORICAL_DATA_COLLECTION].distinct("symbol")
        # Latest data date (descending order by date field)
        latest_doc = await db[_HISTORICAL_DATA_COLLECTION].find_one(
            {}, sort=[("date", -1)]
        )
        latest_date = None
        if latest_doc:
            d = latest_doc.get("date")
            if isinstance(d, datetime):
                latest_date = d.strftime("%Y-%m-%d")
            elif d:
                latest_date = str(d)[:10]
        return {
            "total_records": total_records,
            "symbol_count": len(distinct_symbols) if distinct_symbols else 0,
            "latest_date": latest_date,
        }
    except Exception as exc:
        logger.warning("[get_data_sync_status] Querying the overall situation of historical data failed: %s", exc)
        return {"error": str(exc)}


async def _query_financial_overview(db) -> Dict[str, Any]:
    """Query the overall situation of financial data: number of stocks covered, latest update time, and total number of records."""
    try:
        total_records = await db[_FINANCIAL_DATA_COLLECTION].count_documents({})
        distinct_symbols = await db[_FINANCIAL_DATA_COLLECTION].distinct("symbol")
        latest_doc = await db[_FINANCIAL_DATA_COLLECTION].find_one(
            {}, sort=[("updated_at", -1)]
        )
        latest_updated = None
        if latest_doc:
            u = latest_doc.get("updated_at")
            if isinstance(u, datetime):
                latest_updated = u.isoformat()
            elif u:
                latest_updated = str(u)
        return {
            "total_records": total_records,
            "symbol_count": len(distinct_symbols) if distinct_symbols else 0,
            "latest_updated": latest_updated,
        }
    except Exception as exc:
        logger.warning("[get_data_sync_status] Failed to query the overall financial data: %s", exc)
        return {"error": str(exc)}


async def _query_running_sync_tasks(db) -> List[Dict[str, Any]]:
    """Query the running synchronization tasks."""
    try:
        cursor = db[_STOCK_SYNC_TASKS_COLLECTION].find(
            {"status": {"$in": ["running", "pending", "queued"]}},
            {"task_id": 1, "task_type": 1, "symbol": 1, "status": 1, "started_at": 1, "progress": 1}
        ).limit(10)
        docs = await cursor.to_list(length=10)
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception as exc:
        logger.warning("[get_data_sync_status] Synchronization task failed during query running: %s", exc)
        return []


async def _query_single_stock_status(db, symbol: str) -> Dict[str, Any]:
    """Query the synchronization status of a single stock. Reuse the logic of stock_sync routing."""
    try:
        normalized = str(symbol).strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]

        # historical data
        hist_doc = await db[_HISTORICAL_DATA_COLLECTION].find_one(
            {"symbol": normalized}, sort=[("date", -1)]
        )
        hist_count = await db[_HISTORICAL_DATA_COLLECTION].count_documents({"symbol": normalized})

        # financial data
        fin_doc = await db[_FINANCIAL_DATA_COLLECTION].find_one(
            {"symbol": normalized}, sort=[("updated_at", -1)]
        )
        fin_count = await db[_FINANCIAL_DATA_COLLECTION].count_documents({"symbol": normalized})

        # Basic data
        basic_doc = await db[_STOCK_BASIC_INFO_COLLECTION].find_one({"symbol": normalized})

        return {
            "symbol": normalized,
            "historical": {
                "last_sync": hist_doc.get("updated_at") if hist_doc else None,
                "last_date": (
                    hist_doc.get("date").strftime("%Y-%m-%d")
                    if hist_doc and isinstance(hist_doc.get("date"), datetime)
                    else (str(hist_doc.get("date"))[:10] if hist_doc and hist_doc.get("date") else None)
                ),
                "total_records": hist_count,
            },
            "financial": {
                "last_sync": fin_doc.get("updated_at") if fin_doc else None,
                "total_records": fin_count,
            },
            "basic": {"available": basic_doc is not None},
        }
    except Exception as exc:
        logger.warning("[get_data_sync_status] Failed to query single stock synchronization status(%s): %s", symbol, exc)
        return {"symbol": symbol, "error": str(exc)}


def _format_single_stock_status(result: Dict[str, Any]) -> List[str]:
    """Format single sync status as a text line."""
    if result.get("error"):
        return [f"❌ 查询失败: {result['error']}"]

    lines = [f"📊 股票 {result.get('symbol', '?')} 的数据同步状态"]

    hist = result.get("historical", {})
    hist_records = hist.get("total_records", 0)
    if hist_records > 0:
        lines.append(
            f"- 历史行情: ✅ 已同步 {hist_records} 条，"
            f"latest date {hist.get('last_date', '?')} (Update time: {_format_time_ago(hist.get('last_sync'))}) "
        )
    else:
        lines.append("- Historical Quotes: ❌ Not synchronized (the stock has no record in the historical_data collection)")

    fin = result.get("financial", {})
    fin_records = fin.get("total_records", 0)
    if fin_records > 0:
        lines.append(
            f"- 财务数据: ✅ 已同步 {fin_records} 条（更新时间: {_format_time_ago(fin.get('last_sync'))}）"
        )
    else:
        lines.append("- financial data: ❌ Not synchronized (the stock has no record in the stock_financial_data collection)")

    basic = result.get("basic", {})
    if basic.get("available"):
        lines.append("- Basic data: ✅ Synced")
    else:
        lines.append("- Basic data: ❌ Not synced")

    # Comprehensive judgment
    has_data = hist_records > 0 or fin_records > 0
    if not has_data:
        lines.append("")
        lines.append("💡 This stock has not yet synchronized data. It is recommended to trigger synchronization before analysis.")
        lines.append("   It can be said: Synchronize the data of stock 600519 ")
    elif hist_records == 0:
        lines.append("")
        lines.append("💡 There is a lack of historical market data. If analysis is required, please synchronize historical data first.")
    elif fin_records == 0:
        lines.append("")
        lines.append("💡 Financial data is missing. If you need to do financial analysis, please synchronize the financial data first.")

    return lines


@tool
@register_tool(
    tool_id="get_data_sync_status",
    name="查询数据同步状态",
    description="Query the data synchronization status of tushare/akshare: basic stock data, historical quotes, the latest synchronization time of financial data, the number of records, and whether the synchronization task is running. Supports passing symbol to search single stocks, but not passing it to search the whole stock. When the user asks'Is the data synchronized?''Is the data up to date?''Do you want to resynchronize?'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "data_sync_status", "tushare", "akshare", "historical_data", "financial_data", "sync_status", "data_freshness"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "数据同步好了吗",
        "数据是否最新",
        "tushare 同步状态",
        "历史数据同步到什么时候",
        "财务数据是否需要更新",
        "中国银行数据同步了吗",
        "是否需要重新同步",
        "有同步任务在跑吗",
    ],
    when_to_use="Used when users ask about data synchronization status, data freshness, whether resynchronization is needed, and whether there are synchronization tasks running. Supports passing symbol parameter to check single stock data synchronization status.",
    returns="Returns a data synchronization status summary in text format, including the latest synchronization time and record number of basic data/historical market data/financial data, running synchronization tasks, and judgment on whether new synchronization needs to be triggered.",
)
async def get_data_sync_status(
    symbol: Annotated[
        Optional[str],
        "Stock code (optional, 6 digits such as 600519). If it is passed in, the synchronization status of the stock will be checked; if it is not passed, the overall data synchronization status will be checked."
    ] = None,
) -> str:
    """Query the data synchronization status."""
    from app.core.database import get_mongo_db

    db = get_mongo_db()

    # ---- Single stock query branch ----
    if symbol and str(symbol).strip():
        result = await _query_single_stock_status(db, str(symbol).strip())
        return "\n".join(_format_single_stock_status(result))

    # ---- Overall query branch ----
    basics_sync = await _query_stock_basics_sync(db)
    hist_overview = await _query_historical_overview(db)
    fin_overview = await _query_financial_overview(db)
    running_tasks = await _query_running_sync_tasks(db)

    lines = ["📊 数据同步状态总览"]

    # 1) Stock basic data synchronization task
    if basics_sync.get("available"):
        doc = basics_sync["doc"]
        status = doc.get("status", "未知")
        emoji, status_cn = _summarize_status(status)
        lines.append("")
        lines.append(" [1] Basic stock data (A-share list+Industry+financial indicators)")
        lines.append(f"- 状态: {emoji} {status_cn}")
        if doc.get("started_at"):
            lines.append(f"- 最近开始时间: {_format_time_ago(doc.get('started_at'))}")
        if doc.get("finished_at"):
            lines.append(f"- 最近完成时间: {_format_time_ago(doc.get('finished_at'))}")
        total = doc.get("total", 0) or 0
        inserted = doc.get("inserted", 0) or 0
        updated = doc.get("updated", 0) or 0
        errors = doc.get("errors", 0) or 0
        if total > 0 or inserted > 0 or updated > 0:
            lines.append(f"- 总数 {total}：新增 {inserted}，更新 {updated}，错误 {errors}")
        if doc.get("last_trade_date"):
            lines.append(f"- 最近交易日: {doc.get('last_trade_date')}")
        sources_used = doc.get("data_sources_used") or []
        if sources_used:
            lines.append(f"- 使用的数据源: {', '.join(sources_used)}")
        if doc.get("message") and status in {"failed", "success_with_errors"}:
            lines.append(f"- 备注: {doc.get('message')}")
    else:
        lines.append("")
        lines.append(" [1] Basic stock data: ⚪ No synchronization task has ever been run")

    # 2) The overall situation of historical market data
    lines.append("")
    lines.append(" [2] Historical market data (historical_data)")
    if hist_overview.get("error"):
        lines.append(f"- ❌ 查询失败: {hist_overview['error']}")
    else:
        symbol_count = hist_overview.get("symbol_count", 0)
        total_records = hist_overview.get("total_records", 0)
        latest_date = hist_overview.get("latest_date")
        lines.append(f"- 已覆盖股票数: {symbol_count}")
        lines.append(f"- 总记录数: {total_records}")
        lines.append(f"- 最新数据日期: {latest_date or '无'}")
        if symbol_count == 0:
            lines.append("- ⚠️ The data is empty. It is recommended to trigger the synchronization of basic stock data before synchronizing single stocks.")

    # 3) Overall financial data
    lines.append("")
    lines.append(" [3] Financial data (stock_financial_data)")
    if fin_overview.get("error"):
        lines.append(f"- ❌ 查询失败: {fin_overview['error']}")
    else:
        symbol_count = fin_overview.get("symbol_count", 0)
        total_records = fin_overview.get("total_records", 0)
        latest_updated = fin_overview.get("latest_updated")
        lines.append(f"- 已覆盖股票数: {symbol_count}")
        lines.append(f"- 总记录数: {total_records}")
        lines.append(f"- 最近更新时间: {_format_time_ago(latest_updated)}")

    # 4) Running sync tasks
    lines.append("")
    lines.append("【4】运行中的同步任务")
    if not running_tasks:
        lines.append("- 💤 There are currently no sync tasks running")
    else:
        lines.append(f"- 🔄 共 {len(running_tasks)} 个任务在运行:")
        for t in running_tasks[:5]:
            task_type = t.get("task_type", "?")
            sym = t.get("symbol", "?")
            st = t.get("status", "?")
            started = _format_time_ago(t.get("started_at")) if t.get("started_at") else "?"
            progress = t.get("progress")
            progress_str = f", Progress {progress}" if progress is not None else ""
            lines.append(f"  • [{task_type}] {sym} | {st} | 开始于 {started}{progress_str}")

    # 5) Comprehensive suggestions
    lines.append("")
    lines.append("💡 综合判断")
    suggestions = []

    basics_status = basics_sync.get("doc", {}).get("status") if basics_sync.get("available") else "never_run"
    if basics_status == "running":
        suggestions.append("Basic stock data synchronization is running, please wait for completion before viewing details.")
    elif basics_status == "failed":
        suggestions.append("⚠️ The basic stock data synchronization failed last time. It is recommended to check the cause of the error on the Data Synchronization page or trigger it again.")
    elif basics_status in ("never_run", "idle") or not basics_sync.get("available"):
        suggestions.append("The basic stock data has not been synchronized yet. It is recommended to trigger the synchronization of the basic stock data first.")

    hist_symbol_count = hist_overview.get("symbol_count", 0) if not hist_overview.get("error") else 0
    if hist_symbol_count == 0:
        suggestions.append("The historical market data is empty. Stock data needs to be synchronized before analysis.")
    elif hist_symbol_count < 100:
        suggestions.append(f"历史行情仅覆盖 {hist_symbol_count} 只股票，建议补充同步")

    fin_symbol_count = fin_overview.get("symbol_count", 0) if not fin_overview.get("error") else 0
    if fin_symbol_count == 0:
        suggestions.append("The financial data is empty and needs to be synchronized before doing financial analysis.")

    if not suggestions:
        lines.append("- ✅ Data synchronization is normal and analysis tasks can be performed normally.")
    else:
        for s in suggestions:
            lines.append(f"- {s}")

    lines.append("")
    lines.append("📌 Note: JD Cloud version only supports Tushare + AKShare Two data sources, forcing single concurrency, synchronization will be slower")

    return "\n".join(lines)
