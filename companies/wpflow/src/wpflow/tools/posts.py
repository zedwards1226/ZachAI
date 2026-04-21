"""Post tools: list_posts, get_post, create_post, update_post, delete_post, search_content."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

from .. import wp_client
from ..errors import WPClientError, err
from ._common import coerce_page, excerpt_200, page_meta, post_full, post_summary, strip_html


def _list_posts(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page, per_page = coerce_page(args)
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "status": args.get("status", "publish"),
            "orderby": args.get("orderby", "date"),
            "order": args.get("order", "desc"),
            "context": "view" if args.get("status", "publish") == "publish" else "edit",
            "_fields": "id,title,status,date,modified,slug,excerpt,content,link,author,categories,tags",
        }
        if args.get("search"):
            params["search"] = args["search"]
        if args.get("author_id"):
            params["author"] = args["author_id"]
        if args.get("category_ids"):
            params["categories"] = ",".join(str(x) for x in args["category_ids"])
        if args.get("tag_ids"):
            params["tags"] = ",".join(str(x) for x in args["tag_ids"])
        if args.get("after"):
            params["after"] = args["after"]
        if args.get("before"):
            params["before"] = args["before"]

        data, resp = wp_client.request_with_headers("GET", "/wp-json/wp/v2/posts", params=params)
        if not isinstance(data, list):
            return err("internal", "Unexpected WP posts response shape.")
        posts = [post_summary(p) for p in data]
        return {"posts": posts, "pagination": page_meta(resp.headers, page, per_page)}
    except WPClientError as e:
        return e.to_dict()


def _get_post(args: Dict[str, Any]) -> Dict[str, Any]:
    post_id = args.get("post_id")
    if not post_id:
        return err("invalid_params", "post_id is required.")
    include_raw = bool(args.get("include_raw", False))
    try:
        data = wp_client.request(
            "GET",
            f"/wp-json/wp/v2/posts/{post_id}",
            params={"context": "edit"},
        )
        if not isinstance(data, dict):
            return err("internal", "Unexpected get_post response.")
        return {"post": post_full(data, include_raw=include_raw)}
    except WPClientError as e:
        return e.to_dict()


def _create_post(args: Dict[str, Any]) -> Dict[str, Any]:
    if not args.get("title") or not args.get("content_html"):
        return err("invalid_params", "title and content_html are required.")
    body: Dict[str, Any] = {
        "title": args["title"],
        "content": args["content_html"],
        "status": args.get("status", "draft"),
    }
    for in_field, out_field in (
        ("excerpt", "excerpt"),
        ("slug", "slug"),
        ("date", "date"),
    ):
        if args.get(in_field):
            body[out_field] = args[in_field]
    if args.get("category_ids"):
        body["categories"] = args["category_ids"]
    if args.get("tag_ids"):
        body["tags"] = args["tag_ids"]
    if args.get("featured_media_id"):
        body["featured_media"] = args["featured_media_id"]
    if body["status"] == "future" and not body.get("date"):
        return err("invalid_params", "date is required when status=future.")
    try:
        data = wp_client.request("POST", "/wp-json/wp/v2/posts", json_body=body)
        if not isinstance(data, dict):
            return err("internal", "Unexpected create_post response.")
        return {"post": post_full(data), "created": True}
    except WPClientError as e:
        return e.to_dict()


def _update_post(args: Dict[str, Any]) -> Dict[str, Any]:
    post_id = args.get("post_id")
    if not post_id:
        return err("invalid_params", "post_id is required.")
    body: Dict[str, Any] = {}
    updated: list = []
    mapping = {
        "title": "title",
        "content_html": "content",
        "status": "status",
        "excerpt": "excerpt",
        "slug": "slug",
        "date": "date",
        "category_ids": "categories",
        "tag_ids": "tags",
        "featured_media_id": "featured_media",
    }
    for in_key, out_key in mapping.items():
        if in_key in args and args[in_key] is not None:
            body[out_key] = args[in_key]
            updated.append(in_key)
    if not body:
        return err("invalid_params", "No updatable fields provided.")
    try:
        data = wp_client.request("POST", f"/wp-json/wp/v2/posts/{post_id}", json_body=body)
        if not isinstance(data, dict):
            return err("internal", "Unexpected update_post response.")
        return {"post": post_full(data), "updated_fields": updated}
    except WPClientError as e:
        return e.to_dict()


def _delete_post(args: Dict[str, Any]) -> Dict[str, Any]:
    post_id = args.get("post_id")
    if not post_id:
        return err("invalid_params", "post_id is required.")
    force = bool(args.get("force", False))
    try:
        data = wp_client.request(
            "DELETE",
            f"/wp-json/wp/v2/posts/{post_id}",
            params={"force": "true" if force else "false"},
        )
        previous_status = None
        if isinstance(data, dict):
            previous = data.get("previous") or data
            if isinstance(previous, dict):
                previous_status = previous.get("status")
        return {
            "deleted": True,
            "post_id": post_id,
            "force": force,
            "previous_status": previous_status,
        }
    except WPClientError as e:
        return e.to_dict()


def _search_content(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query")
    if not query:
        return err("invalid_params", "query is required.")
    types = args.get("types") or ["post", "page"]
    per_type = int(args.get("per_type", 5) or 5)
    if per_type < 1:
        per_type = 1
    if per_type > 20:
        per_type = 20
    try:
        params = {
            "search": query,
            "subtype": ",".join(types),
            "per_page": per_type * len(types),
            "_fields": "id,title,url,type,subtype,excerpt",
        }
        data = wp_client.request("GET", "/wp-json/wp/v2/search", params=params)
        results = []
        if isinstance(data, list):
            for r in data:
                results.append({
                    "type": r.get("subtype") or r.get("type"),
                    "id": r.get("id"),
                    "title": strip_html((r.get("title") or "")),
                    "link": r.get("url"),
                    "excerpt_200": excerpt_200(r.get("excerpt") or ""),
                })
        return {"results": results, "query": query}
    except WPClientError as e:
        return e.to_dict()


# ---- Tool declarations ----

TOOLS = [
    mt.Tool(
        name="list_posts",
        description="WHEN: Use to find posts by status, date, author, category, tag, or search term. Returns summaries only (no full body) for token efficiency. Follow up with get_post for full content.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["publish", "draft", "pending", "private", "future", "any"], "default": "publish"},
                "search": {"type": "string"},
                "author_id": {"type": "integer"},
                "category_ids": {"type": "array", "items": {"type": "integer"}},
                "tag_ids": {"type": "array", "items": {"type": "integer"}},
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
        name="get_post",
        description="WHEN: Use when you need the full content of a single post (body HTML, meta, featured image). Do NOT use for browsing - use list_posts first.",
        inputSchema={
            "type": "object",
            "properties": {
                "post_id": {"type": "integer", "minimum": 1},
                "include_raw": {"type": "boolean", "default": False, "description": "If true, also returns raw block-editor source."},
            },
            "required": ["post_id"],
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="create_post",
        description="WHEN: Use when the user asks to publish a new blog post or create a draft. For editing existing posts, use update_post.",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 500},
                "content_html": {"type": "string"},
                "status": {"type": "string", "enum": ["publish", "draft", "pending", "private", "future"], "default": "draft"},
                "excerpt": {"type": "string", "maxLength": 1000},
                "slug": {"type": "string"},
                "category_ids": {"type": "array", "items": {"type": "integer"}},
                "tag_ids": {"type": "array", "items": {"type": "integer"}},
                "featured_media_id": {"type": "integer"},
                "date": {"type": "string", "format": "date-time"},
            },
            "required": ["title", "content_html"],
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="update_post",
        description="WHEN: Use to edit an existing post - title, body, status, categories/tags, slug, or featured image. Partial updates supported; only provided fields change.",
        inputSchema={
            "type": "object",
            "properties": {
                "post_id": {"type": "integer", "minimum": 1},
                "title": {"type": "string", "maxLength": 500},
                "content_html": {"type": "string"},
                "status": {"type": "string", "enum": ["publish", "draft", "pending", "private", "future"]},
                "excerpt": {"type": "string", "maxLength": 1000},
                "slug": {"type": "string"},
                "category_ids": {"type": "array", "items": {"type": "integer"}},
                "tag_ids": {"type": "array", "items": {"type": "integer"}},
                "featured_media_id": {"type": "integer"},
                "date": {"type": "string", "format": "date-time"},
            },
            "required": ["post_id"],
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="delete_post",
        description="WHEN: Use only when the user explicitly asks to delete or trash a post. Defaults to trash (recoverable); pass force=true only if user says 'permanently' or 'purge'.",
        inputSchema={
            "type": "object",
            "properties": {
                "post_id": {"type": "integer", "minimum": 1},
                "force": {"type": "boolean", "default": False},
            },
            "required": ["post_id"],
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="search_content",
        description="WHEN: Use for a cross-content-type search: one call hits posts, pages, and media at once and returns a unified summary list.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "types": {"type": "array", "items": {"type": "string", "enum": ["post", "page", "attachment"]}, "default": ["post", "page"]},
                "per_type": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
]


HANDLERS = {
    "list_posts": _list_posts,
    "get_post": _get_post,
    "create_post": _create_post,
    "update_post": _update_post,
    "delete_post": _delete_post,
    "search_content": _search_content,
}
