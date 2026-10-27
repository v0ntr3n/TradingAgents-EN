"""
TradingAgents-CN MCP Server

Use fastmcp to expose multi-agent analysis capabilities for external MCP Client calls.

MCP Tool list:
- analyze_stock       — Trigger stock analysis (supports blocking/non-blocking)
- get_report          — Query historical analysis report
- chat_with_assistant — Chat freely with an analysis assistant
- list_workflows      — List available analysis workflows
- screen_stocks       — Intelligent stock selection based on conditions (natural language)
- get_market_overview — Get market overview (A shares)
"""

import asyncio
import logging
import os
from typing import Optional

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP, Context

from core.mcp.auth import mcp_auth

logger = logging.getLogger(__name__)

# ── FastMCP Example ──
# When environment variables MCP_AUTH_ENABLED=true Enable API Key authentication;
# Otherwise (development/stdio mode) authentication is not enabled.
_auth_enabled = os.getenv("MCP_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")

_auth_settings = None
if _auth_enabled:
    _auth_settings = AuthSettings(
        issuer_url=os.getenv("MCP_AUTH_ISSUER_URL", "http://127.0.0.1:8000/mcp"),
        resource_server_url=os.getenv("MCP_RESOURCE_SERVER_URL", "http://127.0.0.1:8000/mcp"),
        required_scopes=mcp_auth.required_scopes,
    )

mcp = FastMCP(
    "TradingAgents-CN",
    version="1.0.0",
    instructions=(
        "TradingAgents-CN It is a multi-agent A-share analysis system.\n"
        "You can use analyze_stock to trigger in-depth analysis and get_report to view the report,\n"
        "Use chat_with_assistant for free chat, use list_workflows to view available workflows,\n"
        "Use screen_stocks to intelligently select stocks based on conditions, and use get_market_overview to get an overview of the A-share market."
    ),
    auth=_auth_settings,
    token_verifier=mcp_auth if _auth_enabled else None,
)


# ── Database initialization assistance ──
_db_initialized = False


async def _ensure_db():
    """Make sure the database connection is initialized (lazy initialization, only performed on the first call)"""
    global _db_initialized
    if _db_initialized:
        return
    from app.core.database import init_database
    await init_database()
    _db_initialized = True
    logger.info("✅ MCP Server Database connection has been initialized")


