"""ICTBot Flask dashboard on :3002.

READ-ONLY view of state. Never writes, never places orders. Used to verify
the bot is alive, see today's setups, and check journal entries.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import pytz
from flask import Flask, jsonify, render_template

# Ensure repo root on path so config + services + data_layer import
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (  # noqa: E402
    TIMEZONE, ICT_SYMBOL, PAPER_MODE, SCAN_ONLY, DASHBOARD_PORT,
)
from data_layer.database import (  # noqa: E402
    init_db, fetch_recent_trades, fetch_today_setups, fetch_open_position,
    equity_curve, get_connection, DB_PATH,
)
from services.state_manager import (  # noqa: E402
    read_arm_status, can_trade_now, pnl_today, pnl_week, trades_today,
    consecutive_losses, is_cross_bot_halted, orb_arm_status,
)
from services.ict_tv_client import health_check as cdp_health  # noqa: E402

ET = pytz.timezone(TIMEZONE)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
init_db()


@app.route("/")
def index():
    return render_template("index.html",
                           symbol=ICT_SYMBOL,
                           paper_mode=PAPER_MODE,
                           scan_only=SCAN_ONLY)


@app.route("/api/status")
def api_status():
    arm = read_arm_status()
    halted, halt_reason = is_cross_bot_halted()
    can, reason = can_trade_now()
    cdp_ok, cdp_msg = cdp_health()
    open_pos = fetch_open_position(ICT_SYMBOL)
    return jsonify({
        "now_et": datetime.now(ET).isoformat(),
        "symbol": ICT_SYMBOL,
        "paper_mode": PAPER_MODE,
        "scan_only": SCAN_ONLY,
        "arm": arm,
        "cross_bot_halted": halted,
        "halt_reason": halt_reason,
        "can_trade": can,
        "can_trade_reason": reason,
        "cdp_ok": cdp_ok,
        "cdp_msg": cdp_msg,
        # Backwards-compat aliases for older dashboard payload consumers
        "cdp_9223_ok": cdp_ok,
        "cdp_9223_msg": cdp_msg,
        "trades_today": trades_today(),
        "pnl_today": pnl_today(),
        "pnl_week": pnl_week(),
        "consecutive_losses": consecutive_losses(),
        "open_position": open_pos,
        "orb_arm": orb_arm_status(),
    })


@app.route("/api/today-setups")
def api_today_setups():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    return jsonify({"date": today, "setups": fetch_today_setups(today)})


@app.route("/api/recent-trades")
def api_recent_trades():
    return jsonify({"trades": fetch_recent_trades(30)})


@app.route("/api/equity-curve")
def api_equity_curve():
    return jsonify({"curve": [{"date": d, "cum_pnl": p} for d, p in equity_curve()]})


@app.route("/api/edge-stats")
def api_edge_stats():
    with get_connection(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT s.setup_name, COUNT(t.id) AS trades, "
            "  COALESCE(SUM(CASE WHEN t.pnl_dollars > 0 THEN 1 ELSE 0 END), 0) AS wins, "
            "  COALESCE(AVG(t.pnl_r), 0) AS avg_r, "
            "  COALESCE(SUM(t.pnl_dollars), 0) AS total_pnl "
            "FROM setups s LEFT JOIN trades t ON t.setup_id = s.id "
            "WHERE t.exit_time IS NOT NULL "
            "GROUP BY s.setup_name"
        ).fetchall()
    stats = []
    for r in rows:
        n = r["trades"] or 0
        w = r["wins"] or 0
        stats.append({
            "setup_name": r["setup_name"],
            "trades": n,
            "wins": w,
            "win_rate": round(w / n, 3) if n else 0.0,
            "avg_r": round(r["avg_r"], 3) if r["avg_r"] else 0.0,
            "total_pnl": round(r["total_pnl"], 2) if r["total_pnl"] else 0.0,
        })
    return jsonify({"stats": stats})


def main():
    app.run(host="127.0.0.1", port=DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
