# OMNIALPHA — Project Brain

## OVERVIEW
24/7 multi-sector Kalshi prediction-market bot. Sister to WeatherAlpha (`C:\ZachAI\kalshi\`) but **completely independent** — separate process, separate SQLite DB, separate Telegram channel suffix, separate capital allocation.

WA proves the edge thesis: structural mispricing on narrow / long-shot YES contracts where retail overprices the "fun" outcome. OmniAlpha generalizes that thesis across sectors (crypto, sports, politics, economics) and sectors that are 24/7-tradeable (so the bot is always working, not gated to one daily weather cycle).

**Paper mode: ON** — `PAPER_MODE=true` in `omnialpha/.env`. Going live requires Zach's explicit approval (one of the 3 hard stops in master CLAUDE.md).

## RELATIONSHIP TO WEATHERALPHA — READ FIRST
- **Never modify `C:\ZachAI\kalshi\`** for OmniAlpha work. WA is profitable and untouchable.
- Both bots use Zach's same Kalshi credentials but separate state/DB.
- Cross-bot risk coupling lives in `C:\ZachAI\data\risk_state.json` (read by both, written by neither yet — design TBD).
- Telegram alerts use the same Jarvis bot but prefix messages `[OmniAlpha]` so WA notifications stay clean.

## CURRENT STATUS
**Phase 1 — Scaffold (in progress).** Foundation only. NO live strategies, NO order placement, NO authenticated API calls beyond `health` check.

What works:
- Project structure + CLAUDE.md
- Reference repos cloned (`reference/ryanfrigo-kalshi-bot`, `reference/joseph-pm-calibration`, `reference/roman-kalshi-btc`)

What does NOT work yet:
- No strategies
- No live trading
- No backtest engine
- No dashboard data
- No auto-start

## SERVICES + PORTS (planned)
| Service | Port | Status |
|---|---|---|
| Streamlit dashboard | `:8502` (WA dashboard owns `:3001`, ORB watchdog has none, Jarvis approval is `:8765`, Kalshi WA API is `:5000`) | TBD |
| Live bot main loop | n/a (background process) | TBD |
| Auto-start VBS | `scripts/OmniAlpha.vbs` | TBD |

## KEY FILE PATHS (planned)
```
omnialpha/
├── CLAUDE.md                      # this file
├── ACTIVE_FILES.md                # manifest (every file Zach has)
├── .env                           # gitignored, has KALSHI keys + Anthropic key
├── .env.example                   # template
├── requirements.txt
├── config.py                      # paper mode flag, capital, risk caps
├── main.py                        # entry point (APScheduler)
├── cli.py                         # status/health/scores commands
├── bots/
│   ├── kalshi_client.py           # signed REST + WebSocket
│   └── kalshi_public.py           # unauthenticated /historical/* puller
├── data_layer/
│   ├── database.py                # SQLite schema (trades, signals, decisions, costs)
│   ├── events_scanner.py          # live universe scanner
│   └── historical_pull.py         # backtest data ingest
├── strategies/                    # one file per strategy
├── backtest/
│   └── runner.py                  # replay historical trades through strategies
├── dashboard/
│   └── app.py                     # Streamlit
├── state/                         # gitignored runtime state
├── logs/                          # gitignored logs
└── tests/
```

## DATA SOURCES — ALL FREE
- **Kalshi REST + WebSocket** (authenticated): live markets, orders, positions
- **Kalshi `/historical/markets`** (unauthenticated): all settled markets w/ outcomes
- **Kalshi `/historical/trades`** (unauthenticated): tick-level trade history
- **Kalshi `/historical/cutoff`** (unauthenticated): data-availability check (currently ~2-month lag)

No paid data feeds. No PMXT relay. No third-party data brokers. Everything Zach needs is on Kalshi's own public endpoints.

## STRATEGY STACK (planned, NOT yet implemented)
1. **Behavioral-bias scanner** — finds NO-side overpricing on long-shots, narrow-range mispricing (WA's thesis generalized)
2. **Theta harvesting** — far-OTM long-dated NO positions on conditional events
3. **News reaction** — sentinel-driven (uses `C:\ZachAI\trading\state\sentinel.json` shared with ORB)
4. **5-gate pre-trade filter** — Kelly / Liquidity / Correlation / Concentration / Drawdown (stolen from OctagonAI/kalshi-trading-bot-cli)
5. **CLV grading** — auto-pause underperforming sectors (mirrors WA's learning-agent city pause)
6. **Hedge-to-lock** — buy opposite side at favorable price to lock partial profit, free capital faster

## RISK CAPS (paper, $500 bankroll, growth-with-risk-management)
- Starting capital: $500 (paper)
- Per-trade max risk: $25 (5% of starting capital; matches Kelly 0.05 frac × $500 exactly so the cap doesn't artificially clip)
- Daily max loss: $50 (10% of starting capital — circuit breaker, halts new entries for the day)
- Weekly max loss: $100 (20% of starting capital — kill switch)
- Max concurrent positions: 8
- Max trades per sector per day: 20 (three crypto strategies share the sector)
- Sectors must be enabled per-sector via config — opt-in, not opt-out

Capital scales naturally with realized P&L: `capital_usd = STARTING_CAPITAL_USD + realized − open_risk`, and Kelly stake recomputes off the live capital each scan. As the account grows, position sizes grow with it; the absolute USD caps stay fixed until the next review (re-tune when capital crosses 1.5× starting).

Subject to revision as the bot proves itself in paper.

## PROTECTIONS / AUTO-MERGE EXCEPTIONS
- **Don't touch `C:\ZachAI\kalshi\`** for OmniAlpha work — period.
- Once strategies + live order placement are added, that file becomes auto-merge exception list (parallel to ORB's `tv_trader.py` rule). Until then, normal flow.
- `PAPER_MODE=true` is enforced in `bots/kalshi_client.py` — going live requires explicit approval same as ORB / WA.

## REFERENCE REPOS (read-only, in `C:\ZachAI\reference\`)
- **`ryanfrigo-kalshi-bot/`** — toolkit pattern, MIT, very recent. Source for kalshi_client, ingest, dashboard scaffold, SQLite schema. Borrow patterns; don't fork wholesale.
- **`joseph-pm-calibration/`** — Brier score + calibration pipeline, public Kalshi historical endpoints. Source for backtest analysis.
- **`roman-kalshi-btc/`** — KXBTC15M binary up/down puller. Source for crypto sector v1.

## OUT OF SCOPE (do NOT add without Zach's say-so)
- Live trading (paper only until 30+ paper trades + Zach's explicit OK)
- Cross-platform arbitrage (Polymarket integration is heavy + adds risk surface)
- Market making (capital + latency game; not solo-friendly at this scale)
- Custom React/Vue dashboard (Streamlit is the call per master brief)
- MQTT broker / multi-node orchestration (premature at 4 bots; revisit at 8+)

## OPEN ITEMS / NEXT STEPS
1. Finish Phase 1 scaffold (this branch): config, DB schema, kalshi_public.py historical puller, dashboard skeleton, smoke test
2. Phase 2: build first sector strategy (likely crypto via KXBTC15M — simplest 24/7 entry point)
3. Phase 3: paper-mode live with 1 strategy, observe 7+ days
4. Phase 4: add second sector (sports), CLV grading, hedge primitive
5. Phase 5: discuss live-mode criteria with Zach (NOT before)
