"""
WeatherAlpha Bot Monitor
Periodically checks bot health and reports problems.
Run: python monitor.py
Stop: Ctrl+C (or kill the process once bot is confirmed stable)
"""
import time
import logging
import sys
import requests
from datetime import datetime

API_BASE = "http://localhost:5000"
CHECK_INTERVAL = 30  # seconds between checks
ALERT_COOLDOWN = 300  # don't repeat same alert within 5 min

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MONITOR] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("monitor.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("monitor")

# Track recent alerts to avoid spam
_last_alert = {}


def alert(key: str, msg: str):
    """Log an alert, respecting cooldown to avoid spam."""
    now = time.time()
    if key in _last_alert and (now - _last_alert[key]) < ALERT_COOLDOWN:
        return  # still in cooldown
    _last_alert[key] = now
    log.warning("ALERT: %s", msg)


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
                alert(f"dupe_{mid}", f"DUPLICATE: {count} open positions for market {mid}")
            else:
                clear_alert(f"dupe_{mid}")
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
            alert("daily_loss_warning", f"Daily P&L is ${daily_pnl:.2f} — approaching limit")
        else:
            clear_alert("daily_loss_warning")

        # Capital at risk check — warn only above the configured 40% limit
        car = data.get("capital_at_risk_usd", 0)
        if car > 80 * 0.40:  # MAX_CAPITAL_AT_RISK = 40% of $80
            alert("high_risk", f"Capital at risk: ${car:.2f} (over 40% limit)")
        else:
            clear_alert("high_risk")
    except Exception as e:
        alert("guardrail_error", f"Guardrail check failed: {e}")


def check_trade_consistency():
    """Cross-check trade counts and guardrail counters."""
    try:
        summary_r = requests.get(f"{API_BASE}/api/summary", timeout=10)
        guard_r = requests.get(f"{API_BASE}/api/guardrails", timeout=10)
        if summary_r.status_code != 200 or guard_r.status_code != 200:
            return
        summary = summary_r.json()
        guard = guard_r.json()

        total_trades = summary.get("total_trades", 0)
        open_count = summary.get("open_trades", 0)

        # Check if open trades exceed reasonable count for 6 cities
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

        # Check for stale prices (positions with no live data)
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
            # Check if scan has been running too long (>5 min = stuck)
            last_scan_str = data.get("last_scan_time")
            if last_scan_str:
                try:
                    last_scan = datetime.fromisoformat(last_scan_str)
                    elapsed = (datetime.utcnow() - last_scan).total_seconds()
                    if elapsed > 300:
                        alert("scan_stuck", f"Scan has been running for {elapsed:.0f}s — may be stuck")
                except Exception:
                    pass
        else:
            clear_alert("scan_stuck")
    except Exception as e:
        alert("scan_status_error", f"Scan status check failed: {e}")


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
    log.info("WeatherAlpha Monitor started")
    log.info("Checking %s every %ds", API_BASE, CHECK_INTERVAL)
    log.info("=" * 50)

    while True:
        try:
            run_all_checks()
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error("Monitor loop error: %s", e)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
