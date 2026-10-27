"""
MCP (Model Context Protocol) Integrated module

Provides client management and tool packaging, and supports user-defined MCP server access.
Transmission type:
  - sse              — Server-Sent Events (HTTP)
  - streamable_http  — Streamable HTTP (New version of MCP standard)
  - stdio            — child process standard input and output
"""

from .client_manager import MCPClientManager, get_mcp_client_manager

__all__ = ["MCPClientManager", "get_mcp_client_manager"]

