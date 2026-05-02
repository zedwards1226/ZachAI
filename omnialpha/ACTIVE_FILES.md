# OmniAlpha — Active Files Manifest

Per master CLAUDE.md hygiene rule: every file in this directory MUST appear here. After every create/delete/rename, update this manifest in the same commit.

## Project root
- `CLAUDE.md` — project brain
- `ACTIVE_FILES.md` — this manifest
- `.env.example` — env template (gitignore the actual `.env`)
- `.gitignore` — ignore patterns
- `requirements.txt` — Python deps
- `config.py` — paper mode flag, capital, risk caps, sector enables
- `main.py` — APScheduler-driven main loop (NOT WIRED YET — paper-only)
- `cli.py` — status / health / pull-historical commands

## `bots/`
- `__init__.py`
- `kalshi_client.py` — authenticated REST client (RSA signing) — STUB ONLY for now
- `kalshi_public.py` — unauthenticated `/historical/*` puller (works without keys)

## `data_layer/`
- `__init__.py`
- `database.py` — SQLite schema + helpers
- `events_scanner.py` — live universe scanner (NOT WIRED — Phase 2)
- `historical_pull.py` — bulk historical data ingest using public endpoints

## `strategies/`
- `__init__.py` — empty for now (Phase 2 adds first strategy)

## `backtest/`
- `__init__.py` — empty for now (Phase 2)

## `dashboard/`
- `app.py` — Streamlit dashboard (skeleton, reads SQLite)

## `tests/`
- `__init__.py`
- `test_kalshi_public.py` — unit tests for unauthenticated puller (mocked)

## `state/` (gitignored)
- runtime state files written by the bot — never commit

## `logs/` (gitignored)
- log files — never commit

## Reference (lives in `C:\ZachAI\reference\`, NOT here)
- `ryanfrigo-kalshi-bot/` — read-only scaffold source
- `joseph-pm-calibration/` — read-only calibration code source
- `roman-kalshi-btc/` — read-only KXBTC15M puller source

These are NOT part of OmniAlpha — they're upstream code we read for patterns, not run.
