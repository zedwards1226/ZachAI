"""SENTINEL AGENT — Economic calendar + Truth Social monitoring.

Initial run at 8:00 AM ET: fetch today's economic events and recent Truth Social posts.
Continuous polling every 60 seconds during session: re-check Truth Social for new posts.
Sets NEWS_BLOCK and TRUTH_BLOCK flags. Sends Telegram alert on high-impact detection.
Writes output to state/sentinel.json.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pytz
from bs4 import BeautifulSoup

from config import (
    TIMEZONE, TRUTH_HIGH_IMPACT_KEYWORDS,
    SENTINEL_POLL_WINDOW, SESSION_END_HOUR, SESSION_END_MINUTE,
)
from services.state_manager import read_state, write_state
from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

_http: Optional[httpx.AsyncClient] = None
_last_truth_ids: set[str] = set()

# Cache 403 state so we don't hammer a blocked endpoint every 60 seconds.
# After a 403 we skip the API for 20 minutes and go straight to scrape.
_api_blocked_until: Optional[datetime] = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            follow_redirects=True,
        )
    return _http


async def run_initial() -> dict:
    """Initial run at 8:00 AM ET. Fetches economic calendar and Truth Social."""
    logger.info("Sentinel agent starting (initial run)")

    economic_events = await _fetch_economic_calendar()
    truth_posts, truth_status = await _fetch_truth_social()

    now = datetime.now(ET)

    # Check for high-impact events within 90 minutes of open (9:30)
    open_time = now.replace(hour=9, minute=30, second=0)
    window_start = open_time - timedelta(minutes=30)
    window_end = open_time + timedelta(minutes=60)

    news_block = False
    block_reason = None

    for event in economic_events:
        if event["impact"] == "HIGH" and event.get("within_session_window"):
            news_block = True
            block_reason = f"High-impact: {event['event']} at {event['time']}"
            break

    # Check Truth Social for high-impact posts in last 12 hours
    truth_block = False
    for post in truth_posts:
        if post["impact"] == "HIGH_IMPACT":
            post_age_min = post.get("age_minutes", 999)
            if post_age_min <= 30:
                truth_block = True
                block_reason = (block_reason or "") + f"; Truth Social: {post['text'][:80]}"
                break

    data = {
        "date": now.strftime("%Y-%m-%d"),
        "news_block": news_block,
        "truth_block": truth_block,
        "economic_events": economic_events,
        "truth_posts": truth_posts[:10],
        "truth_status": truth_status,
        "last_poll": now.isoformat(),
        "block_reason": block_reason,
    }

    write_state("sentinel", data)
    logger.info("Sentinel initial complete: news_block=%s, truth_block=%s", news_block, truth_block)

    # Alert on blocks
    if news_block:
        await telegram.notify_sentinel_alert("NEWS BLOCK", block_reason or "High-impact event near open")
    if truth_block:
        await telegram.notify_sentinel_alert("TRUTH BLOCK", block_reason or "High-impact post detected")

    return data


async def poll() -> Optional[dict]:
    """Continuous polling during session. Re-checks Truth Social every 60 seconds."""
    now = datetime.now(ET)

    # Check if within poll window
    poll_start_h, poll_start_m = SENTINEL_POLL_WINDOW[0]
    poll_end_h, poll_end_m = SENTINEL_POLL_WINDOW[1]
    poll_start = now.replace(hour=poll_start_h, minute=poll_start_m, second=0)
    poll_end = now.replace(hour=poll_end_h, minute=poll_end_m, second=0)

    if now < poll_start or now > poll_end:
        return None

    # Re-check Truth Social
    truth_posts, truth_status = await _fetch_truth_social()

    # Load current state
    current = read_state("sentinel")

    # Check for NEW high-impact posts
    truth_block = current.get("truth_block", False)
    new_alert = False

    for post in truth_posts:
        post_id = post.get("id", post.get("text", "")[:50])
        if post["impact"] == "HIGH_IMPACT" and post_id not in _last_truth_ids:
            age_min = post.get("age_minutes", 999)
            if age_min <= 30:
                truth_block = True
                new_alert = True
                _last_truth_ids.add(post_id)
                logger.warning("NEW high-impact Truth Social post: %s", post["text"][:100])

    # Recompute news_block based on any upcoming high-impact event within 15
    # min. If nothing is imminent, clear the block (otherwise a stale block
    # from hours ago could linger for the whole session).
    news_block = False
    for event in current.get("economic_events", []):
        if event["impact"] != "HIGH":
            continue
        event_time = _parse_event_time(event.get("time", ""))
        if not event_time:
            continue
        minutes_until = (event_time - now).total_seconds() / 60
        if 0 <= minutes_until <= 15:
            news_block = True
            break

    # Update state
    current["truth_block"] = truth_block
    current["news_block"] = news_block
    current["truth_posts"] = truth_posts[:10]
    current["truth_status"] = truth_status
    current["last_poll"] = now.isoformat()

    write_state("sentinel", current)

    # Send alert on new high-impact post
    if new_alert:
        alert_text = "\n".join(
            f"• {p['text'][:120]}" for p in truth_posts
            if p["impact"] == "HIGH_IMPACT" and p.get("age_minutes", 999) <= 30
        )
        await telegram.notify_sentinel_alert(
            "TRUTH SOCIAL — HIGH IMPACT",
            f"New market-moving post detected:\n{alert_text}"
        )

    return current


# ─── Data Fetchers ──────────────────────────────────────────────

async def _fetch_economic_calendar() -> list[dict]:
    """Fetch today's economic events from Forex Factory."""
    events = []
    now = datetime.now(ET)

    try:
        http = _get_http()
        # Try the calendar page
        url = "https://www.forexfactory.com/calendar?day=today"
        resp = await http.get(url)

        if resp.status_code != 200:
            logger.warning("Forex Factory returned %d", resp.status_code)
            return _get_static_events(now)

        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse calendar rows
        rows = soup.select("tr.calendar__row")
        for row in rows:
            impact_el = row.select_one(".calendar__impact span")
            if not impact_el:
                continue

            impact_classes = impact_el.get("class", [])
            if any("high" in c.lower() for c in impact_classes):
                impact = "HIGH"
            elif any("medium" in c.lower() for c in impact_classes):
                impact = "MEDIUM"
            else:
                impact = "LOW"

            time_el = row.select_one(".calendar__time")
            event_el = row.select_one(".calendar__event")

            event_time = time_el.get_text(strip=True) if time_el else ""
            event_name = event_el.get_text(strip=True) if event_el else ""

            if not event_name:
                continue

            # Check if within session window (8:00 AM - 11:00 AM)
            within_window = _is_near_session(event_time, now)

            events.append({
                "time": event_time,
                "event": event_name,
                "impact": impact,
                "within_session_window": within_window,
            })

    except Exception as e:
        logger.warning("Failed to fetch Forex Factory: %s", e)
        return _get_static_events(now)

    if not events:
        events = _get_static_events(now)

    return events


