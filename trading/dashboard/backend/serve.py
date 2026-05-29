"""ORB dashboard backend.

Read-only Flask API + serves the React build from ./static/. Schema:
trades, signal_history, agent_journal, arm_status.json, active_orders.json.

API:
  GET /api/health     — healthcheck
  GET /api/summary    — today/WTD/lifetime P&L, WR, paper flag, arm status
  GET /api/trades     — recent trades with full score breakdown
  GET /api/equity     — cumulative P&L over last 30 days (for chart)
  GET /api/learning   — agent_journal rows (knob proposals/applied/digests)
  GET /api/live       — arm_status + active_orders (open positions)
  GET /api/signals    — signal_history including blocked ones

Reads from trading/journal.db (SQLite) and trading/state/*.json. No writes,
no coupling to the running bot. Safe to run continuously.

Port 8502 (vacated by OmniAlpha when it moved to 8503).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Allow imports from trading/ root (config, etc.)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
JOURNAL_DB = BASE_DIR / "journal.db"
STATE_DIR = BASE_DIR / "state"
STATIC_DIR = Path(__file__).parent / "static"
SERVE_PORT = 8502

# Starting capital — pulled lazily from trading/config.py so the dashboard
# stays in sync if Zach ever changes it. Falls back to 5000 if import fails.
def _starting_capital() -> float:
    try:
        from config import STARTING_CAPITAL
        return float(STARTING_CAPITAL)
    except Exception:
        return 5000.0


def _baseline_adjustment() -> float:
    """One-time reconciliation offset (USD) added to journal-computed capital.

    The journal historically over-booked losses (exits were recorded at the
    theoretical SL/T2 level, not the real fill — fixed going forward by Phase 1
    on 2026-05-22). That left journal-computed capital ~$313 below the real
    broker balance and spammed the watchdog balance-discrepancy alert. This
    fixed offset re-baselines computed → real at the moment Phase 1 went live.
    Future real discrepancies (beyond this offset) still trip the alert.
    Stored in state/journal_baseline.json so it's auditable, not hidden in code.
    """
    try:
        f = STATE_DIR / "journal_baseline.json"
        if f.exists():
            return float(json.loads(f.read_text(encoding="utf-8")).get("adjustment_usd") or 0.0)
    except Exception:
        pass
    return 0.0


def _real_broker_balance() -> tuple[float | None, str | None]:
    """Pull the LATEST real TV broker available_funds from broker_state.json.

    The bot writes this every 60s in reconcile_tv_state. If the file is
    fresh (< 5 min), use it as authoritative; if stale or missing, return
    None so caller falls back to journal-computed capital.

    Audit 2026-05-18 fix: dashboard was computing capital as
      $5,000 + sum(journal.pnl_after_slippage)
    which silently lied when there was a phantom position the bot didn't
    know about. Today's $550 phantom-position loss was invisible because
    of this — Zach saw $5,366 in dashboard while real broker was $4,816.
    Now we surface the real number AND flag any discrepancy.
    """
    state_file = STATE_DIR / "broker_state.json"
    if not state_file.exists():
        return (None, "broker_state.json missing — bot hasn't written it yet")
    try:
        with open(state_file, "r") as f:
            data = json.load(f)
        avail = data.get("available_funds")
        updated_at = data.get("updated_at")
        if avail is None:
            return (None, "broker_state has no available_funds")
        # Freshness check — if older than 5 min, broker data is stale
        if updated_at:
            try:
                # Tolerate both "Z" suffix and explicit "+00:00"
                ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                age_s = (datetime.now(ts.tzinfo).timestamp() - ts.timestamp())
                if age_s > 300:
                    return (None, f"broker_state stale ({int(age_s)}s old)")
            except Exception:
                pass
        return (float(avail), None)
    except Exception as e:
        return (None, f"broker_state read error: {e}")

app = Flask(__name__, static_folder=None)
CORS(app, origins=[
    f"http://localhost:{SERVE_PORT}",
    f"http://127.0.0.1:{SERVE_PORT}",
    "http://localhost:5173",  # Vite dev server
])


# ─── DB helper ───────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    """Read-only connection to journal.db.

    Uses URI form with mode=ro so even bugs in this server can never
    write to or lock the journal that the live bot is using.
    """
    uri = f"file:{JOURNAL_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def _read_state_json(name: str) -> dict | None:
    """Read a state JSON file (arm_status, active_orders, etc.)."""
    path = STATE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _paper_mode() -> bool:
    """Best-effort read of PAPER_MODE from trading/.env."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return True  # default to paper for safety
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("PAPER_MODE"):
            _, _, val = line.partition("=")
            return val.strip().lower() in ("true", "1", "yes")
    return True


