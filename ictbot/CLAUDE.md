# ICTBOT — Project Brain

## OVERVIEW
TradingView paper-trading bot using ICT (Inner Circle Trader) concepts on a non-MNQ emini. Sister to ORB (`C:\ZachAI\trading\`) — **shares the TradingView Desktop CDP session on `:9222` with ORB** but on its own tab pinned to **MES1!**. ORB stays on MNQ1!. Each bot's `tv_client` filters by symbol/tab so they never collide.

Architecture (updated 2026-05-07): originally proposed dual-Chromium with a second CDP `:9223`; Zach asked to use TV Desktop directly. Order placement (Phase 2, when SCAN_ONLY=false) requires a cross-bot lock at `data/tv_cdp_lock` so ORB and ICTBot don't manipulate the chart at the same instant.

Separate from ORB:
- Separate process + PID lock + SQLite DB (`ictbot/state/trades.db`)
- Separate Telegram bot + channel (prefix `[ICTBot]`)
- Separate dashboard (`:3002`)
- Separate capital filter on the same TV paper broker (each bot reads only its own symbol's positions)

**Paper mode: ON** — `PAPER_MODE=true` in `ictbot/.env`. Going live requires Zach's explicit approval (one of the 3 hard stops in master CLAUDE.md).

## RELATIONSHIP TO ORB — READ FIRST
- **Never modify `C:\ZachAI\trading\`** for ICTBot work. ORB is profitable and untouchable.
- Both bots use Zach's same TradingView account, same paper broker, separate symbols (MNQ vs MES).
- Cross-bot risk halt lives in `C:\ZachAI\data\risk_state.json` (read by both, written by external sentinel).
- Telegram alerts use a SEPARATE bot + channel — prefix `[ICTBot]` so ORB notifications stay distinct.

## CURRENT STATUS
**Phase 1 — Scaffold + observe (in progress).** Foundation, no live trades yet.

What works:
- Project skeleton + CLAUDE.md
- Config + database schema
- ICT analyzer (FVG / sweep / MSS detection)
- Setup scanner (NY AM FVG)
- Dashboard skeleton
- Observe-mode (Telegram pings on setup detect, no order placement)

What does NOT work yet:
- Real TV paper trades (gated behind `SCAN_ONLY=false`, default true in Phase 1)
- Backtest harness with full historical data (stub only)
- Watchdog auto-restart
- Auto-start VBS not yet registered with Task Scheduler

## SERVICES + PORTS
| Service | Port | Status |
|---|---|---|
| Flask dashboard | `:3002` | Phase 1 |
| Live bot main loop | n/a (background process) | Phase 1 |
| Shared TV Desktop CDP | `:9222` (owned by ORB) | inherited |
| Auto-start bot VBS | `scripts/start_ictbot.vbs` | Phase 1 |

## KEY FILE PATHS
```
ictbot/
├── CLAUDE.md                       # this file
├── ACTIVE_FILES.md                 # manifest
├── .env                            # gitignored, Telegram + Anthropic + CDP_PORT
├── .env.example                    # template
├── requirements.txt
├── config.py                       # paper mode, capital, risk caps, killzones, symbol
├── main.py                         # APScheduler entry, PID lock
├── cli.py                          # status, health, last-trade
├── services/
│   ├── ict_tv_client.py            # CDP client to TV Desktop :9222 (shared w/ ORB)
│   ├── ict_tv_trader.py            # place_bracket_order on MES via :9222
│   ├── tv_data.py                  # read MES bars
│   ├── ict_analyzer.py             # FVG / sweep / MSS detection
│   ├── setup_scanner.py            # detected-setup combiner
│   ├── trade_manager.py            # open-position monitor
│   ├── telegram.py                 # separate bot + channel
│   └── state_manager.py            # SQLite + arm/halt status
├── strategies/
│   └── ny_am_fvg.py                # FIRST setup
├── agents/
│   ├── monitor.py                  # 30s wake during killzones
│   ├── briefing.py                 # 7:00 AM ET morning report
│   └── learning.py                 # nightly review
├── data_layer/
│   └── database.py                 # SQLite schema
├── dashboard/
│   ├── app.py                      # Flask :3002
│   └── templates/index.html
├── backtest/
│   ├── runner.py                   # replays bars through strategy
│   └── data_loader.py              # load historical CSVs
├── state/                          # gitignored runtime state
├── scripts/
│   ├── start_ictbot.vbs
│   └── ictbot_watchdog.py
├── docs/setups.md                  # ICT setup definitions
├── logs/                           # gitignored
└── tests/
```

## SYMBOL: MES1!
- Micro E-mini S&P 500
- $1.25/pt, ~$1,500 margin on TV demo
- Configurable via `ICT_SYMBOL` env (alternatives: M2K, MYM, 6E)

## HOURS — NY KILLZONES ONLY (Phase 1)
- **NY AM**: 08:30–11:00 ET (primary)
- **NY PM (Silver Bullet)**: 13:30–16:00 ET (added in Phase 3)
- **Hard close**: 14:55 ET — all positions closed via market

Phase 2+ will add London (02:00–05:00 ET) and Asia (20:00–00:00 ET) once NY edge proves out.

## STRATEGY STACK
**Phase 1 — Setup #1 only: NY AM FVG**
- HTF bias: 1H close vs 4H 50EMA
- Look for clean 5m FVG created by 9:30–10:00 displacement (gap ≥3 ES pts)
- Entry: market on first 5m close that retraces into the FVG
- Stop: opposite side of the displacement leg + 3 pt buffer
- TP: opposing liquidity (PD high/low) or 2R, whichever closer
- Skip: VIX>30, scheduled CPI/NFP/FOMC, position already open

**Phase 3 — additional setups added one at a time after Setup #1 proves out:**
- Silver Bullet (FVG entries in killzone windows)
- Judas Swing (9:30 sweep + MSS reversal)
- Sellside/Buyside Sweep (equal-highs/lows liquidity grab + reversal)

## RISK CAPS (active hard caps)
- **Position size**: 1 MES contract per trade (paper)
- **Per-trade max risk**: $150 — `MAX_RISK_PER_TRADE_DOLLARS`
- **Daily max loss**: $250 — `DAILY_LOSS_LIMIT_DOLLARS` (independent of ORB's $200)
- **Weekly max loss**: $500 — `WEEKLY_LOSS_LIMIT_DOLLARS`
- **3 consecutive losses**: pause day — `MAX_CONSECUTIVE_LOSSES=3`
- **Max trades/session**: 3 (one per killzone) — `MAX_TRADES_PER_SESSION=3`
- **One position at a time** — bot won't open #2 while #1 is live
- **VIX > 30**: pause day — `VIX_HARD_BLOCK=30`
- **High-impact news day**: CPI/NFP/FOMC scheduled in session window — pause day
- **Cross-bot halt**: `data/risk_state.json` flag = stand down

## ARM GATE (08:25 AM ET, before NY AM killzone opens at 08:30)
- Reads CDP `:9223` health, paper-broker connectivity, news-block, VIX
- Writes `state/arm_status.json` with `armed=true|false, source, reason`
- Monitor reads on every poll; sits out the day if `armed=false`
- **Manual override**: ask Jarvis "arm ictbot anyway"

## PAPER GUARANTEE
- `PAPER_MODE=true` env required in `ictbot/.env`
- `ict_tv_trader.place_bracket_order()` raises `RuntimeError` if `PAPER_MODE != "true"`
- Setting `PAPER_MODE=false` is one of the 3 hard stops in master CLAUDE.md

## OBSERVE MODE (`SCAN_ONLY=true`, default in Phase 1)
- Setup scanner runs normally
- Telegram pings on every detected setup
- `ict_tv_trader.place_bracket_order()` is NO-OP (logs the call but places nothing)
- Used to validate detector logic before flipping `SCAN_ONLY=false` in Phase 2

## TELEGRAM CHANNEL
- Separate bot via @BotFather (Zach picks the handle, e.g. `ICTBotJarvis`)
- Separate private channel
- Bot token + channel ID in `.env`, gitignored
- All messages prefixed `[ICTBot]`

## DASHBOARD
- Flask on `:3002`
- Sections: Live, Today's setups, Journal (last 30), Equity curve, Edge stats, Health
- Read-only — never places orders, never edits state

## FILE HYGIENE
- `state/trades.db`, `state/ictbot.pid`, `logs/`, `.env` are gitignored
- No `.pine` files (Pine scripts live in TradingView editor only)
- **Auto-merge exception:** changes to `services/ict_tv_trader.py` (live order placement) — commit + push but notify Zach BEFORE merging.

## 2026 HIGH-IMPACT CALENDAR (mirror ORB)
- **CPI** (8:30 AM): Jan 13, Feb 11, Mar 11, Apr 10, May 12, Jun 10, Jul 14, Aug 12, Sep 11, Oct 14, Nov 10, Dec 10
- **NFP** (8:30 AM): Jan 9, Feb 6, Mar 6, Apr 3, May 8, Jun 5, Jul 2, Aug 7, Sep 4, Oct 2, Nov 6, Dec 4
- **FOMC** (2:00 PM): Jan 28, Mar 18, Apr 29, Jun 17, Jul 29, Sep 16, Oct 28, Dec 9