async def _fetch_truth_social() -> tuple[list[dict], str]:
    """Fetch recent posts from Truth Social @realDonaldTrump.

    Priority order:
    1. RSS feed (server-rendered XML — works even when SPA/API is blocked)
    2. JSON API (fast when available)
    3. HTML scrape (last resort — rarely works due to SPA)
    """
    global _api_blocked_until
    posts = []
    now = datetime.now(ET)

    try:
        http = _get_http()

        # 1. Financial news RSS (Reuters/AP/CNBC/Yahoo) — always try first.
        #    Truth Social serves a JS SPA for all routes so direct scraping
        #    never works. News RSS picks up Trump statements within minutes.
        rss_posts = await _fetch_truth_rss(http, now)
        if rss_posts:
            return rss_posts, "NEWS_RSS"

        # 2. JSON API (if not currently backed off due to 403)
        api_ok = _api_blocked_until is None or now >= _api_blocked_until
        if api_ok:
            url = "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses?limit=20"
            resp = await http.get(url, headers={"Accept": "application/json"})

            if resp.status_code == 200:
                _api_blocked_until = None
                data = resp.json()
                for item in data:
                    text = _strip_html(item.get("content", ""))
                    created = item.get("created_at", "")
                    post_time = _parse_iso_time(created)
                    age_min = (now - post_time).total_seconds() / 60 if post_time else 999

                    if age_min > 720:
                        continue

                    impact = _classify_truth_impact(text)
                    posts.append({
                        "id": item.get("id", ""),
                        "time": created,
                        "text": text[:300],
                        "impact": impact,
                        "keywords_matched": _matched_keywords(text),
                        "age_minutes": round(age_min),
                    })

                return posts, "API"

            logger.info("Truth Social API returned %d, backing off 20 min", resp.status_code)
            _api_blocked_until = now + timedelta(minutes=20)

        # 3. HTML scrape (SPA — rarely yields posts)
        resp2 = await http.get("https://truthsocial.com/@realDonaldTrump")
        if resp2.status_code == 200:
            scraped = _parse_truth_html(resp2.text, now)
            if scraped:
                return scraped, "SCRAPED"
            return [], "SCRAPED_EMPTY"

    except Exception as e:
        logger.warning("Failed to fetch Truth Social: %s", e)

    return posts, "UNAVAILABLE"


