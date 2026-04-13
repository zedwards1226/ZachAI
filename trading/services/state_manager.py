"""State file manager — read/write JSON state files with atomic writes."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import STATE_DIR

logger = logging.getLogger(__name__)

# Ensure state directory exists
STATE_DIR.mkdir(parents=True, exist_ok=True)


def read_state(agent_name: str) -> dict:
    """Read state/{agent_name}.json. Returns {} if missing or corrupt."""
    path = STATE_DIR / f"{agent_name}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path, e)
        return {}


def write_state(agent_name: str, data: dict) -> None:
    """Atomic write to state/{agent_name}.json. Adds _updated_at timestamp."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data["_updated_at"] = datetime.now(timezone.utc).isoformat()

    target = STATE_DIR / f"{agent_name}.json"

    # Write to temp file first, then atomic rename
    fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, target)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
