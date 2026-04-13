"""TradingView Replay Backtester — visual step-by-step via MCP replay tools.

Uses TradingView's replay mode to step through historical data candle-by-candle,
running the scoring engine at each step. Places trades in replay mode that are
visible on the chart.

Usage:
    python -m backtest.replay --date 2026-04-01 --days 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz

from config import (
    TIMEZONE, ORB_MINUTES, ORB_START_HOUR, ORB_START_MINUTE,
    SESSION_END_HOUR, SESSION_END_MINUTE,
    SCORE_FULL_SIZE, SCORE_HALF_SIZE,
    STOP_EXTENSION_MULT, TARGET_1_MULT, TARGET_2_MULT,
    SLIPPAGE_PTS, MULTIPLIER,
    VIX_SWEET_SPOT_LOW, VIX_SWEET_SPOT_HIGH,
)
from models import Direction, CandleDirection, ScoreBreakdown, ORBRange, TradeSize
from services.tv_client import get_client

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# Replay session state
_orb: Optional[ORBRange] = None
_first_break_dir: Optional[Direction] = None
_first_break_failed: bool = False
_trades_today: int = 0


def _reset_replay_state():
    global _orb, _first_break_dir, _first_break_failed, _trades_today
    _orb = None
    _first_break_dir = None
    _first_break_failed = False
    _trades_today = 0


def _score_replay(direction: Direction, orb: ORBRange,
                  is_second_break: bool, price: float) -> ScoreBreakdown:
    """Simplified scoring for replay mode."""
    b = ScoreBreakdown()

    # +3: ORB candle direction
    if orb.candle_direction == CandleDirection.BULLISH and direction == Direction.LONG:
        b.orb_candle_direction = 3
    elif orb.candle_direction == CandleDirection.BEARISH and direction == Direction.SHORT:
        b.orb_candle_direction = 3

    # +2: Second break
    if is_second_break:
        b.second_break = 2

    # +1: No news/truth (assume clear in replay)
    b.no_news_block = 1
    b.no_truth_block = 1

    # +1: VWAP alignment (approximate — above ORB mid for longs)
    orb_mid = (orb.high + orb.low) / 2
    if (direction == Direction.LONG and price > orb_mid) or \
       (direction == Direction.SHORT and price < orb_mid):
        b.vwap_alignment = 1

    b.compute_total()
    return b


async def replay_day(tv, date_str: str) -> list[dict]:
    """Replay one trading day using TradingView replay mode.

    Steps through the session candle-by-candle, detects ORB and breakouts,
    and places replay trades when signals fire.
    """
    _reset_replay_state()
    global _orb, _first_break_dir, _first_break_failed, _trades_today

    print(f"\n--- Replaying {date_str} ---")

    # Start replay at 9:25 AM (5 min before ORB)
    replay_start = f"{date_str}T09:25:00"

    # Use CDP to start replay
    start_js = f"""
    (function() {{
      try {{
        var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
        var replay = chart.model().replayController();
        if (!replay) return {{success: false, reason: 'No replay controller'}};
        replay.start(new Date('{replay_start}').getTime() / 1000);
        return {{success: true}};
      }} catch(e) {{
        return {{success: false, reason: e.message}};
      }}
    }})()
    """
    result = await tv.evaluate(start_js)
    if not result or not result.get("success"):
        print(f"  Failed to start replay: {result}")
        return []

    await asyncio.sleep(2)

    trades = []
    bars_seen = []
    orb_bars = []
    active_trade = None

    # Step through ~90 bars (9:25 to 11:00 on 1-min = 95 bars)
    # On 5-min chart: ~19 bars
    max_steps = 100
    step_delay = 0.5  # seconds between steps

    for step in range(max_steps):
        # Step one candle forward
        step_js = """
        (function() {
          try {
            var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
            var replay = chart.model().replayController();
            if (!replay || !replay.isActive()) return {active: false};
            replay.step();
            return {active: true};
          } catch(e) {
            return {active: false, error: e.message};
          }
        })()
        """
        step_result = await tv.evaluate(step_js)
        if not step_result or not step_result.get("active"):
            break

        await asyncio.sleep(step_delay)

        # Get current bar data
        quote = await tv.get_quote()
        price = quote.get("last") or quote.get("close", 0)
        if price == 0:
            continue

        bar = {
            "time": quote.get("time", 0),
            "open": quote.get("open", 0),
            "high": quote.get("high", 0),
            "low": quote.get("low", 0),
            "close": price,
            "volume": quote.get("volume", 0),
        }
        bars_seen.append(bar)

        # Determine current time from bar timestamp
        bar_ts = bar["time"]
        if bar_ts > 1e12:
            bar_ts /= 1000
        if bar_ts < 1e8:
            # No valid timestamp, estimate from step count
            continue

        bar_dt = datetime.fromtimestamp(bar_ts, tz=ET)
        h, m = bar_dt.hour, bar_dt.minute

        # Collect ORB bars (9:30 to 9:30 + ORB_MINUTES)
        if h == 9 and 30 <= m < 30 + ORB_MINUTES:
            orb_bars.append(bar)
            continue

        # Capture ORB after the window
        if _orb is None and orb_bars and (h > 9 or m >= 30 + ORB_MINUTES):
            orb_high = max(b["high"] for b in orb_bars)
            orb_low = min(b["low"] for b in orb_bars)
            orb_range = orb_high - orb_low
            if orb_range <= 0:
                print(f"  ORB range zero, skipping day")
                break

            first_open = orb_bars[0]["open"]
            last_close = orb_bars[-1]["close"]
            candle_dir = CandleDirection.BULLISH if last_close > first_open else CandleDirection.BEARISH

            _orb = ORBRange(
                high=orb_high, low=orb_low, range=orb_range,
                candle_direction=candle_dir, captured_at=date_str,
            )
            print(f"  ORB: H={orb_high:.2f} L={orb_low:.2f} range={orb_range:.2f} dir={candle_dir.value}")

            # Draw ORB levels on chart
            await _draw_replay_level(tv, orb_high, "ORB High", "#2196F3")
            await _draw_replay_level(tv, orb_low, "ORB Low", "#2196F3")

        # Past 11:00 AM — stop
        if h >= SESSION_END_HOUR:
            break

        if _orb is None:
            continue

        # --- Manage active trade ---
        if active_trade:
            direction = active_trade["direction"]
            entry = active_trade["entry"]
            stop = active_trade["stop"]
            t1 = active_trade["target_1"]
            t2 = active_trade["target_2"]

            hit = None
            if direction == "LONG":
                if bar["low"] <= stop:
                    hit = ("LOSS", stop, "stop_hit")
                elif bar["high"] >= t2:
                    hit = ("WIN", t2, "t2_hit")
                elif bar["high"] >= t1:
                    hit = ("WIN", t1, "t1_hit")
            else:
                if bar["high"] >= stop:
                    hit = ("LOSS", stop, "stop_hit")
                elif bar["low"] <= t2:
                    hit = ("WIN", t2, "t2_hit")
                elif bar["low"] <= t1:
                    hit = ("WIN", t1, "t1_hit")

            if hit:
                outcome, exit_price, exit_reason = hit
                if direction == "LONG":
                    pts = exit_price - entry
                else:
                    pts = entry - exit_price
                pnl = (pts - SLIPPAGE_PTS) * MULTIPLIER

                active_trade.update({
                    "exit_price": round(exit_price, 2),
                    "outcome": outcome,
                    "exit_reason": exit_reason,
                    "pnl_after_slippage": round(pnl, 2),
                })
                trades.append(active_trade)
                active_trade = None

                color = "#4CAF50" if outcome == "WIN" else "#F44336"
                print(f"  EXIT: {outcome} at {exit_price:.2f} P&L=${pnl:.2f} ({exit_reason})")
                await _draw_replay_level(tv, exit_price, f"EXIT {outcome}", color)

            continue

        # --- Watch for breakout ---
        breakout_dir = None
        if price > _orb.high:
            breakout_dir = Direction.LONG
        elif price < _orb.low:
            breakout_dir = Direction.SHORT

        if breakout_dir is None:
            if _first_break_dir is not None and not _first_break_failed:
                _first_break_failed = True
                print(f"  First break failed — double break forming")
            continue

        # Double break
        is_second_break = False
        if _first_break_dir is None:
            _first_break_dir = breakout_dir
        elif _first_break_failed and breakout_dir != _first_break_dir:
            is_second_break = True
            print(f"  SECOND BREAK: {breakout_dir.value}")

        # Score
        breakdown = _score_replay(breakout_dir, _orb, is_second_break, price)
        score = breakdown.total

        if score < SCORE_HALF_SIZE:
            print(f"  Breakout {breakout_dir.value} score={score} — SKIP")
            continue

        size = TradeSize.FULL if score >= SCORE_FULL_SIZE else TradeSize.HALF

        # Calculate stops/targets
        orb_range = _orb.range
        if breakout_dir == Direction.LONG:
            stop = _orb.low - (orb_range * (STOP_EXTENSION_MULT - 1))
            target_1 = price + (orb_range * TARGET_1_MULT)
            target_2 = price + (orb_range * TARGET_2_MULT)
        else:
            stop = _orb.high + (orb_range * (STOP_EXTENSION_MULT - 1))
            target_1 = price - (orb_range * TARGET_1_MULT)
            target_2 = price - (orb_range * TARGET_2_MULT)

        active_trade = {
            "date": date_str,
            "direction": breakout_dir.value,
            "score": score,
            "size": size.value,
            "entry": round(price, 2),
            "stop": round(stop, 2),
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "was_second_break": is_second_break,
            "orb_candle_direction": _orb.candle_direction.value,
        }
        _trades_today += 1

        sb_mark = " [2nd break]" if is_second_break else ""
        print(f"  ENTRY: {breakout_dir.value} at {price:.2f} score={score} "
              f"stop={stop:.2f} t1={target_1:.2f} t2={target_2:.2f}{sb_mark}")

        # Draw on chart
        await _draw_replay_level(tv, price, f"ENTRY {breakout_dir.value}", "#2196F3")
        await _draw_replay_level(tv, stop, "STOP", "#F44336")
        await _draw_replay_level(tv, target_1, "T1", "#4CAF50")
        await _draw_replay_level(tv, target_2, "T2", "#4CAF50")

    # Close any remaining trade at session end
    if active_trade and bars_seen:
        last_price = bars_seen[-1]["close"]
        direction = active_trade["direction"]
        entry = active_trade["entry"]
        if direction == "LONG":
            pts = last_price - entry
        else:
            pts = entry - last_price
        pnl = (pts - SLIPPAGE_PTS) * MULTIPLIER

        active_trade.update({
            "exit_price": round(last_price, 2),
            "outcome": "WIN" if pts > 0 else "LOSS",
            "exit_reason": "time_exit",
            "pnl_after_slippage": round(pnl, 2),
        })
        trades.append(active_trade)
        print(f"  TIME EXIT at {last_price:.2f} P&L=${pnl:.2f}")

    # Stop replay
    stop_js = """
    (function() {
      try {
        var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
        var replay = chart.model().replayController();
        if (replay && replay.isActive()) replay.stop();
        return true;
      } catch(e) { return false; }
    })()
    """
    await tv.evaluate(stop_js)

    return trades


async def _draw_replay_level(tv, price: float, text: str, color: str):
    """Draw a level on the chart during replay."""
    js = f"""
    (function() {{
      try {{
        var chart = window.TradingViewApi._activeChartWidgetWV.value();
        chart.createMultipointShape([{{price: {price}, time: Date.now()/1000}}], {{
          shape: 'horizontal_line',
          overrides: {{
            linecolor: '{color}',
            linewidth: 1,
            linestyle: 0,
            showLabel: true,
            text: '{text} {price:.2f}',
            horzLabelsAlign: 'right',
            textcolor: '{color}',
            fontsize: 9
          }}
        }});
        return true;
      }} catch(e) {{ return false; }}
    }})()
    """
    try:
        await tv.evaluate(js)
    except Exception:
        pass


async def run_replay(start_date: str, days: int = 5):
    """Run replay backtester across multiple days.

    Steps through each day visually on the TradingView chart.
    """
    tv = await get_client()

    # Set to 5-min timeframe
    await tv.set_timeframe("5")
    await asyncio.sleep(2)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    all_trades = []

    for i in range(days):
        day = start + timedelta(days=i)

        # Skip weekends
        if day.weekday() >= 5:
            continue

        date_str = day.strftime("%Y-%m-%d")
        day_trades = await replay_day(tv, date_str)
        all_trades.extend(day_trades)

        if day_trades:
            for t in day_trades:
                marker = "W" if t["outcome"] == "WIN" else "L"
                print(f"  Result: {t['direction']} ${t['pnl_after_slippage']:+.2f} [{marker}]")
        else:
            print(f"  No trades")

        # Pause between days for chart cleanup
        await asyncio.sleep(2)

    # Summary
    print("\n" + "=" * 50)
    print("REPLAY BACKTEST SUMMARY")
    print("=" * 50)

    if not all_trades:
        print("No trades taken across replay period.")
        return

    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["outcome"] == "WIN")
    total_pnl = sum(t["pnl_after_slippage"] for t in all_trades)
    wr = wins / total if total else 0

    print(f"Days replayed: {days}")
    print(f"Trades: {total}")
    print(f"Win Rate: {wr:.0%}")
    print(f"Total P&L: ${total_pnl:.2f}")

    # Save results
    output = {
        "run_date": datetime.now(ET).isoformat(),
        "start_date": start_date,
        "days": days,
        "trades": all_trades,
    }
    with open("replay_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nResults saved to replay_results.json")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="TradingView Replay Backtester")
    parser.add_argument("--date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=5, help="Number of days to replay")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run_replay(args.date, args.days))


if __name__ == "__main__":
    main()
