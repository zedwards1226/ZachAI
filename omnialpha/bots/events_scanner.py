"""Live universe scanner — pulls active markets from Kalshi's authenticated
/markets endpoint, filters by enabled sectors, hands snapshots to strategies.

Used by the main loop in two ways:
  1. Periodic poll (every 60s): refresh universe, snapshot any market
     whose state has changed (new trade, price moved, volume threshold)
  2. On-demand scan: filtered view (e.g. only KXBTC15M closing in next 5 min)

For PAPER MODE / DRY RUN: this can run against /historical data when no
live credentials are available — useful for end-to-end smoke tests.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from bots.kalshi_public import (
    classify_sector,
    iter_historical_markets,
    market_row_from_api,
)
from data_layer.database import get_conn
from data_layer.historical_pull import upsert_market

logger = logging.getLogger(__name__)


def scan_recent_markets(
    *,
    series_ticker: Optional[str] = None,
    sector: Optional[str] = None,
    minutes: int = 60,
) -> Iterator[dict]:
    """Pull markets that closed within the last `minutes` minutes from the
    historical store. Used for paper-mode smoke testing (the 'live' loop
    actually replays history during dev).
    """
    cutoff_lower = (
        datetime.now(timezone.utc) - timedelta(minutes=minutes)
    ).isoformat().replace("+00:00", "Z")
    with get_conn(readonly=True) as conn:
        sql = (
            "SELECT * FROM markets "
            "WHERE close_time > ? "
        )
        params: list = [cutoff_lower]
        if series_ticker:
            sql += " AND series_ticker = ?"
            params.append(series_ticker)
        if sector:
            sql += " AND sector = ?"
            params.append(sector)
        sql += " ORDER BY close_time ASC"
        for row in conn.execute(sql, params):
            yield dict(row)


def refresh_historical(
    *,
    series_ticker: str,
    days: int = 1,
) -> int:
    """Pull recent settled markets into the DB. Idempotent."""
    n = 0
    cutoff_lower = (
        datetime.now(timezone.utc) - timedelta(days=days + 60)
    ).isoformat().replace("+00:00", "Z")
    cutoff_upper = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with get_conn() as conn:
        for raw in iter_historical_markets(
            series_ticker=series_ticker,
            min_close_ts=cutoff_lower,
            max_close_ts=cutoff_upper,
        ):
            upsert_market(conn, market_row_from_api(raw))
            n += 1
            if n % 500 == 0:
                conn.commit()
    return n
