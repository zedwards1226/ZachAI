"""ICT pattern detection on bar series.

Pure functions over an iterable of `Bar` objects (or any obj with .open/.high/.low/.close).
No I/O, no SQLite — keeps unit testing trivial.

Detected patterns:
- FVG (Fair Value Gap) — 3-bar bullish/bearish gap
- Liquidity sweep — bar wicks past prior swing then closes back inside
- Swing highs/lows — N-bar fractal
- MSS / BOS — break of structure events
- Displacement — strong impulse bar
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Sequence


@dataclass
class FVG:
    direction: str             # 'bullish' | 'bearish'
    high: float                # top of gap
    low: float                 # bottom of gap
    midpoint: float
    middle_bar_index: int      # index of the displacement (middle) bar
    middle_bar_time: Any       # datetime or whatever the bar carries
    displacement_pts: float    # body size of the middle bar
    mitigated: bool = False
    mitigated_index: int | None = None

    @property
    def gap_size(self) -> float:
        return self.high - self.low


@dataclass
class Sweep:
    direction: str             # 'high_sweep' = swept high, reverses down; 'low_sweep' = swept low, reverses up
    swept_level: float
    sweep_bar_index: int
    sweep_bar_time: Any
    confirmed_close_inside: bool


@dataclass
class StructurePoint:
    kind: str                  # 'swing_high' | 'swing_low'
    price: float
    bar_index: int
    bar_time: Any


@dataclass
class MSSEvent:
    direction: str             # 'bullish' (broke a swing high) | 'bearish' (broke a swing low)
    broken_level: float
    break_bar_index: int
    break_bar_time: Any


# ─── Helpers ──────────────────────────────────────────────────────────
def _bar_at(bars: Sequence[Any], i: int):
    return bars[i]


# ─── FVG detection ────────────────────────────────────────────────────
def find_fvgs(bars: Sequence[Any], min_gap: float = 0.0,
              min_displacement: float = 0.0) -> list[FVG]:
    """Find 3-bar FVGs. Returns oldest-first.

    Bullish FVG: bars[i-1].high < bars[i+1].low → gap [bars[i-1].high, bars[i+1].low]
    Bearish FVG: bars[i-1].low  > bars[i+1].high → gap [bars[i+1].high, bars[i-1].low]

    `min_gap`: minimum gap size (in price points) to qualify
    `min_displacement`: minimum body size (in points) of the middle bar
    """
    out: list[FVG] = []
    for i in range(1, len(bars) - 1):
        prev_b = bars[i - 1]
        mid_b = bars[i]
        next_b = bars[i + 1]
        body = abs(mid_b.close - mid_b.open)
        if body < min_displacement:
            continue
        # Bullish FVG
        if prev_b.high < next_b.low:
            gap_size = next_b.low - prev_b.high
            if gap_size >= min_gap:
                out.append(FVG(
                    direction="bullish",
                    high=next_b.low,
                    low=prev_b.high,
                    midpoint=(next_b.low + prev_b.high) / 2,
                    middle_bar_index=i,
                    middle_bar_time=getattr(mid_b, "time", i),
                    displacement_pts=body,
                ))
        # Bearish FVG
        elif prev_b.low > next_b.high:
            gap_size = prev_b.low - next_b.high
            if gap_size >= min_gap:
                out.append(FVG(
                    direction="bearish",
                    high=prev_b.low,
                    low=next_b.high,
                    midpoint=(prev_b.low + next_b.high) / 2,
                    middle_bar_index=i,
                    middle_bar_time=getattr(mid_b, "time", i),
                    displacement_pts=body,
                ))
    return out


def update_fvg_mitigation(fvg: FVG, bars: Sequence[Any]) -> FVG:
    """Walk forward from the bar after the middle bar; mark mitigated if price wicks into gap."""
    if fvg.mitigated:
        return fvg
    # First mitigation candidate is bar at middle+2 (since middle+1 created the gap)
    start = fvg.middle_bar_index + 2
    for j in range(start, len(bars)):
        b = bars[j]
        if fvg.direction == "bullish":
            # bullish gap is below current price; mitigated if any low touches the high of the gap
            if b.low <= fvg.high:
                fvg.mitigated = True
                fvg.mitigated_index = j
                break
        else:
            if b.high >= fvg.low:
                fvg.mitigated = True
                fvg.mitigated_index = j
                break
    return fvg


def find_unmitigated_fvgs(bars: Sequence[Any], min_gap: float = 0.0,
                          min_displacement: float = 0.0) -> list[FVG]:
    fvgs = find_fvgs(bars, min_gap=min_gap, min_displacement=min_displacement)
    for f in fvgs:
        update_fvg_mitigation(f, bars)
    return [f for f in fvgs if not f.mitigated]


# ─── Swing points (N-bar fractal) ─────────────────────────────────────
def find_swings(bars: Sequence[Any], lookback: int = 2) -> list[StructurePoint]:
    """Detect swing highs/lows. Bar i is a swing high if its high is strictly
    greater than the highs of the `lookback` bars on either side. Same for lows.
    """
    out: list[StructurePoint] = []
    for i in range(lookback, len(bars) - lookback):
        b = bars[i]
        is_high = all(b.high > bars[j].high for j in range(i - lookback, i + lookback + 1) if j != i)
        is_low = all(b.low < bars[j].low for j in range(i - lookback, i + lookback + 1) if j != i)
        if is_high:
            out.append(StructurePoint(
                kind="swing_high", price=b.high, bar_index=i,
                bar_time=getattr(b, "time", i),
            ))
        if is_low:
            out.append(StructurePoint(
                kind="swing_low", price=b.low, bar_index=i,
                bar_time=getattr(b, "time", i),
            ))
    return out


def last_swing(bars: Sequence[Any], kind: str, lookback: int = 2) -> StructurePoint | None:
    """Return the most recent swing of given kind, or None."""
    swings = [s for s in find_swings(bars, lookback) if s.kind == kind]
    return swings[-1] if swings else None


# ─── Liquidity sweeps ─────────────────────────────────────────────────
def find_sweeps(bars: Sequence[Any], lookback: int = 2) -> list[Sweep]:
    """A sweep is when bar[i] takes out the prior swing (high or low) and
    closes back inside the prior range. Returns sweeps oldest-first.
    """
    swings = find_swings(bars, lookback=lookback)
    out: list[Sweep] = []
    if not swings:
        return out

    # Build sorted list of (index, high_price) for swing highs and (index, low_price) for swing lows
    swing_highs = [(s.bar_index, s.price) for s in swings if s.kind == "swing_high"]
    swing_lows = [(s.bar_index, s.price) for s in swings if s.kind == "swing_low"]

    for i, b in enumerate(bars):
        # Sweep prior swing high?
        prior_highs = [(idx, p) for idx, p in swing_highs if idx < i]
        if prior_highs:
            last_idx, last_high = prior_highs[-1]
            if b.high > last_high and b.close < last_high:
                out.append(Sweep(
                    direction="high_sweep",
                    swept_level=last_high,
                    sweep_bar_index=i,
                    sweep_bar_time=getattr(b, "time", i),
                    confirmed_close_inside=True,
                ))
        prior_lows = [(idx, p) for idx, p in swing_lows if idx < i]
        if prior_lows:
            last_idx, last_low = prior_lows[-1]
            if b.low < last_low and b.close > last_low:
                out.append(Sweep(
                    direction="low_sweep",
                    swept_level=last_low,
                    sweep_bar_index=i,
                    sweep_bar_time=getattr(b, "time", i),
                    confirmed_close_inside=True,
                ))
    return out


# ─── Market Structure Shift (MSS) ─────────────────────────────────────
def find_mss_events(bars: Sequence[Any], lookback: int = 2) -> list[MSSEvent]:
    """Detect MSS — a bar that closes beyond a prior swing in the OPPOSITE
    direction of the prevailing trend (bullish MSS = closes above swing high
    after a downtrend leg; bearish MSS = closes below swing low after an
    uptrend leg).

    Simplified Phase-1 version: just emit a MSS event whenever a closed bar
    breaks a prior swing point. Trend context is left to the strategy layer.
    """
    swings = find_swings(bars, lookback=lookback)
    out: list[MSSEvent] = []
    seen_high_breaks: set[int] = set()
    seen_low_breaks: set[int] = set()
    for i, b in enumerate(bars):
        for s in swings:
            if s.bar_index >= i:
                continue
            if s.kind == "swing_high" and b.close > s.price and s.bar_index not in seen_high_breaks:
                out.append(MSSEvent(
                    direction="bullish",
                    broken_level=s.price,
                    break_bar_index=i,
                    break_bar_time=getattr(b, "time", i),
                ))
                seen_high_breaks.add(s.bar_index)
            elif s.kind == "swing_low" and b.close < s.price and s.bar_index not in seen_low_breaks:
                out.append(MSSEvent(
                    direction="bearish",
                    broken_level=s.price,
                    break_bar_index=i,
                    break_bar_time=getattr(b, "time", i),
                ))
                seen_low_breaks.add(s.bar_index)
    return out


# ─── Displacement ─────────────────────────────────────────────────────
def is_displacement_bar(bar: Any, min_body: float, atr: float | None = None,
                        atr_mult: float = 1.5) -> bool:
    """A displacement bar has a body ≥ min_body OR ≥ atr_mult × ATR."""
    body = abs(bar.close - bar.open)
    if body >= min_body:
        return True
    if atr is not None and body >= atr * atr_mult:
        return True
    return False


# ─── ATR (true range smoothing) ───────────────────────────────────────
def atr(bars: Sequence[Any], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        b = bars[i]
        prev = bars[i - 1]
        tr = max(
            b.high - b.low,
            abs(b.high - prev.close),
            abs(b.low - prev.close),
        )
        trs.append(tr)
    # Wilder smoothing
    if len(trs) < period:
        return None
    seed = sum(trs[:period]) / period
    val = seed
    for tr in trs[period:]:
        val = (val * (period - 1) + tr) / period
    return val
