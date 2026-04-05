"""
Trading guardrails — all checks must pass before a trade is placed.
Returns (allowed: bool, reason: str).
"""
import logging
from datetime import datetime
import pytz
from config import (
    MAX_BET, MAX_DAILY_TRADES, MAX_DAILY_LOSS, MAX_CAPITAL_AT_RISK,
    MAX_CONSECUTIVE_LOSSES, MIN_EDGE, TRADE_WINDOW_START_HOUR,
    TRADE_WINDOW_END_HOUR, TIMEZONE, STARTING_CAPITAL
)
from database import get_guardrail_state, get_summary

log = logging.getLogger(__name__)

# In-memory override flag — bypasses trade window for testing
_window_override: bool = False


def set_window_override(enabled: bool) -> None:
    global _window_override
    _window_override = enabled
    log.info("Trade window override: %s", "ENABLED" if enabled else "DISABLED")


def get_window_override() -> bool:
    return _window_override


def _cst_now() -> datetime:
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)


def check_trade_window() -> tuple[bool, str]:
    if _window_override:
        return True, "Trade window override active"
    now = _cst_now()
    if TRADE_WINDOW_START_HOUR <= now.hour < TRADE_WINDOW_END_HOUR:
        return True, "ok"
    return False, (
        f"Outside trade window ({TRADE_WINDOW_START_HOUR}AM-"
        f"{TRADE_WINDOW_END_HOUR}AM CST, currently {now.strftime('%I:%M%p %Z')})"
    )


def check_daily_trades(state: dict) -> tuple[bool, str]:
    if state["daily_trades"] >= MAX_DAILY_TRADES:
        return False, f"Daily trade limit reached ({MAX_DAILY_TRADES})"
    return True, "ok"


def check_daily_loss(state: dict) -> tuple[bool, str]:
    if state["daily_pnl_usd"] <= -MAX_DAILY_LOSS:
        return False, f"Daily loss limit hit (${-state['daily_pnl_usd']:.2f} / ${MAX_DAILY_LOSS})"
    return True, "ok"


def check_consecutive_losses(state: dict) -> tuple[bool, str]:
    if state["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        return False, f"Consecutive loss limit ({MAX_CONSECUTIVE_LOSSES}) — cooling off"
    return True, "ok"


def check_capital_at_risk(state: dict, new_stake: float, capital: float) -> tuple[bool, str]:
    current_risk = state.get("capital_at_risk_usd", 0.0)
    if capital <= 0:
        return False, "No capital"
    ratio = (current_risk + new_stake) / capital
    if ratio > MAX_CAPITAL_AT_RISK:
        return False, (
            f"Capital at risk would exceed {MAX_CAPITAL_AT_RISK*100:.0f}% "
            f"(${current_risk + new_stake:.2f} / ${capital:.2f})"
        )
    return True, "ok"


def check_edge(edge: float) -> tuple[bool, str]:
    if abs(edge) < MIN_EDGE:
        return False, f"Edge {abs(edge)*100:.1f}% below minimum {MIN_EDGE*100:.0f}%"
    return True, "ok"


def check_bet_size(stake: float) -> tuple[bool, str]:
    if stake <= 0:
        return False, "Stake is zero"
    if stake > MAX_BET:
        return False, f"Stake ${stake:.2f} exceeds MAX_BET ${MAX_BET}"
    return True, "ok"


def check_halt(state: dict) -> tuple[bool, str]:
    if state.get("halted"):
        return False, f"Trading halted: {state.get('halt_reason', 'unknown')}"
    return True, "ok"


def all_checks(edge: float, stake: float, capital: float,
               paper: bool = True) -> tuple[bool, list[str]]:
    """
    Run all guardrail checks.
    Returns (all_passed: bool, failed_reasons: list[str])
    Paper mode bypasses trade window and halt checks.
    """
    state   = get_guardrail_state()
    reasons = []

    checks = [
        check_trade_window(),     # always checked; bypassed by override or in-window
        check_halt(state),
        check_edge(edge),
        check_bet_size(stake),
        check_daily_trades(state),
        check_daily_loss(state),
        check_consecutive_losses(state),
        check_capital_at_risk(state, stake, capital),
    ]

    # Paper mode: skip window check unless override is explicitly OFF (default: allow anytime)
    if paper and not _window_override:
        checks.pop(0)  # remove window check — paper trades run anytime by default

    for passed, reason in checks:
        if not passed:
            reasons.append(reason)

    all_passed = len(reasons) == 0
    if not all_passed:
        log.warning("Guardrail block: %s", "; ".join(reasons))

    return all_passed, reasons


def guardrail_status() -> dict:
    """Return human-readable guardrail status for the dashboard."""
    state   = get_guardrail_state()
    summary = get_summary()
    capital = STARTING_CAPITAL + summary["total_pnl_usd"]

    window_ok, window_msg   = check_trade_window()
    halt_ok, halt_msg       = check_halt(state)

    return {
        "halted":              bool(state["halted"]),
        "halt_reason":         state.get("halt_reason"),
        "trade_window_active": window_ok,
        "trade_window_msg":    window_msg,
        "window_override":     _window_override,
        "daily_trades":        state["daily_trades"],
        "max_daily_trades":    MAX_DAILY_TRADES,
        "daily_pnl_usd":       round(state["daily_pnl_usd"], 2),
        "max_daily_loss":      MAX_DAILY_LOSS,
        "consecutive_losses":  state["consecutive_losses"],
        "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
        "capital_at_risk_usd": round(state["capital_at_risk_usd"], 2),
        "max_capital_at_risk": round(capital * MAX_CAPITAL_AT_RISK, 2),
        "capital_usd":         round(capital, 2),
    }
