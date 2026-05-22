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
MAX_TRADES_PER_SESSION = 999999  # 2026-05-20: ALL LIMITS DISABLED at Zach's explicit request (paper mode). Was 1/day.

# Factor weight defaults — these can be overridden by state/learned_config.json
# (see LEARNABLE_KNOBS in agents/config_loader.py). Added 2026-05-11 after the
# 22-trade audit revealed:
#   - second_break setup accounts for +$475 of total profit but is hard-coded
#     at +2; raising to +3 or +4 would proportionally boost its score weighting.
#   - orb_candle_direction is a negative predictor at +3: scored positive in 10
#     trades, 70% WR but net -$198. Setting to 0 effectively drops the factor.
# Defaults preserve historical behavior; tune via JSON edit or learning agent.
WEIGHT_SECOND_BREAK = 2
WEIGHT_ORB_CANDLE_DIRECTION = 3

# Stop/Target (2026-05-19 rewrite — Zarattini/Aziz SSRN 4416622, Concretum)
# Old setting STOP_EXTENSION_MULT=1.25 placed stop at 0.25x range BEYOND the
# opposite OR boundary, giving stop≈1.25x range vs TP=1.5x range = R:R 1.2:1.
# Foundational ORB literature uses stop AT the opposite OR edge (1.0R) with
# TP up to 10R. We move TP to 2.0x range for a real 2:1 R:R baseline.
# NOTE: NO MIN_RR refuse-trade gate. Bot trades the first valid breakout
# regardless of computed R:R — learning needs trades to happen.
STOP_EXTENSION_MULT = 1.0  # Stop AT the OR opposite edge (no beyond-buffer)
TARGET_1_MULT = 0.50  # BE trigger + 50% scale (Phase 1.5)
TARGET_2_MULT = 2.0   # Runner TP — 2.0x ORB range from entry

# Slippage (Finding 9: paper-to-live gap)
SLIPPAGE_PTS = 2  # Deduct 2 pts MNQ ($4) from every trade P&L

# Risk Management (Finding 12: circuit breaker)
# 2026-05-20: ALL RISK LIMITS DISABLED at Zach's explicit request (paper mode).
# Set to non-binding values so combiner.poll()/daily_pnl_guard never pause the
# bot. Revert by restoring the originals (in comments) if going back to capped.
MAX_CONSECUTIVE_LOSSES = 999999  # was 3 (pause for rest of day)
WEEKLY_LOSS_LIMIT_PCT = 1000000.0  # was 0.07 (7% of capital)
ROLLING_WR_ALERT_THRESHOLD = 0.40  # Alert if 20-trade WR drops below 40%
ROLLING_WR_ALERT_WEEKS = 2  # For 2 consecutive weeks

# Per-trade and per-day risk caps (account size aware — $5,000 paper baseline)
MAX_RISK_PER_TRADE_DOLLARS = 1000000000   # 2026-05-20 DISABLED (was 350)
DAILY_LOSS_LIMIT_DOLLARS = 1000000000     # 2026-05-20 DISABLED (was 200)

# ── Phase 0.5 profit protection (2026-05-19) ────────────────────────────
# Zach lost $700 today after being up $200 — bot had no daily-lock and the
# stall logic was too loose to catch the give-back. These knobs add:
#   - Daily +$200 target: stop trading once realized + unrealized P&L hits target
#   - Daily -$200 stop: overlap with DAILY_LOSS_LIMIT_DOLLARS — both checked
#   - MFE 50% giveback exit: after +1R captured, if runner gives back 50% of MFE peak, market close
DAILY_PROFIT_TARGET_DOLLARS = 1000000000.0  # 2026-05-20 DISABLED (was 200.0) — let winners run
MFE_GIVEBACK_RATIO = 0.5             # Exit runner if price retraces 50% from MFE peak
MFE_GIVEBACK_ACTIVATE_R = 1.0        # Only active once trade has captured at least +1R

# HARD per-trade ceiling — uncondtionally enforced inside place_bracket_order
# regardless of RISK_CAP_ENABLED. Set 2x the soft cap. Audit 2026-05-17 T4:
# with RISK_CAP_ENABLED=False, a 200-pt ORB at 1.25x stop extension = $500
# actual exposure, which was uncapped. This is the absolute floor — any
# trade that would risk more than this gets refused at the broker layer,
# not just the signal layer. Cannot be toggled off via env or config flag.
HARD_PER_TRADE_RISK_CEILING_DOLLARS = 1000000000  # 2026-05-20 DISABLED (was 700)

# Per-trade $ risk gate (combiner.py). When False, the gate is skipped and
# wide-OR signals fire regardless of stop distance. Set False on 2026-05-04
# at Zach's call after the cap was blocking most signals in the 200+ pt
# volatility regime. Audit 2026-05-17 T4 (corrected understanding): the
# bracket order's stop-loss does NOT cap actual losses at
# MAX_RISK_PER_TRADE_DOLLARS — actual stop distance depends on ORB range.
# That misunderstanding lived in the comment for 13 days. The HARD ceiling
# above is the real ceiling now; this flag controls the soft signal-volume veto.
RISK_CAP_ENABLED = False

# ── Phase 2 (2026-05-22): real TV trailing stop ───────────────────────────
# When True, the BE-move and trail PUSH the real TradingView bracket stop via
# the account-manager "Modify Order" panel (proven recipe), so the stop is
# server-side and protected even if the 30s monitor misses a fast wick.
# ADDITIVE + best-effort: the existing virtual-stop logic stays as a backup,
# and TV's original bracket SL is always there — so if a modify fails, behavior
# degrades to exactly the pre-Phase-2 path. Flip True to enable.
# OFF until the live auto-finder is hardened + verified at the open (2026-05-22):
# the manual recipe is proven, but the "Modify Order" control renders on row
# ACTIVATION (not just hover), so modify_stop_on_tv needs live tuning against a
# real position before we trust it. Flip True once verified at 9:30 ET.
USE_REAL_TV_STOP = False
# Only push to TV when the stop has moved at least this many points since the
# last push — limits panel churn from 30s trail steps.
TV_STOP_MIN_STEP = 5.0

# Mid-trade intervention thresholds (used by tv_trader.monitor_trades)
VIX_INTERVENTION_PCT = 0.20        # Close trade if VIX rises 20%+ from trade-open VIX

# Trailing stop after T1 hit. virtual_stop = price - (TRAIL_DISTANCE_RATIO × ORB range)
# 0.5 × ORB matches the T1 distance — gives trade room equal to the breakeven trigger band
TRAIL_DISTANCE_RATIO = 0.5

# Pre-T1 management (added 2026-05-11 per audit Finding D):
#   Today's trade #23 reached 80% of T1 path then rolled over and time-exited
#   at +$32 instead of capturing the high. These knobs let the bot react
#   before T1 is hit.
PRE_T1_BE_PROGRESS = 0.80    # If MFE reaches 80% of T1 distance from entry
PRE_T1_BE_PULLBACK = 0.30    # And price pulls back 30% from MFE → snap stop to BE
STALL_MIN_MFE_POINTS = 20    # Stall detection only fires if MFE >= 20pts profit
STALL_NO_PROGRESS_MIN = 30   # If MFE hasn't advanced in 30 min, tighten stop
STALL_LOCK_PCT = 0.50        # Lock 50% of MFE-from-entry when stall fires

# VIX Regime (Finding 7)
VIX_HARD_BLOCK = 100000  # 2026-05-20 DISABLED (was 30)
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
