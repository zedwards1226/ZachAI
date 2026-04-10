# TradingAgents — Active Files Manifest

## Core
- `main.py` — FastAPI gate, webhook endpoint, trade entry/close logic
- `config.py` — All thresholds, limits, env var loading
- `models.py` — Pydantic models (Signal, Trade, Decision, AgentVerdict)
- `database.py` — SQLite schema + queries
- `requirements.txt` — Python dependencies

## Agents
- `agents/__init__.py`
- `agents/overseer.py` — Rule-based guardrails (zero tokens, blocking)
- `agents/sentinel.py` — Anomaly detection (Phase 4)
- `agents/sweep_detector.py` — Smart money patterns (Phase 5)
- `agents/context.py` — Market regime/bias (Phase 6)
- `agents/trade_monitor.py` — Live position tracking (Phase 7)
- `agents/analyst.py` — EOD review with Claude API (Phase 8)

## Services
- `services/__init__.py`
- `services/telegram_bot.py` — Dedicated Telegram bot (Phase 3)
- `services/claude_client.py` — Anthropic SDK wrapper (Phase 4)

## Config
- `.env` — Telegram token, chat ID, Anthropic key (gitignored)

## Data (gitignored)
- `db/tradingagents.db` — SQLite database
- `logs/` — Log files
