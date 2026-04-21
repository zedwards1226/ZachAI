"""Page tools: list_pages, get_page, update_page."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

import wp_client
from errors import WPClientError, err
from tools._common import coerce_page, page_meta, post_full, post_summary


def _page_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    s = post_summary(raw)
    s["parent_id"] = raw.get("parent")
    return s


def _list_pages(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page, per_page = coerce_page(args)
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "status": args.get("status", "publish"),
            "orderby": args.get("orderby", "date"),
            "order": args.get("order", "desc"),
            "context": "view" if args.get("status", "publish") == "publish" else "edit",
            "_fields": "id,title,status,date,modified,slug,excerpt,content,link,author,parent",
        }
        if args.get("search"):
            params["search"] = args["search"]
        if args.get("author_id"):
            params["author"] = args["author_id"]
        if args.get("parent_id") is not None:
            params["parent"] = args["parent_id"]
        if args.get("after"):
            params["after"] = args["after"]
        if args.get("before"):
            params["before"] = args["before"]
        data, resp = wp_client.request_with_headers("GET", "/wp-json/wp/v2/pages", params=params)
        pages = [_page_summary(p) for p in data] if isinstance(data, list) else []
        return {"pages": pages, "pagination": page_meta(resp.headers, page, per_page)}
    except WPClientError as e:
        return e.to_dict()


def _get_page(args: Dict[str, Any]) -> Dict[str, Any]:
    page_id = args.get("page_id")
    if not page_id:
        return err("invalid_params", "page_id is required.")
    include_raw = bool(args.get("include_raw", False))
    try:
        data = wp_client.request(
            "GET",
            f"/wp-json/wp/v2/pages/{page_id}",
            params={"context": "edit"},
        )
        if not isinstance(data, dict):
            return err("internal", "Unexpected get_page response.")
        out = post_full(data, include_raw=include_raw)
        out["parent_id"] = data.get("parent")
        return {"page": out}
    except WPClientError as e:
        return e.to_dict()


def _update_page(args: Dict[str, Any]) -> Dict[str, Any]:
    page_id = args.get("page_id")
    if not page_id:
        return err("invalid_params", "page_id is required.")
    body: Dict[str, Any] = {}
    updated = []
    mapping = {
        "title": "title",
        "content_html": "content",
        "status": "status",
        "excerpt": "excerpt",
        "slug": "slug",
        "date": "date",
        "parent_id": "parent",
        "featured_media_id": "featured_media",
    }
    for in_key, out_key in mapping.items():
        if in_key in args and args[in_key] is not None:
            body[out_key] = args[in_key]
            updated.append(in_key)
    if not body:
        return err("invalid_params", "No updatable fields provided.")
    try:
        data = wp_client.request("POST", f"/wp-json/wp/v2/pages/{page_id}", json_body=body)
        if not isinstance(data, dict):
            return err("internal", "Unexpected update_page response.")
        out = post_full(data)
        out["parent_id"] = data.get("parent")
        return {"page": out, "updated_fields": updated}
    except WPClientError as e:
        return e.to_dict()


TOOLS = [
    mt.Tool(
        name="list_pages",
        description="WHEN: Use to find static pages (About, Contact, etc.). Separate from posts - WordPress treats pages and posts as distinct content types.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["publish", "draft", "pending", "private", "future", "any"], "default": "publish"},
                "search": {"type": "string"},
                "author_id": {"type": "integer"},
                "parent_id": {"type": "integer"},
                "after": {"type": "string", "format": "date-time"},
                "before": {"type": "string", "format": "date-time"},
                "orderby": {"type": "string", "enum": ["date", "modified", "title", "id"], "default": "date"},
                "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="get_page",
        description="WHEN: Use when you need the full content of a single page (body HTML, parent). Do NOT use for browsing - use list_pages first.",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "integer", "minimum": 1},
                "include_raw": {"type": "boolean", "default": False},
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="update_page",
        description="WHEN: Use to edit an existing page - title, body, status, parent, slug. Partial updates supported.",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "integer", "minimum": 1},
                "title": {"type": "string", "maxLength": 500},
                "content_html": {"type": "string"},
                "status": {"type": "string", "enum": ["publish", "draft", "pending", "private", "future"]},
                "excerpt": {"type": "string", "maxLength": 1000},
                "slug": {"type": "string"},
                "parent_id": {"type": "integer"},
                "featured_media_id": {"type": "integer"},
                "date": {"type": "string", "format": "date-time"},
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_pages": _list_pages,
    "get_page": _get_page,
    "update_page": _update_page,
}
