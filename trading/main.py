"""ORB Multi-Agent Trading System — Master Controller.

Single entry point: python main.py
Starts all agents via APScheduler. Manages state folder and logging.
"""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TIMEZONE, LOG_DIR, STATE_DIR
from agents import journal

logger = logging.getLogger("orb")
ET = pytz.timezone(TIMEZONE)


def setup_logging() -> None:
    """Configure rotating file + console logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — daily rotation, keep 14 days
    fh = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "trading.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)


# ─── Agent Wrappers (catch exceptions so scheduler doesn't die) ───

async def run_structure():
    try:
        from agents.structure import run
        await run()
    except Exception as e:
        logger.error("Structure agent failed: %s", e, exc_info=True)


async def run_memory():
    try:
        from agents.memory import run
        await run()
    except Exception as e:
        logger.error("Memory agent failed: %s", e, exc_info=True)


async def run_briefing():
    try:
        from agents.briefing import run
        await run()
    except Exception as e:
        logger.error("Briefing agent failed: %s", e, exc_info=True)


async def run_sentinel_initial():
    try:
        from agents.sentinel import run_initial
        await run_initial()
    except ImportError:
        logger.info("Sentinel agent not built yet")
    except Exception as e:
        logger.error("Sentinel initial failed: %s", e, exc_info=True)


async def run_sentinel_poll():
    try:
        from agents.sentinel import poll
        await poll()
    except ImportError:
        pass  # Not built yet
    except Exception as e:
        logger.error("Sentinel poll failed: %s", e, exc_info=True)


async def run_sweep_poll():
    try:
        from agents.sweep import poll
        await poll()
    except ImportError:
        pass  # Not built yet
    except Exception as e:
        logger.error("Sweep poll failed: %s", e, exc_info=True)


async def run_combiner_poll():
    try:
        from agents.combiner import poll
        await poll()
    except Exception as e:
        logger.error("Combiner poll failed: %s", e, exc_info=True)


async def run_trade_monitor():
    try:
        from services.tv_trader import monitor_trades
        await monitor_trades()
    except Exception as e:
        logger.error("Trade monitor failed: %s", e, exc_info=True)


async def run_weekly_report():
    try:
        await journal.weekly_report()
    except Exception as e:
        logger.error("Weekly report failed: %s", e, exc_info=True)


async def main():
    """Main entry point — initialize and start the scheduler."""
    setup_logging()
    logger.info("=" * 60)
    logger.info("ORB Multi-Agent Trading System starting")
    logger.info("Timezone: %s", TIMEZONE)
    logger.info("=" * 60)

    # Initialize
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    journal.init_db()

    # Create scheduler
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # ─── Scheduled Agents ───

    # Memory: 6:00 PM ET daily
    scheduler.add_job(run_memory, "cron", hour=18, minute=0,
                      id="memory", name="Memory Agent")

    # Sentinel initial: 8:00 AM ET
    scheduler.add_job(run_sentinel_initial, "cron", hour=8, minute=0,
                      id="sentinel_initial", name="Sentinel Initial")

    # Structure: 8:45 AM ET
    scheduler.add_job(run_structure, "cron", hour=8, minute=45,
                      id="structure", name="Structure Agent")

    # Morning briefing: 8:50 AM ET
    scheduler.add_job(run_briefing, "cron", hour=8, minute=50,
                      id="briefing", name="Morning Briefing")

    # ─── Interval Polls (check clock internally) ───
    # max_instances=1 + coalesce=True prevents overlapping runs if a poll
    # stalls (e.g. CDP hang) — late runs are dropped instead of piling up.

    # Sweep detector: every 15 seconds
    scheduler.add_job(run_sweep_poll, "interval", seconds=15,
                      id="sweep_poll", name="Sweep Poll",
                      max_instances=1, coalesce=True)

    # Sentinel continuous: every 60 seconds
    scheduler.add_job(run_sentinel_poll, "interval", seconds=60,
                      id="sentinel_poll", name="Sentinel Poll",
                      max_instances=1, coalesce=True)

    # Combiner: every 15 seconds
    scheduler.add_job(run_combiner_poll, "interval", seconds=15,
                      id="combiner_poll", name="Combiner Poll",
                      max_instances=1, coalesce=True)

    # Trade monitor: every 30 seconds
    scheduler.add_job(run_trade_monitor, "interval", seconds=30,
                      id="trade_monitor", name="Trade Monitor",
                      max_instances=1, coalesce=True)

    # Weekly journal report: Sunday 7:00 AM ET
    scheduler.add_job(run_weekly_report, "cron", day_of_week="sun",
                      hour=7, minute=0,
                      id="journal_weekly", name="Weekly Report")

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logger.info("  Job: %s — next run: %s", job.name, job.next_run_time)

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
