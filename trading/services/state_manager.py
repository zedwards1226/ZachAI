"""State file manager — read/write JSON state files with atomic writes and file locking."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import msvcrt

from config import STATE_DIR

logger = logging.getLogger(__name__)

# Ensure state directory exists
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Max retries for file lock acquisition and os.replace
_LOCK_RETRIES = 5
_LOCK_DELAY = 0.05  # 50ms between lock retries
_REPLACE_RETRIES = 3
_REPLACE_DELAY = 0.1  # 100ms between replace retries


def _acquire_lock(lock_fd):
    """Acquire file lock with retries. Windows msvcrt, no-op on other platforms."""
    if sys.platform != "win32":
        return
    for attempt in range(_LOCK_RETRIES):
        try:
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if attempt == _LOCK_RETRIES - 1:
                raise
            time.sleep(_LOCK_DELAY * (attempt + 1))


def _release_lock(lock_fd):
    """Release file lock. Windows msvcrt, no-op on other platforms."""
    if sys.platform != "win32":
        return
    try:
        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def read_state(agent_name: str) -> dict:
    """Read state/{agent_name}.json. Returns {} if missing or corrupt.

    Uses file locking for read-safety during concurrent writes.
    """
    path = STATE_DIR / f"{agent_name}.json"
    if not path.exists():
        return {}

    lock_path = STATE_DIR / f"{agent_name}.lock"
    lock_fd = None
    try:
        lock_fd = open(lock_path, "w")
        _acquire_lock(lock_fd)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path, e)
        return {}
    finally:
        if lock_fd:
            _release_lock(lock_fd)
            lock_fd.close()


def write_state(agent_name: str, data: dict) -> None:
    """Atomic write to state/{agent_name}.json with file locking.

    Adds _updated_at timestamp. Uses temp file + os.replace for atomicity,
    wrapped in a file lock to prevent concurrent read/write corruption.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data["_updated_at"] = datetime.now(timezone.utc).isoformat()

    target = STATE_DIR / f"{agent_name}.json"
    lock_path = STATE_DIR / f"{agent_name}.lock"
    lock_fd = None

    try:
        lock_fd = open(lock_path, "w")
        _acquire_lock(lock_fd)

        # Write to temp file first, then atomic rename
        fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            # Retry os.replace for antivirus interference on Windows
            for attempt in range(_REPLACE_RETRIES):
                try:
                    os.replace(tmp_path, target)
                    break
                except PermissionError:
                    if attempt == _REPLACE_RETRIES - 1:
                        raise
                    time.sleep(_REPLACE_DELAY)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    finally:
        if lock_fd:
            _release_lock(lock_fd)
            lock_fd.close()


def read_all_states() -> dict[str, dict]:
    """Read all agent state files. Returns {agent_name: data}."""
    agents = ["structure", "memory", "sentinel", "sweep", "signal_log"]
    result = {}
    for name in agents:
        result[name] = read_state(name)
    return result


def is_state_fresh(agent_name: str, max_age_seconds: float) -> bool:
    """Check if a state file was updated within max_age_seconds."""
    data = read_state(agent_name)
    updated = data.get("_updated_at")
    if not updated:
        return False
    try:
        ts = datetime.fromisoformat(updated)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= max_age_seconds
    except (ValueError, TypeError):
        return False


def is_state_today(agent_name: str) -> bool:
    """Check if a state file has today's date."""
    data = read_state(agent_name)
    state_date = data.get("date")
    if not state_date:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    return state_date == today
