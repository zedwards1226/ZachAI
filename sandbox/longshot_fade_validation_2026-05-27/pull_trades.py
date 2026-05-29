"""Pull executed trades for the 4 sport series in the validation window.

We need TRADE-LEVEL data (not market-level) because market `last_price_dollars`
is the post-settlement price (always 0.01 or 0.99). To test Becker's edge, we
need prices that printed *during the game* when retail was betting.

Strategy:
  1. For each settled market in markets.db that's in our 4 sport series,
     pull all trades via `/historical/trades?ticker=...`.
  2. Filter client-side to longshot band: YES price 1-15¢ (= NO price 85-99¢).
  3. Persist only the filtered trades — drops 80%+ of data we don't need.

This is the heavier of the two pulls. Skip markets whose ticker doesn't
match KXNBA/KXNFL/KXEPL/KXUFC prefixes (in case markets.db ever picks up
extras). Each trade row gets the market's eventual result joined in for
fast downstream analysis.

Idempotent: `(market_ticker, trade_created_ts, yes_price_dollars)` is the
unique key. Re-runs upsert without duplicating.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "longshot"))
from bots.kalshi_public import iter_historical_trades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_PATH = HERE / "db" / "markets.db"

# Becker's longshot fade band — NO price 85¢ to 99¢, i.e. YES price 1-15¢.
YES_PRICE_MIN_C = 1   # inclusive
YES_PRICE_MAX_C = 15  # inclusive
SERIES_PREFIXES = ("KXNBA", "KXNFL", "KXEPL", "KXUFC")

# Trades-pull sample size per series. 200 markets × 3-4 series → 600-800
# markets to pull trades for. With Kalshi's paginated trades endpoint at
# 1000 trades/page and 200ms inter-page delay, this completes in ~5-15 min
# depending on per-market trade depth. Sampling (vs full census) is fine
# because each market is already a real data point — we don't need the
# entire universe to get statistically significant per-bucket counts.
SAMPLE_PER_SERIES = 200


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    market_ticker      TEXT,
    created_time       TEXT,
    yes_price_cents    INTEGER,
    no_price_cents     INTEGER,
    count              INTEGER,
    taker_side         TEXT,
    market_result      TEXT,    -- joined from markets table
    series_ticker      TEXT,    -- joined for fast filtering
    PRIMARY KEY (market_ticker, created_time, yes_price_cents)
);
CREATE INDEX IF NOT EXISTS idx_trades_series ON trades(series_ticker);
CREATE INDEX IF NOT EXISTS idx_trades_no_price ON trades(no_price_cents);
CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(market_result);
"""

UPSERT_SQL = """
INSERT INTO trades (
    market_ticker, created_time, yes_price_cents, no_price_cents,
    count, taker_side, market_result, series_ticker
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(market_ticker, created_time, yes_price_cents) DO UPDATE SET
    count = excluded.count,
    taker_side = excluded.taker_side,
    market_result = excluded.market_result,
    series_ticker = excluded.series_ticker;
"""


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    return conn


def _market_universe(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Returns (market_ticker, series_ticker, result) for every settled sport
    market in markets.db. Filtered to our 4 series, then RANDOM SAMPLE per
    series to keep pull time bounded (see SAMPLE_PER_SERIES)."""
    placeholders = " OR ".join(["series_ticker LIKE ?"] * len(SERIES_PREFIXES))
    sql = (
        f"SELECT ticker, series_ticker, result FROM markets "
        f"WHERE result IN ('yes','no') AND ({placeholders}) "
        f"ORDER BY series_ticker, RANDOM()"
    )
    params = [f"{p}%" for p in SERIES_PREFIXES]
    rows = list(conn.execute(sql, params))
    # Limit per series — deterministic with seed not needed, RANDOM() above
    # gives statistical sample.
    out: list[tuple[str, str, str]] = []
    counts: dict[str, int] = {}
    for r in rows:
        series = r[1] or ""
        if counts.get(series, 0) >= SAMPLE_PER_SERIES:
            continue
        out.append(r)
        counts[series] = counts.get(series, 0) + 1
    return out


def _yes_cents(t: dict) -> int | None:
    """Trade payload reports yes_price_dollars as a string like '0.05'."""
    v = t.get("yes_price_dollars")
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(round(f * 100))
    except (TypeError, ValueError):
        return None


def pull_trades_for_market(
    conn: sqlite3.Connection,
    market_ticker: str,
    series_ticker: str,
    result: str,
) -> tuple[int, int]:
    """Pull all trades for one market. Return (seen, kept_in_band)."""
    batch: list[tuple] = []
    seen = 0
    kept = 0
    for t in iter_historical_trades(market_ticker=market_ticker):
        seen += 1
        yes_c = _yes_cents(t)
        if yes_c is None:
            continue
        # Filter: longshot fade band (YES 1-15¢ = NO 85-99¢)
        if yes_c < YES_PRICE_MIN_C or yes_c > YES_PRICE_MAX_C:
            continue
        kept += 1
        no_c = 100 - yes_c
        batch.append((
            market_ticker,
            t.get("created_time") or t.get("yes_trade_created_time"),
            yes_c,
            no_c,
            int(t.get("count") or 0),
            t.get("taker_side"),
            result,
            series_ticker,
        ))
        if len(batch) >= 500:
            conn.executemany(UPSERT_SQL, batch)
            conn.commit()
            batch.clear()
    if batch:
        conn.executemany(UPSERT_SQL, batch)
        conn.commit()
    return seen, kept


def main() -> int:
    conn = _init_db()
    universe = _market_universe(conn)
    if not universe:
        log.error("no settled sport markets in markets.db — run pull_markets.py first")
        return 2

    log.info("pulling trades for %d settled sport markets", len(universe))
    total_seen = 0
    total_kept = 0
    started = datetime.now(timezone.utc)

    for i, (ticker, series, result) in enumerate(universe, 1):
        try:
            seen, kept = pull_trades_for_market(conn, ticker, series, result)
        except Exception as e:
            log.error("  %s failed: %s", ticker, e)
            continue
        total_seen += seen
        total_kept += kept
        if i % 25 == 0 or i == len(universe):
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            rate = i / max(elapsed, 0.1)
            eta_s = (len(universe) - i) / max(rate, 0.001)
            log.info(
                "  %d/%d markets (%.1f/s) — seen=%d kept=%d ETA=%.0fs",
                i, len(universe), rate, total_seen, total_kept, eta_s,
            )

    log.info("=" * 50)
    log.info("TRADES PULL COMPLETE")
    log.info("  markets processed: %d", len(universe))
    log.info("  trades seen:       %d", total_seen)
    log.info("  trades kept (NO band 85-99¢): %d", total_kept)
    log.info("  drop rate: %.1f%%", 100 * (1 - total_kept / max(total_seen, 1)))
    log.info("  DB: %s", DB_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
