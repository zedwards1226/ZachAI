"""Configuration for ORB Multi-Agent Trading System."""
import os
from datetime import datetime as _datetime
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
JOURNAL_DB = BASE_DIR / "journal.db"

# Telegram — ORB Alerts bot (dedicated bot for all trading notifications)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# TradingView CDP
CDP_HOST = "localhost"
CDP_PORT = 9222

# Instrument
DEFAULT_SYMBOL = "CME_MINI:MNQ1!"
MULTIPLIER = 2  # $2/pt for MNQ
STARTING_CAPITAL = 5000  # Demo account balance

# ORB Settings (research-calibrated)
ORB_MINUTES = 15  # 15-min ORB default (Finding 4: fewer false breakouts)
ORB_START_HOUR, ORB_START_MINUTE = 9, 30
SESSION_END_HOUR, SESSION_END_MINUTE = 14, 0
HARD_CLOSE_HOUR, HARD_CLOSE_MINUTE = 15, 0  # 3 PM ET close everything
MAX_HOLD_MINUTES = 120  # 2-hour time exit (Finding 11)

# ORB Range Filter (Finding 10: 30-60% of 14-day ATR)
ORB_ATR_MIN_PCT = 0.30
ORB_ATR_MAX_PCT = 0.60
ATR_LOOKBACK_DAYS = 14

# Scoring Thresholds
# Lowered HALF from 6 → 5 to compensate for direction-aware / strength-tiered
# AT_LEVEL filter (structure.py). The old filter over-penalized any nearby
# level regardless of trade direction, dragging average scores down by ~1-2pts.
SCORE_FULL_SIZE = 8
SCORE_HALF_SIZE = 5
MAX_TRADES_PER_SESSION = 2  # Strict ORB: first break + optional second-break (Zarattini)

# Stop/Target (Finding 2: extension-based, 7x Sharpe improvement)
STOP_EXTENSION_MULT = 1.25  # Stop at 1.25x ORB range beyond opposite boundary
TARGET_1_MULT = 0.50  # Close 50% at 0.5x ORB range
TARGET_2_MULT = 1.50  # Trail remainder to 1.5x ORB range

# Slippage (Finding 9: paper-to-live gap)
SLIPPAGE_PTS = 2  # Deduct 2 pts MNQ ($4) from every trade P&L

# Risk Management (Finding 12: circuit breaker)
MAX_CONSECUTIVE_LOSSES = 3  # Pause for rest of day
WEEKLY_LOSS_LIMIT_PCT = 0.07  # 7% of capital — enforced via combiner.poll()
ROLLING_WR_ALERT_THRESHOLD = 0.40  # Alert if 20-trade WR drops below 40%
ROLLING_WR_ALERT_WEEKS = 2  # For 2 consecutive weeks

# Per-trade and per-day risk caps (account size aware — $5,000 paper baseline)
MAX_RISK_PER_TRADE_DOLLARS = 350   # 7% — bumped 2026-04-30 from $250. Today's 101pt ORB needed $308-341 risk; $250 was blocking most NQ ORBs in the wider 100-150pt regime.
DAILY_LOSS_LIMIT_DOLLARS = 200     # 4% — bumped from $150 to keep ratio with per-trade cap. One losing trade can't blow the day twice.

# Mid-trade intervention thresholds (used by tv_trader.monitor_trades)
VIX_INTERVENTION_PCT = 0.20        # Close trade if VIX rises 20%+ from trade-open VIX

# Trailing stop after T1 hit. virtual_stop = price - (TRAIL_DISTANCE_RATIO × ORB range)
# 0.5 × ORB matches the T1 distance — gives trade room equal to the breakeven trigger band
TRAIL_DISTANCE_RATIO = 0.5

# Position-state heuristic: if available funds drop below this fraction of STARTING_CAPITAL,
# we know a position is open (margin used). Otherwise we assume flat.
POSITION_OPEN_FUNDS_THRESHOLD = 0.90  # Below 90% of starting capital = position open

# VIX Regime (Finding 7)
VIX_HARD_BLOCK = 30  # No trading above VIX 30
VIX_SWEET_SPOT_LOW = 15
VIX_SWEET_SPOT_HIGH = 25

# RVOL (Finding 6)
RVOL_THRESHOLD = 1.5

# Agent Windows (ET hours)
STRUCTURE_TIME = (8, 45)
MEMORY_TIME = (18, 0)
BRIEFING_TIME = (8, 50)
SENTINEL_INITIAL_TIME = (8, 0)
COMBINER_WINDOW = ((9, 30), (14, 0))
SENTINEL_POLL_WINDOW = ((9, 30), (14, 0))

# Sentinel Keywords
TRUTH_HIGH_IMPACT_KEYWORDS = [
    "fomc", "fed", "interest rate", "rates", "treasury",
]

# Timezone
TIMEZONE = "America/New_York"

# US Market Holidays (CME: MNQ closed these days)
MARKET_HOLIDAYS = {
    # 2026
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
    # 2027 — add when CME publishes schedule
}

# Half days — market closes at 1:00 PM ET instead of 3:00 PM
HALF_DAYS = {
    "2026-11-27",  # Day after Thanksgiving
    "2026-12-24",  # Christmas Eve
}
HALF_DAY_CLOSE_HOUR = 13
HALF_DAY_CLOSE_MINUTE = 0


def is_trading_day(dt=None) -> bool:
    """Return True if dt is a regular market day (not weekend, not holiday)."""
    import pytz
    if dt is None:
        dt = _datetime.now(pytz.timezone(TIMEZONE))
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return dt.strftime("%Y-%m-%d") not in MARKET_HOLIDAYS


def get_hard_close_time(dt=None) -> tuple:
    """Return (hour, minute) for today's hard close. 1 PM on half days, 3 PM otherwise."""
    import pytz
    if dt is None:
        dt = _datetime.now(pytz.timezone(TIMEZONE))
    if dt.strftime("%Y-%m-%d") in HALF_DAYS:
        return (HALF_DAY_CLOSE_HOUR, HALF_DAY_CLOSE_MINUTE)
    return (HARD_CLOSE_HOUR, HARD_CLOSE_MINUTE)


# ─── Learned config overrides (applied at import time) ─────────────
# The ORB learning agent may propose threshold changes. Approved ones
# land in state/learned_config.json, which this block overlays onto the
# defaults above. Other modules that do `from config import X` pick up
# the overridden value automatically.
#
# Manual edits to state/learned_config.json are detected by the learning
# agent on its next run and logged to agent_journal with source='manual'.
LEARNED_OVERRIDES: dict = {}
try:
    from agents import config_loader as _config_loader
    _overrides = _config_loader.load_overrides()
    for _k, _v in _overrides.items():
        globals()[_k] = _v
    LEARNED_OVERRIDES = dict(_overrides)
except Exception:  # noqa: BLE001 — overrides must never break config import
    import logging as _logging
    _logging.getLogger(__name__).exception(
        "Failed to apply learned_config overrides; using defaults"
    )
