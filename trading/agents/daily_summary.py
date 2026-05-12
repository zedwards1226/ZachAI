"""Daily cross-bot P&L summary — Telegram post at 4:15 PM ET.

Born from 2026-05-11: Zach had to manually ask "how we do today" to get
P&L because no automatic daily summary across the 3 bots existed.

Reads each bot's journal DB read-only (cross-bot read is fine per existing
pattern — no writes) and posts one consolidated message via the ORB
Telegram client. Wired into trading/main.py's APScheduler.

Bot DBs:
  - ORB:          C:\\ZachAI\\trading\\journal.db          (table: trades)
  - WeatherAlpha: C:\\ZachAI\\kalshi\\bots\\weatheralpha.db (table: trades)
  - OmniAlpha:    C:\\ZachAI\\omnialpha\\state\\omnialpha.db (table: trades)
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytz

from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

ORB_DB = Path(r"C:\ZachAI\trading\journal.db")
WA_DB = Path(r"C:\ZachAI\kalshi\bots\weatheralpha.db")
OA_DB = Path(r"C:\ZachAI\omnialpha\state\omnialpha.db")


def _week_start_iso() -> str:
    """ISO date string for the Monday of the current US trading week (ET).
    Zach trades Mon-Thu (Friday off), so the week starts Monday."""
    now = datetime.now(ET)
    # weekday(): Monday=0, Sunday=6
    days_since_monday = now.weekday()
    monday = now.date() - timedelta(days=days_since_monday)
    return monday.isoformat()


def _orb_stats(target_date: str, week_start: str) -> dict:
    """ORB schema uses date='YYYY-MM-DD' and pnl_after_slippage column."""
    if not ORB_DB.exists():
        return {"day_n": 0, "day_w": 0, "day_pnl": 0.0, "wtd_pnl": 0.0}
    with sqlite3.connect(str(ORB_DB)) as db:
        cur = db.cursor()
        d = cur.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(pnl_after_slippage), 0) "
            "FROM trades WHERE date=?", (target_date,)
        ).fetchone()
        w = cur.execute(
            "SELECT COALESCE(SUM(pnl_after_slippage), 0) "
            "FROM trades WHERE date >= ?", (week_start,)
        ).fetchone()
        return {
            "day_n": int(d[0] or 0),
            "day_w": int(d[1] or 0),
            "day_pnl": float(d[2] or 0),
            "wtd_pnl": float(w[0] or 0),
        }


def _wa_stats(target_date: str, week_start: str) -> dict:
    """WeatherAlpha schema uses timestamp='YYYY-MM-DDTHH:MM:SS...' ISO and
    status IN ('won','lost')."""
    if not WA_DB.exists():
        return {"day_n": 0, "day_w": 0, "day_pnl": 0.0, "wtd_pnl": 0.0}
    with sqlite3.connect(str(WA_DB)) as db:
        cur = db.cursor()
        d = cur.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(pnl_usd), 0) "
            "FROM trades WHERE substr(timestamp,1,10)=? "
            "AND status IN ('won','lost')",
            (target_date,)
        ).fetchone()
        w = cur.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) "
            "FROM trades WHERE substr(timestamp,1,10) >= ? "
            "AND status IN ('won','lost')",
            (week_start,)
        ).fetchone()
        return {
            "day_n": int(d[0] or 0),
            "day_w": int(d[1] or 0),
            "day_pnl": float(d[2] or 0),
            "wtd_pnl": float(w[0] or 0),
        }


def _oa_stats(target_date: str, week_start: str) -> dict:
    """OmniAlpha schema mirrors WeatherAlpha — timestamp ISO + status."""
    if not OA_DB.exists():
        return {"day_n": 0, "day_w": 0, "day_pnl": 0.0, "wtd_pnl": 0.0}
    with sqlite3.connect(str(OA_DB)) as db:
        cur = db.cursor()
        d = cur.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(pnl_usd), 0) "
            "FROM trades WHERE substr(timestamp,1,10)=? "
            "AND status IN ('won','lost')",
            (target_date,)
        ).fetchone()
        w = cur.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) "
            "FROM trades WHERE substr(timestamp,1,10) >= ? "
            "AND status IN ('won','lost')",
            (week_start,)
        ).fetchone()
        return {
            "day_n": int(d[0] or 0),
            "day_w": int(d[1] or 0),
            "day_pnl": float(d[2] or 0),
            "wtd_pnl": float(w[0] or 0),
        }


def _fmt_dollars(amt: float) -> str:
    sign = "+" if amt >= 0 else "-"
    return f"{sign}${abs(amt):.2f}"


def _build_message(date_str: str, orb: dict, wa: dict, oa: dict) -> str:
    """Markdown-formatted Telegram summary. Mirrors the answer style Claude
    used when Zach asked 'how we do today' on 2026-05-11."""
    day_total = orb["day_pnl"] + wa["day_pnl"] + oa["day_pnl"]
    wtd_total = orb["wtd_pnl"] + wa["wtd_pnl"] + oa["wtd_pnl"]

    # Header
    emoji = "🟢" if day_total >= 0 else "🔴"
    lines = [
        f"{emoji} *Daily P&L — {date_str}*",
        "",
    ]

    # Per-bot rows: only show stats if traded today
    def row(label: str, s: dict) -> str:
        if s["day_n"] == 0:
            return f"  {label}: no trades · WTD {_fmt_dollars(s['wtd_pnl'])}"
        wr = (s["day_w"] / s["day_n"] * 100) if s["day_n"] else 0
        return (f"  {label}: {s['day_n']} trades · {s['day_w']}W "
                f"({wr:.0f}% WR) · {_fmt_dollars(s['day_pnl'])}"
                f" · WTD {_fmt_dollars(s['wtd_pnl'])}")

    lines.append(row("ORB", orb))
    lines.append(row("WeatherAlpha", wa))
    lines.append(row("OmniAlpha", oa))
    lines.append("")
    lines.append(f"*Today total:* {_fmt_dollars(day_total)}")
    lines.append(f"*WTD total:* {_fmt_dollars(wtd_total)}")
    return "\n".join(lines)


async def run() -> None:
    """Build today's summary across the 3 bots and post to Telegram."""
    try:
        now_et = datetime.now(ET)
        date_str = now_et.strftime("%Y-%m-%d")
        week_start = _week_start_iso()

        orb = _orb_stats(date_str, week_start)
        wa = _wa_stats(date_str, week_start)
        oa = _oa_stats(date_str, week_start)

        msg = _build_message(date_str, orb, wa, oa)
        logger.info("Daily summary built: today=%s wtd=%s",
                    sum(s["day_pnl"] for s in (orb, wa, oa)),
                    sum(s["wtd_pnl"] for s in (orb, wa, oa)))
        await telegram.send(msg)
    except Exception as e:
        logger.error("Daily summary failed: %s", e, exc_info=True)
