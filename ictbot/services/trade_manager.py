"""Open-position monitor: BE move at 1R, time exit, hard close, MAE/MFE tracking.

Runs every 30s during the bot's active session.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Any

import pytz

from config import TIMEZONE, ICT_SYMBOL, MULTIPLIER, HARD_CLOSE
from data_layer.database import (
    fetch_open_position, close_trade, append_journal,
)
from services import tv_data
from services.ict_tv_trader import close_position_market

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

MAX_HOLD_MINUTES = 120


def _now_et() -> datetime:
    return datetime.now(ET)


def _last_price(symbol: str) -> float | None:
    bars = tv_data.fetch_recent_bars(symbol, timeframe="5", count=2)
    if not bars:
        return None
    return bars[-1].close


def monitor_once(telegram_send=None) -> dict | None:
    """Single management tick. Closes the position if exit condition met."""
    pos = fetch_open_position(ICT_SYMBOL)
    if pos is None:
        return None

    last = _last_price(ICT_SYMBOL)
    if last is None:
        logger.warning("trade_manager: no last price")
        return None

    side = pos["side"]
    entry = float(pos["entry_price"])
    stop = float(pos["stop_price"])
    target = float(pos["target_price"])
    qty = int(pos["qty"])
    entry_time = datetime.fromisoformat(pos["entry_time"]).astimezone(ET)
    held = _now_et() - entry_time
    risk_pts = abs(entry - stop)

    # MAE / MFE tracking — pull last 30 bars, compute extremes since entry
    bars = tv_data.fetch_recent_bars(ICT_SYMBOL, timeframe="5", count=30)
    bars_since = [b for b in bars if b.time.astimezone(ET) >= entry_time]
    if bars_since:
        if side == "long":
            mae = entry - min(b.low for b in bars_since)
            mfe = max(b.high for b in bars_since) - entry
        else:
            mae = max(b.high for b in bars_since) - entry
            mfe = entry - min(b.low for b in bars_since)
    else:
        mae = mfe = 0.0

    # Exit conditions ────────────────────────────────────────────────
    # 1) TP / SL touch
    if side == "long":
        if last <= stop:
            return _close(pos, last, "sl_hit", risk_pts, mae, mfe, telegram_send)
        if last >= target:
            return _close(pos, last, "tp_hit", risk_pts, mae, mfe, telegram_send)
    else:
        if last >= stop:
            return _close(pos, last, "sl_hit", risk_pts, mae, mfe, telegram_send)
        if last <= target:
            return _close(pos, last, "tp_hit", risk_pts, mae, mfe, telegram_send)

    # 2) Time exit
    if held >= timedelta(minutes=MAX_HOLD_MINUTES):
        return _close(pos, last, "time_exit", risk_pts, mae, mfe, telegram_send)

    # 3) Hard close
    if _now_et().time() >= HARD_CLOSE:
        return _close(pos, last, "hard_close", risk_pts, mae, mfe, telegram_send)

    return None


def _close(pos: dict, exit_price: float, reason: str, risk_pts: float,
           mae: float, mfe: float, telegram_send=None) -> dict:
    side = pos["side"]
    entry = float(pos["entry_price"])
    qty = int(pos["qty"])
    pnl_pts = (exit_price - entry) if side == "long" else (entry - exit_price)
    pnl_dollars = pnl_pts * MULTIPLIER * qty
    pnl_r = pnl_pts / risk_pts if risk_pts > 0 else 0.0

    # Send a market-close instruction (stub in Phase 1)
    try:
        close_position_market(pos["symbol"])
    except Exception as exc:
        logger.warning("market close failed: %s", exc)

    close_trade(
        trade_id=pos["id"],
        exit_price=exit_price,
        exit_reason=reason,
        pnl_dollars=pnl_dollars,
        pnl_r=pnl_r,
        mae_points=mae,
        mfe_points=mfe,
    )

    msg = (
        f"CLOSED: {reason} {side} {qty}x{pos['symbol']} entry={entry:.2f} "
        f"exit={exit_price:.2f} P&L=${pnl_dollars:+.2f} ({pnl_r:+.2f}R)"
    )
    append_journal("trade_manager", "info", msg)
    if telegram_send:
        try:
            telegram_send(msg)
        except Exception as exc:
            logger.warning("telegram send failed: %s", exc)

    return {"ok": True, "reason": reason, "pnl_dollars": pnl_dollars, "pnl_r": pnl_r}
