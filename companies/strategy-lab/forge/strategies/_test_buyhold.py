"""
Sanity strategy: buy-and-hold. ONE long entry at bar 0, never stops out, never
hits target — exits at last bar via the simulator's EOD fallback.

Observed verdict on MNQ 5m / 60d (2026-04-20 baseline):
  trades   = 1
  gross    = $2,962.00   (1,481 pts × $2.00/pt)
  net      = $2,958.50   (gross − $2.00 slippage − $1.50 commission = $3.50 cost)
  sharpe   = 2.79  (single-trade artifact, ignore)
  PROMOTED = False (fails trades>=100 gate by design)

This nails the cost model: gross − net per trade must equal exactly
SLIPPAGE_TICKS*2*TICK_SIZE*POINT_VALUE + COMMISSION_RT = $3.50 on MNQ.
If that ever drifts, the cost constants in backtester.py are wrong.

Run:  python -m forge.judge --strategy _test_buyhold
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "signal": np.zeros(len(df), dtype=int),
            "entry":  np.full(len(df), np.nan),
            "stop":   np.full(len(df), np.nan),
            "target": np.full(len(df), np.nan),
        },
        index=df.index,
    )
    entry_price = float(df["close"].iloc[0])
    out.iloc[0, out.columns.get_loc("signal")] = 1
    out.iloc[0, out.columns.get_loc("entry")]  = entry_price
    out.iloc[0, out.columns.get_loc("stop")]   = entry_price - 1_000_000.0
    out.iloc[0, out.columns.get_loc("target")] = entry_price + 1_000_000.0
    return out
