# ZachAI — Autonomous AI Company Factory

Personal infrastructure for running autonomous AI-operated companies on a single Windows host. One prompt = one new company; every company auto-starts on boot and runs itself.

## Active projects
- **`trading/`** — MNQ ORB futures strategy, direct CDP to TradingView Desktop (paper mode)
- **`kalshi/`** — WeatherAlpha Kalshi weather event bot (paper mode) — dashboard at http://localhost:3001, API at http://localhost:5000
- **`longshot/`** — Kalshi infra library + LongshotFade sports NO-maker bot (paper mode) — dashboard at http://localhost:8503
- **`telegram-bridge/`** — Jarvis Telegram bot (command surface) — http://localhost:8765
- **`companies/`** — TradingAgents (FastAPI gate), Zacks Work Drawings (Flutter Android)

## Where to start
- **`CLAUDE.md`** — master operating brain for Claude Code sessions (rules, autonomy policy, project roster)
- **`ACTIVE_FILES.md`** — manifest of every file that should exist in the repo
- **`RULES.md`** — terse operating rules
- Each project has its own `CLAUDE.md` with operational details

## Auto-start + reliability
- Windows Startup folder launches all services on boot via VBS scripts in `scripts/`
- Watchdogs (`scripts/orb_watchdog.py`, `scripts/watchdog.py`) auto-restart crashed services and alert via Telegram
- `backup.bat` + Task Scheduler push to GitHub every 2 hours

## Owner
Zach Edwards · Memphis TN · [zedwards1226](https://github.com/zedwards1226)
