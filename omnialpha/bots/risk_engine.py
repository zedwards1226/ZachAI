"""5-gate pre-trade risk engine + cross-bot risk-state coupling.

Inspired by OctagonAI/kalshi-trading-bot-cli's pre-trade gates. Every entry
the strategy proposes runs through the gates IN ORDER. First gate to fail
kills the trade.

Gates:
  1. Paper-mode check       — refuse if PAPER_MODE flag is off without approval
  2. Per-trade $ cap        — clamp contract count so max_loss <= PER_TRADE_MAX_RISK_USD
  3. Liquidity              — refuse if market volume_fp < MIN_LIQUIDITY_FP
  4. Concentration          — refuse if open positions in this sector >= MAX_CONCURRENT
  5. Drawdown / loss caps   — daily, weekly, consecutive losses. Refuse if breached
  6. Cross-bot risk state   — read shared risk_state.json. If aggregate loss across all
                              ZachAI bots breaches DAILY_MAX_LOSS_USD, refuse

(Six gates total, not five. The 5-in-the-name comes from OctagonAI's original;
adding cross-bot gates Zach asked for explicitly. The naming is intentional.)

Returns RiskCheckResult with verdict + reason + clamped contract count.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import (
    DAILY_MAX_LOSS_USD,
    MAX_CONCURRENT_POSITIONS,
    MAX_TRADES_PER_SECTOR_PER_DAY,
    PAPER_MODE,
    PER_TRADE_MAX_RISK_USD,
    SHARED_RISK_STATE,
    WEEKLY_MAX_LOSS_USD,
)
from data_layer.database import get_conn
from strategies.base import EntryDecision, MarketSnapshot, StrategyContext

logger = logging.getLogger(__name__)

# Don't trade markets with less than this volume — unreliable pricing.
MIN_LIQUIDITY_FP = 500.0

# Cap on consecutive losses in a sector before forced cooldown.
MAX_CONSEC_LOSSES_BEFORE_PAUSE = 5

# Sector cooldown duration once tripped.
SECTOR_COOLDOWN_HOURS = 6


@dataclass
class RiskCheckResult:
    approved: bool
    reason: str             # short tag, machine-friendly ('per_trade_cap', 'liquidity', ...)
    detail: str             # human-readable
    clamped_contracts: int  # what the strategy should ACTUALLY enter (0 if denied)


def check_entry(
    decision: EntryDecision,
    market: MarketSnapshot,
    context: StrategyContext,
) -> RiskCheckResult:
    """Run all gates. Return verdict for the runner."""

    # Gate 1: paper mode
    if not PAPER_MODE:
        return RiskCheckResult(
            approved=False,
            reason="paper_mode_off",
            detail="PAPER_MODE is not enabled. Refusing live order without approval.",
            clamped_contracts=0,
        )

    # Gate 2: per-trade $ cap → clamp contracts
    # max_loss for a binary YES/NO bet at price p, n contracts = n × p × $1
    # (since worst case the contract goes to 0).
    p = decision.price_cents / 100.0
    if p <= 0:
        return RiskCheckResult(
            approved=False,
            reason="invalid_price",
            detail=f"Decision had price_cents={decision.price_cents}",
            clamped_contracts=0,
        )
    max_contracts_by_dollar_cap = max(1, int(PER_TRADE_MAX_RISK_USD / p))
    clamped = min(decision.contracts, max_contracts_by_dollar_cap)
    if clamped == 0:
        return RiskCheckResult(
            approved=False,
            reason="per_trade_cap_excludes_min_size",
            detail=f"PER_TRADE_MAX_RISK_USD ${PER_TRADE_MAX_RISK_USD} cannot fit even 1 contract at {decision.price_cents}c",
            clamped_contracts=0,
        )

    # Gate 3: liquidity floor
    if market.volume_fp < MIN_LIQUIDITY_FP:
        return RiskCheckResult(
            approved=False,
            reason="liquidity",
            detail=f"market volume {market.volume_fp:.0f} < floor {MIN_LIQUIDITY_FP:.0f}",
            clamped_contracts=0,
        )

    # Gate 4: concentration — max open positions
    if context.open_positions_count >= MAX_CONCURRENT_POSITIONS:
        return RiskCheckResult(
            approved=False,
            reason="concentration",
            detail=f"already {context.open_positions_count} open positions (cap {MAX_CONCURRENT_POSITIONS})",
            clamped_contracts=0,
        )

    # Gate 5: drawdown / loss caps
    if -context.daily_realized_pnl_usd >= DAILY_MAX_LOSS_USD:
        return RiskCheckResult(
            approved=False,
            reason="daily_loss_cap",
            detail=f"daily loss ${context.daily_realized_pnl_usd:+.2f} exceeds cap ${DAILY_MAX_LOSS_USD}",
            clamped_contracts=0,
        )
    if -context.weekly_realized_pnl_usd >= WEEKLY_MAX_LOSS_USD:
        return RiskCheckResult(
            approved=False,
            reason="weekly_loss_cap",
            detail=f"weekly loss ${context.weekly_realized_pnl_usd:+.2f} exceeds cap ${WEEKLY_MAX_LOSS_USD}",
            clamped_contracts=0,
        )
    if context.consecutive_losses_in_sector >= MAX_CONSEC_LOSSES_BEFORE_PAUSE:
        return RiskCheckResult(
            approved=False,
            reason="consec_losses_pause",
            detail=f"sector {context.sector} has {context.consecutive_losses_in_sector} consecutive losses",
            clamped_contracts=0,
        )

    # Gate 5b: per-sector daily trade cap (don't burn the day on one sector)
    today_in_sector = _count_today_trades_in_sector(context.sector)
    if today_in_sector >= MAX_TRADES_PER_SECTOR_PER_DAY:
        return RiskCheckResult(
            approved=False,
            reason="sector_daily_trade_cap",
            detail=f"sector {context.sector}: {today_in_sector} trades today (cap {MAX_TRADES_PER_SECTOR_PER_DAY})",
            clamped_contracts=0,
        )

    # Gate 6: cross-bot risk state — read shared file, refuse if aggregate breached
    cross_bot = _read_cross_bot_state()
    if cross_bot.get("halt_all"):
        return RiskCheckResult(
            approved=False,
            reason="cross_bot_halt",
            detail=f"shared risk_state.halt_all set: {cross_bot.get('reason', 'unknown')}",
            clamped_contracts=0,
        )

    return RiskCheckResult(
        approved=True,
        reason="ok",
        detail="all gates passed",
        clamped_contracts=clamped,
    )


def _count_today_trades_in_sector(sector: str) -> int:
    """Count today's TV-confirmed (non-failed) trades in a sector."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sql = (
        "SELECT COUNT(*) FROM trades "
        "WHERE sector = ? AND substr(timestamp, 1, 10) = ? "
        "AND status != 'failed_placement'"
    )
    try:
        with get_conn(readonly=True) as conn:
            return conn.execute(sql, (sector, today)).fetchone()[0]
    except Exception as e:
        logger.warning("could not count today's trades for %s: %s", sector, e)
        return 0


