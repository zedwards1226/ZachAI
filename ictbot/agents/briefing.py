"""Morning briefing agent — fires at 07:00 ET with yesterday's results + today's plan."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytz

from config import TIMEZONE, ICT_SYMBOL, is_high_impact_today
from services import telegram, tv_data
from services.tv_data import htf_bias
from data_layer.database import fetch_recent_trades, equity_curve

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


def run() -> None:
    today = datetime.now(ET).date()
    yesterday = today - timedelta(days=1)

    trades = fetch_recent_trades(50)
    y_iso = yesterday.isoformat()
    y_trades = [t for t in trades if (t.get("entry_time") or "")[:10] == y_iso]
    y_pnl = sum((t.get("pnl_dollars") or 0.0) for t in y_trades)
    y_wins = sum(1 for t in y_trades if (t.get("pnl_dollars") or 0.0) > 0)
    y_losses = sum(1 for t in y_trades if (t.get("pnl_dollars") or 0.0) < 0)

    bias = htf_bias(ICT_SYMBOL)
    high_impact, event = is_high_impact_today(today.isoformat())

    cum = equity_curve()
    eq = cum[-1][1] if cum else 0.0

    lines = [
        f"morning briefing — {today.isoformat()}",
        f"yesterday: {y_wins}W/{y_losses}L  P&L=${y_pnl:+.2f}",
        f"cumulative paper P&L: ${eq:+.2f}",
        f"HTF bias on {ICT_SYMBOL}: {bias}",
    ]
    if high_impact:
        lines.append(f"⚠ high-impact day: {event} — bot will sit out")
    else:
        lines.append("no scheduled high-impact news")

    telegram.send("\n".join(lines))
