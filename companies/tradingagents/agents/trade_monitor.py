"""
Trade Monitor Agent — Live position health tracking.
Runs on a polling loop while a trade is open.

Monitors:
1. Unrealized P&L and distance to stop/target
2. Adverse move alerts (drawdown exceeds threshold)
3. Time stop (trade open too long without hitting target)
4. Session end warning (approaching 4:00 PM ET close)

Uses TradingView MCP quote_get for live price when available.
Sends Telegram warnings on concerning conditions.
"""
import logging
from datetime import datetime

import pytz

import config
import database as db

log = logging.getLogger("trade_monitor")

# ── Thresholds ──
ADVERSE_MOVE_PTS = 20      # alert if unrealized loss exceeds this many points
TIME_STOP_MINUTES = 90     # alert if trade open longer than this
SESSION_END_WARN_MINUTES = 15  # warn this many minutes before session end


def check_open_trades(current_prices: dict = None) -> list[dict]:
    """
    Check health of all open trades.
    current_prices: optional dict of {symbol: price} from live data.
    Returns list of warning dicts.
    """
    open_trades = db.get_open_trades()
    if not open_trades:
        return []

    warnings = []
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)

    for t in open_trades:
        trade_warnings = []

        # Check unrealized P&L if we have current price
        if current_prices and t["symbol"] in current_prices:
            current = current_prices[t["symbol"]]
            if t["side"] == "BUY":
                unrealized_pts = current - t["entry"]
            else:
                unrealized_pts = t["entry"] - current

            unrealized_pnl = unrealized_pts * t["multiplier"] * t["qty"]

            if unrealized_pts < -ADVERSE_MOVE_PTS:
                trade_warnings.append(
                    f"ADVERSE MOVE: {unrealized_pts:+.2f} pts (${unrealized_pnl:+,.2f})"
                )

        # Check time in trade
        try:
            opened = datetime.fromisoformat(t["opened_at"])
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=pytz.utc)
            elapsed_min = (now.astimezone(pytz.utc) - opened.astimezone(pytz.utc)).total_seconds() / 60

            if elapsed_min > TIME_STOP_MINUTES:
                trade_warnings.append(
                    f"TIME STOP: open {elapsed_min:.0f} min (>{TIME_STOP_MINUTES} min threshold)"
                )
        except (ValueError, TypeError):
            pass

        # Check session end proximity
        session_end = now.replace(hour=config.SESSION_END_HOUR,
                                  minute=config.SESSION_END_MINUTE, second=0)
        minutes_to_close = (session_end - now).total_seconds() / 60
        if 0 < minutes_to_close <= SESSION_END_WARN_MINUTES:
            trade_warnings.append(
                f"SESSION END: {minutes_to_close:.0f} min to close — consider EOD exit"
            )

        if trade_warnings:
            warning = {
                "trade_id": t["id"],
                "symbol": t["symbol"],
                "side": t["side"],
                "entry": t["entry"],
                "warnings": trade_warnings,
            }
            warnings.append(warning)
            log.info("Trade #%d %s %s: %s",
                     t["id"], t["side"], t["symbol"], "; ".join(trade_warnings))

    return warnings
