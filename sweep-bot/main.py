"""Sweep-Bot entry point.

Runs a 15-second poll loop during 09:30-14:30 ET that reads
trading/state/sweep.json, scores SWEEP_CONFIRMED events, and fires
paper trades independent of the ORB bot.

Usage:
    python main.py               # normal live-poll mode
    python main.py --once        # single pass, exit
    python main.py --dry-run     # don't fire trades, just log what would fire
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Prepend trading/ so we can import its modules.
TRADING = Path("C:/ZachAI/trading")
sys.path.insert(0, str(TRADING))
sys.path.insert(0, str(Path(__file__).parent))

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402

import sb_config as sb  # noqa: E402
from config import TIMEZONE, is_trading_day  # trading/config.py  # noqa: E402
from services import telegram  # noqa: E402
from hunter import poll_once  # noqa: E402

ET = pytz.timezone(TIMEZONE)


def _setup_logging() -> None:
    sb.LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(sb.LOG_FILE, maxBytes=5_000_000, backupCount=5,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s — %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler(sys.stdout))


async def _poll_wrapper(dry_run: bool = False) -> None:
    try:
        await poll_once(dry_run=dry_run)
    except Exception:
        logging.getLogger("sweep_bot").exception("poll_once failed")


async def _run_forever(dry_run: bool) -> None:
    scheduler = AsyncIOScheduler(
        timezone=ET,
        job_defaults={"misfire_grace_time": 60, "coalesce": True, "max_instances": 1},
    )
    scheduler.add_job(
        _poll_wrapper, "interval", seconds=sb.POLL_INTERVAL_SEC,
        id="sweep_poll", args=[dry_run],
    )
    scheduler.start()

    now = datetime.now(ET)
    await telegram.send(
        f"🌊 <b>SWEEP-BOT online</b>\n"
        f"Started at {now.strftime('%H:%M:%S')} ET\n"
        f"Session: {sb.SESSION_START_HOUR:02d}:{sb.SESSION_START_MINUTE:02d}"
        f"–{sb.SESSION_END_HOUR:02d}:{sb.SESSION_END_MINUTE:02d}\n"
        f"Max trades/day: {sb.MAX_SWEEP_TRADES}"
        + ("\n<i>DRY-RUN MODE — no orders will be placed</i>" if dry_run else "")
    )

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="run a single poll and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="don't place orders, just log what would fire")
    args = parser.parse_args()

    _setup_logging()
    log = logging.getLogger("sweep_bot")

    now = datetime.now(ET)
    if not is_trading_day(now):
        log.info("Not a trading day — exiting")
        return

    if args.once:
        asyncio.run(_poll_wrapper(dry_run=args.dry_run))
        return

    asyncio.run(_run_forever(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