# ── Depth mapping (consistent with assistant_ops)──
_DEPTH_MAP = {1: "fast", 2: "Basics", 3: "Standard", 4: "Depth", 5: "Comprehensive"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCP Tool 1: analyze_stock
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def analyze_stock(
    symbol: str,
    depth: int = 3,
    wait: bool = False,
    workflow_id: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """
    Conduct multi-agent collaborative analysis on designated A-share stocks.

    Args:
        symbol: Stock code, 6 digits, such as "600519" (Kweichow Moutai),"000858" (Wuliangye)
        depth: Analysis Depth 1-5 (1=fast, 2=Basics, 3=Standard, 4=Depth, 5=Comprehensive), default 3
        wait: Whether to block waiting for analysis to complete.True=Wait for complete report to be returned (up to 5 minutes);False=Return to task immediately ID
        workflow_id: Specify workflow ID (optional, if not specified, the default workflow will be used)

    Returns:
        wait=False Return the task ID and status prompt;wait=True Return the complete Markdown analysis report when
    """
    await _ensure_db()

    from bson import ObjectId
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType
    from core.tools.context import set_current_user_id

    mcp_user_id = await _get_mcp_user_id(ctx)
    set_current_user_id(mcp_user_id)

    service = get_task_analysis_service()
    depth_label = _DEPTH_MAP.get(depth, "Standard")

    if wait:
        # Blocking mode: create and wait for completion
        task = await service.create_and_execute_task(
            user_id=ObjectId(mcp_user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params={"symbol": symbol, "market_type": "cn", "research_depth": depth_label, "_mcp_source": True},
            engine_type="auto",
            workflow_id=workflow_id,
        )
        return _format_report(task)
    else:
        # Non-blocking mode: return immediately task_id
        task = await service.create_task(
            user_id=ObjectId(mcp_user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params={"symbol": symbol, "market_type": "cn", "research_depth": depth_label, "_mcp_source": True},
            engine_type="auto",
            workflow_id=workflow_id,
        )
        asyncio.create_task(service.execute_task(task.task_id))
        return (
            f"✅ Analysis task has been created\n"
            f"- Task ID: {task.task_id}\n"
            f"- stocks: {symbol}\n"
            f"- Depth: {depth_label}\n"
            f"- Estimated time to complete is 2-5 minutes\n\n"
            f"Please call later get_report(task_id=\"{task.task_id}\") Get the full report."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCP Tool 2: get_report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_report(
    task_id: Optional[str] = None,
    symbol: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """
    Query analysis report. Can be queried by task ID or stock code.

    Args:
        task_id: Analysis task ID (returned by analyze_stock)
        symbol: Stock code (query the latest completed report for this stock)

    Returns:
        Markdown format analysis report, or task status information
    """
    if not task_id and not symbol:
        return "❌ Please provide task_id or symbol parameter"

    await _ensure_db()

    from bson import ObjectId
    from app.services.task_analysis_service import get_task_analysis_service
    from app.core.database import get_mongo_db
    from core.tools.context import set_current_user_id

    mcp_user_id = await _get_mcp_user_id(ctx)
    set_current_user_id(mcp_user_id)

    if task_id:
        # Query by task_id
        service = get_task_analysis_service()
        task = await service.get_task(task_id)
        if not task:
            return f"❌ Task not found: {task_id}"
        if task.status != "completed":
            status_emoji = {"pending": "⏳", "processing": "🔄", "failed": "❌", "cancelled": "🚫"}
            emoji = status_emoji.get(task.status, "❓")
            return f"{emoji} The task has not been completed (status: {task.status}, Progress: {task.progress}%) "
        return _format_report(task)
    else:
        # Query recent reports by symbol
        db = get_mongo_db()
        doc = await db.unified_analysis_tasks.find_one(
            {"user_id": ObjectId(mcp_user_id), "task_params.symbol": symbol, "status": "completed"},
            sort=[("created_at", -1)],
        )
        if not doc:
            return f"not found {symbol} analysis report. you can call analyze_stock(symbol=\"{symbol}\") Initiate analysis."

        # Build a brief report
        result = doc.get("result", {})
        recommendation = result.get("recommendation", "None")
        confidence = result.get("confidence", "N/A")
        summary = result.get("summary", "No abstract")
        return (
            f"# {symbol} Recent analysis reports\n\n"
            f"**research conclusion tendency**: {recommendation}\n"
            f"**degree of certainty**: {confidence}\n\n"
            f"## Summary\n{summary}\n\n"
            f"💡 Use get_report(task_id=\"{doc.get('task_id', '')}\") Get full details."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCP Tool 3: chat_with_assistant
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def chat_with_assistant(message: str, ctx: Context = None) -> str:
    """
    Chat freely with TradingAgents analysis assistants.
    The assistant has operational capabilities such as data query, analysis triggering, report viewing, and stock watch list management.

    Args:
        message: Your questions or instructions such as "Help me analyze 600519", "What are the recent analysis reports?", "What are the fundamentals of Moutai?"

    Returns:
        Assistant s reply
    """
    await _ensure_db()

    from app.services.intelligent_assistant_service import chat_with_assistant as _chat
    from app.core.database import get_mongo_db

    mcp_user_id = await _get_mcp_user_id(ctx)
    db = get_mongo_db()

    result = await _chat(
        db=db,
        user_message=message,
        user_id=mcp_user_id,
    )
    return result.get("reply", "The assistant is temporarily unable to reply, please try again later.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCP Tool 4: list_workflows
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def list_workflows(ctx: Context = None) -> str:
    """
    Lists the analysis workflows available in the system.
    Each workflow represents a different analysis strategy (such as standard analysis, in-depth analysis, quick screening, etc.).

    Returns:
        List of available workflows with ID, name and description
    """
    await _ensure_db()

    from app.core.database import get_mongo_db

    db = get_mongo_db()
    cursor = db.workflow_definitions.find(
        {"is_active": True},
        {"workflow_id": 1, "name": 1, "description": 1, "category": 1, "_id": 0},
    )
    workflows = await cursor.to_list(length=50)

    if not workflows:
        return "There are currently no workflows available."

    lines = ["# Available analysis workflows\n"]
    for wf in workflows:
        wf_id = wf.get("workflow_id", "N/A")
        name = wf.get("name", "Unnamed")
        desc = wf.get("description", "No description")
        cat = wf.get("category", "")
        cat_tag = f" [{cat}]" if cat else ""
        lines.append(f"- **{name}**{cat_tag}\n  ID: `{wf_id}`\n  {desc}\n")

    lines.append("\n💡 Use the workflow_id parameter in analyze_stock to specify the workflow.")
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCP Tool 5: screen_stocks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def screen_stocks(
    criteria: str,
    max_stocks: int = 10,
    ctx: Context = None,
) -> str:
    """
    Intelligently filter A-shares based on natural language conditions and return a list of stocks that meet the conditions and their reasons.

    Args:
        criteria: Filter criteria (natural language) such as "PE Technology stocks less than 20", "A consumer leader with a market value greater than 10 billion"
        max_stocks: Maximum number of stocks returned, default 10

    Returns:
        Explanation of stock selection results and stock list (including code, name, brief reason)
    """
    await _ensure_db()

    from app.core.database import get_mongo_db
    from app.services.intelligent_screening_service import IntelligentScreeningService
    from core.tools.context import set_current_user_id

    mcp_user_id = await _get_mcp_user_id(ctx)
    set_current_user_id(mcp_user_id)

    db = get_mongo_db()
    service = IntelligentScreeningService(db)
    result = await service.run_direct_screening(
        user_id=mcp_user_id,
        criteria=criteria,
        max_stocks=max_stocks,
    )
    reply = result.get("reply", "The stock picking service is temporarily unavailable.")
    stocks = result.get("stocks") or []
    if stocks:
        lines = [reply, "\n## Filter results\n"]
        for i, s in enumerate(stocks[:max_stocks], 1):
            code = s.get("code", "")
            name = s.get("name", "")
            reason = s.get("reason", "")
            lines.append(f"{i}. **{name}**({code}) {reason}")
        return "\n".join(lines)
    return reply


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCP Tool 6: get_market_overview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_market_overview(
    market: str = "cn",
    ctx: Context = None,
) -> str:
    """
    Get an overall overview of a given market (index rise and fall, transactions, etc.).
    Currently only A shares (cn) are supported.

    Args:
        market: market code,cn=A shares / hk=Hong Kong stocks / us=US stocks; currently only supported cn

    Returns:
        Market Overview Report (Markdown)
    """
    if market and market.lower() not in ("cn", "china", "a", "a shares"):
        return "❌ Currently only A-share market overview is supported, please use market=\"cn\". The overview of Hong Kong stocks/U.S. stocks will be available later."

    await _ensure_db()

    from app.services.intelligent_assistant_service import _get_latest_trade_date
    from core.tools import get_tool_registry

    curr_date = _get_latest_trade_date()
    registry = get_tool_registry()
    fn = registry.get_function("get_china_market_overview")
    if not fn:
        return "❌ The China Market Overview tool is not registered, please check your system configuration."
    try:
        report = await asyncio.to_thread(fn, curr_date=curr_date)
        return report if report else "There is no market overview data yet."
    except Exception as e:
        logger.warning("get_market_overview call failed: %s", e)
        return f"❌ Failed to get market overview: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper function
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _get_mcp_user_id(ctx: Optional[Context] = None) -> str:
    """Get MCP service user ID

    Priority:
    1. Get from Context.client_id (authentication mode, user_id mapped by API Key)
    2. Find admin user from database (fallback for unauthenticated/stdio mode)
    """
    # 1. Priority is given to using certified client_id
    if ctx is not None:
        client_id = ctx.client_id
        if client_id:
            return client_id

    # 2. Fallback: Find default user from database
    from app.core.database import get_mongo_db

    db = get_mongo_db()
    user = await db.users.find_one({"role": "admin"}, {"_id": 1})
    if user:
        return str(user["_id"])

    user = await db.users.find_one({}, {"_id": 1})
    if user:
        return str(user["_id"])

    raise RuntimeError("There is no user in the database, please create a user first.")


def _format_report(task) -> str:
    """Format analysis task results into a Markdown report"""
    if not task.result:
        return "⚠️ The task was completed but no report data was generated."

    result = task.result if isinstance(task.result, dict) else {}
    symbol = (task.task_params or {}).get("symbol", "unknown")
    recommendation = result.get("recommendation", "None")
    confidence = result.get("confidence", "N/A")
    summary = result.get("summary", "")
    risk = result.get("risk_assessment", "")
    key_points = result.get("key_points", [])

    lines = [
        f"# {symbol} analysis report\n",
        f"**research conclusion tendency**: {recommendation}",
        f"**degree of certainty**: {confidence}\n",
    ]
    if summary:
        lines.append(f"## Summary\n{summary}\n")
    if risk:
        lines.append(f"## risk assessment\n{risk}\n")
    if key_points:
        lines.append("## Key takeaways")
        for pt in key_points:
            lines.append(f"- {pt}")

    return "\n".join(lines)
