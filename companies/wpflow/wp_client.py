"""WP REST client for wpflow.

- httpx-based sync client (mcp SDK handles event loop elsewhere).
- Basic auth with (username, app_password).
- Real browser-like User-Agent (Cloudflare 1010 workaround; see data/INGESTION.md).
- 5 MB response cap.
- Secret scrubbing in logs.
- Typed errors via WPClientError.
"""
from __future__ import annotations

import base64
import ipaddress
import logging
import logging.handlers
import mimetypes
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlparse

import httpx

from config import CONFIG
from errors import WPClientError


# ---------- Logging ----------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "wpflow.log"

_logger: Optional[logging.Logger] = None


class _SecretScrubber(logging.Filter):
    """Strips Authorization: Basic <b64>, app password, and URL userinfo from log records."""

    def __init__(self, app_password: str) -> None:
        super().__init__()
        self._patterns = [
            re.compile(r"Authorization:\s*Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE),
            re.compile(r"authorization['\"]?\s*[:=]\s*['\"]?Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE),
            re.compile(r"https?://[^/\s:@]+:[^/\s@]+@"),  # URL userinfo
        ]
        if app_password:
            pw = app_password.strip()
            if pw:
                self._patterns.append(re.compile(re.escape(pw)))
                self._patterns.append(re.compile(re.escape(pw.replace(" ", ""))))

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        scrubbed = msg
        for p in self._patterns:
            scrubbed = p.sub("<REDACTED>", scrubbed)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        return True


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    lg = logging.getLogger("wpflow")
    lg.setLevel(getattr(logging, CONFIG.log_level, logging.INFO))
    lg.handlers.clear()

    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(fmt)
    handler.addFilter(_SecretScrubber(CONFIG.app_password or ""))
    lg.addHandler(handler)
    lg.propagate = False
    _logger = lg
    return lg


# ---------- Constants ----------

USER_AGENT = "wpflow/0.1.0 (+https://github.com/zedwards1226/wpflow)"
BROWSERISH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 "
    "wpflow/0.1.0"
)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
ALLOWED_UPLOAD_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "video/mp4",
    "application/pdf",
}


def _auth_header() -> str:
    user = CONFIG.username or ""
    pw = CONFIG.normalized_app_password
    raw = f"{user}:{pw}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _default_headers(write: bool = False) -> Dict[str, str]:
    headers = {
        "User-Agent": BROWSERISH_UA,
        "Accept": "application/json",
    }
    if write:
        headers["Content-Type"] = "application/json"
    if CONFIG.is_configured:
        headers["Authorization"] = _auth_header()
    return headers


def _check_site_scheme() -> None:
    if not CONFIG.base_url:
        raise WPClientError("auth_not_configured", "WPFLOW_SITE_URL is not set.")
    if not CONFIG.base_url.startswith("https://") and not CONFIG.allow_insecure:
        raise WPClientError(
            "invalid_params",
            "WPFLOW_SITE_URL must be https:// (set WPFLOW_ALLOW_INSECURE=1 for http).",
            http_status=400,
        )


def _translate_http_error(resp: httpx.Response) -> WPClientError:
    status = resp.status_code
    body: Dict[str, Any] = {}
    try:
        body = resp.json()
    except Exception:
        pass
    wp_code = body.get("code") if isinstance(body, dict) else None
    wp_msg = body.get("message") if isinstance(body, dict) else None

    if status == 401:
        return WPClientError(
            "auth_failed",
            "WordPress rejected the application password.",
            http_status=401,
            wp_body=body if isinstance(body, dict) else None,
        )
    if status == 403:
        return WPClientError(
            "permission_denied",
            wp_msg or "Forbidden; user lacks required capability.",
            http_status=403,
            wp_body=body if isinstance(body, dict) else None,
        )
    if status == 404:
        if wp_code == "rest_no_route":
            return WPClientError(
                "rest_api_disabled",
                wp_msg or "WP REST route not found.",
                http_status=404,
            )
        return WPClientError(
            "not_found",
            wp_msg or "Resource not found.",
            http_status=404,
        )
    if status == 409 or (wp_code and "exists" in str(wp_code)):
        return WPClientError(
            "conflict",
            wp_msg or "Resource already exists.",
            http_status=status,
            wp_body=body if isinstance(body, dict) else None,
        )
    if status == 429:
        retry_after = None
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                retry_after = int(ra)
            except ValueError:
                retry_after = None
        return WPClientError(
            "rate_limited",
            "Host throttled the request.",
            http_status=429,
            retry_after_s=retry_after,
        )
    if 400 <= status < 500:
        return WPClientError(
            "invalid_params",
            wp_msg or f"WP rejected the request ({status}).",
            http_status=status,
            wp_body=body if isinstance(body, dict) else None,
        )
    if status >= 500:
        return WPClientError(
            "upload_failed" if wp_code == "rest_upload_sideload_error" else "internal",
            wp_msg or f"WP returned {status}.",
            http_status=status,
        )
    return WPClientError("internal", f"Unhandled status {status}.", http_status=status)


# ---------- Client ----------

_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=CONFIG.timeout_seconds,
            follow_redirects=True,
            verify=True,
            headers={"User-Agent": BROWSERISH_UA},
        )
    return _client


def close_client() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        finally:
            _client = None


def _url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"{CONFIG.base_url}{path}"


def _enforce_size(resp: httpx.Response) -> None:
    cl = resp.headers.get("Content-Length")
    if cl and cl.isdigit() and int(cl) > MAX_RESPONSE_BYTES:
        raise WPClientError(
            "response_too_large",
            f"Response body {cl} bytes exceeds 5MB cap.",
            http_status=resp.status_code,
        )
    content = resp.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise WPClientError(
            "response_too_large",
            f"Response body {len(content)} bytes exceeds 5MB cap.",
            http_status=resp.status_code,
        )


