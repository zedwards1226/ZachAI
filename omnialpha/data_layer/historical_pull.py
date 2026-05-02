"""Bulk historical data ingest. Pulls settled markets from Kalshi's public
/historical/* endpoints and upserts into our SQLite store. The bot reads
from this when backtesting; the dashboard reads from this for charts.

Re-runnable: re-pulling the same series + window UPSERTS, doesn't dupe.

Usage from CLI (see omnialpha/cli.py):
    python cli.py pull-historical --series KXBTC15M --days 30
    python cli.py pull-historical --series KXNBAGAME --days 7
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bots.kalshi_public import (
    iter_historical_markets,
    market_row_from_api,
    get_cutoff,
)
from data_layer.database import get_conn, init_db

logger = logging.getLogger(__name__)


def upsert_market(conn, row: dict[str, Any]) -> bool:
    """Insert or update a markets row. Returns True if newly inserted, False if updated.

    Strategy: try INSERT; if it conflicts on ticker PRIMARY KEY, fall back to
    UPDATE preserving first_seen_at. This is more readable than ON CONFLICT
    DO UPDATE clause and behaves identically for our needs.
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO markets (
            ticker, event_ticker, series_ticker, sector, title,
            open_time, close_time, expiration_time,
            market_type, strike_type, floor_strike, cap_strike,
            status, result, settlement_value_dollars,
            final_yes_ask_dollars, final_no_ask_dollars,
            volume_fp, open_interest_fp,
            raw_json, first_seen_at, last_updated_at
        ) VALUES (
            :ticker, :event_ticker, :series_ticker, :sector, :title,
            :open_time, :close_time, :expiration_time,
            :market_type, :strike_type, :floor_strike, :cap_strike,
            :status, :result, :settlement_value_dollars,
            :final_yes_ask_dollars, :final_no_ask_dollars,
            :volume_fp, :open_interest_fp,
            :raw_json, :first_seen_at, :last_updated_at
        )
        """,
        row,
    )
    if cur.rowcount > 0:
        return True

    # Already exists — update fields that may have changed (status, result,
    # settlement, prices) but preserve first_seen_at.
    conn.execute(
        """
        UPDATE markets SET
            event_ticker = :event_ticker,
            series_ticker = :series_ticker,
            sector = :sector,
            title = :title,
            open_time = :open_time,
            close_time = :close_time,
            expiration_time = :expiration_time,
            market_type = :market_type,
            strike_type = :strike_type,
            floor_strike = :floor_strike,
            cap_strike = :cap_strike,
            status = :status,
            result = :result,
            settlement_value_dollars = :settlement_value_dollars,
            final_yes_ask_dollars = :final_yes_ask_dollars,
            final_no_ask_dollars = :final_no_ask_dollars,
            volume_fp = :volume_fp,
            open_interest_fp = :open_interest_fp,
            raw_json = :raw_json,
            last_updated_at = :last_updated_at
        WHERE ticker = :ticker
        """,
        row,
    )
    return False


def pull_historical_markets(
    *,
    series_ticker: str | None = None,
    days: int = 30,
    max_pages: int | None = None,
) -> dict[str, int]:
    """Pull settled markets for a series across the last N days, upsert into SQLite.

    Returns counts: {pulled, inserted, updated, by_sector_*}.
    """
    init_db()  # safe to call repeatedly

    cutoff = get_cutoff()
    cutoff_ts = cutoff.get("market_settled_ts", "")
    logger.info("Kalshi historical cutoff: %s", cutoff_ts)

    # Window: from N days before cutoff back through cutoff (since data is
    # ~2 months lagged, "the last N days" of historical means N days
    # ending at the cutoff timestamp).
    try:
        end_dt = datetime.fromisoformat(cutoff_ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        end_dt = datetime.now(timezone.utc) - timedelta(days=60)
    start_dt = end_dt - timedelta(days=days)
    min_close = start_dt.isoformat().replace("+00:00", "Z")
    max_close = end_dt.isoformat().replace("+00:00", "Z")

    pulled = inserted = updated = 0
    by_sector: dict[str, int] = {}
    with get_conn() as conn:
        for raw in iter_historical_markets(
            series_ticker=series_ticker,
            min_close_ts=min_close,
            max_close_ts=max_close,
            max_pages=max_pages,
        ):
            row = market_row_from_api(raw)
            is_new = upsert_market(conn, row)
            pulled += 1
            if is_new:
                inserted += 1
            else:
                updated += 1
            by_sector[row["sector"]] = by_sector.get(row["sector"], 0) + 1
            if pulled % 500 == 0:
                logger.info("pulled=%d inserted=%d updated=%d", pulled, inserted, updated)
                conn.commit()  # incremental commit so progress is durable

    return {
        "pulled": pulled,
        "inserted": inserted,
        "updated": updated,
        "window_start": min_close,
        "window_end": max_close,
        **{f"sector_{k}": v for k, v in by_sector.items()},
    }
