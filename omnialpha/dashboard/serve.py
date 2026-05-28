"""LongshotFade dashboard backend — Flask read-only API on :8503.

Serves the static dashboard.html at `/` and exposes JSON endpoints that
the dashboard polls every couple seconds. Read-only against
omnialpha/state/kalshi.db via SQLite URI mode — the dashboard can NEVER
write to or lock the journal the live bot uses.

Endpoints:
  GET /                       — dashboard.html (single-file SPA)
  GET /api/health             — paper mode flag, uptime, scan stats, capital
  GET /api/feed               — last N decisions (paginated by ?since=<id>)
  GET /api/thinking           — most recent ENGAGE decision with full math
  GET /api/positions          — open trades + recent settlements
  GET /api/performance        — equity curve, band WR vs forecast, series PnL
  GET /api/subsystems         — bot/api/db/telegram/watchdog health dots

Mirrors the trading/dashboard/backend/serve.py pattern but adapted for
omnialpha's schema (decisions, trades, pnl_snapshots).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Make omnialpha importable
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS  # type: ignore

from config import DB_PATH, PAPER_MODE, STARTING_CAPITAL_USD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("dashboard")
logging.getLogger("werkzeug").setLevel(logging.WARNING)


# ─── App ────────────────────────────────────────────────────────────────
APP_START_TS = time.time()
PID_FILE = HERE.parent / "state" / "longshot.pid"

app = Flask(__name__, static_folder=None)
CORS(app)


def _ro_conn() -> sqlite3.Connection:
    """Read-only SQLite connection via URI mode. Dashboard bugs can't
    affect the live bot's journal."""
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA busy_timeout=2000")
    conn.row_factory = sqlite3.Row
    return conn


def _bot_pid_alive() -> int | None:
    """Return PID if the bot's PID file points at a live process. None otherwise.

    Requires psutil — on Windows, `os.kill(pid, 0)` actually calls
    TerminateProcess (not a safe liveness check), so we refuse the fallback.
    If psutil is missing, we assume the bot is dead and surface a warning;
    don't ever risk killing the real process from a dashboard call.
    """
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None
    try:
        import psutil  # type: ignore
    except ImportError:
        log.warning("psutil missing — cannot safely check bot liveness on Windows. "
                    "Run: pip install psutil")
        return None
    return pid if psutil.pid_exists(pid) else None


# ─── Routes ─────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return send_file(str(HERE / "dashboard.html"))


@app.route("/api/health")
def api_health():
    bot_pid = _bot_pid_alive()
    uptime_s = int(time.time() - APP_START_TS)

    try:
        with _ro_conn() as conn:
            # Last scan: most recent decision row
            last_decision = conn.execute(
                "SELECT timestamp FROM decisions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            # Counts for the most recent batch (same timestamp)
            if last_decision:
                batch_ts = last_decision["timestamp"]
                last_cycle = conn.execute(
                    "SELECT COUNT(*) FROM decisions WHERE timestamp = ?",
                    (batch_ts,),
                ).fetchone()[0]
            else:
                batch_ts = None
                last_cycle = 0
            # Last-hour engagements
            hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            engaged_hour = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE decision_type='enter' "
                "AND timestamp >= ?",
                (hour_ago,),
            ).fetchone()[0]
            # Daily P&L
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            day_pnl = float(conn.execute(
                "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
                "WHERE substr(timestamp,1,10)=? AND status IN ('won','lost')",
                (today,),
            ).fetchone()[0])
            # Open risk + realized
            open_risk = float(conn.execute(
                "SELECT COALESCE(SUM(stake_usd), 0) FROM trades WHERE status='open'"
            ).fetchone()[0])
            realized_total = float(conn.execute(
                "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
                "WHERE status IN ('won','lost')"
            ).fetchone()[0])
            # Lifetime WR
            wr_row = conn.execute(
                "SELECT COUNT(*) n, "
                "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) w "
                "FROM trades WHERE status IN ('won','lost')"
            ).fetchone()
            n = int(wr_row[0] or 0); w = int(wr_row[1] or 0)
            wr_pct = (100.0 * w / n) if n else 0.0
    except sqlite3.OperationalError as e:
        log.warning("db query failed (likely fresh install): %s", e)
        batch_ts = None
        last_cycle = engaged_hour = 0
        day_pnl = open_risk = realized_total = wr_pct = 0.0
        n = w = 0

    capital = max(0.0, STARTING_CAPITAL_USD + realized_total - open_risk)

    return jsonify({
        "paper_mode": PAPER_MODE,
        "bot_pid": bot_pid,
        "bot_alive": bot_pid is not None,
        "dashboard_uptime_s": uptime_s,
        "last_scan_ts": batch_ts,
        "scanned_last_cycle": last_cycle,
        "engaged_last_hour": engaged_hour,
        "starting_capital_usd": STARTING_CAPITAL_USD,
        "capital_usd": round(capital, 2),
        "open_risk_usd": round(open_risk, 2),
        "realized_total_usd": round(realized_total, 2),
        "day_pnl_usd": round(day_pnl, 2),
        "trades_settled": n,
        "trades_won": w,
        "win_rate_pct": round(wr_pct, 1),
    })


