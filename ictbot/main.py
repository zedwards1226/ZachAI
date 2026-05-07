"""ICTBot main loop — APScheduler with PID lock + startup ping.

Run with:  python -m main   (from inside ictbot/)
"""
from __future__ import annotations

import atexit
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from config import TIMEZONE, PAPER_MODE, SCAN_ONLY, LOG_LEVEL, ICT_SYMBOL
from data_layer.database import init_db, append_journal
from services.state_manager import (
    acquire_pid_lock, release_pid_lock, write_arm_status, can_trade_now,
)
from services import telegram
from services.ict_tv_client import health_check as cdp_health
from agents import monitor, briefing, learning

ET = pytz.timezone(TIMEZONE)


def _setup_logging() -> None:
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "ictbot.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _arm_check() -> None:
    """08:25 ET — verify CDP, paper mode, write arm_status.json."""
    ok_paper = PAPER_MODE
    ok_cdp, cdp_msg = cdp_health()
    armed = ok_paper and ok_cdp
    reason = "ok" if armed else f"paper={ok_paper} cdp={cdp_msg}"
    write_arm_status(armed=armed, source="auto", reason=reason)
    append_journal("arm_check", "info" if armed else "warn",
                   f"arm: {armed} ({reason})")
    telegram.send(f"arm: {'✅' if armed else '❌'} {reason}")


def _hard_close() -> None:
    """14:55 ET — close any open position, regardless of strategy."""
    from services.ict_tv_trader import close_position_market
    try:
        result = close_position_market(ICT_SYMBOL)
        append_journal("hard_close", "info", f"hard close result: {result}")
    except Exception as exc:
        append_journal("hard_close", "error", f"hard close failed: {exc}")


def main() -> int:
    _setup_logging()
    log = logging.getLogger("main")

    init_db()

    if not acquire_pid_lock():
        log.error("could not acquire pid lock — another ictbot is running")
        return 1
    atexit.register(release_pid_lock)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    log.info(
        "ICTBot starting symbol=%s PAPER_MODE=%s SCAN_ONLY=%s",
        ICT_SYMBOL, PAPER_MODE, SCAN_ONLY,
    )
    telegram.send(
        f"online @ {datetime.now(ET).strftime('%H:%M ET')}  "
        f"sym={ICT_SYMBOL} paper={PAPER_MODE} scan_only={SCAN_ONLY}"
    )

    sched = BlockingScheduler(timezone=ET)

    # Arm check before NY AM killzone
    sched.add_job(_arm_check, "cron", hour=8, minute=25, id="arm_check",
                  misfire_grace_time=600)

    # Monitor (scan + manage) every 30s during 08:30-16:00 ET
    sched.add_job(monitor.tick, "cron", second="*/30",
                  hour="8-16", id="monitor", misfire_grace_time=60)

    # Hard close 14:55
    sched.add_job(_hard_close, "cron", hour=14, minute=55, id="hard_close",
                  misfire_grace_time=300)

    # Morning briefing 07:00
    sched.add_job(briefing.run, "cron", hour=7, minute=0, id="briefing",
                  misfire_grace_time=3600)

    # Nightly learning 18:30
    sched.add_job(learning.run, "cron", hour=18, minute=30, id="learning",
                  misfire_grace_time=3600)

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("ictbot shutting down")
        return 0


if __name__ == "__main__":
    sys.exit(main())
