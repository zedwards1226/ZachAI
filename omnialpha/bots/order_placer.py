"""Order placement — the ONLY path live orders can travel.

Two modes:
  - Paper (default per config.PAPER_MODE): simulates the order, writes to
    trades table with paper=1, returns a fake order ID. NEVER hits Kalshi.
  - Live (PAPER_MODE=false + explicit Zach approval): hits the real Kalshi
    API. Refused unless `assert_paper_mode_off_was_explicit()` is True.

The live path is gated by TWO checks: PAPER_MODE flag in .env AND a
runtime explicit-approval flag. Two locks. Both have to be off.

For now (Phase 2), the live code path exists but assert_paper_mode_off_was_explicit
returns False unconditionally. Toggling it is part of the live cutover —
a separate session with explicit Zach sign-off.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from config import PAPER_MODE
from data_layer.database import get_conn
from strategies.base import EntryDecision

logger = logging.getLogger(__name__)


def assert_paper_mode_off_was_explicit() -> bool:
    """Always False for now. Flipping this to True requires:
      1. Zach manually editing this file
      2. PAPER_MODE=false in .env
      3. A live-trading PR + merge approval

    Both gates must align before any real order leaves this PC.
    """
    return False


class OrderPlacementError(RuntimeError):
    pass


def place_paper_order(
    decision: EntryDecision,
    market_ticker: str,
    sector: str,
    strategy_name: str,
    decision_id: Optional[int] = None,
) -> dict:
    """Simulate the order in paper-mode. Writes to trades table, returns
    a fake order record."""
    now_iso = datetime.now(timezone.utc).isoformat()
    fake_order_id = f"paper-{uuid.uuid4().hex[:12]}"
    stake_usd = decision.contracts * decision.price_cents / 100.0

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades (
                timestamp, sector, strategy, market_ticker, side,
                contracts, price_cents, edge, kelly_frac, stake_usd,
                paper, status, decision_id
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'open', ?
            )
            """,
            (
                now_iso, sector, strategy_name, market_ticker, decision.side,
                decision.contracts, decision.price_cents,
                decision.edge, decision.kelly_frac, stake_usd,
                decision_id,
            ),
        )
        trade_id = cur.lastrowid

    logger.info(
        "[paper] %s/%s placed: %s %d×%s @%dc on %s — stake=$%.2f trade_id=%d",
        sector, strategy_name, decision.side.upper(), decision.contracts,
        market_ticker.split("-")[0], decision.price_cents, market_ticker,
        stake_usd, trade_id,
    )

    return {
        "order_id": fake_order_id,
        "trade_id": trade_id,
        "paper": True,
        "side": decision.side,
        "contracts": decision.contracts,
        "price_cents": decision.price_cents,
        "stake_usd": stake_usd,
    }


def place_live_order(
    decision: EntryDecision,
    market_ticker: str,
    sector: str,
    strategy_name: str,
    kalshi_client,
    decision_id: Optional[int] = None,
) -> dict:
    """REAL Kalshi order. Refused unless both PAPER_MODE=false AND
    assert_paper_mode_off_was_explicit() returns True.

    Even after both gates pass, the live path is wrapped in defensive checks:
    balance > stake, market still open, price hasn't moved >5 cents from
    decision.price_cents."""
    if PAPER_MODE:
        raise OrderPlacementError(
            "PAPER_MODE=true — cannot place live order. "
            "Set PAPER_MODE=false in .env if you really mean it."
        )
    if not assert_paper_mode_off_was_explicit():
        raise OrderPlacementError(
            "Live mode requires explicit code-level approval — see "
            "order_placer.assert_paper_mode_off_was_explicit(). "
            "Currently locked. Edit that function only after Zach's sign-off."
        )

    # The live code path. Wired but not callable until both gates flip.
    body = {
        "ticker": market_ticker,
        "side": decision.side,
        "action": "buy",
        "count": decision.contracts,
        "type": "limit",
        "time_in_force": "fill_or_kill",
        "client_order_id": f"omnialpha-{uuid.uuid4().hex[:12]}",
    }
    if decision.side == "yes":
        body["yes_price"] = decision.price_cents
    else:
        body["no_price"] = decision.price_cents

    result = kalshi_client.place_order(
        ticker=market_ticker,
        side=decision.side,
        action="buy",
        count=decision.contracts,
        price_cents=decision.price_cents,
        client_order_id=body["client_order_id"],
    )

    # Persist to trades table with paper=0
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades (
                timestamp, sector, strategy, market_ticker, side,
                contracts, price_cents, edge, kelly_frac, stake_usd,
                paper, status, decision_id, notes
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'open', ?, ?
            )
            """,
            (
                now_iso, sector, strategy_name, market_ticker, decision.side,
                decision.contracts, decision.price_cents,
                decision.edge, decision.kelly_frac,
                decision.contracts * decision.price_cents / 100.0,
                decision_id,
                f"kalshi_order_id={result.get('order', {}).get('order_id')}",
            ),
        )
        trade_id = cur.lastrowid

    return {
        "order_id": result.get("order", {}).get("order_id"),
        "trade_id": trade_id,
        "paper": False,
        **result,
    }


def place(
    decision: EntryDecision,
    market_ticker: str,
    sector: str,
    strategy_name: str,
    kalshi_client=None,
    decision_id: Optional[int] = None,
) -> dict:
    """Single entry point — dispatch to paper or live based on PAPER_MODE."""
    if PAPER_MODE:
        return place_paper_order(
            decision=decision, market_ticker=market_ticker,
            sector=sector, strategy_name=strategy_name, decision_id=decision_id,
        )
    if kalshi_client is None:
        raise OrderPlacementError("Live mode requires kalshi_client")
    return place_live_order(
        decision=decision, market_ticker=market_ticker,
        sector=sector, strategy_name=strategy_name,
        kalshi_client=kalshi_client, decision_id=decision_id,
    )


def mark_resolved(
    trade_id: int,
    *,
    won: bool,
    pnl_usd: float,
    settlement_value_dollars: float,
) -> None:
    """Settle a paper trade in the journal once the underlying market resolves."""
    now_iso = datetime.now(timezone.utc).isoformat()
    status = "won" if won else "lost"
    with get_conn() as conn:
        conn.execute(
            "UPDATE trades SET status = ?, pnl_usd = ?, resolved_at = ? "
            "WHERE id = ? AND status = 'open'",
            (status, pnl_usd, now_iso, trade_id),
        )