def request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    raw_response: bool = False,
) -> Union[Dict[str, Any], list, Tuple[Any, httpx.Response]]:
    """Issue a WP REST request. Returns parsed JSON or (json, response) if raw_response."""
    if not CONFIG.is_configured:
        raise WPClientError(
            "auth_not_configured",
            f"Missing env vars: {', '.join(CONFIG.missing_vars)}",
        )
    _check_site_scheme()
    logger = get_logger()

    write = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
    hdrs = _default_headers(write=write and files is None)
    if files is not None:
        hdrs.pop("Content-Type", None)  # multipart handled by httpx
    if headers:
        hdrs.update(headers)

    url = _url(path)
    # Retry policy: GET retries twice on 5xx / connection errors, 1s/3s backoff.
    attempts = 3 if method.upper() == "GET" else 1
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            client = _get_client()
            logger.info("HTTP %s %s (attempt %d)", method.upper(), path, attempt + 1)
            resp = client.request(
                method,
                url,
                params=params,
                json=json_body if files is None else None,
                files=files,
                headers=hdrs,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, socket.gaierror) as e:
            last_exc = e
            logger.warning("Network error: %s", e)
            if attempt + 1 < attempts:
                time.sleep(1 * (attempt + 1) * 2)
                continue
            raise WPClientError(
                "site_unreachable",
                f"Could not reach {CONFIG.base_url}: {type(e).__name__}",
            )
        except httpx.HTTPError as e:
            raise WPClientError("internal", f"HTTP error: {e}")

        if resp.status_code >= 500 and attempt + 1 < attempts and method.upper() == "GET":
            time.sleep(1 * (attempt + 1) * 2)
            continue

        _enforce_size(resp)

        if resp.status_code >= 400:
            logger.warning("WP %s -> %d", path, resp.status_code)
            raise _translate_http_error(resp)

        logger.info("WP %s -> %d (%d bytes)", path, resp.status_code, len(resp.content))

        if not resp.content:
            data: Any = {}
        else:
            try:
                data = resp.json()
            except Exception as e:
                raise WPClientError(
                    "internal",
                    f"WP response not JSON: {e}",
                    http_status=resp.status_code,
                )

        if raw_response:
            return data, resp
        return data

    # Should be unreachable
    raise WPClientError("internal", f"Request failed: {last_exc}")


# ---------- Helpers for composite calls ----------

def request_with_headers(
    method: str,
    path: str,
    **kwargs: Any,
) -> Tuple[Any, httpx.Response]:
    """Like request() but always returns (body, response) so callers can read X-WP-Total etc."""
    return request(method, path, raw_response=True, **kwargs)  # type: ignore[return-value]


def ssrf_guard(url: str) -> None:
    """Reject URLs that point at internal/loopback/link-local/unknown schemes."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise WPClientError("invalid_source", f"Scheme '{parsed.scheme}' not allowed; use https://")
    host = parsed.hostname or ""
    if not host:
        raise WPClientError("invalid_source", "URL has no host.")
    if host.endswith(".internal") or host in ("localhost",):
        raise WPClientError("invalid_source", "Internal hosts not allowed.")
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise WPClientError("invalid_source", f"Could not resolve host {host}.")
    for family, _, _, _, sockaddr in addrs:
        ip = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
            raise WPClientError("invalid_source", f"Host {host} resolves to non-public IP {ip}.")


def validate_upload_path(path_str: str) -> Path:
    """Ensure the path is absolute and inside an allowed upload root."""
    p = Path(path_str)
    if not p.is_absolute():
        raise WPClientError("invalid_source", "Local path must be absolute.")
    try:
        resolved = p.resolve(strict=True)
    except FileNotFoundError:
        raise WPClientError("invalid_source", f"File not found: {path_str}")
    except OSError as e:
        raise WPClientError("invalid_source", f"Cannot access {path_str}: {e}")

    # Denylist of system paths
    blocked_prefixes = [
        Path("C:/Windows").resolve() if os.name == "nt" else None,
        Path("C:/ProgramData").resolve() if os.name == "nt" else None,
        Path("/etc"),
        Path("/var"),
        Path("/sys"),
        Path("/proc"),
    ]
    for bp in blocked_prefixes:
        if bp is None:
            continue
        try:
            resolved.relative_to(bp)
            raise WPClientError("path_not_allowed", f"Path is in denylist root {bp}.")
        except ValueError:
            pass

    if not CONFIG.upload_roots:
        raise WPClientError(
            "path_not_allowed",
            "No WPFLOW_UPLOAD_ROOT configured and no default dirs found.",
        )
    for root in CONFIG.upload_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise WPClientError(
        "path_not_allowed",
        f"Path {resolved} is outside allowed roots.",
    )


def guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def fetch_url_bytes(url: str, max_bytes: int) -> Tuple[bytes, str]:
    """Fetch a URL's bytes (for upload_media URL source). Returns (content, mime)."""
    ssrf_guard(url)
    client = httpx.Client(
        timeout=CONFIG.timeout_seconds,
        follow_redirects=True,
        verify=True,
        headers={"User-Agent": BROWSERISH_UA},
    )
    try:
        with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise WPClientError(
                    "invalid_source",
                    f"Fetch of {url} returned {resp.status_code}.",
                    http_status=resp.status_code,
                )
            mime = resp.headers.get("Content-Type", "").split(";")[0].strip() or "application/octet-stream"
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise WPClientError(
                        "file_too_large",
                        f"Source exceeds {max_bytes} bytes.",
                    )
            return bytes(buf), mime
    finally:
        client.close()
