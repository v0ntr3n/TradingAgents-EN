"""
Tool Execution Logger

Record the input parameters, output parameters, time-consuming and other information of the Agent tool call to facilitate subsequent review and debugging.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ToolExecutionLogger:
    """Tool execution logger (singleton)

    Supports both synchronous/asynchronous databases (pymongo/motor).
    Submit via create_task in an asynchronous context and fall back using get_mongo_db_sync in a synchronous context.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._db = None
            cls._instance._collection_name = "tool_execution_logs"
        return cls._instance

    def set_db(self, db):
        """Set up a database connection (can be AsyncIOMotorDatabase or pymongo Database)"""
        self._db = db

    def log(
        self,
        tool_id: str,
        agent_id: str,
        tool_args: Dict[str, Any],
        result: Any,
        success: bool,
        execution_time_ms: int,
        analysis_id: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Record a tool execution (automatically adapt to synchronous/asynchronous database)"""
        try:
            # Result serialization (truncate overly long results)
            result_str = str(result) if result is not None else None
            if result_str and len(result_str) > 5000:
                result_str = result_str[:5000] + "...[truncated]"

            doc = {
                "tool_id": tool_id,
                "agent_id": agent_id,
                "tool_args": tool_args,
                "result": result_str,
                "success": success,
                "execution_time_ms": execution_time_ms,
                "analysis_id": analysis_id,
                "error": error,
                "created_at": datetime.utcnow().isoformat(),
            }

            # Preferred: Use injected in an async context motor db
            if self._db is not None and self._is_async_db(self._db):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._async_insert(doc))
                    return
                except RuntimeError:
                    # Not in the event loop, fallback to synchronous writing
                    pass

            # Synchronous writing (pymongo or fallback path)
            self._sync_insert(doc)
        except Exception as e:
            logger.warning(f"记录工具执行日志失败: {e}")

    @staticmethod
    def _is_async_db(db) -> bool:
        cls_name = type(db).__name__
        return "AsyncIOMotor" in cls_name or cls_name.endswith("Proxy")

    async def _async_insert(self, doc: Dict[str, Any]) -> None:
        try:
            await self._db[self._collection_name].insert_one(doc)
        except Exception as e:
            logger.warning(f"Asynchronous writing tool execution log failed: {e}")

    def _sync_insert(self, doc: Dict[str, Any]) -> None:
        try:
            from app.core.database import get_mongo_db_sync
            sync_db = get_mongo_db_sync()
            if sync_db is not None:
                sync_db[self._collection_name].insert_one(doc)
        except Exception as e:
            logger.warning(f"Synchronous writing tool execution log failed: {e}")


# global instance
_global_logger: Optional[ToolExecutionLogger] = None


def get_tool_execution_logger() -> ToolExecutionLogger:
    """Get the global tool execution logger"""
    global _global_logger
    if _global_logger is None:
        _global_logger = ToolExecutionLogger()
    return _global_logger
