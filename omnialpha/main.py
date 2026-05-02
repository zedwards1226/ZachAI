"""OmniAlpha main loop — APScheduler-driven, paper-mode by default.

Jobs (all paper-safe in this version):
  - settle_open_trades        every 30s — settle any paper trades whose
                                 underlying markets resolved
  - write_pnl_snapshot        every 60s — periodic equity curve point
  - daily_summary             07:00 ET — Telegram summary of yesterday
  - update_risk_state         every 60s — write our section to shared
                                 risk_state.json so other bots can see
                                 our P&L + open positions

Strategy polling is NOT in this version. The first strategy
(crypto_midband) currently runs against historical data only — its
backtest is the validation. To actually place paper trades on live
markets, we'd need an authenticated client + a live-data feed; that's
the cutover step (separate session, with Zach's eyes on it).

What this loop DOES achieve in paper mode:
  - All scaffolding and lifecycle works
  - Telegram alerts wired
  - DB snapshots running
  - Cross-bot risk-state coupling active
  - Restart-safe: schedulers + DB survive crashes
  - Auto-start via scripts/OmniAlpha.vbs
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow `python main.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from apscheduler.schedulers.blocking import BlockingScheduler

from bots import telegram_alerts
from bots.risk_engine import update_my_section
from bots.trade_monitor import settle_resolved_trades, write_pnl_snapshot
from config import (
    LOG_DIR,
    PAPER_MODE,
    STARTING_CAPITAL_USD,
)
from data_layer.database import get_conn, init_db


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "omnialpha.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


log = logging.getLogger("omnialpha")


def job_settle() -> None:
    try:
        result = settle_resolved_trades()
        if result["settled"] > 0:
            log.info("Settled %d trades (P&L $%+.2f)",
                     result["settled"], result["total_pnl_usd"])
    except Exception as e:
        log.exception("settle job failed: %s", e)
        telegram_alerts.notify_error("settle_resolved_trades", e)


def job_pnl_snapshot() -> None:
    try:
        snap = write_pnl_snapshot(starting_capital_usd=STARTING_CAPITAL_USD)
        # Update cross-bot risk-state with our latest P&L
        update_my_section(
            bot="omnialpha",
            daily_pnl_usd=snap["realized_today"],
            weekly_pnl_usd=snap["realized_total"],   # rolling — refine later
            open_positions=snap["open_positions"],
            last_trade_ts=snap["timestamp"],
        )
    except Exception as e:
        log.exception("pnl_snapshot job failed: %s", e)


def job_daily_summary() -> None:
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        with get_conn(readonly=True) as conn:
            row = conn.execute(
                "SELECT "
                "  COUNT(*) total, "
                "  SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) wins, "
                "  SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) losses, "
                "  COALESCE(SUM(CASE WHEN status IN ('won','lost') THEN pnl_usd END), 0) pnl "
                "FROM trades WHERE substr(timestamp, 1, 10) = ?",
                (today,),
            ).fetchone()
            cap_row = conn.execute(
                "SELECT capital_usd FROM pnl_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        capital = float(cap_row["capital_usd"]) if cap_row else STARTING_CAPITAL_USD
        telegram_alerts.notify_daily_summary(
            capital_usd=capital,
            day_pnl_usd=float(row["pnl"] or 0),
            trades_today=int(row["total"] or 0),
            wins=int(row["wins"] or 0),
            losses=int(row["losses"] or 0),
        )
    except Exception as e:
        log.exception("daily_summary job failed: %s", e)


def main() -> int:
    _setup_logging()
    log.info("OmniAlpha starting — PAPER_MODE=%s", PAPER_MODE)

    if not PAPER_MODE:
        log.error("PAPER_MODE is off; refusing to start without explicit approval. "
                  "Set PAPER_MODE=true in omnialpha/.env.")
        telegram_alerts.notify_error(
            "startup", RuntimeError("PAPER_MODE off — refused to start")
        )
        return 1

    init_db()
    log.info("DB ready: %s", "")

    sched = BlockingScheduler(timezone="America/New_York")
    sched.add_job(job_settle, "interval", seconds=30, id="settle",
                  misfire_grace_time=300)
    sched.add_job(job_pnl_snapshot, "interval", seconds=60, id="pnl_snap",
                  misfire_grace_time=300)
    sched.add_job(job_daily_summary, "cron", hour=7, minute=0,
                  id="daily_summary", misfire_grace_time=3600)

    telegram_alerts.notify_startup()
    log.info("Scheduler started")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopping")
        sched.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