# ─── API ────────────────────────────────────────────────────────────────


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "ts": time.time()})


@app.route("/api/summary")
def api_summary():
    """Top-of-page stat cards.

    Returns:
      - today_trades, today_wins, today_losses, today_pnl_usd
      - wtd_trades, wtd_pnl_usd (Monday-current)
      - lifetime_trades, lifetime_wins, lifetime_losses, lifetime_pnl_usd, lifetime_wr
      - paper_mode, armed (from arm_status.json)
      - open_positions (count from active_orders.json)
    """
    starting_capital = _starting_capital()
    if not JOURNAL_DB.exists():
        return jsonify({
            "paper_mode": _paper_mode(),
            "armed": False,
            "today_trades": 0, "today_wins": 0, "today_losses": 0, "today_pnl_usd": 0.0,
            "wtd_trades": 0, "wtd_pnl_usd": 0.0,
            "lifetime_trades": 0, "lifetime_wins": 0, "lifetime_losses": 0,
            "lifetime_pnl_usd": 0.0, "lifetime_wr": None,
            "open_positions": 0,
            "starting_capital_usd": starting_capital,
            "current_capital_usd": starting_capital,
            "return_pct": 0.0,
        })

    today = datetime.now().strftime("%Y-%m-%d")
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")

    with _conn() as conn:
        today_row = conn.execute(
            "SELECT COUNT(*) n, "
            "SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) w, "
            "SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) l, "
            "COALESCE(SUM(pnl_after_slippage),0) pnl "
            "FROM trades WHERE date=? AND outcome IN ('WIN','LOSS')",
            (today,),
        ).fetchone()
        wtd_row = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(pnl_after_slippage),0) pnl "
            "FROM trades WHERE date>=? AND outcome IN ('WIN','LOSS')",
            (week_start,),
        ).fetchone()
        life_row = conn.execute(
            "SELECT COUNT(*) n, "
            "SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) w, "
            "SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) l, "
            "COALESCE(SUM(pnl_after_slippage),0) pnl, "
            "COALESCE(SUM(pnl),0) pnl_raw "
            "FROM trades WHERE outcome IN ('WIN','LOSS')"
        ).fetchone()

    arm = _read_state_json("arm_status") or {}
    armed = bool(arm.get("armed")) if arm.get("date") == today else False

    active_doc = _read_state_json("active_orders") or {}
    orders = active_doc.get("orders", {}) if isinstance(active_doc, dict) else {}
    open_count = sum(1 for v in orders.values() if isinstance(v, dict)) if isinstance(orders, dict) else 0

    lifetime_wr = None
    if life_row["n"]:
        lifetime_wr = round(life_row["w"] / life_row["n"] * 100, 1)

    lifetime_pnl = float(life_row["pnl"] or 0)            # after-slippage — conservative PERFORMANCE view
    lifetime_pnl_raw = float(life_row["pnl_raw"] or 0)    # raw fills — matches the real broker balance

    # CAPITAL RECONCILIATION must use RAW pnl, not after-slippage.
    # The journal applies a synthetic SLIPPAGE_PTS (2pt=$4) haircut per trade
    # to pnl_after_slippage for conservative performance display. The real TV
    # paper broker has NO such synthetic haircut — its balance reflects actual
    # fills (= raw pnl). Summing after-slippage here made computed_capital fall
    # $4/trade below the broker, so the watchdog balance-discrepancy alert
    # re-fired every ~25 trades and we band-aided it with journal_baseline
    # re-bases (twice). Using raw pnl makes computed track the broker exactly
    # and permanently — no more drift, no more re-baselining.
    computed_capital = starting_capital + lifetime_pnl_raw + _baseline_adjustment()

    # Real broker balance (authoritative) vs journal-computed (optimistic).
    # If the bot wrote a fresh broker_state, use the real number; otherwise
    # fall back to computed. Always expose BOTH + a discrepancy flag so the
    # UI can warn about untracked phantom positions / hidden losses.
    real_balance, real_balance_err = _real_broker_balance()
    if real_balance is not None:
        current_capital = real_balance
        capital_source = "broker_live"
    else:
        current_capital = computed_capital
        capital_source = f"journal_computed_fallback ({real_balance_err})"

    discrepancy_usd = round(computed_capital - current_capital, 2)
    return_pct = ((current_capital - starting_capital) / starting_capital * 100) if starting_capital else 0.0

    return jsonify({
        "paper_mode": _paper_mode(),
        "armed": armed,
        "today_trades": today_row["n"] or 0,
        "today_wins": today_row["w"] or 0,
        "today_losses": today_row["l"] or 0,
        "today_pnl_usd": round(today_row["pnl"] or 0, 2),
        "wtd_trades": wtd_row["n"] or 0,
        "wtd_pnl_usd": round(wtd_row["pnl"] or 0, 2),
        "lifetime_trades": life_row["n"] or 0,
        "lifetime_wins": life_row["w"] or 0,
        "lifetime_losses": life_row["l"] or 0,
        "lifetime_pnl_usd": round(lifetime_pnl, 2),
        "lifetime_wr": lifetime_wr,
        "open_positions": open_count,
        "starting_capital_usd": round(starting_capital, 2),
        "current_capital_usd": round(current_capital, 2),
        "capital_source": capital_source,
        "computed_capital_usd": round(computed_capital, 2),
        "untracked_pnl_usd": discrepancy_usd,  # >0 means real balance is LOWER than journal expects (hidden losses)
        "return_pct": round(return_pct, 2),
    })


