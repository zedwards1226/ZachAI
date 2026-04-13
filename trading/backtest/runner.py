"""Historical ORB Backtester — runs scoring pipeline on past data.

Pulls historical 15-min candles via CDP, simulates the full ORB detection
and scoring engine for each trading day, and reports statistics.

Usage:
    python -m backtest.runner --days 60 --orb-minutes 15
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import pytz

from config import (
    TIMEZONE, ORB_MINUTES, SCORE_FULL_SIZE, SCORE_HALF_SIZE,
    STOP_EXTENSION_MULT, TARGET_1_MULT, TARGET_2_MULT,
    SLIPPAGE_PTS, MULTIPLIER, MAX_TRADES_PER_SESSION,
    VIX_HARD_BLOCK, ORB_ATR_MIN_PCT, ORB_ATR_MAX_PCT,
    RVOL_THRESHOLD, VIX_SWEET_SPOT_LOW, VIX_SWEET_SPOT_HIGH,
)
from models import Direction, CandleDirection, ScoreBreakdown, ORBRange, TradeSize

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


def _score_backtest(direction: Direction, orb: ORBRange,
                    is_second_break: bool, structure: dict,
                    memory: dict, price: float) -> ScoreBreakdown:
    """Score a simulated trade using available data."""
    b = ScoreBreakdown()

    # +3: ORB candle direction aligns
    if orb.candle_direction == CandleDirection.BULLISH and direction == Direction.LONG:
        b.orb_candle_direction = 3
    elif orb.candle_direction == CandleDirection.BEARISH and direction == Direction.SHORT:
        b.orb_candle_direction = 3

    # +2: HTF bias (from prior day direction)
    pd_dir = structure.get("prior_day_direction")
    if pd_dir:
        if (pd_dir == "BULLISH" and direction == Direction.LONG) or \
           (pd_dir == "BEARISH" and direction == Direction.SHORT):
            b.htf_bias = 2
        elif (pd_dir == "BULLISH" and direction == Direction.SHORT) or \
             (pd_dir == "BEARISH" and direction == Direction.LONG):
            b.bias_conflict = -2

    # +2: Second break
    if is_second_break:
        b.second_break = 2

    # +1: VIX sweet spot
    vix = structure.get("vix", 0)
    if vix and VIX_SWEET_SPOT_LOW <= vix <= VIX_SWEET_SPOT_HIGH:
        b.vix_regime = 1

    # +1: VWAP alignment (approximate from prior day close)
    pd_close = structure.get("prior_day_close", 0)
    if pd_close:
        if (direction == Direction.LONG and price > pd_close) or \
           (direction == Direction.SHORT and price < pd_close):
            b.vwap_alignment = 1

    # +1: Prior day direction
    if pd_dir:
        if (pd_dir == "BULLISH" and direction == Direction.LONG) or \
           (pd_dir == "BEARISH" and direction == Direction.SHORT):
            b.prior_day_direction = 1

    # +1: No news block (assume clear in backtest)
    b.no_news_block = 1
    b.no_truth_block = 1

    b.compute_total()
    return b


def _group_bars_by_day(bars: list[dict]) -> dict[str, list[dict]]:
    """Group bars into trading days based on timestamp."""
    days: dict[str, list[dict]] = defaultdict(list)
    for bar in bars:
        ts = bar["time"]
        if ts > 1e12:
            ts /= 1000
        dt = datetime.fromtimestamp(ts, tz=ET)
        date_str = dt.strftime("%Y-%m-%d")
        bar["_dt"] = dt
        days[date_str].append(bar)

    # Sort bars within each day
    for date_str in days:
        days[date_str].sort(key=lambda b: b["_dt"])

    return dict(days)


def _get_session_bars(day_bars: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split day bars into ORB window and post-ORB trading window.

    Returns (orb_bars, trading_bars).
    """
    orb_bars = []
    trading_bars = []

    for bar in day_bars:
        dt = bar["_dt"]
        h, m = dt.hour, dt.minute
        # ORB: 9:30 to 9:30 + ORB_MINUTES
        if h == 9 and 30 <= m < 30 + ORB_MINUTES:
            orb_bars.append(bar)
        # Trading window: 9:30+ORB_MINUTES to 11:00
        elif (h == 9 and m >= 30 + ORB_MINUTES) or (h == 10):
            trading_bars.append(bar)

    return orb_bars, trading_bars


