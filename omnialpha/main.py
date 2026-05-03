"""OmniAlpha main loop — APScheduler-driven, paper-mode by default.

Jobs (all paper-safe):
  - strategy_poll             every 60s — scan live KXBTC15M markets via
                                 public /markets endpoint, run enabled
                                 strategies, place paper orders for any
                                 approved entries
  - settle_open_trades        every 30s — settle any paper trades whose
                                 underlying markets resolved
  - write_pnl_snapshot        every 60s — periodic equity curve point +
                                 update our section in cross-bot risk_state.json
  - daily_summary             07:00 ET — Telegram summary

Live-mode order placement is locked behind two flags in
order_placer.py — paper mode is the only path that can actually fire.
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
from bots.live_scanner import scan_and_trade
from bots.risk_engine import update_my_section
from bots.trade_monitor import settle_resolved_trades, write_pnl_snapshot
from config import (
    ENABLED_SECTORS,
    LOG_DIR,
    PAPER_MODE,
    STARTING_CAPITAL_USD,
)
from data_layer.database import get_conn, init_db
from strategies.crypto_midband import CryptoMidBandStrategy

# Strategy registry — one entry per (sector, series). Each strategy is
# tuned to that series's calibration evidence. Bands are chosen
# conservatively from the well-sampled bins per the sweep on
# 2026-05-02.

_BTC15M_STRATEGY = CryptoMidBandStrategy(
    name="crypto_btc15m_midband",
    no_bands=[(0.20, 0.30, 0.15)],   # n=88, actual ~12%; conservative 15
    yes_bands=[(0.75, 0.85, 0.90)],  # n=94, actual ~96%; conservative 90
)

_ETH15M_STRATEGY = CryptoMidBandStrategy(
    name="crypto_eth15m_midband",
    # ETH15M calibration: NO band 0.15-0.30 (n=294 across, miscal -8 to -15)
    # YES band 0.65-0.85 (n=336 across, miscal +9 to +15)
    no_bands=[(0.15, 0.30, 0.10)],   # actual 4-13%, conservative 10
    yes_bands=[(0.65, 0.85, 0.85)],  # actual 81-93%, conservative 85
)

_BTCD_STRATEGY = CryptoMidBandStrategy(
    name="crypto_btcd_midband",
    # KXBTCD daily Bitcoin range markets — even larger samples, similar pattern.
    # NO band 0.20-0.30 (n=875, actual 3-12%, edge much bigger)
    # YES band 0.70-0.85 (n=1580, actual 95-98%)
    no_bands=[(0.20, 0.30, 0.10)],
    yes_bands=[(0.70, 0.85, 0.92)],
    # Daily markets — entry window can be longer (15 min vs 3 min for 15M).
    max_seconds_to_close=900,
    min_seconds_to_close=60,
)

# Sector → list of (Strategy instance, series_ticker_to_scan).
# Add a sector here once at least one strategy is built and validated.
_STRATEGY_REGISTRY: dict[str, list[tuple]] = {
    "crypto": [
        (_BTC15M_STRATEGY, "KXBTC15M"),
        (_ETH15M_STRATEGY, "KXETH15M"),
        (_BTCD_STRATEGY,  "KXBTCD"),
    ],
}


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


def _current_capital_estimate() -> float:
    """Best estimate of available trading capital. Subtracts open paper
    stakes so Kelly sizing doesn't double-allocate."""
    with get_conn(readonly=True) as conn:
        row = conn.execute(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN status IN ('won','lost') THEN pnl_usd END), 0) realized, "
            "  COALESCE(SUM(CASE WHEN status='open' THEN stake_usd END), 0) open_risk "
            "FROM trades"
        ).fetchone()
    return STARTING_CAPITAL_USD + float(row["realized"] or 0) - float(row["open_risk"] or 0)


def job_strategy_poll() -> None:
    """Scan live markets in every enabled sector, run each enabled
    strategy, place paper orders on approved entries."""
    if not ENABLED_SECTORS:
        return  # bot is dormant by design until a sector is opted in
    capital = _current_capital_estimate()
    for sector in ENABLED_SECTORS:
        for strategy, series_ticker in _STRATEGY_REGISTRY.get(sector, []):
            try:
                result = scan_and_trade(
                    strategy=strategy,
                    series_ticker=series_ticker,
                    capital_usd=capital,
                )
                if result.get("placed", 0) > 0 or result.get("approved", 0) > 0:
                    log.info(
                        "scan %s/%s: %s",
                        sector, series_ticker,
                        ", ".join(f"{k}={v}" for k, v in result.items()),
                    )
            except Exception as e:
                log.exception("strategy_poll %s/%s failed: %s",
                              sector, series_ticker, e)
                telegram_alerts.notify_error(
                    f"strategy_poll {sector}/{series_ticker}", e
                )


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
        # Update cross-bot risk-state with our latest P&L. Pass live capital
        # so the global-halt threshold (2× daily cap) compounds with the bot.
        update_my_section(
            bot="omnialpha",
            daily_pnl_usd=snap["realized_today"],
            weekly_pnl_usd=snap["realized_total"],   # rolling — refine later
            open_positions=snap["open_positions"],
            capital_usd=_current_capital_estimate(),
            last_trade_ts=snap["timestamp"],
        )
    except Exception as e:
        log.exception("pnl_snapshot job failed: %s", e)


def job_daily_summary() -> None:
    try:
        # Match the scheduler's tz so "today" agrees with the cron's 07:00 ET fire
        import pytz
        et = pytz.timezone("America/New_York")
        today = datetime.now(et).strftime("%Y-%m-%d")
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
    from config import DB_PATH, PER_TRADE_MAX_RISK_PCT
    log.info("DB ready: %s", DB_PATH)
    log.info("Enabled sectors: %s", ENABLED_SECTORS or "<none — bot dormant>")

    # Drift detector: per-trade cap must >= every strategy's Kelly fraction
    # or the cap silently clips the natural Kelly stake. Surfaces config
    # drift at startup so we don't discover it weeks later.
    for sector_strats in _STRATEGY_REGISTRY.values():
        for strat, _ in sector_strats:
            kfrac = getattr(strat, "kelly_fraction", None)
            if kfrac is not None and kfrac > PER_TRADE_MAX_RISK_PCT:
                log.warning(
                    "Strategy %s has kelly_fraction=%.3f > PER_TRADE_MAX_RISK_PCT=%.3f "
                    "— per-trade cap will clip every Kelly stake from this strategy. "
                    "Bump PER_TRADE_MAX_RISK_PCT or lower kelly_fraction to align.",
                    strat.name, kfrac, PER_TRADE_MAX_RISK_PCT,
                )

    # max_instances=1 explicit on every job — APScheduler default is 1
    # but stating it prevents accidental concurrent-scan bugs if the
    # executor is ever swapped to a thread/process pool.
    sched = BlockingScheduler(timezone="America/New_York")
    sched.add_job(job_strategy_poll, "interval", seconds=60, id="strategy_poll",
                  max_instances=1, misfire_grace_time=120)
    sched.add_job(job_settle, "interval", seconds=30, id="settle",
                  max_instances=1, misfire_grace_time=300)
    sched.add_job(job_pnl_snapshot, "interval", seconds=60, id="pnl_snap",
                  max_instances=1, misfire_grace_time=300)
    sched.add_job(job_daily_summary, "cron", hour=7, minute=0,
                  id="daily_summary", max_instances=1, misfire_grace_time=3600)

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
