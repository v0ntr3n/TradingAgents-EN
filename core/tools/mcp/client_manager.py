"""
MCP client manager

Run a separate asyncio event loop in a background thread,
Provides a synchronization interface for tool registry and Agent calls.
Supports three transmission methods: SSE, Streamable HTTP, and stdio.
"""

import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    MCP Client Manager (singleton)

    Maintain a background asyncio loop in which all MCP asynchronous operations are performed,
    and pass _run_sync() Exposed as a synchronous interface.
    """

    _instance: Optional["MCPClientManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MCPClientManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            name="mcp-event-loop",
            daemon=True,
        )
        self._thread.start()
        self._initialized = True
        logger.info("✅ MCPClientManager Initialization completed (background event loop started)")

    # ------------------------------------------------------------------
    # Internal: execute asynchronous coroutines synchronously
    # ------------------------------------------------------------------

    def _run_sync(self, coro, timeout: int = 30) -> Any:
        """Synchronously execute coroutines in the background event loop"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal: Establish connection and perform operations by transport type
    # ------------------------------------------------------------------

    async def _with_session(self, config: Dict, action):
        """
        Establish an MCP session according to config and execute action(session), Return results.
        action: async callable(session) -> Any
        """
        transport_type = config.get("transport_type", "sse")
        conn = config.get("connection", {})

        from mcp import ClientSession

        if transport_type in ("sse",):
            from mcp.client.sse import sse_client
            url = conn.get("url", "")
            headers = conn.get("headers", {})
            async with sse_client(url=url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await action(session)

        elif transport_type == "streamable_http":
            from mcp.client.streamable_http import streamablehttp_client
            url = conn.get("url", "")
            headers = conn.get("headers", {})
            async with streamablehttp_client(url=url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await action(session)

        elif transport_type == "stdio":
            from mcp.client.stdio import stdio_client
            from mcp import StdioServerParameters
            params = StdioServerParameters(
                command=conn.get("command", ""),
                args=conn.get("args", []),
                env=conn.get("env") or None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await action(session)

        else:
            raise ValueError(f"Unsupported MCP transport type: {transport_type}")

    # ------------------------------------------------------------------
    # Public API: Tool Discovery
    # ------------------------------------------------------------------

    def discover_tools(self, config: Dict, timeout: int = 30) -> List[Dict]:
        """
        Connects to the MCP server and returns a list of available tools.

        Returns:
            List of tool dicts with keys: name, description, inputSchema
        """
        async def _action(session):
            result = await session.list_tools()
            tools_out = []
            for t in result.tools:
                if t.inputSchema is None:
                    schema = {}
                elif isinstance(t.inputSchema, dict):
                    schema = t.inputSchema
                elif hasattr(t.inputSchema, "model_dump"):
                    schema = t.inputSchema.model_dump()
                else:
                    schema = dict(t.inputSchema) if t.inputSchema else {}
                tools_out.append({
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": schema,
                })
            return tools_out

        return self._run_sync(self._with_session(config, _action), timeout=timeout)

    # ------------------------------------------------------------------
    # Public API: tool calls
    # ------------------------------------------------------------------

    def call_tool(
        self,
        config: Dict,
        tool_name: str,
        arguments: Dict,
        timeout: int = 60,
    ) -> str:
        """
        Connect to the MCP server and call the specified tool.

        Returns:
            The tool returns the result (in string form)
        """
        async def _action(session):
            result = await session.call_tool(tool_name, arguments=arguments)
            # Concatenate the content list into a string
            parts = []
            for c in result.content:
                if hasattr(c, "text"):
                    parts.append(c.text)
                else:
                    parts.append(json.dumps(c.model_dump(), ensure_ascii=False))
            return "\n".join(parts)

        return self._run_sync(self._with_session(config, _action), timeout=timeout)

    # ------------------------------------------------------------------
    # Public API: Test connection
    # ------------------------------------------------------------------

    def test_connection(self, config: Dict, timeout: int = 15) -> Dict:
        """Test MCP server connection, return {success, tool_count, error}"""
        try:
            tools = self.discover_tools(config, timeout=timeout)
            return {"success": True, "tool_count": len(tools), "error": None}
        except Exception as e:
            return {"success": False, "tool_count": 0, "error": str(e)}


# ------------------------------------------------------------------
# Global singleton get function
# ------------------------------------------------------------------

_manager: Optional[MCPClientManager] = None


def get_mcp_client_manager() -> MCPClientManager:
    """Get the MCPClientManager global singleton"""
    global _manager
    if _manager is None:
        _manager = MCPClientManager()
    return _manager

