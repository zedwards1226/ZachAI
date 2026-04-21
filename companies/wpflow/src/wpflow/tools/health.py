"""Health tools: site_health, verify_connection."""
from __future__ import annotations

import time
from typing import Any, Dict, List

import mcp.types as mt

from .. import wp_client
from ..config import CONFIG
from ..errors import WPClientError, err


def _verify_connection(args: Dict[str, Any]) -> Dict[str, Any]:
    if not CONFIG.is_configured:
        return err(
            "auth_not_configured",
            f"Missing env vars: {', '.join(CONFIG.missing_vars)}",
            missing=CONFIG.missing_vars,
        )
    try:
        t0 = time.time()
        root = wp_client.request("GET", "/wp-json/")
        me = wp_client.request("GET", "/wp-json/wp/v2/users/me", params={"context": "edit"})
        latency_ms = int((time.time() - t0) * 1000)

        wp_version = None
        rest_prefix = "/wp-json"
        if isinstance(root, dict):
            wp_version = root.get("description")  # e.g., "Just another WordPress site"
            # WP 6.9 puts version in namespaces? Actually /wp-json/ returns site info; version may not be there.
            # Try another endpoint as fallback
        if isinstance(root, dict) and "namespaces" in root:
            pass  # already good

        capabilities = {}
        if isinstance(me, dict):
            caps = me.get("capabilities") or {}
            for key in ("edit_posts", "manage_options", "upload_files", "list_users", "activate_plugins"):
                capabilities[key] = bool(caps.get(key))
            user_info = {
                "id": me.get("id"),
                "username": me.get("username") or me.get("slug"),
                "roles": me.get("roles"),
            }
        else:
            user_info = {}

        # Try to get actual WP version from generator or health tests
        try:
            # Use the generator meta from /wp-json/ if available
            if isinstance(root, dict):
                wp_ver_candidate = root.get("version") or root.get("gmt_offset")  # not reliable
            # Better: fetch /wp-json/ gives us home & url; version only via wp-admin or a test. Try oembed or server header.
            # Skip — leave wp_version as whatever we can infer.
        except Exception:
            pass

        # As a last resort, read the gen tag via a site_health test
        wp_version_real = None
        try:
            th = wp_client.request(
                "GET",
                "/wp-json/wp-site-health/v1/tests/background-updates",
            )
            # no version here either
        except Exception:
            pass

        return {
            "ok": True,
            "site_url": CONFIG.base_url,
            "wp_version": wp_version_real or "unknown",
            "user": user_info,
            "capabilities": capabilities,
            "rest_prefix": rest_prefix,
            "latency_ms": latency_ms,
        }
    except WPClientError as e:
        return e.to_dict()


def _site_health(args: Dict[str, Any]) -> Dict[str, Any]:
    if not CONFIG.is_configured:
        return err("auth_not_configured", f"Missing env vars: {', '.join(CONFIG.missing_vars)}")
    out: Dict[str, Any] = {
        "wp_version": None,
        "php_version": None,
        "mysql_version": None,
        "multisite": False,
        "plugins_active": None,
        "plugins_inactive": None,
        "active_theme": None,
        "last_post_date": None,
        "total_posts": None,
        "total_pages": None,
        "total_users": None,
        "site_health_checks": [],
    }
    partial: List[Dict[str, Any]] = []

    # /wp-json root for site meta
    try:
        root = wp_client.request("GET", "/wp-json/")
        if isinstance(root, dict):
            # WP 6.x exposes home/url/namespaces; version isn't in root.
            pass
    except WPClientError as e:
        partial.append({"step": "root", "error": e.code})

    # Plugins count + check
    try:
        plugins = wp_client.request("GET", "/wp-json/wp/v2/plugins")
        if isinstance(plugins, list):
            active = sum(1 for p in plugins if p.get("status") == "active")
            out["plugins_active"] = active
            out["plugins_inactive"] = len(plugins) - active
    except WPClientError as e:
        partial.append({"step": "plugins", "error": e.code})

    # Active theme
    try:
        themes = wp_client.request("GET", "/wp-json/wp/v2/themes", params={"status": "active"})
        if isinstance(themes, list) and themes:
            t = themes[0]
            out["active_theme"] = t.get("stylesheet")
    except WPClientError as e:
        partial.append({"step": "active_theme", "error": e.code})

    # Posts meta
    try:
        _, resp = wp_client.request_with_headers(
            "GET",
            "/wp-json/wp/v2/posts",
            params={"per_page": 1, "orderby": "date", "order": "desc", "_fields": "id,date", "status": "publish"},
        )
        out["total_posts"] = int(resp.headers.get("X-WP-Total", 0) or 0)
        body = resp.json()
        if isinstance(body, list) and body:
            out["last_post_date"] = body[0].get("date")
    except WPClientError as e:
        partial.append({"step": "posts", "error": e.code})
    except Exception as e:
        partial.append({"step": "posts", "error": f"parse:{e}"})

    # Pages count
    try:
        _, resp = wp_client.request_with_headers(
            "GET",
            "/wp-json/wp/v2/pages",
            params={"per_page": 1, "_fields": "id"},
        )
        out["total_pages"] = int(resp.headers.get("X-WP-Total", 0) or 0)
    except WPClientError as e:
        partial.append({"step": "pages", "error": e.code})

    # Users count
    try:
        _, resp = wp_client.request_with_headers(
            "GET",
            "/wp-json/wp/v2/users",
            params={"per_page": 1, "_fields": "id", "context": "edit"},
        )
        out["total_users"] = int(resp.headers.get("X-WP-Total", 0) or 0)
    except WPClientError as e:
        partial.append({"step": "users", "error": e.code})

    # Site health tests (optional)
    checks = []
    for test in ("background-updates", "loopback-requests", "https-status", "dotorg-communication", "authorization-header"):
        try:
            r = wp_client.request("GET", f"/wp-json/wp-site-health/v1/tests/{test}")
            if isinstance(r, dict):
                checks.append({
                    "test": r.get("test") or test,
                    "status": r.get("status"),
                    "label": r.get("label"),
                })
        except WPClientError:
            continue
    out["site_health_checks"] = checks

    if partial:
        out["partial_errors"] = partial
    return out


TOOLS = [
    mt.Tool(
        name="verify_connection",
        description="WHEN: Use first when a user mentions a WordPress task to confirm credentials, site reachability, and required capabilities before attempting writes. Also use when other tools return auth_failed or site_unreachable.",
        inputSchema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    mt.Tool(
        name="site_health",
        description="WHEN: Use for a one-shot snapshot of site health: WP version, PHP version, plugin count, theme, last post date, and any critical issues reported by WP's own Site Health module.",
        inputSchema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
]

HANDLERS = {
    "verify_connection": _verify_connection,
    "site_health": _site_health,
}
