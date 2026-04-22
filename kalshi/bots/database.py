"""
SQLite database layer for WeatherAlpha.
Tables: trades, forecasts, guardrail_state, pnl_snapshots, decision_log, signals
"""
import logging
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
            floor_f      REAL,              -- between-market floor temp
            cap_f        REAL,              -- between-market cap temp
            strike_type  TEXT,              -- 'greater' or 'between'
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

        CREATE TABLE IF NOT EXISTS signals (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT    NOT NULL,
            city             TEXT    NOT NULL,
            market_id        TEXT,
            direction        TEXT,           -- YES or NO
            model_prob       REAL,           -- our probability
            market_price     REAL,           -- Kalshi implied price (0-1)
            edge             REAL,
            kelly_fraction   REAL,
            suggested_size   REAL,
            actionable       INTEGER NOT NULL DEFAULT 0,
            reason_skipped   TEXT,           -- why not traded (guardrail, low edge, etc.)
            trade_id         INTEGER,        -- FK to trades.id if traded
            actual_outcome   TEXT,           -- YES or NO (after settlement)
            outcome_correct  INTEGER,        -- 1 if predicted correctly
            settled_at       TEXT,
            forecast_hi_f    REAL,
            forecast_lo_f    REAL,
            strike_f         REAL
        );

        CREATE TABLE IF NOT EXISTS scan_logs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id            TEXT    NOT NULL UNIQUE,
            started_at        TEXT    NOT NULL,
            completed_at      TEXT,
            cities_scanned    TEXT,
            markets_found     INTEGER DEFAULT 0,
            signals_generated INTEGER DEFAULT 0,
            trades_executed   INTEGER DEFAULT 0,
            errors            INTEGER DEFAULT 0,
            success           INTEGER DEFAULT 1,
            error_detail      TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_state (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS city_cooldowns (
            city        TEXT PRIMARY KEY,
            reason      TEXT NOT NULL,
            until_ts    TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_journal (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
            category    TEXT NOT NULL,   -- observation|decision|action|digest
            subject     TEXT,            -- city, setting name, or null
            rationale   TEXT NOT NULL,
            data_json   TEXT             -- raw metrics JSON
        );

        -- Prevent duplicate trades: one open trade per market at a time
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_market_open
            ON trades (market_id) WHERE status = 'open';
        """)

        # Migrate: add columns if they don't exist (safe for existing DBs)
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN floor_f REAL")
        except Exception:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN cap_f REAL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN strike_type TEXT")
        except Exception:
            pass


# ── Trades ────────────────────────────────────────────────────────────────────

def insert_trade(city, market_id, side, contracts, price_cents,
                 edge, kelly_frac, stake_usd, paper=True,
                 floor_f=None, cap_f=None, strike_type=None, notes="") -> int:
    """Insert a trade. Returns row id, or -1 if blocked by unique constraint (duplicate)."""
    import sqlite3
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO trades
                   (timestamp, city, market_id, side, contracts, price_cents,
                    edge, kelly_frac, stake_usd, paper, floor_f, cap_f, strike_type, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.utcnow().isoformat(), city, market_id, side, contracts,
                 price_cents, edge, kelly_frac, stake_usd, int(paper),
                 floor_f, cap_f, strike_type, notes)
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        logging.getLogger(__name__).warning(
            "Duplicate trade blocked by DB constraint: %s %s", city, market_id
        )
        return -1


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


def has_trade_for_market_today(market_id: str) -> bool:
    """Check if ANY trade (open, won, lost) was placed today for this market.
    Prevents duplicate entries during rapid restarts or repeated scans."""
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM trades WHERE market_id=? AND timestamp LIKE ? LIMIT 1",
            (market_id, f"{today_str}%")
        ).fetchone()
    return row is not None


def has_open_trade_for_city(city: str) -> bool:
    """Check if there's already an open trade for this city.
    Prevents multiple bets on same city (different strikes)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM trades WHERE city=? AND status='open' LIMIT 1",
            (city,)
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
        # Win rate computed only over resolved trades (wins + losses).
        "win_rate": round(wins / (wins + losses), 3) if (wins + losses) else 0.0,
    }


def get_today_stats() -> dict:
    """Today's activity: realized PnL, new trades, resolved wins/losses."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                COUNT(*),
                COALESCE(SUM(CASE WHEN status='won'  THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(pnl_usd),0)
               FROM trades WHERE date(timestamp)=date('now','localtime')"""
        ).fetchone()
    return {
        "trades_today": row[0],
        "wins_today": row[1],
        "losses_today": row[2],
        "pnl_today_usd": round(row[3], 2),
    }


