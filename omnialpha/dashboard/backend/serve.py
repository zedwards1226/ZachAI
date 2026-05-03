"""OmniAlpha dashboard backend.

Serves the React build from ./static/ and exposes a tiny API:
  GET /api/summary    — bankroll, today P&L, win rate, open count, paper flag
  GET /api/positions  — open positions with strike + current price + 30m history
  GET /api/activity   — combined feed: closed trades + recent log entries
  GET /api/health     — healthcheck

All read-only against the SQLite store at ../state/omnialpha.db. Live crypto
prices via dashboard/feeds.py (CoinGecko free tier).

Port 8503 (separate from Streamlit 8502 so we can keep the old one as
fallback while testing the React version).
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path

# Allow imports from the omnialpha root (config, data_layer, dashboard.feeds)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import DB_PATH, PAPER_MODE, STARTING_CAPITAL_USD
from data_layer.database import get_conn
from dashboard.feeds import fetch_crypto_history, fetch_crypto_prices

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
SERVE_PORT = 8503

app = Flask(__name__, static_folder=None)
CORS(app, origins=["http://localhost:8503", "http://127.0.0.1:8503", "http://localhost:5173"])


# ─── Cache helpers ──────────────────────────────────────────────────────
# Keep external HTTP traffic to free APIs under control.
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl_s: float, fn):
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < ttl_s:
        return cached[1]
    value = fn()
    _cache[key] = (now, value)
    return value


def _live_prices() -> dict:
    return _cached("crypto_prices", 10.0, fetch_crypto_prices)


def _btc_history() -> list:
    return _cached("btc_history", 30.0, lambda: fetch_crypto_history("bitcoin", minutes=30))


def _eth_history() -> list:
    return _cached("eth_history", 30.0, lambda: fetch_crypto_history("ethereum", minutes=30))


# ─── API ─────────────────────────────────────────────────────────────────


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "ts": time.time()})


@app.route("/api/summary")
def api_summary():
    if not DB_PATH.exists():
        return jsonify({
            "paper_mode": PAPER_MODE,
            "kalshi_ok": None,
            "starting_capital_usd": STARTING_CAPITAL_USD,
            "capital_usd": STARTING_CAPITAL_USD,
            "today_pnl_usd": 0.0,
            "wins": 0,
            "losses": 0,
            "open_positions": 0,
            "win_rate_pct": None,
        })
    with get_conn(readonly=True) as conn:
        row = conn.execute(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN status IN ('won','lost') THEN pnl_usd END), 0) realized, "
            "  COALESCE(SUM(CASE WHEN status='open' THEN stake_usd END), 0) open_risk, "
            "  SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) wins, "
            "  SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) losses, "
            "  SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) open_count "
            "FROM trades"
        ).fetchone()
        today = conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
            "WHERE substr(timestamp, 1, 10) = date('now') "
            "AND status IN ('won','lost')"
        ).fetchone()[0]

    realized = float(row["realized"] or 0)
    wins = int(row["wins"] or 0)
    losses = int(row["losses"] or 0)
    closed = wins + losses
    wr_pct = (wins / closed * 100) if closed > 0 else None

    # Kalshi liveness — best-effort
    kalshi_ok = None
    try:
        prices = _live_prices()
        if prices.get("bitcoin"):
            kalshi_ok = True
    except Exception:
        kalshi_ok = False

    return jsonify({
        "paper_mode": bool(PAPER_MODE),
        "kalshi_ok": kalshi_ok,
        "starting_capital_usd": STARTING_CAPITAL_USD,
        "capital_usd": STARTING_CAPITAL_USD + realized - float(row["open_risk"] or 0),
        "realized_total_usd": realized,
        "today_pnl_usd": float(today),
        "wins": wins,
        "losses": losses,
        "open_positions": int(row["open_count"] or 0),
        "win_rate_pct": wr_pct,
    })


def _coin_id_from_ticker(ticker: str) -> str | None:
    if not ticker:
        return None
    upper = ticker.upper()
    if "BTC" in upper:
        return "bitcoin"
    if "ETH" in upper:
        return "ethereum"
    return None


def _strike_from_raw(raw_json: str) -> tuple[float | None, str]:
    """Best-effort strike + subtitle extraction from Kalshi raw market JSON."""
    if not raw_json:
        return (None, "")
    try:
        d = json.loads(raw_json)
    except Exception:
        return (None, "")
    floor = d.get("floor_strike")
    if floor is not None:
        try:
            return (float(floor), d.get("yes_sub_title") or "")
        except (TypeError, ValueError):
            pass
    sub = d.get("yes_sub_title") or d.get("title") or ""
    m = re.search(r"\$([\d,]+\.?\d*)", sub)
    if m:
        try:
            return (float(m.group(1).replace(",", "")), sub)
        except ValueError:
            pass
    return (None, sub)


def _is_winning(side: str, current_price: float, strike: float | None) -> bool | None:
    if not strike or current_price <= 0:
        return None
    above = current_price >= strike
    return above if (side or "").lower() == "yes" else (not above)


@app.route("/api/positions")
def api_positions():
    if not DB_PATH.exists():
        return jsonify({"positions": []})

    prices = _live_prices()
    btc_now = float((prices.get("bitcoin") or {}).get("usd", 0))
    eth_now = float((prices.get("ethereum") or {}).get("usd", 0))

    with get_conn(readonly=True) as conn:
        rows = conn.execute(
            "SELECT t.id, t.timestamp, t.sector, t.strategy, t.market_ticker, "
            "  t.side, t.contracts, t.price_cents, t.stake_usd, t.edge, "
            "  m.raw_json AS market_raw "
            "FROM trades t LEFT JOIN markets m ON t.market_ticker = m.ticker "
            "WHERE t.status='open' "
            "ORDER BY t.id DESC"
        ).fetchall()

    positions = []
    for r in rows:
        coin = _coin_id_from_ticker(r["market_ticker"])
        strike, subtitle = _strike_from_raw(r["market_raw"] or "")
        current = btc_now if coin == "bitcoin" else (eth_now if coin == "ethereum" else 0)
        history = (
            _btc_history() if coin == "bitcoin"
            else _eth_history() if coin == "ethereum"
            else []
        )
        positions.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "sector": r["sector"],
            "strategy": r["strategy"],
            "market_ticker": r["market_ticker"],
            "market_subtitle": subtitle,
            "side": r["side"],
            "contracts": r["contracts"],
            "price_cents": r["price_cents"],
            "stake_usd": float(r["stake_usd"] or 0),
            "edge": r["edge"],
            "strike": strike,
            "coin": coin,
            "current_price": current if current > 0 else None,
            "winning": _is_winning(r["side"] or "", current, strike),
            "price_history": history[-30:],  # cap to keep payload small
        })
    return jsonify({"positions": positions})


@app.route("/api/activity")
def api_activity():
    """Combined feed: closed trades (most recent 30) flagged as wins/losses."""
    if not DB_PATH.exists():
        return jsonify({"entries": []})
    entries = []
    with get_conn(readonly=True) as conn:
        for r in conn.execute(
            "SELECT id, timestamp, sector, strategy, market_ticker, side, "
            "  price_cents, contracts, status, pnl_usd "
            "FROM trades WHERE status IN ('won','lost') "
            "ORDER BY id DESC LIMIT 30"
        ).fetchall():
            kind = "win" if r["status"] == "won" else "loss"
            entries.append({
                "id": f"trade-{r['id']}",
                "ts": r["resolved_at"] if False else r["timestamp"],
                "sector": r["sector"] or "other",
                "kind": kind,
                "pnl_usd": float(r["pnl_usd"] or 0),
                "message": (
                    f"{r['side'].upper()} {r['contracts']}× "
                    f"{r['market_ticker']} @ {r['price_cents']}¢ "
                    f"[{r['strategy']}]"
                ),
            })
        # Add open-trade entries at the top
        for r in conn.execute(
            "SELECT id, timestamp, sector, strategy, market_ticker, side, "
            "  price_cents, contracts FROM trades WHERE status='open' "
            "ORDER BY id DESC"
        ).fetchall():
            entries.insert(0, {
                "id": f"open-{r['id']}",
                "ts": r["timestamp"],
                "sector": r["sector"] or "other",
                "kind": "entry",
                "pnl_usd": None,
                "message": (
                    f"Entered {r['side'].upper()} {r['contracts']}× "
                    f"{r['market_ticker']} @ {r['price_cents']}¢"
                ),
            })
    return jsonify({"entries": entries})


# ─── Static file serving (SPA) ───────────────────────────────────────────


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    if path and (STATIC_DIR / path).exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


def main():
    if not STATIC_DIR.exists():
        print(f"ERROR: {STATIC_DIR} not found. Run 'npm run build' in frontend/ first.")
        sys.exit(1)
    print("\n" + "=" * 55)
    print("  OmniAlpha — War Room")
    print(f"  Local  -> http://localhost:{SERVE_PORT}")
    print("=" * 55 + "\n")
    app.run(host="0.0.0.0", port=SERVE_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
