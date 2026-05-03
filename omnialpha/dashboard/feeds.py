"""External data feeds for the dashboard. All free, no API keys.

  - CoinGecko free price API for BTC/ETH live + 30-min history
  - Kalshi public endpoints for live trade tape, trending events, top volume
  - RSS aggregator for CoinDesk + The Block + Decrypt + Cointelegraph

Cached aggressively to stay under rate limits — CoinGecko free tier is
30 req/min. Each cache TTL is tuned to the meaningful update frequency.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
HTTP_TIMEOUT_S = 8.0
USER_AGENT = "ZachAI-OmniAlpha/0.1"


# ─── CoinGecko (BTC/ETH live + history) ─────────────────────────────────


def fetch_crypto_prices() -> dict[str, dict[str, float]]:
    """Returns {'bitcoin': {'usd': float, 'usd_24h_change': float}, 'ethereum': {...}}.
    Empty dict if API fails — caller should handle gracefully."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
            r = c.get(
                f"{COINGECKO_BASE}/simple/price",
                params={
                    "ids": "bitcoin,ethereum",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                },
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("fetch_crypto_prices failed: %s", e)
        return {}


def fetch_crypto_history(coin_id: str, minutes: int = 60) -> list[tuple[int, float]]:
    """Returns [(ts_ms, price_usd), ...] for the last `minutes` minutes.

    coin_id is CoinGecko's id ('bitcoin' or 'ethereum'). Returns [] on failure.
    """
    days = max(1, (minutes + 59) // 60 // 24 + 1)  # ceil to days; 1+ to get 5-min granularity
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
            r = c.get(
                f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": days},
            )
            r.raise_for_status()
            payload = r.json()
            prices = payload.get("prices", []) or []
            if not prices:
                return []
            cutoff_ms = int((time.time() - minutes * 60) * 1000)
            return [(int(p[0]), float(p[1])) for p in prices if p[0] >= cutoff_ms]
    except Exception as e:
        logger.warning("fetch_crypto_history(%s) failed: %s", coin_id, e)
        return []


# ─── Kalshi public feeds ────────────────────────────────────────────────


@dataclass
class KalshiTrade:
    ticker: str
    created_time: str
    yes_price_dollars: float
    no_price_dollars: float
    side: str  # taker side
    count: float

    @property
    def time_str(self) -> str:
        return self.created_time[11:19] if self.created_time else "?"


def fetch_kalshi_live_trades(limit: int = 30) -> list[KalshiTrade]:
    """Recent fills across the entire Kalshi platform.
    This is the 'live tape' Zach asked for — every executed trade, public."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
            r = c.get(f"{KALSHI_BASE}/markets/trades", params={"limit": limit})
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        logger.warning("fetch_kalshi_live_trades failed: %s", e)
        return []
    out: list[KalshiTrade] = []
    for t in payload.get("trades", []) or []:
        try:
            out.append(KalshiTrade(
                ticker=t.get("ticker", ""),
                created_time=t.get("created_time", ""),
                yes_price_dollars=float(t.get("yes_price_dollars") or 0),
                no_price_dollars=float(t.get("no_price_dollars") or 0),
                side=t.get("taker_side", "?"),
                count=float(t.get("count_fp") or 0),
            ))
        except Exception:
            continue
    return out


@dataclass
class KalshiEvent:
    event_ticker: str
    title: str
    category: str


def fetch_kalshi_trending_events(limit: int = 20) -> list[KalshiEvent]:
    """Open events sorted by Kalshi's default ordering (recency / activity)."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
            r = c.get(f"{KALSHI_BASE}/events", params={"limit": limit, "status": "open"})
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        logger.warning("fetch_kalshi_trending_events failed: %s", e)
        return []
    out: list[KalshiEvent] = []
    for e in payload.get("events", []) or []:
        out.append(KalshiEvent(
            event_ticker=e.get("event_ticker", ""),
            title=e.get("title", ""),
            category=e.get("category", "Other"),
        ))
    return out


@dataclass
class KalshiTopMarket:
    ticker: str
    title: str
    yes_sub_title: str
    last_price_dollars: float
    volume_24h: float


def fetch_kalshi_top_markets(limit: int = 20) -> list[KalshiTopMarket]:
    """Top markets by activity. Walks 3 pages of /markets and ranks by
    volume_24h_fp falling back to lifetime volume_fp. Kalshi's default
    ordering surfaces newer markets, so we pull broadly and rank ourselves.
    """
    out: list[KalshiTopMarket] = []
    cursor: str | None = None
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
            for _ in range(3):
                params: dict[str, Any] = {"limit": 200, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                r = c.get(f"{KALSHI_BASE}/markets", params=params)
                r.raise_for_status()
                payload = r.json()
                for m in payload.get("markets", []) or []:
                    try:
                        v24 = float(m.get("volume_24h_fp") or 0)
                        vlt = float(m.get("volume_fp") or 0)
                    except (TypeError, ValueError):
                        continue
                    activity = v24 if v24 > 0 else vlt
                    if activity <= 0:
                        continue
                    out.append(KalshiTopMarket(
                        ticker=m.get("ticker", ""),
                        title=m.get("title", "") or m.get("yes_sub_title", ""),
                        yes_sub_title=m.get("yes_sub_title", ""),
                        last_price_dollars=float(m.get("last_price_dollars") or 0),
                        volume_24h=activity,
                    ))
                cursor = payload.get("cursor")
                if not cursor:
                    break
    except Exception as e:
        logger.warning("fetch_kalshi_top_markets failed: %s", e)
    out.sort(key=lambda x: x.volume_24h, reverse=True)
    return out[:limit]


# ─── Crypto news (RSS, no key needed) ────────────────────────────────────

# Free, no signup, no rate limits worth worrying about.
CRYPTO_NEWS_FEEDS: list[tuple[str, str]] = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]


@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    published: str  # ISO

    @property
    def short_time(self) -> str:
        # "2026-05-02T22:14:00Z" -> "22:14"
        return self.published[11:16] if len(self.published) >= 16 else self.published


def _parse_pub_date(text: str) -> str:
    """Best-effort parse of RFC822 / ISO published-date strings.
    Returns ISO string in UTC, or the original on parse failure."""
    if not text:
        return ""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
                timezone.utc).isoformat()
        except Exception:
            return text


def fetch_crypto_news(per_source_limit: int = 6) -> list[NewsItem]:
    """Aggregate latest headlines from all configured sources."""
    items: list[NewsItem] = []
    for source, url in CRYPTO_NEWS_FEEDS:
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT_S,
                              headers={"User-Agent": USER_AGENT},
                              follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                root = ET.fromstring(r.content)
        except Exception as e:
            logger.warning("RSS fetch %s failed: %s", source, e)
            continue
        # RSS shape: rss/channel/item/{title,link,pubDate}
        # Atom shape: feed/entry/{title,link@href,published}
        for item in root.iter():
            tag = item.tag.split("}", 1)[-1]
            if tag != "item" and tag != "entry":
                continue
            title = ""
            link = ""
            pub = ""
            for child in item:
                ctag = child.tag.split("}", 1)[-1]
                if ctag == "title" and child.text:
                    title = child.text.strip()
                elif ctag == "link":
                    link = child.attrib.get("href", "") or (child.text or "").strip()
                elif ctag in ("pubDate", "published", "updated"):
                    if child.text:
                        pub = child.text.strip()
            if title:
                items.append(NewsItem(
                    source=source,
                    title=title,
                    url=link,
                    published=_parse_pub_date(pub),
                ))
                if sum(1 for i in items if i.source == source) >= per_source_limit:
                    break
    items.sort(key=lambda x: x.published, reverse=True)
    return items
