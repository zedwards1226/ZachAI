"""
Overseer Agent — Rule-based guardrails. Zero Claude tokens.
The ONLY blocking agent in the pipeline. Must return fast (<10ms).

Checks:
1. Position size (max contracts)
2. Daily trade count limit
3. Hourly trade frequency cap
4. Daily loss limit
5. Consecutive loss streak
6. Trade session window (NY session hours)
7. Duplicate trade prevention (no double entries)

Returns: AgentVerdict (PASS / BLOCK / REDUCE)
"""
import logging
from datetime import datetime

import pytz

import config
import database as db
from models import Signal, AgentVerdict, Verdict

log = logging.getLogger("overseer")


def evaluate(signal: Signal) -> AgentVerdict:
    """Run all guardrail checks. Returns on first BLOCK, or PASS if all clear."""
    reasons = []

    # Run all checks
    checks = [
        _check_session_window(),
        _check_position_size(signal.qty),
        _check_daily_trades(),
        _check_hourly_trades(),
        _check_daily_loss(),
        _check_consecutive_losses(),
        _check_duplicate_entry(signal.symbol),
    ]

    for passed, reason in checks:
        if not passed:
            reasons.append(reason)

    if reasons:
        combined = "; ".join(reasons)
        log.info("BLOCK: %s", combined)
        return AgentVerdict(
            agent="overseer",
            verdict=Verdict.BLOCK,
            reasoning=combined,
        )

    log.info("PASS: all checks clear for %s %s", signal.action, signal.symbol)
    return AgentVerdict(
        agent="overseer",
        verdict=Verdict.PASS,
        reasoning="All guardrail checks passed",
    )


# ── Individual checks ────────────────────────────────────────────────────────

def _check_session_window() -> tuple[bool, str]:
    """Only allow trades during NY session hours."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    start = now.replace(hour=config.SESSION_START_HOUR, minute=config.SESSION_START_MINUTE, second=0)
    end = now.replace(hour=config.SESSION_END_HOUR, minute=config.SESSION_END_MINUTE, second=0)

    if start <= now < end:
        return True, "ok"
    return False, f"Outside session window ({config.SESSION_START_HOUR}:{config.SESSION_START_MINUTE:02d}-{config.SESSION_END_HOUR}:{config.SESSION_END_MINUTE:02d} ET, now {now.strftime('%I:%M%p')})"


def _check_position_size(qty: int) -> tuple[bool, str]:
    """Max contracts per trade."""
    if qty > config.MAX_CONTRACTS:
        return False, f"Position size {qty} exceeds max {config.MAX_CONTRACTS}"
    return True, "ok"


def _check_daily_trades() -> tuple[bool, str]:
    """Max trades per day."""
    state = db.get_guardrail_state()
    if state["daily_trades"] >= config.MAX_DAILY_TRADES:
        return False, f"Daily trade limit reached ({config.MAX_DAILY_TRADES})"
    return True, "ok"


def _check_hourly_trades() -> tuple[bool, str]:
    """Max trades per rolling hour."""
    trades_today = db.get_trades_today()
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    one_hour_ago = now.timestamp() - 3600

    recent = 0
    for t in trades_today:
        try:
            opened = datetime.fromisoformat(t["opened_at"]).timestamp()
            if opened >= one_hour_ago:
                recent += 1
        except (ValueError, TypeError):
            continue

    if recent >= config.MAX_TRADES_PER_HOUR:
        return False, f"Hourly trade limit reached ({config.MAX_TRADES_PER_HOUR}/hr)"
    return True, "ok"


def _check_daily_loss() -> tuple[bool, str]:
    """Daily loss cap."""
    state = db.get_guardrail_state()
    if state["daily_pnl"] <= -config.MAX_DAILY_LOSS:
        return False, f"Daily loss limit hit (${-state['daily_pnl']:.2f} / ${config.MAX_DAILY_LOSS})"
    return True, "ok"


def _check_consecutive_losses() -> tuple[bool, str]:
    """Consecutive loss streak limit."""
    state = db.get_guardrail_state()
    if state["consecutive_losses"] >= config.MAX_CONSECUTIVE_LOSSES:
        return False, f"Consecutive loss limit ({config.MAX_CONSECUTIVE_LOSSES}) — cooling off"
    return True, "ok"


def _check_duplicate_entry(symbol: str) -> tuple[bool, str]:
    """Prevent opening a second position on same symbol."""
    open_trades = db.get_open_trades(symbol=symbol)
    if open_trades:
        return False, f"Already have open position on {symbol}"
    return True, "ok"
