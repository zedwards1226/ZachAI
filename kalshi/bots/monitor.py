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
ALERT_COOLDOWN = 3600  # don't repeat same alert within 1 hour

# Telegram config — read from trading .env or fall back to hardcoded
def _load_telegram_config():
    """Load Telegram bot token and chat ID."""
    env_path = Path(__file__).parent.parent.parent / "trading" / ".env"
    token = None
    chat_id = None
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip()
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


def alert(key: str, msg: str):
    """Log an alert and send to Telegram, respecting cooldown."""
    now = time.time()
    if key in _last_alert and (now - _last_alert[key]) < ALERT_COOLDOWN:
        return  # still in cooldown
    _last_alert[key] = now
    log.warning("ALERT: %s", msg)
    send_telegram(f"<b>WeatherAlpha Alert</b>\n{msg}")


def clear_alert(key: str):
    """Remove an alert key so it can fire again if the problem recurs."""
    _last_alert.pop(key, None)


def check_api_health():
    """Check /api/health endpoint."""
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=10)
        if r.status_code != 200:
            alert("api_down", f"API returned HTTP {r.status_code}")
            return False
        data = r.json()
        if not data.get("kalshi_connected"):
            alert("kalshi_disconnected", "Kalshi API is disconnected")
        else:
            clear_alert("kalshi_disconnected")
        clear_alert("api_down")
        return True
    except requests.ConnectionError:
        alert("api_down", "Cannot connect to bot API at localhost:5000 — is the bot running?")
        return False
    except Exception as e:
        alert("api_error", f"Health check error: {e}")
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
                alert(f"dupe_{mid}", f"DUPLICATE: {count} open positions for {mid}")
            else:
                clear_alert(f"dupe_{mid}")
        # Also check per-city duplicates
        city_counts = {}
        for p in positions:
            c = p.get("city", "")
            city_counts[c] = city_counts.get(c, 0) + 1
        for city, count in city_counts.items():
            if count > 1:
                alert(f"dupe_city_{city}", f"DUPLICATE: {count} open positions for city {city}")
            else:
                clear_alert(f"dupe_city_{city}")
    except Exception as e:
        alert("dupe_check_error", f"Duplicate check failed: {e}")


def check_guardrails():
    """Verify guardrails are not tripped / halted."""
    try:
        r = requests.get(f"{API_BASE}/api/guardrails", timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        if data.get("halted"):
            alert("halted", f"Bot is HALTED: {data.get('halt_reason', 'unknown')}")
        else:
            clear_alert("halted")

        # Check if daily loss is approaching limit
        daily_pnl = data.get("daily_pnl_usd", 0)
        if daily_pnl < -15:  # approaching $20 max daily loss
            alert("daily_loss_warning", f"Daily P&L is ${daily_pnl:.2f} — approaching $20 limit")
        else:
            clear_alert("daily_loss_warning")

        # Capital at risk check — use dynamic capital from config
        car = data.get("capital_at_risk_usd", 0)
        max_car = data.get("max_capital_at_risk", 40)  # from guardrail_status()
        if car > max_car:
            alert("high_risk", f"Capital at risk: ${car:.2f} (over ${max_car:.2f} limit)")
        else:
            clear_alert("high_risk")
    except Exception as e:
        alert("guardrail_error", f"Guardrail check failed: {e}")


def check_trade_consistency():
    """Cross-check trade counts and guardrail counters."""
    try:
        summary_r = requests.get(f"{API_BASE}/api/summary", timeout=10)
        if summary_r.status_code != 200:
            return
        summary = summary_r.json()
        open_count = summary.get("open_trades", 0)

        if open_count > 12:
            alert("too_many_open", f"Unusual: {open_count} open trades (expected max ~6)")
        else:
            clear_alert("too_many_open")
    except Exception as e:
        alert("consistency_error", f"Consistency check failed: {e}")


def check_positions_pnl():
    """Check for extreme unrealized losses."""
    try:
        r = requests.get(f"{API_BASE}/api/positions", timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        total_unrealized = data.get("total_unrealized_pnl", 0)
        if total_unrealized < -10:
            alert("unrealized_loss", f"Large unrealized loss: ${total_unrealized:.2f}")
        else:
            clear_alert("unrealized_loss")

        # Check for stale prices
        positions = data.get("positions", [])
        stale = [p for p in positions if p.get("current_price") is None]
        if stale:
            tickers = [p["market_id"] for p in stale]
            alert("stale_prices", f"{len(stale)} positions with no live price: {', '.join(tickers[:3])}")
        else:
            clear_alert("stale_prices")
    except Exception as e:
        alert("pnl_check_error", f"P&L check failed: {e}")


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
                        alert("scan_stuck", f"Scan running for {elapsed:.0f}s — may be stuck")
                except Exception:
                    pass
        else:
            clear_alert("scan_stuck")
    except Exception as e:
        alert("scan_status_error", f"Scan status check failed: {e}")


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

    # Startup notification with status summary
    summary = build_status_summary()
    send_telegram(
        f"<b>WeatherAlpha Monitor Started</b>\n"
        f"Checking every {CHECK_INTERVAL}s\n\n{summary}"
    )

    while True:
        try:
            run_all_checks()
        except KeyboardInterrupt:
            send_telegram("WeatherAlpha Monitor stopped")
            break
        except Exception as e:
            log.error("Monitor loop error: %s", e)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
