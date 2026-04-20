"""
Sanity strategy: random coin-flip signals with a fixed risk:reward ratio.

Observed verdict on MNQ 5m / 60d (2026-04-20 baseline):
  trades     = 250
  winrate    = 29.2%   (NOT 50% — random shorts get crushed in MNQ uptrend)
  avg_win    = $6.50   (5 pts × $2 − $3.50 cost)
  avg_loss   = -$13.50 (-5 pts × $2 − $3.50 cost)
  expectancy = -$7.66/trade
  net        = -$1,915.00
  cost drag per trade = exactly $3.50 (slippage $2 + commission $1.50) ✓
  PROMOTED = False (no edge, by design)

This validates: (a) costs are charged per trade, (b) the simulator handles
both sides correctly. If avg_win or avg_loss drifts from ±$5pt × $2 − $3.50,
the cost or fill math has a bug.

The negative expectancy here is the cost drag. Random signals + 1:1 R:R in a
trending market also creates side-asymmetric outcomes (shorts stop out more
than longs in an uptrend) — that's a real market property, not a lab bug.

Run:  python -m forge.judge --strategy _test_random
"""
from __future__ import annotations
import numpy as np
import pandas as pd


SEED = 42
SIGNAL_PROB = 0.02     # ~1 signal every 50 bars (gives ~100+ trades on 60d/5m)
RISK_POINTS = 5.0      # 5 points stop = $10 risk per MNQ contract
REWARD_POINTS = 5.0    # 1:1 R:R — random signals + 1:1 = pure cost-drag test


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    n = len(df)
    close = df["close"].to_numpy()

    signals = np.zeros(n, dtype=int)
    entries = np.full(n, np.nan)
    stops   = np.full(n, np.nan)
    targets = np.full(n, np.nan)

    fires = rng.random(n) < SIGNAL_PROB
    sides = rng.choice([1, -1], size=n)

    for i in range(n):
        if not fires[i]:
            continue
        side = sides[i]
        e = float(close[i])
        signals[i] = side
        entries[i] = e
        stops[i]   = e - RISK_POINTS  if side == 1 else e + RISK_POINTS
        targets[i] = e + REWARD_POINTS if side == 1 else e - REWARD_POINTS

    return pd.DataFrame(
        {"signal": signals, "entry": entries, "stop": stops, "target": targets},
        index=df.index,
    )
