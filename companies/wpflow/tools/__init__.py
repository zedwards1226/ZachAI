"""wpflow tools package.

Each submodule exports:
  TOOLS: list[mcp.types.Tool]
  HANDLERS: dict[str, callable(args: dict) -> dict]

server.py aggregates them all.
"""
from . import posts, pages, media, plugins, themes, users, comments, taxonomy, health


def all_tools():
    tools = []
    handlers = {}
    for m in (posts, pages, media, plugins, themes, users, comments, taxonomy, health):
        tools.extend(m.TOOLS)
        handlers.update(m.HANDLERS)
    return tools, handlers
