# WeatherAlpha (Kalshi) — Active Files Manifest

Any file under `C:\ZachAI\kalshi\` that is NOT in this list should be deleted.

## Bot (Flask API :5000)
- `bots/app.py` — Flask entry point. Auto-start via `scripts/WeatherAlpha_Bot.vbs`.
- `bots/scheduler.py` — APScheduler (scan loop, 15-min interval)
- `bots/trader.py` — signal → stake → guardrails → place order; reconcile on exception
- `bots/guardrails.py` — trade checks (edge, price, capital, disagreement, spread, blocked strike types)
- `bots/edge.py` — ensemble probability → edge calculation, strike_type clips
- `bots/kelly.py` — position sizing (fractional Kelly)
- `bots/weather.py` — Open-Meteo ensemble forecast
- `bots/kalshi_client.py` — Kalshi API wrapper (RSA-signed)
- `bots/monitor.py` — health-check daemon, scan trigger, Telegram heartbeat
- `bots/database.py` — SQLite layer (trades, signals, guardrail_state, agent_state)
- `bots/calibration.py` — per-(city,side) Bayesian shrinkage from resolved-trade WR
- `bots/learning_agent.py` — nightly Brier-driven MIN_EDGE adapter + per-city pause
- `bots/check.py` — ops/smoke-test helper (last-20-trades CLI dump)
- `bots/config.py` — constants, MAX_BET, MIN_EDGE, BLOCK_STRIKE_TYPES, CITIES, TIMEZONE

## Tests
- `bots/tests/__init__.py`
- `bots/tests/test_edge.py`
- `bots/tests/test_kelly.py`
- `bots/tests/test_kalshi_client.py` — order placement validation + get_orders reconciliation probe
- `bots/tests/test_weather_retry.py` — Open-Meteo retry wrapper
- `bots/tests/test_trader_orderpath.py` — phantom-position reconciliation after place_order raises
- `bots/tests/test_guardrail_between.py` — between-strike disagreement bypass regression
- `bots/tests/test_guardrail_midnight.py` — midnight rollover edge case
- `bots/tests/test_api_auth.py` — internal-secret gate on POST endpoints

## Dashboard (Flask proxy :3001)
- `dashboard/backend/serve.py` — Auto-start via `scripts/WeatherAlpha_Dashboard.vbs`
- `dashboard/frontend/` — Vite/React source; build output served from `dashboard/backend/static/`

## Runtime (gitignored)
- `keys/` — Kalshi RSA private keys
- `.env` — KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH, TELEGRAM_*, INTERNAL_API_SECRET
- `bots/weatheralpha.db` — SQLite trade log + signals + agent state
- `bots/monitor.log`, `bots/weatheralpha.log` — runtime logs
- Tunnel handled by `scripts/WeatherAlpha_Tunnel.vbs` → localhost.run
