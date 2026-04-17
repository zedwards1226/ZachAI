"""Twilio SMS backup for critical alerts.

Set in trading/.env:
  TWILIO_ACCOUNT_SID=...
  TWILIO_AUTH_TOKEN=...
  TWILIO_FROM=+15551234567
  ALERT_PHONE=+1YOURNUMBER

Use sparingly — only for failures Telegram can't deliver (phone off WiFi,
Telegram outage). No-op if creds not configured.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def _load() -> dict:
    cfg = {k: os.environ.get(k, "") for k in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "ALERT_PHONE"
    )}
    if not all(cfg.values()):
        try:
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k.strip() in cfg and not cfg[k.strip()]:
                            cfg[k.strip()] = v.strip()
        except Exception:
            pass
    return cfg


_CFG = _load()


def configured() -> bool:
    return all(_CFG.values())


async def send(msg: str) -> bool:
    """Send one SMS (truncated to 160 chars). Returns True on success."""
    if not configured():
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{_CFG['TWILIO_ACCOUNT_SID']}/Messages.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                auth=(_CFG["TWILIO_ACCOUNT_SID"], _CFG["TWILIO_AUTH_TOKEN"]),
                data={
                    "From": _CFG["TWILIO_FROM"],
                    "To": _CFG["ALERT_PHONE"],
                    "Body": msg[:160],
                },
            )
            if r.status_code in (200, 201):
                return True
            logger.warning("Twilio %d: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Twilio send failed: %s", e)
    return False
