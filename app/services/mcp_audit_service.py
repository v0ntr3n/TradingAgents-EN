"""
MCP Audit log service

All MCP tool calls (data source classes and function classes) are logged to the mcp_audit_logs collection.
Use synchronization interface, suitable for calling in executor closure (synchronization context).
"""

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLLECTION = "mcp_audit_logs"


def _write_audit_log(doc: Dict) -> None:
    """Synchronously write audit logs to MongoDB"""
    try:
        from app.core.database import get_mongo_db_sync
        db = get_mongo_db_sync()
        if db is not None:
            db[COLLECTION].insert_one(doc)
    except Exception as e:
        logger.warning(f"⚠️ MCP Audit log writing failed: {e}")


def log_mcp_call_sync(
    server_name: str,
    tool_name: str,
    category: str,
    request_params: Dict,
    response_summary: str,
    persisted_to: Optional[str] = None,
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Asynchronous (fire-and-forget) writing to the MCP call audit log.

    Write in a background thread without blocking the MCP tool call link.

    Args:
        server_name:      MCP Server name
        tool_name:        Tool name
        category:         Data source type datasource | function
        request_params:   Call parameters
        response_summary: Response summary (e.g. "OK, 10 records") 
        persisted_to:     The name of the target collection written by the data source class (can be None)
        task_id:          Correlation analysis task ID (optional)
        user_id:          Trigger user ID (optional)
    """
    from app.utils.timezone import now_tz

    doc = {
        "task_id": task_id,
        "user_id": user_id,
        "server_name": server_name,
        "tool_name": tool_name,
        "category": category,
        "request_params": request_params,
        "response_summary": response_summary,
        "persisted_to": persisted_to,
        "created_at": now_tz(),
    }

    # fire-and-forget: Background thread writes without blocking executor
    t = threading.Thread(target=_write_audit_log, args=(doc,), daemon=True)
    t.start()

