"""ORB Multi-Agent Trading System — Master Controller.

Single entry point: python main.py
Starts all agents via APScheduler. Manages state folder and logging.
"""
from __future__ import annotations

import asyncio
import atexit
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TIMEZONE, LOG_DIR, STATE_DIR, is_trading_day
from agents import journal
from services import telegram
from services.tv_client import get_client

logger = logging.getLogger("orb")
ET = pytz.timezone(TIMEZONE)

# ─── Single-instance guard ─────────────────────────────────────
PID_FILE = STATE_DIR / "orb.pid"


def _acquire_pid_lock() -> None:
    """Ensure only one main.py runs at a time. Kill stale instances."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        old_pid = PID_FILE.read_text().strip()
        try:
            old_pid = int(old_pid)
            # Check if process is actually running
            os.kill(old_pid, 0)  # signal 0 = check existence
            # Process exists — kill it so we take over with latest code
            logger.warning("Killing stale ORB instance PID %d", old_pid)
            os.kill(old_pid, 9)
            import time
            time.sleep(1)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass  # Process already dead or PID invalid

    PID_FILE.write_text(str(os.getpid()))
    atexit.register(_release_pid_lock)


def _release_pid_lock() -> None:
    """Clean up PID file on exit."""
    try:
        if PID_FILE.exists():
            stored = PID_FILE.read_text().strip()
            if stored == str(os.getpid()):
                PID_FILE.unlink()
    except Exception:
        pass


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
        if not is_trading_day():
            return
        from agents.sentinel import poll
        await poll()
    except ImportError:
        pass  # Not built yet
    except Exception as e:
        logger.error("Sentinel poll failed: %s", e, exc_info=True)


async def run_sweep_poll():
    try:
        if not is_trading_day():
            return
        from agents.sweep import poll
        await poll()
    except ImportError:
        pass  # Not built yet
    except Exception as e:
        logger.error("Sweep poll failed: %s", e, exc_info=True)


async def run_combiner_poll():
    try:
        if not is_trading_day():
            return
        from agents.combiner import poll
        await poll()
    except Exception as e:
        logger.error("Combiner poll failed: %s", e, exc_info=True)


async def run_trade_monitor():
    try:
        if not is_trading_day():
            return
        from services.tv_trader import monitor_trades
        await monitor_trades()
    except Exception as e:
        logger.error("Trade monitor failed: %s", e, exc_info=True)


async def run_weekly_report():
    try:
        await journal.weekly_report()
    except Exception as e:
        logger.error("Weekly report failed: %s", e, exc_info=True)


async def run_preflight():
    try:
        if not is_trading_day():
            return
        from agents.preflight import run
        await run()
    except Exception as e:
        logger.error("Preflight failed: %s", e, exc_info=True)


async def run_journal_backup():
    """Daily backup of journal.db — keeps last 30 days."""
    try:
        import shutil
        from config import JOURNAL_DB
        backup_dir = STATE_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        today = datetime.now(ET).strftime("%Y-%m-%d")
        backup_path = backup_dir / f"journal_{today}.db"
        if not backup_path.exists() and JOURNAL_DB.exists():
            shutil.copy2(str(JOURNAL_DB), str(backup_path))
            logger.info("Journal backed up to %s", backup_path)
            # Clean up backups older than 30 days
            backups = sorted(backup_dir.glob("journal_*.db"))
            for old_backup in backups[:-30]:
                old_backup.unlink()
    except Exception as e:
        logger.error("Journal backup failed: %s", e, exc_info=True)


async def run_briefing_heartbeat():
    """Post-briefing Telegram ping so Zach knows morning agents ran."""
    try:
        if not is_trading_day():
            return
        now_et = datetime.now(ET)
        await telegram.send(f"ORB morning agents ran @ {now_et.strftime('%I:%M %p ET')}")
    except Exception:
        logger.exception("Briefing heartbeat failed")


async def run_combiner_heartbeat():
    """Market-open Telegram ping confirming combiner is armed."""
    try:
        if not is_trading_day():
            return
        now_et = datetime.now(ET)
        await telegram.send(f"ORB combiner armed @ {now_et.strftime('%I:%M %p ET')} — scanning for setups")
    except Exception:
        logger.exception("Combiner heartbeat failed")


async def main():
    """Main entry point — initialize and start the scheduler."""
    setup_logging()

    # Kill any stale instance before starting
    _acquire_pid_lock()

    logger.info("=" * 60)
    logger.info("ORB Multi-Agent Trading System starting (PID %d)", os.getpid())
    now_et = datetime.now(ET)
    now_local = datetime.now()
    logger.info("TZ target=%s | ET now=%s | System now=%s | offset=%s",
                TIMEZONE,
                now_et.strftime("%Y-%m-%d %H:%M:%S %Z%z"),
                now_local.strftime("%Y-%m-%d %H:%M:%S"),
                now_et.utcoffset())
    logger.info("=" * 60)

    # Startup Telegram ping — if this never arrives, boot failed silently
    try:
        await telegram.send(
            f"ORB online @ {now_et.strftime('%Y-%m-%d %I:%M %p ET')} "
            f"(PID {os.getpid()})"
        )
    except Exception:
        logger.exception("Startup Telegram ping failed")

    # Initialize
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    journal.init_db()

    # Recover any active orders from a previous crash
    from services.tv_trader import load_and_reconcile_orders
    await load_and_reconcile_orders()

    # Create scheduler — misfire_grace_time=3600 lets jobs run up to 1h late
    # instead of silently skipping on any clock drift. Without this a 1-second
    # hiccup = permanently missed morning briefing.
    scheduler = AsyncIOScheduler(
        timezone=TIMEZONE,
        job_defaults={"misfire_grace_time": 3600, "coalesce": True},
    )

    # ─── Scheduled Agents ───

    # Memory: 7:30 AM ET (pre-market refresh — catches overnight gaps before briefing)
    scheduler.add_job(run_memory, "cron", hour=7, minute=30,
                      id="memory_morning", name="Memory Agent (Morning)")

    # Memory: 6:00 PM ET daily (primary end-of-day analysis)
    scheduler.add_job(run_memory, "cron", hour=18, minute=0,
                      id="memory", name="Memory Agent")

    # Morning preflight: 7:00 AM ET (verify stack before open)
    scheduler.add_job(run_preflight, "cron", hour=7, minute=0,
                      id="preflight", name="Morning Preflight")

    # Sentinel initial: 8:00 AM ET
    scheduler.add_job(run_sentinel_initial, "cron", hour=8, minute=0,
                      id="sentinel_initial", name="Sentinel Initial")

    # Structure: 8:45 AM ET
    scheduler.add_job(run_structure, "cron", hour=8, minute=45,
                      id="structure", name="Structure Agent")

    # Morning briefing: 8:50 AM ET
    scheduler.add_job(run_briefing, "cron", hour=8, minute=50,
                      id="briefing", name="Morning Briefing")

    # Heartbeat: 8:55 AM ET — confirms briefing/structure/sentinel fired
    scheduler.add_job(run_briefing_heartbeat, "cron", hour=8, minute=55,
                      id="briefing_heartbeat", name="Briefing Heartbeat")

    # Heartbeat: 9:31 AM ET — confirms combiner is active at market open
    scheduler.add_job(run_combiner_heartbeat, "cron", hour=9, minute=31,
                      id="combiner_heartbeat", name="Combiner Heartbeat")

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

    # Daily journal backup: 6:00 AM ET
    scheduler.add_job(run_journal_backup, "cron", hour=6, minute=0,
                      id="journal_backup", name="Journal Backup")

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logger.info("  Job: %s — next run: %s", job.name, job.next_run_time)

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        await _graceful_shutdown(scheduler)


async def _graceful_shutdown(scheduler) -> None:
    """Graceful shutdown — close trades, disconnect services, stop scheduler."""
    logger.info("Graceful shutdown initiated...")

    # 1. Stop scheduler (prevent new trades)
    scheduler.shutdown(wait=False)

    # 2. Close all active trades at current price
    from services.tv_trader import get_active_orders, close_position
    active = get_active_orders()
    if active:
        try:
            tv = await get_client()
            quote = await tv.get_quote()
            price = quote.get("last") or quote.get("close", 0)
            if price > 0:
                for trade_id in list(active.keys()):
                    try:
                        await close_position(trade_id, price, "System shutdown")
                    except Exception as e:
                        logger.error("Failed to close trade %d: %s", trade_id, e)
                logger.info("Closed %d active trade(s) on shutdown", len(active))
                await telegram.send(
                    f"System shutting down — {len(active)} trade(s) closed at {price:.2f}"
                )
        except Exception as e:
            logger.error("Failed to close trades on shutdown: %s", e)

    # 3. Disconnect CDP
    try:
        from services.tv_client import disconnect
        await disconnect()
    except Exception:
        pass

    # 4. Close Telegram httpx client
    try:
        await telegram.close()
    except Exception:
        pass

    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
