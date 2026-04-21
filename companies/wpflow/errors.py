"""wpflow error taxonomy — 20 codes per ARCHITECTURE.md §7.

Every tool must return a structured error dict on failure, never raise.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


_HINTS: Dict[str, str] = {
    "auth_not_configured": "Set WPFLOW_SITE_URL / WPFLOW_USERNAME / WPFLOW_APP_PASSWORD.",
    "auth_failed": "Run verify_connection; likely bad app password.",
    "permission_denied": "The configured user lacks the capability for this action.",
    "not_found": "Try listing first to confirm ids.",
    "invalid_params": "Fix the offending field and retry.",
    "conflict": "Try a different slug or re-use returned existing_id.",
    "rate_limited": "Retry after retry_after_s seconds.",
    "site_unreachable": "Check WPFLOW_SITE_URL is correct and the site is online.",
    "rest_api_disabled": "Ask user to re-enable the WP REST API.",
    "rest_disabled_for_plugins": "Some hosts block /plugins; ask user to enable it.",
    "file_too_large": "Reduce file size or increase WPFLOW_MAX_UPLOAD_MB.",
    "mime_not_allowed": "Use an allowed MIME type (jpeg/png/gif/webp/svg/mp4/pdf).",
    "path_not_allowed": "Move the file under WPFLOW_UPLOAD_ROOT.",
    "upload_failed": "Check WP uploads directory is writable.",
    "plugin_broken": "Check WP error log for the plugin activation failure.",
    "partial": "Some sub-queries failed; see partial_errors.",
    "internal": "Unexpected error; see logs for request_id.",
    "invalid_source": "Provide an https:// URL or an absolute local path inside WPFLOW_UPLOAD_ROOT.",
    "invalid_action": "Use one of: approve, hold, spam, trash, delete_permanently.",
    "response_too_large": "WP returned >5MB; refine filters or reduce per_page.",
}


ALL_CODES = tuple(_HINTS.keys())


def err(
    code: str,
    message: str,
    *,
    http_status: Optional[int] = None,
    hint: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a structured error payload."""
    payload: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if http_status is not None:
        payload["http_status"] = http_status
    payload["hint"] = hint or _HINTS.get(code, "")
    for k, v in extra.items():
        if v is not None:
            payload[k] = v
    return {"error": payload}


class WPClientError(Exception):
    """Raised by wp_client on HTTP/transport failures; tool handlers translate to err()."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: Optional[int] = None,
        retry_after_s: Optional[int] = None,
        wp_body: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retry_after_s = retry_after_s
        self.wp_body = wp_body

    def to_dict(self) -> Dict[str, Any]:
        extra: Dict[str, Any] = {}
        if self.retry_after_s is not None:
            extra["retry_after_s"] = self.retry_after_s
        return err(
            self.code,
            self.message,
            http_status=self.http_status,
            **extra,
        )