def _simulate_day(date_str: str, day_bars: list[dict],
                  prev_day_bars: Optional[list[dict]] = None) -> Optional[dict]:
    """Simulate one trading day. Returns trade result or None."""
    orb_bars, trading_bars = _get_session_bars(day_bars)

    if not orb_bars or not trading_bars:
        return None

    # Capture ORB
    orb_high = max(b["high"] for b in orb_bars)
    orb_low = min(b["low"] for b in orb_bars)
    orb_range = orb_high - orb_low

    if orb_range <= 0:
        return None

    # ORB candle direction
    first_open = orb_bars[0]["open"]
    last_close = orb_bars[-1]["close"]
    candle_dir = CandleDirection.BULLISH if last_close > first_open else CandleDirection.BEARISH

    orb = ORBRange(
        high=orb_high, low=orb_low, range=orb_range,
        candle_direction=candle_dir, captured_at=date_str,
    )

    # Build approximate structure context from prior day
    structure = {}
    if prev_day_bars:
        pd_high = max(b["high"] for b in prev_day_bars)
        pd_low = min(b["low"] for b in prev_day_bars)
        pd_close = prev_day_bars[-1]["close"]
        pd_open = prev_day_bars[0]["open"]
        structure["prior_day_close"] = pd_close
        structure["prior_day_direction"] = "BULLISH" if pd_close > pd_open else "BEARISH"

    # Watch for breakouts in trading bars
    first_break_dir: Optional[Direction] = None
    first_break_failed = False
    trades_today = 0
    results = []

    for bar in trading_bars:
        if trades_today >= MAX_TRADES_PER_SESSION:
            break

        price = bar["close"]

        # Check breakout
        breakout_direction = None
        if price > orb_high:
            breakout_direction = Direction.LONG
        elif price < orb_low:
            breakout_direction = Direction.SHORT

        if breakout_direction is None:
            # Price back inside range
            if first_break_dir is not None and not first_break_failed:
                first_break_failed = True
            continue

        # Double break detection
        is_second_break = False
        if first_break_dir is None:
            first_break_dir = breakout_direction
        elif first_break_failed and breakout_direction != first_break_dir:
            is_second_break = True

        # Score
        breakdown = _score_backtest(
            breakout_direction, orb, is_second_break, structure, {}, price
        )

        score = breakdown.total
        if score < SCORE_HALF_SIZE:
            continue

        size = TradeSize.FULL if score >= SCORE_FULL_SIZE else TradeSize.HALF

        # Calculate stop/target
        if breakout_direction == Direction.LONG:
            stop = orb_low - (orb_range * (STOP_EXTENSION_MULT - 1))
            target_1 = price + (orb_range * TARGET_1_MULT)
            target_2 = price + (orb_range * TARGET_2_MULT)
        else:
            stop = orb_high + (orb_range * (STOP_EXTENSION_MULT - 1))
            target_1 = price - (orb_range * TARGET_1_MULT)
            target_2 = price - (orb_range * TARGET_2_MULT)

        # Simulate trade outcome using remaining bars
        bar_idx = trading_bars.index(bar)
        remaining = trading_bars[bar_idx + 1:]

        exit_price = price  # Default: exit at entry if no bars remain
        outcome = "SCRATCH"
        exit_reason = "no_bars"

        for future_bar in remaining:
            # Check stop
            if breakout_direction == Direction.LONG:
                if future_bar["low"] <= stop:
                    exit_price = stop
                    outcome = "LOSS"
                    exit_reason = "stop_hit"
                    break
                if future_bar["high"] >= target_2:
                    exit_price = target_2
                    outcome = "WIN"
                    exit_reason = "t2_hit"
                    break
                if future_bar["high"] >= target_1:
                    exit_price = target_1
                    outcome = "WIN"
                    exit_reason = "t1_hit"
                    break
            else:
                if future_bar["high"] >= stop:
                    exit_price = stop
                    outcome = "LOSS"
                    exit_reason = "stop_hit"
                    break
                if future_bar["low"] <= target_2:
                    exit_price = target_2
                    outcome = "WIN"
                    exit_reason = "t2_hit"
                    break
                if future_bar["low"] <= target_1:
                    exit_price = target_1
                    outcome = "WIN"
                    exit_reason = "t1_hit"
                    break
        else:
            # No stop/target hit — close at last bar (time exit)
            if remaining:
                exit_price = remaining[-1]["close"]
                if breakout_direction == Direction.LONG:
                    outcome = "WIN" if exit_price > price else "LOSS"
                else:
                    outcome = "WIN" if exit_price < price else "LOSS"
                exit_reason = "time_exit"

        # P&L
        if breakout_direction == Direction.LONG:
            pts = exit_price - price
        else:
            pts = price - exit_price

        pnl = pts * MULTIPLIER
        pnl_after_slip = (pts - SLIPPAGE_PTS) * MULTIPLIER
        risk = abs(price - stop)
        rr = pts / risk if risk > 0 else 0

        result = {
            "date": date_str,
            "direction": breakout_direction.value,
            "score": score,
            "size": size.value,
            "entry": round(price, 2),
            "stop": round(stop, 2),
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "exit_price": round(exit_price, 2),
            "outcome": outcome,
            "exit_reason": exit_reason,
            "pnl": round(pnl, 2),
            "pnl_after_slippage": round(pnl_after_slip, 2),
            "rr": round(rr, 2),
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_range": round(orb_range, 2),
            "orb_candle_direction": candle_dir.value,
            "was_second_break": is_second_break,
        }

        results.append(result)
        trades_today += 1

        # Only take first qualifying trade for simplicity
        break

    return results[0] if results else None


