"""Media tools: list_media, upload_media."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import mcp.types as mt

from .. import wp_client
from ..config import CONFIG
from ..errors import WPClientError, err
from ._common import coerce_page, page_meta


def _media_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    details = raw.get("media_details") or {}
    sizes_raw = details.get("sizes") or {}
    sizes = {}
    for key in ("thumbnail", "medium", "large"):
        sd = sizes_raw.get(key) or {}
        if sd:
            sizes[key] = sd.get("source_url")
    return {
        "id": raw.get("id"),
        "title": (raw.get("title") or {}).get("rendered", ""),
        "mime_type": raw.get("mime_type"),
        "source_url": raw.get("source_url"),
        "alt_text": raw.get("alt_text"),
        "caption": (raw.get("caption") or {}).get("rendered", ""),
        "date": raw.get("date"),
        "sizes": sizes,
    }


def _list_media(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page, per_page = coerce_page(args)
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "_fields": "id,title,mime_type,source_url,alt_text,caption,date,media_details",
        }
        if args.get("mime_type"):
            params["mime_type"] = args["mime_type"]
        if args.get("search"):
            params["search"] = args["search"]
        if args.get("after"):
            params["after"] = args["after"]
        if args.get("before"):
            params["before"] = args["before"]
        data, resp = wp_client.request_with_headers("GET", "/wp-json/wp/v2/media", params=params)
        media = [_media_summary(m) for m in data] if isinstance(data, list) else []
        return {"media": media, "pagination": page_meta(resp.headers, page, per_page)}
    except WPClientError as e:
        return e.to_dict()


def _upload_media(args: Dict[str, Any]) -> Dict[str, Any]:
    source = args.get("source")
    if not source:
        return err("invalid_params", "source is required.")
    title = args.get("title")
    alt_text = args.get("alt_text")
    caption = args.get("caption")
    filename_hint = args.get("filename")

    max_bytes = CONFIG.max_upload_mb * 1024 * 1024

    try:
        if source.startswith("http://") or source.startswith("https://"):
            if source.startswith("http://"):
                return err("invalid_source", "Only https:// URLs are allowed.")
            content, mime = wp_client.fetch_url_bytes(source, max_bytes=max_bytes)
            # Derive filename from URL if not given
            if not filename_hint:
                from urllib.parse import urlparse
                path = urlparse(source).path
                filename_hint = Path(path).name or "upload.bin"
        elif source.startswith("file://") or source.startswith("gopher://") or source.startswith("ftp://"):
            return err("invalid_source", "Scheme not allowed; use https:// or an absolute local path.")
        else:
            # Local path
            resolved = wp_client.validate_upload_path(source)
            size = resolved.stat().st_size
            if size > max_bytes:
                return err("file_too_large", f"File size {size} exceeds {max_bytes} bytes.")
            content = resolved.read_bytes()
            mime = wp_client.guess_mime(resolved.name)
            if not filename_hint:
                filename_hint = resolved.name

        # If MIME unknown from URL, try inferring from filename
        if mime in (None, "application/octet-stream") and filename_hint:
            guessed = wp_client.guess_mime(filename_hint)
            if guessed != "application/octet-stream":
                mime = guessed

        if mime not in wp_client.ALLOWED_UPLOAD_MIMES:
            return err("mime_not_allowed", f"MIME {mime} is not in whitelist.")

        files = {
            "file": (filename_hint, content, mime),
        }
        form_data: Dict[str, str] = {}
        if title:
            form_data["title"] = title
        if alt_text:
            form_data["alt_text"] = alt_text
        if caption:
            form_data["caption"] = caption

        # httpx multipart: we need the form data alongside the file
        # We'll use a combined dict
        multipart = {"file": files["file"]}
        for k, v in form_data.items():
            multipart[k] = (None, v)

        data = wp_client.request("POST", "/wp-json/wp/v2/media", files=multipart)
        if not isinstance(data, dict):
            return err("internal", "Unexpected upload_media response.")
        return {"media": _media_summary(data)}
    except WPClientError as e:
        return e.to_dict()


TOOLS = [
    mt.Tool(
        name="list_media",
        description="WHEN: Use to find uploaded images, videos, or files in the media library. Returns summaries; does not download binary content.",
        inputSchema={
            "type": "object",
            "properties": {
                "mime_type": {"type": "string"},
                "search": {"type": "string"},
                "after": {"type": "string", "format": "date-time"},
                "before": {"type": "string", "format": "date-time"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="upload_media",
        description="WHEN: Use to add an image or file to the media library, e.g., when creating a post with a featured image. Accepts a public https:// URL or an absolute local file path inside WPFLOW_UPLOAD_ROOT.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "filename": {"type": "string"},
                "title": {"type": "string"},
                "alt_text": {"type": "string"},
                "caption": {"type": "string"},
            },
            "required": ["source"],
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "list_media": _list_media,
    "upload_media": _upload_media,
}
