"""
SQLite database layer for WeatherAlpha.
Tables: trades, forecasts, guardrail_state, pnl_snapshots
"""
import sqlite3
import json
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from config import DATABASE_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            city         TEXT    NOT NULL,
            market_id    TEXT    NOT NULL,
            side         TEXT    NOT NULL,   -- YES or NO
            contracts    INTEGER NOT NULL,
            price_cents  INTEGER NOT NULL,   -- Kalshi price 0-100
            edge         REAL    NOT NULL,
            kelly_frac   REAL    NOT NULL,
            stake_usd    REAL    NOT NULL,
            paper        INTEGER NOT NULL DEFAULT 1,
            status       TEXT    NOT NULL DEFAULT 'open',  -- open/won/lost/cancelled
            pnl_usd      REAL,
            resolved_at  TEXT,
            notes        TEXT
        );

        CREATE TABLE IF NOT EXISTS forecasts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            city         TEXT    NOT NULL,
            forecast_hi_f REAL   NOT NULL,
            forecast_lo_f REAL   NOT NULL,
            kalshi_market_id TEXT,
            kalshi_strike_f  REAL,
            kalshi_yes_price REAL,
            kalshi_no_price  REAL,
            implied_prob_yes REAL,
            our_prob_yes     REAL,
            edge             REAL,
            raw_weather      TEXT   -- JSON blob
        );

        CREATE TABLE IF NOT EXISTS guardrail_state (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            date                 TEXT    NOT NULL UNIQUE,
            daily_trades         INTEGER NOT NULL DEFAULT 0,
            daily_pnl_usd        REAL    NOT NULL DEFAULT 0.0,
            consecutive_losses   INTEGER NOT NULL DEFAULT 0,
            capital_at_risk_usd  REAL    NOT NULL DEFAULT 0.0,
            halted               INTEGER NOT NULL DEFAULT 0,
            halt_reason          TEXT
        );

        CREATE TABLE IF NOT EXISTS pnl_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            capital_usd REAL NOT NULL,
            open_risk   REAL NOT NULL DEFAULT 0.0,
            total_trades INTEGER NOT NULL DEFAULT 0,
            total_wins   INTEGER NOT NULL DEFAULT 0,
            total_losses INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS decision_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
            type         TEXT NOT NULL,  -- scan|trade|block|skip|error|system|connect|info
            city         TEXT,
            message      TEXT NOT NULL,
            edge         REAL,
            contracts    INTEGER,
            side         TEXT,
            price_cents  INTEGER,
            stake_usd    REAL,
            reason       TEXT
        );
        """)


# ── Trades ────────────────────────────────────────────────────────────────────

def insert_trade(city, market_id, side, contracts, price_cents,
                 edge, kelly_frac, stake_usd, paper=True, notes="") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO trades
               (timestamp, city, market_id, side, contracts, price_cents,
                edge, kelly_frac, stake_usd, paper, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.utcnow().isoformat(), city, market_id, side, contracts,
             price_cents, edge, kelly_frac, stake_usd, int(paper), notes)
        )
        return cur.lastrowid


def resolve_trade(trade_id: int, won: bool, pnl_usd: float) -> None:
    status = "won" if won else "lost"
    with get_conn() as conn:
        conn.execute(
            "UPDATE trades SET status=?, pnl_usd=?, resolved_at=? WHERE id=?",
            (status, pnl_usd, datetime.utcnow().isoformat(), trade_id)
        )


def get_open_trades() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='open' ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def has_open_trade_for_market(market_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM trades WHERE market_id=? AND status='open' LIMIT 1",
            (market_id,)
        ).fetchone()
    return row is not None


def get_trades(limit=100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Guardrail state ───────────────────────────────────────────────────────────

def get_guardrail_state(today: str | None = None) -> dict:
    if today is None:
        today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM guardrail_state WHERE date=?", (today,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT OR IGNORE INTO guardrail_state (date) VALUES (?)", (today,)
            )
            row = conn.execute(
                "SELECT * FROM guardrail_state WHERE date=?", (today,)
            ).fetchone()
    return dict(row)


def update_guardrail_state(**fields) -> None:
    today = date.today().isoformat()
    state = get_guardrail_state(today)
    state.update(fields)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO guardrail_state
                (date, daily_trades, daily_pnl_usd, consecutive_losses,
                 capital_at_risk_usd, halted, halt_reason)
            VALUES (:date, :daily_trades, :daily_pnl_usd, :consecutive_losses,
                    :capital_at_risk_usd, :halted, :halt_reason)
            ON CONFLICT(date) DO UPDATE SET
                daily_trades        = excluded.daily_trades,
                daily_pnl_usd       = excluded.daily_pnl_usd,
                consecutive_losses  = excluded.consecutive_losses,
                capital_at_risk_usd = excluded.capital_at_risk_usd,
                halted              = excluded.halted,
                halt_reason         = excluded.halt_reason
        """, state)


