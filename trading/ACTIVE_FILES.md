# ORB Trading System — Active Files Manifest

Any file under `C:\ZachAI\trading\` that is NOT in this list should be deleted.

## Entry Point
- `main.py` — APScheduler multi-agent controller. Auto-start via `scripts/ORBAgents.vbs`.

## Core
- `config.py` — constants, timezone, market holidays, `is_trading_day()`, `get_hard_close_time()`
- `models.py` — dataclasses (Trade, Signal, etc.)

## Agents
- `agents/__init__.py`
- `agents/sentinel.py` — 8 AM initial + 60s poll (news/truth watch)
- `agents/structure.py` — 8:45 AM (daily levels, VIX, ATR)
- `agents/briefing.py` — 8:50 AM (morning Telegram report)
- `agents/sweep.py` — 15s poll during 9:00–11:00 (sweep detection)
- `agents/combiner.py` — 15s poll during 9:30–15:00 (ORB scoring + trades)
- `agents/preflight.py` — 7:00 AM (stack verification)
- `agents/memory.py` — 7:30 AM + 6:00 PM (daily memory + EOD)
- `agents/journal.py` — journal DB + weekly report

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

## Runtime (gitignored)
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- `state/orb.pid` — single-instance lock
- `state/state.json` — runtime state
- `state/backups/journal_*.db` — daily journal DB backup (keeps 30 days)
- `journal.db` — SQLite journal
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
| `journal_backup` | 6:00 AM ET | Copy journal.db to `state/backups/` |
| `journal_weekly` | Sun 7:00 AM | Weekly report |
