# Strategy Lab — Active Files Manifest

Every file in this project must be listed here. If it's not listed, delete it.

## Root
- `CLAUDE.md` — mission + lab architecture
- `ACTIVE_FILES.md` — this file
- `README.md` — human-facing overview
- `.env` — `GROQ_API_KEY` (gitignored via root `.gitignore`)
- `.gitignore` — excludes `data/{backtests,judge}/*.json`, `logs/`, pycache

## forge/ (the lab)
- `__init__.py` — package marker
- `data_loader.py` — yfinance MNQ=F loader, returns canonical OHLCV df in US/Eastern
- `primitives.py` — SMC/TA building blocks (FVG, OB, MSS, swings, PDH/PDL, sessions, liquidity sweeps); lookahead-safe via `swing_length` shifts
- `backtester.py` — Honest intrabar simulator + vectorbt-derived sharpe/sortino/expectancy
- `judge.py` — Walk-forward + Monte Carlo + 6 promotion gates, writes leaderboard JSON

## forge/strategies/ (one .py per strategy you want to test)
- `.gitkeep` — placeholder so the empty dir is tracked

## data/ (all gitignored except this note)
- `backtests/` — per-strategy backtest result JSONs
- `judge/` — per-strategy verdicts + leaderboard.json

## logs/
- *(gitignored)*
