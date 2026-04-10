"""
TradingAgents configuration — all thresholds, limits, and toggles.
Env vars override defaults via .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Anthropic Claude API ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_MAX_TOKENS_PER_CALL = 300  # hard cap for Sentinel/Context agents

# ── Server ────────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8766"))

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH = Path(__file__).parent / "db" / "tradingagents.db"

# ── Contract multipliers (dollar value per 1-point move per contract) ─────────
MULTIPLIERS = {
    "NQ1!":  20,
    "MNQ1!":  2,
    "ES1!":  50,
    "MES1!":  5,
    "QQQ":    1,
    "SPY":    1,
}

# ── Overseer guardrail thresholds ─────────────────────────────────────────────
MAX_CONTRACTS = int(os.getenv("MAX_CONTRACTS", "4"))          # max contracts per trade
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "10"))   # max trades per day
MAX_TRADES_PER_HOUR = int(os.getenv("MAX_TRADES_PER_HOUR", "3"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "500"))    # dollars
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

# ── Trade session window (Eastern Time) ──────────────────────────────────────
TIMEZONE = "America/New_York"
SESSION_START_HOUR = 9    # 9:30 AM ET (we check >= 9)
SESSION_START_MINUTE = 30
SESSION_END_HOUR = 16     # 4:00 PM ET
SESSION_END_MINUTE = 0

# ── Analyst EOD schedule ─────────────────────────────────────────────────────
ANALYST_EOD_HOUR = 16     # 4:15 PM ET
ANALYST_EOD_MINUTE = 15