async def _fetch_truth_rss(http: httpx.AsyncClient, now: datetime) -> list[dict]:
    """Fetch market-moving news from free financial RSS feeds.

    Truth Social's site serves a JS SPA for all routes (including .rss),
    so direct scraping never yields posts. Instead we pull from Reuters,
    AP, and Yahoo Finance — they pick up Trump statements within minutes
    and require no API key.
    """
    RSS_FEEDS = [
        ("https://finance.yahoo.com/rss/topstories", "Yahoo Finance"),
        ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC"),
        ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "NYT Business"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
    ]

    posts: list[dict] = []
    seen_ids: set[str] = set()

    for feed_url, source in RSS_FEEDS:
        try:
            resp = await http.get(
                feed_url,
                headers={"Accept": "application/rss+xml, application/xml, text/xml"},
            )
            if resp.status_code != 200:
                logger.debug("%s RSS returned %d", source, resp.status_code)
                continue

            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item")
            if not items:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.find_all("item")

            for item in items[:30]:
                title_el = item.find("title")
                desc_el = item.find("description")
                title = _strip_html(title_el.get_text() if title_el else "")
                desc = _strip_html(desc_el.get_text() if desc_el else "")
                text = f"{title}. {desc}".strip(". ") if desc else title
                if not title:
                    continue

                pub_el = item.find("pubDate")
                pub_str = pub_el.get_text(strip=True) if pub_el else ""
                post_time = _parse_rfc2822(pub_str, now)
                age_min = (now - post_time).total_seconds() / 60 if post_time else 0

                if age_min > 720:
                    continue

                link_el = item.find("link") or item.find("guid")
                post_id = link_el.get_text(strip=True) if link_el else f"{source}_{len(posts)}"

                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                impact = _classify_truth_impact(text, news_rss=True)
                posts.append({
                    "id": post_id,
                    "source": source,
                    "time": post_time.isoformat() if post_time else now.isoformat(),
                    "text": f"[{source}] {text[:250]}",
                    "impact": impact,
                    "keywords_matched": _matched_keywords(text),
                    "age_minutes": round(age_min),
                })

        except Exception as e:
            logger.warning("%s RSS fetch failed: %s", source, e)

    # Sort by recency
    posts.sort(key=lambda p: p.get("age_minutes", 999))
    return posts


