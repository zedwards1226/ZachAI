"""ICTBot SQLite schema + connection helpers.

Tables:
- trades         — every paper-traded entry/exit with R, MAE, MFE, journal text
- setups         — every detected setup (whether traded or not, for hit-rate stats)
- fvgs           — every FVG seen (open, mitigated, expired) for edge research
- daily_levels   — PDH, PDL, premarket high/low, ORB high/low (for context)
- signals        — each scan tick's raw signals (for replay + debug)
- journal        — free-form session notes appended by agents
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "state" / "trades.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id        INTEGER,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,           -- 'long' | 'short'
    qty             INTEGER NOT NULL,
    entry_time      TEXT NOT NULL,           -- ISO ET
    entry_price     REAL NOT NULL,
    stop_price      REAL NOT NULL,
    target_price    REAL NOT NULL,
    exit_time       TEXT,
    exit_price      REAL,
    exit_reason     TEXT,                    -- 'tp_hit' | 'sl_hit' | 'be_scratch' | 'time_exit' | 'hard_close' | 'manual'
    pnl_dollars     REAL,
    pnl_r           REAL,
    mae_points      REAL,
    mfe_points      REAL,
    paper_mode      INTEGER NOT NULL,
    scan_only       INTEGER NOT NULL,
    notes           TEXT,
    FOREIGN KEY (setup_id) REFERENCES setups(id)
);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);

CREATE TABLE IF NOT EXISTS setups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_time   TEXT NOT NULL,           -- ISO ET
    setup_name      TEXT NOT NULL,           -- 'ny_am_fvg' | 'silver_bullet' | ...
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    bias            TEXT,                    -- 'long' | 'short'
    entry_zone_low  REAL,
    entry_zone_high REAL,
    stop_price      REAL,
    target_price    REAL,
    rr              REAL,
    confidence      INTEGER,                 -- 0-100
    triggered       INTEGER DEFAULT 0,       -- 0 = detected only, 1 = trade fired
    invalidated     INTEGER DEFAULT 0,       -- 1 = price action killed setup before trigger
    payload         TEXT                     -- JSON blob of supporting context
);
CREATE INDEX IF NOT EXISTS idx_setups_detected_time ON setups(detected_time);
CREATE INDEX IF NOT EXISTS idx_setups_setup_name ON setups(setup_name);

CREATE TABLE IF NOT EXISTS fvgs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_time   TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    direction       TEXT NOT NULL,           -- 'bullish' | 'bearish'
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    midpoint        REAL NOT NULL,
    displacement_pts REAL,
    mitigated_time  TEXT,                    -- ISO ET when filled
    mitigated       INTEGER DEFAULT 0,
    expired         INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fvgs_detected_time ON fvgs(detected_time);
CREATE INDEX IF NOT EXISTS idx_fvgs_mitigated ON fvgs(mitigated);

CREATE TABLE IF NOT EXISTS daily_levels (
    date            TEXT PRIMARY KEY,        -- YYYY-MM-DD
    symbol          TEXT NOT NULL,
    pdh             REAL,                    -- prior day high
    pdl             REAL,
    pdc             REAL,                    -- prior day close
    premarket_high  REAL,
    premarket_low   REAL,
    orb_high        REAL,                    -- 9:30-9:45 range
    orb_low         REAL,
    htf_bias        TEXT                     -- 'long' | 'short' | 'neutral'
);

CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_time       TEXT NOT NULL,
    setup_name      TEXT NOT NULL,
    payload         TEXT NOT NULL            -- JSON
);
CREATE INDEX IF NOT EXISTS idx_signals_tick_time ON signals(tick_time);

CREATE TABLE IF NOT EXISTS journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    source          TEXT NOT NULL,           -- 'monitor' | 'briefing' | 'learning' | 'manual'
    level           TEXT NOT NULL,           -- 'info' | 'warn' | 'error'
    message         TEXT NOT NULL,
    payload         TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON journal(timestamp);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create tables if they don't exist."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def insert_setup(setup: dict, db_path: Path = DB_PATH) -> int:
    """Insert a detected setup, return its id."""
    cols = ["detected_time", "setup_name", "symbol", "timeframe", "bias",
            "entry_zone_low", "entry_zone_high", "stop_price", "target_price",
            "rr", "confidence", "triggered", "invalidated", "payload"]
    values = [setup.get(c) for c in cols]
    with get_connection(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO setups ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            values,
        )
        return cur.lastrowid


def insert_fvg(fvg: dict, db_path: Path = DB_PATH) -> int:
    cols = ["detected_time", "symbol", "timeframe", "direction", "high", "low",
            "midpoint", "displacement_pts", "mitigated_time", "mitigated", "expired"]
    values = [fvg.get(c) for c in cols]
    with get_connection(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO fvgs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            values,
        )
        return cur.lastrowid


def insert_trade(trade: dict, db_path: Path = DB_PATH) -> int:
    cols = ["setup_id", "symbol", "side", "qty", "entry_time", "entry_price",
            "stop_price", "target_price", "paper_mode", "scan_only", "notes"]
    values = [trade.get(c) for c in cols]
    with get_connection(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO trades ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            values,
        )
        return cur.lastrowid


def close_trade(trade_id: int, exit_price: float, exit_reason: str,
                pnl_dollars: float, pnl_r: float,
                mae_points: float | None, mfe_points: float | None,
                db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE trades SET exit_time=?, exit_price=?, exit_reason=?, "
            "pnl_dollars=?, pnl_r=?, mae_points=?, mfe_points=? WHERE id=?",
            (datetime.utcnow().isoformat(), exit_price, exit_reason,
             pnl_dollars, pnl_r, mae_points, mfe_points, trade_id),
        )


def append_journal(source: str, level: str, message: str,
                   payload: str | None = None, db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO journal (timestamp, source, level, message, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), source, level, message, payload),
        )


def fetch_recent_trades(limit: int = 30, db_path: Path = DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def fetch_today_setups(date_iso: str, db_path: Path = DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM setups WHERE substr(detected_time,1,10)=? ORDER BY detected_time DESC",
            (date_iso,),
        ).fetchall()
        return [dict(r) for r in rows]


def fetch_open_position(symbol: str, db_path: Path = DB_PATH) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE symbol=? AND exit_time IS NULL ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return dict(row) if row else None


def equity_curve(db_path: Path = DB_PATH) -> list[tuple[str, float]]:
    """Return cumulative P&L by date as [(YYYY-MM-DD, cumulative_pnl), ...]."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT substr(exit_time,1,10) AS d, SUM(pnl_dollars) AS daily "
            "FROM trades WHERE exit_time IS NOT NULL GROUP BY d ORDER BY d"
        ).fetchall()
    cum = 0.0
    out: list[tuple[str, float]] = []
    for r in rows:
        cum += (r["daily"] or 0.0)
        out.append((r["d"], cum))
    return out
