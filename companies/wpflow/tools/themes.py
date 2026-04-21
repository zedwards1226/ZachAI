"""Theme tools: list_themes, get_active_theme."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

import wp_client
from errors import WPClientError, err


def _theme_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    name = raw.get("name")
    if isinstance(name, dict):
        name = name.get("rendered") or name.get("raw") or ""
    author = raw.get("author")
    if isinstance(author, dict):
        author = author.get("rendered") or author.get("raw") or ""
    screenshot = raw.get("screenshot")
    if isinstance(screenshot, dict):
        screenshot = screenshot.get("rendered") or ""
    return {
        "stylesheet": raw.get("stylesheet"),
        "name": name,
        "version": raw.get("version"),
        "status": raw.get("status"),
        "author": author,
        "template": raw.get("template"),
        "screenshot_url": screenshot,
    }


def _list_themes(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = wp_client.request("GET", "/wp-json/wp/v2/themes")
        if isinstance(data, list):
            return {"themes": [_theme_summary(t) for t in data]}
        return err("internal", "Unexpected list_themes response.")
    except WPClientError as e:
        return e.to_dict()


def _get_active_theme(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = wp_client.request("GET", "/wp-json/wp/v2/themes", params={"status": "active"})
        if isinstance(data, list) and data:
            theme = data[0]
            out = _theme_summary(theme)
            out["theme_supports"] = theme.get("theme_supports")
            return {"theme": out}
        return err("not_found", "No active theme found.")
    except WPClientError as e:
        return e.to_dict()


TOOLS = [
    mt.Tool(
        name="list_themes",
        description="WHEN: Use to see installed themes. v0.1 does not support activating or installing themes - read-only.",
        inputSchema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="get_active_theme",
        description="WHEN: Use to identify which theme is currently running - useful before advising customizations.",
        inputSchema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_themes": _list_themes,
    "get_active_theme": _get_active_theme,
}
