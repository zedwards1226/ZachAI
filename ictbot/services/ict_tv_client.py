"""CDP client for ICTBot — talks to the SAME TradingView Desktop CDP that
ORB uses (port 9222), but as a separate codebase. ICTBot uses its own TV
tab pinned to MES1! while ORB stays on its MNQ1! tab.

Phase-1 SCAN_ONLY = read-only via this CDP (health + chart_state). Order
placement (Phase 2) requires pane/tab focus serialization with ORB —
we'll add a cross-bot lock in `data/tv_cdp_lock` before flipping
SCAN_ONLY=false.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

import websockets.sync.client as ws_client

from config import CDP_HOST, CDP_PORT

logger = logging.getLogger(__name__)


def _json_request(path: str, timeout: float = 3.0) -> Any:
    url = f"http://{CDP_HOST}:{CDP_PORT}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def health_check() -> tuple[bool, str]:
    """Return (ok, message). Confirms CDP responds at /json/version."""
    try:
        ver = _json_request("/json/version")
        return True, f"chromium ok: {ver.get('Browser', '?')}"
    except urllib.error.URLError as exc:
        return False, f"cdp dead: {exc}"
    except Exception as exc:
        return False, f"cdp error: {exc}"


def list_tabs() -> list[dict[str, Any]]:
    try:
        return _json_request("/json")
    except Exception as exc:
        logger.warning("list_tabs failed: %s", exc)
        return []


def get_tradingview_tab() -> dict[str, Any] | None:
    """Find the first tab with a tradingview.com URL."""
    for tab in list_tabs():
        if tab.get("type") != "page":
            continue
        url = tab.get("url", "")
        if "tradingview.com" in url:
            return tab
    return None


class CDPSession:
    """Minimal CDP wrapper — open WebSocket, send Runtime.evaluate, close."""

    def __init__(self, ws_url: str, request_timeout: float = 10.0):
        self.ws_url = ws_url
        self.request_timeout = request_timeout
        self._ws: ws_client.ClientConnection | None = None
        self._next_id = 1

    def __enter__(self) -> "CDPSession":
        self._ws = ws_client.connect(self.ws_url, max_size=20 * 1024 * 1024)
        return self

    def __exit__(self, *exc) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def evaluate(self, expression: str, return_by_value: bool = True,
                await_promise: bool = False) -> Any:
        if self._ws is None:
            raise RuntimeError("CDP session not opened (use `with`)")
        msg_id = self._next_id
        self._next_id += 1
        msg = {
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise,
            },
        }
        self._ws.send(json.dumps(msg))
        # Drain until we see a response with our id
        while True:
            raw = self._ws.recv(timeout=self.request_timeout)
            payload = json.loads(raw)
            if payload.get("id") == msg_id:
                if "error" in payload:
                    raise RuntimeError(f"CDP error: {payload['error']}")
                result = payload.get("result", {}).get("result", {})
                return result.get("value")
            # Otherwise ignore (events from CDP)


def open_session() -> CDPSession | None:
    """Find TV tab on :9223 and return an unentered CDPSession. None if unavailable."""
    tab = get_tradingview_tab()
    if not tab:
        return None
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        return None
    return CDPSession(ws_url)


def chart_ready() -> tuple[bool, str]:
    """Quick DOM probe — does the TV chart canvas exist?"""
    sess = open_session()
    if sess is None:
        return False, "no tradingview tab on :9223"
    try:
        with sess as s:
            has_chart = s.evaluate(
                "!!document.querySelector('div[data-name=\"chart\"]') || "
                "!!document.querySelector('canvas')"
            )
            return bool(has_chart), "chart loaded" if has_chart else "no chart canvas"
    except Exception as exc:
        return False, f"evaluate failed: {exc}"
