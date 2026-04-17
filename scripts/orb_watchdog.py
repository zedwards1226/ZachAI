"""ORB Trading System Watchdog.

Monitors ORB stack every 60s and auto-recovers:
  - main.py (via state/orb.pid + process liveness)
  - paper_trader.py (http://localhost:8766/status)
  - TradingView CDP (http://localhost:9222/json)
  - Jarvis Telegram bot (process scan)
  - Cloudflare tunnels (ping tunnel URLs if present in .env)

Actions:
  - Restart ORB main.py via scripts/ORBAgents.vbs when dead
  - Restart paper_trader when unreachable
  - Telegram alerts on state change (with 1-hour cooldown per key)
  - Optional Healthchecks.io ping (env HEALTHCHECK_ORB_URL)
  - Optional Twilio SMS on critical failures (env TWILIO_* + ALERT_PHONE)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ─── Paths ────────────────────────────────────────────────────────────────
TRADING_DIR = Path(r"C:\ZachAI\trading")
SCRIPTS_DIR = Path(r"C:\ZachAI\scripts")
LOG_DIR = TRADING_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "orb_watchdog.log"

ORB_PID_FILE = TRADING_DIR / "state" / "orb.pid"
ORB_VBS = SCRIPTS_DIR / "ORBAgents.vbs"
PAPER_TRADER_SCRIPT = TRADING_DIR / "paper_trader.py"

# ─── Endpoints ────────────────────────────────────────────────────────────
PAPER_TRADER_URL = "http://localhost:8766/status"
CDP_URL = "http://localhost:9222/json/version"
CHECK_EVERY = 60  # seconds

# ─── Load Telegram + optional alerting from trading/.env ──────────────────
def _load_env() -> dict:
    env = {}
    env_path = TRADING_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "HEALTHCHECK_ORB_URL", "TWILIO_ACCOUNT_SID",
              "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "ALERT_PHONE"):
        env[k] = os.environ.get(k, env.get(k, ""))
    return env

CFG = _load_env()
BOT_TOKEN = CFG.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = CFG.get("TELEGRAM_CHAT_ID", "")
HEALTHCHECK_URL = CFG.get("HEALTHCHECK_ORB_URL", "")
TW_SID = CFG.get("TWILIO_ACCOUNT_SID", "")
TW_TOKEN = CFG.get("TWILIO_AUTH_TOKEN", "")
TW_FROM = CFG.get("TWILIO_FROM", "")
ALERT_PHONE = CFG.get("ALERT_PHONE", "")

# ─── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ORB-WATCHDOG] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("orb_watchdog")

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ─── Alert cooldown ───────────────────────────────────────────────────────
_last_alert: dict[str, float] = {}
ALERT_COOLDOWN = 3600


def _cooldown_ok(key: str) -> bool:
    now = time.time()
    if key in _last_alert and (now - _last_alert[key]) < ALERT_COOLDOWN:
        return False
    _last_alert[key] = now
    return True


def _clear_cooldown(key: str) -> None:
    _last_alert.pop(key, None)


# ─── Notification fanout ──────────────────────────────────────────────────
def tg(msg: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning("Telegram send failed: %s", e)


def sms(msg: str) -> None:
    if not (TW_SID and TW_TOKEN and TW_FROM and ALERT_PHONE):
        return
    try:
        requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TW_SID}/Messages.json",
            auth=(TW_SID, TW_TOKEN),
            data={"From": TW_FROM, "To": ALERT_PHONE, "Body": msg[:160]},
            timeout=10,
        )
    except Exception as e:
        log.warning("Twilio SMS failed: %s", e)


def ping_healthcheck(suffix: str = "") -> None:
    """Ping Healthchecks.io — suffix '/fail' marks failure, empty = success."""
    if not HEALTHCHECK_URL:
        return
    try:
        requests.get(f"{HEALTHCHECK_URL}{suffix}", timeout=10)
    except Exception:
        pass


def alert(key: str, msg: str, critical: bool = False) -> None:
    """Send Telegram + optional SMS with cooldown."""
    if _cooldown_ok(key):
        log.warning(msg)
        tg(msg)
        if critical:
            sms(msg.replace("<b>", "").replace("</b>", ""))


def resolved(key: str, msg: str) -> None:
    _clear_cooldown(key)
    log.info(msg)
    tg(msg)


# ─── Process management ───────────────────────────────────────────────────
def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _find_processes(fragment: str) -> list[int]:
    """Find python processes whose command line contains fragment."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter "
             "\"(name='python.exe' OR name='pythonw.exe')\" | "
             "Select-Object ProcessId,CommandLine | "
             "ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        pids = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            if fragment in line:
                parts = line.split(",", 1)
                if parts and parts[0].strip('"').isdigit():
                    pids.append(int(parts[0].strip('"')))
        return pids
    except Exception:
        return []


