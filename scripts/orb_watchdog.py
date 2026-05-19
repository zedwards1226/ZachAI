"""ORB Trading System Watchdog.

Monitors ORB stack every 60s and auto-recovers:
  - main.py (via state/orb.pid + process liveness)
  - TradingView CDP (http://localhost:9222/json)
  - Jarvis Telegram bot (process scan)
  - OmniAlpha main + dashboard, ORB dashboard

Actions:
  - Restart dead processes via their VBS launchers
  - Telegram alerts on state change (with 1-hour cooldown per key)
  - Holds a Windows wake-lock so the machine never idle-sleeps while the
    trading stack is up (see _hold_wake_lock below)
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


# ─── Wake-lock ────────────────────────────────────────────────────────────
# 2026-05-14: the laptop kept entering Modern Standby (S0) on idle even with
# powercfg standby-timeout set to 0 — because standby-timeout does NOT govern
# Modern Standby's user-presence "Idle Timeout". The reliable cross-platform
# fix is SetThreadExecutionState: while this watchdog process is alive it
# tells Windows "system required, do not idle-sleep". Same mechanism VLC /
# PowerPoint / video players use. ES_CONTINUOUS makes it persist until reset.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def _hold_wake_lock() -> bool:
    """Tell Windows to stay awake while this process runs. Returns True on success."""
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        )
        return True
    except Exception:
        return False

# ─── Paths ────────────────────────────────────────────────────────────────
TRADING_DIR = Path(r"C:\ZachAI\trading")
SCRIPTS_DIR = Path(r"C:\ZachAI\scripts")
LOG_DIR = TRADING_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "orb_watchdog.log"

ORB_PID_FILE = TRADING_DIR / "state" / "orb.pid"
ORB_VBS = SCRIPTS_DIR / "ORBAgents.vbs"
JARVIS_VBS = SCRIPTS_DIR / "Jarvis_Bot.vbs"
OMNIALPHA_DASHBOARD_VBS = SCRIPTS_DIR / "OmniAlpha_Dashboard.vbs"
OMNIALPHA_VBS = SCRIPTS_DIR / "OmniAlpha.vbs"
OMNIALPHA_PID_FILE = Path(r"C:\ZachAI\omnialpha\state\omnialpha.pid")
ORB_DASHBOARD_VBS = SCRIPTS_DIR / "ORB_Dashboard.vbs"

# ─── Endpoints ────────────────────────────────────────────────────────────
CDP_URL = "http://localhost:9222/json/version"
OMNIALPHA_DASHBOARD_URL = "http://localhost:8503/"
ORB_DASHBOARD_URL = "http://localhost:8502/api/health"
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
# Use UTF-8 for stdout too — Windows cp1252 default chokes on emoji and
# spams "UnicodeEncodeError" to the log when alerts contain 🚨/⚠️/✅.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
    # os.kill(pid, 0) raises OSError on Windows — use OpenProcess instead.
    if sys.platform == "win32":
        import ctypes
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
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
        # Before restarting, check if main.py is already running (PID file lost).
        # On Windows os.kill(pid,9) silently fails, so spawned instances crash,
        # their atexit deletes the PID file, and we loop forever.
        live_pids = _find_processes("main.py")
        if live_pids:
            pid = live_pids[0]
            try:
                ORB_PID_FILE.write_text(str(pid))
                log.info("ORB running as PID %d but PID file was missing — restored", pid)
                resolved("orb_dead", f"✅ <b>ORB running (PID {pid})</b> — PID file restored")
            except OSError as e:
                log.error("Failed to restore PID file: %s", e)
            return True

        log.warning("ORB PID file missing and no main.py process found — starting")
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


def check_omnialpha_main() -> bool:
    """OmniAlpha main.py alive via PID file. Restart via OmniAlpha.vbs if dead.

    Added 2026-05-12 after discovering PID 2832 (last night's restart) died
    silently after ~110 minutes. omnialpha.db-wal sat untouched for 22 hours
    before we noticed. Mirrors check_orb_main() pattern: trust PID file first,
    fall back to process-name scan, restart via VBS on death.
    """
    if not OMNIALPHA_PID_FILE.exists():
        # PID file missing — try to find a running omnialpha main.py before restarting
        live_pids = _find_processes("omnialpha")
        # Filter to actual main.py (exclude dashboard's serve.py)
        live_main = []
        for pid in live_pids:
            try:
                cmd_check = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine"],
                    capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW,
                )
                if "main.py" in cmd_check.stdout and "serve.py" not in cmd_check.stdout:
                    live_main.append(pid)
            except Exception:
                pass
        if live_main:
            pid = live_main[0]
            try:
                OMNIALPHA_PID_FILE.write_text(str(pid))
                log.info("OmniAlpha running as PID %d but PID file missing — restored", pid)
                resolved("omnialpha_dead", f"✅ <b>OmniAlpha running (PID {pid})</b> — PID file restored")
            except OSError as e:
                log.error("Failed to restore OmniAlpha PID file: %s", e)
            return True

        log.warning("OmniAlpha PID file missing and no main.py process found — starting")
        alert("omnialpha_dead",
              f"⚠️ <b>OmniAlpha main.py not running</b>\n🔧 Starting via OmniAlpha.vbs\n"
              f"⏰ {datetime.now().strftime('%H:%M:%S')}")
        if _start_vbs(OMNIALPHA_VBS):
            time.sleep(15)
            if OMNIALPHA_PID_FILE.exists():
                resolved("omnialpha_dead", "✅ <b>OmniAlpha main.py started</b>")
                return True
        return False

    try:
        pid = int(OMNIALPHA_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        alert("omnialpha_pid_bad", "⚠️ <b>OmniAlpha PID file corrupt</b>")
        return False

    if _pid_alive(pid):
        _clear_cooldown("omnialpha_dead")
        return True

    log.warning("OmniAlpha PID %d is dead — restarting", pid)
    alert("omnialpha_dead",
          f"🚨 <b>OmniAlpha main.py crashed (PID {pid})</b>\n"
          f"🔧 Restarting via OmniAlpha.vbs\n⏰ {datetime.now().strftime('%H:%M:%S')}")
    try:
        OMNIALPHA_PID_FILE.unlink()
    except OSError:
        pass
    if _start_vbs(OMNIALPHA_VBS):
        time.sleep(15)
        if OMNIALPHA_PID_FILE.exists():
            resolved("omnialpha_dead", "✅ <b>OmniAlpha main.py recovered</b>")
            return True
    alert("omnialpha_fail",
          "🚨 <b>OmniAlpha RESTART FAILED</b> — manual: "
          "wscript C:\\ZachAI\\scripts\\OmniAlpha.vbs")
    return False


def check_omnialpha_dashboard() -> bool:
    """OmniAlpha dashboard on :8503. Auto-restart via VBS if down.

    Added 2026-05-11 after the dashboard silently died sometime overnight
    and we only caught it during morning-readiness checks. The VBS launcher
    has anti-double-launch logic so re-firing it when alive is a no-op.

    Streamlit serves /healthz and / both 200 when alive — just check / with
    a short timeout. 2 attempts (handles transient Streamlit slow-rerender).
    """
    for attempt in range(2):
        try:
            r = requests.get(OMNIALPHA_DASHBOARD_URL, timeout=5)
            if r.status_code == 200:
                _clear_cooldown("omnialpha_dashboard_down")
                return True
        except Exception:
            pass
        if attempt == 0:
            time.sleep(2)

    log.warning("OmniAlpha dashboard :8503 not responding — restarting")
    alert("omnialpha_dashboard_down",
          f"📊 <b>OmniAlpha dashboard down</b> (:8503)\n"
          f"🔧 Restarting via OmniAlpha_Dashboard.vbs\n"
          f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    if _start_vbs(OMNIALPHA_DASHBOARD_VBS):
        time.sleep(10)
        try:
            r = requests.get(OMNIALPHA_DASHBOARD_URL, timeout=5)
            if r.status_code == 200:
                resolved("omnialpha_dashboard_down",
                         f"✅ <b>OmniAlpha dashboard recovered</b>\n"
                         f"⏰ {datetime.now().strftime('%H:%M:%S')}")
                return True
        except Exception:
            pass
    alert("omnialpha_dashboard_fail",
          "🚨 <b>OmniAlpha dashboard RESTART FAILED</b> — manual: "
          "wscript C:\\ZachAI\\scripts\\OmniAlpha_Dashboard.vbs")
    return False


def check_orb_dashboard() -> bool:
    """ORB dashboard on :8502. Auto-restart via VBS if down.

    Added 2026-05-13 when the ORB React+Flask dashboard shipped. Mirrors
    check_omnialpha_dashboard exactly — HTTP GET against /api/health with
    2 attempts (handles transient Flask slow-startup), VBS relaunch on
    persistent failure, Telegram alert + auto-recovery message.
    """
    for attempt in range(2):
        try:
            r = requests.get(ORB_DASHBOARD_URL, timeout=5)
            if r.status_code == 200:
                _clear_cooldown("orb_dashboard_down")
                return True
        except Exception:
            pass
        if attempt == 0:
            time.sleep(2)

    log.warning("ORB dashboard :8502 not responding — restarting")
    alert("orb_dashboard_down",
          f"📊 <b>ORB dashboard down</b> (:8502)\n"
          f"🔧 Restarting via ORB_Dashboard.vbs\n"
          f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    if _start_vbs(ORB_DASHBOARD_VBS):
        time.sleep(10)
        try:
            r = requests.get(ORB_DASHBOARD_URL, timeout=5)
            if r.status_code == 200:
                resolved("orb_dashboard_down",
                         f"✅ <b>ORB dashboard recovered</b>\n"
                         f"⏰ {datetime.now().strftime('%H:%M:%S')}")
                return True
        except Exception:
            pass
    alert("orb_dashboard_fail",
          "🚨 <b>ORB dashboard RESTART FAILED</b> — manual: "
          "wscript C:\\ZachAI\\scripts\\ORB_Dashboard.vbs")
    return False


def check_jarvis_bot() -> bool:
    """Telegram Jarvis bot alive. Auto-restart via VBS if dead.

    Added 2026-05-12 retry-once: PowerShell process scan can time out under
    load (the 15s subprocess timeout fires, _find_processes returns empty,
    watchdog mistakenly thinks bot is dead). Tonight that cascaded into 4
    duplicate bot.py instances all conflicting on Telegram getUpdates,
    causing message storm. Retry once with 2s gap before declaring dead.
    """
    if _find_processes("bot.py"):
        _clear_cooldown("jarvis_down")
        return True
    # First scan returned empty — could be a real death OR a PowerShell timeout
    # under system load. Wait 2s and retry once before triggering a restart.
    time.sleep(2)
    if _find_processes("bot.py"):
        _clear_cooldown("jarvis_down")
        return True

    log.warning("Jarvis bot not running (confirmed by retry) — restarting via Jarvis_Bot.vbs")
    alert("jarvis_down",
          f"⚠️ <b>Jarvis Telegram bot dead</b>\n"
          f"🔧 Restarting via Jarvis_Bot.vbs\n"
          f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    if _start_vbs(JARVIS_VBS):
        time.sleep(5)
        if _find_processes("bot.py"):
            resolved("jarvis_down",
                     f"✅ <b>Jarvis bot recovered</b>\n"
                     f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            return True
    alert("jarvis_fail",
          "🚨 <b>Jarvis bot RESTART FAILED</b> — manual: "
          "wscript C:\\ZachAI\\scripts\\Jarvis_Bot.vbs")
    return False


# ─── ORB Bulletproof v1 (added 2026-05-18) ────────────────────────────────
# Five additional checks that catch silent-failure modes that today's
# disasters revealed. Each runs every cycle, each only alerts once per
# cooldown, each is defensive (returns True on its own error so it can't
# break the watchdog).
import json
import sqlite3
import re

ORB_TRADING_LOG    = TRADING_DIR / "logs" / "trading.log"
ORB_BROKER_STATE   = TRADING_DIR / "state" / "broker_state.json"
ORB_ACTIVE_ORDERS  = TRADING_DIR / "state" / "active_orders.json"
ORB_JOURNAL_DB     = TRADING_DIR / "journal.db"
ORB_SUMMARY_URL    = "http://localhost:8502/api/summary"

# Per-check consecutive-failure counters (escalate after N consecutive)
_orb_drift_consec = 0
_orb_stuck_scan_consec = 0
ORB_DRIFT_ESCALATE_AFTER = 3   # 3 cycles (~3 min) of state drift -> alert
ORB_STUCK_SCAN_AFTER     = 3   # 3 cycles (~3 min) of no combiner activity -> restart
ORB_UNTRACKED_PNL_THRESH = 50.0  # USD — alert if dashboard untracked_pnl exceeds this
ORB_PREFLIGHT_HOUR_ET    = 9   # 9:25 ET = 5 min before RTH
ORB_PREFLIGHT_MIN_ET     = 25
ORB_ENTRY_THRESHOLD      = 5   # score >= this would normally take a trade


def _now_et_components() -> tuple[int, int, int]:
    """Return (weekday 0=Mon-6=Sun, hour, minute) in America/New_York."""
    try:
        from zoneinfo import ZoneInfo
        n = datetime.now(ZoneInfo("America/New_York"))
        return n.weekday(), n.hour, n.minute
    except Exception:
        # Fallback: assume local == ET (close enough for the time-window check)
        n = datetime.now()
        return n.weekday(), n.hour, n.minute


def _is_rth_now() -> bool:
    """True if current time is within US RTH (9:30–16:00 ET, Mon–Fri)."""
    wd, h, m = _now_et_components()
    if wd >= 5:  # Sat/Sun
        return False
    minutes = h * 60 + m
    return 9 * 60 + 30 <= minutes < 16 * 60


def check_orb_stuck_scan() -> bool:
    """During RTH, ensure the bot is actively scanning. Tail trading.log for
    the most recent 'Combiner Poll executed successfully' marker. If older
    than 3 min during RTH, bot is hung — restart and alert.
    """
    global _orb_stuck_scan_consec
    if not _is_rth_now():
        _orb_stuck_scan_consec = 0
        _clear_cooldown("orb_stuck_scan")
        return True
    if not ORB_TRADING_LOG.exists():
        return True  # log not initialized yet, don't false-alarm
    try:
        # Tail last ~200 lines (cheap on Windows even for big logs)
        with open(ORB_TRADING_LOG, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 32_000))
            tail = f.read().splitlines()
        last_ts = None
        for line in reversed(tail):
            if "Combiner Poll" in line and "executed successfully" in line:
                # Format: "2026-05-18 09:35:04 INFO ..."
                m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if m:
                    last_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    break
        if last_ts is None:
            return True  # no marker found yet — bot may have just started
        age_s = (datetime.now() - last_ts).total_seconds()
        if age_s > 180:  # 3 min
            _orb_stuck_scan_consec += 1
            if _orb_stuck_scan_consec >= ORB_STUCK_SCAN_AFTER:
                log.warning("ORB stuck scan — last combiner poll %.0fs ago (cycles=%d)",
                            age_s, _orb_stuck_scan_consec)
                alert("orb_stuck_scan",
                      f"🚨 <b>ORB STUCK — no scan for {int(age_s)}s during RTH</b>\n"
                      f"Last Combiner Poll: {last_ts.strftime('%H:%M:%S')}\n"
                      f"🔧 Restarting via ORBAgents.vbs\n"
                      f"⏰ {datetime.now().strftime('%H:%M:%S')}")
                # Kill + restart
                try:
                    if ORB_PID_FILE.exists():
                        pid = int(ORB_PID_FILE.read_text().strip())
                        if _pid_alive(pid):
                            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                           capture_output=True, creationflags=_NO_WINDOW)
                        ORB_PID_FILE.unlink(missing_ok=True)
                except Exception as e:
                    log.error("Failed to kill stuck ORB: %s", e)
                _start_vbs(ORB_VBS)
                _orb_stuck_scan_consec = 0
            return False
        else:
            _orb_stuck_scan_consec = 0
            _clear_cooldown("orb_stuck_scan")
            return True
    except Exception as e:
        log.debug("check_orb_stuck_scan error: %s", e)
        return True  # fail-open — don't break watchdog


def check_orb_state_drift() -> bool:
    """Compare TV broker position count to local active_orders. If divergent
    for 3+ consecutive cycles, alert. Catches phantom positions early
    (before the soft-drift escalation inside the bot would, AND from
    outside the bot in case the bot's reconcile is itself hung).
    """
    global _orb_drift_consec
    try:
        if not ORB_BROKER_STATE.exists():
            return True
        broker = json.loads(ORB_BROKER_STATE.read_text(encoding="utf-8"))
        tv_count = int(broker.get("tv_position_count") or 0)
        local_count = int(broker.get("local_active_orders") or 0)
        if tv_count == local_count:
            _orb_drift_consec = 0
            _clear_cooldown("orb_state_drift")
            return True
        _orb_drift_consec += 1
        if _orb_drift_consec >= ORB_DRIFT_ESCALATE_AFTER:
            alert("orb_state_drift",
                  f"🚨 <b>ORB STATE DRIFT — {_orb_drift_consec}+ cycles</b>\n"
                  f"TV broker shows {tv_count} position(s), bot tracks {local_count}.\n"
                  f"TV avail: ${broker.get('available_funds')}\n"
                  f"Signal: {broker.get('tv_signal')}\n\n"
                  f"<b>Action:</b> Open TradingView → close MNQ position manually.\n"
                  f"Bot will auto-resume within 60s after TV is flat.\n"
                  f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            return False
        return True
    except Exception as e:
        log.debug("check_orb_state_drift error: %s", e)
        return True


def check_orb_balance_discrepancy() -> bool:
    """Read /api/summary. If untracked_pnl_usd > $50, hidden P&L has appeared
    (typically from a phantom position or unrecorded trade). Alert once
    per cooldown so user knows the dashboard's "real" balance moved
    without a journal trade explaining it.
    """
    try:
        r = requests.get(ORB_SUMMARY_URL, timeout=5)
        if r.status_code != 200:
            return True
        data = r.json()
        untracked = float(data.get("untracked_pnl_usd") or 0)
        if abs(untracked) >= ORB_UNTRACKED_PNL_THRESH:
            direction = "LOSS" if untracked > 0 else "GAIN"
            alert("orb_balance_discrepancy",
                  f"🚨 <b>ORB HIDDEN {direction} ${abs(untracked):.2f}</b>\n"
                  f"Computed (journal-only): ${data.get('computed_capital_usd')}\n"
                  f"Real broker balance:     ${data.get('current_capital_usd')}\n"
                  f"Gap means a position opened/closed without ORB tracking it.\n"
                  f"<b>Action:</b> Check TradingView for phantom positions or "
                  f"trades you placed manually.\n"
                  f"⏰ {datetime.now().strftime('%H:%M:%S')}")
            return False
        _clear_cooldown("orb_balance_discrepancy")
        return True
    except Exception as e:
        log.debug("check_orb_balance_discrepancy error: %s", e)
        return True


def check_orb_preflight() -> bool:
    """At 9:25 ET each weekday, run a pre-RTH health check and send a single
    Telegram with the pass/fail summary. Cooldown is 1 day so this fires
    once per session.
    """
    wd, h, m = _now_et_components()
    if wd >= 5 or h != ORB_PREFLIGHT_HOUR_ET or m != ORB_PREFLIGHT_MIN_ET:
        return True
    key = f"orb_preflight_{datetime.now().strftime('%Y%m%d')}"
    if not _cooldown_ok(key):
        return True  # already ran today
    items = []
    # 1) CDP
    try:
        r = requests.get(CDP_URL, timeout=5)
        items.append(("CDP 9222", r.status_code == 200))
    except Exception:
        items.append(("CDP 9222", False))
    # 2) ORB main alive
    items.append(("ORB main", ORB_PID_FILE.exists() and
                  _pid_alive(int(ORB_PID_FILE.read_text().strip()))))
    # 3) Dashboard responding
    try:
        items.append(("ORB dashboard", requests.get(
            ORB_DASHBOARD_URL, timeout=5).status_code == 200))
    except Exception:
        items.append(("ORB dashboard", False))
    # 4) Broker state fresh + has funds + no phantom
    try:
        broker = json.loads(ORB_BROKER_STATE.read_text(encoding="utf-8"))
        items.append(("Broker reachable", broker.get("available_funds") is not None))
        items.append(("Funds > $0", float(broker.get("available_funds") or 0) > 0))
        items.append(("No phantom position",
                      int(broker.get("tv_position_count") or 0) ==
                      int(broker.get("local_active_orders") or 0)))
    except Exception:
        items.append(("Broker state", False))
    # 5) Untracked PnL clean
    try:
        data = requests.get(ORB_SUMMARY_URL, timeout=5).json()
        items.append(("Capital matches journal",
                      abs(float(data.get("untracked_pnl_usd") or 0)) < 1.0))
    except Exception:
        pass
    all_pass = all(ok for _, ok in items)
    lines = "\n".join(f"  {'✅' if ok else '❌'} {name}" for name, ok in items)
    if all_pass:
        tg(f"✅ <b>ORB Preflight Pass</b> ({datetime.now().strftime('%H:%M')})\n{lines}\n"
           f"Ready for 9:30 RTH open.")
    else:
        failed = [n for n, ok in items if not ok]
        tg(f"❌ <b>ORB Preflight FAIL</b> ({datetime.now().strftime('%H:%M')})\n{lines}\n\n"
           f"<b>Action needed:</b> fix {', '.join(failed)} before 9:30 ET.")
    return all_pass


def check_orb_signal_without_trade() -> bool:
    """Detect signals scored high enough to trade that didn't result in an
    order. Cross-reference signal_history vs trades. If the block_reason
    is a TECHNICAL failure (not a deliberate risk-mgmt skip), alert —
    that's the case Zach asked about ("it sees a trade but can't trade").
    """
    if not ORB_JOURNAL_DB.exists():
        return True
    try:
        # Read-only connection so the bot's writes are never locked
        conn = sqlite3.connect(f"file:{ORB_JOURNAL_DB}?mode=ro", uri=True, timeout=5)
        c = conn.cursor()
        # Make sure signal_history exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signal_history'")
        if not c.fetchone():
            conn.close()
            return True
        # Look at signals from last 10 minutes that scored high
        # but have no matching trade. Use timestamp diff in the DB layer.
        # signal_history schema: id, date, time, direction, score, block_reason, ...
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute(
            "SELECT id, time, direction, score, block_reason "
            "FROM signal_history "
            "WHERE date = ? AND score >= ? "
            "AND time(time) >= time('now', '-10 minutes', 'localtime') "
            "ORDER BY id DESC",
            (today, ORB_ENTRY_THRESHOLD),
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            return True
        # Technical (NOT-by-design) failure patterns
        TECHNICAL_PATTERNS = (
            "broker_disconnect", "dom_not_ready", "side_not_found",
            "circuit_breaker", "circuit_open", "FAILED_PLACEMENT",
            "phantom_position", "submit_failed", "submit_not_found",
            "exception", "place_bracket_order failed", "tp_sl_",
        )
        # Risk-mgmt skips that are intentional — don't alert on these
        EXPECTED_PATTERNS = (
            "Daily trade limit", "consecutive losses", "loss cap",
            "Edge .* below minimum", "Strike type 'less'", "news",
            "Ensemble spread", "Outside trade window", "Score below threshold",
            "risk_too_wide", "halt",
        )
        for sig_id, sig_time, direction, score, reason in rows:
            reason = reason or ""
            is_technical = any(p.lower() in reason.lower() for p in TECHNICAL_PATTERNS)
            is_expected = any(re.search(p, reason, re.IGNORECASE) for p in EXPECTED_PATTERNS)
            if is_technical and not is_expected:
                key = f"orb_signal_skip_{sig_id}"
                if _cooldown_ok(key):
                    alert(key,
                          f"🚨 <b>ORB SAW TRADE BUT COULDN'T EXECUTE</b>\n"
                          f"Signal #{sig_id} at {sig_time}: {direction} score={score}\n"
                          f"Reason: <code>{reason[:150]}</code>\n"
                          f"<b>Action:</b> investigate plumbing — broker, CDP, "
                          f"or DOM state\n"
                          f"⏰ {datetime.now().strftime('%H:%M:%S')}")
                return False
        return True
    except Exception as e:
        log.debug("check_orb_signal_without_trade error: %s", e)
        return True


# ─── Main loop ────────────────────────────────────────────────────────────
def run_cycle() -> None:
    log.info("--- ORB watchdog cycle ---")
    results = {
        "orb_main":            check_orb_main(),
        "orb_dashboard":       check_orb_dashboard(),
        "cdp":                 check_cdp(),
        "jarvis_bot":          check_jarvis_bot(),
        "omnialpha_main":      check_omnialpha_main(),
        "omnialpha_dashboard": check_omnialpha_dashboard(),
        # ORB bulletproof v1 (2026-05-18)
        "orb_stuck_scan":      check_orb_stuck_scan(),
        "orb_state_drift":     check_orb_state_drift(),
        "orb_balance_discrep": check_orb_balance_discrepancy(),
        "orb_preflight":       check_orb_preflight(),
        "orb_signal_skip":     check_orb_signal_without_trade(),
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
    wake = _hold_wake_lock()
    log.info("Wake-lock: %s", "HELD (machine will not idle-sleep)" if wake else "NOT HELD")
    log.info("=" * 55)

    tg(f"🟢 <b>ORB Watchdog Started</b>\nChecking every {CHECK_EVERY}s\n"
       f"{'🔒 wake-lock held' if wake else '⚠️ wake-lock NOT held'}\n"
       f"⏰ {datetime.now().strftime('%H:%M:%S')}")

    while True:
        try:
            # Re-assert the wake-lock every cycle. ES_CONTINUOUS should persist
            # on its own, but re-asserting is cheap insurance against anything
            # that resets the thread execution state.
            _hold_wake_lock()
            run_cycle()
        except KeyboardInterrupt:
            log.info("Watchdog stopped by user")
            # Release the wake-lock so the machine can sleep normally again
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                pass
            tg("🔴 <b>ORB Watchdog Stopped</b> (manual)")
            break
        except Exception as e:
            log.error("Cycle error: %s", e, exc_info=True)
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
