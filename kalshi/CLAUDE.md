# WEATHERALPHA — Project Brain

## OVERVIEW
Kalshi weather prediction market trading bot. Trades between-markets on daily high/low temperature contracts across 6 US cities using Open-Meteo forecasts as edge signal.

- **LIVE real-money mode** (PAPER_MODE=false) since 2026-05-21, confirmed intentional by Zach. Flipping the mode either direction is still a hard stop — NEVER change without explicit approval.
- **RECALIBRATION MODE since 2026-05-25** — Post-May-21 live WR collapsed from 72% → 48% after coord-fix + calibration reset wiped per-city shrinkage. Applied via kalshi/.env: MIN_EDGE 0.08→0.20, MIN_EDGE_YES=0.25, PROB_SHRINK_TO_MARKET 0.25→0.45, KELLY_FRACTION 0.25→0.15, MAX_DAILY_TRADES 7→4, BLOCK_STRIKE_TYPES=less,between. Trading 'greater' strikes only until per-city calibration has ≥10 post-2026-05-22 samples. Full diagnosis: `C:\Users\zedwa\.claude\plans\i-want-you-look-swift-panda.md`. Revisit when shrinkage table matures (~mid-June).

## SERVICES
- **Bot API:** `http://localhost:5000` — Flask app at `C:\ZachAI\kalshi\bots\app.py`
  - Auto-start: `scripts/WeatherAlpha_Bot.vbs` (also aliased KalshiBot.vbs)
- **Dashboard:** `http://localhost:3001` — React + Flask proxy at `C:\ZachAI\kalshi\dashboard\`
  - Auto-start: `scripts/WeatherAlpha_Dashboard.vbs`
- **Tunnel:** Cloudflare trycloudflare via `cloudflared.exe` for remote dashboard access
  - Auto-start: `scripts/WeatherAlpha_Tunnel.vbs`
- **Watchdog:** `scripts/watchdog.py` monitors all three, auto-restarts on failure
  - Auto-start: `scripts/WeatherAlpha_Watchdog.vbs`

## KEYS
- Location: `C:\ZachAI\kalshi\keys\` (gitignored)
- Never commit private keys. `.gitignore` must protect this dir before any push.

## CITIES
20 active (added 2026-05-05): NYC, CHI, MIA, LAX, DEN, AUS, ATL, BOS, DAL, WDC, HOU, LAS, MIN, NOL, OKC, PHX, SAT, SEA, SFO, PHL.
Each KXHIGH series ships 12 strike levels per day. Bot picks top edges system-wide; MAX_DAILY_TRADES (default 5) caps per-day exposure. Learning agent auto-pauses any city after 3/5 losses, so the lineup self-selects.

## API ENDPOINTS (`kalshi/bots/app.py`)
- `/api/health` — status + paper_mode + kalshi_connected
- `/api/status` — service state
- `/api/forecasts` — Open-Meteo forecasts per city
- `/api/trades` — trade log
- `/api/trades/verified` — verified trades only
- `/api/pnl` — P&L curve
- `/api/summary` — wins/losses/win_rate/total_pnl_usd
- `/api/today` — today's trades
- `/api/by-city` — P&L per city
- `/api/guardrails` — risk guardrail state
- `/api/guardrails/window-override` — manual override (POST)
- `/api/scan` — trigger scan (POST)
- `/api/scan/status` — last scan time + result
- `/api/resolve` — manual resolution (POST)
- `/api/decision-log` — full decision feed
- `/api/signals` — active signals
- `/api/equity-curve` — equity over time
- `/api/calibration` — forecast vs reality calibration
- `/api/positions` — open positions
- `/api/markets/browse` — Kalshi market browser

## TELEGRAM
- 8 AM digest (pre-market overview)
- 6 PM digest (daily wrap)
- Unrealized loss alert threshold: -$25
- `stale_prices` alerts silenced

## AUTO-MERGE EXCEPTION
Any task touching Kalshi credentials (`kalshi/keys/*`, `.env` files with Kalshi secrets) must commit and push but notify Zach BEFORE merging.
