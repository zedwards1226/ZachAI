"""ORB Trading System Watchdog.

Monitors ORB stack every 60s and auto-recovers:
  - main.py (via state/orb.pid + process liveness)
  - TradingView CDP (http://localhost:9222/json)
  - Jarvis Telegram bot (process scan)

Actions:
  - Restart ORB main.py via scripts/ORBAgents.vbs when dead
  - Telegram alerts on state change (with 1-hour cooldown per key)
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

# ─── Endpoints ────────────────────────────────────────────────────────────
CDP_URL = "http://localhost:9222/json/version"
CHECK_EVERY = 60  # seconds

# ─── Load Telegram from trading/.env ──────────────────────────────────────
def _load_env() -> dict:
    env = {}
    env_path = TRADING_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env[k] = os.environ.get(k, env.get(k, ""))
    return env

CFG = _load_env()
BOT_TOKEN = CFG.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = CFG.get("TELEGRAM_CHAT_ID", "")

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


# ─── Notification ─────────────────────────────────────────────────────────
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


def alert(key: str, msg: str) -> None:
    if _cooldown_ok(key):
        log.warning(msg)
        tg(msg)


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
        time.sleep(10)
        return True
    except Exception as e:
        log.error("Failed to start %s: %s", vbs_path, e)
        return False


# ─── Individual checks ────────────────────────────────────────────────────
def check_orb_main() -> bool:
    """ORB main.py alive via PID file. Restart via VBS if dead."""
    if not ORB_PID_FILE.exists():
        log.warning("ORB PID file missing — starting main.py")
        alert("orb_dead",
              f"⚠️ <b>ORB main.py not running</b>\n🔧 Starting via ORBAgents.vbs\n"
              f"⏰ {datetime.now().strftime('%H:%M:%S')}")
        if _start_vbs(ORB_VBS):
            time.sleep(30)
            if ORB_PID_FILE.exists():
                resolved("orb_dead", "✅ <b>ORB main.py restarted</b>")
                return True
        return False

    try:
        pid = int(ORB_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        alert("orb_pid_bad", "⚠️ <b>ORB PID file corrupt</b>")
        return False

    if _pid_alive(pid):
        _clear_cooldown("orb_dead")
        return True

    log.warning("ORB PID %d is dead — restarting", pid)
    alert("orb_dead",
          f"🚨 <b>CRITICAL:</b> ORB main.py crashed (PID {pid})\n"
          f"🔧 Restarting via ORBAgents.vbs\n⏰ {datetime.now().strftime('%H:%M:%S')}")
    try:
        ORB_PID_FILE.unlink()
    except OSError:
        pass
    if _start_vbs(ORB_VBS):
        time.sleep(30)
        if ORB_PID_FILE.exists():
            resolved("orb_dead", "✅ <b>ORB main.py recovered</b>")
            return True
    alert("orb_fail",
          "🚨 <b>ORB RESTART FAILED</b> — manual intervention needed")
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
          f"⏰ {datetime.now().strftime('%H:%M:%S')}")
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
        "orb_main":   check_orb_main(),
        "cdp":        check_cdp(),
        "jarvis_bot": check_jarvis_bot(),
    }
    if not all(results.values()):
        failed = [k for k, v in results.items() if not v]
        log.warning("Failed checks: %s", failed)
    log.info("Cycle complete: %s", results)


def main() -> None:
    log.info("=" * 55)
    log.info("ORB Trading Watchdog")
    log.info("Telegram: %s", "configured" if BOT_TOKEN else "NOT CONFIGURED")
    log.info("PID file: %s", ORB_PID_FILE)
    log.info("Check interval: %ds", CHECK_EVERY)
    log.info("=" * 55)

    tg(f"🟢 <b>ORB Watchdog Started</b>\nChecking every {CHECK_EVERY}s\n"
       f"⏰ {datetime.now().strftime('%H:%M:%S')}")

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
