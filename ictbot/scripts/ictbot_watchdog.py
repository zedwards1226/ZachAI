"""ICTBot watchdog — checks PID lock + CDP :9223 + recent log activity, restarts if dead.

Designed to be invoked by Task Scheduler every 5 min. Uses a local mutex file
so multiple invocations don't pile up.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(r"C:\ZachAI\ictbot")
PID_PATH = PROJECT_DIR / "state" / "ictbot.pid"
LOG_PATH = PROJECT_DIR / "logs" / "ictbot.log"
WATCHDOG_LOG = PROJECT_DIR / "logs" / "watchdog.log"
WATCHDOG_MUTEX = PROJECT_DIR / "state" / "watchdog.lock"
START_VBS = PROJECT_DIR / "scripts" / "start_ictbot.vbs"
START_BROWSER_VBS = PROJECT_DIR / "scripts" / "start_ictbot_browser.vbs"

CDP_URL = "http://127.0.0.1:9223/json/version"
STALE_LOG_MINUTES = 10  # if log not touched in this long, assume hang


def _log(msg: str) -> None:
    WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with WATCHDOG_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def acquire_mutex(timeout_seconds: int = 60) -> bool:
    if WATCHDOG_MUTEX.exists():
        age = time.time() - WATCHDOG_MUTEX.stat().st_mtime
        if age < timeout_seconds:
            return False
    WATCHDOG_MUTEX.parent.mkdir(parents=True, exist_ok=True)
    WATCHDOG_MUTEX.write_text(str(os.getpid()))
    return True


def release_mutex() -> None:
    if WATCHDOG_MUTEX.exists():
        try:
            WATCHDOG_MUTEX.unlink()
        except Exception:
            pass


def pid_alive() -> bool:
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text().strip())
    except Exception:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        # Fallback: assume alive if pid file fresh
        age = time.time() - PID_PATH.stat().st_mtime
        return age < 600


def cdp_alive() -> bool:
    try:
        with urllib.request.urlopen(CDP_URL, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def log_recent() -> bool:
    if not LOG_PATH.exists():
        return False
    age = (datetime.now() - datetime.fromtimestamp(LOG_PATH.stat().st_mtime))
    return age < timedelta(minutes=STALE_LOG_MINUTES)


def restart_bot() -> None:
    _log("restarting bot via VBS")
    subprocess.Popen(["wscript.exe", str(START_VBS)], shell=False)


def restart_browser() -> None:
    _log("restarting browser via VBS")
    subprocess.Popen(["wscript.exe", str(START_BROWSER_VBS)], shell=False)


def main() -> int:
    if not acquire_mutex():
        return 0

    try:
        if not cdp_alive():
            _log("CDP :9223 dead — relaunching browser")
            restart_browser()
            time.sleep(8)

        if not pid_alive():
            _log("bot pid dead — restarting")
            restart_bot()
            return 0

        if not log_recent():
            _log("log stale (>10min) — bot may be hung; restarting")
            restart_bot()
            return 0

        _log("ok")
        return 0
    finally:
        release_mutex()


if __name__ == "__main__":
    sys.exit(main())
