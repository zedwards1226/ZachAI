"""
ORB No-ATR — same rules as orb_classic but the ATR range filter is REMOVED.

Why this exists:
  The live TradingView Pine strategy ("NQ ORB Strategy" v29) prints 93 trades,
  61% WR, +$1920 over Feb 22-Apr 20. My orb_classic.py port prints 11 trades,
  27% WR, -$4248 over the same window. The 30-60% ATR filter in config.py is
  the prime suspect — it killed 30 of 45 trading days in the current low-vol
  regime. This variant tests the breakout edge with the filter removed.

  If this prints ~93 trades and roughly matches TV — the ATR filter was the
  only meaningful divergence between the Python and Pine versions.

  If trade count matches but win rate doesn't — the difference is in
  stop/target geometry or the time-exit handling.

Run:  python -m forge.judge --strategy orb_no_atr
"""
from __future__ import annotations
from datetime import time
import numpy as np
import pandas as pd

ORB_START = time(9, 30)
ORB_END = time(9, 45)
SESSION_END = time(15, 0)
STOP_EXTENSION_MULT = 1.25
TARGET_MULT = 1.5


def _et_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    return df.index.tz_convert("US/Eastern") if df.index.tz is not None else df.index


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    out = pd.DataFrame({
        "signal": np.zeros(n, dtype=int),
        "entry":  np.full(n, np.nan),
        "stop":   np.full(n, np.nan),
        "target": np.full(n, np.nan),
    }, index=df.index)

    et = _et_index(df)
    dates = pd.Series(et.date, index=df.index)
    times = pd.Series(et.time, index=df.index)

    for date, day_idx in dates.groupby(dates).groups.items():
        day_df = df.loc[day_idx]
        day_times = times.loc[day_idx]

        orb_mask = (day_times >= ORB_START) & (day_times < ORB_END)
        orb_bars = day_df[orb_mask]
        if len(orb_bars) < 2:
            continue
        orb_high = float(orb_bars["high"].max())
        orb_low  = float(orb_bars["low"].min())
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            continue

        post_mask = (day_times >= ORB_END) & (day_times < SESSION_END)
        post = day_df[post_mask]
        if post.empty:
            continue

        for ts, bar in post.iterrows():
            c = float(bar["close"])
            if c > orb_high:
                entry = c
                stop = orb_low - STOP_EXTENSION_MULT * orb_range
                target = entry + TARGET_MULT * orb_range
                out.at[ts, "signal"] = 1
                out.at[ts, "entry"]  = entry
                out.at[ts, "stop"]   = stop
                out.at[ts, "target"] = target
                break
            if c < orb_low:
                entry = c
                stop = orb_high + STOP_EXTENSION_MULT * orb_range
                target = entry - TARGET_MULT * orb_range
                out.at[ts, "signal"] = -1
                out.at[ts, "entry"]  = entry
                out.at[ts, "stop"]   = stop
                out.at[ts, "target"] = target
                break

    return out
