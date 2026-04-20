"""
ICT primitives — shared building blocks every strategy in forge/strategies/
imports. Keep these deterministic, vectorized where possible, and tested.

Conventions:
- df has columns ['open', 'high', 'low', 'close', 'volume'] and a tz-aware
  DatetimeIndex in US/Eastern (ET).
- Functions return new Series/DataFrames aligned to df's index. Boolean masks
  for "event happened on this bar" semantics. Prices are NaN where event
  didn't happen.
- All windows/lookbacks are bar-count, never wall-clock seconds.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


# -------------------- session windows --------------------
# All times in US/Eastern. Inclusive start, exclusive end.
SESSIONS = {
    "asia":         ("19:00", "21:00"),
    "london_open":  ("02:00", "05:00"),
    "ny_am":        ("09:30", "11:00"),
    "ny_am_kz":     ("08:30", "11:00"),  # ICT NY AM killzone
    "ny_lunch":     ("12:00", "13:00"),
    "ny_pm":        ("13:30", "16:00"),
    "silver_bullet_am": ("10:00", "11:00"),
    "silver_bullet_pm": ("14:00", "15:00"),
}


def in_session(df: pd.DataFrame, session: str) -> pd.Series:
    """Boolean mask of rows inside the named session."""
    if session not in SESSIONS:
        raise ValueError(f"unknown session {session!r}; have {list(SESSIONS)}")
    start, end = SESSIONS[session]
    times = df.index.tz_convert("US/Eastern").time if df.index.tz is not None else df.index.time
    s_h, s_m = map(int, start.split(":"))
    e_h, e_m = map(int, end.split(":"))
    from datetime import time as t
    s, e = t(s_h, s_m), t(e_h, e_m)
    return pd.Series([s <= x < e for x in times], index=df.index)


# -------------------- swing points --------------------
def swing_high(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    """Bar i is a swing high if its high > highs of `lookback` bars on each side."""
    h = df["high"]
    out = pd.Series(False, index=df.index)
    for i in range(lookback, len(df) - lookback):
        if h.iloc[i] == h.iloc[i - lookback : i + lookback + 1].max() and \
           h.iloc[i] > h.iloc[i - lookback : i].max() and \
           h.iloc[i] > h.iloc[i + 1 : i + lookback + 1].max():
            out.iloc[i] = True
    return out


def swing_low(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    l = df["low"]
    out = pd.Series(False, index=df.index)
    for i in range(lookback, len(df) - lookback):
        if l.iloc[i] == l.iloc[i - lookback : i + lookback + 1].min() and \
           l.iloc[i] < l.iloc[i - lookback : i].min() and \
           l.iloc[i] < l.iloc[i + 1 : i + lookback + 1].min():
            out.iloc[i] = True
    return out


# -------------------- FVG (Fair Value Gap) --------------------
def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    A 3-candle FVG forms on candle[i] when there's a gap between candle[i-2]
    and candle[i]. Bullish FVG: low[i] > high[i-2]. Bearish FVG: high[i] < low[i-2].
    Gap range = (high[i-2], low[i]) bullish, or (high[i], low[i-2]) bearish.

    Returns DataFrame indexed like df with columns:
        bull_fvg (bool), bull_fvg_low, bull_fvg_high  -- lower/upper edge of bull gap
        bear_fvg (bool), bear_fvg_low, bear_fvg_high
    """
    h, l = df["high"], df["low"]
    bull = l > h.shift(2)
    bear = h < l.shift(2)
    out = pd.DataFrame({
        "bull_fvg": bull.fillna(False),
        "bull_fvg_low": h.shift(2).where(bull),     # gap bottom
        "bull_fvg_high": l.where(bull),              # gap top
        "bear_fvg": bear.fillna(False),
        "bear_fvg_low": h.where(bear),               # gap bottom
        "bear_fvg_high": l.shift(2).where(bear),     # gap top
    }, index=df.index)
    return out


