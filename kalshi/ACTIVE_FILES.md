# WeatherAlpha (Kalshi) — Active Files Manifest

Any file under `C:\ZachAI\kalshi\` that is NOT in this list should be deleted.

## Bot (Flask API :5000)
- `bots/app.py` — Flask entry point. Auto-start via `scripts/WeatherAlpha_Bot.vbs` (or equivalent).
- `bots/scheduler.py` — APScheduler (scan loop, 15-min interval)
- `bots/trader.py` — signal → stake → guardrails → place order
- `bots/guardrails.py` — trade checks (edge, price, capital, disagreement, spread)
- `bots/edge.py` — ensemble probability → edge calculation, strike_type clips
- `bots/kelly.py` — position sizing
- `bots/weather.py` — Open-Meteo ensemble forecast
- `bots/kalshi_client.py` — Kalshi API wrapper (RSA-signed)
- `bots/monitor.py` — open-position reconciliation
- `bots/database.py` — SQLite layer (trades, signals, guardrail_state)
- `bots/check.py` — ops/smoke-test helper
- `bots/config.py` — constants, MAX_BET, MIN_EDGE, TRADE_WINDOW_*, TIMEZONE

## Tests
- `bots/tests/__init__.py`
- `bots/tests/test_edge.py`
- `bots/tests/test_kelly.py`
- `bots/tests/test_kalshi_client.py` — order placement validation + get_orders reconciliation probe
- `bots/tests/test_weather_retry.py` — Open-Meteo retry wrapper
- `bots/tests/test_trader_orderpath.py` — phantom-position reconciliation after place_order raises

## Dashboard (Flask proxy :3001)
- `dashboard/backend/serve.py` — Auto-start via `scripts/WeatherAlpha_Dashboard.vbs`

## Runtime (gitignored)
- `keys/` — Kalshi RSA private keys
- `.env` — KALSHI_EMAIL, KALSHI_KEY_ID, SSH tunnel creds
- `kalshi.db` — SQLite trade log
- Tunnel handled by `scripts/WeatherAlpha_Tunnel.bat` → localhost.run
