"""Shared helpers for tool modules."""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Tuple


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str) -> str:
    if not s:
        return ""
    txt = _TAG_RE.sub("", s)
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def excerpt_200(raw_excerpt: str, fallback_content: str = "") -> str:
    src = raw_excerpt or fallback_content or ""
    text = strip_html(src)
    if len(text) <= 200:
        return text
    return text[:197].rstrip() + "..."


def page_meta(resp_headers: Dict[str, str], page: int, per_page: int) -> Dict[str, Any]:
    total = int(resp_headers.get("X-WP-Total", 0) or 0)
    total_pages = int(resp_headers.get("X-WP-TotalPages", 0) or 0)
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_more": page < total_pages,
    }


def post_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    title = (raw.get("title") or {}).get("rendered", "")
    excerpt_raw = (raw.get("excerpt") or {}).get("rendered", "")
    content_raw = (raw.get("content") or {}).get("rendered", "")
    return {
        "id": raw.get("id"),
        "title": strip_html(title),
        "status": raw.get("status"),
        "date": raw.get("date"),
        "modified": raw.get("modified"),
        "slug": raw.get("slug"),
        "excerpt_200": excerpt_200(excerpt_raw, content_raw),
        "link": raw.get("link"),
        "author_id": raw.get("author"),
        "categories": raw.get("categories"),
        "tags": raw.get("tags"),
    }


def post_full(raw: Dict[str, Any], include_raw: bool = False) -> Dict[str, Any]:
    title_obj = raw.get("title") or {}
    content_obj = raw.get("content") or {}
    excerpt_obj = raw.get("excerpt") or {}
    out = {
        "id": raw.get("id"),
        "title": strip_html(title_obj.get("rendered", "")),
        "status": raw.get("status"),
        "date": raw.get("date"),
        "modified": raw.get("modified"),
        "slug": raw.get("slug"),
        "link": raw.get("link"),
        "author_id": raw.get("author"),
        "excerpt_200": excerpt_200(excerpt_obj.get("rendered", ""), content_obj.get("rendered", "")),
        "content_html": content_obj.get("rendered", ""),
        "featured_media": raw.get("featured_media"),
        "categories": raw.get("categories"),
        "tags": raw.get("tags"),
        "meta": raw.get("meta"),
    }
    if include_raw and "raw" in content_obj:
        out["content_raw"] = content_obj.get("raw")
    return out


def pagination_schema() -> Dict[str, Any]:
    return {
        "page": {"type": "integer", "minimum": 1, "default": 1},
        "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
    }


def coerce_page(args: Dict[str, Any]) -> Tuple[int, int]:
    page = int(args.get("page", 1) or 1)
    per_page = int(args.get("per_page", 10) or 10)
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 10
    if per_page > 100:
        per_page = 100
    return page, per_page
