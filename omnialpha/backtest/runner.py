"""Backtest harness. Replays settled markets through a strategy.

Backtest model — intentionally simple:
  1. Iterate settled markets in `markets` table for a given sector/series
  2. For each market, synthesize a MarketSnapshot at the "decision moment"
     (defaults to the market's last public price before close)
  3. Call strategy.decide_entry(market, context). If returns EntryDecision,
     simulate the trade.
  4. At settlement, compute PnL = (settlement_value - entry_price) × contracts
     (signed for YES vs NO)
  5. Track running capital, win rate, Brier score, sector consecutive losses
  6. Return BacktestResult with per-trade detail + aggregate metrics

This is "directional" backtest — it does NOT model intra-trade exit logic
(stops, trails, time-exits) because we don't have second-resolution price
paths in the markets table. To model exits properly we'd need
/historical/trades for each market — see backtest/runner_with_trades.py
(future work).

Fee model: Kalshi charges 7% of profit on winning trades, no fee on losses.
Hardcoded here, configurable in v2.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterator

# Backtest decision moment: how many seconds before close the strategy
# evaluates the market. Matches live-scanner policy (enter in the last
# few minutes where the calibration distribution actually applies).
BACKTEST_DECISION_OFFSET_S = 120

from data_layer.database import get_conn
from strategies.base import EntryDecision, MarketSnapshot, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Kalshi fee — 7% of winnings on YES side fills, equivalent on NO. Verify
# before live; this is the published retail rate as of 2026.
KALSHI_FEE_RATE = 0.07


@dataclass
class BacktestTrade:
    """One simulated trade. Append-only."""
    market_ticker: str
    side: str
    contracts: int
    entry_price_cents: int
    exit_price_cents: int            # 100 if YES wins, 0 if NO wins (Kalshi binary)
    edge: float
    forecast_prob: float
    pnl_usd: float
    won: bool
    reason: str
    sector: str
    decision_ts: str


@dataclass
class BacktestResult:
    strategy_name: str
    starting_capital_usd: float
    ending_capital_usd: float
    n_markets_evaluated: int
    n_trades: int
    n_wins: int
    n_losses: int
    realized_pnl_usd: float
    max_drawdown_usd: float
    sharpe_proxy: float              # mean / std of per-trade returns
    win_rate: float                  # wins / (wins + losses)
    avg_win_usd: float
    avg_loss_usd: float
    profit_factor: float             # sum(wins) / |sum(losses)|
    trades: list[BacktestTrade] = field(default_factory=list)


def _market_snapshot_from_db_row(row: dict) -> MarketSnapshot:
    """Build a MarketSnapshot from the markets table.

    Decision moment is the LAST PUBLIC TRADE before settlement — that's
    `last_price_dollars` from raw_json, expressed in YES dollars. The
    schema's `final_yes_ask_dollars` is post-settlement residual (always
    0 or 1) and useless for replay. For binary markets, last_price IS the
    implied YES probability the market was settling at right before close.
    """
    import json as _json
    try:
        raw = _json.loads(row["raw_json"]) if row.get("raw_json") else {}
    except (TypeError, ValueError, _json.JSONDecodeError):
        raw = {}

    last_yes = _safe_float(raw.get("last_price_dollars"))
    if last_yes is None:
        last_yes = 0.5  # un-traded; strategy should reject anyway via volume filter
    yes_ask = int(round(last_yes * 100))
    no_ask = int(round((1 - last_yes) * 100))
    last = yes_ask
    # Bids approximated 1c tighter — backtest doesn't need precise bids,
    # only ask side for entry simulation.
    yes_bid = max(0, yes_ask - 1)
    no_bid = max(0, no_ask - 1)

    # Decision moment is "2 minutes before close" — matches live-scanner
    # entry policy (only trade in the final stretch, where price ≈ closing
    # distribution that the calibration was measured on). Without this the
    # MIN_SECONDS_TO_CLOSE filter never trips in backtest, since (close - open)
    # is the FULL market lifetime (900s for KXBTC15M), not time remaining.
    open_dt = _parse_iso(row["open_time"]) or datetime.now(timezone.utc)
    close_dt = _parse_iso(row["close_time"]) or open_dt
    decision_moment = close_dt - timedelta(seconds=BACKTEST_DECISION_OFFSET_S)
    seconds_to_close = max(
        0, int((close_dt - decision_moment).total_seconds())
    )

    return MarketSnapshot(
        ticker=row["ticker"],
        sector=row["sector"] or "other",
        series_ticker=row["series_ticker"],
        title=row["title"] or "",
        open_time=row["open_time"] or "",
        close_time=row["close_time"] or "",
        yes_ask_cents=yes_ask,
        yes_bid_cents=yes_bid,
        no_ask_cents=no_ask,
        no_bid_cents=no_bid,
        last_price_cents=last,
        volume_fp=row["volume_fp"] or 0.0,
        open_interest_fp=row["open_interest_fp"] or 0.0,
        seconds_to_close=seconds_to_close,
        extras={
            "strike_type": row["strike_type"],
            "floor_strike": row["floor_strike"],
            "cap_strike": row["cap_strike"],
        },
    )


def _safe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _iter_settled_markets(
    *,
    sector: str | None = None,
    series_ticker: str | None = None,
    limit: int | None = None,
) -> Iterator[dict]:
    """Pull settled markets from DB in close_time order — chronological replay."""
    sql = (
        "SELECT * FROM markets WHERE status='finalized' AND result IN ('yes','no') "
    )
    params: list = []
    if sector:
        sql += " AND sector = ?"
        params.append(sector)
    if series_ticker:
        sql += " AND series_ticker = ?"
        params.append(series_ticker)
    sql += " ORDER BY close_time ASC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn(readonly=True) as conn:
        for row in conn.execute(sql, params):
            yield dict(row)


def _resolve_pnl(
    decision: EntryDecision,
    market_row: dict,
) -> tuple[float, bool, int]:
    """Compute PnL for one settled binary trade.

    Kalshi binary markets settle at 100 cents (YES) or 0 cents (NO).
    PnL formula:
      - Buy YES at p cents, settles 100 → win: contracts * (100 - p) cents
      - Buy YES at p cents, settles 0   → loss: -contracts * p cents
      - Buy NO at p cents, settles 0 (yes loses) → win: contracts * (100 - p) cents
      - Buy NO at p cents, settles 100 (yes wins) → loss: -contracts * p cents
    Apply Kalshi fee (7%) to winning P&L.

    Returns (pnl_usd, won, exit_price_cents).
    """
    result = market_row.get("result")  # 'yes' or 'no'
    side = decision.side.lower()
    p = decision.price_cents
    n = decision.contracts

    yes_won = (result == "yes")
    bet_won = (side == "yes" and yes_won) or (side == "no" and not yes_won)

    if bet_won:
        gross_cents = n * (100 - p)
        fee_cents = gross_cents * KALSHI_FEE_RATE
        net_cents = gross_cents - fee_cents
        return (net_cents / 100.0, True, 100 if side == "yes" else 0)
    else:
        loss_cents = n * p
        return (-loss_cents / 100.0, False, 0 if side == "yes" else 100)


def run_backtest(
    strategy: Strategy,
    *,
    sector: str | None = None,
    series_ticker: str | None = None,
    starting_capital_usd: float = 100.0,
    limit: int | None = None,
    apply_risk_engine: bool = True,
) -> BacktestResult:
    """Run a strategy against settled-market history. Returns full result."""
    capital = starting_capital_usd
    peak_capital = capital
    max_drawdown = 0.0

    trades: list[BacktestTrade] = []
    wins = 0
    losses = 0
    sector_consec_losses = 0
    n_markets = 0
    daily_pnl = 0.0
    weekly_pnl = 0.0
    last_decision_date: str | None = None

    for market_row in _iter_settled_markets(
        sector=sector, series_ticker=series_ticker, limit=limit
    ):
        n_markets += 1
        snap = _market_snapshot_from_db_row(market_row)

        # Reset daily P&L accumulator on date rollover (used to feed the
        # strategy's StrategyContext for risk-aware sizing).
        decision_date = (snap.close_time or "")[:10]
        if decision_date != last_decision_date:
            daily_pnl = 0.0
            last_decision_date = decision_date

        ctx = StrategyContext(
            capital_usd=capital,
            open_positions_count=0,    # backtest closes each trade at settlement
            daily_realized_pnl_usd=daily_pnl,
            weekly_realized_pnl_usd=weekly_pnl,
            sector=snap.sector,
            consecutive_losses_in_sector=sector_consec_losses,
        )
        decision = strategy.decide_entry(snap, ctx)
        if decision is None:
            continue

        # Run through risk engine (same gates the live bot will apply,
        # except for ones that need live DB / cross-bot state which would
        # leak production state into the backtest).
        if apply_risk_engine:
            from bots.risk_engine import check_entry
            verdict = check_entry(decision, snap, ctx, skip_db_gates=True)
            if not verdict.approved:
                continue
            if verdict.clamped_contracts != decision.contracts:
                from dataclasses import replace
                decision = replace(decision, contracts=verdict.clamped_contracts)

        pnl, won, exit_price = _resolve_pnl(decision, market_row)
        capital += pnl
        daily_pnl += pnl
        weekly_pnl += pnl
        peak_capital = max(peak_capital, capital)
        max_drawdown = max(max_drawdown, peak_capital - capital)

        if won:
            wins += 1
            sector_consec_losses = 0
        else:
            losses += 1
            sector_consec_losses += 1

        trades.append(BacktestTrade(
            market_ticker=snap.ticker,
            side=decision.side,
            contracts=decision.contracts,
            entry_price_cents=decision.price_cents,
            exit_price_cents=exit_price,
            edge=decision.edge,
            forecast_prob=decision.forecast_prob,
            pnl_usd=pnl,
            won=won,
            reason=decision.reason,
            sector=snap.sector,
            decision_ts=snap.close_time,
        ))

    # Aggregate metrics
    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades else 0.0
    win_pnls = [t.pnl_usd for t in trades if t.won]
    loss_pnls = [t.pnl_usd for t in trades if not t.won]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    profit_factor = (sum(win_pnls) / abs(sum(loss_pnls))) if loss_pnls and sum(loss_pnls) != 0 else float("inf") if win_pnls else 0.0
    realized_pnl = capital - starting_capital_usd

    # Sharpe proxy (per-trade): mean(returns) / std(returns).
    # Returns expressed as % of starting capital so trades are comparable.
    if total_trades >= 2:
        returns = [t.pnl_usd / starting_capital_usd for t in trades]
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = var ** 0.5
        sharpe_proxy = mean / std if std > 0 else 0.0
    else:
        sharpe_proxy = 0.0

    return BacktestResult(
        strategy_name=strategy.name,
        starting_capital_usd=starting_capital_usd,
        ending_capital_usd=capital,
        n_markets_evaluated=n_markets,
        n_trades=total_trades,
        n_wins=wins,
        n_losses=losses,
        realized_pnl_usd=realized_pnl,
        max_drawdown_usd=max_drawdown,
        sharpe_proxy=sharpe_proxy,
        win_rate=win_rate,
        avg_win_usd=avg_win,
        avg_loss_usd=avg_loss,
        profit_factor=profit_factor,
        trades=trades,
    )


def format_result(result: BacktestResult) -> str:
    """One-screen summary, no JSON noise."""
    lines = [
        f"=== Backtest: {result.strategy_name} ===",
        f"Markets evaluated:  {result.n_markets_evaluated:,}",
        f"Trades taken:       {result.n_trades:,}  ({result.n_trades / max(result.n_markets_evaluated, 1) * 100:.1f}% take rate)",
        f"Wins / losses:      {result.n_wins} / {result.n_losses}",
        f"Win rate:           {result.win_rate * 100:.1f}%",
        f"Starting capital:   ${result.starting_capital_usd:,.2f}",
        f"Ending capital:     ${result.ending_capital_usd:,.2f}",
        f"Realized P&L:       ${result.realized_pnl_usd:+,.2f}",
        f"Max drawdown:       ${result.max_drawdown_usd:,.2f}",
        f"Avg win / loss:     ${result.avg_win_usd:+,.2f} / ${result.avg_loss_usd:+,.2f}",
        f"Profit factor:      {result.profit_factor:.2f}",
        f"Sharpe (per-trade): {result.sharpe_proxy:.3f}",
    ]
    return "\n".join(lines)
