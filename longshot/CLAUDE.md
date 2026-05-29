# `longshot/` — Kalshi Infra Library + LongshotFade Bot

## What this is

`longshot/` is the **reusable Kalshi infrastructure library** plus the **LongshotFade bot** that runs on top of it. It was named `omnialpha/` until 2026-05-29 (renamed at Zach's request) and was originally the OmniAlpha crypto-bot project until 2026-05-27, when that mid-band crypto strategy was deleted after losing −$230 across 247 paper trades (full postmortem in master `C:\ZachAI\CLAUDE.md`).

What survives and runs here:
- **The shared Kalshi infra** — signed auth client, public-data puller, scanner, risk engine, order placer, trade monitor, alerts, DB schema, strategy ABC, CLI. Any new Kalshi bot imports these instead of re-deriving them.
- **LongshotFade** — the first (and currently only) bot built on the library. Sports-market NO-maker, **live in paper mode** since Phase 3. Harness at `main_longshot.py`, dashboard at `dashboard/` on :8503. This is an active process supervised by the ORB watchdog.

A second Kalshi bot would live at `longshot/strategies/<name>.py` + its own `main_<name>.py` harness, reusing the modules below.

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
- **`config.py`** — paper-mode flag, capital, risk caps, sector enables, paths, Kalshi base URL. Imported by the bot's `main_<name>.py`. All paths are relative to this file (`BASE_DIR`), so the directory can be renamed without breaking them.
- **`cli.py`** — operational verbs: `health`, `init-db`, `pull-historical`, `status`. Works against whichever DB `config.DB_PATH` resolves to.
- **`requirements.txt`** — pinned deps shared across any bot built on this library.

## How to wire a new bot

1. **Strategy:** create `longshot/strategies/<your_strategy>.py` implementing the `Strategy` ABC from `strategies/base.py`.
2. **Harness:** create `longshot/main_<your_bot>.py` — APScheduler job that calls `live_scanner.scan_and_trade(strategy=YourStrategy(), series_ticker=..., capital_usd=...)` on whatever cadence you want.
3. **Env:** create `longshot/.env` with `PAPER_MODE=true`, Kalshi credentials, Telegram credentials, Anthropic key (if needed).
4. **Sector enable:** add your sector to `config.ENABLED_SECTORS`.
5. **Label:** add a `STRATEGY_LABELS` entry in `bots/strategy_labels.py` for Telegram readability.
6. **DB:** override `DB_PATH` in your harness so each bot writes to its own `state/<bot>.db`.
7. **Auto-start (optional, after paper validation):** add a `scripts/<YourBot>.vbs` launcher.

## LongshotFade harness (Phase 3 — paper mode)

The first bot built on this library. Single-strategy harness at `main_longshot.py` with the SpaceX-style mission-control dashboard at `dashboard/`.

- **Launch the bot:** `longshot\run_longshot.bat` (or `python main_longshot.py`)
- **Launch the dashboard:** `longshot\run_dashboard.bat` (or `cd dashboard && python serve.py`) → http://localhost:8503
- **Scheduler:** scan every 60s, settle every 5min, equity snapshot every 15min, AM/PM Telegram digest at 13/23 UTC
- **Universe:** KXNBAGAME + KXNFLGAME per the strategy's hard-coded allowlist; EPL/UCL/LIGA blocked at code level (Phase 1 found negative edge on soccer). NOTE 2026-05-29: live trades have also been booked on KXMLBGAME / KXWNBAGAME / KXATPMATCH — reconcile whether the universe was deliberately widened or the series allowlist needs tightening.
- **Capital:** $300 default. Recomputed every scan (start + realized − open_risk) so Kelly auto-scales.
- **Paper-mode enforcement:** harness refuses to start unless `PAPER_MODE=true` in `longshot/.env`. `order_placer.place_live_order()` adds a second hard stop (refuses unless an explicit code flag is also set).
- **Watchdog:** `scripts/LongshotFade.vbs` + `scripts/LongshotFade_Dashboard.vbs` launchers, supervised by `scripts/orb_watchdog.py::check_longshot_main/check_longshot_dashboard`. OPT-IN — the checks no-op unless `state/longshot.pid` exists, so a deliberately-stopped bot isn't nagged. ORB watchdog runs every 5 min via Task Scheduler → bot + dashboard auto-restart on crash and survive reboot (stale PID file triggers relaunch). NOT in the Windows Startup folder — to fully auto-start on boot independent of the watchdog cadence, add the VBS to Startup at Day-18 live promotion.

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

## History

- **2026-05-29:** directory renamed `omnialpha/` → `longshot/` (project name change). Folder moved, all filesystem path references updated (VBS launchers, orb_watchdog PID path, `.gitignore`, `.bat` files, telegram throttle path, sandbox sys.path), User-Agent headers `ZachAI-OmniAlpha` → `ZachAI-Longshot`, CLI prog name, risk-engine bot label `omnialpha` → `longshot`. 66/66 tests pass. DB/capital/trade history carried over intact.
- **2026-05-27:** OmniAlpha crypto bot deleted. Removed: `strategies/crypto_midband.py`, `backtest/`, the old Streamlit/React dashboard, `bots/band_tuner.py`, `main.py` (OmniAlpha entry point), `state/` runtime artifacts (`omnialpha.db`, `strategy_bands.json`, `band_history.jsonl`), and tests for the deleted modules. All outside callers cleaned. The kept infra passes `pytest` clean.

## Auto-merge

LongshotFade is a shipped, running bot. This directory carries the same auto-merge exception WeatherAlpha and ORB have: commit + push, but **notify Zach BEFORE merging** anything touching `bots/order_placer.py` (live order path) or live Kalshi credentials. Normal library changes (infra, tests, docs, other strategies) auto-merge as usual.
