"""OmniAlpha SQLite schema + connection helpers.

Schema design borrows from WA's `kalshi/bots/database.py` and ryanfrigo's
`src/utils/database.py`, generalized to multi-sector. Five core tables:

  markets             — universe of Kalshi markets seen (live + historical)
  trades              — every order placement, state transitions, fills, exits
  signals             — every scored signal (taken, skipped, blocked) for ML labeling
  decisions           — auditable "why did the bot decide X" rows, joinable to trades
  llm_calls           — LLM cost tracker per bot/strategy (prevents runaway spend)

Plus two sidecars:
  pnl_snapshots       — periodic capital + open-risk + day P&L snapshots
  sector_state        — per-sector pause flags, last-poll timestamps, cooldown counters

WAL mode + busy_timeout=5000 so the dashboard can read without blocking the bot.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH


@contextmanager
def get_conn(db_path: Path = DB_PATH, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    """SQLite connection with WAL + busy_timeout. Commits on clean exit,
    rolls back on exception so a mid-write failure can't leave the
    connection stuck in an aborted transaction."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        # URI mode lets the dashboard open without contention with the bot.
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        # Even readonly connections can hit SQLITE_BUSY during a WAL
        # checkpoint. 2s is plenty for a checkpoint to complete; without
        # it, a coincident checkpoint raises OperationalError.
        conn.execute("PRAGMA busy_timeout=2000")
    else:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if not readonly:
            conn.commit()
    except Exception:
        if not readonly:
            conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
-- Universe of Kalshi markets we've seen. Settled markets keep their result.
-- Pulled from /historical/markets for backtests + /markets for live scanning.
CREATE TABLE IF NOT EXISTS markets (
    ticker              TEXT    PRIMARY KEY,
    event_ticker        TEXT,
    series_ticker       TEXT,
    sector              TEXT,                       -- 'crypto' | 'sports' | 'politics' | 'economics' | 'weather' | 'other'
    title               TEXT,
    open_time           TEXT,
    close_time           TEXT,
    expiration_time     TEXT,
    market_type         TEXT,                       -- 'binary' | 'scalar' (mostly binary)
    strike_type         TEXT,                       -- 'between' | 'less' | 'greater' | 'custom' | etc
    floor_strike        REAL,
    cap_strike          REAL,
    status              TEXT,                       -- 'active' | 'finalized' | 'closed'
    result              TEXT,                       -- NULL while open; 'yes' | 'no' | 'cancelled' once settled
    settlement_value_dollars REAL,
    final_yes_ask_dollars REAL,
    final_no_ask_dollars  REAL,
    volume_fp           REAL,
    open_interest_fp    REAL,
    raw_json            TEXT,                       -- full JSON blob for debugging
    first_seen_at       TEXT    NOT NULL,
    last_updated_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_markets_sector ON markets(sector);
CREATE INDEX IF NOT EXISTS idx_markets_close_time ON markets(close_time);
CREATE INDEX IF NOT EXISTS idx_markets_status ON markets(status);

-- Every order the bot places. paper=1 means simulated, paper=0 is live.
CREATE TABLE IF NOT EXISTS trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    sector              TEXT    NOT NULL,
    strategy            TEXT    NOT NULL,           -- name of the strategy module that fired
    market_ticker       TEXT    NOT NULL,
    side                TEXT    NOT NULL,           -- 'yes' | 'no'
    contracts           INTEGER NOT NULL,
    price_cents         INTEGER NOT NULL,
    edge                REAL,                       -- forecast_prob - market_prob at entry
    kelly_frac          REAL,
    stake_usd           REAL    NOT NULL,
    paper               INTEGER NOT NULL DEFAULT 1, -- 1 = paper, 0 = live
    status              TEXT    NOT NULL,           -- 'open' | 'won' | 'lost' | 'cancelled' | 'failed_placement'
    pnl_usd             REAL    DEFAULT 0,
    resolved_at         TEXT,
    notes               TEXT,
    decision_id         INTEGER,                    -- FK -> decisions.id
    FOREIGN KEY (market_ticker) REFERENCES markets(ticker)
);
CREATE INDEX IF NOT EXISTS idx_trades_sector ON trades(sector);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);

-- Every scored signal — taken, skipped, blocked. Joinable to trades for the ones taken.
-- Captures the full pre-trade state for ML labeling later.
CREATE TABLE IF NOT EXISTS signals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    sector              TEXT    NOT NULL,
    strategy            TEXT    NOT NULL,
    market_ticker       TEXT    NOT NULL,
    side                TEXT,
    forecast_prob       REAL,
    market_prob         REAL,
    edge                REAL,
    score               INTEGER,
    block_reason        TEXT,                       -- NULL if taken; reason if skipped (e.g. 'edge_too_thin', 'risk_cap')
    trade_id            INTEGER,                    -- FK -> trades.id (NULL if not taken)
    raw_features        TEXT                        -- JSON blob of full features at signal time
);
CREATE INDEX IF NOT EXISTS idx_signals_sector ON signals(sector);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);

-- Auditable trail. Every "the bot decided to do X because of Y" row.
-- Trade fills, sector pauses, risk-cap trips, manual interventions all log here.
CREATE TABLE IF NOT EXISTS decisions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    sector              TEXT,
    decision_type       TEXT    NOT NULL,           -- 'enter' | 'exit' | 'skip' | 'pause_sector' | 'resume_sector' | 'risk_cap_hit' | 'manual'
    summary             TEXT    NOT NULL,
    payload             TEXT                        -- JSON details for replay
);
CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);

-- LLM cost ledger. Every Anthropic/other-provider call is logged here so we
-- catch runaway loops at the dashboard before the credit card.
CREATE TABLE IF NOT EXISTS llm_calls (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    sector              TEXT,
    strategy            TEXT,
    model               TEXT    NOT NULL,
    input_tokens        INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    cost_usd            REAL    NOT NULL,
    latency_ms          INTEGER,
    trade_id            INTEGER,                    -- FK -> trades.id; lets us join cost-to-PnL
    purpose             TEXT,                       -- short tag like 'forecast' | 'news_grade' | 'debate'
    success             INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_timestamp ON llm_calls(timestamp);
CREATE INDEX IF NOT EXISTS idx_llm_calls_sector ON llm_calls(sector);

-- Periodic snapshots — like WA's pnl_snapshots, lets the dashboard plot
-- equity curves without scanning the full trades table.
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    capital_usd         REAL    NOT NULL,
    open_risk_usd       REAL    NOT NULL,
    realized_today      REAL    NOT NULL,
    realized_total      REAL    NOT NULL,
    open_positions      INTEGER NOT NULL,
    total_trades        INTEGER NOT NULL,
    total_wins          INTEGER NOT NULL,
    total_losses        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pnl_snapshots_timestamp ON pnl_snapshots(timestamp);

-- Per-sector state — pause flag, last-poll timestamp, cooldown counter.
-- A sector can be auto-paused by CLV grading without restarting the bot.
CREATE TABLE IF NOT EXISTS sector_state (
    sector              TEXT    PRIMARY KEY,
    enabled             INTEGER NOT NULL DEFAULT 1,
    paused_until        TEXT,                       -- NULL or ISO timestamp
    last_poll_at        TEXT,
    consecutive_losses  INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the schema if it doesn't exist. Idempotent — safe to call on every startup."""
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
