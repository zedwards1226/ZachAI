# ORB Trading System — Active Files Manifest

Any file under `C:\ZachAI\trading\` that is NOT in this list should be deleted.

## Entry Point
- `main.py` — APScheduler multi-agent controller. Auto-start via `scripts/ORBAgents.vbs`.

## Core
- `config.py` — constants, timezone, market holidays, `is_trading_day()`, `get_hard_close_time()`
- `models.py` — dataclasses (Trade, Signal, etc.)
- `requirements.txt` — pip deps
- `CLAUDE.md` — per-project operating brief (auto-loaded by Claude Code)
- `ACTIVE_FILES.md` — this manifest

## Agents
- `agents/__init__.py`
- `agents/sentinel.py` — 8 AM initial + 60s poll (news/truth watch)
- `agents/structure.py` — 8:45 AM (daily levels, VIX, ATR)
- `agents/briefing.py` — 8:50 AM (morning Telegram report)
- `agents/combiner.py` — 15s poll during 9:30–15:00 (ORB scoring + trades)
- `agents/preflight.py` — 7:00 AM (stack verification)
- `agents/memory.py` — 7:30 AM + 6:00 PM (daily memory + EOD)
- `agents/journal.py` — journal DB + weekly report + agent_journal audit table
- `agents/learning_agent.py` — 6:30 PM daily + Sun 7:05 AM weekly; reviews trades, proposes knob changes
- `agents/config_loader.py` — loads `state/learned_config.json` overrides on top of `config.py` + manual-edit detection

## Services
- `services/__init__.py`
- `services/tv_client.py` — TradingView CDP wrapper
- `services/tv_trader.py` — order placement + trade monitoring
- `services/telegram.py` — Telegram send/close
- `services/state_manager.py` — state.json reads/writes

## Backtest
- `backtest/__init__.py`
- `backtest/runner.py`
- `backtest/replay.py`

## Tests
- `tests/test_cascade_second_break.py`
- `tests/test_combiner_reversal.py`
- `tests/test_config_loader.py`
- `tests/test_learning_agent.py`

## Research
- `research/production_patterns_2026-04-30.md` — pattern audit from 5 parallel research subagents

## Runtime (gitignored)
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- `state/orb.pid` — single-instance lock
- `state/state.json` — runtime state
- `state/backups/journal_*.db` — daily journal DB backup (keeps 30 days)
- `state/learned_config.json` — learning agent's approved knob overrides (manual edits detected + logged)
- `state/learned_config.meta.json` — checksum + snapshot for manual-edit detection
- `journal.db` — SQLite journal (includes `agent_journal` audit table)
- `logs/trading.log*` — rotated daily, 14-day retention

## Scheduler jobs (source of truth: `main.py`)
| Job ID | Schedule | Purpose |
|---|---|---|
| `preflight` | 7:00 AM ET | Stack verification |
| `memory_morning` | 7:30 AM ET | Pre-market memory refresh |
| `sentinel_initial` | 8:00 AM ET | News/truth initial scan |
| `structure` | 8:45 AM ET | Daily levels, VIX, ATR |
| `briefing` | 8:50 AM ET | Morning Telegram report |
| `briefing_heartbeat` | 8:55 AM ET | Confirms morning agents ran |
| `combiner_heartbeat` | 9:31 AM ET | Confirms combiner armed |
| `sweep_poll` | every 15s | Sweep detection (internal clock gate) |
| `sentinel_poll` | every 60s | News/truth poll |
| `combiner_poll` | every 15s | ORB scoring + trade execution |
| `trade_monitor` | every 30s | Stop/TP reconciliation |
| `memory` | 6:00 PM ET | EOD memory |
| `learning_agent` | 6:30 PM ET | Nightly trade review + Telegram digest (heartbeat even if <20 trades) |
| `learning_weekly` | Sun 7:05 AM | Weekly learning-agent digest |
| `journal_backup` | 6:00 AM ET | Copy journal.db to `state/backups/` |
| `journal_weekly` | Sun 7:00 AM | Weekly report |