@app.route("/api/trades")
def api_trades():
    """Recent trades with full scoring breakdown.

    Query params:
      - days: lookback window (default 30)
      - limit: max rows (default 100)
    """
    days = int(request.args.get("days", 30))
    limit = min(int(request.args.get("limit", 100)), 500)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if not JOURNAL_DB.exists():
        return jsonify({"trades": []})

    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, date, time, direction, score, breakdown, entry, stop, "
            "target_1, target_2, exit_price, outcome, pnl_after_slippage, rr, "
            "size, was_second_break, vix_at_entry, rvol_at_entry, notes, "
            "setup_type, orb_high, orb_low, orb_candle_direction "
            "FROM trades WHERE date >= ? "
            "ORDER BY id DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()

    trades = []
    for r in rows:
        d = dict(r)
        # Decode breakdown JSON into structured dict
        bd_raw = d.pop("breakdown") or "{}"
        try:
            d["breakdown"] = json.loads(bd_raw)
        except (json.JSONDecodeError, TypeError):
            d["breakdown"] = {}
        d["was_second_break"] = bool(d.get("was_second_break"))
        trades.append(d)
    return jsonify({"trades": trades})


@app.route("/api/equity")
def api_equity():
    """Daily P&L points for the equity chart (last 30 days)."""
    if not JOURNAL_DB.exists():
        return jsonify({"points": []})
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, COUNT(*) n, "
            "SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) wins, "
            "SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) losses, "
            "COALESCE(SUM(pnl_after_slippage),0) pnl "
            "FROM trades WHERE date >= ? AND outcome IN ('WIN','LOSS') "
            "GROUP BY date ORDER BY date",
            (cutoff,),
        ).fetchall()

    points = []
    cum = 0.0
    for r in rows:
        cum += float(r["pnl"] or 0)
        points.append({
            "date": r["date"],
            "trades": r["n"],
            "wins": r["wins"],
            "losses": r["losses"],
            "daily_pnl": round(float(r["pnl"] or 0), 2),
            "cumulative_pnl": round(cum, 2),
        })
    return jsonify({"points": points})


