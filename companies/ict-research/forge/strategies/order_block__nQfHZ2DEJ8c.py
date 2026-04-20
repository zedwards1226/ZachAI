"""2022 Mentorship Order Block (Change in State of Delivery) — hand-written reference.
Source: 2022 ICT Mentorship Episode 3. Lookahead-clean baseline."""
from __future__ import annotations
import pandas as pd
import numpy as np
from forge.primitives import (
    in_session,
    detect_order_block,
    empty_signals,
)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = empty_signals(df)

    ob = detect_order_block(df, displacement_atr_mult=1.5, atr_period=14)
    session = in_session(df, "ny_am_kz") | in_session(df, "london_open")

    bull = ob["bull_ob"] & session
    bear = ob["bear_ob"] & session

    close = df["close"]

    bull_entry = close.where(bull)
    bull_stop  = ob["bull_ob_low"].where(bull)
    bull_risk  = bull_entry - bull_stop
    bull_tp    = bull_entry + bull_risk * 2.0

    bear_entry = close.where(bear)
    bear_stop  = ob["bear_ob_high"].where(bear)
    bear_risk  = bear_stop - bear_entry
    bear_tp    = bear_entry - bear_risk * 2.0

    valid_bull = bull & (bull_risk > 0)
    valid_bear = bear & (bear_risk > 0)

    out.loc[valid_bull, "signal"] = 1
    out.loc[valid_bull, "entry"]  = bull_entry[valid_bull]
    out.loc[valid_bull, "stop"]   = bull_stop[valid_bull]
    out.loc[valid_bull, "target"] = bull_tp[valid_bull]

    out.loc[valid_bear, "signal"] = -1
    out.loc[valid_bear, "entry"]  = bear_entry[valid_bear]
    out.loc[valid_bear, "stop"]   = bear_stop[valid_bear]
    out.loc[valid_bear, "target"] = bear_tp[valid_bear]

    return out
