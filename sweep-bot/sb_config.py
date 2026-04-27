"""Sweep-Bot config — standalone liquidity sweep trader.

Runs as a separate process alongside the ORB bot. Reads
`trading/state/sweep.json` (one writer, multiple readers), scores
SWEEP_CONFIRMED events, and places its own paper orders through the
existing tv_trader path.
"""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
STATE_FILE = STATE_DIR / "sweep_bot.json"
LOG_FILE = LOG_DIR / "sweep_bot.log"

# Session — wider than ORB's 9:30-11:00 because sweeps fire all day.
SESSION_START_HOUR, SESSION_START_MINUTE = 9, 30
SESSION_END_HOUR, SESSION_END_MINUTE = 14, 30

# Budget — independent from ORB's 3 trades/day.
MAX_SWEEP_TRADES = 3

# Signal qualification
MIN_WICK_POINTS = 5.0        # Filter out micro-sweeps below this wick size.
MIN_POOL_BARS = 2            # Pool must have ≥ N prior touches.

# Scoring
SCORE_FLOOR = 5              # Minimum score to take a trade (same floor as ORB HALF).
SCORE_FULL_SIZE = 8          # ≥ this → FULL size; 5-7 → HALF.
SCORE_HALF_SIZE = 5

# Stop/target geometry
STOP_ATR_BUFFER = 0.25       # Stop = swept_level ± (wick + 0.25 * ATR_14).
TARGET_1_RR = 1.0
TARGET_2_RR = 2.0

# Poll interval (seconds). Matches sweep.py's own cadence.
POLL_INTERVAL_SEC = 15

# Path to ORB's sweep.json state file.
TRADING_DIR = Path("C:/ZachAI/trading")
SWEEP_STATE_FILE = TRADING_DIR / "state" / "sweep.json"
