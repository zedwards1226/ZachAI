"""
WeatherAlpha Bot Monitor + Telegram Alerts
Periodically checks bot health, reports problems to Telegram.
Run: python monitor.py
Stop: Ctrl+C (or kill the process once bot is confirmed stable)
"""
import time
import logging
import sys
import os
import requests
from datetime import datetime
from pathlib import Path

API_BASE = "http://localhost:5000"
CHECK_INTERVAL = 30  # seconds between checks
ALERT_COOLDOWN = 21600  # default 6h between same alert

# Per-key overrides for conditions that stay tripped all day. These got spammy
# at the old 1h cooldown — bump them to once-per-day so the feed stays useful.
ALERT_COOLDOWN_OVERRIDES = {
    "unrealized_loss": 86400,      # open book underwater — don't re-ping every hour
    "daily_loss_warning": 86400,   # day-long condition, one notice is enough
    "high_risk": 43200,            # capital-at-risk — 12h
    "kalshi_disconnected": 3600,   # keep 1h — urgent
    "halted": 3600,                # keep 1h — urgent
    "api_down": 1800,              # 30m — urgent
}

# Telegram config — prefer dedicated WeatherAlpha bot in kalshi/.env,
# fall back to shared ORB Trading Alerts bot in trading/.env if not set.
def _load_telegram_config():
    """Load Telegram bot token and chat ID.

    Priority:
      1. kalshi/.env  → @zacksweather_bot (dedicated WeatherAlpha bot)
      2. trading/.env → @ORD_trading_bot   (legacy shared bot)
      3. Environment variables (override)
    """
    def _read_env(path: Path):
        token, chat_id = None, None
        if not path.exists():
            return token, chat_id
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip() or None
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip() or None
        return token, chat_id

    kalshi_env = Path(__file__).parent.parent / ".env"
    trading_env = Path(__file__).parent.parent.parent / "trading" / ".env"

    token, chat_id = _read_env(kalshi_env)
    if not token or not chat_id:
        fallback_token, fallback_chat = _read_env(trading_env)
        token = token or fallback_token
        chat_id = chat_id or fallback_chat

    # Environment variable override
    token = os.environ.get("TELEGRAM_BOT_TOKEN", token)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", chat_id)
    return token, chat_id

TELEGRAM_TOKEN, TELEGRAM_CHAT_ID = _load_telegram_config()

log_file = Path(__file__).parent / "monitor.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MONITOR] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8"),
    ],
)
log = logging.getLogger("monitor")

# Track recent alerts to avoid spam
_last_alert = {}


