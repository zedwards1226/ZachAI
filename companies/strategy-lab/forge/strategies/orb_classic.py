"""
ORB Classic — faithful port of the live ORB bot's MECHANICAL rules.

Source of truth: C:\\ZachAI\\trading\\config.py (ORB_MINUTES=15, stops, targets,
ATR filter). Live bot adds a multi-agent context layer (VIX, news, RVOL, sweep,
HTF bias, level proximity) on top of these mechanics. This backtest tests the
mechanical edge ALONE — no scoring, no agent context. If the mechanics aren't
profitable on their own, the agent layer must carry all the weight.

Rules (mirrors trading/config.py):
  ORB window:        9:30-9:45 ET (15-min opening range)
  Entry trigger:     first 5-min bar that CLOSES outside the range
  ATR filter:        ORB range must be 30%-60% of 14-day ATR (else skip day)
  Stop:              1.25 × ORB range beyond opposite boundary
  Target:            1.5 × ORB range from entry (single-target version of the
                     bot's 0.5×/1.5× partial-close ladder)
  Direction:         long on upside break, short on downside break
  Max:               1 trade per day (live bot allows 3, but the simulator is
                     1-position-at-a-time and most ORB days have 1 valid break)

Simplifications vs live bot (HONEST disclosure):
  - No partial close at 0.5× (lab can't model partials with one stop/target)
  - No 120-min time exit, no 15:00 hard close (lab simulator only exits on
    stop/target/EOD-of-dataset). Most trades resolve same-session due to the
    aggressive target.
  - No multi-agent score gating — every valid breakout fires
  - No VIX/news/RVOL filters
  - No second-break logic (failed-then-rebreak)

Run:  python -m forge.judge --strategy orb_classic
"""
from __future__ import annotations
from datetime import time
import numpy as np
import pandas as pd

# --- live bot constants (mirror trading/config.py) ---
ORB_MINUTES = 15
ORB_START = time(9, 30)
ORB_END = time(9, 45)
SESSION_END = time(15, 0)        # don't open new trades after this
STOP_EXTENSION_MULT = 1.25
TARGET_MULT = 1.5
ATR_LOOKBACK_DAYS = 14
ORB_ATR_MIN_PCT = 0.30
ORB_ATR_MAX_PCT = 0.60


def _et_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    return df.index.tz_convert("US/Eastern") if df.index.tz is not None else df.index


def _daily_atr(df: pd.DataFrame, lookback: int = ATR_LOOKBACK_DAYS) -> pd.Series:
    """Daily True Range, rolling mean. Returns one value per session date."""
    et = _et_index(df)
    daily = pd.DataFrame({
        "high": df["high"].groupby(et.date).max(),
        "low":  df["low"].groupby(et.date).min(),
        "close": df["close"].groupby(et.date).last(),
    })
    prev_close = daily["close"].shift(1)
    tr = pd.concat([
        daily["high"] - daily["low"],
        (daily["high"] - prev_close).abs(),
        (daily["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(lookback, min_periods=5).mean().shift(1)  # shift 1 = use yesterday's ATR


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
    atr_by_date = _daily_atr(df)

    for date, day_idx in dates.groupby(dates).groups.items():
        day_df = df.loc[day_idx]
        day_times = times.loc[day_idx]

        # --- capture the ORB (9:30 - 9:45 ET) ---
        orb_mask = (day_times >= ORB_START) & (day_times < ORB_END)
        orb_bars = day_df[orb_mask]
        if len(orb_bars) < 2:
            continue
        orb_high = float(orb_bars["high"].max())
        orb_low  = float(orb_bars["low"].min())
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            continue

        # --- ATR filter (30%-60% of 14d ATR) ---
        atr = atr_by_date.get(date, np.nan)
        if not np.isfinite(atr) or atr <= 0:
            continue
        ratio = orb_range / atr
        if ratio < ORB_ATR_MIN_PCT or ratio > ORB_ATR_MAX_PCT:
            continue

        # --- find first 5m close outside the range, after 9:45, before 15:00 ---
        post_mask = (day_times >= ORB_END) & (day_times < SESSION_END)
        post = day_df[post_mask]
        if post.empty:
            continue

        for ts, bar in post.iterrows():
            c = float(bar["close"])
            if c > orb_high:
                # long break
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
