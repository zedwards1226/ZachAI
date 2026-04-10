"""
WeatherAlpha Bot Watchdog
- Monitors http://localhost:5000/api/health every 30s
- Restarts bot if it goes down (2 consecutive failures)
- Sends Telegram alert on crash + restart
- Does NOT start the bot on launch — assumes it's already running via VBS
"""

import time
import subprocess
import requests
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

BOT_SCRIPT   = r"C:\ZachAI\kalshi\bots\app.py"
HEALTH_URL   = "http://localhost:5000/api/health"
CHECK_EVERY  = 30       # seconds
FAIL_THRESH  = 2        # consecutive failures before restart

# Load Telegram config from trading .env
def _load_telegram():
    env_path = Path(r"C:\ZachAI\trading\.env")
    token = chat_id = None
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip()
    return token or os.environ.get("TELEGRAM_BOT_TOKEN"), chat_id or os.environ.get("TELEGRAM_CHAT_ID")

BOT_TOKEN, CHAT_ID = _load_telegram()

LOG_FILE = r"C:\ZachAI\logs\watchdog.log"
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def telegram(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning("Telegram notify failed: %s", e)


def is_healthy() -> bool:
    try:
        r = requests.get(HEALTH_URL, timeout=5)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


def kill_bot():
    """Kill any running app.py process."""
    try:
        # Find and kill python processes running app.py
        import ctypes
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"name='python.exe' AND CommandLine LIKE '%app.py%'\" "
             "| ForEach-Object { Stop-Process -Id $($_.ProcessId) -Force; $_.ProcessId }"],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            log.info("Killed bot PIDs: %s", result.stdout.strip().replace('\n', ', '))
    except Exception as e:
        log.warning("Kill bot error: %s", e)


def start_bot() -> subprocess.Popen:
    log.info("Starting WeatherAlpha bot...")
    return subprocess.Popen(
        ["pythonw", BOT_SCRIPT],
        cwd=str(Path(BOT_SCRIPT).parent),
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def main():
    log.info("=" * 50)
    log.info("Watchdog started — monitoring %s every %ss", HEALTH_URL, CHECK_EVERY)
    log.info("Telegram: %s", "configured" if BOT_TOKEN else "NOT configured")
    log.info("=" * 50)

    # Check if bot is already running
    if is_healthy():
        log.info("Bot is already running and healthy")
        telegram("<b>Watchdog Started</b>\nWeatherAlpha bot is running and healthy")
    else:
        log.warning("Bot is not running — starting it now")
        start_bot()
        time.sleep(10)
        if is_healthy():
            log.info("Bot started successfully")
            telegram("<b>Watchdog Started</b>\nWeatherAlpha bot was down — started it successfully")
        else:
            log.error("Bot failed to start")
            telegram("<b>Watchdog Started</b>\nWeatherAlpha bot FAILED to start — manual check needed")

    failures = 0

    while True:
        if is_healthy():
            if failures > 0:
                log.info("Bot recovered after %d failures", failures)
            failures = 0
        else:
            failures += 1
            log.warning("Health check failed (%d/%d)", failures, FAIL_THRESH)

            if failures >= FAIL_THRESH:
                now = datetime.now().strftime("%H:%M")
                log.error("Bot down — restarting...")
                telegram(f"<b>WeatherAlpha CRASHED</b> at {now}\nRestarting now...")

                kill_bot()
                time.sleep(3)
                start_bot()
                time.sleep(10)
                failures = 0

                if is_healthy():
                    log.info("Bot restarted successfully")
                    telegram("WeatherAlpha bot restarted successfully")
                else:
                    log.error("Bot failed to restart")
                    telegram("<b>WeatherAlpha FAILED to restart</b>\nManual intervention needed!")

        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