def get_today_signal_stats() -> dict:
    """Today's signal scan counts — powers the daily heartbeat.

    Returns total evaluated, actionable (opened trade), and skipped (with
    the top skip reason). Zero-trade days still produce a non-zero scanned
    count so Telegram silence can't be mistaken for 'bot died.'
    """
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE date(timestamp)=date('now','localtime')"
        ).fetchone()[0]
        opened = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE date(timestamp)=date('now','localtime') AND actionable=1"
        ).fetchone()[0]
        skipped = total - opened
        top_reason_row = conn.execute(
            """SELECT reason_skipped, COUNT(*) c
                 FROM signals
                WHERE date(timestamp)=date('now','localtime')
                  AND actionable=0 AND reason_skipped IS NOT NULL
                GROUP BY reason_skipped ORDER BY c DESC LIMIT 1"""
        ).fetchone()
    return {
        "scanned": total,
        "opened": opened,
        "skipped": skipped,
        "top_skip_reason": top_reason_row[0] if top_reason_row else None,
    }


def get_city_performance() -> list:
    """Lifetime performance per city — drives the city scoreboard."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT city,
                      COUNT(*),
                      SUM(CASE WHEN status='won'  THEN 1 ELSE 0 END),
                      SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN status='open' THEN 1 ELSE 0 END),
                      COALESCE(SUM(pnl_usd),0)
                 FROM trades GROUP BY city ORDER BY 6 DESC"""
        ).fetchall()
    out = []
    for r in rows:
        wins, losses = r[2], r[3]
        out.append({
            "city": r[0], "total": r[1], "wins": wins, "losses": losses,
            "open": r[4], "pnl_usd": round(r[5], 2),
            "win_rate": round(wins/(wins+losses), 3) if (wins+losses) else 0.0,
        })
    return out


# ── Signals (calibration tracking) ──────────────────────────────────────────

def insert_signal(city, market_id=None, direction=None, model_prob=None,
                  market_price=None, edge=None, kelly_fraction=None,
                  suggested_size=None, actionable=False, reason_skipped=None,
                  trade_id=None, forecast_hi_f=None, forecast_lo_f=None,
                  strike_f=None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (timestamp, city, market_id, direction, model_prob, market_price,
                edge, kelly_fraction, suggested_size, actionable, reason_skipped,
                trade_id, forecast_hi_f, forecast_lo_f, strike_f)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.utcnow().isoformat(), city, market_id, direction,
             model_prob, market_price, edge, kelly_fraction, suggested_size,
             int(actionable), reason_skipped, trade_id,
             forecast_hi_f, forecast_lo_f, strike_f)
        )
        return cur.lastrowid


def settle_signal(signal_id: int, actual_outcome: str, outcome_correct: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE signals SET actual_outcome=?, outcome_correct=?, settled_at=?
               WHERE id=?""",
            (actual_outcome, int(outcome_correct), datetime.utcnow().isoformat(), signal_id)
        )


def settle_signal_by_trade(trade_id: int, actual_outcome: str, outcome_correct: bool) -> None:
    """Settle the signal linked to a given trade."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE signals SET actual_outcome=?, outcome_correct=?, settled_at=?
               WHERE trade_id=?""",
            (actual_outcome, int(outcome_correct), datetime.utcnow().isoformat(), trade_id)
        )


def get_signals(limit=100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_unsettled_signals() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signals WHERE actual_outcome IS NULL ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_equity_curve() -> list[dict]:
    """Build cumulative P&L curve from settled trades in chronological order."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, timestamp, resolved_at, city, market_id, side,
                      price_cents, stake_usd, pnl_usd, status
               FROM trades WHERE status IN ('won', 'lost')
               ORDER BY COALESCE(resolved_at, timestamp) ASC"""
        ).fetchall()
    from config import STARTING_CAPITAL
    curve = [{"timestamp": None, "pnl": 0.0, "capital": STARTING_CAPITAL, "trade_id": None}]
    cumulative = 0.0
    for r in rows:
        d = dict(r)
        cumulative += d["pnl_usd"] or 0.0
        curve.append({
            "timestamp": d["resolved_at"] or d["timestamp"],
            "pnl": round(cumulative, 2),
            "capital": round(STARTING_CAPITAL + cumulative, 2),
            "trade_id": d["id"],
        })
    return curve


def get_calibration() -> dict:
    """Compute calibration metrics from settled signals."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        settled = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE actual_outcome IS NOT NULL"
        ).fetchone()[0]
        correct = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE outcome_correct = 1"
        ).fetchone()[0]
        # Brier score: mean of (predicted_prob - actual_outcome)^2
        brier_rows = conn.execute(
            """SELECT model_prob, outcome_correct FROM signals
               WHERE actual_outcome IS NOT NULL AND model_prob IS NOT NULL"""
        ).fetchall()

    accuracy = round(correct / settled, 4) if settled else 0.0

    # Brier score
    brier = 0.0
    if brier_rows:
        sq_errors = []
        for r in brier_rows:
            p = r["model_prob"]
            actual = r["outcome_correct"]  # 1 or 0
            sq_errors.append((p - actual) ** 2)
        brier = round(sum(sq_errors) / len(sq_errors), 4) if sq_errors else 0.0

    return {
        "total_signals": total,
        "settled": settled,
        "correct": correct,
        "accuracy": accuracy,
        "brier_score": brier,
    }


