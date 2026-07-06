# WEATHERALPHA — Project Brain

## OVERVIEW
Kalshi weather prediction market trading bot. Trades between-markets on daily high/low temperature contracts across 20 US cities using Open-Meteo ensemble forecasts as edge signal.

- **LIVE real-money mode** (PAPER_MODE=false) since 2026-05-21, confirmed intentional by Zach. Flipping the mode either direction is still a hard stop — NEVER change without explicit approval.
- **DIRECTIONAL STRATEGY 2026-07-06 (supersedes the 6/10 and 6/23 entry rules).** 197-live-trade audit + settlement-vs-downtown-actual comparison (Open-Meteo ERA5 archive): Kalshi settles on NWS station obs, which ran HOTTER than the downtown actual in 68 of 88 disagreements (77%) — the downtown ensemble is structurally cold vs settlement. Direction, not distance, drives P&L: NO on bins ABOVE forecast = 109 trades, 47% WR, **-$83.29** (the loss engine); NO on bins BELOW forecast = 66 trades, 71% WR, **+$52.34**, positive in May AND June separately. Changes: (1) `NO_BELOW_ONLY=true` — NO trades only on 'between' bins with midpoint ≤ forecast high; 'greater' strikes also blocked for NO (1W/3L −$8.32); (2) `MIN_DISTANCE_FROM_FORECAST=0.0` — the 2°F outer-ladder filter was blocking the best segment (NO-below <2°F: +$45.21, 70% WR, n=43); the May audit's distance signal was confounded by direction; (3) `MIN_NO_PRICE_CENTS=30` (was 65) — the "cheap-NO bleed" was entirely cheap NO-ABOVE (30-49¢ above: 22% WR −$48.52); NO-below is profitable at 30-49¢ (78% WR +$24.36) and 50-64¢ (67% WR +$25.47), breakeven at 65-79¢.
- **MIN_EDGE DEADLOCK GUARD (2026-07-06).** `learning_agent.MIN_EDGE_CEIL` must stay BELOW `MAX_CLAIMED_EDGE` (0.15). Edges are clamped to the cap, so an agent-ratcheted MIN_EDGE ≥ the cap gates out every trade permanently and the 14-day P&L can never recover to lower it — this silenced the bot 2026-07-02→07-06 (min_edge hit 0.20). CEIL now 0.12; stored min_edge manually reset to 0.08 (journaled).
- Still in force from 6/10-6/29: `MAX_CLAIMED_EDGE=0.15` edge clamp; learning agent MIN_EDGE moves graded on rolling 14-day realized trade P&L/WR (not Brier); YES side disabled (`TRADE_YES=false`); NO priced at the NO ask.
- **DO NOT REPOINT CITY COORDS TO AIRPORT STATIONS.** Reverted 2026-05-25 evening after a 116-trade bin-position audit proved downtown coords are a structural feature of the strategy: pre-May-21 NO bets sat 2-4°F from forecast (outer ladder, 86% WR over 93 trades); airport coords pulled bets to <2°F from forecast (center ladder, 57% WR over 23 trades). Kalshi's strike ladder rewards distance from the center — the downtown forecast bias is the noise function that keeps the bot picking outer bins. The May 21 "fix" (commit fcc8131) was structurally wrong. If you ever want technically-correct station coords, you must first redesign the edge function to deliberately target outer-ladder bins (e.g., MIN_DISTANCE_FROM_FORECAST filter); never swap coords alone. Full evidence: `C:\Users\zedwa\.claude\plans\i-want-you-look-swift-panda.md`.

## SERVICES
- **Bot API:** `http://localhost:5000` — Flask app at `C:\ZachAI\kalshi\bots\app.py`
  - Auto-start: `scripts/WeatherAlpha_Bot.vbs` (also aliased KalshiBot.vbs)
- **Dashboard:** `http://localhost:3001` — React + Flask proxy at `C:\ZachAI\kalshi\dashboard\`
  - Auto-start: `scripts/WeatherAlpha_Dashboard.vbs`
- **Watchdog:** `scripts/watchdog.py` monitors and restarts bot + dashboard on failure
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
