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
DEFAULT_SYMBOL = "MNQ1!"
MULTIPLIER = 2  # $2/pt for MNQ
STARTING_CAPITAL = 5000  # Demo account balance

# ORB Settings (research-calibrated)
ORB_MINUTES = 15  # 15-min ORB default (Finding 4: fewer false breakouts)
ORB_START_HOUR, ORB_START_MINUTE = 9, 30
SESSION_END_HOUR, SESSION_END_MINUTE = 11, 0
HARD_CLOSE_HOUR, HARD_CLOSE_MINUTE = 15, 0  # 3 PM ET close everything
MAX_HOLD_MINUTES = 120  # 2-hour time exit (Finding 11)

# ORB Range Filter (Finding 10: 30-60% of 14-day ATR)
ORB_ATR_MIN_PCT = 0.30
ORB_ATR_MAX_PCT = 0.60
ATR_LOOKBACK_DAYS = 14

# Scoring Thresholds (adjusted +1 to account for 2pt MNQ slippage erosion)
SCORE_FULL_SIZE = 8
SCORE_HALF_SIZE = 6
MAX_TRADES_PER_SESSION = 3

# Stop/Target (Finding 2: extension-based, 7x Sharpe improvement)
STOP_EXTENSION_MULT = 1.25  # Stop at 1.25x ORB range beyond opposite boundary
TARGET_1_MULT = 0.50  # Close 50% at 0.5x ORB range
TARGET_2_MULT = 1.50  # Trail remainder to 1.5x ORB range

# Slippage (Finding 9: paper-to-live gap)
SLIPPAGE_PTS = 2  # Deduct 2 pts MNQ ($4) from every trade P&L

# Risk Management (Finding 12: circuit breaker)
MAX_CONSECUTIVE_LOSSES = 3  # Pause for rest of day
WEEKLY_LOSS_LIMIT_PCT = 0.07  # 7% of capital = pause for manual review
ROLLING_WR_ALERT_THRESHOLD = 0.40  # Alert if 20-trade WR drops below 40%
ROLLING_WR_ALERT_WEEKS = 2  # For 2 consecutive weeks

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
SWEEP_WINDOW = ((9, 0), (11, 0))
COMBINER_WINDOW = ((9, 30), (11, 0))
SENTINEL_POLL_WINDOW = ((9, 30), (11, 0))

# Sentinel Keywords
TRUTH_HIGH_IMPACT_KEYWORDS = [
    "tariff", "trade", "china", "ban", "sanctions", "tax", "fed",
    "interest rate", "market", "executive order", "emergency",
    "rates", "treasury", "stock", "crash", "recession",
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
