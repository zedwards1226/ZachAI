# ICTBOT — Active Files Manifest

If a file isn't listed here, it shouldn't exist. After every create/delete/rename, update this file in the same commit.

## Root
- `CLAUDE.md` — project brain
- `ACTIVE_FILES.md` — this file
- `.env.example` — env template (gitignored .env at runtime)
- `.gitignore` — excludes state/, logs/, .env, *.db, __pycache__
- `requirements.txt` — pip dependencies
- `config.py` — runtime knobs (paper mode, capital, risk caps, killzones, symbol)
- `main.py` — APScheduler entry, PID lock, startup ping
- `cli.py` — `status` / `health` / `last-trade` / `today-setups` commands

## services/
- `services/__init__.py`
- `services/state_manager.py` — SQLite handle, arm/halt status, daily reset
- `services/ict_tv_client.py` — CDP client targeting :9223
- `services/ict_tv_trader.py` — `place_bracket_order(symbol, side, qty, sl, tp)` on MES via :9223
- `services/tv_data.py` — read MES bars (multi-timeframe via TV MCP fallback to CDP)
- `services/ict_analyzer.py` — FVG / sweep / MSS / displacement detection
- `services/setup_scanner.py` — combines analyzer signals into named setups
- `services/trade_manager.py` — open-position monitor (BE move, time exit, hard close)
- `services/telegram.py` — separate bot + channel, `[ICTBot]` prefix

## strategies/
- `strategies/__init__.py`
- `strategies/ny_am_fvg.py` — entry/stop/target rules for NY AM FVG setup

## agents/
- `agents/__init__.py`
- `agents/monitor.py` — 30s wake during active killzones
- `agents/briefing.py` — 7:00 AM ET morning report
- `agents/learning.py` — nightly review (placeholder Phase 1)

## data_layer/
- `data_layer/__init__.py`
- `data_layer/database.py` — SQLite schema (trades, setups, fvgs, daily_levels, signals, journal)

## dashboard/
- `dashboard/app.py` — Flask :3002
- `dashboard/templates/index.html` — single-page dashboard

## backtest/
- `backtest/runner.py` — replay historical bars through strategy
- `backtest/data_loader.py` — load historical 5m CSVs (Google Drive / databento style)

## scripts/
- `scripts/start_ictbot.vbs` — auto-start Python bot
- `scripts/start_ictbot_browser.vbs` — auto-launch Chromium :9223
- `scripts/ictbot_watchdog.py` — supervisor (auto-restart + Telegram alert)

## docs/
- `docs/setups.md` — ICT setup definitions (entry/stop/target rules per setup)

## tests/
- `tests/__init__.py`
- `tests/test_ict_analyzer.py` — FVG / sweep / MSS unit tests with fixture bars
- `tests/test_setup_scanner.py` — end-to-end on a replayed historical day

## state/ (gitignored)
- `state/ictbot.pid`
- `state/trades.db`
- `state/arm_status.json`
- `state/current_view.json`

## logs/ (gitignored)
- `logs/ictbot.log`
- `logs/watchdog.log`
