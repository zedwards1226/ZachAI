"""Plugin tools: list_plugins, activate_plugin, deactivate_plugin."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

from .. import wp_client
from ..errors import WPClientError, err


def _plugin_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plugin": raw.get("plugin"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "version": raw.get("version"),
        "author": raw.get("author"),
        "network_only": raw.get("network_only"),
        "requires_wp": raw.get("requires_wp"),
        "requires_php": raw.get("requires_php"),
    }


def _list_plugins(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params: Dict[str, Any] = {}
        status = args.get("status", "any")
        if status != "any":
            params["status"] = status
        if args.get("search"):
            params["search"] = args["search"]
        data = wp_client.request("GET", "/wp-json/wp/v2/plugins", params=params or None)
        if isinstance(data, list):
            return {"plugins": [_plugin_summary(p) for p in data]}
        return err("internal", "Unexpected list_plugins response.")
    except WPClientError as e:
        d = e.to_dict()
        if e.code == "rest_api_disabled" or e.code == "not_found":
            d = err("rest_disabled_for_plugins", "Host appears to block /plugins endpoint.")
        return d


def _set_status(plugin: str, status: str) -> Dict[str, Any]:
    try:
        data = wp_client.request(
            "POST",
            f"/wp-json/wp/v2/plugins/{plugin}",
            json_body={"status": status},
        )
        if not isinstance(data, dict):
            return err("internal", "Unexpected plugin update response.")
        return data
    except WPClientError as e:
        return e.to_dict()


def _activate_plugin(args: Dict[str, Any]) -> Dict[str, Any]:
    plugin = args.get("plugin")
    if not plugin:
        return err("invalid_params", "plugin is required.")
    # Get previous status first
    prev: str = "unknown"
    try:
        cur = wp_client.request("GET", f"/wp-json/wp/v2/plugins/{plugin}")
        if isinstance(cur, dict):
            prev = cur.get("status", "unknown")
    except WPClientError as e:
        return e.to_dict()
    resp = _set_status(plugin, "active")
    if "error" in resp:
        return resp
    return {"plugin": plugin, "previous_status": prev, "new_status": resp.get("status")}


def _deactivate_plugin(args: Dict[str, Any]) -> Dict[str, Any]:
    plugin = args.get("plugin")
    if not plugin:
        return err("invalid_params", "plugin is required.")
    prev = "unknown"
    try:
        cur = wp_client.request("GET", f"/wp-json/wp/v2/plugins/{plugin}")
        if isinstance(cur, dict):
            prev = cur.get("status", "unknown")
    except WPClientError as e:
        return e.to_dict()
    resp = _set_status(plugin, "inactive")
    if "error" in resp:
        return resp
    return {"plugin": plugin, "previous_status": prev, "new_status": resp.get("status")}


TOOLS = [
    mt.Tool(
        name="list_plugins",
        description="WHEN: Use to see what plugins are installed and which are active. Do NOT use to install new plugins - that is not supported in v0.1.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive", "any"], "default": "any"},
                "search": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="activate_plugin",
        description="WHEN: Use when the user asks to turn on an already-installed plugin.",
        inputSchema={
            "type": "object",
            "properties": {
                "plugin": {"type": "string", "description": "Plugin slug, e.g. 'akismet/akismet'"},
            },
            "required": ["plugin"],
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="deactivate_plugin",
        description="WHEN: Use when the user asks to turn off a plugin (e.g., to troubleshoot a conflict).",
        inputSchema={
            "type": "object",
            "properties": {
                "plugin": {"type": "string"},
            },
            "required": ["plugin"],
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_plugins": _list_plugins,
    "activate_plugin": _activate_plugin,
    "deactivate_plugin": _deactivate_plugin,
}
