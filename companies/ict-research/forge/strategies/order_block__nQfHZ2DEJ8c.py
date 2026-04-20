"""2022 Mentorship Order Block (Change in State of Delivery) from 2022 ICT Mentorship Episode 3"""
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
    liquidity_sweep_low
)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    # Assumption: HTF liquidity is proxied by Previous Day High/Low and recent 15-bar swings.
    out = empty_signals(df)
    
    # 1. Primitives
    pdl_levels = previous_day_levels(df)
    pdh = pdl_levels['pdh']
    pdl = pdl_levels['pdl']
    
    mss = market_structure_shift(df, lookback=5)
    fvg = detect_fvg(df)
    ob = detect_order_block(df, displacement_atr_mult=1.2)
    
    # Session Filters
    london = in_session(df, 'london_open')
    ny_am = in_session(df, 'ny_am')
    ny_pm = in_session(df, 'ny_pm')
    asia = in_session(df, 'asia')
    valid_session = london | ny_am | ny_pm | asia
    
    # Liquidity Sweeps
    sweep_low = liquidity_sweep_low(df, pdl) | liquidity_sweep_low(df, df['low'].shift(1).rolling(15).min())
    sweep_high = liquidity_sweep_high(df, pdh) | liquidity_sweep_high(df, df['high'].shift(1).rolling(15).max())
    
    # Track state for sweep occurrence (within last 20 bars)
    recent_sweep_low = sweep_low.rolling(window=20, min_periods=1).max().fillna(0).astype(bool)
    recent_sweep_high = sweep_high.rolling(window=20, min_periods=1).max().fillna(0).astype(bool)
    
    # Confirmation: FVG exists within the last 3 bars of an MSS
    recent_bull_fvg = fvg['bull_fvg'].rolling(window=3, min_periods=1).max().fillna(0).astype(bool)
    recent_bear_fvg = fvg['bear_fvg'].rolling(window=3, min_periods=1).max().fillna(0).astype(bool)
    
    # Logic for Longs
    # 1. Recent Sweep of Sell-side Liquidity
    # 2. Bullish MSS
    # 3. Bullish FVG for displacement confirmation
    # 4. Identify the OB that initiated the move
    bull_setup = (
        valid_session & 
        recent_sweep_low & 
        mss['bull_mss'] & 
        recent_bull_fvg
    )
    
    # Logic for Shorts
    # 1. Recent Sweep of Buy-side Liquidity
    # 2. Bearish MSS
    # 3. Bearish FVG for displacement confirmation
    # 4. Identify the OB that initiated the move
    bear_setup = (
        valid_session & 
        recent_sweep_high & 
        mss['bear_mss'] & 
        recent_bear_fvg
    )
    
    # Iterate to find the specific OB Open (Change in State of Delivery)
    # We look back from the MSS bar to find the most recent OB candle
    for i in range(1, len(df)):
        if bull_setup.iloc[i]:
            # Look back up to 10 bars for the OB candle
            lookback_range = range(i, max(0, i-10), -1)
            found_ob = False
            for j in lookback_range:
                if ob['bull_ob'].iloc[j]:
                    # Entry is the Open of the OB candle (Change in State of Delivery)
                    entry_price = df['open'].iloc[j]
                    stop_price = ob['bull_ob_low'].iloc[j]
                    
                    # Ensure entry is valid (price hasn't run too far)
                    if df['close'].iloc[i] > entry_price:
                        risk = entry_price - stop_price
                        if risk > 0:
                            out.loc[df.index[i], 'signal'] = 1
                            out.loc[df.index[i], 'entry'] = entry_price
                            out.loc[df.index[i], 'stop'] = stop_price
                            out.loc[df.index[i], 'target'] = entry_price + (risk * 2.0) # Default 1:2 RR
                            found_ob = True
                            break
            if found_ob: continue

        if bear_setup.iloc[i]:
            # Look back up to 10 bars for the OB candle
            lookback_range = range(i, max(0, i-10), -1)
            found_ob = False
            for j in lookback_range:
                if ob['bear_ob'].iloc[j]:
                    # Entry is the Open of the OB candle
                    entry_price = df['open'].iloc[j]
                    stop_price = ob['bear_ob_high'].iloc[j]
                    
                    # Ensure entry is valid
                    if df['close'].iloc[i] < entry_price:
                        risk = stop_price - entry_price
                        if risk > 0:
                            out.loc[df.index[i], 'signal'] = -1
                            out.loc[df.index[i], 'entry'] = entry_price
                            out.loc[df.index[i], 'stop'] = stop_price
                            out.loc[df.index[i], 'target'] = entry_price - (risk * 2.0) # Default 1:2 RR
                            found_ob = True
                            break
            if found_ob: continue

    return out