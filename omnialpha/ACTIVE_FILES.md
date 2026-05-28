# `omnialpha/` — Active Files Manifest

Updated 2026-05-27 after surgical OmniAlpha delete. If a file isn't listed here, it shouldn't exist (per master CLAUDE.md FILE HYGIENE rule).

This directory is now a **shared Kalshi infrastructure library**, not a bot. See `CLAUDE.md` for what each module does and how to wire a new bot.

## Top-level

- `CLAUDE.md` — project brain (this library, not the dead OmniAlpha bot)
- `ACTIVE_FILES.md` — this file
- `config.py` — paper-mode flag, capital, risk caps, sector enables, Kalshi base URL
- `cli.py` — operational CLI (`health`, `init-db`, `pull-historical`, `status`)
- `requirements.txt` — pinned deps
- `.env.example` — env template (no secrets)
- `.gitignore` — local ignores (state/, logs/)

## `bots/`

- `__init__.py`
- `kalshi_client.py` — signed REST + WebSocket client (the hard one)
- `kalshi_public.py` — unauthenticated `/historical/*` puller
- `live_scanner.py` — universe scan loop, strategy-agnostic
- `order_placer.py` — paper/live order placement, paper-mode hard stop
- `risk_engine.py` — 5-gate pre-trade check (Kelly + caps + bucket)
- `trade_monitor.py` — fill + settlement reconciliation
- `strategy_grader.py` — CLV/WR-based auto-pause
- `strategy_labels.py` — plain-English label map for Telegram (empty after OmniAlpha delete; add per new bot)
- `telegram_alerts.py` — `[<BotName>]`-prefixed dispatcher

## `data_layer/`

- `__init__.py`
- `database.py` — SQLite schema + `init_db()`
- `historical_pull.py` — bulk-pull settled markets into local DB

## `strategies/`

- `__init__.py`
- `base.py` — `Strategy` ABC + `MarketSnapshot`/`StrategyContext`/`EntryDecision`/`ExitDecision` dataclasses
- `longshot_fade.py` — NO-side maker on KXNBAGAME + KXNFLGAME at 85-99¢ band (Phase 2, paper-mode only until live promotion gate)

## `tests/`

- `__init__.py`
- `test_kalshi_public.py` — historical puller, network mocked
- `test_live_scanner.py` — snapshot conversion + scan-and-trade (uses `StubBuyNoStrategy` fixture)
- `test_order_placer.py` — paper/live invariants
- `test_rate_limit_cooldown.py` — per-series 429 cooldown
- `test_risk_engine.py` — every gate, contract clamping, bucket
- `test_longshot_fade.py` — sector/series/price/liquidity/time gates, Kelly sizing, EV math, bucket calibration

## Runtime (gitignored, NOT committed)

- `state/` — per-bot SQLite DB + PID + throttle files
- `logs/` — per-bot logs
- `__pycache__/` — bytecode

When a new bot adds `strategies/<bot>.py` and `main_<bot>.py`, list them here in the same commit.
