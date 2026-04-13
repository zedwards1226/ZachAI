"""JOURNAL AGENT — SQLite trade journal + weekly Telegram report.

Logs every trade to journal.db with full scoring metadata.
Sunday 7:00 AM: sends weekly performance report via Telegram.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

import pytz

from config import (
    JOURNAL_DB, TIMEZONE, SLIPPAGE_PTS, MULTIPLIER,
    ROLLING_WR_ALERT_THRESHOLD, STARTING_CAPITAL,
)
from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


@contextmanager
def get_conn():
    """Get a SQLite connection with WAL mode."""
    conn = sqlite3.connect(str(JOURNAL_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                time            TEXT NOT NULL,
                direction       TEXT NOT NULL,
                score           INTEGER NOT NULL,
                breakdown       TEXT NOT NULL,
                entry           REAL NOT NULL,
                stop            REAL,
                target_1        REAL,
                target_2        REAL,
                exit_price      REAL,
                outcome         TEXT DEFAULT 'OPEN',
                rr              REAL,
                pnl             REAL,
                pnl_after_slippage REAL,
                size            TEXT,
                orb_high        REAL,
                orb_low         REAL,
                orb_candle_direction TEXT,
                was_second_break INTEGER DEFAULT 0,
                vix_at_entry    REAL,
                rvol_at_entry   REAL,
                notes           TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                date            TEXT PRIMARY KEY,
                trades          INTEGER,
                wins            INTEGER,
                losses          INTEGER,
                total_pnl       REAL,
                avg_score       REAL,
                notes           TEXT
            )
        """)


def log_trade_open(direction: str, score: int, breakdown: dict,
                   entry: float, stop: float, target_1: float, target_2: float,
                   size: str, orb_high: float, orb_low: float,
                   orb_candle_dir: str, was_second_break: bool,
                   vix: Optional[float], rvol: Optional[float]) -> int:
    """Log a new trade entry. Returns the trade ID."""
    now = datetime.now(ET)
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO trades (date, time, direction, score, breakdown, entry, stop,
                                target_1, target_2, size, orb_high, orb_low,
                                orb_candle_direction, was_second_break,
                                vix_at_entry, rvol_at_entry, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
            direction, score, json.dumps(breakdown),
            entry, stop, target_1, target_2, size,
            orb_high, orb_low, orb_candle_dir,
            1 if was_second_break else 0,
            vix, rvol, now.isoformat(),
        ))
        trade_id = cur.lastrowid
        logger.info("Trade logged: id=%d, %s score=%d entry=%.2f", trade_id, direction, score, entry)
        return trade_id


def log_trade_close(trade_id: int, exit_price: float, outcome: str,
                    notes: str = "") -> dict:
    """Close a trade with exit price and outcome. Returns trade summary."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row:
            logger.error("Trade %d not found", trade_id)
            return {}

        entry = row["entry"]
        direction = row["direction"]
        stop = row["stop"]

        # Calculate P&L
        if direction == "LONG":
            pts = exit_price - entry
        else:
            pts = entry - exit_price

        pnl = pts * MULTIPLIER
        pnl_after_slip = (pts - SLIPPAGE_PTS) * MULTIPLIER

        # Calculate RR achieved
        risk = abs(entry - stop) if stop else 1
        rr = pts / risk if risk > 0 else 0

        conn.execute("""
            UPDATE trades SET exit_price = ?, outcome = ?, rr = ?,
                              pnl = ?, pnl_after_slippage = ?, notes = ?
            WHERE id = ?
        """, (exit_price, outcome, round(rr, 2),
              round(pnl, 2), round(pnl_after_slip, 2), notes, trade_id))

        return {
            "trade_id": trade_id,
            "direction": direction,
            "entry": entry,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "pnl_after_slippage": round(pnl_after_slip, 2),
            "outcome": outcome,
            "rr": round(rr, 2),
        }


def get_open_trades() -> list[dict]:
    """Get all currently open trades."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE outcome = 'OPEN' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_today_trades() -> list[dict]:
    """Get all trades from today."""
    today = datetime.now(ET).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE date = ? ORDER BY id", (today,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_today_stats() -> dict:
    """Get today's trade statistics."""
    trades = get_today_trades()
    closed = [t for t in trades if t["outcome"] != "OPEN"]
    wins = sum(1 for t in closed if t["outcome"] == "WIN")
    losses = sum(1 for t in closed if t["outcome"] == "LOSS")
    total_pnl = sum(t.get("pnl_after_slippage", 0) or 0 for t in closed)

    # Consecutive losses (from end)
    consec_losses = 0
    for t in reversed(closed):
        if t["outcome"] == "LOSS":
            consec_losses += 1
        else:
            break

    return {
        "total_trades": len(trades),
        "closed": len(closed),
        "open": len(trades) - len(closed),
        "wins": wins,
        "losses": losses,
        "total_pnl": round(total_pnl, 2),
        "consecutive_losses": consec_losses,
        "win_rate": wins / len(closed) if closed else 0,
    }


