"""OmniAlpha config — paper mode flag, capital, risk caps, sector enables.

Single source of truth for runtime knobs. Read from .env where appropriate;
fall back to defaults that match the master CLAUDE.md hard caps.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ─── Paper-mode hard stop ─────────────────────────────────────────────
# OmniAlpha refuses live orders unless PAPER_MODE is exactly "true".
# Setting to anything else (false, off, 0, "") is one of Zach's 3 hard stops
# and requires explicit approval per master CLAUDE.md.
PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").strip().lower() == "true"

# ─── Kalshi credentials ───────────────────────────────────────────────
KALSHI_API_KEY_ID: str | None = os.getenv("KALSHI_API_KEY_ID") or None
KALSHI_PRIVATE_KEY_PATH: Path | None = (
    Path(os.getenv("KALSHI_PRIVATE_KEY_PATH")) if os.getenv("KALSHI_PRIVATE_KEY_PATH")
    else None
)

# ─── Anthropic (for any LLM-driven strategy) ──────────────────────────
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY") or None

# ─── Telegram ─────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN") or None
TELEGRAM_CHAT_ID: str | None = os.getenv("TELEGRAM_CHAT_ID") or None

# ─── Risk caps (compound — % of live capital, not fixed $) ────────────
# Caps are derived at gate-eval time from context.capital_usd × pct, with
# a hard USD floor so a deep drawdown can't degenerate the cap to pennies.
# As the account grows, caps grow with it (compounding); as it shrinks,
# caps shrink (auto-deleveraging).
PER_TRADE_MAX_RISK_PCT: float = float(os.getenv("PER_TRADE_MAX_RISK_PCT", "0.05"))   # 5% of live capital
DAILY_MAX_LOSS_PCT: float = float(os.getenv("DAILY_MAX_LOSS_PCT", "0.10"))           # 10% of live capital
WEEKLY_MAX_LOSS_PCT: float = float(os.getenv("WEEKLY_MAX_LOSS_PCT", "0.20"))         # 20% of live capital

# Hard USD floors — caps never drop below these regardless of how small
# the account gets. Keeps the bot able to place a meaningful trade even
# during deep drawdown / re-warmup.
PER_TRADE_FLOOR_USD: float = float(os.getenv("PER_TRADE_FLOOR_USD", "5"))
DAILY_FLOOR_USD: float = float(os.getenv("DAILY_FLOOR_USD", "10"))
WEEKLY_FLOOR_USD: float = float(os.getenv("WEEKLY_FLOOR_USD", "20"))

MAX_CONCURRENT_POSITIONS: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "8"))
MAX_TRADES_PER_SECTOR_PER_DAY: int = int(os.getenv("MAX_TRADES_PER_SECTOR_PER_DAY", "20"))


def per_trade_cap_usd(capital_usd: float) -> float:
    """Live per-trade $ cap = max(floor, capital × pct)."""
    return max(PER_TRADE_FLOOR_USD, capital_usd * PER_TRADE_MAX_RISK_PCT)


def daily_loss_cap_usd(capital_usd: float) -> float:
    """Live daily-loss $ cap = max(floor, capital × pct)."""
    return max(DAILY_FLOOR_USD, capital_usd * DAILY_MAX_LOSS_PCT)


def weekly_loss_cap_usd(capital_usd: float) -> float:
    """Live weekly-loss $ cap = max(floor, capital × pct)."""
    return max(WEEKLY_FLOOR_USD, capital_usd * WEEKLY_MAX_LOSS_PCT)

# ─── Sector enables ───────────────────────────────────────────────────
# Opt-in. Add a sector here only when its strategy module exists AND has
# been paper-validated.
#
# crypto: backtest 89.4% WR, +20.5% return on $100 over 7 days,
#         $3.43 max DD, Sharpe 0.424, PF 2.91 (verified 2026-05-02 with
#         tightened bands + 0.05 Kelly + 3-min entry window).
#
# Future values: "sports" (KXNBA*, KXMLB*, KXNHL*), "politics", "economics".
ENABLED_SECTORS: list[str] = ["crypto"]

# ─── Kalshi API endpoints ─────────────────────────────────────────────
# /historical/* are PUBLIC and unauthenticated.
# Live /markets, /portfolio, /orders require RSA-signed requests.
KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# ─── Paths ────────────────────────────────────────────────────────────
DB_PATH = BASE_DIR / "state" / "omnialpha.db"
LOG_DIR = BASE_DIR / "logs"
BACKTEST_DATA_DIR = BASE_DIR / "data" / "raw"

# ─── Cross-bot risk coupling ──────────────────────────────────────────
# Read by all bots before sizing. Daily aggregate loss across WA + ORB +
# OmniAlpha gates new entries when the account-wide cap is breached.
SHARED_RISK_STATE = Path("C:/ZachAI/data/risk_state.json")

# ─── Capital allocation ───────────────────────────────────────────────
# OmniAlpha starts with a small dedicated bankroll. Separate from WA's
# $295 capital. Tune as paper-mode results justify.
STARTING_CAPITAL_USD: float = float(os.getenv("STARTING_CAPITAL_USD", "100"))


def is_paper_mode() -> bool:
    """Check enforced — call before any order placement."""
    return PAPER_MODE


def assert_paper_mode() -> None:
    """Raise if paper mode is disabled. Use as a guard in any code path
    that could hit the live order endpoint."""
    if not PAPER_MODE:
        raise RuntimeError(
            "PAPER_MODE is not enabled. OmniAlpha refuses to place live "
            "orders without explicit approval. Set PAPER_MODE=true in "
            "omnialpha/.env to proceed in paper mode."
        )
