"""Unauthenticated Kalshi `/historical/*` puller.

Kalshi exposes three public endpoints that work without API keys:
  /historical/markets   — settled markets w/ outcomes + closing prices
  /historical/trades    — tick-level executed trades, second-resolution timestamps
  /historical/cutoff    — current data-availability cutoff (~2-month lag)

This module is the foundation of the backtest engine — pulls historical
data, normalizes into our SQLite schema, and persists. Designed to be
re-runnable: `upsert` semantics mean re-running the same date range is
safe and idempotent.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

from config import KALSHI_API_BASE

logger = logging.getLogger(__name__)

# Kalshi public endpoints have a 100 req/min default rate limit. Sleep
# briefly between paginated calls to stay well under that ceiling.
DEFAULT_PAGINATION_DELAY_S = 0.2

# Httpx default timeout is fine for these — they're small responses.
HTTP_TIMEOUT_S = 30.0


def _client() -> httpx.Client:
    """One-shot httpx client. Caller is responsible for closing via context manager."""
    return httpx.Client(
        base_url=KALSHI_API_BASE,
        timeout=HTTP_TIMEOUT_S,
        headers={
            # User-Agent helps if Kalshi ever needs to debug bot traffic.
            "User-Agent": "ZachAI-OmniAlpha/0.1 (+https://github.com/zedwards1226)",
        },
    )


def get_market_status(ticker: str) -> dict | None:
    """Fetch live state for a single market via the unauthenticated
    /markets/{ticker} endpoint. Returns None if not found.

    Used by trade_monitor to settle paper trades whose markets resolved
    but haven't been re-ingested into the local markets table yet.
    """
    with _client() as client:
        try:
            r = client.get(f"/markets/{ticker}")
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    return r.json().get("market") or {}


def get_cutoff() -> dict[str, str]:
    """Fetch the current historical-data cutoff timestamps.

    Returns a dict like:
      {
        "market_settled_ts": "2026-03-02T00:00:00Z",
        "orders_updated_ts": "2026-03-02T00:00:00Z",
        "trades_created_ts": "2026-03-02T00:00:00Z",
      }

    Anything older than these timestamps is available via /historical/*.
    Anything newer needs the authenticated /markets and /trades endpoints.
    """
    with _client() as client:
        r = client.get("/historical/cutoff")
        r.raise_for_status()
        return r.json()


def iter_historical_markets(
    *,
    series_ticker: str | None = None,
    event_ticker: str | None = None,
    min_close_ts: str | None = None,
    max_close_ts: str | None = None,
    limit_per_page: int = 1000,
    max_pages: int | None = None,
    pagination_delay_s: float = DEFAULT_PAGINATION_DELAY_S,
) -> Iterator[dict[str, Any]]:
    """Yield settled markets one by one, paginating through Kalshi's cursor.

    All filters are applied server-side (Kalshi supports them as query params).

    Args:
        series_ticker: e.g. "KXBTC15M" for Bitcoin 15-min binary up/down.
        event_ticker: drill down to a specific event.
        min_close_ts / max_close_ts: ISO timestamps to bound the window.
        limit_per_page: 1000 is the API max.
        max_pages: safety cap for incremental pulls. None = pull everything.
    """
    params: dict[str, str | int] = {"limit": limit_per_page}
    if series_ticker:
        params["series_ticker"] = series_ticker
    if event_ticker:
        params["event_ticker"] = event_ticker
    if min_close_ts:
        params["min_close_ts"] = min_close_ts
    if max_close_ts:
        params["max_close_ts"] = max_close_ts

    cursor: str | None = None
    page = 0
    with _client() as client:
        while True:
            page += 1
            if cursor:
                params["cursor"] = cursor
            r = client.get("/historical/markets", params=params)
            r.raise_for_status()
            payload = r.json()

            markets = payload.get("markets", []) or []
            for m in markets:
                yield m

            cursor = payload.get("cursor")
            logger.debug(
                "page %d: %d markets, cursor=%s",
                page, len(markets), (cursor or "")[:12],
            )
            if not cursor or not markets:
                return
            if max_pages and page >= max_pages:
                logger.info("hit max_pages=%d, stopping", max_pages)
                return
            time.sleep(pagination_delay_s)


def iter_historical_trades(
    *,
    market_ticker: str | None = None,
    min_ts: str | None = None,
    max_ts: str | None = None,
    limit_per_page: int = 1000,
    max_pages: int | None = None,
    pagination_delay_s: float = DEFAULT_PAGINATION_DELAY_S,
) -> Iterator[dict[str, Any]]:
    """Yield executed trades for one market (or all markets) in a window.

    Trades are second-resolution timestamps. Useful for backtesting
    strategies that depend on intra-market price movement (theta plays,
    mean reversion, news reaction).
    """
    params: dict[str, str | int] = {"limit": limit_per_page}
    if market_ticker:
        params["ticker"] = market_ticker
    if min_ts:
        params["min_ts"] = min_ts
    if max_ts:
        params["max_ts"] = max_ts

    cursor: str | None = None
    page = 0
    with _client() as client:
        while True:
            page += 1
            if cursor:
                params["cursor"] = cursor
            r = client.get("/historical/trades", params=params)
            r.raise_for_status()
            payload = r.json()

            trades = payload.get("trades", []) or []
            for t in trades:
                yield t

            cursor = payload.get("cursor")
            if not cursor or not trades:
                return
            if max_pages and page >= max_pages:
                return
            time.sleep(pagination_delay_s)


# ─── Sector classification ─────────────────────────────────────────────
# Kalshi's series_ticker prefixes are stable enough to classify by string.
# Add new patterns as new sectors come online.
_SECTOR_PREFIXES: list[tuple[str, str]] = [
    ("KXBTC", "crypto"),
    ("KXETH", "crypto"),
    ("KXSOL", "crypto"),
    ("KXNBA", "sports"),
    ("KXMLB", "sports"),
    ("KXNHL", "sports"),
    ("KXNFL", "sports"),
    ("KXEPL", "sports"),
    ("KXLALIGA", "sports"),
    ("KXHIGH", "weather"),
    ("KXTEMP", "weather"),
    ("KXCPI", "economics"),
    ("KXNFP", "economics"),
    ("KXFED", "economics"),
    ("KXFOMC", "economics"),
    ("KXPRES", "politics"),
    ("KXSEN", "politics"),
    ("KXHOUSE", "politics"),
    ("KXGOV", "politics"),
]


def classify_sector(ticker: str) -> str:
    """Map a Kalshi market ticker (or series ticker) to a sector tag.
    Returns 'other' for anything we don't recognize yet."""
    upper = ticker.upper()
    for prefix, sector in _SECTOR_PREFIXES:
        if upper.startswith(prefix):
            return sector
    return "other"


# ─── Persistence ───────────────────────────────────────────────────────
def market_row_from_api(m: dict[str, Any]) -> dict[str, Any]:
    """Project a Kalshi /historical/markets payload onto our markets-table columns.

    Keeps the full raw JSON in raw_json so we can reprocess if the schema evolves.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = m.get("ticker", "")
    return {
        "ticker": ticker,
        "event_ticker": m.get("event_ticker"),
        "series_ticker": _series_from_ticker(ticker),
        "sector": classify_sector(m.get("series_ticker") or ticker),
        "title": m.get("title") or m.get("yes_sub_title"),
        "open_time": m.get("open_time"),
        "close_time": m.get("close_time"),
        "expiration_time": m.get("expiration_time"),
        "market_type": m.get("market_type"),
        "strike_type": m.get("strike_type"),
        "floor_strike": _safe_float(m.get("floor_strike")),
        "cap_strike": _safe_float(m.get("cap_strike")),
        "status": m.get("status"),
        "result": m.get("result"),
        "settlement_value_dollars": _safe_float(m.get("settlement_value_dollars")),
        "final_yes_ask_dollars": _safe_float(m.get("yes_ask_dollars")),
        "final_no_ask_dollars": _safe_float(m.get("no_ask_dollars")),
        "volume_fp": _safe_float(m.get("volume_fp")),
        "open_interest_fp": _safe_float(m.get("open_interest_fp")),
        "raw_json": json.dumps(m),
        "first_seen_at": now_iso,
        "last_updated_at": now_iso,
    }


def _series_from_ticker(ticker: str) -> str | None:
    """Series ticker is everything before the first '-' in the market ticker.
    e.g. "KXBTC15M-26MAR011845-45" -> "KXBTC15M"."""
    if not ticker or "-" not in ticker:
        return None
    return ticker.split("-", 1)[0]


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
