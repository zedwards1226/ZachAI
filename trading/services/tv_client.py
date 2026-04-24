"""TradingView CDP Client — connects to TradingView Desktop via Chrome DevTools Protocol.

Uses the same JavaScript expressions as tradingview-mcp/src/core/data.js to extract
OHLCV bars, quotes, indicator values, and control chart timeframe/symbol.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

import httpx
import websockets

from config import CDP_HOST, CDP_PORT

logger = logging.getLogger(__name__)

# Singleton
_client: Optional["TVClient"] = None
_lock = asyncio.Lock()


async def get_client() -> "TVClient":
    """Get or create the singleton TVClient."""
    global _client
    async with _lock:
        if _client is None or not _client.connected:
            _client = TVClient()
            await _client.connect()
        return _client


async def disconnect() -> None:
    """Disconnect the singleton TVClient on shutdown."""
    global _client
    if _client and _client.connected:
        await _client.disconnect()
        _client = None


class TVClient:
    """CDP WebSocket client for TradingView Desktop."""

    def __init__(self, host: str = CDP_HOST, port: int = CDP_PORT):
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.msg_id = 0
        self.connected = False
        self._pending: dict[int, asyncio.Future] = {}
        self._recv_task: Optional[asyncio.Task] = None
        self._last_ping = 0.0

    async def connect(self) -> None:
        """Discover TradingView chart target and connect via WebSocket."""
        target = await self._find_chart_target()
        if not target:
            raise ConnectionError("TradingView chart not found on CDP port %d" % self.port)

        ws_url = target["webSocketDebuggerUrl"]
        # On Windows, sometimes the URL uses 0.0.0.0 — replace with localhost
        ws_url = ws_url.replace("0.0.0.0", self.host)

        logger.info("Connecting to TradingView CDP: %s", ws_url)
        self.ws = await websockets.connect(ws_url, max_size=10 * 1024 * 1024)
        self.connected = True

        # Start background receiver
        self._recv_task = asyncio.create_task(self._receiver())

        # Enable Runtime domain
        await self._send("Runtime.enable", {})
        logger.info("TradingView CDP connected successfully")

    async def _find_chart_target(self) -> Optional[dict]:
        """HTTP GET to /json/list to find the TradingView chart page."""
        url = f"http://{self.host}:{self.port}/json/list"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                targets = resp.json()
        except Exception as e:
            logger.error("Failed to discover CDP targets: %s", e)
            return None

        for t in targets:
            page_url = t.get("url", "").lower()
            if "tradingview.com/chart" in page_url and t.get("type") == "page":
                return t

        # Fallback: any tradingview page
        for t in targets:
            if "tradingview" in t.get("url", "").lower():
                return t

        logger.error("No TradingView page found among %d targets", len(targets))
        return None

    async def _receiver(self) -> None:
        """Background task to receive and dispatch CDP responses."""
        try:
            async for msg in self.ws:
                data = json.loads(msg)
                msg_id = data.get("id")
                if msg_id is not None and msg_id in self._pending:
                    self._pending[msg_id].set_result(data)
        except websockets.ConnectionClosed:
            logger.warning("CDP WebSocket connection closed")
            self.connected = False
        except Exception as e:
            logger.error("CDP receiver error: %s", e)
            self.connected = False

    async def _send(self, method: str, params: dict, timeout: float = 10.0) -> dict:
        """Send a CDP command and wait for the response."""
        if not self.ws or not self.connected:
            raise ConnectionError("Not connected to TradingView CDP")

        self.msg_id += 1
        msg_id = self.msg_id
        # get_running_loop is preferred over the deprecated get_event_loop
        # inside async contexts (Python 3.10+ emits a DeprecationWarning).
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future

        payload = {"id": msg_id, "method": method, "params": params}
        try:
            await self.ws.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            self.connected = False
            self._pending.pop(msg_id, None)
            raise

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

        return result.get("result", {})

    async def _evaluate_once(self, js: str, *, await_promise: bool, timeout: float) -> Any:
        """Single Runtime.evaluate round-trip — raises on connection loss."""
        result = await self._send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
            "awaitPromise": await_promise,
        }, timeout=timeout)
        if "exceptionDetails" in result:
            err = result["exceptionDetails"]
            raise RuntimeError("JS evaluation error: %s" % err.get("text", str(err)))
        return result.get("result", {}).get("value")

    async def evaluate(self, js: str, timeout: float = 10.0) -> Any:
        """Evaluate JavaScript in the TradingView page context.

        Auto-heals in two layers:
          1. Stale-ping: if it's been >5s since the last known-good call,
             send a trivial `1` to confirm the socket is alive before the
             real payload; on failure, reconnect.
          2. Retry-once: if the payload itself fails because the WS dropped
             (TV page reloaded, chart crashed, CDP target churned), reconnect
             and retry the same call one time. After that, propagate.
        """
        # Health check if stale
        now = time.monotonic()
        if now - self._last_ping > 5.0:
            try:
                await self._send("Runtime.evaluate",
                                 {"expression": "1", "returnByValue": True}, timeout=3)
                self._last_ping = now
            except Exception:
                await self._reconnect()

        try:
            return await self._evaluate_once(js, await_promise=False, timeout=timeout)
        except (ConnectionError, websockets.ConnectionClosed) as exc:
            logger.warning("evaluate lost connection (%s) — reconnecting and retrying once", exc)
            await self._reconnect()
            return await self._evaluate_once(js, await_promise=False, timeout=timeout)

    async def evaluate_async(self, js: str, timeout: float = 15.0) -> Any:
        """Evaluate async JavaScript (returns a Promise) in the TradingView page context.

        Same reconnect-and-retry-once semantics as `evaluate`. Useful for
        order-placement IIFEs — if TradingView rerendered the trading panel
        mid-flight we reconnect transparently rather than bubbling a hard
        failure that marks the trade FAILED_PLACEMENT.
        """
        try:
            return await self._evaluate_once(js, await_promise=True, timeout=timeout)
        except (ConnectionError, websockets.ConnectionClosed) as exc:
            logger.warning("evaluate_async lost connection (%s) — reconnecting and retrying once", exc)
            await self._reconnect()
            return await self._evaluate_once(js, await_promise=True, timeout=timeout)

    async def _reconnect(self, retries: int = 5) -> None:
        """Reconnect with exponential backoff."""
        delay = 0.5
        for attempt in range(retries):
            logger.info("CDP reconnect attempt %d/%d", attempt + 1, retries)
            try:
                if self.ws:
                    await self.ws.close()
                if self._recv_task:
                    self._recv_task.cancel()
                await self.connect()
                return
            except Exception as e:
                logger.warning("Reconnect failed: %s", e)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
        raise ConnectionError("Failed to reconnect after %d attempts" % retries)

    async def disconnect(self) -> None:
        """Close the CDP connection."""
        self.connected = False
        if self._recv_task:
            self._recv_task.cancel()
        if self.ws:
            await self.ws.close()

    # ─── Data Methods ───────────────────────────────────────────────

    async def get_ohlcv(self, count: int = 100) -> list[dict]:
        """Get OHLCV bars from the current chart. Returns list of bar dicts."""
        js = f"""
        (function() {{
          try {{
            var bars = window.TradingViewApi._activeChartWidgetWV.value()
                ._chartWidget.model().mainSeries().bars();
            if (!bars || typeof bars.lastIndex !== 'function') return null;
            var result = [];
            var end = bars.lastIndex();
            var start = Math.max(bars.firstIndex(), end - {count} + 1);
            for (var i = start; i <= end; i++) {{
              var v = bars.valueAt(i);
              if (v) result.push({{
                time: v[0], open: v[1], high: v[2],
                low: v[3], close: v[4], volume: v[5] || 0
              }});
            }}
            return result;
          }} catch(e) {{ return {{error: e.message}}; }}
        }})()
        """
        result = await self.evaluate(js)
        if result is None:
            return []
        if isinstance(result, dict) and "error" in result:
            logger.error("get_ohlcv error: %s", result["error"])
            return []
        return result

    async def get_quote(self) -> dict:
        """Get current price quote for the active chart symbol."""
        js = """
        (function() {
          try {
            var api = window.TradingViewApi._activeChartWidgetWV.value();
            var bars = api._chartWidget.model().mainSeries().bars();
            var sym = '';
            try { sym = api.symbol(); } catch(e) {}
            var quote = {symbol: sym};
            if (bars && typeof bars.lastIndex === 'function') {
              var last = bars.valueAt(bars.lastIndex());
              if (last) {
                quote.time = last[0]; quote.open = last[1]; quote.high = last[2];
                quote.low = last[3]; quote.close = last[4]; quote.last = last[4];
                quote.volume = last[5] || 0;
              }
            }
            return quote;
          } catch(e) { return {error: e.message}; }
        })()
        """
        return await self.evaluate(js) or {}

    async def get_symbol(self) -> str:
        """Get the current chart symbol."""
        js = """
        (function() {
          try {
            return window.TradingViewApi._activeChartWidgetWV.value().symbol();
          } catch(e) { return ''; }
        })()
        """
        return await self.evaluate(js) or ""

    async def get_study_values(self) -> list[dict]:
        """Get all visible indicator values from the data window."""
        js = """
        (function() {
          try {
            var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
            var sources = chart.model().model().dataSources();
            var results = [];
            for (var si = 0; si < sources.length; si++) {
              var s = sources[si];
              if (!s.metaInfo) continue;
              try {
                var meta = s.metaInfo();
                var name = meta.description || meta.shortDescription || '';
                if (!name) continue;
                var values = {};
                var dwv = s.dataWindowView();
                if (dwv) {
                  var items = dwv.items();
                  if (items) {
                    for (var i = 0; i < items.length; i++) {
                      var item = items[i];
                      if (item._value && item._value !== '∅' && item._title) {
                        var v = parseFloat(item._value);
                        values[item._title] = isNaN(v) ? item._value : v;
                      }
                    }
                  }
                }
                if (Object.keys(values).length > 0) {
                  results.push({name: name, values: values});
                }
              } catch(e) {}
            }
            return results;
          } catch(e) { return []; }
        })()
        """
        return await self.evaluate(js) or []

    async def set_timeframe(self, tf: str) -> None:
        """Change chart timeframe. Values: '1','5','15','60','D','W','M'."""
        js = f"""
        (function() {{
          try {{
            var chart = window.TradingViewApi._activeChartWidgetWV.value();
            chart.setResolution('{tf}', {{}});
            return true;
          }} catch(e) {{ return false; }}
        }})()
        """
        await self.evaluate(js)
        await self._wait_chart_ready()

    async def set_symbol(self, symbol: str) -> None:
        """Change chart symbol."""
        js = f"""
        (function() {{
          try {{
            var chart = window.TradingViewApi._activeChartWidgetWV.value();
            chart.setSymbol('{symbol}', {{}});
            return true;
          }} catch(e) {{ return false; }}
        }})()
        """
        await self.evaluate(js)
        await self._wait_chart_ready()

    async def _wait_chart_ready(self, timeout: float = 10.0, poll_interval: float = 0.3) -> bool:
        """Wait for chart data to stabilize after timeframe/symbol change."""
        start = time.monotonic()
        prev_count = -1
        stable_reads = 0

        while time.monotonic() - start < timeout:
            js = """
            (function() {
              try {
                var bars = window.TradingViewApi._activeChartWidgetWV.value()
                    ._chartWidget.model().mainSeries().bars();
                return bars ? bars.size() : -1;
              } catch(e) { return -1; }
            })()
            """
            count = await self.evaluate(js)
            if count is not None and count > 0:
                if count == prev_count:
                    stable_reads += 1
                    if stable_reads >= 2:
                        return True
                else:
                    stable_reads = 0
                prev_count = count
            await asyncio.sleep(poll_interval)

        logger.warning("Chart readiness timeout after %.1fs", timeout)
        return False
