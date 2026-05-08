"""ICTBot config — paper mode, capital, risk caps, killzones, symbol.

Single source of truth for runtime knobs. Read from .env where appropriate;
fall back to defaults that match CLAUDE.md hard caps.
"""
from __future__ import annotations

import os
from datetime import time as dt_time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

TIMEZONE = "America/New_York"

# ─── Paper-mode hard stop ─────────────────────────────────────────────
PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").strip().lower() == "true"

# Phase-1 default: detect setups but do not place orders
SCAN_ONLY: bool = os.getenv("SCAN_ONLY", "true").strip().lower() == "true"

# ─── Symbol / chart ───────────────────────────────────────────────────
ICT_SYMBOL: str = os.getenv("ICT_SYMBOL", "MES1!")
ICT_TIMEFRAME: str = os.getenv("ICT_TIMEFRAME", "5")  # 5-minute primary
HTF_TIMEFRAME: str = os.getenv("HTF_TIMEFRAME", "60")  # 1H bias
MULTIPLIER: float = float(os.getenv("MES_MULTIPLIER", "1.25"))  # $/pt for MES

# ─── CDP (TradingView Desktop, shared with ORB) ───────────────────────
# Updated 2026-05-07: ICTBot shares ORB's TV Desktop CDP session on :9222.
# Phase-1 SCAN_ONLY → only READ via this CDP (chart_get_state, health-check);
# data feeds come from Yahoo so chart-state contention is minimal.
# Phase-2 order placement will require pane/tab focus serialization with ORB.
CDP_HOST: str = os.getenv("CDP_HOST", "127.0.0.1")
CDP_PORT: int = int(os.getenv("CDP_PORT", "9222"))

# ─── Telegram (separate from Jarvis bridge) ───────────────────────────
TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN") or None
TELEGRAM_CHAT_ID: str | None = os.getenv("TELEGRAM_CHAT_ID") or None
TELEGRAM_PREFIX: str = "[ICTBot]"

# ─── Anthropic (optional) ─────────────────────────────────────────────
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY") or None

# ─── Risk caps ────────────────────────────────────────────────────────
MAX_RISK_PER_TRADE_DOLLARS: float = float(os.getenv("MAX_RISK_PER_TRADE_DOLLARS", "150"))
DAILY_LOSS_LIMIT_DOLLARS: float = float(os.getenv("DAILY_LOSS_LIMIT_DOLLARS", "250"))
WEEKLY_LOSS_LIMIT_DOLLARS: float = float(os.getenv("WEEKLY_LOSS_LIMIT_DOLLARS", "500"))
MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
MAX_TRADES_PER_SESSION: int = int(os.getenv("MAX_TRADES_PER_SESSION", "3"))
VIX_HARD_BLOCK: float = float(os.getenv("VIX_HARD_BLOCK", "30"))

# ─── Hours (ET) ───────────────────────────────────────────────────────
def _parse_hhmm(s: str, default_h: int, default_m: int) -> dt_time:
    try:
        h, m = s.split(":")
        return dt_time(int(h), int(m))
    except Exception:
        return dt_time(default_h, default_m)

NY_AM_START: dt_time = _parse_hhmm(os.getenv("NY_AM_START", "08:30"), 8, 30)
NY_AM_END: dt_time = _parse_hhmm(os.getenv("NY_AM_END", "11:00"), 11, 0)
NY_PM_START: dt_time = _parse_hhmm(os.getenv("NY_PM_START", "13:30"), 13, 30)
NY_PM_END: dt_time = _parse_hhmm(os.getenv("NY_PM_END", "16:00"), 16, 0)
HARD_CLOSE: dt_time = _parse_hhmm(os.getenv("HARD_CLOSE", "14:55"), 14, 55)

# ─── Dashboard ────────────────────────────────────────────────────────
DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "3002"))

# ─── Logging ──────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ─── Strategy params (NY AM FVG) ──────────────────────────────────────
FVG_MIN_GAP_POINTS: float = float(os.getenv("FVG_MIN_GAP_POINTS", "3.0"))   # ES pts
DISPLACEMENT_MIN_POINTS: float = float(os.getenv("DISPLACEMENT_MIN_POINTS", "5.0"))
STOP_BUFFER_POINTS: float = float(os.getenv("STOP_BUFFER_POINTS", "3.0"))
DEFAULT_RR_TARGET: float = float(os.getenv("DEFAULT_RR_TARGET", "2.0"))

# ─── Cross-bot risk halt path ─────────────────────────────────────────
RISK_STATE_PATH = Path(os.getenv("RISK_STATE_PATH", r"C:\ZachAI\data\risk_state.json"))

# ─── Cross-bot ORB read-only state (informational) ────────────────────
ORB_STATE_DIR = Path(os.getenv("ORB_STATE_DIR", r"C:\ZachAI\trading\state"))

# ─── 2026 high-impact calendar (mirrors ORB) ──────────────────────────
HIGH_IMPACT_DAYS_2026 = {
    "CPI":  ["2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10", "2026-05-12",
             "2026-06-10", "2026-07-14", "2026-08-12", "2026-09-11", "2026-10-14",
             "2026-11-10", "2026-12-10"],
    "NFP":  ["2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03", "2026-05-08",
             "2026-06-05", "2026-07-02", "2026-08-07", "2026-09-04", "2026-10-02",
             "2026-11-06", "2026-12-04"],
    "FOMC": ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
             "2026-09-16", "2026-10-28", "2026-12-09"],
}


def is_high_impact_today(date_iso: str) -> tuple[bool, str | None]:
    """Return (True, event_name) if `date_iso` is a high-impact day."""
    for event, dates in HIGH_IMPACT_DAYS_2026.items():
        if date_iso in dates:
            return True, event
    return False, None