def _print_report(trades: list[dict], days_total: int):
    """Print backtest results summary."""
    print("\n" + "=" * 70)
    print("ORB BACKTEST RESULTS")
    print("=" * 70)

    if not trades:
        print("No trades generated.")
        return

    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = sum(1 for t in trades if t["outcome"] == "LOSS")
    scratches = total - wins - losses
    wr = wins / total if total else 0
    total_pnl = sum(t["pnl_after_slippage"] for t in trades)
    avg_rr = sum(t["rr"] for t in trades) / total if total else 0

    print(f"Days analyzed:    {days_total}")
    print(f"Trades taken:     {total}")
    print(f"Trade frequency:  {total / days_total * 100:.0f}% of days" if days_total else "")
    print(f"Wins:             {wins} ({wr:.0%})")
    print(f"Losses:           {losses}")
    print(f"Scratches:        {scratches}")
    print(f"Total P&L:        ${total_pnl:.2f} (after 2-pt slippage)")
    print(f"Avg RR:           {avg_rr:.2f}")

    # Max drawdown
    equity = 0
    peak = 0
    max_dd = 0
    for t in trades:
        equity += t["pnl_after_slippage"]
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    print(f"Max Drawdown:     ${max_dd:.2f}")

    # Simple Sharpe (daily returns)
    if total >= 5:
        returns = [t["pnl_after_slippage"] for t in trades]
        avg_ret = sum(returns) / len(returns)
        var = sum((r - avg_ret) ** 2 for r in returns) / len(returns)
        std = var ** 0.5
        sharpe = (avg_ret / std) * (252 ** 0.5) if std > 0 else 0
        print(f"Sharpe (approx):  {sharpe:.2f}")

    # Score band breakdown
    print("\nWin Rate by Score Band:")
    for band_name, lo, hi in [("7+ (full)", 7, 99), ("5-6 (half)", 5, 6)]:
        band = [t for t in trades if lo <= t["score"] <= hi]
        if band:
            bw = sum(1 for t in band if t["outcome"] == "WIN")
            bwr = bw / len(band)
            bpnl = sum(t["pnl_after_slippage"] for t in band)
            print(f"  Score {band_name}: {bwr:.0%} WR ({len(band)} trades, ${bpnl:.2f})")

    # Second break analysis
    sb = [t for t in trades if t["was_second_break"]]
    fb = [t for t in trades if not t["was_second_break"]]
    if sb:
        sbw = sum(1 for t in sb if t["outcome"] == "WIN")
        print(f"\nSecond Break WR:  {sbw / len(sb):.0%} ({len(sb)} trades)")
    if fb:
        fbw = sum(1 for t in fb if t["outcome"] == "WIN")
        print(f"First Break WR:   {fbw / len(fb):.0%} ({len(fb)} trades)")

    # ORB candle direction analysis
    print("\nORB Candle Direction:")
    for cd in ["BULLISH", "BEARISH"]:
        cd_trades = [t for t in trades if t["orb_candle_direction"] == cd]
        if cd_trades:
            cdw = sum(1 for t in cd_trades if t["outcome"] == "WIN")
            print(f"  {cd}: {cdw / len(cd_trades):.0%} WR ({len(cd_trades)} trades)")

    # Exit reason breakdown
    print("\nExit Reasons:")
    from collections import Counter
    reasons = Counter(t["exit_reason"] for t in trades)
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count}")

    # Best and worst trades
    best = max(trades, key=lambda t: t["pnl_after_slippage"])
    worst = min(trades, key=lambda t: t["pnl_after_slippage"])
    print(f"\nBest trade:  {best['date']} {best['direction']} ${best['pnl_after_slippage']:.2f}")
    print(f"Worst trade: {worst['date']} {worst['direction']} ${worst['pnl_after_slippage']:.2f}")

    # Daily P&L
    print("\nDaily Breakdown:")
    for t in trades:
        marker = "W" if t["outcome"] == "WIN" else "L" if t["outcome"] == "LOSS" else "S"
        sb_mark = " [2nd]" if t["was_second_break"] else ""
        print(f"  {t['date']} {t['direction']:5s} score={t['score']:2d} "
              f"entry={t['entry']:.2f} exit={t['exit_price']:.2f} "
              f"P&L=${t['pnl_after_slippage']:+.2f} [{marker}]{sb_mark}")

    print("=" * 70)


