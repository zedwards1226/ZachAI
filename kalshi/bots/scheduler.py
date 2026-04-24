"""
APScheduler jobs for WeatherAlpha.
  - scan_job: every SCAN_INTERVAL_MINUTES during trade window
  - resolve_job: every 30 minutes (check settled markets)
  - snapshot_job: every hour
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import SCAN_INTERVAL_MINUTES, TIMEZONE
from trader import scan_and_trade, resolve_expired_trades
from database import snapshot_pnl, get_summary, get_open_trades
from config import STARTING_CAPITAL
from monitor import send_daily_digest
from learning_agent import run_review as run_agent_review

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scan_job():
    try:
        scan_and_trade()
    except Exception as exc:
        log.error("Scan job failed: %s", exc, exc_info=True)


def _resolve_job():
    try:
        resolve_expired_trades()
    except Exception as exc:
        log.error("Resolve job failed: %s", exc, exc_info=True)


def _snapshot_job():
    try:
        summary = get_summary()
        capital = STARTING_CAPITAL + summary["total_pnl_usd"]
        # Live-compute open risk from actual trades — the cached
        # guardrail counter gets zeroed at midnight and triggered
        # spurious RESYNC alerts.
        open_risk = round(sum(t["stake_usd"] for t in get_open_trades()), 2)
        snapshot_pnl(capital, open_risk)
    except Exception as exc:
        log.error("Snapshot job failed: %s", exc, exc_info=True)


def _morning_digest_job():
    try:
        send_daily_digest("morning")
    except Exception as exc:
        log.error("Morning digest failed: %s", exc, exc_info=True)


def _eod_digest_job():
    try:
        send_daily_digest("eod")
    except Exception as exc:
        log.error("EOD digest failed: %s", exc, exc_info=True)


def _learning_agent_job():
    try:
        run_agent_review()
    except Exception as exc:
        log.error("Learning agent review failed: %s", exc, exc_info=True)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    tz = pytz.timezone(TIMEZONE)
    _scheduler = BackgroundScheduler(timezone=tz)

    _scheduler.add_job(
        _scan_job,
        trigger=IntervalTrigger(minutes=SCAN_INTERVAL_MINUTES, timezone=tz),
        id="scan",
        name="WeatherAlpha market scan",
        replace_existing=True,
    )
    _scheduler.add_job(
        _resolve_job,
        trigger=IntervalTrigger(minutes=30, timezone=tz),
        id="resolve",
        name="Resolve expired trades",
        replace_existing=True,
    )
    _scheduler.add_job(
        _snapshot_job,
        trigger=IntervalTrigger(minutes=60, timezone=tz),
        id="snapshot",
        name="P&L snapshot",
        replace_existing=True,
    )
    _scheduler.add_job(
        _morning_digest_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=tz),
        id="digest_morning",
        name="Morning digest (8 AM ET)",
        replace_existing=True,
    )
    _scheduler.add_job(
        _eod_digest_job,
        trigger=CronTrigger(hour=18, minute=0, timezone=tz),
        id="digest_eod",
        name="EOD digest (6 PM ET)",
        replace_existing=True,
    )
    _scheduler.add_job(
        _learning_agent_job,
        trigger=CronTrigger(hour=18, minute=30, timezone=tz),
        id="learning_agent",
        name="Learning agent review (6:30 PM)",
        replace_existing=True,
    )

    _scheduler.start()
    log.info("Scheduler started — scan every %d min", SCAN_INTERVAL_MINUTES)
    return _scheduler


def stop_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")


def trigger_scan_now():
    """Manually trigger a scan outside the schedule."""
    return scan_and_trade()