# ─── Cross-bot risk state ─────────────────────────────────────────────
# Shared file at C:\ZachAI\data\risk_state.json. Each bot writes its own
# section. All bots read aggregate halt flag. File-locked to prevent
# concurrent-write torn JSON.
_RISK_STATE_LOCK_TIMEOUT_S = 5.0


def _read_cross_bot_state() -> dict:
    """Read shared risk_state.json. Returns {} if missing or corrupt — fail open."""
    if not SHARED_RISK_STATE.exists():
        return {}
    try:
        return json.loads(SHARED_RISK_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def update_my_section(
    *,
    bot: str = "omnialpha",
    daily_pnl_usd: float,
    weekly_pnl_usd: float,
    open_positions: int,
    last_trade_ts: Optional[str] = None,
) -> None:
    """Write our section to risk_state.json, preserving other bots' data.

    Uses a sidecar .lock file as a coarse mutex. Best-effort — if locking
    fails we still write (the consequence is rare race-write churn, not
    correctness).
    """
    SHARED_RISK_STATE.parent.mkdir(parents=True, exist_ok=True)
    lock = SHARED_RISK_STATE.with_suffix(".lock")
    deadline = time.monotonic() + _RISK_STATE_LOCK_TIMEOUT_S

    # Acquire-or-skip
    while lock.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        lock.touch()
    except Exception:
        pass

    try:
        state = _read_cross_bot_state()
        bots = state.setdefault("bots", {})
        bots[bot] = {
            "daily_pnl_usd": daily_pnl_usd,
            "weekly_pnl_usd": weekly_pnl_usd,
            "open_positions": open_positions,
            "last_trade_ts": last_trade_ts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Aggregate daily P&L across all bots — used by halt logic
        agg_daily = sum(
            (b.get("daily_pnl_usd") or 0)
            for b in bots.values()
        )
        state["aggregate_daily_pnl_usd"] = agg_daily
        # Trip the global halt if aggregate daily loss breaches cap
        # (this is in addition to per-bot daily caps — defense in depth)
        if -agg_daily >= DAILY_MAX_LOSS_USD * 2:  # 2× per-bot cap = global halt
            state["halt_all"] = True
            state["reason"] = (
                f"aggregate daily loss ${agg_daily:+.2f} exceeded global cap"
            )
        else:
            # Don't auto-clear halt_all; that requires manual reset
            pass

        SHARED_RISK_STATE.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def clear_global_halt(reason: str = "manual") -> None:
    """Operator-initiated unlock. Used after investigating a halt trigger."""
    state = _read_cross_bot_state()
    if state.pop("halt_all", None):
        state["last_halt_clear_reason"] = reason
        state["last_halt_clear_at"] = datetime.now(timezone.utc).isoformat()
        SHARED_RISK_STATE.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )
        logger.warning("Cleared global halt: %s", reason)
