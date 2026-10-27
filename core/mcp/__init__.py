"""
MCP Server module

Expose TradingAgents-CN s multi-agent analysis capabilities as MCP tools,
Called by MCP Clients such as Claude Desktop, Cursor, OpenClaw, etc.

What is exposed is"Analytical capabilities (finished product)", rather than raw data tools (parts).

Catalog description:
- server.py   — FastMCP Example + MCP Tool definition
- auth.py     — API Key Authentication and user mapping
- __main__.py — Independent process startup entrance
"""

from core.mcp.auth import MCPApiKeyVerifier, mcp_auth
from core.mcp.server import mcp

__all__ = ["mcp", "mcp_auth", "MCPApiKeyVerifier"]

