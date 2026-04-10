"""
WeatherAlpha Autonomous Watchdog
================================
Monitors everything, auto-fixes problems, alerts via Telegram.

Checks every 30s:
  - Bot API health (:5000)
  - Monitor.py is alive (restarts if dead)
  - Dashboard (:3001) is alive
  - Kalshi API connection
  - Guardrail counter sync (compares DB state vs actual open trades)
  - Capital at risk < 40%
  - Daily loss < $12
  - No duplicate open trades
  - Scan not stuck > 5 min

Auto-fix actions:
  - Resync guardrail counters when they drift
  - Restart bot API if it crashes
  - Restart monitor.py if it dies
  - Send Telegram alerts for every action

Startup: VBS script in Windows Startup folder
Logging: C:\\ZachAI\\kalshi\\logs\\watchdog.log
"""
import time
import subprocess
import requests
import logging
import sys
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BOT_SCRIPT = r"C:\ZachAI\kalshi\bots\app.py"
MONITOR_SCRIPT = r"C:\ZachAI\kalshi\bots\monitor.py"
DB_PATH = r"C:\ZachAI\kalshi\bots\weatheralpha.db"
LOG_DIR = Path(r"C:\ZachAI\kalshi\logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "watchdog.log"

HEALTH_URL = "http://localhost:5000/api/health"
DASHBOARD_URL = "http://localhost:3001"
CHECK_EVERY = 30  # seconds
FAIL_THRESH = 2  # consecutive API failures before restart

# ── Telegram config ───────────────────────────────────────────────────────────
def _load_telegram():
    """Load token from trading/.env, fall back to env vars."""
    env_path = Path(r"C:\ZachAI\trading\.env")
    token = chat_id = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip()
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN", token),
        os.environ.get("TELEGRAM_CHAT_ID", chat_id),
    )

BOT_TOKEN, CHAT_ID = _load_telegram()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watchdog")

# ── Alert cooldown ────────────────────────────────────────────────────────────
_last_alert = {}
ALERT_COOLDOWN = 300  # 5 minutes


def _cooldown_ok(key: str) -> bool:
    now = time.time()
    if key in _last_alert and (now - _last_alert[key]) < ALERT_COOLDOWN:
        return False
    _last_alert[key] = now
    return True


def _clear_cooldown(key: str):
    _last_alert.pop(key, None)


# ── Telegram ──────────────────────────────────────────────────────────────────
def tg(msg: str):
    """Send Telegram message. Never raises."""
    if not BOT_TOKEN or not CHAT_ID:
        log.debug("Telegram not configured")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning("Telegram send failed: %s", e)


def tg_alert(key: str, msg: str):
    """Send alert with cooldown."""
    if _cooldown_ok(key):
        log.warning(msg)
        tg(msg)


def tg_resolved(key: str, msg: str):
    """Send resolved notification and clear cooldown."""
    _clear_cooldown(key)
    log.info(msg)
    tg(msg)


# ── Direct DB access (bypasses the running bot) ──────────────────────────────
def _db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_get_open_trades() -> list[dict]:
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='open' ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _db_get_guardrail_state() -> dict:
    today = date.today().isoformat()
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM guardrail_state WHERE date=?", (today,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT OR IGNORE INTO guardrail_state (date) VALUES (?)", (today,)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM guardrail_state WHERE date=?", (today,)
            ).fetchone()
        return dict(row)
    finally:
        conn.close()


def _db_update_guardrail_field(field: str, value):
    today = date.today().isoformat()
    conn = _db_conn()
    try:
        conn.execute(
            f"UPDATE guardrail_state SET {field}=? WHERE date=?",
            (value, today)
        )
        conn.commit()
    finally:
        conn.close()


def _db_get_summary() -> dict:
    conn = _db_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM trades WHERE status='won'").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM trades WHERE status='lost'").fetchone()[0]
        pnl = conn.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM trades WHERE pnl_usd IS NOT NULL").fetchone()[0]
        open_c = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
        open_r = conn.execute("SELECT COALESCE(SUM(stake_usd),0) FROM trades WHERE status='open'").fetchone()[0]
        return {
            "total_trades": total, "wins": wins, "losses": losses,
            "open_trades": open_c, "open_risk_usd": round(open_r, 2),
            "total_pnl_usd": round(pnl, 2),
        }
    finally:
        conn.close()


def _db_count_today_trades() -> int:
    today = date.today().isoformat()
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE timestamp LIKE ? AND status != 'cancelled'",
            (f"{today}%",)
        ).fetchone()
        return row[0]
    finally:
        conn.close()


# Hide all subprocess windows — prevents CMD flash on screen
_NO_WINDOW = subprocess.CREATE_NO_WINDOW