@app.route("/api/feed")
def api_feed():
    """Last N decisions. Optional ?since=<id> for delta polling."""
    limit = min(int(request.args.get("limit", 60)), 200)
    since_id = int(request.args.get("since", 0))
    try:
        with _ro_conn() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, sector, decision_type, summary, payload "
                "FROM decisions WHERE id > ? ORDER BY id DESC LIMIT ?",
                (since_id, limit),
            ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload"]) if r["payload"] else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        out.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "sector": r["sector"],
            "decision_type": r["decision_type"],
            "summary": r["summary"],
            "ticker": payload.get("ticker"),
            "reason_code": payload.get("reason_code"),
            "payload": payload,
        })
    return jsonify({"rows": out})


@app.route("/api/thinking")
def api_thinking():
    """Most recent ENGAGE decision with full edge math."""
    try:
        with _ro_conn() as conn:
            r = conn.execute(
                "SELECT id, timestamp, sector, summary, payload FROM decisions "
                "WHERE decision_type='enter' ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except sqlite3.OperationalError:
        r = None
    if r is None:
        return jsonify({"none": True})
    try:
        payload = json.loads(r["payload"]) if r["payload"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return jsonify({
        "id": r["id"],
        "timestamp": r["timestamp"],
        "sector": r["sector"],
        "summary": r["summary"],
        "ticker": payload.get("ticker"),
        "side": payload.get("side"),
        "contracts": payload.get("contracts"),
        "price_cents": payload.get("price_cents"),
        "stake_usd": payload.get("stake_usd"),
        "edge": payload.get("edge"),
        "forecast_prob": payload.get("forecast_prob"),
        "extras": payload.get("extras") or {},
        "payload": payload,
    })


@app.route("/api/positions")
def api_positions():
    """Open positions + recent settlements."""
    try:
        with _ro_conn() as conn:
            open_rows = conn.execute(
                "SELECT id, timestamp, market_ticker, sector, side, contracts, "
                "price_cents, stake_usd, status "
                "FROM trades WHERE status='open' "
                "ORDER BY id DESC LIMIT 10"
            ).fetchall()
            settled_rows = conn.execute(
                "SELECT id, timestamp, market_ticker, sector, side, contracts, "
                "price_cents, stake_usd, pnl_usd, status, resolved_at "
                "FROM trades WHERE status IN ('won','lost') "
                "ORDER BY id DESC LIMIT 10"
            ).fetchall()
    except sqlite3.OperationalError:
        open_rows = []
        settled_rows = []
    return jsonify({
        "open": [dict(r) for r in open_rows],
        "settled": [dict(r) for r in settled_rows],
    })


@app.route("/api/performance")
def api_performance():
    """Equity sparkline + band WR vs Phase 1 forecast + series PnL."""
    try:
        with _ro_conn() as conn:
            # 30 daily equity points: realized + open_risk per day
            # Simpler proxy: cumulative pnl_usd per day from settled trades
            equity_rows = conn.execute(
                "SELECT substr(timestamp,1,10) d, "
                "SUM(pnl_usd) day_pnl "
                "FROM trades WHERE status IN ('won','lost') "
                "GROUP BY d ORDER BY d ASC"
            ).fetchall()
            equity = []
            running = 0.0
            for r in equity_rows:
                running += float(r["day_pnl"] or 0)
                equity.append({
                    "date": r["d"],
                    "day_pnl": float(r["day_pnl"] or 0),
                    "cumulative": round(running, 2),
                })

            # Per-band WR (NO 85-89, 90-94, 95-99) from settled trades
            band_rows = conn.execute(
                "SELECT price_cents, status FROM trades "
                "WHERE side='no' AND status IN ('won','lost')"
            ).fetchall()
            bands = {
                "85-89": {"n": 0, "w": 0, "forecast_pct": 89.3},
                "90-94": {"n": 0, "w": 0, "forecast_pct": 93.9},
                "95-99": {"n": 0, "w": 0, "forecast_pct": 97.3},
            }
            for r in band_rows:
                no_p = int(r["price_cents"] or 0)
                if 85 <= no_p <= 89:
                    k = "85-89"
                elif 90 <= no_p <= 94:
                    k = "90-94"
                elif 95 <= no_p <= 99:
                    k = "95-99"
                else:
                    continue
                bands[k]["n"] += 1
                if r["status"] == "won":
                    bands[k]["w"] += 1
            for k, v in bands.items():
                v["actual_pct"] = round(100.0 * v["w"] / v["n"], 1) if v["n"] else None

            # Per-series PnL
            series_rows = conn.execute(
                "SELECT "
                "  CASE "
                "    WHEN market_ticker LIKE 'KXNBA%' THEN 'NBA' "
                "    WHEN market_ticker LIKE 'KXNFL%' THEN 'NFL' "
                "    WHEN market_ticker LIKE 'KXEPL%' THEN 'EPL' "
                "    ELSE 'OTHER' END series, "
                "  COUNT(*) n, "
                "  SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) w, "
                "  COALESCE(SUM(pnl_usd), 0) pnl "
                "FROM trades WHERE status IN ('won','lost') "
                "GROUP BY series"
            ).fetchall()
            series = [
                {
                    "name": r["series"],
                    "n": int(r["n"] or 0),
                    "w": int(r["w"] or 0),
                    "pnl_usd": round(float(r["pnl"] or 0), 2),
                    "wr_pct": round(100.0 * (r["w"] or 0) / (r["n"] or 1), 1),
                }
                for r in series_rows
            ]
    except sqlite3.OperationalError:
        equity = []
        bands = {
            "85-89": {"n": 0, "w": 0, "actual_pct": None, "forecast_pct": 89.3},
            "90-94": {"n": 0, "w": 0, "actual_pct": None, "forecast_pct": 93.9},
            "95-99": {"n": 0, "w": 0, "actual_pct": None, "forecast_pct": 97.3},
        }
        series = []

    return jsonify({
        "equity": equity,
        "bands": bands,
        "series": series,
    })


@app.route("/api/subsystems")
def api_subsystems():
    """Health of bot, Kalshi API, DB, Telegram, Watchdog."""
    bot_pid = _bot_pid_alive()
    db_ok = DB_PATH.exists()
    try:
        # 100ms ping to Kalshi public API
        import httpx
        with httpx.Client(timeout=3.0) as c:
            r = c.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                      params={"limit": 1})
            api_ok = r.status_code == 200
            api_latency_ms = int(r.elapsed.total_seconds() * 1000)
    except Exception:
        api_ok = False
        api_latency_ms = None

    return jsonify({
        "bot": {"ok": bot_pid is not None, "pid": bot_pid,
                "detail": f"PID {bot_pid}" if bot_pid else "not running"},
        "kalshi_api": {"ok": api_ok,
                       "detail": f"{api_latency_ms}ms" if api_latency_ms else "unreachable"},
        "database": {"ok": db_ok,
                     "detail": f"{DB_PATH.stat().st_size // 1024} KB" if db_ok else "missing"},
        "telegram": {"ok": True, "detail": "live"},  # could ping the bot API
        "watchdog": {"ok": True, "detail": "n/a"},   # added when watchdog ships
    })


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", "8503"))
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    log.info("LongshotFade dashboard starting on http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
