"""Strategy base class — every strategy module implements this contract.

Two paths:
  decide_entry(market, context) -> EntryDecision | None
      Called when a new market becomes scoreable. Returns None to skip,
      or an EntryDecision specifying side, size, target/stop.

  decide_exit(position, market, context) -> ExitDecision | None
      Called periodically while a position is open. Returns None to hold,
      or an ExitDecision to close.

The runner (live or backtest) calls these. Strategies are pure functions of
their inputs — no I/O, no time.sleep, no logging side effects beyond what
the runner provides. This keeps backtests deterministic and tests trivial.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MarketSnapshot:
    """A read-only view of a market at decision time. Filled by the runner.

    For backtests: synthesized from settled market data + (optional) trades.
    For live: filled from REST + WebSocket polling.
    """
    ticker: str
    sector: str
    series_ticker: Optional[str]
    title: str
    open_time: str            # ISO
    close_time: str           # ISO
    yes_ask_cents: int        # ask price for YES, 0-100
    yes_bid_cents: int
    no_ask_cents: int
    no_bid_cents: int
    last_price_cents: int
    volume_fp: float
    open_interest_fp: float
    seconds_to_close: int     # negative if closed
    extras: dict[str, Any] = field(default_factory=dict)  # sector-specific bits


@dataclass
class StrategyContext:
    """What the strategy knows about itself + the wider state."""
    capital_usd: float
    open_positions_count: int
    daily_realized_pnl_usd: float
    weekly_realized_pnl_usd: float
    sector: str
    consecutive_losses_in_sector: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryDecision:
    """A bid to enter a market. The runner applies risk gates before placing."""
    side: str              # 'yes' or 'no'
    contracts: int
    price_cents: int       # limit price (use ask for immediate fill)
    edge: float            # forecast_prob - market_prob (signed)
    forecast_prob: float   # the strategy's estimate
    kelly_frac: float      # full Kelly value the strategy computed (risk engine clamps)
    reason: str            # short tag for journal/audit
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExitDecision:
    """A bid to close a position."""
    reason: str            # 'stop_loss' | 'take_profit' | 'time_exit' | 'risk_cap' | etc
    notes: str = ""


class Strategy(ABC):
    """Strategy contract. Each strategy is a class with a unique `name`."""

    name: str = "abstract"
    sector: str = "abstract"

    @abstractmethod
    def decide_entry(
        self,
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[EntryDecision]:
        ...

    @abstractmethod
    def decide_exit(
        self,
        position: dict,            # row from trades table for the open position
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[ExitDecision]:
        ...