def get_weekly_trades(weeks_back: int = 1) -> list[dict]:
    """Get trades from the last N weeks."""
    cutoff = datetime.now(ET) - timedelta(weeks=weeks_back)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE date >= ? AND outcome != 'OPEN' ORDER BY date, time",
            (cutoff_str,)
        ).fetchall()
        return [dict(r) for r in rows]


async def weekly_report() -> bool:
    """Generate and send the weekly performance report via Telegram."""
    logger.info("Generating weekly report")
    trades = get_weekly_trades(1)

    if not trades:
        return await telegram.notify_weekly_report("No trades this week.")

    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = sum(1 for t in trades if t["outcome"] == "LOSS")
    scratches = total - wins - losses
    wr = wins / total if total else 0
    total_pnl = sum(t.get("pnl_after_slippage", 0) or 0 for t in trades)
    avg_rr = sum(t.get("rr", 0) or 0 for t in trades) / total if total else 0

    lines = [
        f"Trades: {total} (W: {wins} / L: {losses} / S: {scratches})",
        f"Win Rate: {wr:.0%}",
        f"Total P&L (after slippage): ${total_pnl:.2f}",
        f"Avg RR: {avg_rr:.1f}",
        "",
    ]

    # Score band analysis
    lines.append("<b>Win Rate by Score Band:</b>")
    for band_name, lo, hi in [("7+ (full)", 7, 99), ("5-6 (half)", 5, 6), ("<5 (skip)", -99, 4)]:
        band_trades = [t for t in trades if lo <= (t.get("score") or 0) <= hi]
        if band_trades:
            band_wins = sum(1 for t in band_trades if t["outcome"] == "WIN")
            band_wr = band_wins / len(band_trades)
            lines.append(f"  Score {band_name}: {band_wr:.0%} ({len(band_trades)} trades)")

    # Second break analysis
    second_break_trades = [t for t in trades if t.get("was_second_break")]
    first_break_trades = [t for t in trades if not t.get("was_second_break")]
    if second_break_trades:
        sb_wins = sum(1 for t in second_break_trades if t["outcome"] == "WIN")
        sb_wr = sb_wins / len(second_break_trades)
        lines.append(f"\n<b>Second Break WR:</b> {sb_wr:.0%} ({len(second_break_trades)} trades)")
    if first_break_trades:
        fb_wins = sum(1 for t in first_break_trades if t["outcome"] == "WIN")
        fb_wr = fb_wins / len(first_break_trades)
        lines.append(f"<b>First Break WR:</b> {fb_wr:.0%} ({len(first_break_trades)} trades)")

    # VIX regime analysis
    lines.append("\n<b>Win Rate by VIX Regime:</b>")
    for regime, lo, hi in [("< 15", 0, 15), ("15-25", 15, 25), ("> 25", 25, 100)]:
        vix_trades = [t for t in trades
                      if t.get("vix_at_entry") and lo <= t["vix_at_entry"] < hi]
        if vix_trades:
            vix_wins = sum(1 for t in vix_trades if t["outcome"] == "WIN")
            vix_wr = vix_wins / len(vix_trades)
            lines.append(f"  VIX {regime}: {vix_wr:.0%} ({len(vix_trades)} trades)")

    # Best and worst days
    from collections import defaultdict
    daily_pnl = defaultdict(float)
    for t in trades:
        daily_pnl[t["date"]] += t.get("pnl_after_slippage", 0) or 0

    if daily_pnl:
        best_day = max(daily_pnl, key=daily_pnl.get)
        worst_day = min(daily_pnl, key=daily_pnl.get)
        lines.append(f"\n<b>Best day:</b> {best_day} (${daily_pnl[best_day]:.2f})")
        lines.append(f"<b>Worst day:</b> {worst_day} (${daily_pnl[worst_day]:.2f})")

    # Rolling 20-trade win rate
    all_recent = get_weekly_trades(4)  # Last 4 weeks for rolling
    if len(all_recent) >= 20:
        last_20 = all_recent[-20:]
        rolling_wr = sum(1 for t in last_20 if t["outcome"] == "WIN") / 20
        lines.append(f"\n<b>Rolling 20-trade WR:</b> {rolling_wr:.0%}")
        if rolling_wr < ROLLING_WR_ALERT_THRESHOLD:
            lines.append("⚠️ Below 40% threshold — review parameters!")
            await telegram.notify_strategy_review(rolling_wr, 1)

    # Recommendation
    lines.append("\n<b>Recommendation:</b>")
    if wr >= 0.60:
        lines.append("Strategy performing well. Maintain current parameters.")
    elif wr >= 0.45:
        lines.append("Acceptable performance. Monitor next week.")
    else:
        lines.append("Below target. Consider raising score threshold or reviewing filters.")

    report = "\n".join(lines)
    return await telegram.notify_weekly_report(report)
