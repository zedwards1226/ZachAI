"""
ICT primitives — public API for forge/strategies/.

Backed by `smartmoneyconcepts` (joshyattridge) for FVG / OB / swings / BOS
detection, with our own thin wrappers that:
  - keep the public API stable (in_session, detect_fvg, detect_order_block,
    market_structure_shift, swing_high/low, previous_day_levels, empty_signals,
    liquidity_sweep_high/low)
  - strip future-info columns (MitigatedIndex, BrokenIndex) so strategies cannot
    accidentally cheat
  - shift swing-derived signals forward by `swing_length` bars so they are
    "confirmed" only after enough future bars have passed (lookahead-safe)

Conventions:
  - df has columns ['open','high','low','close','volume'] (lowercase) and a
    tz-aware DatetimeIndex in US/Eastern.
  - Functions return Series/DataFrames aligned to df's index. Booleans are
    "event happened on this bar"; prices are NaN where the event didn't happen.
  - All windows/lookbacks are bar-count, never wall-clock seconds.
"""

from __future__ import annotations

import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
from smartmoneyconcepts import smc


# -------------------- session windows --------------------
SESSIONS = {
    "asia":             ("19:00", "21:00"),
    "london_open":      ("02:00", "05:00"),
    "ny_am":            ("09:30", "11:00"),
    "ny_am_kz":         ("08:30", "11:00"),
    "ny_lunch":         ("12:00", "13:00"),
    "ny_pm":            ("13:30", "16:00"),
    "silver_bullet_am": ("10:00", "11:00"),
    "silver_bullet_pm": ("14:00", "15:00"),
}


def in_session(df: pd.DataFrame, session: str) -> pd.Series:
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
def _align(out: pd.DataFrame | pd.Series, df: pd.DataFrame) -> pd.DataFrame | pd.Series:
    """smc returns int-indexed frames; reattach df's DatetimeIndex."""
    out = out.copy()
    out.index = df.index
    return out


def _swings(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """smc swings, shifted forward by `lookback` bars so they are lookahead-safe."""
    shl = _align(smc.swing_highs_lows(df, swing_length=lookback), df)
    return shl.shift(lookback)


def swing_high(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    """True on bar where a confirmed swing high was identified `lookback` bars ago."""
    shl = _swings(df, lookback)
    return (shl["HighLow"] == 1).fillna(False)


def swing_low(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    shl = _swings(df, lookback)
    return (shl["HighLow"] == -1).fillna(False)


# -------------------- FVG --------------------
def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """3-candle FVG: bull when low[i] > high[i-2]; bear when high[i] < low[i-2].

    Lookahead-safe: smc.fvg detects on candle i using candles i-2..i, then we
    drop MitigatedIndex (future). Returns:
        bull_fvg / bull_fvg_low / bull_fvg_high
        bear_fvg / bear_fvg_low / bear_fvg_high
    """
    f = _align(smc.fvg(df, join_consecutive=False), df)
    bull = (f["FVG"] == 1).fillna(False)
    bear = (f["FVG"] == -1).fillna(False)
    return pd.DataFrame({
        "bull_fvg":      bull,
        "bull_fvg_low":  f["Bottom"].where(bull),
        "bull_fvg_high": f["Top"].where(bull),
        "bear_fvg":      bear,
        "bear_fvg_low":  f["Bottom"].where(bear),
        "bear_fvg_high": f["Top"].where(bear),
    }, index=df.index)


# -------------------- Order Block --------------------
def detect_order_block(df: pd.DataFrame, displacement_atr_mult: float = 1.5,
                       atr_period: int = 14) -> pd.DataFrame:
    """OB anchored to swings via smc.ob, shifted by swing_length so lookahead-safe.

    Returns:
        bull_ob / bull_ob_low / bull_ob_high
        bear_ob / bear_ob_low / bear_ob_high
    `displacement_atr_mult` and `atr_period` kept for API compat (smc.ob handles
    its own displacement logic via the swing structure).
    """
    swing_length = 10
    shl = smc.swing_highs_lows(df, swing_length=swing_length)
    o = _align(smc.ob(df, shl, close_mitigation=False), df).shift(swing_length)
    bull = (o["OB"] == 1).fillna(False)
    bear = (o["OB"] == -1).fillna(False)
    return pd.DataFrame({
        "bull_ob":      bull,
        "bull_ob_low":  o["Bottom"].where(bull),
        "bull_ob_high": o["Top"].where(bull),
        "bear_ob":      bear,
        "bear_ob_low":  o["Bottom"].where(bear),
        "bear_ob_high": o["Top"].where(bear),
    }, index=df.index)


# -------------------- Liquidity sweep --------------------
def liquidity_sweep_high(df: pd.DataFrame, level: pd.Series) -> pd.Series:
    return (df["high"] > level) & (df["close"] < level)


def liquidity_sweep_low(df: pd.DataFrame, level: pd.Series) -> pd.Series:
    return (df["low"] < level) & (df["close"] > level)


# -------------------- MSS (BOS / CHoCH) --------------------
def market_structure_shift(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """smc.bos_choch wrapped to our public columns. CHOCH==reversal MSS,
    BOS==continuation. We expose both as 'mss' since most ICT setups treat
    either as a structural break."""
    shl = smc.swing_highs_lows(df, swing_length=lookback)
    bc = _align(smc.bos_choch(df, shl, close_break=True), df).shift(lookback)
    bull = ((bc["BOS"] == 1) | (bc["CHOCH"] == 1)).fillna(False)
    bear = ((bc["BOS"] == -1) | (bc["CHOCH"] == -1)).fillna(False)
    return pd.DataFrame({
        "bull_mss": bull,
        "bear_mss": bear,
    }, index=df.index)


# -------------------- Previous day levels --------------------
def previous_day_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-filled previous calendar day's high/low onto each intraday bar."""
    daily = df.resample("1D").agg({"high": "max", "low": "min"}).shift(1)
    pdh = daily["high"].reindex(df.index, method="ffill")
    pdl = daily["low"].reindex(df.index, method="ffill")
    return pd.DataFrame({"pdh": pdh, "pdl": pdl}, index=df.index)


# -------------------- Empty signal frame --------------------
def empty_signals(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "signal": 0,
        "entry":  np.nan,
        "stop":   np.nan,
        "target": np.nan,
    }, index=df.index)
