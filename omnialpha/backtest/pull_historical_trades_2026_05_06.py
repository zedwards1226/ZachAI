"""Pull Kalshi historical decision-time price snapshots for OmniAlpha backtest.

For each finalized market in the last 30 days of KXBTC15M and KXBTCD:
  1. List all finalized markets via /historical/markets
  2. For each market: pull /historical/trades, pick the trade closest to
     close_time - 90s (the strategy's entry-time anchor)
  3. Save (market_ticker, decision_yes_price, result, close_time, n_trades,
     trade_offset_seconds) to a new SQLite table `historical_decision_snapshots`

Key data caveats discovered during probing:
- KXBTC15M markets are dense (914/1000 trades in the 30-180s window) → high quality
- KXBTCD markets are sparse (median trade ~3000s before close, none in last 30 min)
  → we fall back to "last trade before close" and flag the data quality
- Kalshi historical cutoff is 2026-03-07 (~2 month lag), so "last 30 days" of
  finalized markets is actually data from Feb-March 2026, overlapping the
  original Feb 23-Mar 2 calibration period. Documented in the report.

Run: python C:/ZachAI/omnialpha/backtest/pull_historical_trades_2026_05_06.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
DB_PATH = Path(r"C:\ZachAI\omnialpha\state\omnialpha.db")
SERIES = ["KXBTC15M", "KXBTCD"]
DAYS_BACK = 30
TARGET_OFFSET_S = -90  # 90 seconds before close
RATE_LIMIT_S = 0.15   # ~6 req/sec
MAX_RETRIES = 3
TRADES_PAGE_LIMIT = 1000  # newest-first; covers close window for any reasonable market

session = requests.Session()


def _get(path: str, params: dict, retries: int = MAX_RETRIES) -> dict:
    """GET with retry + backoff on 429/5xx."""
    for attempt in range(retries):
        try:
            r = session.get(f"{BASE}{path}", params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503):
                wait = 2 ** attempt + 1
                print(f"  rate-limit/5xx ({r.status_code}), backing off {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
        except requests.exceptions.Timeout:
            print(f"  timeout, attempt {attempt+1}/{retries}")
            time.sleep(2)
            continue
    raise RuntimeError(f"Exceeded retries on {path} {params}")


def list_finalized_markets(series: str, since: datetime) -> list[dict]:
    """Page through /historical/markets for a series, filter to finalized
    after `since`."""
    out = []
    cursor = None
    pages = 0
    while True:
        params = {"series_ticker": series, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        j = _get("/historical/markets", params)
        time.sleep(RATE_LIMIT_S)
        markets = j.get("markets", [])
        for m in markets:
            if m.get("status") != "finalized" or m.get("result") not in ("yes", "no"):
                continue
            ct = m.get("close_time")
            if not ct:
                continue
            close_dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if close_dt < since:
                # Older than our window — we can stop paginating
                return out
            out.append(m)
        cursor = j.get("cursor")
        pages += 1
        if not cursor or not markets:
            break
        if pages > 100:  # safety stop
            print(f"  WARN: hit page-100 safety on {series}")
            break
    return out


def find_decision_trade(ticker: str, close_dt: datetime) -> dict | None:
    """Pull first page (newest-first, limit=1000) of trades for the market,
    return the trade with created_time closest to close_dt + TARGET_OFFSET_S.

    Page 1 covers the most recent ~1000 trades, which spans the entry window
    for any reasonable market. Skipping pagination cuts ~30%+ of round-trips.
    For sparse markets (e.g. KXBTCD) returns the latest available trade with
    `is_in_window=False`.
    """
    target = close_dt + timedelta(seconds=TARGET_OFFSET_S)
    j = _get("/historical/trades", {"ticker": ticker, "limit": TRADES_PAGE_LIMIT})
    time.sleep(RATE_LIMIT_S)
    all_trades = j.get("trades", [])
    if not all_trades:
        return None

    # Pick trade closest to target time
    def offset(t):
        ct = datetime.fromisoformat(t["created_time"].replace("Z", "+00:00"))
        return abs((ct - target).total_seconds())
    best = min(all_trades, key=offset)
    best_offset = (
        datetime.fromisoformat(best["created_time"].replace("Z", "+00:00")) - close_dt
    ).total_seconds()
    return {
        "yes_price": float(best.get("yes_price_dollars", 0)),
        "no_price": float(best.get("no_price_dollars", 0)),
        "trade_time": best["created_time"],
        "offset_from_close_s": best_offset,
        "n_trades_in_market": len(all_trades),
        "is_in_target_window": -180 <= best_offset <= -30,
    }


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historical_decision_snapshots (
            market_ticker TEXT PRIMARY KEY,
            series_ticker TEXT NOT NULL,
            close_time TEXT NOT NULL,
            decision_yes_price REAL NOT NULL,
            decision_no_price REAL,
            decision_trade_time TEXT,
            offset_from_close_s REAL,
            n_trades_in_market INTEGER,
            is_in_target_window INTEGER,
            result TEXT NOT NULL,
            volume_fp REAL,
            pulled_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def upsert_snapshot(conn: sqlite3.Connection, m: dict, snap: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO historical_decision_snapshots
        (market_ticker, series_ticker, close_time, decision_yes_price,
         decision_no_price, decision_trade_time, offset_from_close_s,
         n_trades_in_market, is_in_target_window, result, volume_fp, pulled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            m["ticker"],
            m.get("event_ticker", "").split("-")[0] if "-" in m.get("event_ticker", "") else "",
            m["close_time"],
            snap["yes_price"],
            snap["no_price"],
            snap["trade_time"],
            snap["offset_from_close_s"],
            snap["n_trades_in_market"],
            1 if snap["is_in_target_window"] else 0,
            m["result"],
            float(m.get("volume_fp", 0) or 0),
        datetime.now(timezone.utc).isoformat(),
        ),
    )


def main():
    cutoff = _get("/historical/cutoff", {})
    print(f"Kalshi historical cutoff: {cutoff}")
    settled_cutoff = datetime.fromisoformat(
        cutoff["market_settled_ts"].replace("Z", "+00:00")
    )
    print(f"Most recent settled market available: {settled_cutoff.isoformat()}")
    since = settled_cutoff - timedelta(days=DAYS_BACK)
    print(f"Pulling markets settled between {since.isoformat()} and {settled_cutoff.isoformat()}")
    print()

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    # Resume support: skip markets we already have
    cur = conn.cursor()
    cur.execute("SELECT market_ticker FROM historical_decision_snapshots")
    already_pulled = {r[0] for r in cur.fetchall()}
    print(f"Resume: already have {len(already_pulled)} snapshots from prior runs")
    print()

    series_series_ticker_map = {}  # ticker prefix -> series

    for series in SERIES:
        print(f"=== {series} ===")
        markets = list_finalized_markets(series, since)
        print(f"  {len(markets)} finalized markets in window")

        skipped = 0
        pulled = 0
        no_trades = 0
        out_of_window = 0

        for i, m in enumerate(markets, 1):
            if m["ticker"] in already_pulled:
                skipped += 1
                continue
            # Skip markets with zero volume — no trades, wastes a round-trip
            if float(m.get("volume_fp", 0) or 0) == 0:
                no_trades += 1
                continue
            close_dt = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
            try:
                snap = find_decision_trade(m["ticker"], close_dt)
            except Exception as e:
                print(f"    [{i}/{len(markets)}] {m['ticker']} ERR {e}")
                continue
            if snap is None:
                no_trades += 1
                continue
            if not snap["is_in_target_window"]:
                out_of_window += 1
            # Override series field for the table (event ticker prefix isn't reliable)
            m_with_series = dict(m, _series=series)
            # Use the series we know
            conn.execute(
                """
                INSERT OR REPLACE INTO historical_decision_snapshots
                (market_ticker, series_ticker, close_time, decision_yes_price,
                 decision_no_price, decision_trade_time, offset_from_close_s,
                 n_trades_in_market, is_in_target_window, result, volume_fp, pulled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    m["ticker"], series, m["close_time"],
                    snap["yes_price"], snap["no_price"], snap["trade_time"],
                    snap["offset_from_close_s"], snap["n_trades_in_market"],
                    1 if snap["is_in_target_window"] else 0, m["result"],
                    float(m.get("volume_fp", 0) or 0),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            pulled += 1
            if pulled % 50 == 0:
                conn.commit()
                print(f"    [{i}/{len(markets)}] pulled {pulled}, in-window={pulled - out_of_window}, no-trades={no_trades}")

        conn.commit()
        print(f"  DONE {series}: {pulled} new snapshots, {skipped} resumed, "
              f"{no_trades} markets had no trades, {out_of_window} out of "
              f"30-180s window (used last available trade)")
        print()

    # Summary
    cur.execute(
        "SELECT series_ticker, COUNT(*), SUM(is_in_target_window), "
        "SUM(CASE WHEN result='yes' THEN 1 ELSE 0 END) "
        "FROM historical_decision_snapshots GROUP BY series_ticker"
    )
    print("=== Summary ===")
    for series, n, in_win, yes_won in cur.fetchall():
        print(f"  {series}: {n} snapshots, {in_win} in target window, {yes_won} resolved YES")


if __name__ == "__main__":
    main()
