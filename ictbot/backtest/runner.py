"""Backtest runner — replay bars through ny_am_fvg strategy with simulated fills.

Fill model (matches what we plan to validate against live paper):
- Entry on next bar OPEN at close+1tick slippage (long) or close-1tick (short)
- Stop fills if bar high/low touches SL price
- Target fills if bar high/low touches TP price
- Same-bar SL+TP touch → assume SL (conservative)
- Commission: $0.74 round trip per MES contract

Output: list of trade dicts with entry/exit/PnL/R, plus aggregate stats.

Usage:
    python -m backtest.runner --symbol MES1! --days 30
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Iterable

import pytz

# repo-root path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (  # noqa: E402
    TIMEZONE, ICT_SYMBOL, MULTIPLIER, FVG_MIN_GAP_POINTS,
    DISPLACEMENT_MIN_POINTS, STOP_BUFFER_POINTS, DEFAULT_RR_TARGET,
)
from services.tv_data import Bar  # noqa: E402
from services.ict_analyzer import find_fvgs  # noqa: E402
from backtest.data_loader import load_yf  # noqa: E402

ET = pytz.timezone(TIMEZONE)
TICK = 0.25
COMMISSION_RT = 0.74  # round-trip per contract

logger = logging.getLogger(__name__)


@dataclass
class SimTrade:
    entry_time: datetime
    entry_price: float
    side: str
    stop: float
    target: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    pnl_dollars: float | None = None
    pnl_r: float | None = None


def _bar_et(b: Bar) -> datetime:
    t = b.time
    if t.tzinfo is None:
        t = pytz.UTC.localize(t)
    return t.astimezone(ET)


def _htf_bias_at(bars: list[Bar], i: int) -> str:
    """Quick proxy: 50-EMA on the last 50 bars vs current close."""
    if i < 50:
        return "neutral"
    closes = [b.close for b in bars[max(0, i - 60):i + 1]]
    k = 2 / (50 + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    last = closes[-1]
    if last > ema * 1.0005:
        return "long"
    if last < ema * 0.9995:
        return "short"
    return "neutral"


def _group_by_session(bars: list[Bar]) -> dict[str, list[tuple[int, Bar]]]:
    """Bucket bars by ET date. Each value is [(orig_index, bar), ...]."""
    out: dict[str, list[tuple[int, Bar]]] = {}
    for i, b in enumerate(bars):
        d = _bar_et(b).strftime("%Y-%m-%d")
        out.setdefault(d, []).append((i, b))
    return out


def _simulate_trade(bars: list[Bar], entry_idx: int, side: str,
                    entry_price: float, stop: float, target: float,
                    max_hold_bars: int = 24) -> SimTrade:
    """Simulate fill against bar OHLC. Returns a closed SimTrade."""
    risk_pts = abs(entry_price - stop)
    trade = SimTrade(
        entry_time=_bar_et(bars[entry_idx]),
        entry_price=entry_price,
        side=side, stop=stop, target=target,
    )
    end_idx = min(len(bars), entry_idx + max_hold_bars)
    for j in range(entry_idx + 1, end_idx):
        b = bars[j]
        if side == "long":
            sl_hit = b.low <= stop
            tp_hit = b.high >= target
            if sl_hit and tp_hit:
                trade.exit_price = stop
                trade.exit_reason = "sl_hit"
            elif tp_hit:
                trade.exit_price = target
                trade.exit_reason = "tp_hit"
            elif sl_hit:
                trade.exit_price = stop
                trade.exit_reason = "sl_hit"
            else:
                continue
        else:  # short
            sl_hit = b.high >= stop
            tp_hit = b.low <= target
            if sl_hit and tp_hit:
                trade.exit_price = stop
                trade.exit_reason = "sl_hit"
            elif tp_hit:
                trade.exit_price = target
                trade.exit_reason = "tp_hit"
            elif sl_hit:
                trade.exit_price = stop
                trade.exit_reason = "sl_hit"
            else:
                continue
        trade.exit_time = _bar_et(b)
        break
    if trade.exit_price is None:
        # Time exit at last bar's close
        last = bars[end_idx - 1]
        trade.exit_price = last.close
        trade.exit_reason = "time_exit"
        trade.exit_time = _bar_et(last)

    pnl_pts = (trade.exit_price - entry_price) if side == "long" else (entry_price - trade.exit_price)
    trade.pnl_dollars = pnl_pts * MULTIPLIER - COMMISSION_RT
    trade.pnl_r = pnl_pts / risk_pts if risk_pts > 0 else 0.0
    return trade


def run_ny_am_fvg(bars: list[Bar]) -> list[SimTrade]:
    """Walk bars chronologically; for each NY AM session, take the first
    valid FVG entry and simulate the trade.
    """
    trades: list[SimTrade] = []
    sessions = _group_by_session(bars)
    for d in sorted(sessions.keys()):
        session = sessions[d]
        # Restrict to bars between 09:25 and 11:00 ET to find FVG + entry
        am_window = [
            (i, b) for (i, b) in session
            if dt_time(9, 25) <= _bar_et(b).time() <= dt_time(11, 0)
        ]
        if len(am_window) < 6:
            continue
        # Use the global bars array indexes
        last_global_idx = am_window[-1][0]
        # Build a slice ending at the last AM bar so HTF EMA has context
        slice_end = last_global_idx + 1
        slice_start = max(0, slice_end - 200)
        window = bars[slice_start:slice_end]
        if len(window) < 30:
            continue
        bias = _htf_bias_at(bars, last_global_idx)
        if bias == "neutral":
            continue

        fvgs = [
            f for f in find_fvgs(window, min_gap=FVG_MIN_GAP_POINTS,
                                 min_displacement=DISPLACEMENT_MIN_POINTS)
            if (window[f.middle_bar_index].time.tzinfo is not None) and
               dt_time(9, 30) <= _bar_et(window[f.middle_bar_index]).time() <= dt_time(10, 30)
        ]
        if not fvgs:
            continue
        # Filter to direction matching bias
        fvgs = [f for f in fvgs if (bias == "long" and f.direction == "bullish") or
                                   (bias == "short" and f.direction == "bearish")]
        if not fvgs:
            continue
        fvg = fvgs[-1]

        # Find first bar AFTER the FVG window that wicks into the gap
        entry_global_idx = None
        for k in range(slice_start + fvg.middle_bar_index + 2, slice_end):
            b = bars[k]
            t_et = _bar_et(b).time()
            if t_et > dt_time(11, 0):
                break
            in_zone = (fvg.low <= b.low <= fvg.high) or (fvg.low <= b.high <= fvg.high)
            if in_zone:
                entry_global_idx = k
                break
        if entry_global_idx is None:
            continue

        # Stop = displacement extreme +/- buffer
        disp_window = bars[slice_start + fvg.middle_bar_index - 1: slice_start + fvg.middle_bar_index + 2]
        if not disp_window:
            continue
        disp_low = min(b.low for b in disp_window)
        disp_high = max(b.high for b in disp_window)

        entry_close = bars[entry_global_idx].close
        if fvg.direction == "bullish":
            stop = disp_low - STOP_BUFFER_POINTS
            risk = entry_close - stop
            if risk <= 0:
                continue
            target = entry_close + risk * DEFAULT_RR_TARGET
            trade = _simulate_trade(bars, entry_global_idx, "long",
                                     entry_close, stop, target)
        else:
            stop = disp_high + STOP_BUFFER_POINTS
            risk = stop - entry_close
            if risk <= 0:
                continue
            target = entry_close - risk * DEFAULT_RR_TARGET
            trade = _simulate_trade(bars, entry_global_idx, "short",
                                     entry_close, stop, target)
        trades.append(trade)
    return trades


def summarize(trades: list[SimTrade]) -> dict:
    if not trades:
        return {"trades": 0}
    wins = [t for t in trades if (t.pnl_dollars or 0) > 0]
    losses = [t for t in trades if (t.pnl_dollars or 0) <= 0]
    total_pnl = sum((t.pnl_dollars or 0) for t in trades)
    avg_r = sum((t.pnl_r or 0) for t in trades) / len(trades)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 3),
        "total_pnl_dollars": round(total_pnl, 2),
        "avg_r": round(avg_r, 3),
        "best_pnl": round(max((t.pnl_dollars or 0) for t in trades), 2),
        "worst_pnl": round(min((t.pnl_dollars or 0) for t in trades), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=ICT_SYMBOL)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--csv", default=None, help="optional path to a bars CSV")
    args = parser.parse_args()

    if args.csv:
        from backtest.data_loader import load_csv
        bars = load_csv(Path(args.csv))
    else:
        lookback = args.days * 24 * 60
        bars = load_yf(args.symbol, interval="5m", lookback_minutes=lookback)

    if not bars:
        print("no bars loaded — Yahoo may be rate-limited or symbol unsupported")
        return 1

    print(f"loaded {len(bars)} bars from {bars[0].time.isoformat()} to {bars[-1].time.isoformat()}")
    trades = run_ny_am_fvg(bars)
    summary = summarize(trades)
    print("\nSummary:", summary)
    print("\nTrades:")
    for t in trades:
        print(f"  {t.entry_time.isoformat()}  {t.side:5s}  "
              f"entry={t.entry_price:.2f} stop={t.stop:.2f} target={t.target:.2f}  "
              f"exit={t.exit_price:.2f} ({t.exit_reason})  "
              f"P&L=${t.pnl_dollars:+.2f} ({t.pnl_r:+.2f}R)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