def get_trades_with_verification(limit=100) -> list[dict]:
    """Trades joined with forecast data for verification."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.*,
                      f.forecast_hi_f, f.forecast_lo_f,
                      f.kalshi_strike_f, f.our_prob_yes, f.implied_prob_yes
               FROM trades t
               LEFT JOIN forecasts f ON f.kalshi_market_id = t.market_id
                   AND f.id = (
                       SELECT MAX(f2.id) FROM forecasts f2
                       WHERE f2.kalshi_market_id = t.market_id
                         AND f2.timestamp <= t.timestamp
                   )
               ORDER BY t.timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Agent state / cooldowns / journal ────────────────────────────────────────

def agent_get(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM agent_state WHERE key=?", (key,)
        ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def agent_set(key: str, value) -> None:
    payload = json.dumps(value) if not isinstance(value, str) else value
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO agent_state (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                   value=excluded.value, updated_at=excluded.updated_at""",
            (key, payload)
        )


def agent_state_all() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value, updated_at FROM agent_state").fetchall()
    out = {}
    for r in rows:
        try:
            out[r["key"]] = {"value": json.loads(r["value"]), "updated_at": r["updated_at"]}
        except Exception:
            out[r["key"]] = {"value": r["value"], "updated_at": r["updated_at"]}
    return out


def pause_city(city: str, hours: int, reason: str) -> None:
    from datetime import timedelta
    until = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO city_cooldowns (city, reason, until_ts, created_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(city) DO UPDATE SET
                   reason=excluded.reason,
                   until_ts=excluded.until_ts,
                   created_at=excluded.created_at""",
            (city, reason, until)
        )


def unpause_city(city: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM city_cooldowns WHERE city=?", (city,))


def city_is_paused(city: str) -> tuple[bool, str | None]:
    """Return (paused, reason). Auto-expires cooldowns past until_ts."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT reason, until_ts FROM city_cooldowns WHERE city=?", (city,)
        ).fetchone()
        if row is None:
            return False, None
        try:
            until = datetime.fromisoformat(row["until_ts"])
        except Exception:
            return False, None
        if datetime.utcnow() >= until:
            conn.execute("DELETE FROM city_cooldowns WHERE city=?", (city,))
            return False, None
        return True, f"{row['reason']} (until {row['until_ts']})"


def get_city_cooldowns() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT city, reason, until_ts, created_at FROM city_cooldowns"
        ).fetchall()
    return [dict(r) for r in rows]


def journal_write(category: str, rationale: str, subject: str | None = None,
                  data: dict | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO agent_journal (category, subject, rationale, data_json)
               VALUES (?, ?, ?, ?)""",
            (category, subject, rationale, json.dumps(data) if data else None)
        )
        return cur.lastrowid


def get_agent_journal(limit: int = 100, category: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if category:
            rows = conn.execute(
                """SELECT * FROM agent_journal WHERE category=?
                   ORDER BY id DESC LIMIT ?""",
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_journal ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("data_json"):
            try:
                d["data"] = json.loads(d["data_json"])
            except Exception:
                pass
        out.append(d)
    return out


def get_recent_city_trades(city: str, limit: int = 10) -> list[dict]:
    """Resolved trades for a city, newest first, for streak analysis."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM trades
               WHERE city=? AND status IN ('won','lost')
               ORDER BY resolved_at DESC LIMIT ?""",
            (city, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_brier_recent(days: int = 14) -> dict:
    """Rolling Brier + accuracy over the last N days of settled signals."""
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT model_prob, outcome_correct FROM signals
               WHERE actual_outcome IS NOT NULL
                 AND model_prob IS NOT NULL
                 AND settled_at >= ?""",
            (cutoff,)
        ).fetchall()
    if not rows:
        return {"samples": 0, "brier": None, "accuracy": None}
    sq = [(r["model_prob"] - r["outcome_correct"]) ** 2 for r in rows]
    correct = sum(r["outcome_correct"] for r in rows)
    return {
        "samples": len(rows),
        "brier": round(sum(sq) / len(sq), 4),
        "accuracy": round(correct / len(rows), 4),
    }
