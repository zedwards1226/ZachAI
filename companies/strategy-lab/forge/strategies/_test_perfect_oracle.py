"""
Sanity strategy: PERFECT FORESIGHT — peeks at the next bar to pick the winning
side every time. This is intentional lookahead bias and is NOT a real strategy.

Observed verdict on MNQ 5m / 60d (2026-04-20 baseline):
  trades  = 6,708    (signal fires every bar — saturated)
  sharpe  = 3.79     (absurdly high — real strategies max out 1.5–2.5)
  sortino = 13.0     (impossible without leakage)
  PF      = 0.41     (losses dominate)
  winrate = 4.8%     (tight 0.25pt stop gets wicked before target hits)
  MaxDD   = 150%     (catastrophic)
  PROMOTED = False   (rejected on PF, MaxDD, walk-forward, MC)

The "fingerprint" of lookahead is the contradiction: high Sharpe AND blown
drawdown in the same backtest. A real strategy can have one or the other —
never both. Real edge produces moderate Sharpe (1.5–2.5) with controlled DD.

If any real strategy ever shows Sharpe > 3 with abnormal trade count or DD,
audit the strategy code for `.shift(-1)`, future indexing (`df.iloc[i+k]`),
or use of un-shifted swing/pivot data.

This strategy is NOT auto-rejected — the lab currently has no AST-level
lookahead detector. Adding one (regex/AST scan for `shift(-`, `iloc[i+`,
negative period args) is a future hardening task. For now this file is the
smell-test reference: "if my strategy's metrics look like this, it's cheating."

Run:  python -m forge.judge --strategy _test_perfect_oracle
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    close = df["close"].to_numpy()
    next_close = df["close"].shift(-1).to_numpy()  # ← THE CHEAT

    signals = np.zeros(n, dtype=int)
    entries = np.full(n, np.nan)
    stops   = np.full(n, np.nan)
    targets = np.full(n, np.nan)

    for i in range(n - 1):
        c = float(close[i])
        nxt = float(next_close[i])
        if not np.isfinite(nxt) or nxt == c:
            continue
        side = 1 if nxt > c else -1
        signals[i] = side
        entries[i] = c
        # tight stop just past entry on wrong-side, target = next bar's close.
        # since we KNOW next bar moves to `nxt`, target is guaranteed to fill.
        stops[i]   = c - 0.25 if side == 1 else c + 0.25
        targets[i] = nxt

    return pd.DataFrame(
        {"signal": signals, "entry": entries, "stop": stops, "target": targets},
        index=df.index,
    )
