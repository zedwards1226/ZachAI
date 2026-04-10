"""
Paper Trade Engine
- Receives signals from TradingView alerts via webhook
- Logs paper trades, tracks P&L
- Notifies Telegram when trade opens/closes
- No real money. Demo only.
"""

import os, json, asyncio, logging
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests as req

BASE_DIR   = Path(__file__).parent
LOG_FILE   = BASE_DIR / "paper_trades.json"
PORT       = 8766

# Dollar value per 1-point move per contract
MULTIPLIERS = {
    "NQ1!":  20,
    "MNQ1!":  2,
    "ES1!":  50,
    "MES1!":  5,
    "QQQ":    1,
    "SPY":    1,
}

def get_multiplier(symbol: str) -> float:
    return MULTIPLIERS.get(symbol.upper(), 1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── state ──────────────────────────────────────────────────────────────────────

def load_trades() -> dict:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except Exception:
            pass
    return {"open": [], "closed": [], "stats": {"total_pnl": 0, "wins": 0, "losses": 0}}

def save_trades(data: dict):
    LOG_FILE.write_text(json.dumps(data, indent=2))

def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ── telegram notify ────────────────────────────────────────────────────────────

def notify_telegram(text: str):
    try:
        # Uses trading/.env for dedicated trading alerts bot token
        trading_env = Path(__file__).parent / ".env"
        cfg_file    = Path(__file__).parent.parent / "telegram-bridge" / "config.json"

        token, chat_id = None, None
        if trading_env.exists():
            for line in trading_env.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    chat_id = line.split("=", 1)[1].strip()
        if not chat_id and cfg_file.exists():
            chat_id = json.loads(cfg_file.read_text()).get("chat_id")

        if token and chat_id:
            req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=5
            )
    except Exception as e:
        log.error("Telegram notify failed: %s", e)

# ── webhook endpoint ───────────────────────────────────────────────────────────

def _parse_alert(request) -> dict:
    """
    Parse TradingView webhook body — handles two formats:
    1. JSON:  {"action":"buy","symbol":"MNQ1!","price":25000,"order_id":"Long","position_size":1}
    2. TV default order-fill text:
       "ORB 5m v3: order buy @ 1 filled on CME_MINI:MNQ1!. New strategy position is 1"

    Order IDs from NQ ORB Strategy:
      Entry:  "Long", "Short"
      Exit:   "LX1" (T1 long), "LX2" (T2 long), "SX1" (T1 short), "SX2" (T2 short)
      Close:  "EOD" (end of day close-all)
    """
    import re
    data = request.get_json(force=True, silent=True)
    if data and data.get("action"):
        action = data.get("action", "").lower()
        order_id = data.get("order_id", "")
        position_size = data.get("position_size")

        # Detect close/exit using position_size (most reliable) or order_id pattern
        is_exit = False
        if position_size is not None and float(position_size) == 0:
            is_exit = True
        elif order_id:
            oid = order_id.upper()
            # LX1, LX2, SX1, SX2 = partial/full exits; EOD = end-of-day close
            if oid in ("LX1", "LX2", "SX1", "SX2", "EOD") or "EXIT" in oid:
                is_exit = True

        if is_exit:
            data["action"] = "close"

        # Tag strategy name if not provided
        if not data.get("strategy"):
            data["strategy"] = "NQ ORB 15m"

        return data

    text = request.get_data(as_text=True) or ""
    action_m   = re.search(r'\border (\w+)\b', text)
    symbol_m   = re.search(r'filled on (?:CME_MINI:|BATS:)?(\w+)', text)
    position_m = re.search(r'position is (-?\d+\.?\d*)', text)
    price_m    = re.search(r'@\s*([\d,.]+)', text)

    if not action_m:
        return {}

    raw_action = action_m.group(1).lower()
    position   = float(position_m.group(1)) if position_m else None
    sym        = symbol_m.group(1) if symbol_m else "MNQ1!"
    price_val  = float(price_m.group(1).replace(",", "")) if price_m else 0.0

    # position == 0 means the trade was closed (exit order)
    action = "close" if position == 0 else raw_action

    return {
        "action":   action,
        "symbol":   sym,
        "price":    price_val,
        "strategy": "MNQ ORB 15m Paper",
    }


