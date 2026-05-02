# OmniAlpha — Active Files Manifest

Per master CLAUDE.md hygiene rule: every file in this directory MUST appear here.

## Project root
- `CLAUDE.md` — project brain
- `ACTIVE_FILES.md` — this manifest
- `.env.example` — env template (the actual `.env` is gitignored)
- `.gitignore` — ignore patterns
- `requirements.txt` — Python deps
- `config.py` — paper-mode flag, capital, risk caps, sector enables
- `main.py` — APScheduler-driven main loop (paper-only; live cutover is separate)
- `cli.py` — health / init-db / pull-historical / status

## `bots/`
- `__init__.py`
- `kalshi_public.py` — unauthenticated `/historical/*` puller (no API key needed)
- `kalshi_client.py` — RSA-PSS authenticated REST client (live only; not yet active)
- `order_placer.py` — paper-order writer (live path exists but locked behind two flags)
- `events_scanner.py` — universe scanner (currently reads from historical store)
- `trade_monitor.py` — settles open paper trades + writes pnl_snapshots
- `telegram_alerts.py` — Jarvis-bot send-only with [OmniAlpha] prefix
- `risk_engine.py` — 5-gate pre-trade filter + cross-bot risk_state.json coupling

## `data_layer/`
- `__init__.py`
- `database.py` — SQLite schema (markets, trades, signals, decisions, llm_calls, pnl_snapshots, sector_state)
- `historical_pull.py` — bulk-pull settled markets via public endpoints

## `strategies/`
- `__init__.py`
- `base.py` — Strategy ABC + MarketSnapshot + StrategyContext + EntryDecision/ExitDecision
- `crypto_midband.py` — first strategy, tuned to KXBTC15M calibration findings

## `backtest/`
- `__init__.py`
- `runner.py` — replays settled markets through a strategy, applies risk engine, returns BacktestResult
- `calibration.py` — Brier score + log loss + calibration curve from settled markets

## `dashboard/`
- `app.py` — Streamlit, port 8502, read-only

## `tests/` (50 tests passing)
- `__init__.py`
- `test_kalshi_public.py` — 6 tests (sector classification, market row mapping, pagination)
- `test_calibration.py` — 7 tests (Brier, log loss, bin computation)
- `test_strategy_midband.py` — 13 tests (band classification, gates, Kelly scaling, dropped-bands, entry-window)
- `test_risk_engine.py` — 10 tests (every gate, contract clamping, cross-bot state)
- `test_order_placer.py` — 4 tests (paper writes correctly, live refused without explicit flag)
- `test_live_scanner.py` — 9 tests (snapshot conversion, scan-and-trade, already-taken, HTTP failure)
- `test_end_to_end.py` — 1 test, full lifecycle (strategy → risk → place → settle → P&L)

## `state/` (gitignored)
- `omnialpha.db` — SQLite store
- `omnialpha.db-wal`, `omnialpha.db-shm` — WAL artifacts

## `logs/` (gitignored)
- `omnialpha.log` — main process log
- `stdout.log` — VBS-redirected stdout
- `git_pull.log` — pre-launch git pull output

## Reference (lives in `C:\ZachAI\reference\`, NOT here)
- `ryanfrigo-kalshi-bot/` — toolkit pattern source
- `joseph-pm-calibration/` — calibration pipeline source
- `roman-kalshi-btc/` — KXBTC15M puller source

## Auto-start
- `C:\ZachAI\scripts\OmniAlpha.vbs` — git-pull + launch main.py (NOT yet auto-registered in Windows Startup; manual launch only until live cutover)
