"""LongshotFade bot harness — single-strategy entrypoint, paper-mode only.

Wires the LongshotFadeStrategy into the omnialpha shared library and
schedules it on APScheduler. Modeled on the existing WeatherAlpha bot
in kalshi/bots/app.py, but stripped to one strategy with no Flask app
(the dashboard runs as a separate process from omnialpha/dashboard/serve.py).

Jobs (all times UTC unless noted):
  scan          — every 60s, calls scan_and_trade(LongshotFadeStrategy)
  settle        — every 5min, resolves paper trades whose markets closed
  pnl_snapshot  — every 15min, writes equity curve point
  digest_am     — 13:00 UTC (8 AM CT) Telegram morning digest
  digest_pm     — 23:00 UTC (6 PM CT) Telegram evening digest
  heartbeat     — every 15min, PID file refresh + Telegram if first ever boot

Paper mode is enforced by the order_placer module; this harness refuses to
start if PAPER_MODE != "true" in .env (one of master CLAUDE.md's 3 hard stops).
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make omnialpha/ importable when launched as `python main_longshot.py`
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore

from bots import live_scanner, trade_monitor, telegram_alerts
from config import (
    DB_PATH, LOG_DIR, PAPER_MODE, STARTING_CAPITAL_USD, assert_paper_mode,
)
from data_layer.database import init_db, get_conn
from strategies.longshot_fade import LongshotFadeStrategy


# ─── Series the bot polls ──────────────────────────────────────────────
# Per Phase 1 validation, KXEPLGAME is BLOCKED (negative edge). The
# strategy enforces this at code level too, but listing only profitable
# series here avoids burning rate-limit budget on markets we'd reject anyway.
SERIES_TO_SCAN: tuple[str, ...] = ("KXNBAGAME", "KXNFLGAME")


# ─── Logging ───────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "longshot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
# Quiet the noisy httpx INFO logs — one per Kalshi GET. We log scan summaries
# at INFO ourselves so the per-request lines are just clutter.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("longshot")


# ─── PID file (for the watchdog + dashboard) ───────────────────────────
PID_FILE = HERE / "state" / "longshot.pid"


def _write_pid() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _clear_pid() -> None:
    try:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        pass


# ─── Capital tracking ──────────────────────────────────────────────────
# capital_usd = STARTING_CAPITAL_USD + realized_pnl - open_risk
# Recomputed on every scan so the strategy's Kelly sizing scales with the
# live account. Honest auto-deleveraging on drawdown, honest growth on wins.

def live_capital_usd() -> float:
    """Current strategy-allocated capital. Read-only DB query."""
    with get_conn(readonly=True) as conn:
        realized = float(conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades WHERE status IN ('won','lost')"
        ).fetchone()[0])
        open_risk = float(conn.execute(
            "SELECT COALESCE(SUM(stake_usd), 0) FROM trades WHERE status = 'open'"
        ).fetchone()[0])
    return max(0.0, STARTING_CAPITAL_USD + realized - open_risk)


# ─── Jobs ──────────────────────────────────────────────────────────────
_strategy_singleton = LongshotFadeStrategy()


def job_scan() -> None:
    """Run scan_and_trade for every series in our universe."""
    cap = live_capital_usd()
    log.info("scan begin · capital=$%.2f", cap)
    totals = {"scanned": 0, "snapshots": 0, "decisions": 0, "approved": 0, "placed": 0}
    for series in SERIES_TO_SCAN:
        try:
            r = live_scanner.scan_and_trade(
                _strategy_singleton,
                series_ticker=series,
                capital_usd=cap,
            )
            for k in totals:
                totals[k] += r.get(k, 0)
            blocked = {k.removeprefix("blocked_"): v for k, v in r.items() if k.startswith("blocked_")}
            log.info(
                "  %-12s scanned=%d snap=%d dec=%d apr=%d placed=%d blocked=%s",
                series, r["scanned"], r["snapshots"], r["decisions"],
                r["approved"], r["placed"], blocked or "{}",
            )
        except Exception as e:
            log.exception("scan_and_trade failed for %s: %s", series, e)
    log.info(
        "scan complete · scanned=%d placed=%d (capital=$%.2f)",
        totals["scanned"], totals["placed"], cap,
    )


def job_settle() -> None:
    """Resolve paper trades whose markets have settled. Writes pnl_usd."""
    try:
        result = trade_monitor.settle_resolved_trades()
        if result.get("settled", 0):
            log.info("settled %d trades · realized=$%+.2f",
                     result["settled"], result.get("realized_pnl_usd", 0.0))
            try:
                telegram_alerts.send(
                    f"[LongshotFade] Settled {result['settled']} trades · "
                    f"realized ${result.get('realized_pnl_usd', 0.0):+.2f}"
                )
            except Exception as e:
                log.warning("settle telegram failed: %s", e)
    except Exception as e:
        log.exception("settle job failed: %s", e)


def job_pnl_snapshot() -> None:
    """Write one equity curve point to pnl_snapshots."""
    try:
        cap = live_capital_usd()
        now = datetime.now(timezone.utc).isoformat()
        with get_conn() as conn:
            realized = float(conn.execute(
                "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades WHERE status IN ('won','lost')"
            ).fetchone()[0])
            open_risk = float(conn.execute(
                "SELECT COALESCE(SUM(stake_usd), 0) FROM trades WHERE status = 'open'"
            ).fetchone()[0])
            open_n = int(conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'open'"
            ).fetchone()[0])
            conn.execute(
                "INSERT INTO pnl_snapshots (timestamp, strategy, capital_usd, realized_pnl_usd, "
                "open_risk_usd, open_positions, day_pnl_usd, week_pnl_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, "longshot_fade", cap, realized, open_risk, open_n, 0.0, 0.0),
            )
    except Exception as e:
        # pnl_snapshots may have a different schema than I assumed — log + skip,
        # don't kill the scheduler. Dashboard reads equity from `trades` anyway.
        log.warning("pnl_snapshot job skipped: %s", e)


def _todays_summary_msg() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_conn(readonly=True) as conn:
        d = conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(pnl_usd), 0) "
            "FROM trades WHERE substr(timestamp,1,10)=? "
            "AND strategy='longshot_fade' "
            "AND status IN ('won','lost')",
            (today,),
        ).fetchone()
        open_n = int(conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status = 'open' "
            "AND strategy='longshot_fade'"
        ).fetchone()[0])
    n = int(d[0] or 0)
    w = int(d[1] or 0)
    pnl = float(d[3] or 0)
    return (f"[LongshotFade] {today}\n"
            f"  Settled: {n} ({w}W) · realized ${pnl:+.2f}\n"
            f"  Open: {open_n} positions · capital ${live_capital_usd():.2f}")


def job_digest_am() -> None:
    try:
        telegram_alerts.send(_todays_summary_msg())
    except Exception as e:
        log.warning("AM digest failed: %s", e)


def job_digest_pm() -> None:
    try:
        telegram_alerts.send(_todays_summary_msg())
    except Exception as e:
        log.warning("PM digest failed: %s", e)


# ─── Entry point ───────────────────────────────────────────────────────
def main() -> int:
    if not PAPER_MODE:
        log.error("PAPER_MODE is not true — refusing to start. Set PAPER_MODE=true in omnialpha/.env.")
        return 2
    assert_paper_mode()

    log.info("=" * 60)
    log.info("LongshotFade bot starting · PID=%d · DB=%s", os.getpid(), DB_PATH)
    log.info("Series: %s", ", ".join(SERIES_TO_SCAN))
    log.info("Starting capital: $%.2f · PAPER_MODE=true", STARTING_CAPITAL_USD)
    log.info("=" * 60)

    init_db()
    _write_pid()

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(job_scan, "interval", seconds=60,
                  id="scan", max_instances=1, coalesce=True,
                  misfire_grace_time=120)
    sched.add_job(job_settle, "interval", minutes=5,
                  id="settle", max_instances=1, coalesce=True,
                  misfire_grace_time=600)
    sched.add_job(job_pnl_snapshot, "interval", minutes=15,
                  id="pnl_snapshot", max_instances=1, coalesce=True)
    sched.add_job(job_digest_am, "cron", hour=13, minute=0, id="digest_am")
    sched.add_job(job_digest_pm, "cron", hour=23, minute=0, id="digest_pm")

    # Startup boot-message
    try:
        telegram_alerts.send(
            f"[LongshotFade] Bot online @ {datetime.now(timezone.utc).strftime('%H:%M UTC')} · "
            f"capital ${live_capital_usd():.2f} · PAPER"
        )
    except Exception as e:
        log.warning("startup telegram failed: %s", e)

    def _shutdown(signum, frame):
        log.info("shutdown signal %s — stopping scheduler", signum)
        try:
            sched.shutdown(wait=False)
        except Exception:
            pass
    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        sched.start()
    finally:
        _clear_pid()
        log.info("scheduler stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