def _parse_truth_html(html: str, now: datetime) -> list[dict]:
    """Extract posts from Truth Social HTML.

    Truth Social (Mastodon fork) sometimes embeds JSON-LD or inline
    <script> state. Try those first, then fall back to CSS selectors.
    """
    posts: list[dict] = []

    # 1. Try JSON-LD (application/ld+json)
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                text = item.get("articleBody") or item.get("text") or ""
                if not text:
                    continue
                created = item.get("datePublished", now.isoformat())
                post_time = _parse_iso_time(created)
                age_min = (now - post_time).total_seconds() / 60 if post_time else 0
                impact = _classify_truth_impact(text)
                posts.append({
                    "id": item.get("url", f"ld_{len(posts)}"),
                    "time": created,
                    "text": text[:300],
                    "impact": impact,
                    "keywords_matched": _matched_keywords(text),
                    "age_minutes": round(age_min),
                })
        except Exception:
            pass

    if posts:
        return posts

    # 2. Try inline __INITIAL_STATE__ or similar JS blobs
    for script in soup.find_all("script"):
        src = script.string or ""
        if "statuses" not in src and "content" not in src:
            continue
        # Look for JSON arrays containing {content: "...", created_at: "..."}
        matches = re.findall(r'\{"id":"(\d+)","content":"(.*?)","created_at":"([^"]+)"', src)
        for m_id, m_content, m_created in matches[:20]:
            text = _strip_html(m_content.replace("\\u003c", "<").replace("\\u003e", ">"))
            if not text:
                continue
            post_time = _parse_iso_time(m_created)
            age_min = (now - post_time).total_seconds() / 60 if post_time else 0
            impact = _classify_truth_impact(text)
            posts.append({
                "id": m_id,
                "time": m_created,
                "text": text[:300],
                "impact": impact,
                "keywords_matched": _matched_keywords(text),
                "age_minutes": round(age_min),
            })
        if posts:
            return posts

    # 3. CSS selectors as last resort (works only if SSR content present)
    status_els = soup.select(
        "[class*='status-content'], [class*='status__content'], article p"
    )
    for i, el in enumerate(status_els[:20]):
        text = el.get_text(strip=True)
        if len(text) < 10:
            continue
        impact = _classify_truth_impact(text)
        posts.append({
            "id": f"scraped_{i}",
            "time": now.isoformat(),
            "text": text[:300],
            "impact": impact,
            "keywords_matched": _matched_keywords(text),
            "age_minutes": 0,
        })

    return posts


def is_blocked() -> tuple[bool, str]:
    """Return (blocked, reason) based on current sentinel state.

    Shared helper for both ORB and sweep-bot so they check the same
    news/truth block flags without each bot re-implementing the read.
    """
    state = read_state("sentinel") or {}
    if state.get("news_block"):
        return True, state.get("block_reason") or "News block active"
    if state.get("truth_block"):
        return True, state.get("block_reason") or "Truth Social block active"
    return False, ""


# ─── Helpers ────────────────────────────────────────────────────

# Keywords that indicate BREAKING/URGENT events from news RSS headlines.
# Must be specific enough that a normal financial headline won't trigger them.
_NEWS_RSS_URGENT_KEYWORDS = [
    "trump announces", "trump signs", "executive order", "trump declares",
    "trump imposes", "new tariff", "tariff hike", "trade war", "sanctions",
    "fed cuts", "fed raises", "rate cut", "rate hike", "rate decision",
    "emergency declaration", "market halt", "circuit breaker", "flash crash",
    "bank run", "bank failure", "debt ceiling", "default", "shutdown",
    "recession confirmed", "gdp contraction",
]


def _classify_truth_impact(text: str, news_rss: bool = False) -> str:
    """Classify a post as HIGH_IMPACT or LOW_IMPACT.

    news_rss=True uses a stricter keyword list so routine financial
    headlines don't permanently trip the truth_block flag.
    """
    text_lower = text.lower()
    keywords = _NEWS_RSS_URGENT_KEYWORDS if news_rss else TRUTH_HIGH_IMPACT_KEYWORDS
    for keyword in keywords:
        if keyword in text_lower:
            return "HIGH_IMPACT"
    return "LOW_IMPACT"


def _matched_keywords(text: str) -> list[str]:
    """Return which high-impact keywords matched."""
    text_lower = text.lower()
    return [kw for kw in TRUTH_HIGH_IMPACT_KEYWORDS if kw in text_lower]


def _strip_html(html: str) -> str:
    """Strip HTML tags from content."""
    return re.sub(r"<[^>]+>", "", html).strip()


def _parse_rfc2822(rfc_str: str, fallback: datetime) -> Optional[datetime]:
    """Parse RFC 2822 date from RSS pubDate (e.g. 'Mon, 14 Apr 2026 08:30:00 +0000')."""
    if not rfc_str:
        return fallback
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(rfc_str)
        return dt.astimezone(ET)
    except Exception:
        return fallback


