"""Morning Preflight Agent.

Runs at 7:00 AM ET. Verifies the full stack is ready before the 9:30 open:
  - TradingView CDP reachable
  - CDP symbol locked to DEFAULT_SYMBOL
  - Today's high-impact economic events (CPI/NFP/FOMC)
  - Disk space on C:
  - Journal DB healthy
  - Quote pull sanity check

Sends Telegram brief with PASS/FAIL checklist.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

import pytz

from config import DEFAULT_SYMBOL, JOURNAL_DB, TIMEZONE
from services import telegram
from services.tv_client import get_client

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# 2026 High-impact calendar (from CLAUDE.md)
CPI_DATES = {"2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10", "2026-05-12",
             "2026-06-10", "2026-07-14", "2026-08-12", "2026-09-11", "2026-10-14",
             "2026-11-10", "2026-12-10"}
NFP_DATES = {"2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03", "2026-05-08",
             "2026-06-05", "2026-07-02", "2026-08-07", "2026-09-04", "2026-10-02",
             "2026-11-06", "2026-12-04"}
FOMC_DATES = {"2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
              "2026-09-16", "2026-10-28", "2026-12-09"}


async def _check_cdp_and_symbol() -> tuple[bool, str]:
    try:
        tv = await get_client()
        symbol = await tv.get_symbol()
        if symbol != DEFAULT_SYMBOL:
            return False, f"CDP symbol is {symbol}, expected {DEFAULT_SYMBOL}"
        return True, f"CDP locked on {symbol}"
    except Exception as e:
        return False, f"CDP check failed: {e}"


async def _check_quote() -> tuple[bool, str]:
    try:
        tv = await get_client()
        q = await tv.get_quote()
        price = q.get("last") or q.get("close", 0)
        if price > 0:
            return True, f"Quote pull OK — last={price}"
        return False, "Quote pull returned 0"
    except Exception as e:
        return False, f"Quote pull failed: {e}"


def _check_calendar() -> tuple[bool, str]:
    today = datetime.now(ET).strftime("%Y-%m-%d")
    events = []
    if today in CPI_DATES:
        events.append("CPI 8:30 AM")
    if today in NFP_DATES:
        events.append("NFP 8:30 AM")
    if today in FOMC_DATES:
        events.append("FOMC 2:00 PM")
    if events:
        return True, f"⚠️ High-impact today: {', '.join(events)}"
    return True, "No high-impact events today"


def _check_disk() -> tuple[bool, str]:
    try:
        total, used, free = shutil.disk_usage("C:\\")
        free_gb = free / 1e9
        if free_gb < 5:
            return False, f"Low disk: {free_gb:.1f} GB free on C:"
        return True, f"Disk OK: {free_gb:.0f} GB free"
    except Exception as e:
        return False, f"Disk check failed: {e}"


def _check_journal_db() -> tuple[bool, str]:
    if not JOURNAL_DB.exists():
        return False, "journal.db missing"
    size_mb = JOURNAL_DB.stat().st_size / 1e6
    return True, f"journal.db {size_mb:.1f} MB"


async def run() -> None:
    """Execute preflight and send Telegram brief."""
    logger.info("Morning preflight starting")

    calendar_ok, calendar_msg = _check_calendar()
    disk_ok, disk_msg = _check_disk()
    journal_ok, journal_msg = _check_journal_db()
    cdp_ok, cdp_msg = await _check_cdp_and_symbol()
    quote_ok, quote_msg = await _check_quote()

    checks = [
        ("CDP/symbol", cdp_ok, cdp_msg),
        ("quote pull", quote_ok, quote_msg),
        ("calendar", calendar_ok, calendar_msg),
        ("disk space", disk_ok, disk_msg),
        ("journal DB", journal_ok, journal_msg),
    ]

    all_ok = all(ok for _, ok, _ in checks)
    now = datetime.now(ET).strftime("%H:%M %Z")

    lines = [
        f"{'🟢' if all_ok else '🟡'} <b>Morning Preflight</b> — {now}",
        "",
    ]
    for name, ok, msg in checks:
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} {name}: {msg}")
    lines.append("")
    lines.append("Open: 9:30 AM ET" if all_ok else "⚠️ Fix failed checks before open")

    brief = "\n".join(lines)
    await telegram.send(brief)
    logger.info("Preflight complete — all_ok=%s", all_ok)
