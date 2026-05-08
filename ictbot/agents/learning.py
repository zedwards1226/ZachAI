"""Nightly learning agent — Phase 1 placeholder.

Walks the last 30 days of trades + setups, computes hit rates per setup_name,
and writes a plain-text summary to the journal table. Phase 4 will add
parameter-tweak proposals.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytz

from config import TIMEZONE
from data_layer.database import get_connection, append_journal, DB_PATH

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


def run() -> dict:
    cutoff = (datetime.now(ET) - timedelta(days=30)).isoformat()
    with get_connection(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT setup_id, side, pnl_dollars, pnl_r, exit_reason "
            "FROM trades WHERE entry_time >= ? AND exit_time IS NOT NULL",
            (cutoff,),
        ).fetchall()
        setup_rows = conn.execute(
            "SELECT id, setup_name FROM setups WHERE detected_time >= ?",
            (cutoff,),
        ).fetchall()

    setup_map = {r["id"]: r["setup_name"] for r in setup_rows}
    by_setup: dict[str, list[float]] = {}
    for r in rows:
        name = setup_map.get(r["setup_id"], "unknown")
        by_setup.setdefault(name, []).append(r["pnl_dollars"] or 0.0)

    summary: dict[str, dict] = {}
    for name, pnls in by_setup.items():
        wins = sum(1 for p in pnls if p > 0)
        total = len(pnls)
        win_rate = wins / total if total else 0
        summary[name] = {
            "trades": total,
            "win_rate": round(win_rate, 3),
            "total_pnl": round(sum(pnls), 2),
        }

    append_journal(
        "learning", "info",
        f"30d summary: {summary}",
        payload=str(summary),
    )
    return summary
