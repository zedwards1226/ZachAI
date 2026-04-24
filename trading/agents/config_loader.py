"""Runtime config overrides for the ORB learning agent.

Loads `state/learned_config.json` as overrides on top of `config.py`
defaults, and detects manual edits to that file (checksum drift vs
`state/learned_config.meta.json`).

Manual edits are detected on the next learning_agent run and logged to
`agent_journal` with `source='manual'`. Do not bypass this — the audit
trail is the whole point. In 3 months you will want to know where a
config drift came from.

Standalone on purpose — this module must not import from config.py
because config.py imports *us* at the end to apply overrides.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_STATE_DIR = _BASE_DIR / "state"
_CONFIG_PATH = _STATE_DIR / "learned_config.json"
_META_PATH = _STATE_DIR / "learned_config.meta.json"

# The 3 knobs the learning agent is allowed to touch. Any proposal or
# manual edit outside these bounds is rejected / ignored.
LEARNABLE_KNOBS: dict[str, dict] = {
    "SCORE_FULL_SIZE": {"min": 6, "max": 12, "step": 1, "type": "int"},
    "SCORE_HALF_SIZE": {"min": 3, "max": 9,  "step": 1, "type": "int"},
    "RVOL_THRESHOLD":  {"min": 1.2, "max": 2.0, "step": 0.1, "type": "float"},
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    """Write text to `path` atomically via tempfile + os.replace.

    Kill-between-writes safety: without this, a crash between the config
    and meta writes leaves a stale checksum and triggers spurious
    manual_edit alerts forever.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _coerce(key: str, val) -> Optional[float]:
    """Coerce to declared type, return None if invalid or out of bounds."""
    meta = LEARNABLE_KNOBS[key]
    try:
        if meta["type"] == "int":
            val = int(val)
        else:
            val = float(val)
    except (TypeError, ValueError):
        return None
    if val < meta["min"] or val > meta["max"]:
        return None
    return val


def load_overrides() -> dict:
    """Return {knob: value} from learned_config.json, filtered to valid knobs.

    Invalid types or out-of-bounds values are dropped with a warning.
    Called from config.py at import time.
    """
    if not _CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read learned_config.json: %s", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("learned_config.json must be a JSON object, got %s", type(data))
        return {}
    out: dict = {}
    for key in LEARNABLE_KNOBS:
        if key not in data:
            continue
        coerced = _coerce(key, data[key])
        if coerced is None:
            logger.warning("learned_config %s=%r invalid or out of bounds, ignoring",
                           key, data[key])
            continue
        out[key] = coerced
    return out


def _read_meta() -> dict:
    if not _META_PATH.exists():
        return {}
    try:
        return json.loads(_META_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def detect_manual_edit() -> Optional[dict]:
    """Return a drift dict if learned_config.json changed outside the agent.

    Shape: {"before": {...}, "after": {...}, "checksum": "..."}

    Returns None when:
      - file is missing
      - checksum matches meta (no drift)
      - meta file is missing AND config file is missing
    """
    if not _CONFIG_PATH.exists():
        return None
    try:
        current_text = _CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    current_sum = _sha256(current_text)
    meta = _read_meta()
    last_sum = meta.get("checksum")
    if last_sum == current_sum:
        return None
    before = meta.get("snapshot", {}) or {}
    try:
        after = json.loads(current_text)
        if not isinstance(after, dict):
            after = {}
    except json.JSONDecodeError:
        after = {}
    return {"before": before, "after": after, "checksum": current_sum}


def apply_proposal(updates: dict, source: str = "agent") -> dict:
    """Merge updates into learned_config.json and refresh meta.

    Returns the new full config dict. Raises ValueError if any key is not
    a learnable knob or value is out of bounds.
    """
    for key, val in updates.items():
        if key not in LEARNABLE_KNOBS:
            raise ValueError(f"{key!r} is not a learnable knob")
        if _coerce(key, val) is None:
            meta = LEARNABLE_KNOBS[key]
            raise ValueError(
                f"{key}={val!r} outside bounds [{meta['min']}, {meta['max']}]"
            )

    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    current: dict = {}
    if _CONFIG_PATH.exists():
        try:
            current = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(current, dict):
                current = {}
        except json.JSONDecodeError:
            current = {}

    for key, val in updates.items():
        current[key] = _coerce(key, val)

    text = json.dumps(current, indent=2, sort_keys=True)
    meta_text = json.dumps(
        {"checksum": _sha256(text), "last_source": source, "snapshot": current},
        indent=2, sort_keys=True,
    )
    _atomic_write(_CONFIG_PATH, text)
    _atomic_write(_META_PATH, meta_text)
    logger.info("learned_config updated (source=%s): %s", source, updates)
    return current


def acknowledge_current() -> None:
    """Accept the current learned_config.json as the new baseline.

    Called after logging a manual-edit drift row to `agent_journal` so
    subsequent runs don't keep alerting on the same drift.
    """
    if not _CONFIG_PATH.exists():
        if _META_PATH.exists():
            _META_PATH.unlink()
        return
    try:
        text = _CONFIG_PATH.read_text(encoding="utf-8")
        snapshot = json.loads(text)
        if not isinstance(snapshot, dict):
            snapshot = {}
    except (OSError, json.JSONDecodeError):
        return
    _atomic_write(
        _META_PATH,
        json.dumps(
            {"checksum": _sha256(text), "last_source": "manual", "snapshot": snapshot},
            indent=2, sort_keys=True,
        ),
    )


def revert_key(key: str) -> None:
    """Remove a single knob from learned_config.json (rollback to default)."""
    if not _CONFIG_PATH.exists():
        return
    try:
        current = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if key in current:
        del current[key]
        text = json.dumps(current, indent=2, sort_keys=True)
        meta_text = json.dumps(
            {"checksum": _sha256(text), "last_source": "revert",
             "snapshot": current},
            indent=2, sort_keys=True,
        )
        _atomic_write(_CONFIG_PATH, text)
        _atomic_write(_META_PATH, meta_text)
        logger.info("learned_config reverted: %s removed", key)
