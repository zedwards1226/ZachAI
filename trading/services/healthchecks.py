"""Healthchecks.io ping wrapper.

Usage: set HEALTHCHECK_ORB_URL in trading/.env to your check URL.
Agents call `ping()` after successful cycles and `ping_fail(reason)` on errors.
No-op if URL not set — safe to deploy before signup.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_URL = os.environ.get("HEALTHCHECK_ORB_URL", "")
if not _URL:
    try:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("HEALTHCHECK_ORB_URL="):
                    _URL = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass


async def ping(suffix: str = "") -> None:
    """Success ping (suffix empty). Fire-and-forget."""
    if not _URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(f"{_URL}{suffix}")
    except Exception as e:
        logger.debug("Healthcheck ping failed: %s", e)


async def ping_fail(reason: str = "") -> None:
    """Failure ping — marks the check as down in Healthchecks.io."""
    body = reason[:100] if reason else ""
    if not _URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{_URL}/fail", content=body)
    except Exception as e:
        logger.debug("Healthcheck fail-ping failed: %s", e)


async def ping_start() -> None:
    """Mark start of a long-running job (for timing)."""
    await ping("/start")