async def run_backtest(days: int = 60, orb_minutes: int = 15):
    """Run the historical backtester.

    Fetches bars from TradingView via CDP and simulates the scoring engine.
    """
    from services.tv_client import get_client

    print(f"Starting backtest: {days} days, {orb_minutes}-min ORB")

    tv = await get_client()

    # Switch to 5-min chart for granular data
    await tv.set_timeframe("5")
    await asyncio.sleep(2)

    # Need ~78 bars per day (6:30 AM to 1 PM = 78 five-min bars)
    # For 60 days: ~4,680 bars. TradingView can return many bars on scroll.
    total_bars_needed = days * 80
    print(f"Fetching {total_bars_needed} bars (5-min)...")

    bars = await tv.get_ohlcv(count=min(total_bars_needed, 5000))
    print(f"Got {len(bars)} bars")

    if len(bars) < 80:
        print("ERROR: Not enough bars for backtest. Check TradingView connection.")
        return

    # Group into trading days
    day_groups = _group_bars_by_day(bars)
    dates = sorted(day_groups.keys())
    print(f"Found {len(dates)} trading days")

    # Simulate each day
    all_trades = []
    for i, date_str in enumerate(dates):
        prev_day_bars = day_groups.get(dates[i - 1]) if i > 0 else None
        result = _simulate_day(date_str, day_groups[date_str], prev_day_bars)
        if result:
            all_trades.append(result)

    # Print report
    _print_report(all_trades, len(dates))

    # Save results
    output = {
        "run_date": datetime.now(ET).isoformat(),
        "days_analyzed": len(dates),
        "orb_minutes": orb_minutes,
        "trades": all_trades,
        "summary": {
            "total_trades": len(all_trades),
            "wins": sum(1 for t in all_trades if t["outcome"] == "WIN"),
            "losses": sum(1 for t in all_trades if t["outcome"] == "LOSS"),
            "total_pnl": round(sum(t["pnl_after_slippage"] for t in all_trades), 2),
        },
    }

    output_path = "backtest_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="ORB Historical Backtester")
    parser.add_argument("--days", type=int, default=60, help="Number of days to backtest")
    parser.add_argument("--orb-minutes", type=int, default=ORB_MINUTES, help="ORB window in minutes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run_backtest(args.days, args.orb_minutes))


if __name__ == "__main__":
    main()
