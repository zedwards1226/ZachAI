"""Comment tools: list_comments, moderate_comment."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

import wp_client
from errors import WPClientError, err
from tools._common import coerce_page, excerpt_200, page_meta


_ACTION_STATUS = {
    "approve": "approved",
    "hold": "hold",
    "spam": "spam",
    "trash": "trash",
}


def _comment_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    content = (raw.get("content") or {}).get("rendered", "")
    return {
        "id": raw.get("id"),
        "post_id": raw.get("post"),
        "author_name": raw.get("author_name"),
        "author_email": raw.get("author_email"),
        "status": raw.get("status"),
        "date": raw.get("date"),
        "content_excerpt_200": excerpt_200(content),
        "parent_id": raw.get("parent"),
        "link": raw.get("link"),
    }


def _list_comments(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page, per_page = coerce_page(args)
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "context": "edit",
            "_fields": "id,post,author_name,author_email,status,date,content,parent,link",
        }
        status = args.get("status", "any")
        if status != "any":
            params["status"] = status
        if args.get("post_id"):
            params["post"] = args["post_id"]
        if args.get("author_email"):
            params["author_email"] = args["author_email"]
        if args.get("search"):
            params["search"] = args["search"]
        data, resp = wp_client.request_with_headers("GET", "/wp-json/wp/v2/comments", params=params)
        comments = [_comment_summary(c) for c in data] if isinstance(data, list) else []
        return {"comments": comments, "pagination": page_meta(resp.headers, page, per_page)}
    except WPClientError as e:
        return e.to_dict()


def _moderate_comment(args: Dict[str, Any]) -> Dict[str, Any]:
    comment_id = args.get("comment_id")
    action = args.get("action")
    if not comment_id or not action:
        return err("invalid_params", "comment_id and action are required.")
    if action not in ("approve", "hold", "spam", "trash", "delete_permanently"):
        return err("invalid_action", f"Unknown action: {action}")
    try:
        # Previous status
        prev = None
        try:
            cur = wp_client.request(
                "GET",
                f"/wp-json/wp/v2/comments/{comment_id}",
                params={"context": "edit"},
            )
            if isinstance(cur, dict):
                prev = cur.get("status")
        except WPClientError:
            pass

        if action == "delete_permanently":
            data = wp_client.request(
                "DELETE",
                f"/wp-json/wp/v2/comments/{comment_id}",
                params={"force": "true"},
            )
            return {
                "comment_id": comment_id,
                "previous_status": prev,
                "action": action,
                "new_status": "deleted",
            }
        target = _ACTION_STATUS[action]
        data = wp_client.request(
            "POST",
            f"/wp-json/wp/v2/comments/{comment_id}",
            json_body={"status": target},
        )
        new_status = data.get("status") if isinstance(data, dict) else target
        return {
            "comment_id": comment_id,
            "previous_status": prev,
            "action": action,
            "new_status": new_status,
        }
    except WPClientError as e:
        return e.to_dict()


TOOLS = [
    mt.Tool(
        name="list_comments",
        description="WHEN: Use to see comments, filter by status (approved / pending / spam / trash), or find comments on a specific post.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["approve", "hold", "spam", "trash", "any"], "default": "any"},
                "post_id": {"type": "integer"},
                "author_email": {"type": "string"},
                "search": {"type": "string"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="moderate_comment",
        description="WHEN: Use to approve, spam, trash, or permanently delete a comment. This is the only comment-write tool in v0.1.",
        inputSchema={
            "type": "object",
            "properties": {
                "comment_id": {"type": "integer", "minimum": 1},
                "action": {"type": "string", "enum": ["approve", "hold", "spam", "trash", "delete_permanently"]},
            },
            "required": ["comment_id", "action"],
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_comments": _list_comments,
    "moderate_comment": _moderate_comment,
}