# ── Process management ────────────────────────────────────────────────────────
def _is_process_running(name_fragment: str) -> bool:
    """Check if a python/pythonw process with given script name is running."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter "
             f"\"(name='python.exe' OR name='pythonw.exe') AND "
             f"CommandLine LIKE '%{name_fragment}%'\").Count"],
            capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
        return count > 0
    except Exception:
        return False


def _start_process(script_path: str, label: str) -> bool:
    """Start a Python script as a detached background process."""
    try:
        subprocess.Popen(
            ["pythonw", script_path],
            cwd=str(Path(script_path).parent),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        time.sleep(3)
        return True
    except Exception as e:
        log.error("Failed to start %s: %s", label, e)
        return False


def _kill_and_restart(script_path: str, name_fragment: str, label: str) -> bool:
    """Kill existing process and start fresh."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_Process -Filter "
             f"\"(name='python.exe' OR name='pythonw.exe') AND "
             f"CommandLine LIKE '%{name_fragment}%'\" | "
             f"ForEach-Object {{ Stop-Process -Id $($_.ProcessId) -Force }}"],
            capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        pass
    time.sleep(2)
    return _start_process(script_path, label)


# ── Health checks ─────────────────────────────────────────────────────────────
_api_failures = 0


def check_bot_api() -> bool:
    """Check bot API is responding. Auto-restart after FAIL_THRESH consecutive failures."""
    global _api_failures
    try:
        r = requests.get(HEALTH_URL, timeout=10)
        if r.status_code == 200 and r.json().get("status") == "ok":
            if _api_failures >= FAIL_THRESH:
                tg_resolved("bot_api", "✅ <b>RESOLVED:</b> Bot API recovered\n"
                            f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            _api_failures = 0
            return True
    except Exception:
        pass

    _api_failures += 1
    log.warning("Bot API health check failed (%d/%d)", _api_failures, FAIL_THRESH)

    if _api_failures >= FAIL_THRESH:
        now = datetime.now().strftime("%H:%M:%S")
        tg_alert("bot_api",
                 f"🚨 <b>CRITICAL:</b> Bot API down ({_api_failures} failures)\n"
                 f"🔧 Action: Restarting app.py\n"
                 f"⏰ Time: {now}")
        ok = _kill_and_restart(BOT_SCRIPT, "app.py", "Bot API")
        time.sleep(8)
        if ok and requests.get(HEALTH_URL, timeout=5).status_code == 200:
            _api_failures = 0
            tg_resolved("bot_api",
                        f"✅ <b>RESOLVED:</b> Bot API restarted successfully\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            return True
        else:
            tg_alert("bot_api_fail",
                     f"🚨 <b>CRITICAL:</b> Bot API FAILED to restart\n"
                     f"⏰ {now}\nManual intervention needed!")
    return False


def check_kalshi_connection() -> bool:
    """Check Kalshi API is connected."""
    try:
        r = requests.get(HEALTH_URL, timeout=10)
        if r.ok:
            data = r.json()
            connected = data.get("kalshi_connected", False)
            if not connected:
                tg_alert("kalshi_down",
                         f"🚨 <b>CRITICAL:</b> Kalshi API disconnected\n"
                         f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                         f"Bot cannot fetch prices or place orders!")
                return False
            else:
                _clear_cooldown("kalshi_down")
                return True
    except Exception:
        pass
    return False


def check_monitor_alive():
    """Ensure monitor.py is running. Restart if dead."""
    if _is_process_running("monitor.py"):
        return True
    log.warning("monitor.py is not running — restarting")
    tg_alert("monitor_dead",
             f"⚠️ <b>WARNING:</b> monitor.py was dead\n"
             f"🔧 Action: Restarting\n"
             f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    ok = _start_process(MONITOR_SCRIPT, "Monitor")
    if ok:
        tg_resolved("monitor_dead",
                     f"✅ <b>RESOLVED:</b> monitor.py restarted\n"
                     f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    return ok


def check_dashboard():
    """Check dashboard on :3001 is responding."""
    try:
        r = requests.get(DASHBOARD_URL, timeout=5)
        if r.status_code == 200:
            _clear_cooldown("dashboard_down")
            return True
    except Exception:
        pass
    tg_alert("dashboard_down",
             f"⚠️ <b>WARNING:</b> Dashboard (:3001) not responding\n"
             f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    return False


def check_guardrail_sync():
    """
    CRITICAL: Compare guardrail_state.capital_at_risk_usd against
    actual SUM(stake_usd) of open trades. Auto-resync if they differ.
    Also sync daily_trades counter.
    """
    try:
        gs = _db_get_guardrail_state()
        open_trades = _db_get_open_trades()
        actual_risk = round(sum(t["stake_usd"] for t in open_trades), 2)
        recorded_risk = round(gs.get("capital_at_risk_usd", 0), 2)

        # Also check daily trade count
        actual_daily = _db_count_today_trades()
        recorded_daily = gs.get("daily_trades", 0)

        synced_something = False
        details = []

        # Capital at risk sync
        if abs(actual_risk - recorded_risk) > 0.01:
            log.warning("Guardrail DESYNC: capital_at_risk recorded=$%.2f actual=$%.2f",
                        recorded_risk, actual_risk)
            _db_update_guardrail_field("capital_at_risk_usd", actual_risk)
            details.append(f"capital_at_risk: ${recorded_risk:.2f} → ${actual_risk:.2f}")
            synced_something = True

        # Daily trades sync
        if actual_daily != recorded_daily:
            log.warning("Guardrail DESYNC: daily_trades recorded=%d actual=%d",
                        recorded_daily, actual_daily)
            _db_update_guardrail_field("daily_trades", actual_daily)
            details.append(f"daily_trades: {recorded_daily} → {actual_daily}")
            synced_something = True

        if synced_something:
            now = datetime.now().strftime("%H:%M:%S")
            summary = _db_get_summary()
            capital = 80.0 + summary["total_pnl_usd"]
            risk_pct = (actual_risk / capital * 100) if capital > 0 else 0
            detail_str = "\n".join(f"  • {d}" for d in details)
            tg_alert("guardrail_sync",
                     f"⚠️ <b>RESYNCED:</b> Guardrail counters were wrong\n"
                     f"{detail_str}\n"
                     f"📊 Capital at risk: ${actual_risk:.2f} / ${capital:.2f} ({risk_pct:.0f}%)\n"
                     f"⏰ {now}")
        return True
    except Exception as e:
        log.error("Guardrail sync error: %s", e)
        return False


def check_capital_at_risk():
    """Verify capital at risk is under 40% limit."""
    try:
        summary = _db_get_summary()
        capital = 80.0 + summary["total_pnl_usd"]
        risk = summary["open_risk_usd"]
        if capital <= 0:
            return
        pct = risk / capital * 100
        if pct > 40:
            tg_alert("risk_over_40",
                     f"🚨 <b>ALERT:</b> Capital at risk {pct:.0f}% (over 40% limit)\n"
                     f"💰 At risk: ${risk:.2f} / ${capital:.2f}\n"
                     f"⏰ {datetime.now().strftime('%H:%M:%S')}")
        else:
            _clear_cooldown("risk_over_40")
    except Exception as e:
        log.error("Risk check error: %s", e)


def check_daily_loss():
    """Check daily P&L hasn't exceeded $12 loss."""
    try:
        gs = _db_get_guardrail_state()
        daily_pnl = gs.get("daily_pnl_usd", 0)
        if daily_pnl < -12:
            tg_alert("daily_loss",
                     f"🚨 <b>ALERT:</b> Daily loss ${daily_pnl:.2f} exceeds -$12 limit\n"
                     f"⏰ {datetime.now().strftime('%H:%M:%S')}")
        else:
            _clear_cooldown("daily_loss")
    except Exception as e:
        log.error("Daily loss check error: %s", e)


def check_duplicate_trades():
    """Check for duplicate open trades on same market or same city."""
    try:
        open_trades = _db_get_open_trades()
        # By market_id
        market_counts = {}
        for t in open_trades:
            mid = t["market_id"]
            market_counts[mid] = market_counts.get(mid, 0) + 1
        for mid, cnt in market_counts.items():
            if cnt > 1:
                tg_alert(f"dupe_{mid}",
                         f"🚨 <b>DUPLICATE:</b> {cnt} open trades for {mid}\n"
                         f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            else:
                _clear_cooldown(f"dupe_{mid}")
        # By city
        city_counts = {}
        for t in open_trades:
            c = t["city"]
            city_counts[c] = city_counts.get(c, 0) + 1
        for city, cnt in city_counts.items():
            if cnt > 1:
                tg_alert(f"dupe_city_{city}",
                         f"🚨 <b>DUPLICATE:</b> {cnt} open trades for city {city}\n"
                         f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            else:
                _clear_cooldown(f"dupe_city_{city}")
    except Exception as e:
        log.error("Duplicate check error: %s", e)


def check_scan_stuck():
    """Check if a scan has been running too long."""
    try:
        r = requests.get("http://localhost:5000/api/scan/status", timeout=5)
        if not r.ok:
            return
        data = r.json()
        if data.get("is_scanning"):
            last_scan_str = data.get("last_scan_time")
            if last_scan_str:
                last_scan = datetime.fromisoformat(last_scan_str)
                elapsed = (datetime.utcnow() - last_scan).total_seconds()
                if elapsed > 300:
                    tg_alert("scan_stuck",
                             f"⚠️ <b>WARNING:</b> Scan stuck for {elapsed:.0f}s\n"
                             f"⏰ {datetime.now().strftime('%H:%M:%S')}")
                else:
                    _clear_cooldown("scan_stuck")
        else:
            _clear_cooldown("scan_stuck")
    except Exception:
        pass


# ── Startup status ────────────────────────────────────────────────────────────
def build_startup_message() -> str:
    """Build startup status report."""
    lines = ["🟢 <b>WeatherAlpha Watchdog Started</b>", ""]

    # Guardrail sync check
    try:
        gs = _db_get_guardrail_state()
        open_trades = _db_get_open_trades()
        actual_risk = round(sum(t["stake_usd"] for t in open_trades), 2)
        recorded_risk = round(gs.get("capital_at_risk_usd", 0), 2)
        if abs(actual_risk - recorded_risk) > 0.01:
            _db_update_guardrail_field("capital_at_risk_usd", actual_risk)
            lines.append(f"Guardrail sync: ⚠️ Fixed ${recorded_risk:.2f}→${actual_risk:.2f}")
        else:
            lines.append("Guardrail sync: ✅")
    except Exception as e:
        lines.append(f"Guardrail sync: ❌ {e}")

    # API health
    try:
        r = requests.get(HEALTH_URL, timeout=5)
        if r.ok and r.json().get("status") == "ok":
            kalshi = "✅" if r.json().get("kalshi_connected") else "❌"
            lines.append(f"API health: ✅")
            lines.append(f"Kalshi: {kalshi}")
        else:
            lines.append("API health: ❌")
    except Exception:
        lines.append("API health: ❌ (not running)")

    # Monitor
    if _is_process_running("monitor.py"):
        lines.append("Monitor.py: ✅")
    else:
        lines.append("Monitor.py: ❌ (starting...)")
        _start_process(MONITOR_SCRIPT, "Monitor")

    # Dashboard
    try:
        r = requests.get(DASHBOARD_URL, timeout=5)
        lines.append("Dashboard: ✅" if r.ok else "Dashboard: ❌")
    except Exception:
        lines.append("Dashboard: ❌")

    # Position summary
    try:
        summary = _db_get_summary()
        open_trades = _db_get_open_trades()
        capital = 80.0 + summary["total_pnl_usd"]
        risk = summary["open_risk_usd"]
        risk_pct = (risk / capital * 100) if capital > 0 else 0
        cities = ", ".join(sorted(set(t["city"] for t in open_trades)))
        lines.append("")
        lines.append(f"Open positions: {len(open_trades)}")
        if cities:
            lines.append(f"Cities: {cities}")
        lines.append(f"Capital: ${capital:.2f}")
        lines.append(f"At risk: ${risk:.2f} ({risk_pct:.0f}%)")
        lines.append(f"Total P&L: ${summary['total_pnl_usd']:+.2f}")
        lines.append(f"Trades: {summary['total_trades']} ({summary['wins']}W/{summary['losses']}L)")
    except Exception:
        pass

    lines.append("")
    lines.append(f"Checking every {CHECK_EVERY}s")
    return "\n".join(lines)


# ── Main loop ─────────────────────────────────────────────────────────────────
def run_all_checks():
    """Run every check. Guardrail sync runs FIRST on every cycle."""
    log.info("--- Health check cycle ---")

    # ALWAYS sync guardrails first — this is the critical fix
    check_guardrail_sync()

    # Bot API (auto-restarts if down)
    api_ok = check_bot_api()
    if not api_ok:
        log.warning("Bot API down — skipping API-dependent checks")
        check_monitor_alive()
        return

    # Everything else
    check_kalshi_connection()
    check_monitor_alive()
    check_dashboard()
    check_capital_at_risk()
    check_daily_loss()
    check_duplicate_trades()
    check_scan_stuck()

    log.info("--- Checks complete ---")


def main():
    log.info("=" * 55)
    log.info("WeatherAlpha Autonomous Watchdog")
    log.info("Telegram: %s", "configured" if BOT_TOKEN else "NOT CONFIGURED")
    log.info("DB: %s", DB_PATH)
    log.info("Check interval: %ds", CHECK_EVERY)
    log.info("=" * 55)

    # Startup message with full status
    startup_msg = build_startup_message()
    log.info("Startup status:\n%s", startup_msg.replace("<b>", "").replace("</b>", ""))
    tg(startup_msg)

    while True:
        try:
            run_all_checks()
        except KeyboardInterrupt:
            log.info("Watchdog stopped by user")
            tg("🔴 <b>Watchdog Stopped</b> (manual)\n"
               f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            break
        except Exception as e:
            log.error("Watchdog loop error: %s", e)
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
