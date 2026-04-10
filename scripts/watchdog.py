"""
WeatherAlpha Bot Watchdog
- Monitors http://localhost:5000/api/health every 30s
- Restarts bot if it goes down
- Sends Telegram alert on crash + restart
"""

import time
import subprocess
import requests
import logging
import sys
from datetime import datetime
from pathlib import Path

BOT_SCRIPT   = r"C:\ZachAI\kalshi\bots\app.py"
HEALTH_URL   = "http://localhost:5000/api/health"
CHECK_EVERY  = 30       # seconds
FAIL_THRESH  = 2        # consecutive failures before restart
BOT_TOKEN    = "8671092372:AAGlY7Xlprq2JTrD7CFRywRfJvhZtOZiOEg"
CHAT_ID      = "6592347446"
LOG_FILE     = r"C:\ZachAI\logs\watchdog.log"

Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def telegram(msg: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
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


def start_bot() -> subprocess.Popen:
    log.info("Starting WeatherAlpha bot...")
    return subprocess.Popen(
        ["pythonw", BOT_SCRIPT],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def main():
    log.info("Watchdog started — monitoring %s every %ss", HEALTH_URL, CHECK_EVERY)
    telegram("Watchdog started — WeatherAlpha bot monitoring active")

    failures = 0
    proc = start_bot()
    time.sleep(10)  # give bot time to boot

    while True:
        if is_healthy():
            if failures > 0:
                log.info("Bot recovered")
            failures = 0
        else:
            failures += 1
            log.warning("Health check failed (%d/%d)", failures, FAIL_THRESH)

            if failures >= FAIL_THRESH:
                log.error("Bot down — restarting...")
                telegram(f"WeatherAlpha bot CRASHED at {datetime.now().strftime('%H:%M')} — restarting now")

                # Kill old process
                try:
                    proc.kill()
                except Exception:
                    pass

                time.sleep(3)
                proc = start_bot()
                time.sleep(10)
                failures = 0

                if is_healthy():
                    log.info("Bot restarted successfully")
                    telegram("WeatherAlpha bot restarted successfully")
                else:
                    log.error("Bot failed to restart")
                    telegram("WeatherAlpha bot FAILED to restart — manual intervention needed")

        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