def _parse_iso_time(iso_str: str) -> Optional[datetime]:
    """Parse ISO datetime string."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(ET)
    except (ValueError, TypeError):
        return None


def _parse_event_time(time_str: str) -> Optional[datetime]:
    """Parse a time string like '8:30am' into today's datetime."""
    if not time_str:
        return None
    now = datetime.now(ET)
    try:
        # Handle formats: "8:30am", "10:00am", "2:00pm"
        time_str = time_str.strip().lower()
        for fmt in ["%I:%M%p", "%I:%M %p", "%H:%M"]:
            try:
                t = datetime.strptime(time_str, fmt)
                return now.replace(hour=t.hour, minute=t.minute, second=0)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _is_near_session(time_str: str, now: datetime) -> bool:
    """Check if an event time is within 90 min of market open (9:30)."""
    event_time = _parse_event_time(time_str)
    if not event_time:
        return False
    open_time = now.replace(hour=9, minute=30, second=0)
    diff = abs((event_time - open_time).total_seconds()) / 60
    return diff <= 90


def _is_upcoming(time_str: str, now: datetime) -> bool:
    """Check if an event time is still upcoming (within 15 min)."""
    event_time = _parse_event_time(time_str)
    if not event_time:
        return False
    minutes_until = (event_time - now).total_seconds() / 60
    return 0 <= minutes_until <= 15


# ─── Official 2026 Calendar (BLS + Federal Reserve) ──────────
# These are the EXACT dates — no guessing. Updated once per year.
# Year-keyed dicts so the system works across year boundaries.

_CPI = {
    2026: {(1, 13), (2, 11), (3, 11), (4, 10), (5, 12), (6, 10),
           (7, 14), (8, 12), (9, 11), (10, 14), (11, 10), (12, 10)},
    # 2027: update when BLS publishes schedule (~October 2026)
    2027: set(),
}

_NFP = {
    2026: {(1, 9), (2, 6), (3, 6), (4, 3), (5, 8), (6, 5),
           (7, 2), (8, 7), (9, 4), (10, 2), (11, 6), (12, 4)},
    # 2027: update when BLS publishes schedule (~October 2026)
    2027: set(),
}

# FOMC statement day (day 2 of meeting, 2:00 PM ET)
_FOMC = {
    2026: {(1, 28), (3, 18), (4, 29), (6, 17), (7, 29), (9, 16), (10, 28), (12, 9)},
    # 2027: update when Fed publishes schedule
    2027: set(),
}


def _get_static_events(now: datetime) -> list[dict]:
    """Return known high-impact events from the official BLS/Fed calendar.

    Uses hard-coded dates — NOT guesswork. This is the fallback
    when Forex Factory returns 403 (which happens frequently).
    Year-aware: looks up dates by now.year.
    """
    year = now.year
    month = now.month
    day = now.day
    weekday = now.weekday()  # 0=Monday

    cpi_dates = _CPI.get(year, set())
    nfp_dates = _NFP.get(year, set())
    fomc_dates = _FOMC.get(year, set())

    if not cpi_dates and not nfp_dates and not fomc_dates:
        logger.error("No static economic calendar for year %d! Update sentinel.py", year)

    events = []

    if (month, day) in cpi_dates:
        events.append({
            "time": "8:30am",
            "event": "CPI — Consumer Price Index",
            "impact": "HIGH",
            "within_session_window": True,
        })

    if (month, day) in nfp_dates:
        events.append({
            "time": "8:30am",
            "event": "NFP — Non-Farm Payrolls",
            "impact": "HIGH",
            "within_session_window": True,
        })

    if (month, day) in fomc_dates:
        events.append({
            "time": "2:00pm",
            "event": "FOMC Statement + Rate Decision",
            "impact": "HIGH",
            "within_session_window": True,
        })

    # Thursday jobless claims (recurring, lower impact)
    if weekday == 3:
        events.append({
            "time": "8:30am",
            "event": "Initial Jobless Claims",
            "impact": "MEDIUM",
            "within_session_window": True,
        })

    return events