# ── Forecasts ─────────────────────────────────────────────────────────────────

def insert_forecast(city, forecast_hi_f, forecast_lo_f, kalshi_market_id=None,
                    kalshi_strike_f=None, kalshi_yes_price=None,
                    kalshi_no_price=None, implied_prob_yes=None,
                    our_prob_yes=None, edge=None, raw_weather=None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO forecasts
               (timestamp, city, forecast_hi_f, forecast_lo_f, kalshi_market_id,
                kalshi_strike_f, kalshi_yes_price, kalshi_no_price,
                implied_prob_yes, our_prob_yes, edge, raw_weather)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.utcnow().isoformat(), city, forecast_hi_f, forecast_lo_f,
             kalshi_market_id, kalshi_strike_f, kalshi_yes_price, kalshi_no_price,
             implied_prob_yes, our_prob_yes, edge,
             json.dumps(raw_weather) if raw_weather else None)
        )
        return cur.lastrowid


def get_latest_forecasts() -> list[dict]:
    """Return the most recent forecast per city."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT f.* FROM forecasts f
            INNER JOIN (
                SELECT city, MAX(timestamp) AS mt FROM forecasts GROUP BY city
            ) latest ON f.city = latest.city AND f.timestamp = latest.mt
        """).fetchall()
    return [dict(r) for r in rows]


# ── P&L snapshots ─────────────────────────────────────────────────────────────

def snapshot_pnl(capital_usd: float, open_risk: float) -> None:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        wins  = conn.execute("SELECT COUNT(*) FROM trades WHERE status='won'").fetchone()[0]
        losses= conn.execute("SELECT COUNT(*) FROM trades WHERE status='lost'").fetchone()[0]
        conn.execute(
            """INSERT INTO pnl_snapshots
               (timestamp, capital_usd, open_risk, total_trades, total_wins, total_losses)
               VALUES (?,?,?,?,?,?)""",
            (datetime.utcnow().isoformat(), capital_usd, open_risk, total, wins, losses)
        )


def get_pnl_history(limit=200) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pnl_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Decision log ──────────────────────────────────────────────────────────────

def log_decision(type: str, message: str, city=None, edge=None, contracts=None,
                 side=None, price_cents=None, stake_usd=None, reason=None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO decision_log
               (type, message, city, edge, contracts, side, price_cents, stake_usd, reason)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (type, message, city, edge, contracts, side, price_cents, stake_usd, reason)
        )
        return cur.lastrowid


def get_decision_log(limit: int = 100, since: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if since:
            rows = conn.execute(
                """SELECT * FROM decision_log WHERE timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (since, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM decision_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_summary() -> dict:
    with get_conn() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        wins   = conn.execute("SELECT COUNT(*) FROM trades WHERE status='won'").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM trades WHERE status='lost'").fetchone()[0]
        pnl    = conn.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM trades WHERE pnl_usd IS NOT NULL").fetchone()[0]
        open_c = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
        open_r = conn.execute("SELECT COALESCE(SUM(stake_usd),0) FROM trades WHERE status='open'").fetchone()[0]
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "open_trades": open_c,
        "open_risk_usd": round(open_r, 2),
        "total_pnl_usd": round(pnl, 2),
        "win_rate": round(wins / total, 3) if total else 0.0,
    }
