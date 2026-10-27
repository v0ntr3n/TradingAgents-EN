"""
MCP Server Independent process startup entrance

Usage:
    python -m core.mcp                  # Default SSE transport, port 8001
    python -m core.mcp --transport http  # HTTP transmission
    python -m core.mcp --port 9001       # Custom port

Claude Desktop Configuration example (claude_desktop_config.json):
{
  "mcpServers": {
    "tradingagents-cn": {
      "url": "http://localhost:8001/sse"
    }
  }
}
"""

import argparse
import logging
import sys
from pathlib import Path

# Make sure the project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configuration log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-24s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("core.mcp")


def main():
    parser = argparse.ArgumentParser(description="TradingAgents-CN MCP Server")
    parser.add_argument(
        "--transport",
        choices=["sse", "http", "stdio"],
        default="sse",
        help="transport protocol (Default: sse)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="listening port (Default: 8001)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="listening address (Default: 0.0.0.0)",
    )
    args = parser.parse_args()

    # Load .env environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    logger.info("=" * 60)
    logger.info("🚀 TradingAgents-CN MCP Server Starting...")
    logger.info(f"   transport protocol: {args.transport}")
    if args.transport != "stdio":
        logger.info(f"   listening address: {args.host}:{args.port}")
    logger.info("=" * 60)

    from core.mcp.server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

