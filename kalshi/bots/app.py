"""
WeatherAlpha Flask API
Endpoints:
  GET  /api/health
  GET  /api/status
  GET  /api/forecasts
  GET  /api/trades?limit=100
  GET  /api/pnl
  GET  /api/guardrails
  GET  /api/summary
  POST /api/scan        — trigger immediate scan
  POST /api/resolve     — trigger trade resolution
"""
import logging
import sys
import os

# Ensure bots directory is on path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import FLASK_HOST, FLASK_PORT, PAPER_MODE, KALSHI_DEMO
from database import (
    init_db, get_trades, get_latest_forecasts, get_pnl_history,
    get_summary, get_guardrail_state, log_decision, get_decision_log
)
from guardrails import guardrail_status
from scheduler import start_scheduler, stop_scheduler, trigger_scan_now
from trader import resolve_expired_trades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("weatheralpha.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="*")

# Module-level scan state tracker
_scan_status = {
    "is_scanning": False,
    "current_city": None,
    "last_scan_time": None,
    "next_scan_time": None,
    "last_results": [],
}


@app.route("/api/health")
def health():
    from kalshi_client import get_client
    connected = get_client()._ready
    return jsonify({"status": "ok", "paper_mode": PAPER_MODE, "demo": KALSHI_DEMO,
                    "kalshi_connected": connected})


@app.route("/api/status")
def status():
    summary  = get_summary()
    gs       = guardrail_status()
    from config import STARTING_CAPITAL
    return jsonify({
        "paper_mode":   PAPER_MODE,
        "kalshi_demo":  KALSHI_DEMO,
        "summary":      summary,
        "guardrails":   gs,
        "capital_usd":  round(STARTING_CAPITAL + summary["total_pnl_usd"], 2),
    })


@app.route("/api/forecasts")
def forecasts():
    return jsonify(get_latest_forecasts())


@app.route("/api/trades")
def trades():
    limit = int(request.args.get("limit", 100))
    return jsonify(get_trades(limit))


@app.route("/api/pnl")
def pnl():
    limit = int(request.args.get("limit", 200))
    rows  = get_pnl_history(limit)
    rows.reverse()   # chronological order for chart
    return jsonify(rows)


@app.route("/api/guardrails")
def guardrails_endpoint():
    return jsonify(guardrail_status())


@app.route("/api/summary")
def summary():
    return jsonify(get_summary())


@app.route("/api/scan", methods=["POST"])
def scan():
    from datetime import datetime as _dt
    _scan_status["is_scanning"] = True
    _scan_status["last_scan_time"] = _dt.utcnow().isoformat()
    try:
        actions = trigger_scan_now()
        _scan_status["last_results"] = actions if isinstance(actions, list) else []
        # Persist each action to decision_log
        if isinstance(actions, list):
            for action in actions:
                atype = action.get("action", "scan")
                city  = action.get("city", "")
                edge  = action.get("edge")
                # Build a human-readable message
                if atype == "traded":
                    msg = (f"{city}: {action.get('side','?')} {action.get('contracts',0)}ct "
                           f"@ {action.get('price',0)}¢ | edge {round((edge or 0)*100,1)}% "
                           f"stake ${action.get('stake',0):.2f}")
                elif atype == "blocked":
                    reasons = action.get("reasons") or action.get("reason") or []
                    if isinstance(reasons, list):
                        reasons = "; ".join(reasons)
                    msg = f"{city}: blocked — {reasons}"
                elif atype == "error":
                    msg = f"{city}: error — {action.get('error','unknown')}"
                else:
                    msg = f"{city}: {atype}"
                log_decision(
                    type=atype,
                    message=msg,
                    city=city,
                    edge=edge,
                    contracts=action.get("contracts"),
                    side=action.get("side"),
                    price_cents=action.get("price"),
                    stake_usd=action.get("stake"),
                    reason="; ".join(action.get("reasons", [])) if isinstance(action.get("reasons"), list) else action.get("reason"),
                )
            if not actions:
                log_decision(type="scan", message="Scan complete — no tradeable edges found")
        else:
            log_decision(type="scan", message="Manual scan triggered", reason="no structured results")
        return jsonify({"ok": True, "actions": actions})
    except Exception as exc:
        log.error("Manual scan error: %s", exc)
        log_decision(type="error", message=f"Manual scan error: {exc}")
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        _scan_status["is_scanning"] = False


@app.route("/api/resolve", methods=["POST"])
def resolve():
    try:
        resolve_expired_trades()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/decision-log")
def decision_log():
    limit = int(request.args.get("limit", 100))
    since = request.args.get("since")
    entries = get_decision_log(limit=limit, since=since)
    return jsonify({"entries": entries, "count": len(entries)})


@app.route("/api/scan/status")
def scan_status():
    return jsonify(_scan_status)


@app.route("/api/markets/browse")
def markets_browse():
    from kalshi_client import get_client
    series = request.args.get("series", "KXHIGHNY")
    limit = int(request.args.get("limit", 20))
    client = get_client()
    try:
        markets = client.search_kxhigh_markets(series)
        return jsonify({"markets": markets[:limit], "series": series})
    except Exception as e:
        return jsonify({"markets": [], "error": str(e)})


@app.route("/api/markets/all")
def markets_all():
    from kalshi_client import get_client
    from config import CITIES
    client = get_client()
    all_markets = []
    for city_code, city_info in CITIES.items():
        try:
            markets = client.search_kxhigh_markets(city_code)
            for m in markets:
                m["city"] = city_code
                m["city_name"] = city_info["name"]
            all_markets.extend(markets)
        except Exception:
            pass
    return jsonify({"markets": all_markets, "count": len(all_markets)})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": str(e)}), 500


def create_app():
    init_db()
    start_scheduler()
    return app


if __name__ == "__main__":
    import socket
    init_db()
    start_scheduler()

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "?.?.?.?"

    print("\n" + "=" * 55)
    print("  WeatherAlpha Trading Bot API")
    print(f"  Mode:    {'PAPER' if PAPER_MODE else 'LIVE'} / {'DEMO' if KALSHI_DEMO else 'PRODUCTION'}")
    print(f"  Local  -> http://localhost:{FLASK_PORT}")
    print(f"  Network-> http://{local_ip}:{FLASK_PORT}")
    print("=" * 55 + "\n")

    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)
