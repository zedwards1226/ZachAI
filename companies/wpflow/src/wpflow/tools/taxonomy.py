"""Taxonomy tools: list_categories, list_tags, create_term."""
from __future__ import annotations

from typing import Any, Dict

import mcp.types as mt

from .. import wp_client
from ..errors import WPClientError, err
from ._common import coerce_page, page_meta


def _term_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "count": raw.get("count"),
        "parent_id": raw.get("parent"),
    }


def _list_terms(taxonomy: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page = int(args.get("page", 1) or 1)
        per_page = int(args.get("per_page", 50) or 50)
        if per_page < 1:
            per_page = 50
        if per_page > 100:
            per_page = 100
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "_fields": "id,name,slug,count,parent",
        }
        if args.get("search"):
            params["search"] = args["search"]
        if taxonomy == "categories" and args.get("parent_id") is not None:
            params["parent"] = args["parent_id"]
        endpoint = f"/wp-json/wp/v2/{taxonomy}"
        data, resp = wp_client.request_with_headers("GET", endpoint, params=params)
        terms = [_term_summary(t) for t in data] if isinstance(data, list) else []
        return {"terms": terms, "pagination": page_meta(resp.headers, page, per_page)}
    except WPClientError as e:
        return e.to_dict()


def _list_categories(args: Dict[str, Any]) -> Dict[str, Any]:
    return _list_terms("categories", args)


def _list_tags(args: Dict[str, Any]) -> Dict[str, Any]:
    return _list_terms("tags", args)


def _create_term(args: Dict[str, Any]) -> Dict[str, Any]:
    taxonomy = args.get("taxonomy")
    name = args.get("name")
    if taxonomy not in ("category", "tag"):
        return err("invalid_params", "taxonomy must be 'category' or 'tag'.")
    if not name:
        return err("invalid_params", "name is required.")
    endpoint_taxonomy = "categories" if taxonomy == "category" else "tags"
    body: Dict[str, Any] = {"name": name}
    if args.get("slug"):
        body["slug"] = args["slug"]
    if args.get("description"):
        body["description"] = args["description"]
    if taxonomy == "category" and args.get("parent_id") is not None:
        body["parent"] = args["parent_id"]
    try:
        data = wp_client.request("POST", f"/wp-json/wp/v2/{endpoint_taxonomy}", json_body=body)
        if not isinstance(data, dict):
            return err("internal", "Unexpected create_term response.")
        term = _term_summary(data)
        term["taxonomy"] = taxonomy
        return {"term": term, "created": True}
    except WPClientError as e:
        if e.code == "conflict" and isinstance(e.wp_body, dict):
            existing = (e.wp_body.get("data") or {}).get("term_id") or (e.wp_body.get("data") or {}).get("existing_term_id")
            d = e.to_dict()
            if existing:
                d["error"]["existing_id"] = existing
            return d
        return e.to_dict()


TOOLS = [
    mt.Tool(
        name="list_categories",
        description="WHEN: Use to see category taxonomy structure for a post - categories are hierarchical. Use when helping the user organize content.",
        inputSchema={
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "parent_id": {"type": "integer"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="list_tags",
        description="WHEN: Use to see all tags - tags are flat. Pair with create_term when the user wants to add a new one.",
        inputSchema={
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="create_term",
        description="WHEN: Use when the user wants to add a new category or tag before assigning it to a post.",
        inputSchema={
            "type": "object",
            "properties": {
                "taxonomy": {"type": "string", "enum": ["category", "tag"]},
                "name": {"type": "string", "minLength": 1, "maxLength": 200},
                "slug": {"type": "string"},
                "description": {"type": "string"},
                "parent_id": {"type": "integer"},
            },
            "required": ["taxonomy", "name"],
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_categories": _list_categories,
    "list_tags": _list_tags,
    "create_term": _create_term,
}
