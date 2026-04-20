# Strategy Lab

Backtest + validation factory for trading strategy ideas.

Write a `generate_signals(df)` function → Judge runs intrabar simulation,
walk-forward, Monte Carlo, and 6 promotion gates → survivors are candidates
for paper-bot deployment.

See [CLAUDE.md](./CLAUDE.md) for architecture and how to add a strategy.

## Quick test
```bash
python -m forge.backtester --strategy <name>   # quick sanity
python -m forge.judge      --strategy <name>   # full gauntlet
```

**Paper mode only.** No strategy goes live without explicit approval.
