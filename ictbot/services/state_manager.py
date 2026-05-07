"""ICTBot runtime state — arm gate, daily counters, cross-bot halt check.

Read-write JSON files in `state/`. Plus convenience accessors for SQLite-backed
trade counts (used by risk caps).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytz

from config import (
    TIMEZONE, RISK_STATE_PATH, ORB_STATE_DIR,
    DAILY_LOSS_LIMIT_DOLLARS, WEEKLY_LOSS_LIMIT_DOLLARS,
    MAX_CONSECUTIVE_LOSSES, MAX_TRADES_PER_SESSION,
)
from data_layer.database import get_connection, DB_PATH

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

STATE_DIR = Path(__file__).parent.parent / "state"
ARM_STATUS_PATH = STATE_DIR / "arm_status.json"
PID_PATH = STATE_DIR / "ictbot.pid"


def _now_iso() -> str:
    return datetime.now(ET).isoformat()


# ─── Arm gate ────────────────────────────────────────────────────────
def write_arm_status(armed: bool, source: str, reason: str = "") -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "armed": armed,
        "source": source,                 # 'auto' | 'manual'
        "reason": reason,
        "updated_at": _now_iso(),
    }
    ARM_STATUS_PATH.write_text(json.dumps(payload, indent=2))


def read_arm_status() -> dict[str, Any]:
    if not ARM_STATUS_PATH.exists():
        return {"armed": False, "source": "missing", "reason": "no arm file", "updated_at": None}
    try:
        return json.loads(ARM_STATUS_PATH.read_text())
    except Exception as exc:
        logger.warning("arm_status.json unreadable: %s", exc)
        return {"armed": False, "source": "error", "reason": str(exc), "updated_at": None}


# ─── Cross-bot halt ──────────────────────────────────────────────────
def is_cross_bot_halted() -> tuple[bool, str]:
    """Return (halted, reason). Reads /data/risk_state.json shared with ORB."""
    if not RISK_STATE_PATH.exists():
        return False, "no risk_state.json"
    try:
        state = json.loads(RISK_STATE_PATH.read_text())
        if state.get("global_halt"):
            return True, state.get("halt_reason", "global_halt set")
        if state.get("ictbot_halt"):
            return True, state.get("ictbot_halt_reason", "ictbot_halt set")
        return False, "ok"
    except Exception as exc:
        logger.warning("risk_state.json unreadable: %s", exc)
        return False, f"unreadable: {exc}"


# ─── ORB state read-only ─────────────────────────────────────────────
def orb_arm_status() -> dict[str, Any]:
    """Read ORB's arm_status.json — informational only, never modify."""
    p = ORB_STATE_DIR / "arm_status.json"
    if not p.exists():
        return {"armed": None, "reason": "ORB arm file missing"}
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        return {"armed": None, "reason": f"unreadable: {exc}"}


# ─── Daily counters from SQLite ──────────────────────────────────────
def trades_today(date_iso: str | None = None) -> int:
    date_iso = date_iso or datetime.now(ET).strftime("%Y-%m-%d")
    with get_connection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE substr(entry_time,1,10)=?",
            (date_iso,),
        ).fetchone()
        return int(row["n"] or 0)


def pnl_today(date_iso: str | None = None) -> float:
    date_iso = date_iso or datetime.now(ET).strftime("%Y-%m-%d")
    with get_connection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl_dollars), 0.0) AS p FROM trades "
            "WHERE substr(exit_time,1,10)=?",
            (date_iso,),
        ).fetchone()
        return float(row["p"] or 0.0)


def pnl_week() -> float:
    today = datetime.now(ET).date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    with get_connection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl_dollars), 0.0) AS p FROM trades "
            "WHERE substr(exit_time,1,10)>=?",
            (week_start.isoformat(),),
        ).fetchone()
        return float(row["p"] or 0.0)


def consecutive_losses() -> int:
    with get_connection(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT pnl_dollars FROM trades WHERE exit_time IS NOT NULL "
            "ORDER BY exit_time DESC LIMIT 10"
        ).fetchall()
    streak = 0
    for r in rows:
        if (r["pnl_dollars"] or 0.0) < 0:
            streak += 1
        else:
            break
    return streak


# ─── Master gate combiner ────────────────────────────────────────────
def can_trade_now() -> tuple[bool, str]:
    """Combined risk-cap check. Returns (ok, reason). Use before any entry."""
    halted, reason = is_cross_bot_halted()
    if halted:
        return False, f"cross_bot_halt: {reason}"

    if trades_today() >= MAX_TRADES_PER_SESSION:
        return False, f"daily_trade_cap: {MAX_TRADES_PER_SESSION}"

    if pnl_today() <= -DAILY_LOSS_LIMIT_DOLLARS:
        return False, f"daily_loss_cap: ${DAILY_LOSS_LIMIT_DOLLARS}"

    if pnl_week() <= -WEEKLY_LOSS_LIMIT_DOLLARS:
        return False, f"weekly_loss_cap: ${WEEKLY_LOSS_LIMIT_DOLLARS}"

    if consecutive_losses() >= MAX_CONSECUTIVE_LOSSES:
        return False, f"consecutive_losses: {MAX_CONSECUTIVE_LOSSES}"

    arm = read_arm_status()
    if not arm.get("armed"):
        return False, f"not_armed: {arm.get('reason')}"

    return True, "ok"


# ─── PID lock ────────────────────────────────────────────────────────
def acquire_pid_lock() -> bool:
    """Atomic-ish PID lock. Returns True if acquired, False if another instance is alive."""
    import os
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            existing_pid = int(PID_PATH.read_text().strip())
            # On Windows, sending signal 0 isn't reliable; check via psutil if available
            try:
                import psutil  # type: ignore
                if psutil.pid_exists(existing_pid):
                    logger.error("ictbot already running, pid=%s", existing_pid)
                    return False
            except ImportError:
                # Fallback: check if file is recent (<10 min) — assume running
                age = datetime.now().timestamp() - PID_PATH.stat().st_mtime
                if age < 600:
                    logger.warning("pidfile recent (%ds old), assuming alive", int(age))
                    return False
        except Exception:
            pass
    PID_PATH.write_text(str(os.getpid()))
    return True


def release_pid_lock() -> None:
    if PID_PATH.exists():
        try:
            PID_PATH.unlink()
        except Exception:
            pass
