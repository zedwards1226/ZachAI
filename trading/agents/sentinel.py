"""SENTINEL AGENT — Economic calendar + Truth Social monitoring.

Initial run at 8:00 AM ET: fetch today's economic events and recent Truth Social posts.
Continuous polling every 60 seconds during session: re-check Truth Social for new posts.
Sets NEWS_BLOCK and TRUTH_BLOCK flags. Sends Telegram alert on high-impact detection.
Writes output to state/sentinel.json.
"""
from __future__ import annotations

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
    """Fetch recent posts from Truth Social @realDonaldTrump."""
    posts = []
    now = datetime.now(ET)

    try:
        http = _get_http()

        # Try Truth Social API endpoint (public timeline)
        url = "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses?limit=20"
        resp = await http.get(url, headers={"Accept": "application/json"})

        if resp.status_code == 200:
            data = resp.json()
            for item in data:
                text = _strip_html(item.get("content", ""))
                created = item.get("created_at", "")
                post_time = _parse_iso_time(created)
                age_min = (now - post_time).total_seconds() / 60 if post_time else 999

                # Only look at last 12 hours
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

            return posts, "OK"

        # Fallback: try scraping the public profile page
        logger.info("Truth Social API returned %d, trying profile page", resp.status_code)
        resp2 = await http.get("https://truthsocial.com/@realDonaldTrump")
        if resp2.status_code == 200:
            soup = BeautifulSoup(resp2.text, "html.parser")
            # Look for status content in the HTML
            status_els = soup.select("[class*='status-content'], [class*='status__content']")
            for i, el in enumerate(status_els[:20]):
                text = el.get_text(strip=True)
                if not text:
                    continue
                impact = _classify_truth_impact(text)
                posts.append({
                    "id": f"scraped_{i}",
                    "time": now.isoformat(),
                    "text": text[:300],
                    "impact": impact,
                    "keywords_matched": _matched_keywords(text),
                    "age_minutes": 0,  # Unknown age from scrape
                })
            return posts, "SCRAPED"

    except Exception as e:
        logger.warning("Failed to fetch Truth Social: %s", e)

    return posts, "UNAVAILABLE"


# ─── Helpers ────────────────────────────────────────────────────

def _classify_truth_impact(text: str) -> str:
    """Classify a Truth Social post as HIGH_IMPACT or LOW_IMPACT."""
    text_lower = text.lower()
    for keyword in TRUTH_HIGH_IMPACT_KEYWORDS:
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


def _get_static_events(now: datetime) -> list[dict]:
    """Return known recurring high-impact events as fallback."""
    weekday = now.weekday()  # 0=Monday
    day = now.day
    month = now.month

    events = []

    # FOMC: 8 times per year, usually Wednesday
    # NFP: first Friday of month
    # CPI: ~12th of each month

    if weekday == 4 and day <= 7:
        events.append({
            "time": "8:30am",
            "event": "Non-Farm Payrolls (NFP)",
            "impact": "HIGH",
            "within_session_window": True,
        })

    # CPI: typically 2nd Tuesday or Wednesday of month (10th-15th range)
    # Only flag as HIGH when ForexFactory is unavailable AND it's a Tue/Wed in range
    if 10 <= day <= 15 and weekday in (1, 2):  # Tuesday or Wednesday only
        events.append({
            "time": "8:30am",
            "event": "CPI (estimated — verify manually)",
            "impact": "HIGH",
            "within_session_window": True,
        })

    # Thursday jobless claims
    if weekday == 3:
        events.append({
            "time": "8:30am",
            "event": "Initial Jobless Claims",
            "impact": "MEDIUM",
            "within_session_window": True,
        })

    return events
