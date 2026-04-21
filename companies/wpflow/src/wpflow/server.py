"""wpflow MCP server — stdio transport, official mcp SDK."""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List

import mcp.server.stdio
import mcp.types as mt
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import wp_client
from .tools import all_tools


SERVER_NAME = "wpflow"
SERVER_VERSION = "0.1.0"


def _build_server() -> Server:
    server = Server(SERVER_NAME)
    tools, handlers = all_tools()

    @server.list_tools()
    async def _list_tools() -> List[mt.Tool]:
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any] | None) -> List[mt.TextContent]:
        logger = wp_client.get_logger()
        args = arguments or {}
        handler = handlers.get(name)
        if handler is None:
            payload = {"error": {"code": "not_found", "message": f"Unknown tool: {name}"}}
        else:
            try:
                # Handlers are sync (httpx.Client); run off the event loop if any blocking.
                payload = await asyncio.to_thread(handler, args)
            except Exception as e:  # safety net — no exceptions to transport
                logger.exception("Handler %s raised: %s", name, e)
                payload = {"error": {"code": "internal", "message": f"Handler raised: {type(e).__name__}"}}
        text = json.dumps(payload, default=str)
        return [mt.TextContent(type="text", text=text)]

    return server


def get_server_and_tools():
    """Expose for test introspection."""
    server = _build_server()
    tools, handlers = all_tools()
    return server, tools, handlers


async def _run_stdio() -> None:
    logger = wp_client.get_logger()
    logger.info("wpflow %s starting (stdio)", SERVER_VERSION)
    server = _build_server()
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> int:
    try:
        asyncio.run(_run_stdio())
    except KeyboardInterrupt:
        return 0
    finally:
        wp_client.close_client()
    return 0


if __name__ == "__main__":
    sys.exit(main())