# -------------------- Order Block --------------------
def detect_order_block(df: pd.DataFrame, displacement_atr_mult: float = 1.5,
                       atr_period: int = 14) -> pd.DataFrame:
    """
    Bullish OB: last down-close candle before a strong up-move (displacement).
    Bearish OB: last up-close candle before a strong down-move.

    Displacement = current-bar range > displacement_atr_mult * ATR.

    Lookahead-safe: an OB is CONFIRMED on the displacement bar (the bar AFTER
    the OB candle). Therefore bull_ob.iloc[i]==True means "bar i-1 was an OB,
    confirmed by displacement on bar i." bull_ob_low/high.iloc[i] = low/high
    of bar i-1. Use these at bar i without peeking forward.

    Returns DataFrame indexed like df with columns:
        bull_ob (bool), bull_ob_low, bull_ob_high
        bear_ob (bool), bear_ob_low, bear_ob_high
    """
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period, min_periods=1).mean()

    cur_range = h - l
    displaced = cur_range > (displacement_atr_mult * atr)
    cur_up = c > o
    cur_down = c < o
    prev_down_close = c.shift(1) < o.shift(1)
    prev_up_close   = c.shift(1) > o.shift(1)

    bull_ob = prev_down_close & displaced & cur_up
    bear_ob = prev_up_close   & displaced & cur_down

    out = pd.DataFrame({
        "bull_ob": bull_ob.fillna(False),
        "bull_ob_low":  l.shift(1).where(bull_ob),
        "bull_ob_high": h.shift(1).where(bull_ob),
        "bear_ob": bear_ob.fillna(False),
        "bear_ob_low":  l.shift(1).where(bear_ob),
        "bear_ob_high": h.shift(1).where(bear_ob),
    }, index=df.index)
    return out


# -------------------- Liquidity sweep --------------------
def liquidity_sweep_high(df: pd.DataFrame, level: pd.Series) -> pd.Series:
    """True on bars where high pierces `level` but close stays below it."""
    return (df["high"] > level) & (df["close"] < level)


def liquidity_sweep_low(df: pd.DataFrame, level: pd.Series) -> pd.Series:
    return (df["low"] < level) & (df["close"] > level)


# -------------------- Market Structure Shift --------------------
def market_structure_shift(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """
    Bull MSS: close breaks above the most recent swing high (after a downtrend).
    Bear MSS: close breaks below the most recent swing low (after an uptrend).

    Returns columns: bull_mss (bool), bear_mss (bool).
    Simple flavor: any close above the rolling swing-high level counts.
    """
    sh = swing_high(df, lookback)
    sl = swing_low(df, lookback)
    last_sh = df["high"].where(sh).ffill()
    last_sl = df["low"].where(sl).ffill()
    bull_mss = (df["close"] > last_sh.shift()) & (df["close"].shift() <= last_sh.shift())
    bear_mss = (df["close"] < last_sl.shift()) & (df["close"].shift() >= last_sl.shift())
    return pd.DataFrame({
        "bull_mss": bull_mss.fillna(False),
        "bear_mss": bear_mss.fillna(False),
    }, index=df.index)


# -------------------- Previous day high/low --------------------
def previous_day_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-filled previous calendar day's high/low onto each intraday bar."""
    daily = df.resample("1D").agg({"high": "max", "low": "min"}).shift(1)
    pdh = daily["high"].reindex(df.index, method="ffill")
    pdl = daily["low"].reindex(df.index, method="ffill")
    return pd.DataFrame({"pdh": pdh, "pdl": pdl}, index=df.index)


# -------------------- Empty signal frame --------------------
def empty_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Strategies must return df + these columns. Use this as a starting point."""
    return pd.DataFrame({
        "signal": 0,
        "entry": np.nan,
        "stop": np.nan,
        "target": np.nan,
    }, index=df.index)
