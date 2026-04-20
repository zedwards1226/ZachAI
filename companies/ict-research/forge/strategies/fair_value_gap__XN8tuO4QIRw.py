# ICT 2023 PM Session Fair Value Gap from ICT Mentorship 2023 Ep 01
from __future__ import annotations
import pandas as pd
import numpy as np
from forge.primitives import (
    in_session,
    detect_fvg,
    detect_order_block,
    market_structure_shift,
    previous_day_levels,
    empty_signals,
    liquidity_sweep_high,
    liquidity_sweep_low,
    swing_high,
    swing_low
)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    # Assume HTF data is available for previous day levels and higher timeframe FVGs
    out = empty_signals(df)
    fvg = detect_fvg(df)
    pd_levels = previous_day_levels(df)
    mss = market_structure_shift(df)
    session_filter = in_session(df, 'ny_pm')
    sweet_spot_filter = (df.index.hour == 15) & ((df.index.minute >= 15) & (df.index.minute <= 45))
    fvg_long = fvg['bull_fvg']
    fvg_short = fvg['bear_fvg']
    fvg_long_low = fvg['bull_fvg_low']
    fvg_long_high = fvg['bull_fvg_high']
    fvg_short_low = fvg['bear_fvg_low']
    fvg_short_high = fvg['bear_fvg_high']
    
    # Entry conditions
    long_entry = (fvg_long) & (session_filter) & (sweet_spot_filter) & (df['close'] > fvg_long_low) & (df['close'] < fvg_long_high)
    short_entry = (fvg_short) & (session_filter) & (sweet_spot_filter) & (df['close'] > fvg_short_low) & (df['close'] < fvg_short_high)
    
    # Confirmation
    long_confirmation = (mss['bull_mss']) & (df['close'] > fvg_long_low) & (df['close'] < fvg_long_high)
    short_confirmation = (mss['bear_mss']) & (df['close'] > fvg_short_low) & (df['close'] < fvg_short_high)
    
    # Invalidation
    invalidation = (df.index.hour == 15) & (df.index.minute >= 50)
    
    # Stop loss
    long_stop = fvg_long_low
    short_stop = fvg_short_high
    
    # Take profit
    long_target = df['close'] + (df['close'] - long_stop) * 2
    short_target = df['close'] - (short_stop - df['close']) * 2
    
    # Set signals
    out.loc[long_entry & long_confirmation & ~invalidation, 'signal'] = 1
    out.loc[short_entry & short_confirmation & ~invalidation, 'signal'] = -1
    out.loc[out['signal'] == 1, 'entry'] = df['close']
    out.loc[out['signal'] == -1, 'entry'] = df['close']
    out.loc[out['signal'] == 1, 'stop'] = long_stop
    out.loc[out['signal'] == -1, 'stop'] = short_stop
    out.loc[out['signal'] == 1, 'target'] = long_target
    out.loc[out['signal'] == -1, 'target'] = short_target
    
    return out