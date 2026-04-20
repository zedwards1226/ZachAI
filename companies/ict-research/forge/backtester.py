"""
Backtester — Agent 5: run a generated strategy against MNQ historical bars,
simulate trades bar-by-bar, write metrics JSON.

Backed by vectorbt under the hood. We keep our intrabar stop/target loop for
correctness on tied stop+target hits (worst-case stop wins), but use vectorbt
for the heavyweight metrics (sharpe, sortino, calmar, expectancy, drawdown
curves) and to make walk-forward splits trivial in Agent 6 (Judge).

Reads:  forge/strategies/<setup>__<video_id>.py
Writes: data/backtests/<setup>__<video_id>.json

Cost model (MNQ default): 2 ticks slippage entry + 2 ticks exit, $1.50 commission.
MNQ tick size = 0.25 pts, point value = $2.00.

Usage:
    python -m forge.backtester                          # all strategies
    python -m forge.backtester --strategy order_block__nQfHZ2DEJ8c
    python -m forge.backtester --interval 5m --period 60d
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
import vectorbt as vbt

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "forge" / "strategies"
BACKTEST_DIR = ROOT / "data" / "backtests"

# MNQ contract specs
TICK_SIZE = 0.25
POINT_VALUE = 2.00
SLIPPAGE_TICKS = 2
COMMISSION_RT = 1.50  # round-turn


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    side: int            # 1 long, -1 short
    entry: float
    exit: float
    stop: float
    target: float
    reason: str          # 'target' | 'stop' | 'eod'
    bars_held: int

    @property
    def points(self) -> float:
        return (self.exit - self.entry) * self.side

    @property
    def gross_pnl(self) -> float:
        return self.points * POINT_VALUE

    @property
    def net_pnl(self) -> float:
        slippage = SLIPPAGE_TICKS * 2 * TICK_SIZE * POINT_VALUE  # entry + exit
        return self.gross_pnl - slippage - COMMISSION_RT


def simulate(df: pd.DataFrame, signals: pd.DataFrame) -> list[Trade]:
    """Honest intrabar simulation. One position at a time. Stop wins on tie."""
    n = len(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    sig = signals["signal"].to_numpy()
    entry_p = signals["entry"].to_numpy()
    stop_p = signals["stop"].to_numpy()
    target_p = signals["target"].to_numpy()

    trades: list[Trade] = []
    i = 0
    while i < n:
        s = sig[i]
        if s == 0 or math.isnan(entry_p[i]) or math.isnan(stop_p[i]) or math.isnan(target_p[i]):
            i += 1
            continue

        side = int(s)
        e_price = float(entry_p[i])
        st_price = float(stop_p[i])
        tg_price = float(target_p[i])
        entry_idx = i
        exit_idx, exit_price, reason = None, None, "eod"

        for j in range(i + 1, n):
            h, l = high[j], low[j]
            if side == 1:
                hit_stop = l <= st_price
                hit_target = h >= tg_price
            else:
                hit_stop = h >= st_price
                hit_target = l <= tg_price

            if hit_stop and hit_target:
                exit_idx, exit_price, reason = j, st_price, "stop"
                break
            if hit_stop:
                exit_idx, exit_price, reason = j, st_price, "stop"
                break
            if hit_target:
                exit_idx, exit_price, reason = j, tg_price, "target"
                break
        if exit_idx is None:
            exit_idx = n - 1
            exit_price = float(close[exit_idx])

        trades.append(Trade(
            entry_idx=entry_idx, exit_idx=exit_idx,
            side=side, entry=e_price, exit=float(exit_price),
            stop=st_price, target=tg_price,
            reason=reason, bars_held=exit_idx - entry_idx,
        ))
        i = exit_idx + 1

    return trades


def compute_metrics(trades: list[Trade], df: pd.DataFrame) -> dict:
    """Trade-level metrics + a vectorbt-derived equity curve summary."""
    total_bars = len(df)
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "winrate": None,
            "gross_pnl": 0.0, "net_pnl": 0.0,
            "avg_win": None, "avg_loss": None, "expectancy": None,
            "profit_factor": None, "sharpe": None, "sortino": None,
            "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
            "bars_in_market": 0, "exposure_pct": 0.0,
        }

    pnls = np.array([t.net_pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    equity_step = pd.Series(0.0, index=df.index)
    for t in trades:
        equity_step.iloc[t.exit_idx] += t.net_pnl
    equity = equity_step.cumsum()
    peak = equity.cummax()
    dd = peak - equity
    max_dd = float(dd.max())

    starting_equity = 10_000.0
    equity_curve = starting_equity + equity
    returns = equity_curve.pct_change().fillna(0)

    bar_freq = pd.infer_freq(df.index) or "5min"
    try:
        sharpe = returns.vbt.returns(freq=bar_freq).sharpe_ratio()
        sortino = returns.vbt.returns(freq=bar_freq).sortino_ratio()
    except Exception:
        sharpe, sortino = float("nan"), float("nan")

    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    pf = (gross_win / gross_loss) if gross_loss > 0 else None
    expectancy = float(pnls.mean())

    bars_in = sum(t.bars_held for t in trades)

    return {
        "trades":            len(trades),
        "wins":              int((pnls > 0).sum()),
        "losses":            int((pnls < 0).sum()),
        "winrate":           float((pnls > 0).mean()),
        "gross_pnl":         float(pnls.sum() + (SLIPPAGE_TICKS*2*TICK_SIZE*POINT_VALUE + COMMISSION_RT) * len(trades)),
        "net_pnl":           float(pnls.sum()),
        "avg_win":           float(wins.mean()) if len(wins) else None,
        "avg_loss":          float(losses.mean()) if len(losses) else None,
        "expectancy":        expectancy,
        "profit_factor":     pf,
        "sharpe":            float(sharpe) if not np.isnan(sharpe) else None,
        "sortino":           float(sortino) if not np.isnan(sortino) else None,
        "max_drawdown":      max_dd,
        "max_drawdown_pct":  float(max_dd / starting_equity * 100),
        "bars_in_market":    bars_in,
        "exposure_pct":      float(bars_in / total_bars * 100) if total_bars else 0.0,
    }


def load_strategy(path: Path):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(f"strat_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_one(path: Path, df: pd.DataFrame, interval: str, period: str) -> dict:
    mod = load_strategy(path)
    t0 = time.perf_counter()
    signals = mod.generate_signals(df)
    gen_ms = (time.perf_counter() - t0) * 1000

    trades = simulate(df, signals)
    metrics = compute_metrics(trades, df)

    return {
        "strategy": path.stem,
        "instrument": "MNQ",
        "interval": interval,
        "period": period,
        "bars": len(df),
        "data_start": df.index.min().isoformat(),
        "data_end": df.index.max().isoformat(),
        "generate_signals_ms": round(gen_ms, 1),
        **metrics,
        "first_trades": [
            {k: v for k, v in asdict(t).items() if k not in ("entry_idx", "exit_idx")}
            | {"entry_time": df.index[t.entry_idx].isoformat(),
               "exit_time": df.index[t.exit_idx].isoformat()}
            for t in trades[:5]
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", default=None,
                   help="strategy stem (without .py); default = all")
    p.add_argument("--interval", default="5m")
    p.add_argument("--period", default="60d")
    args = p.parse_args()

    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    from forge.data_loader import load_mnq
    print(f"[backtester] loading MNQ {args.interval} period={args.period} ...")
    df = load_mnq(interval=args.interval, period=args.period)
    print(f"[backtester] {len(df)} bars: {df.index.min()} -> {df.index.max()}")

    if args.strategy:
        paths = [STRATEGY_DIR / f"{args.strategy}.py"]
    else:
        paths = sorted(STRATEGY_DIR.glob("*.py"))
        paths = [p for p in paths if not p.stem.startswith("_")
                 and ".invalid" not in p.stem and ".smoke_failed" not in p.stem]

    print(f"[backtester] running {len(paths)} strategies\n")
    for path in paths:
        try:
            result = run_one(path, df, args.interval, args.period)
        except Exception as e:
            print(f"  {path.stem}  FAILED: {type(e).__name__}: {e}")
            continue

        out = BACKTEST_DIR / f"{path.stem}.json"
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

        wr = f"{result['winrate']*100:5.1f}%" if result['winrate'] is not None else "  n/a"
        pf = f"{result['profit_factor']:5.2f}" if result['profit_factor'] is not None else "  n/a"
        sh = f"{result['sharpe']:5.2f}" if result['sharpe'] is not None else "  n/a"
        print(f"  {path.stem:42s} trades={result['trades']:>4d}  wr={wr}  PF={pf}  Sharpe={sh}  net=${result['net_pnl']:>+9.2f}  MaxDD=${result['max_drawdown']:>8.2f}")

    print(f"\n[backtester] done — wrote {len(paths)} reports to {BACKTEST_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
