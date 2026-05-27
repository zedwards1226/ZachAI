# WEATHERALPHA — Project Brain

## OVERVIEW
Kalshi weather prediction market trading bot. Trades between-markets on daily high/low temperature contracts across 6 US cities using Open-Meteo forecasts as edge signal.

- **LIVE real-money mode** (PAPER_MODE=false) since 2026-05-21, confirmed intentional by Zach. Flipping the mode either direction is still a hard stop — NEVER change without explicit approval.
- **DO NOT REPOINT CITY COORDS TO AIRPORT STATIONS.** Reverted 2026-05-25 evening after a 116-trade bin-position audit proved downtown coords are a structural feature of the strategy: pre-May-21 NO bets sat 2-4°F from forecast (outer ladder, 86% WR over 93 trades); airport coords pulled bets to <2°F from forecast (center ladder, 57% WR over 23 trades). Kalshi's strike ladder rewards distance from the center — the downtown forecast bias is the noise function that keeps the bot picking outer bins. The May 21 "fix" (commit fcc8131) was structurally wrong. If you ever want technically-correct station coords, you must first redesign the edge function to deliberately target outer-ladder bins (e.g., MIN_DISTANCE_FROM_FORECAST filter); never swap coords alone. Full evidence: `C:\Users\zedwa\.claude\plans\i-want-you-look-swift-panda.md`.

## SERVICES
- **Bot API:** `http://localhost:5000` — Flask app at `C:\ZachAI\kalshi\bots\app.py`
  - Auto-start: `scripts/WeatherAlpha_Bot.vbs` (also aliased KalshiBot.vbs)
- **Dashboard:** `http://localhost:3001` — React + Flask proxy at `C:\ZachAI\kalshi\dashboard\`
  - Auto-start: `scripts/WeatherAlpha_Dashboard.vbs`
- **Tunnel:** Cloudflare trycloudflare via `cloudflared.exe` for remote dashboard access
  - Auto-start: NOT WIRED (audit 2026-05-27 — `scripts/WeatherAlpha_Tunnel.vbs` does not exist;
    tunnel must be started manually until the launcher is written)
- **Watchdog:** `scripts/watchdog.py` monitors bot + dashboard, restarts bot on failure
  - Auto-start: `scripts/WeatherAlpha_Watchdog.vbs`

## AUDIT NOTES — 2026-05-27 (read before touching watchdog)
The 2026-05-27 audit found three gaps in the WA monitoring stack:
1. `scripts/WeatherAlpha_Tunnel.vbs` is referenced in this CLAUDE.md but does NOT exist. The cloudflared tunnel currently has no auto-start. After every reboot, it must be launched by hand.
2. `scripts/watchdog.py::check_dashboard()` only **alerts** when :3001 is down; it does **not restart** the dashboard VBS. The dashboard was found dead at audit time (recovered manually by `cscript WeatherAlpha_Dashboard.vbs`). Mirrors the pattern in `scripts/orb_watchdog.py::check_orb_dashboard()` which DOES restart — port that pattern over when fixing.
3. `scripts/watchdog.py` has no `check_tunnel()` function at all. The tunnel can die silently.

These three items are tracked separately and were NOT fixed in the audit (audit was read-only on WA behavior per the cleanup plan). Open a follow-up to fix all three together.

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
