"""NY AM FVG strategy — first ICT setup ICTBot trades.

Setup definition:
- Time window: 09:30–10:30 ET (FVG must form here; entry retracement allowed
  until 11:00)
- Look for a clean 5m FVG with displacement (gap ≥ FVG_MIN_GAP_POINTS,
  middle-bar body ≥ DISPLACEMENT_MIN_POINTS)
- HTF bias: only take longs if 1H bias is long, only shorts if bias is short
- Entry: market on the first 5m bar that wicks INTO the FVG zone (between
  fvg.low and fvg.high) and CLOSES still inside or beyond it (mitigation
  + acceptance)
- Stop: opposite extreme of the displacement leg, +STOP_BUFFER_POINTS
- Target: 2R by default, capped at PD high/low if closer

Returns a dict the scanner uses to log + (optionally) place a trade.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dt_time
from typing import Any, Sequence

import pytz

from config import (
    TIMEZONE, ICT_SYMBOL, ICT_TIMEFRAME,
    FVG_MIN_GAP_POINTS, DISPLACEMENT_MIN_POINTS, STOP_BUFFER_POINTS,
    DEFAULT_RR_TARGET, NY_AM_START, NY_AM_END,
)
from services.ict_analyzer import find_fvgs, FVG, atr

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


def _bar_et(bar: Any) -> datetime:
    """Return bar.time as ET-aware datetime."""
    t = bar.time
    if t.tzinfo is None:
        t = pytz.UTC.localize(t)
    return t.astimezone(ET)


def in_ny_am_window(bar: Any) -> bool:
    et = _bar_et(bar)
    bar_time = et.time()
    return NY_AM_START <= bar_time <= dt_time(11, 0)  # entry allowed till 11:00


def _displacement_extreme(bars: Sequence[Any], fvg: FVG) -> tuple[float, float]:
    """Return (low_extreme, high_extreme) of the 3-bar displacement window."""
    win = bars[max(0, fvg.middle_bar_index - 1):fvg.middle_bar_index + 2]
    return min(b.low for b in win), max(b.high for b in win)


def evaluate(bars: Sequence[Any], htf_bias: str,
             pdh: float | None = None, pdl: float | None = None) -> dict | None:
    """Scan recent bars for a NY AM FVG entry trigger on the LAST bar.

    Returns a dict like:
        {
            "setup_name": "ny_am_fvg",
            "side": "long" | "short",
            "entry": float,
            "stop": float,
            "target": float,
            "rr": float,
            "fvg": FVG,
            "reason": str,
        }
    or None if no trigger.
    """
    if len(bars) < 10:
        return None

    last_bar = bars[-1]
    if not in_ny_am_window(last_bar):
        return None

    # Restrict to bars whose middle is in the 09:30-10:30 displacement window
    fvgs_today = []
    for f in find_fvgs(bars, min_gap=FVG_MIN_GAP_POINTS,
                       min_displacement=DISPLACEMENT_MIN_POINTS):
        mid = bars[f.middle_bar_index]
        et = _bar_et(mid)
        if dt_time(9, 30) <= et.time() <= dt_time(10, 30):
            fvgs_today.append(f)
    if not fvgs_today:
        return None

    # Bias filter: only take direction that matches HTF
    candidates: list[FVG] = []
    for f in fvgs_today:
        if htf_bias == "long" and f.direction == "bullish":
            candidates.append(f)
        elif htf_bias == "short" and f.direction == "bearish":
            candidates.append(f)
    if not candidates:
        return None

    # Use the most recent qualifying FVG
    fvg = candidates[-1]

    # Has the LAST bar wicked into the FVG zone?
    in_zone = (fvg.low <= last_bar.low and last_bar.low <= fvg.high) or \
              (fvg.low <= last_bar.high and last_bar.high <= fvg.high)
    if not in_zone:
        return None

    # Acceptance check: bar closed inside zone OR closed beyond it on the
    # bias direction (so a decisive rejection bar doesn't lock us out)
    closed_inside = fvg.low <= last_bar.close <= fvg.high
    closed_beyond = (fvg.direction == "bullish" and last_bar.close > fvg.midpoint) or \
                    (fvg.direction == "bearish" and last_bar.close < fvg.midpoint)
    if not (closed_inside or closed_beyond):
        return None

    # Build the trade plan
    disp_low, disp_high = _displacement_extreme(bars, fvg)
    side = "long" if fvg.direction == "bullish" else "short"
    entry = last_bar.close
    if side == "long":
        stop = disp_low - STOP_BUFFER_POINTS
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + risk * DEFAULT_RR_TARGET
        if pdh is not None and pdh < target:
            target = pdh
    else:
        stop = disp_high + STOP_BUFFER_POINTS
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - risk * DEFAULT_RR_TARGET
        if pdl is not None and pdl > target:
            target = pdl

    rr = abs(target - entry) / max(abs(entry - stop), 1e-9)
    if rr < 1.0:
        return None

    return {
        "setup_name": "ny_am_fvg",
        "symbol": ICT_SYMBOL,
        "timeframe": ICT_TIMEFRAME,
        "side": side,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "rr": round(rr, 2),
        "fvg_high": fvg.high,
        "fvg_low": fvg.low,
        "fvg_direction": fvg.direction,
        "displacement_pts": fvg.displacement_pts,
        "htf_bias": htf_bias,
        "reason": f"5m close into NY AM {fvg.direction} FVG, HTF bias={htf_bias}",
    }
