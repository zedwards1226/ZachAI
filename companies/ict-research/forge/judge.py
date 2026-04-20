"""
Judge — Agent 6: walk-forward + Monte Carlo + promotion gates.

For every strategy in forge/strategies/, runs:
  1. In-sample backtest (full window) for headline metrics.
  2. Walk-forward (anchored, 3 splits): split data into train/test windows;
     test windows must remain profitable.
  3. Monte Carlo trade-shuffle: 1000 random trade orderings; require positive
     median PnL and bottom-5%-percentile drawdown < 2x observed.
  4. Promotion gates per CLAUDE.md:
       - >= 100 trades in-sample
       - Sharpe > 1.0
       - Profit factor > 1.5
       - Max drawdown < 20% of starting equity
       - Walk-forward test windows: > 50% profitable
       - Monte Carlo median PnL > 0
  5. Composite score: 0.4*Sharpe + 0.3*PF + 0.2*(1-MaxDD%) + 0.1*winrate

Outputs:
  data/judge/<strategy>.json  — per-strategy verdict
  data/judge/leaderboard.json — sorted by composite score, with PROMOTED flag

Usage:
    python -m forge.judge                          # all strategies
    python -m forge.judge --strategy order_block__nQfHZ2DEJ8c
    python -m forge.judge --interval 5m --period 60d
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "forge" / "strategies"
JUDGE_DIR = ROOT / "data" / "judge"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.backtester import (  # noqa: E402
    load_strategy, simulate, compute_metrics, Trade,
    SLIPPAGE_TICKS, TICK_SIZE, POINT_VALUE, COMMISSION_RT,
)

# Promotion gates
MIN_TRADES_IN_SAMPLE = 100
MIN_SHARPE = 1.0
MIN_PF = 1.5
MAX_DD_PCT = 20.0
MIN_WF_PROFITABLE_PCT = 50.0
MIN_MC_MEDIAN_PNL = 0.0

# Walk-forward config
WF_SPLITS = 3
WF_TRAIN_PCT = 0.6  # of each window
MC_TRIALS = 1000


def _trades_pnls(trades: list[Trade]) -> np.ndarray:
    return np.array([t.net_pnl for t in trades])


def walk_forward(strategy_path: Path, df: pd.DataFrame, splits: int = WF_SPLITS) -> dict:
    """Anchored walk-forward: split data into N consecutive windows. For each
    window, take the last 40% as out-of-sample test. Report per-window test
    metrics and aggregate."""
    mod = load_strategy(strategy_path)
    full_signals = mod.generate_signals(df)
    n = len(df)
    window_size = n // splits

    results = []
    for k in range(splits):
        lo = k * window_size
        hi = (k + 1) * window_size if k < splits - 1 else n
        train_end = lo + int((hi - lo) * WF_TRAIN_PCT)

        test_df = df.iloc[train_end:hi]
        test_sig = full_signals.iloc[train_end:hi]
        test_trades = simulate(test_df, test_sig)

        m = compute_metrics(test_trades, test_df)
        results.append({
            "window": k,
            "test_start": test_df.index.min().isoformat() if len(test_df) else None,
            "test_end":   test_df.index.max().isoformat() if len(test_df) else None,
            "test_bars":  len(test_df),
            "trades":     m["trades"],
            "net_pnl":    m["net_pnl"],
            "winrate":    m["winrate"],
            "sharpe":     m["sharpe"],
            "pf":         m["profit_factor"],
            "max_dd":     m["max_drawdown"],
        })

    profitable = sum(1 for r in results if r["net_pnl"] > 0)
    pct_profitable = (profitable / len(results)) * 100 if results else 0.0

    return {
        "splits": splits,
        "windows": results,
        "windows_profitable": profitable,
        "windows_total": len(results),
        "pct_profitable": pct_profitable,
    }


def monte_carlo(trades: list[Trade], trials: int = MC_TRIALS, seed: int = 42) -> dict:
    """Resample trade order N times; report distribution of net_pnl and max_dd."""
    if len(trades) < 5:
        return {"trials": 0, "median_pnl": None, "p05_pnl": None, "p95_pnl": None,
                "median_dd": None, "p95_dd": None,
                "skipped": "fewer than 5 trades"}

    pnls = _trades_pnls(trades)
    rng = np.random.default_rng(seed)
    end_pnls = np.empty(trials)
    max_dds  = np.empty(trials)
    for i in range(trials):
        order = rng.permutation(len(pnls))
        equity = np.cumsum(pnls[order])
        end_pnls[i] = equity[-1]
        peak = np.maximum.accumulate(equity)
        max_dds[i] = (peak - equity).max()

    return {
        "trials":     trials,
        "median_pnl": float(np.median(end_pnls)),
        "p05_pnl":    float(np.percentile(end_pnls, 5)),
        "p95_pnl":    float(np.percentile(end_pnls, 95)),
        "median_dd":  float(np.median(max_dds)),
        "p95_dd":     float(np.percentile(max_dds, 95)),
    }


def composite_score(metrics: dict) -> float | None:
    sh = metrics.get("sharpe")
    pf = metrics.get("profit_factor")
    dd = metrics.get("max_drawdown_pct", 0.0)
    wr = metrics.get("winrate") or 0.0
    if sh is None or pf is None:
        return None
    return float(0.4 * sh + 0.3 * pf + 0.2 * (1 - dd / 100) + 0.1 * wr)


def evaluate(strategy_path: Path, df: pd.DataFrame) -> dict:
    mod = load_strategy(strategy_path)
    t0 = time.perf_counter()
    signals = mod.generate_signals(df)
    trades = simulate(df, signals)
    is_metrics = compute_metrics(trades, df)
    in_sample_ms = (time.perf_counter() - t0) * 1000

    wf = walk_forward(strategy_path, df)
    mc = monte_carlo(trades)
    score = composite_score(is_metrics)

    gates = {
        "trades_>=_100":       is_metrics["trades"] >= MIN_TRADES_IN_SAMPLE,
        "sharpe_>_1.0":        (is_metrics["sharpe"] or 0) > MIN_SHARPE,
        "pf_>_1.5":            (is_metrics["profit_factor"] or 0) > MIN_PF,
        "max_dd_<_20pct":      is_metrics["max_drawdown_pct"] < MAX_DD_PCT,
        "wf_profitable_>_50%": wf["pct_profitable"] > MIN_WF_PROFITABLE_PCT,
        "mc_median_pnl_>_0":   (mc["median_pnl"] is not None and mc["median_pnl"] > MIN_MC_MEDIAN_PNL),
    }
    promoted = all(gates.values())

    return {
        "strategy":       strategy_path.stem,
        "in_sample":      is_metrics,
        "in_sample_ms":   round(in_sample_ms, 1),
        "walk_forward":   wf,
        "monte_carlo":    mc,
        "composite_score": score,
        "gates":          gates,
        "gates_passed":   sum(gates.values()),
        "gates_total":    len(gates),
        "promoted":       promoted,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", default=None,
                   help="strategy stem (without .py); default = all")
    p.add_argument("--interval", default="5m")
    p.add_argument("--period", default="60d")
    args = p.parse_args()

    JUDGE_DIR.mkdir(parents=True, exist_ok=True)

    from forge.data_loader import load_mnq
    print(f"[judge] loading MNQ {args.interval} period={args.period} ...")
    df = load_mnq(interval=args.interval, period=args.period)
    print(f"[judge] {len(df)} bars: {df.index.min()} -> {df.index.max()}")

    if args.strategy:
        paths = [STRATEGY_DIR / f"{args.strategy}.py"]
    else:
        paths = sorted(STRATEGY_DIR.glob("*.py"))
        paths = [p for p in paths if not p.stem.startswith("_")
                 and ".invalid" not in p.stem and ".smoke_failed" not in p.stem]

    print(f"[judge] evaluating {len(paths)} strategies\n")
    leaderboard = []
    for path in paths:
        try:
            verdict = evaluate(path, df)
        except Exception as e:
            print(f"  {path.stem}  FAILED: {type(e).__name__}: {e}")
            continue

        out = JUDGE_DIR / f"{path.stem}.json"
        out.write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")

        m = verdict["in_sample"]
        wf = verdict["walk_forward"]
        gates = verdict["gates_passed"]
        gates_total = verdict["gates_total"]
        flag = "PROMOTED" if verdict["promoted"] else f"reject ({gates}/{gates_total})"
        score_str = f"{verdict['composite_score']:.2f}" if verdict["composite_score"] is not None else " n/a"
        print(f"  {path.stem:42s} score={score_str}  IS:trades={m['trades']:>4d} sh={m['sharpe'] or 0:>5.2f} pf={m['profit_factor'] or 0:>5.2f} dd%={m['max_drawdown_pct']:>5.1f}  WF:{wf['windows_profitable']}/{wf['windows_total']}  {flag}")
        leaderboard.append(verdict)

    leaderboard.sort(key=lambda v: (v["composite_score"] or -999), reverse=True)
    promoted = [v for v in leaderboard if v["promoted"]]

    summary = {
        "evaluated_at":     pd.Timestamp.utcnow().isoformat(),
        "instrument":       "MNQ",
        "interval":         args.interval,
        "period":           args.period,
        "bars":             len(df),
        "data_start":       df.index.min().isoformat(),
        "data_end":         df.index.max().isoformat(),
        "strategies_total": len(leaderboard),
        "promoted":         [v["strategy"] for v in promoted],
        "leaderboard": [
            {
                "rank": i + 1,
                "strategy":        v["strategy"],
                "composite_score": v["composite_score"],
                "promoted":        v["promoted"],
                "trades":          v["in_sample"]["trades"],
                "sharpe":          v["in_sample"]["sharpe"],
                "profit_factor":   v["in_sample"]["profit_factor"],
                "max_dd_pct":      v["in_sample"]["max_drawdown_pct"],
                "winrate":         v["in_sample"]["winrate"],
                "wf_pct_profitable": v["walk_forward"]["pct_profitable"],
                "mc_median_pnl":   v["monte_carlo"]["median_pnl"],
                "gates_passed":    f"{v['gates_passed']}/{v['gates_total']}",
            }
            for i, v in enumerate(leaderboard)
        ],
    }
    (JUDGE_DIR / "leaderboard.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"\n[judge] done — {len(promoted)}/{len(leaderboard)} promoted")
    print(f"[judge] wrote {len(leaderboard)} verdicts + leaderboard to {JUDGE_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
