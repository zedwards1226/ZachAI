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

from config import FLASK_HOST, FLASK_PORT, PAPER_MODE, KALSHI_DEMO, INTERNAL_API_SECRET
from database import (
    init_db, get_trades, get_latest_forecasts, get_pnl_history,
    get_summary, get_guardrail_state, log_decision, get_decision_log,
    get_signals, get_equity_curve, get_calibration, get_trades_with_verification,
    get_today_stats, get_city_performance,
)
from guardrails import guardrail_status, set_window_override
from scheduler import start_scheduler, trigger_scan_now
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
# CORS: only the dashboard + Vite dev server need cross-origin access.
CORS(app, origins=["http://localhost:3001", "http://127.0.0.1:3001",
                   "http://localhost:5173", "http://127.0.0.1:5173"])


@app.before_request
def _require_internal_secret():
    """Gate every POST (and other state-changing methods) on the shared
    secret. GETs are read-only and stay open so the dashboard proxy and
    health checks keep working without extra wiring."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        import hmac
        sent = request.headers.get("X-Internal-Secret", "")
        if not hmac.compare_digest(sent, INTERNAL_API_SECRET):
            return jsonify({"error": "forbidden"}), 403

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


@app.route("/api/today")
def today_stats():
    return jsonify(get_today_stats())


@app.route("/api/by-city")
def by_city():
    return jsonify(get_city_performance())


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
                elif atype == "skipped_duplicate":
                    reason = action.get("reason", "already in position")
                    msg = f"{city}: skipped — {reason}"
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


@app.route("/api/guardrails/window-override", methods=["POST"])
def window_override():
    enabled = request.json.get("enabled", True) if request.is_json else True
    set_window_override(enabled)
    log_decision(
        type="system",
        message=f"Trade window override {'ENABLED' if enabled else 'DISABLED'} by user",
    )
    return jsonify({"ok": True, "window_override": enabled})


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


@app.route("/api/signals")
def signals():
    limit = int(request.args.get("limit", 100))
    return jsonify(get_signals(limit))


@app.route("/api/equity-curve")
def equity_curve():
    return jsonify(get_equity_curve())


@app.route("/api/calibration")
def calibration():
    return jsonify(get_calibration())


@app.route("/api/agent-journal")
def agent_journal():
    from database import get_agent_journal
    limit = int(request.args.get("limit", 100))
    category = request.args.get("category")
    return jsonify(get_agent_journal(limit=limit, category=category))


@app.route("/api/agent-state")
def agent_state_endpoint():
    from database import agent_state_all, get_city_cooldowns
    from learning_agent import effective_min_edge
    return jsonify({
        "state": agent_state_all(),
        "effective_min_edge": effective_min_edge(),
        "city_cooldowns": get_city_cooldowns(),
    })


@app.route("/api/agent-review", methods=["POST"])
def agent_review():
    """Manually trigger a learning agent review (also runs daily at 6:30 PM)."""
    from learning_agent import run_review
    try:
        result = run_review()
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/trades/verified")
def trades_verified():
    limit = int(request.args.get("limit", 100))
    return jsonify(get_trades_with_verification(limit))


@app.route("/api/positions")
def positions():
    """Open trades enriched with live Kalshi prices and unrealized P&L."""
    from kalshi_client import get_client
    from database import get_open_trades
    client = get_client()
    open_trades = get_open_trades()
    positions = []
    # Deduplicate market tickers for batch price fetch
    price_cache = {}
    for t in open_trades:
        mid = t["market_id"]
        if mid not in price_cache:
            try:
                m = client.get_market(mid)
                if m:
                    # Kalshi API v2 returns prices as dollar strings: "0.0200" = 2 cents
                    yes_bid = m.get("yes_bid_dollars") or m.get("yes_bid")
                    no_bid = m.get("no_bid_dollars") or m.get("no_bid")
                    yes_ask = m.get("yes_ask_dollars") or m.get("yes_ask")
                    no_ask = m.get("no_ask_dollars") or m.get("no_ask")
                    price_cache[mid] = {
                        "yes_bid": round(float(yes_bid) * 100) if yes_bid else None,
                        "no_bid": round(float(no_bid) * 100) if no_bid else None,
                        "yes_ask": round(float(yes_ask) * 100) if yes_ask else None,
                        "no_ask": round(float(no_ask) * 100) if no_ask else None,
                        "title": m.get("title", ""),
                        "volume": m.get("volume_24h_fp"),
                    }
                else:
                    price_cache[mid] = None
            except Exception:
                price_cache[mid] = None

    for t in open_trades:
        mid = t["market_id"]
        live = price_cache.get(mid)
        entry_price = t["price_cents"]
        side = t["side"]  # YES or NO
        contracts = t["contracts"]
        stake = t["stake_usd"]

        # Current market bid for our side (what we could sell at)
        current_price = None
        ask_price = None
        if live:
            if side == "YES":
                current_price = live.get("yes_bid")
                ask_price = live.get("yes_ask")
            else:
                current_price = live.get("no_bid")
                ask_price = live.get("no_ask")

        # Unrealized P&L = contracts * (current_price - entry_price) / 100
        if current_price is not None and current_price > 0:
            unrealized_pnl = round(contracts * (current_price - entry_price) / 100, 2)
        else:
            unrealized_pnl = None

        positions.append({
            "id": t["id"],
            "city": t["city"],
            "market_id": mid,
            "side": side,
            "contracts": contracts,
            "entry_price": entry_price,
            "current_price": current_price,
            "ask_price": ask_price,
            "stake": stake,
            "edge": t["edge"],
            "unrealized_pnl": unrealized_pnl,
            "timestamp": t["timestamp"],
            "title": live.get("title", "") if live else "",
            "volume": live.get("volume") if live else None,
        })
    total_unrealized = sum(p["unrealized_pnl"] for p in positions if p["unrealized_pnl"] is not None)
    return jsonify({"positions": positions, "total_unrealized_pnl": round(total_unrealized, 2)})


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


@app.route("/api/monitor/check")
def monitor_check():
    """One-shot health check — same logic as monitor.py, returns JSON report."""
    from database import get_open_trades, get_summary, get_guardrail_state
    from kalshi_client import get_client
    issues = []

    # Kalshi connection
    try:
        connected = get_client()._ready
        if not connected:
            issues.append("Kalshi API disconnected")
    except Exception as e:
        issues.append(f"Kalshi check error: {e}")

    # Duplicate open trades
    open_trades = get_open_trades()
    market_ids = [t["market_id"] for t in open_trades]
    dupes = [mid for mid in set(market_ids) if market_ids.count(mid) > 1]
    if dupes:
        issues.append(f"Duplicate open trades: {', '.join(dupes)}")

    # Guardrail state
    gs = get_guardrail_state()
    if gs.get("halted"):
        issues.append(f"Bot halted: {gs.get('halt_reason', 'unknown')}")
    if gs.get("daily_pnl_usd", 0) < -15:
        issues.append(f"Daily P&L critical: ${gs['daily_pnl_usd']:.2f}")

    # Open trade count sanity
    if len(open_trades) > 12:
        issues.append(f"Too many open trades: {len(open_trades)}")

    summary = get_summary()
    return jsonify({
        "ok": len(issues) == 0,
        "issues": issues,
        "open_trades": len(open_trades),
        "total_trades": summary.get("total_trades", 0),
        "checked_at": __import__("datetime").datetime.utcnow().isoformat(),
    })


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": str(e)}), 500


def create_app():
    init_db()
    # NOTE: scheduler is started in __main__ only — not here.
    # Starting it here AND in __main__ causes every job to fire twice.
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
