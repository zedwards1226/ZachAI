"""
SQLite database layer for TradingAgents.
Tables: signals, trades, decisions, guardrail_state
"""
import sqlite3
import logging
from contextlib import contextmanager
from datetime import date, datetime, timezone

from config import DATABASE_PATH

log = logging.getLogger(__name__)


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
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
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT    NOT NULL,
            symbol        TEXT    NOT NULL,
            action        TEXT    NOT NULL,
            price         REAL    NOT NULL DEFAULT 0,
            qty           INTEGER NOT NULL DEFAULT 1,
            order_id      TEXT,
            strategy      TEXT,
            raw_body      TEXT,
            position_size REAL
        );

        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id   INTEGER REFERENCES signals(id),
            symbol      TEXT    NOT NULL,
            side        TEXT    NOT NULL,
            entry       REAL    NOT NULL,
            qty         INTEGER NOT NULL DEFAULT 1,
            multiplier  REAL    NOT NULL DEFAULT 2,
            strategy    TEXT,
            order_id    TEXT,
            opened_at   TEXT    NOT NULL,
            exit        REAL,
            closed_at   TEXT,
            pnl         REAL,
            pts         REAL,
            status      TEXT    NOT NULL DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id   INTEGER REFERENCES signals(id),
            trade_id    INTEGER REFERENCES trades(id),
            agent       TEXT    NOT NULL,
            verdict     TEXT    NOT NULL,
            reasoning   TEXT    NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            timestamp   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS guardrail_state (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date                TEXT    NOT NULL UNIQUE,
            daily_trades        INTEGER NOT NULL DEFAULT 0,
            daily_pnl           REAL    NOT NULL DEFAULT 0.0,
            consecutive_losses  INTEGER NOT NULL DEFAULT 0,
            halted              INTEGER NOT NULL DEFAULT 0,
            halt_reason         TEXT
        );
        """)
    log.info("Database initialized at %s", DATABASE_PATH)


# ── Signals ──────────────────────────────────────────────────────────────────

def insert_signal(symbol: str, action: str, price: float, qty: int = 1,
                  order_id: str = "", strategy: str = "", raw_body: str = "",
                  position_size: float = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (timestamp, symbol, action, price, qty, order_id, strategy, raw_body, position_size)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), symbol, action, price, qty,
             order_id, strategy, raw_body, position_size)
        )
        return cur.lastrowid


# ── Trades ───────────────────────────────────────────────────────────────────

def insert_trade(signal_id: int, symbol: str, side: str, entry: float,
                 qty: int, multiplier: float, strategy: str = "",
                 order_id: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO trades
               (signal_id, symbol, side, entry, qty, multiplier, strategy, order_id, opened_at, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (signal_id, symbol, side, entry, qty, multiplier, strategy, order_id,
             datetime.now(timezone.utc).isoformat(), "open")
        )
        return cur.lastrowid


def close_trades_for_symbol(symbol: str, exit_price: float) -> list[dict]:
    """Close all open trades for a symbol. Returns list of closed trade dicts with P&L."""
    closed = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE symbol=? AND status='open'", (symbol,)
        ).fetchall()
        for row in rows:
            t = dict(row)
            pts = (exit_price - t["entry"]) if t["side"] == "BUY" else (t["entry"] - exit_price)
            pnl = round(pts * t["multiplier"] * t["qty"], 2)
            conn.execute(
                """UPDATE trades SET exit=?, closed_at=?, pnl=?, pts=?, status='closed'
                   WHERE id=?""",
                (exit_price, datetime.now(timezone.utc).isoformat(),
                 pnl, round(pts, 2), t["id"])
            )
            t.update(exit=exit_price, pnl=pnl, pts=round(pts, 2), status="closed")
            closed.append(t)
    return closed


def get_open_trades(symbol: str = None) -> list[dict]:
    with get_conn() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='open' AND symbol=?", (symbol,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='open'"
            ).fetchall()
    return [dict(r) for r in rows]


def get_trades_today() -> list[dict]:
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE opened_at LIKE ? ORDER BY opened_at DESC",
            (f"{today}%",)
        ).fetchall()
    return [dict(r) for r in rows]


def get_trades(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Decisions ────────────────────────────────────────────────────────────────

def insert_decision(signal_id: int, agent: str, verdict: str,
                    reasoning: str, tokens_used: int = 0,
                    trade_id: int = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO decisions
               (signal_id, trade_id, agent, verdict, reasoning, tokens_used, timestamp)
               VALUES (?,?,?,?,?,?,?)""",
            (signal_id, trade_id, agent, verdict, reasoning, tokens_used,
             datetime.now(timezone.utc).isoformat())
        )
        return cur.lastrowid


def get_decisions_for_signal(signal_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE signal_id=? ORDER BY timestamp", (signal_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Guardrail state ─────────────────────────────────────────────────────────

def get_guardrail_state() -> dict:
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


def update_guardrail_after_trade(pnl: float = None) -> None:
    """Increment daily trade count. If pnl provided, update daily P&L and streaks."""
    today = date.today().isoformat()
    state = get_guardrail_state()
    state["daily_trades"] += 1
    if pnl is not None:
        state["daily_pnl"] = round(state["daily_pnl"] + pnl, 2)
        if pnl < 0:
            state["consecutive_losses"] += 1
        else:
            state["consecutive_losses"] = 0
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO guardrail_state
                (date, daily_trades, daily_pnl, consecutive_losses, halted, halt_reason)
            VALUES (:date, :daily_trades, :daily_pnl, :consecutive_losses, :halted, :halt_reason)
            ON CONFLICT(date) DO UPDATE SET
                daily_trades       = excluded.daily_trades,
                daily_pnl          = excluded.daily_pnl,
                consecutive_losses = excluded.consecutive_losses,
                halted             = excluded.halted,
                halt_reason        = excluded.halt_reason
        """, state)


def get_summary() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM trades WHERE status='closed'").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM trades WHERE status='closed' AND pnl > 0").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM trades WHERE status='closed' AND pnl <= 0").fetchone()[0]
        pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status='closed'").fetchone()[0]
        open_count = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "open_trades": open_count,
        "total_pnl": round(pnl, 2),
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
    }
