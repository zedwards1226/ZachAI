# `omnialpha/` — Kalshi Shared Infrastructure Library

## What this is now

`omnialpha/` was the OmniAlpha crypto bot project until 2026-05-27. The bot was deleted that day after the mid-band crypto strategy lost −$230 across 247 paper trades (full postmortem in master `C:\ZachAI\CLAUDE.md`). What survives here is the **reusable Kalshi infrastructure** — auth client, public-data puller, scanner, risk engine, order placer, trade monitor, alerts, DB schema, strategy ABC, CLI. Any new Kalshi bot uses these modules instead of re-deriving them.

This directory is **not a bot anymore**. There is no `main.py`, no auto-start VBS, no dashboard, no live process. The next bot will live at `omnialpha/strategies/<name>.py` + its own `main_<name>.py` harness in this directory, importing the shared modules below.

## What's inside

### `bots/` — runtime infrastructure
- **`kalshi_client.py`** — signed REST + WebSocket client. Handles RSA auth, retries, the orderbook_delta channel. The single hardest module in the library (~600 lines). Used by any bot that places orders or subscribes to fills.
- **`kalshi_public.py`** — unauthenticated `/historical/markets`, `/historical/trades`, `/historical/cutoff`. For backtests, calibration runs, edge-validation pulls. No keys needed.
- **`live_scanner.py`** — universe scan loop. Pulls active markets, converts JSON to `MarketSnapshot`, builds `StrategyContext`, hands the snapshot to a `Strategy`, applies the risk engine, places paper or live orders. Strategy-agnostic.
- **`order_placer.py`** — paper/live order placement. `place_paper_order()` writes to the SQLite journal with `paper=1`; `place_live_order()` POSTs to Kalshi. Requires both `PAPER_MODE=false` AND an explicit code-level flag to go live (defense in depth against the hard stop).
- **`risk_engine.py`** — 5-gate pre-trade check: Kelly, per-trade $, daily $, weekly $, same-series-same-side bucket (correlation gate). All caps are % of live capital with USD floors so they compound up and de-lever down.
- **`trade_monitor.py`** — periodic fill + settlement reconciliation. Settles paper trades against Kalshi's resolved-market outcome; updates `status` and `pnl_usd`.
- **`strategy_grader.py`** — CLV/WR-based auto-pause for strategies. Pauses a strategy when WR falls below dynamic break-even after MIN_TRADES settled. Manual resume only.
- **`strategy_labels.py`** — plain-English translations for strategy/sector codenames in Telegram messages. Add an entry per new bot.
- **`telegram_alerts.py`** — `[<BotName>]`-prefixed Telegram dispatcher with cooldown dedup.

### `data_layer/`
- **`database.py`** — SQLite schema. `markets`, `trades`, `strategy_state`, `decision_log`, `cost_ledger`. `init_db()` creates everything idempotently.
- **`historical_pull.py`** — bulk-pulls settled markets into the local DB. Used by backtests and edge-validation.

### `strategies/`
- **`base.py`** — `Strategy` ABC + `MarketSnapshot`, `StrategyContext`, `EntryDecision`, `ExitDecision` dataclasses. Strategies are pure functions of their inputs (no I/O, no time.sleep, no side effects beyond what the runner provides). This makes backtests deterministic and tests trivial.
- **`longshot_fade.py`** — sport-market NO-maker (Phase 2, paper mode only). Sits on the NO bid 1¢ inside the ask in the 85-99¢ longshot band on KXNBAGAME + KXNFLGAME. EPL/UCL/LIGA/etc. are blocked at code level — Phase 1 validation found soccer markets had structurally NEGATIVE edge (-8.4pp at 85-89¢). Per-bucket forecast probabilities derived from 873k-trade Phase 1 sample, shrunk 1pp toward implied to leave margin. Kelly 0.05, $30 hard cap, ≥1¢ EV per $1 risked after Kalshi's 7% fee on winnings. See `sandbox/longshot_fade_validation_2026-05-27/report.md` for the data the calibration was built on.

### `tests/`
- **`test_kalshi_public.py`** — historical-data puller, mocks `httpx.Client`
- **`test_live_scanner.py`** — snapshot conversion + scan-and-trade flow (uses `StubBuyNoStrategy` fixture)
- **`test_order_placer.py`** — paper/live separation invariants
- **`test_rate_limit_cooldown.py`** — per-series 429 cooldown
- **`test_risk_engine.py`** — every gate, contract clamping, cross-bot state, bucket gate

### Top-level
- **`config.py`** — paper-mode flag, capital, risk caps, sector enables, paths, Kalshi base URL. Imported by the bot's `main_<name>.py`.
- **`cli.py`** — operational verbs: `health`, `init-db`, `pull-historical`, `status`. Works against whichever DB `config.DB_PATH` resolves to.
- **`requirements.txt`** — pinned deps shared across any bot built on this library.

## How to wire a new bot

