"""Monitor agent — wakes every 30s during NY killzones to scan + manage."""
from __future__ import annotations

import logging
from datetime import datetime, time as dt_time

import pytz

from config import (
    TIMEZONE, NY_AM_START, NY_AM_END, NY_PM_START, NY_PM_END, HARD_CLOSE,
)
from services import telegram
from services import setup_scanner
from services import trade_manager
from services.state_manager import can_trade_now

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


def in_killzone(now_et: datetime | None = None) -> tuple[bool, str]:
    now_et = now_et or datetime.now(ET)
    t = now_et.time()
    if NY_AM_START <= t <= NY_AM_END:
        return True, "ny_am"
    if NY_PM_START <= t <= NY_PM_END:
        return True, "ny_pm"
    return False, "off"


def tick() -> None:
    """One monitor cycle. Called by APScheduler every 30s."""
    now = datetime.now(ET)
    in_zone, zone = in_killzone(now)

    # Trade manager always runs (an open position past killzone still needs
    # exit handling)
    try:
        trade_manager.monitor_once(telegram_send=telegram.send)
    except Exception:
        logger.exception("trade_manager tick failed")

    if not in_zone:
        return

    # Risk caps
    ok, reason = can_trade_now()
    if not ok:
        logger.debug("scan skipped: %s", reason)
        return

    try:
        setup_scanner.scan_once(telegram_send=telegram.send)
    except Exception:
        logger.exception("setup_scanner tick failed")
