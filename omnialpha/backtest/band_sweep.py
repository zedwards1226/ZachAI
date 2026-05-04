"""Band sweep + auto-tuner.

Performance: pre-loads markets+snapshots for the series ONCE, then runs
every variant against the cached list. Naive sweep would call run_backtest
per variant which re-queries the DB each time — 300+ variants × 500k
markets = hours. Cached version is ~100x faster.


For each strategy, generate variations of its NO/YES bands, run a
backtest on each variation against historical settled markets, pick
the variant with the highest realized P&L (subject to a minimum
trade-count floor to avoid trivial "0 trades = 0 P&L" winners).

Designed to err on the MORE TRADES side. Per Zach 2026-05-04:
"don't use too many guardrails to where it dont trade — we can be
to safe." So:
  - No "X% improvement required to update" gate. If backtest says
    new bands are better, ship them.
  - No "must be inside calibration CI" rail. Backtest is the truth.
  - Single floor: min trade count >= MIN_TRADES so we don't pick
    a degenerate "0 trades, neutral" variant just because it has
    no losses.
  - Single sanity rail: backtested win rate >= MIN_WINRATE so we
    don't ship something gambling.

Output:
  - Returns dict[strategy_name -> {old_bands, new_bands, backtest_metrics}]
  - Caller (band_tuner.tune_all_strategies) writes the new bands to
    state/strategy_bands.json which main.py reads on startup.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from itertools import product
from typing import Iterable

from backtest.runner import (
    BacktestResult,
    BacktestTrade,
    _iter_settled_markets,
    _market_snapshot_from_db_row,
    _resolve_pnl,
    run_backtest,
)
from strategies.base import StrategyContext
from strategies.crypto_midband import CryptoMidBandStrategy

logger = logging.getLogger(__name__)

# ── Tunables ─────────────────────────────────────────────────────────────
MIN_TRADES = 30          # backtest must place at least this many trades
MIN_WINRATE = 0.65       # backtested win rate floor; below = gambling
STARTING_CAPITAL = 500.0


# Band sweep grid. Coarse on purpose — fine sweeps explode the search
# space without changing the winner much.
NO_LOW_GRID = [0.05, 0.10, 0.15, 0.20]
NO_HIGH_GRID = [0.25, 0.30, 0.35, 0.40]
NO_FORECAST_GRID = [0.05, 0.08, 0.10, 0.12, 0.15]

YES_LOW_GRID = [0.60, 0.65, 0.70, 0.75]
YES_HIGH_GRID = [0.80, 0.85, 0.90]
YES_FORECAST_GRID = [0.80, 0.85, 0.88, 0.90, 0.92, 0.95]


def _generate_no_bands(allow_empty: bool = True) -> Iterable[list[tuple]]:
    """Yield single-NO-band variations, plus the empty option if allowed."""
    if allow_empty:
        yield []
    for lo, hi, f in product(NO_LOW_GRID, NO_HIGH_GRID, NO_FORECAST_GRID):
        if hi <= lo:
            continue
        # Forecast must be <= lo (we expect actual rate to be below lo).
        if f > lo:
            continue
        yield [(lo, hi, f)]


def _generate_yes_bands(allow_empty: bool = True) -> Iterable[list[tuple]]:
    """Yield single-YES-band variations, plus the empty option if allowed."""
    if allow_empty:
        yield []
    for lo, hi, f in product(YES_LOW_GRID, YES_HIGH_GRID, YES_FORECAST_GRID):
        if hi <= lo:
            continue
        # Forecast must be >= hi (we expect actual rate to be above hi).
        if f < hi:
            continue
        yield [(lo, hi, f)]


# Cap markets per series to keep sweep wall-time tractable. Daily series
# (KXBTCD/KXETHD) have 500k+ rows because each strike of each daily event
# is its own market — using ALL of them costs an hour per sweep without
# changing the answer materially. The most-recent N is also a more
# RELEVANT sample for forward-looking band tuning (recent regime).
MAX_MARKETS_PER_SWEEP = 30_000


def _load_market_cache(series_ticker: str) -> list[tuple]:
    """Pre-build (snapshot, market_row) pairs ONCE per series. Reused
    across all variant evaluations for that series — this is the speed
    optimization that makes the sweep tractable for daily series.
    Caps at MAX_MARKETS_PER_SWEEP most-recent markets to bound run-time."""
    # Pull most-recent N to keep memory + runtime bounded; the sweep
    # function in runner.py iterates close_time ASC, so we rev-sort here
    # to get newest, then re-sort ASC for chronological replay.
    from data_layer.database import get_conn
    sql = (
        "SELECT * FROM markets WHERE status='finalized' "
        "AND result IN ('yes','no') AND series_ticker = ? "
        "ORDER BY close_time DESC LIMIT ?"
    )
    rows: list[dict] = []
    with get_conn(readonly=True) as conn:
        for row in conn.execute(sql, (series_ticker, MAX_MARKETS_PER_SWEEP)):
            rows.append(dict(row))
    rows.reverse()  # back to chronological order for the replay
    cache: list[tuple] = []
    for row in rows:
        snap = _market_snapshot_from_db_row(row)
        cache.append((snap, row))
    return cache


def _eval_variant_cached(
    *,
    base_strategy: CryptoMidBandStrategy,
    no_bands: list[tuple],
    yes_bands: list[tuple],
    cache: list[tuple],
) -> BacktestResult | None:
    """Run a single variant against pre-loaded market cache. Mirrors
    run_backtest() logic but skips the DB query and the risk engine
    (apply_risk_engine=False is the standard for sweeps)."""
    if not no_bands and not yes_bands:
        return None

    variant = CryptoMidBandStrategy(
        kelly_fraction=base_strategy.kelly_fraction,
        name=base_strategy.name + "__sweep",
        no_bands=deepcopy(no_bands),
        yes_bands=deepcopy(yes_bands),
        min_volume_fp=getattr(base_strategy, "_min_volume_fp", None),
        max_seconds_to_close=getattr(base_strategy, "_max_seconds_to_close", None),
        min_seconds_to_close=getattr(base_strategy, "_min_seconds_to_close", None),
    )

    capital = STARTING_CAPITAL
    peak_capital = capital
    max_drawdown = 0.0
    wins = 0
    losses = 0
    trades: list[BacktestTrade] = []
    sector_consec_losses = 0
    daily_pnl = 0.0
    weekly_pnl = 0.0
    last_decision_date: str | None = None
    n_markets = len(cache)

    for snap, market_row in cache:
        decision_date = (snap.close_time or "")[:10]
        if decision_date != last_decision_date:
            daily_pnl = 0.0
            last_decision_date = decision_date

        ctx = StrategyContext(
            capital_usd=capital,
            open_positions_count=0,
            daily_realized_pnl_usd=daily_pnl,
            weekly_realized_pnl_usd=weekly_pnl,
            sector=snap.sector,
            consecutive_losses_in_sector=sector_consec_losses,
        )
        decision = variant.decide_entry(snap, ctx)
        if decision is None:
            continue
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

    total = wins + losses
    win_rate = wins / total if total else 0.0
    win_pnls = [t.pnl_usd for t in trades if t.won]
    loss_pnls = [t.pnl_usd for t in trades if not t.won]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    profit_factor = (sum(win_pnls) / abs(sum(loss_pnls))) if loss_pnls and sum(loss_pnls) != 0 else (float("inf") if win_pnls else 0.0)
    sharpe = 0.0
    if total >= 2:
        rets = [t.pnl_usd / STARTING_CAPITAL for t in trades]
        m = sum(rets) / len(rets)
        var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
        sd = var ** 0.5
        sharpe = m / sd if sd > 0 else 0.0
    return BacktestResult(
        strategy_name=variant.name,
        starting_capital_usd=STARTING_CAPITAL,
        ending_capital_usd=capital,
        n_markets_evaluated=n_markets,
        n_trades=total,
        n_wins=wins,
        n_losses=losses,
        realized_pnl_usd=capital - STARTING_CAPITAL,
        max_drawdown_usd=max_drawdown,
        sharpe_proxy=sharpe,
        win_rate=win_rate,
        avg_win_usd=avg_win,
        avg_loss_usd=avg_loss,
        profit_factor=profit_factor,
        trades=trades,
    )


def sweep_strategy(
    strategy: CryptoMidBandStrategy,
    series_ticker: str,
    *,
    no_only: bool = False,
) -> dict:
    """Run the full sweep for one strategy. Returns:
        {
          'strategy': strategy.name,
          'series_ticker': series_ticker,
          'baseline': {pnl, winrate, trades, no_bands, yes_bands},
          'best': {pnl, winrate, trades, no_bands, yes_bands},
          'changed': bool,
        }
    """
    cache = _load_market_cache(series_ticker)
    logger.info("Sweep %s: cached %d markets", strategy.name, len(cache))

    baseline_result = _eval_variant_cached(
        base_strategy=strategy,
        no_bands=strategy._no_bands,
        yes_bands=strategy._yes_bands,
        cache=cache,
    )
    baseline = {
        "pnl": baseline_result.realized_pnl_usd if baseline_result else 0.0,
        "winrate": baseline_result.win_rate if baseline_result else 0.0,
        "trades": baseline_result.n_trades if baseline_result else 0,
        "no_bands": deepcopy(strategy._no_bands),
        "yes_bands": deepcopy(strategy._yes_bands),
    }

    # Generate variants — if the existing strategy is NO-only, keep
    # exploring NO-only and NO+YES; if it's both-sided, do the same.
    candidates = []
    yes_options = list(_generate_yes_bands(allow_empty=True))
    if no_only:
        no_options = list(_generate_no_bands(allow_empty=False))
    else:
        no_options = list(_generate_no_bands(allow_empty=True))

    for nb, yb in product(no_options, yes_options):
        if not nb and not yb:
            continue
        result = _eval_variant_cached(
            base_strategy=strategy,
            no_bands=nb,
            yes_bands=yb,
            cache=cache,
        )
        if result is None:
            continue
        if result.n_trades < MIN_TRADES:
            continue
        if result.win_rate < MIN_WINRATE:
            continue
        candidates.append((result, nb, yb))

    if not candidates:
        return {
            "strategy": strategy.name,
            "series_ticker": series_ticker,
            "baseline": baseline,
            "best": baseline,
            "changed": False,
            "reason": "no candidates passed MIN_TRADES + MIN_WINRATE",
        }

    # Score: realized P&L, descending. Simple is fine. Trade count is
    # already enforced via MIN_TRADES; win rate via MIN_WINRATE; this
    # leaves us picking the variant that made the most money.
    candidates.sort(key=lambda c: c[0].realized_pnl_usd, reverse=True)
    best_result, best_nb, best_yb = candidates[0]
    best = {
        "pnl": best_result.realized_pnl_usd,
        "winrate": best_result.win_rate,
        "trades": best_result.n_trades,
        "no_bands": best_nb,
        "yes_bands": best_yb,
    }

    # "Changed" = best is meaningfully better than baseline AND bands differ.
    changed = (
        best["pnl"] > baseline["pnl"]
        and (best_nb != baseline["no_bands"] or best_yb != baseline["yes_bands"])
    )

    return {
        "strategy": strategy.name,
        "series_ticker": series_ticker,
        "baseline": baseline,
        "best": best,
        "changed": changed,
        "candidates_evaluated": len(candidates),
    }