@app.route("/alert", methods=["POST"])
def handle_alert():
    """
    TradingView sends either JSON or default order-fill text via webhook.
    """
    try:
        raw_body = request.get_data(as_text=True)
        log.info("Webhook received: %s", raw_body[:500])

        data     = _parse_alert(request)
        action   = data.get("action", "").lower()
        symbol   = data.get("symbol", "UNKNOWN")
        price    = float(data.get("price", 0))
        strategy = data.get("strategy", "unnamed")
        order_id = data.get("order_id", "")

        log.info("Parsed: action=%s symbol=%s price=%.2f order_id=%s", action, symbol, price, order_id)

        trades = load_trades()

        if action in ("buy", "sell"):
            # Open new position
            trade = {
                "id":       len(trades["closed"]) + len(trades["open"]) + 1,
                "symbol":   symbol,
                "side":     action.upper(),
                "entry":    price,
                "strategy": strategy,
                "order_id": order_id,
                "opened":   now_str(),
                "qty":      1,
            }
            trades["open"].append(trade)
            save_trades(trades)

            mult = get_multiplier(symbol)
            msg = (
                f"📈 PAPER TRADE OPENED\n"
                f"{action.upper()} {symbol} @ {price:.2f}\n"
                f"Strategy: {strategy} | ${mult}/pt\n"
                f"Time: {now_str()}"
            )
            log.info(msg)
            notify_telegram(msg)

        elif action == "close":
            # Close all open trades for this symbol
            closed_any = False
            remaining = []
            for t in trades["open"]:
                if t["symbol"] == symbol:
                    mult = get_multiplier(symbol)
                    pts  = (price - t["entry"]) if t["side"] == "BUY" else (t["entry"] - price)
                    pnl  = round(pts * mult, 2)
                    t["exit"]   = price
                    t["closed"] = now_str()
                    t["pnl"]    = pnl
                    t["pts"]    = round(pts, 2)
                    t["multiplier"] = mult
                    trades["closed"].append(t)
                    trades["stats"]["total_pnl"] = round(trades["stats"]["total_pnl"] + pnl, 2)
                    if pnl > 0:
                        trades["stats"]["wins"] += 1
                    else:
                        trades["stats"]["losses"] += 1

                    win_rate = 0
                    total = trades["stats"]["wins"] + trades["stats"]["losses"]
                    if total > 0:
                        win_rate = round(trades["stats"]["wins"] / total * 100, 1)

                    emoji = "✅" if pnl > 0 else "❌"
                    msg = (
                        f"{emoji} PAPER TRADE CLOSED\n"
                        f"{t['side']} {symbol}: {t['entry']:.2f} → {price:.2f}\n"
                        f"P&L: {'+' if pnl > 0 else ''}${pnl:,.2f} ({'+' if pts > 0 else ''}{pts:.2f} pts × ${mult})\n"
                        f"Total P&L: ${trades['stats']['total_pnl']:,.2f} | Win rate: {win_rate}%"
                    )
                    log.info(msg)
                    notify_telegram(msg)
                    closed_any = True
                else:
                    remaining.append(t)

            trades["open"] = remaining
            save_trades(trades)

            if not closed_any:
                log.warning("Close signal for %s but no open trades", symbol)

        return jsonify({"ok": True})

    except Exception as e:
        log.exception("Alert error")
        return jsonify({"error": str(e)}), 500


@app.route("/status", methods=["GET"])
def status():
    trades = load_trades()
    total = trades["stats"]["wins"] + trades["stats"]["losses"]
    win_rate = round(trades["stats"]["wins"] / total * 100, 1) if total else 0
    return jsonify({
        "open_trades":  len(trades["open"]),
        "closed_trades": len(trades["closed"]),
        "total_pnl":    trades["stats"]["total_pnl"],
        "win_rate":     win_rate,
        "open":         trades["open"],
    })


@app.route("/reset", methods=["POST"])
def reset():
    save_trades({"open": [], "closed": [], "stats": {"total_pnl": 0, "wins": 0, "losses": 0}})
    return jsonify({"ok": True})


if __name__ == "__main__":
    log.info("Paper trader running on port %d", PORT)
    app.run(host="0.0.0.0", port=PORT)