def send_telegram(msg: str):
    """Send a message to Telegram. Silent on failure."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.debug("Telegram not configured — skipping notification")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
    except Exception as e:
        log.warning("Telegram send failed: %s", e)


def _cooldown_for(key: str) -> int:
    """Resolve per-key cooldown. Duplicate position alerts share the `dupe_` prefix."""
    if key in ALERT_COOLDOWN_OVERRIDES:
        return ALERT_COOLDOWN_OVERRIDES[key]
    if key.startswith("dupe_"):
        return 43200  # 12h — dupe persists until manually cleared
    return ALERT_COOLDOWN


def alert(key: str, msg: str):
    """Log an alert and send to Telegram, respecting cooldown."""
    now = time.time()
    cooldown = _cooldown_for(key)
    if key in _last_alert and (now - _last_alert[key]) < cooldown:
        return  # still in cooldown
    _last_alert[key] = now
    log.warning("ALERT: %s (cooldown=%ds)", msg, cooldown)
    send_telegram(f"⚠️ <b>WeatherAlpha — Heads Up</b>\n\n{msg}")


def clear_alert(key: str):
    """Remove an alert key so it can fire again if the problem recurs."""
    _last_alert.pop(key, None)


def check_api_health():
    """Check /api/health endpoint."""
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=10)
        if r.status_code != 200:
            alert("api_down", f"The WeatherAlpha bot's web service is responding with an error code ({r.status_code}). It may be crashing or restarting.")
            return False
        data = r.json()
        if not data.get("kalshi_connected"):
            alert("kalshi_disconnected", "Lost connection to Kalshi (the prediction market exchange). The bot can't place trades or check market prices until this reconnects.")
        else:
            clear_alert("kalshi_disconnected")
        clear_alert("api_down")
        return True
    except requests.ConnectionError:
        alert("api_down", "Can't reach the WeatherAlpha bot at all. The bot process may have crashed — check if app.py is running.")
        return False
    except Exception as e:
        alert("api_error", f"Something went wrong checking the bot's health: {e}")
        return False


def check_duplicate_trades():
    """Look for duplicate open trades on the same market."""
    try:
        r = requests.get(f"{API_BASE}/api/positions", timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        positions = data.get("positions", [])
        # Group by market_id
        market_counts = {}
        for p in positions:
            mid = p.get("market_id", "")
            market_counts[mid] = market_counts.get(mid, 0) + 1
        for mid, count in market_counts.items():
            if count > 1:
                alert(f"dupe_{mid}", f"Found {count} open positions on the same market ({mid}). Looks like a duplicate trade was opened — one of them probably needs closing.")
            else:
                clear_alert(f"dupe_{mid}")
        # Also check per-city duplicates
        city_counts = {}
        for p in positions:
            c = p.get("city", "")
            city_counts[c] = city_counts.get(c, 0) + 1
        for city, count in city_counts.items():
            if count > 1:
                alert(f"dupe_city_{city}", f"There are {count} open positions for {city}. We usually only hold one position per city — something doubled up.")
            else:
                clear_alert(f"dupe_city_{city}")
    except Exception as e:
        alert("dupe_check_error", f"Couldn't run the duplicate-trade check: {e}")


def check_guardrails():
    """Verify guardrails are not tripped / halted."""
    try:
        r = requests.get(f"{API_BASE}/api/guardrails", timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        if data.get("halted"):
            alert("halted", f"Trading is paused right now. Reason: {data.get('halt_reason', 'unknown')}. The bot won't take any new trades until this clears.")
        else:
            clear_alert("halted")

        # Check if daily loss is approaching limit
        daily_pnl = data.get("daily_pnl_usd", 0)
        if daily_pnl < -15:  # approaching $20 max daily loss
            alert("daily_loss_warning", f"Down ${abs(daily_pnl):.2f} today — getting close to the $20 daily loss cap. If we hit $20 the bot stops trading until tomorrow.")
        else:
            clear_alert("daily_loss_warning")

        # Capital at risk check — use dynamic capital from config
        car = data.get("capital_at_risk_usd", 0)
        max_car = data.get("max_capital_at_risk", 40)  # from guardrail_status()
        if car > max_car:
            alert("high_risk", f"We have ${car:.2f} tied up in open trades right now — that's over our ${max_car:.2f} risk limit. Won't open new positions until something closes.")
        else:
            clear_alert("high_risk")
    except Exception as e:
        alert("guardrail_error", f"Couldn't check the safety guardrails: {e}")


def check_trade_consistency():
    """Cross-check trade counts and guardrail counters."""
    try:
        summary_r = requests.get(f"{API_BASE}/api/summary", timeout=10)
        if summary_r.status_code != 200:
            return
        summary = summary_r.json()
        open_count = summary.get("open_trades", 0)

        if open_count > 12:
            alert("too_many_open", f"There are {open_count} open trades right now. We normally don't carry more than ~6 at once, so something's off — worth checking the dashboard.")
        else:
            clear_alert("too_many_open")
    except Exception as e:
        alert("consistency_error", f"Couldn't double-check the trade counts: {e}")


def check_positions_pnl():
    """Check for extreme unrealized losses. Per-trade price blips silenced —
    only fire when combined open book is materially underwater."""
    try:
        r = requests.get(f"{API_BASE}/api/positions", timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        total_unrealized = data.get("total_unrealized_pnl", 0)
        if total_unrealized < -25:
            # Include per-position breakdown so the alert is actionable
            positions = data.get("positions", [])
            losers = sorted(
                [p for p in positions if (p.get("unrealized_pnl") or 0) < 0],
                key=lambda p: p.get("unrealized_pnl") or 0,
            )[:3]
            breakdown = "; ".join(
                f"{p.get('city')} {p.get('side')} (down ${abs(p.get('unrealized_pnl', 0)):.2f})"
                for p in losers
            )
            alert("unrealized_loss",
                  f"Our open positions are down ${abs(total_unrealized):.2f} right now. Worst three: {breakdown}. Nothing's locked in yet — these can recover before the markets close.")
        else:
            clear_alert("unrealized_loss")
        # stale_prices alert removed — 0¢/None on a resolving T-market is normal.
    except Exception as e:
        alert("pnl_check_error", f"Couldn't check current profit/loss: {e}")


def check_scan_status():
    """Check if scans are running and not stuck."""
    try:
        r = requests.get(f"{API_BASE}/api/scan/status", timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        if data.get("is_scanning"):
            last_scan_str = data.get("last_scan_time")
            if last_scan_str:
                try:
                    last_scan = datetime.fromisoformat(last_scan_str)
                    elapsed = (datetime.utcnow() - last_scan).total_seconds()
                    if elapsed > 300:
                        alert("scan_stuck", f"The market scan has been running for {elapsed:.0f} seconds — that's way longer than normal. It may be stuck and need a restart.")
                except Exception:
                    pass
        else:
            clear_alert("scan_stuck")
    except Exception as e:
        alert("scan_status_error", f"Couldn't check whether the scanner is healthy: {e}")


def build_status_summary() -> str:
    """Build a one-time status summary for startup notification."""
    lines = []
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=5)
        h = r.json() if r.ok else {}
        lines.append(f"Kalshi: {'Connected' if h.get('kalshi_connected') else 'DOWN'}")
        lines.append(f"Mode: {'PAPER' if h.get('paper_mode') else 'LIVE'}")
    except Exception:
        lines.append("API: unreachable")
        return "\n".join(lines)

    try:
        r = requests.get(f"{API_BASE}/api/positions", timeout=5)
        pos = r.json() if r.ok else {}
        positions = pos.get("positions", [])
        total_pnl = pos.get("total_unrealized_pnl", 0)
        lines.append(f"Open positions: {len(positions)}")
        if positions:
            cities = [p["city"] for p in positions]
            lines.append(f"Cities: {', '.join(cities)}")
            lines.append(f"Unrealized P&L: ${total_pnl:+.2f}")
    except Exception:
        pass

    try:
        r = requests.get(f"{API_BASE}/api/summary", timeout=5)
        s = r.json() if r.ok else {}
        lines.append(f"Total trades: {s.get('total_trades', '?')} ({s.get('wins', 0)}W/{s.get('losses', 0)}L)")
        lines.append(f"Total P&L: ${s.get('total_pnl_usd', 0):+.2f}")
    except Exception:
        pass

    return "\n".join(lines)


def send_daily_digest(when: str = "eod"):
    """Send a single Telegram summary. `when` = 'morning' or 'eod'.
    Plain-English replacement for per-event spam."""
    try:
        health = requests.get(f"{API_BASE}/api/health", timeout=5).json()
        pos    = requests.get(f"{API_BASE}/api/positions", timeout=5).json()
        summ   = requests.get(f"{API_BASE}/api/summary", timeout=5).json()
    except Exception as e:
        send_telegram(
            f"<b>WeatherAlpha digest couldn't run</b>\n\n"
            f"The bot's web service didn't respond, so I can't pull the numbers.\n"
            f"Technical detail: {e}"
        )
        return

    if when == "morning":
        emoji, header, intro = "☀️", "Good morning — WeatherAlpha update", "Here's where we stand heading into today's markets."
    else:
        emoji, header, intro = "🌙", "End-of-day wrap — WeatherAlpha", "Here's how today landed."

    mode_text = "paper trading (no real money on the line)" if health.get("paper_mode") else "LIVE TRADING (real money)"
    kalshi_text = "working" if health.get("kalshi_connected") else "DOWN — bot can't trade right now"

    total_pnl = summ.get("total_pnl_usd", 0)
    wins = summ.get("wins", 0)
    losses = summ.get("losses", 0)
    total_trades = summ.get("total_trades", wins + losses)
    win_rate = (wins / total_trades * 100) if total_trades else 0
    pnl_word = "profit" if total_pnl >= 0 else "loss"

    open_count = len(pos.get("positions", []))
    unrealized = pos.get("total_unrealized_pnl", 0)
    if open_count == 0:
        open_text = "No positions open right now."
    else:
        unreal_word = "up" if unrealized >= 0 else "down"
        open_text = (
            f"Holding <b>{open_count} position{'s' if open_count != 1 else ''}</b> right now — "
            f"currently {unreal_word} <b>${abs(unrealized):.2f}</b> "
            f"<i>(not locked in until markets resolve)</i>"
        )

    lines = [
        f"{emoji} <b>{header}</b>",
        f"<i>{intro}</i>",
        "",
        f"<b>System status</b>",
        f"  • Trading mode: {mode_text}",
        f"  • Kalshi connection: {kalshi_text}",
        "",
        f"<b>Lifetime results</b>",
        f"  • {total_trades} trades total — <b>{wins} wins, {losses} losses</b> ({win_rate:.0f}% win rate)",
        f"  • Total {pnl_word}: <b>${abs(total_pnl):.2f}</b>",
        "",
        f"<b>Right now</b>",
        f"  {open_text}",
    ]

    if pos.get("positions"):
        lines.append("")
        lines.append(f"<b>Open positions</b>")
        for p in pos["positions"]:
            city = p.get("city", "?")
            side = (p.get("side") or "").upper()
            side_phrase = (
                "betting the high temp WILL hit the target" if side == "YES"
                else "betting the high temp WON'T hit the target" if side == "NO"
                else side
            )
            entry_c = p.get("price_cents")
            now_c = p.get("current_price")
            upnl = p.get("unrealized_pnl")
            if upnl is None:
                pnl_phrase = "still waiting on a current price"
            elif upnl >= 0:
                pnl_phrase = f"up ${upnl:.2f}"
            else:
                pnl_phrase = f"down ${abs(upnl):.2f}"
            price_phrase = (
                f"bought at {entry_c}¢" + (f", currently {now_c}¢" if now_c is not None else "")
                if entry_c is not None else "price data pending"
            )
            lines.append(f"  • <b>{city}</b> — {side_phrase}. {price_phrase} → {pnl_phrase}")

    send_telegram("\n".join(lines))
    log.info("Digest sent (%s)", when)


def run_all_checks():
    """Run all health checks in sequence."""
    log.info("--- Running health checks ---")
    api_ok = check_api_health()
    if not api_ok:
        log.info("API unreachable — skipping remaining checks")
        return

    check_duplicate_trades()
    check_guardrails()
    check_trade_consistency()
    check_positions_pnl()
    check_scan_status()
    log.info("--- Checks complete ---")


def main():
    log.info("=" * 50)
    log.info("WeatherAlpha Monitor started (Telegram alerts ON)")
    log.info("Checking %s every %ds", API_BASE, CHECK_INTERVAL)
    log.info("Telegram: %s", "configured" if TELEGRAM_TOKEN else "NOT configured")
    log.info("=" * 50)

    # Startup ping silenced — morning digest (8 AM ET) covers daily status.
    # Operational alerts (api_down, halted, dupes, high_risk) still fire real-time.
    log.info("Startup summary (log only):\n%s", build_status_summary())

    while True:
        try:
            run_all_checks()
        except KeyboardInterrupt:
            send_telegram("🛑 <b>WeatherAlpha monitor stopped</b>\n\nThe health-check process was shut down. Real-time alerts are paused until it starts again.")
            break
        except Exception as e:
            log.error("Monitor loop error: %s", e)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
