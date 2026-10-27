"""
Assistant Ops tool module (Assistant Ops)

Provides operation tools such as analysis triggering, report query, scheduled task management, stock watch list management, etc.
Make the smart assistant from"data coach"upgraded to"versatile operator". 

tools pass @register_tool The decorator is automatically registered with the ToolRegistry.
The user identity is obtained through the contextvars mechanism of core.tools.context.
"""

# Import each submodule and trigger @register_tool Automatic registration
from core.tools.implementations.assistant_ops import analysis_trigger  # noqa: F401
from core.tools.implementations.assistant_ops import report_query  # noqa: F401
from core.tools.implementations.assistant_ops import schedule_manager  # noqa: F401
from core.tools.implementations.assistant_ops import watchlist_manager  # noqa: F401
from core.tools.implementations.assistant_ops import favorite_manager  # noqa: F401
from core.tools.implementations.assistant_ops import position_analysis  # noqa: F401
from core.tools.implementations.assistant_ops import trade_review_ops  # noqa: F401
from core.tools.implementations.assistant_ops import risk_alerts  # noqa: F401
from core.tools.implementations.assistant_ops import topic_manager  # noqa: F401
from core.tools.implementations.assistant_ops import recent_search  # noqa: F401
from core.tools.implementations.assistant_ops import agent_executor  # noqa: F401
from core.tools.implementations.assistant_ops import stock_sync_ops  # noqa: F401
# v3.0 Online search tool: must be imported explicitly, otherwise .py will be deleted after JD Cloud compiles, and ToolLoader dynamic discovery will fail.
from core.tools.implementations.assistant_ops import web_search  # noqa: F401
from core.tools.implementations.assistant_ops import fetch_url  # noqa: F401
from .gain_alerts import set_stop_gain_alert, list_stop_gain_alerts, clear_stop_gain_alert
# Use Q&A bot-specific tools (new in v3.0): only in assistant_role="usage_helper" loading when
from core.tools.implementations.assistant_ops import user_state  # noqa: F401
from core.tools.implementations.assistant_ops import system_status  # noqa: F401
from core.tools.implementations.assistant_ops import user_activity  # noqa: F401
from core.tools.implementations.assistant_ops import manual_reader  # noqa: F401
from core.tools.implementations.assistant_ops import data_sync_status  # noqa: F401
from core.tools.implementations.assistant_ops import paper_trading_status  # noqa: F401
from core.tools.implementations.assistant_ops import token_usage  # noqa: F401
from core.tools.implementations.assistant_ops import running_tasks  # noqa: F401
# Generic tabular Excel export: deterministic rendering (zero LLM calls), conversational data → xlsx Deliverables
from core.tools.implementations.assistant_ops import export_table_excel_tool  # noqa: F401
