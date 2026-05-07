"""ICTBot Telegram client — separate bot + channel from Jarvis bridge.

Uses bot HTTP API directly (no python-telegram-bot dep). Messages are
prefixed `[ICTBot]` so notifications never blend with ORB's.
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_PREFIX

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send(text: str, silent: bool = False) -> bool:
    """Send a single message. Returns True on success."""
    if not is_configured():
        logger.warning("telegram not configured; would have sent: %s", text)
        return False
    full = f"{TELEGRAM_PREFIX} {text}" if not text.startswith(TELEGRAM_PREFIX) else text
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": full,
        "disable_notification": "true" if silent else "false",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.warning("telegram send failed: %s", exc)
        return False


def send_silent(text: str) -> bool:
    return send(text, silent=True)
