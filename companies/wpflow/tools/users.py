"""User tools: list_users, get_user."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

import wp_client
from errors import WPClientError, err
from tools._common import coerce_page, page_meta


def _user_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw.get("id"),
        "username": raw.get("username") or raw.get("slug"),
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "roles": raw.get("roles"),
        "post_count": (raw.get("post_count") or {}),
    }


def _user_full(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw.get("id"),
        "username": raw.get("username") or raw.get("slug"),
        "email": raw.get("email"),
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "roles": raw.get("roles"),
        "registered_date": raw.get("registered_date"),
        "post_count": raw.get("post_count") or {},
        "url": raw.get("url"),
        "description": raw.get("description"),
    }


def _list_users(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page, per_page = coerce_page(args)
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "context": "edit",
            "_fields": "id,username,name,slug,roles",
        }
        if args.get("role"):
            params["roles"] = args["role"]
        if args.get("search"):
            params["search"] = args["search"]
        data, resp = wp_client.request_with_headers("GET", "/wp-json/wp/v2/users", params=params)
        users = [_user_summary(u) for u in data] if isinstance(data, list) else []
        return {"users": users, "pagination": page_meta(resp.headers, page, per_page)}
    except WPClientError as e:
        return e.to_dict()


def _get_user(args: Dict[str, Any]) -> Dict[str, Any]:
    user_id = args.get("user_id")
    if not user_id:
        return err("invalid_params", "user_id is required.")
    try:
        data = wp_client.request("GET", f"/wp-json/wp/v2/users/{user_id}", params={"context": "edit"})
        if not isinstance(data, dict):
            return err("internal", "Unexpected get_user response.")
        return {"user": _user_full(data)}
    except WPClientError as e:
        return e.to_dict()


TOOLS = [
    mt.Tool(
        name="list_users",
        description="WHEN: Use to find users/authors on the site. Sensitive fields (email) only visible via get_user when authenticated user has list_users capability.",
        inputSchema={
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "search": {"type": "string"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="get_user",
        description="WHEN: Use for full user details including email (requires list_users capability).",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "minimum": 1},
            },
            "required": ["user_id"],
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_users": _list_users,
    "get_user": _get_user,
}
