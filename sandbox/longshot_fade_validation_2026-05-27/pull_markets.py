"""Pull 30 days of settled sports markets via Kalshi `/historical/markets`.

Sports series targeted (highest-volume retail-driven categories per the
research brief at C:\\Users\\zedwa\\.claude\\plans\\greedy-shimmying-hamster.md):
  - KXNBAGAME (NBA games)
  - KXNFLGAME (NFL — likely sparse, off-season Feb-Mar)
  - KXEPLGAME (Premier League)
  - KXUFC (UFC)

Data window:
  Kalshi `/historical/cutoff` is ~60 days stale. As of 2026-05-27 the cutoff
  is 2026-03-28. We pull 30 days back from there: 2026-02-26 → 2026-03-28.

Persistence:
  Local SQLite at db/markets.db. Re-runs are idempotent (INSERT OR REPLACE).
  Sandbox isolation: never writes to production DBs (per sandbox/CLAUDE.md
  rule 2).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Sandbox rule 3 says "no importing live code" but omnialpha is now a
# shared library (CLAUDE.md rewritten 2026-05-27). kalshi_public.py is
# a pure HTTP puller with no scheduler/agent side effects, so it's safe.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "longshot"))
from bots.kalshi_public import iter_historical_markets, get_cutoff

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_PATH = HERE / "db" / "markets.db"

SERIES = ["KXNBAGAME", "KXNFLGAME", "KXEPLGAME", "KXUFC"]
WINDOW_DAYS = 30


SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    ticker             TEXT PRIMARY KEY,
    series_ticker      TEXT,
    event_ticker       TEXT,
    title              TEXT,
    open_time          TEXT,
    close_time         TEXT,
    status             TEXT,
    result             TEXT,
    last_yes_dollars   REAL,
    volume_fp          REAL,
    open_interest_fp   REAL,
    raw_json           TEXT,
    pulled_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_close ON markets(series_ticker, close_time);
CREATE INDEX IF NOT EXISTS idx_result ON markets(result);
"""

UPSERT_SQL = """
INSERT INTO markets (
    ticker, series_ticker, event_ticker, title, open_time, close_time,
    status, result, last_yes_dollars, volume_fp, open_interest_fp,
    raw_json, pulled_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ticker) DO UPDATE SET
    status = excluded.status,
    result = excluded.result,
    last_yes_dollars = excluded.last_yes_dollars,
    volume_fp = excluded.volume_fp,
    open_interest_fp = excluded.open_interest_fp,
    raw_json = excluded.raw_json,
    pulled_at = excluded.pulled_at;
"""


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    return conn


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _series_from_ticker(ticker: str) -> str | None:
    """Kalshi market tickers are SERIES-EVENT-MARKET. Series is the prefix
    before the first '-'. e.g. 'KXNBAGAME-26MAR26NOPDET-NOP' → 'KXNBAGAME'."""
    if not ticker or "-" not in ticker:
        return None
    return ticker.split("-", 1)[0]


def _normalize(m: dict) -> tuple:
    last_yes = _safe_float(m.get("last_price_dollars"))
    ticker = m.get("ticker", "")
    return (
        ticker,
        m.get("series_ticker") or _series_from_ticker(ticker),
        m.get("event_ticker"),
        m.get("title") or m.get("yes_sub_title"),
        m.get("open_time"),
        m.get("close_time"),
        m.get("status"),
        m.get("result"),
        last_yes,
        _safe_float(m.get("volume_fp")),
        _safe_float(m.get("open_interest_fp")),
        json.dumps(m),
        datetime.now(timezone.utc).isoformat(),
    )


def pull_series(conn: sqlite3.Connection, series: str,
                min_close_ts: str, max_close_ts: str) -> int:
    """Pull every settled market in the window for one series. Returns count."""
    log.info("pulling %s (%s → %s)", series, min_close_ts[:10], max_close_ts[:10])
    n = 0
    batch = []
    for m in iter_historical_markets(
        series_ticker=series,
        min_close_ts=min_close_ts,
        max_close_ts=max_close_ts,
    ):
        batch.append(_normalize(m))
        n += 1
        if len(batch) >= 200:
            conn.executemany(UPSERT_SQL, batch)
            conn.commit()
            batch.clear()
            log.info("  %s: %d markets pulled so far", series, n)
    if batch:
        conn.executemany(UPSERT_SQL, batch)
        conn.commit()
    log.info("  %s: TOTAL %d markets", series, n)
    return n


def main() -> int:
    log.info("data cutoff check…")
    cutoff = get_cutoff()
    cutoff_ts = cutoff.get("market_settled_ts", "")
    log.info("cutoff: %s", cutoff_ts)
    if not cutoff_ts:
        log.error("no cutoff returned from Kalshi — bailing")
        return 2

    # Window: [cutoff - 30 days, cutoff]
    cutoff_dt = datetime.fromisoformat(cutoff_ts.replace("Z", "+00:00"))
    min_dt = cutoff_dt - timedelta(days=WINDOW_DAYS)
    min_ts = min_dt.isoformat().replace("+00:00", "Z")
    max_ts = cutoff_ts

    log.info("window: %s → %s (%d days)", min_ts[:10], max_ts[:10], WINDOW_DAYS)

    conn = _init_db()
    totals: dict[str, int] = {}
    for series in SERIES:
        try:
            totals[series] = pull_series(conn, series, min_ts, max_ts)
        except Exception as e:
            log.error("%s pull failed: %s", series, e)
            totals[series] = -1

    log.info("=" * 50)
    log.info("PULL COMPLETE")
    for series, n in totals.items():
        log.info("  %-15s %s", series,
                 f"{n} markets" if n >= 0 else "FAILED")
    log.info("DB: %s", DB_PATH)
    return 0 if all(n >= 0 for n in totals.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
