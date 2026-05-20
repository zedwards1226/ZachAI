"""DAILY P&L GUARD — real-time profit/loss lock.

Phase 0.5 addition (2026-05-19). Zach was up $200 then down -$700 today; the
existing daily-loss gate only sees REALIZED P&L from closed trades, so an
open runner can swing the day after the gate has already cleared the entry.

This module computes realized + unrealized P&L every monitor tick and
force-flats any open runner if today's total crosses either threshold:

  +DAILY_PROFIT_TARGET_DOLLARS  → lock the gain, exit runner
  -DAILY_LOSS_LIMIT_DOLLARS     → lock the loss, exit runner

With MAX_TRADES_PER_SESSION=1 the entry-blocking side is moot (the day
gets one shot regardless), so this module only deals with the runner-exit
half. The lock state is held in memory and resets at the next 9:30 ET poll
(via reset_for_new_session).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pytz

from config import (
    TIMEZONE, MULTIPLIER, SLIPPAGE_PTS,
    DAILY_PROFIT_TARGET_DOLLARS, DAILY_LOSS_LIMIT_DOLLARS,
)
from agents import journal

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


# In-memory lock — flipped True when guard fires, cleared by reset_for_new_session.
# Kept module-local so tv_trader can short-circuit further runner work after fire.
_lock_state: dict = {"locked": False, "reason": None, "fired_at": None, "pnl_at_fire": 0.0}


def reset_for_new_session() -> None:
    """Clear lock at session start. Called from combiner on first poll of the day."""
    global _lock_state
    if _lock_state["locked"]:
        logger.info("Daily P&L guard reset for new session (was locked: %s at $%.2f)",
                    _lock_state["reason"], _lock_state["pnl_at_fire"])
    _lock_state = {"locked": False, "reason": None, "fired_at": None, "pnl_at_fire": 0.0}


def is_locked() -> bool:
    return bool(_lock_state["locked"])


def lock_state() -> dict:
    return dict(_lock_state)


def unrealized_pnl(active_orders: dict, current_price: float) -> float:
    """Sum unrealized P&L (USD) across all currently open trades at current_price.

    Mirrors the bracket math in tv_trader: pts × MULTIPLIER, with SLIPPAGE_PTS
    deducted per side (entry + exit) to match journal accounting. The result is
    intentionally conservative — uses the same slippage haircut journal applies
    to closed trades so the guard fires on the SAME P&L figure Zach sees in
    Telegram and the dashboard.
    """
    total = 0.0
    for _, order in active_orders.items():
        direction = order.get("direction")
        entry = order.get("entry")
        if not direction or entry is None or current_price <= 0:
            continue
        if direction == "LONG":
            gross_pts = current_price - entry
        else:
            gross_pts = entry - current_price
        # Net of full round-trip slippage (entry side already eaten at place; exit haircut here)
        net_pts = gross_pts - SLIPPAGE_PTS
        total += net_pts * MULTIPLIER
    return total


def total_today_pnl(active_orders: dict, current_price: float) -> float:
    """Realized today (from journal) + unrealized (live runners)."""
    return journal.get_today_pnl() + unrealized_pnl(active_orders, current_price)


def check(active_orders: dict, current_price: float) -> Optional[tuple[str, float]]:
    """Evaluate the guard. Returns ('TARGET'|'STOP', total_pnl) if it just fired
    (and arms the lock), or None if no action needed.

    Idempotent: if already locked, returns None — the guard fires once per session.
    """
    global _lock_state
    if _lock_state["locked"]:
        return None
    total = total_today_pnl(active_orders, current_price)
    if total >= DAILY_PROFIT_TARGET_DOLLARS:
        _lock_state = {
            "locked": True, "reason": "TARGET",
            "fired_at": datetime.now(ET).isoformat(), "pnl_at_fire": total,
        }
        logger.warning("Daily PROFIT TARGET hit: $%.2f >= $%.2f — locking day",
                       total, DAILY_PROFIT_TARGET_DOLLARS)
        return ("TARGET", total)
    if total <= -DAILY_LOSS_LIMIT_DOLLARS:
        _lock_state = {
            "locked": True, "reason": "STOP",
            "fired_at": datetime.now(ET).isoformat(), "pnl_at_fire": total,
        }
        logger.warning("Daily LOSS STOP hit: $%.2f <= -$%.2f — locking day",
                       total, DAILY_LOSS_LIMIT_DOLLARS)
        return ("STOP", total)
    return None