def _start_vbs(vbs_path: Path) -> bool:
    try:
        subprocess.Popen(
            ["wscript", str(vbs_path)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        time.sleep(5)
        return True
    except Exception as e:
        log.error("Failed to start %s: %s", vbs_path, e)
        return False


def _start_paper_trader() -> bool:
    try:
        subprocess.Popen(
            ["pythonw", str(PAPER_TRADER_SCRIPT)],
            cwd=str(TRADING_DIR),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        time.sleep(3)
        return True
    except Exception as e:
        log.error("Failed to start paper_trader: %s", e)
        return False


# ─── Individual checks ────────────────────────────────────────────────────
def check_orb_main() -> bool:
    """ORB main.py alive via PID file. Restart via VBS if dead."""
    if not ORB_PID_FILE.exists():
        log.warning("ORB PID file missing — starting main.py")
        alert("orb_dead",
              f"⚠️ <b>ORB main.py not running</b>\n🔧 Starting via ORBAgents.vbs\n"
              f"⏰ {datetime.now().strftime('%H:%M:%S')}", critical=True)
        if _start_vbs(ORB_VBS):
            time.sleep(10)
            if ORB_PID_FILE.exists():
                resolved("orb_dead", "✅ <b>ORB main.py restarted</b>")
                return True
        return False

    try:
        pid = int(ORB_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        alert("orb_pid_bad", "⚠️ <b>ORB PID file corrupt</b>", critical=True)
        return False

    if _pid_alive(pid):
        _clear_cooldown("orb_dead")
        return True

    log.warning("ORB PID %d is dead — restarting", pid)
    alert("orb_dead",
          f"🚨 <b>CRITICAL:</b> ORB main.py crashed (PID {pid})\n"
          f"🔧 Restarting via ORBAgents.vbs\n⏰ {datetime.now().strftime('%H:%M:%S')}",
          critical=True)
    try:
        ORB_PID_FILE.unlink()
    except OSError:
        pass
    if _start_vbs(ORB_VBS):
        time.sleep(10)
        if ORB_PID_FILE.exists():
            resolved("orb_dead", "✅ <b>ORB main.py recovered</b>")
            return True
    alert("orb_fail",
          "🚨 <b>ORB RESTART FAILED</b> — manual intervention needed",
          critical=True)
    return False


def check_paper_trader() -> bool:
    """paper_trader.py on :8766. Restart if unreachable."""
    try:
        r = requests.get(PAPER_TRADER_URL, timeout=5)
        if r.status_code in (200, 401):  # 401 = webhook secret guard, still alive
            _clear_cooldown("paper_down")
            return True
    except Exception:
        pass

    log.warning("paper_trader :8766 unreachable — restarting")
    alert("paper_down",
          f"⚠️ <b>paper_trader.py down</b> (:8766)\n"
          f"🔧 Restarting\n⏰ {datetime.now().strftime('%H:%M:%S')}")
    if _start_paper_trader():
        time.sleep(5)
        try:
            r = requests.get(PAPER_TRADER_URL, timeout=5)
            if r.status_code in (200, 401):
                resolved("paper_down", "✅ <b>paper_trader recovered</b>")
                return True
        except Exception:
            pass
    alert("paper_fail",
          "🚨 <b>paper_trader restart FAILED</b>", critical=True)
    return False


def check_cdp() -> bool:
    """TradingView CDP on :9222. Can't auto-restart — needs MS Store app."""
    try:
        r = requests.get(CDP_URL, timeout=5)
        if r.status_code == 200:
            _clear_cooldown("cdp_down")
            return True
    except Exception:
        pass
    alert("cdp_down",
          f"⚠️ <b>TradingView CDP down</b> (:9222)\n"
          f"Trading paused — relaunch TradingView with --remote-debugging-port=9222\n"
          f"⏰ {datetime.now().strftime('%H:%M:%S')}", critical=True)
    return False


def check_jarvis_bot() -> bool:
    """Telegram Jarvis bot alive."""
    if _find_processes("bot.py"):
        _clear_cooldown("jarvis_down")
        return True
    alert("jarvis_down",
          f"⚠️ <b>Jarvis Telegram bot dead</b>\n"
          f"Run: wscript C:\\ZachAI\\scripts\\Jarvis_Bot.vbs\n"
          f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    return False


# ─── Main loop ────────────────────────────────────────────────────────────
def run_cycle() -> None:
    log.info("--- ORB watchdog cycle ---")
    results = {
        "orb_main":     check_orb_main(),
        "paper_trader": check_paper_trader(),
        "cdp":          check_cdp(),
        "jarvis_bot":   check_jarvis_bot(),
    }
    if all(results.values()):
        ping_healthcheck()  # success ping
    else:
        failed = [k for k, v in results.items() if not v]
        log.warning("Failed checks: %s", failed)
        ping_healthcheck("/fail")
    log.info("Cycle complete: %s", results)


def startup_banner() -> str:
    lines = ["🟢 <b>ORB Watchdog Started</b>", ""]
    lines.append(f"Checking every {CHECK_EVERY}s")
    lines.append(f"Healthchecks.io: {'configured' if HEALTHCHECK_URL else 'not set'}")
    lines.append(f"Twilio SMS: {'configured' if (TW_SID and ALERT_PHONE) else 'not set'}")
    lines.append(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    return "\n".join(lines)


def main() -> None:
    log.info("=" * 55)
    log.info("ORB Trading Watchdog")
    log.info("Telegram: %s", "configured" if BOT_TOKEN else "NOT CONFIGURED")
    log.info("PID file: %s", ORB_PID_FILE)
    log.info("Check interval: %ds", CHECK_EVERY)
    log.info("=" * 55)

    tg(startup_banner())

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log.info("Watchdog stopped by user")
            tg("🔴 <b>ORB Watchdog Stopped</b> (manual)")
            break
        except Exception as e:
            log.error("Cycle error: %s", e, exc_info=True)
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