1. **Strategy:** create `omnialpha/strategies/<your_strategy>.py` implementing the `Strategy` ABC from `strategies/base.py`.
2. **Harness:** create `omnialpha/main_<your_bot>.py` — APScheduler job that calls `live_scanner.scan_and_trade(strategy=YourStrategy(), series_ticker=..., capital_usd=...)` on whatever cadence you want.
3. **Env:** create `omnialpha/.env` with `PAPER_MODE=true`, Kalshi credentials, Telegram credentials, Anthropic key (if needed).
4. **Sector enable:** add your sector to `config.ENABLED_SECTORS`.
5. **Label:** add a `STRATEGY_LABELS` entry in `bots/strategy_labels.py` for Telegram readability.
6. **DB:** override `DB_PATH` in your harness so each bot writes to its own `state/<bot>.db`.
7. **Auto-start (optional, after paper validation):** add a `scripts/<YourBot>.vbs` launcher.

## LongshotFade harness (Phase 3 — paper mode, manual launch)

The first bot built on this library. Single-strategy harness at `main_longshot.py` with the SpaceX-style mission-control dashboard at `dashboard/`.

- **Launch the bot:** `omnialpha\run_longshot.bat` (or `python main_longshot.py`)
- **Launch the dashboard:** `omnialpha\run_dashboard.bat` (or `cd dashboard && python serve.py`) → http://localhost:8503
- **Scheduler:** scan every 60s, settle every 5min, equity snapshot every 15min, AM/PM Telegram digest at 13/23 UTC
- **Universe:** KXNBAGAME + KXNFLGAME only. EPL/UCL/LIGA blocked at code level (Phase 1 found negative edge on soccer)
- **Capital:** $300 default. Recomputed every scan (start + realized − open_risk) so Kelly auto-scales.
- **Paper-mode enforcement:** harness refuses to start unless `PAPER_MODE=true` in `omnialpha/.env`. `order_placer.place_live_order()` adds a second hard stop (refuses unless an explicit code flag is also set).
- **Watchdog (2026-05-27):** `scripts/LongshotFade.vbs` + `scripts/LongshotFade_Dashboard.vbs` launchers exist, supervised by `scripts/orb_watchdog.py::check_longshot_main/check_longshot_dashboard`. OPT-IN — the checks no-op unless `state/longshot.pid` exists, so a deliberately-stopped bot isn't nagged. ORB watchdog runs every 5 min via Task Scheduler → bot + dashboard auto-restart on crash and survive reboot (stale PID file triggers relaunch). NOT in the Windows Startup folder — to fully auto-start on boot independent of the watchdog cadence, add the VBS to Startup at Day-18 live promotion.

### Dashboard endpoints (`dashboard/serve.py`, port 8503)
| Path | Purpose |
|---|---|
| `GET /` | serves `dashboard.html` |
| `GET /api/health` | paper mode, bot pid, capital, day PnL, scan stats |
| `GET /api/feed?limit=&since=` | last N decisions for the live feed |
| `GET /api/thinking` | most recent ENGAGE decision + full math |
| `GET /api/positions` | open trades + recent settlements |
| `GET /api/performance` | equity curve, band WR vs forecast, series PnL |
| `GET /api/subsystems` | health dots for Bot/API/DB/Telegram/Watchdog |

Dashboard reads the journal via `file:...?mode=ro` SQLite URI — dashboard bugs can never lock or corrupt the live bot's DB.

## Paper mode is the hard stop

`config.PAPER_MODE` is read from `.env` and defaults to `true`. `order_placer.place_live_order()` refuses to run unless BOTH `PAPER_MODE=false` AND `assert_paper_mode_off_was_explicit()` returns true. Setting `PAPER_MODE=false` is one of the 3 hard stops in master CLAUDE.md and requires Zach's explicit approval.

## What was removed 2026-05-27

- `strategies/crypto_midband.py` (the failed strategy)
- `backtest/` (calibration runs for the failed bands)
- `dashboard/` (Streamlit + React scaffold, only ever served the failed bot)
- `bots/band_tuner.py` (crypto-specific band tuner)
- `main.py` (OmniAlpha entry point with the crypto registry)
- `state/` runtime artifacts (`omnialpha.db`, `strategy_bands.json`, `band_history.jsonl`)
- Tests for the deleted modules (`test_calibration.py`, `test_end_to_end.py`, `test_strategy_midband.py`, `test_strategy_labels.py`)
- All outside callers cleaned: `scripts/orb_watchdog.py`, `trading/agents/daily_summary.py`, `.claude/launch.json`, `trading/dashboard/backend/serve.py` docstring

The kalshi infra in `bots/`, `data_layer/`, `strategies/base.py`, `config.py`, `cli.py`, and the kept tests pass `pytest` clean (40/40).

## Auto-merge

Until a new bot ships from here, treat `omnialpha/` as a normal library — auto-merge applies, no extra approval gate. Once a strategy ships and goes live, this file gets the same auto-merge exception WeatherAlpha and ORB have (commit + push but notify Zach BEFORE merging anything touching `bots/order_placer.py` or live credentials).
