"""Premium/Discount Equilibrium entry — hand-written reference.
Source: ICT Mentorship Month 1 Elements. Lookahead-clean baseline.

Logic: define a rolling 60-bar range. Equilibrium = 50% of range. After an
expansion (close pierces range edge by >0.5*ATR), enter on the FIRST retrace
back to equilibrium during a session. Stop beyond range edge, target opposite
extreme.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from forge.primitives import in_session, empty_signals


RANGE_BARS = 60
EXPANSION_ATR_MULT = 0.5
ATR_PERIOD = 14


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = empty_signals(df)
    h, l, c = df["high"], df["low"], df["close"]

    rng_hi = h.rolling(RANGE_BARS, min_periods=RANGE_BARS).max().shift(1)
    rng_lo = l.rolling(RANGE_BARS, min_periods=RANGE_BARS).min().shift(1)
    eq = (rng_hi + rng_lo) / 2

    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD, min_periods=1).mean()

    bull_expansion = (c > rng_hi + EXPANSION_ATR_MULT * atr)
    bear_expansion = (c < rng_lo - EXPANSION_ATR_MULT * atr)

    bull_state = bull_expansion.rolling(20, min_periods=1).max().fillna(0).astype(bool)
    bear_state = bear_expansion.rolling(20, min_periods=1).max().fillna(0).astype(bool)

    crosses_eq_down = (l <= eq) & (l.shift(1) > eq)
    crosses_eq_up   = (h >= eq) & (h.shift(1) < eq)

    session = in_session(df, "ny_am_kz") | in_session(df, "ny_pm") | in_session(df, "london_open")

    bull = bull_state & crosses_eq_down & session & ~bull_expansion
    bear = bear_state & crosses_eq_up   & session & ~bear_expansion

    bull_entry = eq.where(bull)
    bull_stop  = rng_lo.where(bull)
    bull_risk  = bull_entry - bull_stop
    bull_tp    = rng_hi.where(bull)

    bear_entry = eq.where(bear)
    bear_stop  = rng_hi.where(bear)
    bear_risk  = bear_stop - bear_entry
    bear_tp    = rng_lo.where(bear)

    valid_bull = bull & (bull_risk > 0) & ((bull_tp - bull_entry) >= bull_risk)
    valid_bear = bear & (bear_risk > 0) & ((bear_entry - bear_tp) >= bear_risk)

    out.loc[valid_bull, "signal"] = 1
    out.loc[valid_bull, "entry"]  = bull_entry[valid_bull]
    out.loc[valid_bull, "stop"]   = bull_stop[valid_bull]
    out.loc[valid_bull, "target"] = bull_tp[valid_bull]

    out.loc[valid_bear, "signal"] = -1
    out.loc[valid_bear, "entry"]  = bear_entry[valid_bear]
    out.loc[valid_bear, "stop"]   = bear_stop[valid_bear]
    out.loc[valid_bear, "target"] = bear_tp[valid_bear]

    return out
