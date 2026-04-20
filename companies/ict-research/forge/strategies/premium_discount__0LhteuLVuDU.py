"""premium_discount from ICT Mentorship Core Content - Month 1 - Elements Of A Trade Setup"""
from __future__ import annotations
import pandas as pd
import numpy as np
from forge.primitives import (
    empty_signals,
    market_structure_shift,
    detect_order_block,
    swing_high,
    swing_low
)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    # HTF context is derived from the local consolidation range and expansion on the provided timeframe.
    out = empty_signals(df)
    
    mss = market_structure_shift(df, lookback=3)
    obs = detect_order_block(df, displacement_atr_mult=1.5, atr_period=14)
    sh = swing_high(df, lookback=3)
    sl = swing_low(df, lookback=3)
    
    # Track the most recent swing levels to define the "Consolidation Range"
    last_sh_val = df['high'].where(sh).ffill()
    last_sl_val = df['low'].where(sl).ffill()
    
    # State variables for the setup state machine
    pending_signal = 0  # 1 for long, -1 for short
    setup_limit = np.nan
    setup_stop = np.nan
    setup_target = np.nan
    setup_invalidation = np.nan
    
    # To prevent pyramiding and track active trades
    in_position = False
    
    # Convert to numpy for faster iteration where state is required
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    
    bull_mss = mss['bull_mss'].values
    bear_mss = mss['bear_mss'].values
    
    bull_ob = obs['bull_ob'].values
    bull_ob_low = obs['bull_ob_low'].values
    bull_ob_high = obs['bull_ob_high'].values
    
    bear_ob = obs['bear_ob'].values
    bear_ob_low = obs['bear_ob_low'].values
    bear_ob_high = obs['bear_ob_high'].values
    
    l_sh = last_sh_val.values
    l_sl = last_sl_val.values

    for i in range(1, len(df)):
        # 1. Check for Expansion / MSS to establish bias and setup
        if not in_position and pending_signal == 0:
            if bull_mss[i]:
                # Expansion Up: Range is from the last swing low to current high
                range_low = l_sl[i]
                range_high = highs[i]
                equilibrium = (range_high + range_low) / 2
                
                # Look for the OB created during this expansion
                # We check the current or very recent OB
                if bull_ob[i]:
                    pending_signal = 1
                    # Entry at Equilibrium or OB High, whichever is higher (Premium/Discount logic)
                    setup_limit = max(equilibrium, bull_ob_high[i])
                    setup_stop = bull_ob_low[i]
                    setup_target = range_high
                    setup_invalidation = range_low
                
            elif bear_mss[i]:
                # Expansion Down: Range is from the last swing high to current low
                range_high = l_sh[i]
                range_low = lows[i]
                equilibrium = (range_high + range_low) / 2
                
                if bear_ob[i]:
                    pending_signal = -1
                    # Entry at Equilibrium or OB Low, whichever is lower
                    setup_limit = min(equilibrium, bear_ob_low[i])
                    setup_stop = bear_ob_high[i]
                    setup_target = range_low
                    setup_invalidation = range_high

        # 2. Check for Entry if a setup is pending
        elif pending_signal != 0:
            if pending_signal == 1:
                # Invalidation: Price trades through the consolidation range bottom
                if lows[i] < setup_invalidation:
                    pending_signal = 0
                # Entry: Price touches the limit (OB or Equilibrium)
                elif lows[i] <= setup_limit:
                    out.iloc[i, out.columns.get_loc('signal')] = 1
                    out.iloc[i, out.columns.get_loc('entry')] = setup_limit
                    out.iloc[i, out.columns.get_loc('stop')] = setup_stop
                    out.iloc[i, out.columns.get_loc('target')] = setup_target
                    in_position = True
                    pending_signal = 0
            
            elif pending_signal == -1:
                # Invalidation: Price trades through the consolidation range top
                if highs[i] > setup_invalidation:
                    pending_signal = 0
                # Entry: Price touches the limit
                elif highs[i] >= setup_limit:
                    out.iloc[i, out.columns.get_loc('signal')] = -1
                    out.iloc[i, out.columns.get_loc('entry')] = setup_limit
                    out.iloc[i, out.columns.get_loc('stop')] = setup_stop
                    out.iloc[i, out.columns.get_loc('target')] = setup_target
                    in_position = True
                    pending_signal = 0

        # 3. Manage Position (Simple logic to reset in_position for the next setup)
        # In a real backtest, the engine handles the exit. 
        # Here we just need to know when we can look for a NEW setup.
        if in_position:
            # If price hits target or stop, we allow new setups
            # This is a simplification for the signal generator
            if (highs[i] >= setup_target if setup_target > setup_limit else lows[i] <= setup_target) or \
               (lows[i] <= setup_stop if setup_target > setup_limit else highs[i] >= setup_stop):
                in_position = False

    return out