# Strategy Lab

## Mission
A general-purpose backtest + validation factory for any trading strategy idea. You write a `generate_signals(df)` function in `forge/strategies/<name>.py`, the lab runs it through honest intrabar simulation → walk-forward → Monte Carlo → 6 promotion gates. If it survives, it's a candidate to deploy as a paper bot alongside ORB.

**Paper mode ONLY. No strategy goes live until Zach approves.**

## What's in the box

```
forge/data_loader.py   yfinance MNQ=F loader (5m / 60d default), US/Eastern tz
forge/primitives.py    SMC/TA building blocks (FVG, OB, MSS, swings, PDH/PDL,
                       sessions, liquidity sweeps) — wraps smartmoneyconcepts,
                       lookahead-safe via swing_length shifts
forge/backtester.py    Honest intrabar sim (one position, stop-wins-on-tie),
                       vectorbt-derived sharpe/sortino/expectancy
forge/judge.py         Walk-forward (3 splits, 60/40) + Monte Carlo (1000
                       trade-shuffle) + 6 promotion gates, writes leaderboard
forge/strategies/      One .py file per strategy. Must export
                       generate_signals(df) -> DataFrame[signal,entry,stop,target]
```

## Promotion gates
A strategy is PROMOTED only if ALL pass:
- ≥ 100 trades in-sample
- Sharpe > 1.0
- Profit factor > 1.5
- Max drawdown < 20% of starting equity
- Walk-forward: > 50% of test windows profitable
- Monte Carlo: median PnL > 0

Composite rank: `0.4*Sharpe + 0.3*PF + 0.2*(1-MaxDD%) + 0.1*winrate`

## Lookahead protection
The backtester walks forward bar-by-bar, stops/targets resolved intrabar with
worst-case-stop-wins ties. `forge/primitives.py` shifts every swing-derived
signal forward by `swing_length` bars so signals are only "confirmed" after
enough future bars have passed. Strategies that use only the public primitives
API (no `df.iloc[k]` for k > current bar, no negative `shift()`) are
lookahead-safe by construction.

## How to add a strategy

1. Create `forge/strategies/<name>.py` with `generate_signals(df)`.
2. Run `python -m forge.backtester --strategy <name>` for a quick sanity check.
3. Run `python -m forge.judge --strategy <name>` for the full gauntlet.
4. Read `data/judge/<name>.json` for the verdict.

## Cost model (MNQ defaults)
- Tick size: 0.25 pts, point value: $2.00
- Slippage: 2 ticks entry + 2 ticks exit
- Commission: $1.50 round-turn

To target a different instrument, edit constants at the top of `forge/backtester.py`
and replace `forge/data_loader.py:load_mnq()` with the appropriate loader.

## Folder layout

```
companies/ict-research/    (folder name kept for git history; project is general now)
├── CLAUDE.md              this file
├── ACTIVE_FILES.md        manifest
├── README.md              human-facing overview
├── .env                   GROQ_API_KEY (used only by future agentic helpers)
├── forge/                 the lab
│   ├── data_loader.py
│   ├── primitives.py
│   ├── backtester.py
│   ├── judge.py
│   └── strategies/        your strategy files (gitkeeped, otherwise empty)
└── data/                  outputs (gitignored)
    ├── backtests/         per-strategy result JSONs
    └── judge/             leaderboard + per-strategy verdicts
```

## Auto-merge exceptions
- Anything in `forge/strategies/` auto-merges (they're code, not config).
- BEFORE any strategy is wired into a live paper bot, Zach approves.

## Current Status (2026-04-20)
- Clean slate after retiring the ICT-specific YouTube research pipeline
- 4 universal modules in `forge/`, ready for strategy submissions
- 0 strategies, 0 backtests, 0 verdicts — bring your own idea

## Next Actions
1. Decide on first strategy to test (Larry Connors mean-reversion? Opening range
   gap fade? Simple SMA crossover with proper risk?)
2. Write `forge/strategies/<name>.py`
3. Run Judge, read verdict