@app.route("/api/learning")
def api_learning():
    """Learning agent activity feed (knob proposals, applied changes, digests)."""
    days = int(request.args.get("days", 30))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if not JOURNAL_DB.exists():
        return jsonify({"entries": []})
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, date, created_at, entry_type, subject, knob, "
            "current_value, proposed_value, sample_size, confidence, "
            "reasoning, source, status, applied_at, data "
            "FROM agent_journal WHERE date >= ? "
            "ORDER BY id DESC",
            (cutoff,),
        ).fetchall()
    entries = []
    for r in rows:
        d = dict(r)
        if d.get("data"):
            try:
                d["data"] = json.loads(d["data"])
            except (json.JSONDecodeError, TypeError):
                pass
        entries.append(d)
    return jsonify({"entries": entries})


@app.route("/api/live")
def api_live():
    """Current bot state: arm status + open positions."""
    arm = _read_state_json("arm_status") or {}
    active_doc = _read_state_json("active_orders") or {}
    today = datetime.now().strftime("%Y-%m-%d")
    # arm_status is per-day; stale rows mean not-armed today
    armed_today = arm.get("date") == today and bool(arm.get("armed"))

    # active_orders.json shape: {"orders": {trade_id: {...}}, "_updated_at": "..."}
    # Unwrap "orders" and defensively skip any non-dict values.
    orders = active_doc.get("orders", {}) if isinstance(active_doc, dict) else {}
    positions = []
    if isinstance(orders, dict):
        for tid, order in orders.items():
            if not isinstance(order, dict):
                continue
            positions.append({
                "trade_id": tid,
                "direction": order.get("direction"),
                "entry": order.get("entry"),
                "stop": order.get("stop"),
                "target_1": order.get("target_1"),
                "target_2": order.get("target_2"),
                "opened_at": order.get("opened_at"),
                "t1_hit": order.get("t1_hit", False),
                "virtual_stop": order.get("virtual_stop"),
                "mfe_price": order.get("mfe_price"),
                "stall_locked": order.get("stall_locked", False),
                "pre_t1_be_armed": order.get("pre_t1_be_armed", False),
            })
    return jsonify({
        "armed_today": armed_today,
        "arm_status": arm,
        "open_positions": positions,
    })


@app.route("/api/signals")
def api_signals():
    """Signal evaluation feed including blocked entries (block_reason set)."""
    days = int(request.args.get("days", 14))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if not JOURNAL_DB.exists():
        return jsonify({"signals": []})
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, date, time, direction, price, score, size, "
            "was_second_break, block_reason, breakdown "
            "FROM signal_history WHERE date >= ? "
            "ORDER BY id DESC LIMIT 200",
            (cutoff,),
        ).fetchall()
    signals = []
    for r in rows:
        d = dict(r)
        bd_raw = d.pop("breakdown") or "{}"
        try:
            d["breakdown"] = json.loads(bd_raw)
        except (json.JSONDecodeError, TypeError):
            d["breakdown"] = {}
        d["was_second_break"] = bool(d.get("was_second_break"))
        signals.append(d)
    return jsonify({"signals": signals})


# ─── Static file serving (SPA fallback) ─────────────────────────────────


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    if path and (STATIC_DIR / path).exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


def main():
    if not STATIC_DIR.exists():
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        # Drop a tiny placeholder if frontend hasn't been built yet
        placeholder = STATIC_DIR / "index.html"
        if not placeholder.exists():
            placeholder.write_text(
                "<!doctype html><html><head><title>ORB Dashboard</title></head>"
                "<body style='font-family:system-ui;padding:2rem;background:#0b1220;color:#e6edf3'>"
                "<h1>ORB Dashboard — API Live</h1>"
                "<p>Backend running on port 8502. React UI not built yet.</p>"
                "<p>Try: <code>/api/health</code> · <code>/api/summary</code> · "
                "<code>/api/trades</code> · <code>/api/equity</code> · "
                "<code>/api/learning</code> · <code>/api/live</code> · "
                "<code>/api/signals</code></p>"
                "</body></html>",
                encoding="utf-8",
            )
    print("\n" + "=" * 55)
    print("  ORB — War Room")
    print(f"  Local  -> http://localhost:{SERVE_PORT}")
    print("=" * 55 + "\n", flush=True)
    app.run(host="0.0.0.0", port=SERVE_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
