"""
APScheduler jobs for WeatherAlpha.
  - scan_job: every SCAN_INTERVAL_MINUTES during trade window
  - resolve_job: every 30 minutes (check settled markets)
  - snapshot_job: every hour
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from config import SCAN_INTERVAL_MINUTES, TIMEZONE
from trader import scan_and_trade, resolve_expired_trades
from database import snapshot_pnl, get_summary, get_guardrail_state
from config import STARTING_CAPITAL

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
        gs      = get_guardrail_state()
        snapshot_pnl(capital, gs.get("capital_at_risk_usd", 0))
    except Exception as exc:
        log.error("Snapshot job failed: %s", exc, exc_info=True)


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
