# Session Log

---

## 2026-05-21 (Late night — ORB balance-discrepancy alert: root cause + re-baseline)

Zach: "go read the telegram alerts it sent me." The repeating alert was the ORB
**balance-discrepancy** watchdog alert ("ORB HIDDEN GAIN $313.09", real broker
$4,192.42 vs journal-computed $3,879.33).

**Cause (Zach was right — NOT my dummy testing):** orb_balance_discrep first
flipped False at **12:22 today**, when trade #34 closed — hours before tonight's
Phase-2 dummy tests. Root cause is the pre-Phase-1 bug: the journal booked exits
at theoretical SL/T2 levels (conservative, over-counts losses) instead of real
fills, so journal-computed capital drifted ~$313 BELOW the real broker balance.
I initially mis-blamed my testing; corrected after checking the log timeline.

**Fix (commit 2af3a1d, pushed):** verified TV genuinely flat (acct margin 0,
unrealized 0, no position). Re-baselined via an auditable offset:
- `trading/state/journal_baseline.json` = {adjustment_usd: 313.09, reason, set_at,
  real_balance_at_set 4192.42} — gitignored (machine-local state).
- `serve.py` `_baseline_adjustment()` reads it; `computed_capital = starting +
  lifetime_pnl + adjustment`. Restarted dashboard.
- Verified: untracked_pnl $0.00, watchdog orb_balance_discrep back to True
  (22:49 cycle). Telegram spam stops. Future REAL gaps still trip the $50
  threshold (offset is fixed). Phase 1 keeps journal/broker in sync going fwd.

**Phase 1/2 status (from earlier this session):** Phase 1 (read real exit fills
from TV order history) LIVE + tested + pushed. Phase 2 (real TV trailing stop,
modify_stop_on_tv) PROVEN manually (moved a paper stop 29,440→29,495) + built +
unit-tested, but staged OFF (`USE_REAL_TV_STOP=False`) — the automated
working-order finder needs live hardening against a real bot trade at the open
(Modify control renders on row ACTIVATION, not hover). Finish + verify at 9:30.

---

## 2026-05-21 (WeatherAlpha live-status check + MD sync)

Zach asked "how the weather bot do today." WeatherAlpha is **LIVE real money**
(PAPER_MODE=false) — went live 2026-05-18, confirmed again intentional today.

**Today's performance (live):** +$4.22 realized (3 of 5-20's positions resolved
as wins: WDC +$2.59, LAX +$0.90, HOU +$0.71). 7 new positions opened, all open,
+$8.52 unrealized. Capital $76.86, at-risk $22.86 (cap $30.74), 7/7 daily trades,
0 consecutive losses, not halted. Lifetime live ~80% WR, +$15.04.

**Note:** `/api/today` counts by ENTRY date so it showed $0 wins; realized PnL
from prior-day positions resolving lands in `/api/guardrails` daily_pnl_usd.

**MD sync (per Zach's request to document live status):** auto-memory
`project_weatheralpha.md` and `kalshi/CLAUDE.md` both still said "paper mode ON"
— corrected both to LIVE (false-alarmed earlier because of the stale note).

### ROOT-CAUSE: 3 losses today = LOCATION BUG (not variance). FIXED.

Zach asked why HOU/LAX/DEN lost when "everything lined up." Investigation:
- Bot fetched Open-Meteo forecasts at **downtown** city coords, but Kalshi
  settles high-temp markets on a specific **NWS ASOS station** (from each
  series' `rules_primary`). LAX settles on the cool coastal **airport** —
  downtown 81° vs airport 70°, a 10°+ gap. Bot bet ">75 YES" at 88% conf on
  downtown temps; airport settled ≤75 → loss. HOU/DEN similar.
- Confirmed at portfolio level: every 100%-win city is inland (downtown≈
  station); every live loss (LAX, MIA, PHX) is a coastal/microclimate city.
- Live trades settle on Kalshi's real result (`trader.py:792`), so the W/L
  record + 72%-accuracy/0.22-Brier calibration are ground truth.

**FIX 1 — coords (commit fcc8131, pushed):** repointed all 20 cities'
lat/lon in `kalshi/bots/config.py` to their Kalshi settlement stations,
pulled authoritatively from each series' `rules_primary` via Kalshi public
API (`/trade-api/v2/markets?series_ticker=...`). Stations are NOT uniform:
NYC=Central Park (not airport), CHI=**Midway** (not O'Hare), LAX/MIA/most=
airport. Verified bot now reads LAX at airport coords → 72.5° not downtown
81°. Single source of truth (weather.py + trader.py both read CITIES).

**FIX 2 — calibration floor (commit a288ccb, pushed):** the per-city/side
shrinkage table was trained on ALL history (paper+live), every trade made
at the WRONG downtown coords → mis-taught confidence. Added
`CALIBRATION_DATA_FLOOR=2026-05-22` in config.py + `AND timestamp >= ?` in
`calibration.py` so it only learns from correctly-located trades. Table now
falls back to neutral global 0.25 until clean data accumulates (~5-23+).

**Calibration design note (for future):** system already distrusts risky
YES/directional bets (high shrinkage) and trusts narrow-band NO bets (0.05
shrink, ~100% base-rate wins). The bot's edge is structural (selling narrow
NO bands), NOT sharp forecasting. Do NOT tune shrinkage params until clean
post-fix data accumulates — tuning on buggy-location data bakes error in.

**Verified clean:** 20 unique cities no dupes, no old coords anywhere, no
override in .env, no on-disk cache, single bot/dashboard/watchdog process
(no restart zombies). Bot live: paper_mode=false, kalshi_connected=true.
Note: cloudflared tunnel NOT running (remote dashboard only, pre-existing).
Today's 7 open positions were placed at OLD coords — left alone, settle 5-22.

---

## 2026-05-20 (Morning/Eve — ORB pause diagnosis, ALL limits off, WeatherAlpha scale-up + capital-gate fix)

**ORB "why is it paused" — NOT the phantom bug (that fix held):** Verified live
this morning ORB was armed, flat, no phantom, combiner polling. It was paused on
the **weekly loss limit** (−$578 vs −$350 cap). Cause: one 2026-05-19 12:10 SHORT
lost −$624.62 — a ~310pt-risk trade that should've been blocked, but the soft
per-trade cap is disabled (`RISK_CAP_ENABLED=False`) and the hard ceiling was
$700 > the daily/weekly caps, so ONE trade blew the week.

**Zach: "erase all fucking limits" (paper money).** Disabled every ORB
risk/loss limit (commit on master, NOT pushed):
- config.py: MAX_TRADES_PER_SESSION 1→999999, DAILY_LOSS_LIMIT 200→1e9,
  WEEKLY_LOSS_LIMIT_PCT 0.07→1e6, MAX_RISK_PER_TRADE 350→1e9,
  HARD_PER_TRADE_RISK_CEILING 700→1e9, DAILY_PROFIT_TARGET 200→1e9,
  MAX_CONSECUTIVE_LOSSES 3→999999, VIX_HARD_BLOCK 30→100000.
- combiner.py `_check_hard_blocks()` short-circuited to return None (VIX +
  CPI/NFP/FOMC news-day blocks off). Originals preserved in comments.
- PAPER_MODE=true UNTOUCHED (hard stop). Restarted ORB (PID 17576), verified
  all values loaded. Trade management (trailing/BE/time exits) left intact.

**WeatherAlpha is LIVE real money** (PAPER_MODE=false, production Kalshi,
KALSHI_DEMO=false, ~$85 start). Zach confirmed this is intentional. He ran it
paper for a month (through 5-15), went live 5-18.
- Balance: $75.90 cash + ~$19 open = ~$95 equity. Live P&L +$10.82 over 15
  trades (5-18 +$8.37, 5-19 +$2.45, 5-20 5 open). 77.8% WR. Up ~13% in 3 days.
- Trade history confirms: NEVER traded >5/day, paper or live (cap held).
- **Scaled MAX_DAILY_TRADES 5→7** in kalshi/.env (LIVE, Zach approved "go").
  Restarted bot, verified loaded. ~$3.30/trade, edges plentiful (constraint was
  the cap, not edge supply). Takes effect tomorrow 6 AM CST.
- **Fixed 6 AM capital stall** (kalshi/bots/guardrails.py
  `check_capital_at_risk`): it summed ALL open trades incl. yesterday's
  not-yet-settled positions, eating the 40% at-risk budget until ~6:30
  settlement → delayed today's entries. Now excludes prior-day (closed-market)
  positions via UTC date compare; only today's count. Restarted, imports clean.
- NOL 5-19 trade still "open" = Kalshi hasn't settled it yet (market closed,
  result blank, expiration 5-26). Actual NOLA high was 86.4°F vs 90-91 band →
  NO bet should WIN (~+$0.66). Bot auto-books when Kalshi posts result. Normal.
- Weather settlement lag (>24h) is by design: Kalshi grades off official NWS
  CLI daily report w/ a multi-day settlement window.

**Cities:** WeatherAlpha expanded from 5 → 20 cities on 2026-05-05; that's why
trades jumped from 1-4/day to a consistent 5/day (more markets = always 5 edges).

**OPEN ITEMS for next session:**
- UNPUSHED local commits on master (await Zach "push it"): ORB phantom fix +
  baseline removal + ORB limits-off + session logs. guardrails.py weather fix
  also pending commit. kalshi/.env (cap=7) is gitignored — machine only.
- **weatheralpha.db is 9 GB** — badly bloated (signals/decision_log per-scan
  rows). Real disk/perf risk. Offered to trim, not yet done.
- Verify tomorrow 6 AM CST that the capital-gate fix lets all 7 fire at open
  (not stalling to 6:30). Just check trade timestamps in the DB.
- Plan-mode flag was stuck "active" all session but edits/commits/restarts all
  went through (enforcement not holding). Flagged to Zach.

---

## 2026-05-19 (Evening — recurring false phantom-position bug: ROOT CAUSE + fix)

**Symptom:** After a PC restart, ORB watchdog fired STATE DRIFT — broker_state
showed `tv_position_count: 1` while bot was flat. Zach: "nothing was open last
night either, same shit, fix it — I thought we went through the whole code."

**Ground truth (via live TV account-manager scrape):** account was FLAT.
Account margin $0.00, Unrealized PnL $0.00, zero position rows. Balance was
$4,250.16 ONLY because of −$749.84 cumulative *realized* (closed) losses.

**Root cause:** `tv_get_positions()` decided "position open" from
`available_funds < 90% × $5000` baseline. The baseline (`_flat_baseline_avail`)
is an in-memory global that RESETS to hardcoded STARTING_CAPITAL ($5000) on
every reboot. Once realized losses pushed the real account below $4,500, the
heuristic was permanently true after any restart → fabricated a phantom every
reboot, tripped the circuit breaker, blocked ALL trading. Also scraped
whole-page innerText → latched onto Strategy-Tester margin numbers when the
broker panel wasn't the visible tab (the flapping True/False).

**Fix (commits d906c3f + 9da74d0, on master — NOT pushed, awaiting Zach OK
per tv_trader.py auto-merge exception):**
- `tv_get_positions()` now reads the broker's own **Account margin** from the
  Account Manager panel (0.00 == flat, independent of balance). Auto-opens the
  "Paper Trading" tab if panel missing; returns `panel_unavailable` (reconcile
  skips) rather than fabricating. Uses `evaluate_async` (async IIFE).
- `_has_open_position()` delegates to the same signal — fixed two latent bugs:
  pre-trade gate refusing all orders, and close_position opening a phantom
  short on a flat account.
- `STRONG_PHANTOM_SIGNALS` now keys on `acct_margin_open`.
- Removed dead `_flat_baseline_avail` global + `POSITION_OPEN_FUNDS_THRESHOLD`
  config constant + unused imports ("take baseline out").

**Verified end-to-end (live):** new ORB process PID 10308 wrote correct
broker_state (`acct_margin_flat`, $4,250.16, count 0); watchdog all-green
(orb_state_drift True, orb_balance_discrep True after stale transient cleared,
gap only −$12.83). Zero circuit-breaker/phantom log lines post-restart. 15
tests pass (6 new `test_tv_position_detection.py` + 9 recovery). 8 unrelated
combiner/cascade test failures are PRE-EXISTING on master (AttributeError in
fixtures), not from this change.

**Also this session:**
- WeatherAlpha dashboard (:3001) didn't auto-start after reboot (API :5000 +
  monitor came up, dashboard serve.py didn't). Relaunched via
  `WeatherAlpha_Dashboard.vbs` → PID 1504, verified "War Room" UI + API 200.
- Dashboard links confirmed: ORB http://localhost:8502, OmniAlpha
  http://localhost:8503, WeatherAlpha http://localhost:3001.
- Explained WeatherAlpha edge to Zach (no code change): 31-member GFS ensemble
  prob vs Shin-adjusted Kalshi price; MIN_EDGE 0.08 (YES 0.15), 25%
  shrink-to-market, 15% fractional Kelly. YES side historically anti-predictive
  (GFS hot-tail over-extrapolation) — flagged as the part to watch.

**OPEN ITEM for next session:** 2 commits (d906c3f, 9da74d0) sit on master
LOCAL ONLY — awaiting Zach's approval to push (tv_trader.py = live-execution
auto-merge exception). Running bot already has the fix loaded from disk.

---

## 2026-05-10 (Morning — Jarvis bot 32-hour outage: root cause + auto-restart fix)

**Symptom:** Zach said "everything is off". Actually only Jarvis Telegram bot
was down — had been silent since 2026-05-09 01:33:12 (~32 hrs). ORD Trading
Alerts channel was firing hourly "Jarvis Telegram bot dead" notices the
whole time.

**Root causes (two independent bugs that compounded):**
1. `scripts/orb_watchdog.py:check_jarvis_bot()` only ALERTED, never restarted —
   asymmetric vs sibling `check_orb_main()` which auto-restarts ORB.
2. `scripts/Jarvis_Bot.vbs` invoked bare `pythonw bot.py`. Bare `pythonw` isn't
   on PATH in non-interactive contexts (Bash/cmd spawns), so even if the
   watchdog HAD called the VBS, it would have silently failed.

**Fixes (committed e883318, pushed to master):**
- `Jarvis_Bot.vbs`: use full path `C:\Python314\pythonw.exe`
- `orb_watchdog.check_jarvis_bot()`: added auto-restart mirroring
  `check_orb_main` (alert → start_vbs → re-check → resolved/fail)

**Verified end-to-end:**
- Manual restart: bot back online 08:41:38 (PID 5804 → later 28908 after kill-test)
- Watchdog sees it: `jarvis_bot: True` from 08:42:01 onward
- Kill-test: stopped bot 08:44:40 → watchdog detected 08:45:36 → respawned 08:45:37
  (~57s end-to-end, fully autonomous)

**Security finding:** bot.log (41 MB, no rotation) had Telegram token
`8671092372:AAGl…` in plaintext on every getUpdates line. Truncated the log;
prompted Zach to rotate token via @BotFather. `.gitignore` already covers
`*.log` and `.env` so token never reached GitHub.

**Pending Zach approval:**
- bot.py log rotation (RotatingFileHandler, 10 MB × 3 backups). Diff prepared,
  CLAUDE.md protection rule requires explicit sign-off before edit.

**Why bot died at 01:33 on 5/9:** unknown. Event Viewer had no relevant
entries (likely needed elevation). Daily 2 AM snapshot job is a suspect but
unconfirmed. Auto-restart now covers it regardless.

---

## 2026-04-24 (Evening — Kalshi audit + Tier 1/2/3 fixes + 'less' strike block)

**Worked on:**
- Dispatched audit agents on `kalshi/` to find bugs, dead code, what's working vs broken
- Built 3-tier triage plan in `lets-go-over-the-glimmering-frost.md` (renamed "Zack's Weather Bot")
- Tier 1: Removed MEM city from `config.py` (Kalshi doesn't publish KXHIGHMEM, 255+ rate-limit errors, zero trades)
- Tier 1: Added TEST market guard in `trader.py` resolver loop (`if "TEST" in mkt_id.upper(): continue`)
- Tier 2: Audited watchdog restart path — fixed restart loop bug where `_api_failures` counter never reset on probe exception
- Tier 2: Narrowed reconcile-probe exception in `trader.py` to `(RequestException, ValueError)` (auth errors will now surface in live mode instead of being swallowed)
- Tier 2: Replaced fragile `checks.pop(0)` in `guardrails.py` with conditional append — paper mode no longer depends on list index
- Tier 3: Added `threading.Lock` around calibration cache refresh — concurrent threads can't double-trigger the DB query
- Tier 3 SKIPPED (verified false alarms): `kalshi_client.py` already has `timeout=10` everywhere; `get_guardrail_state` already wraps INSERT+SELECT in single transaction via `with get_conn()`
- Backtested deferred trade-gating rules from prior plan — only 'less' strike block survived data check
- Added `BLOCK_STRIKE_TYPES` config + `check_blocked_strike()` guardrail (default "less")
- Refreshed `kalshi/ACTIVE_FILES.md` — added calibration.py, learning_agent.py, missing tests; fixed stale .bat→.vbs and kalshi.db→weatheralpha.db paths

**Decisions made:**
- DROPPED MEM permanently rather than adding backoff — Kalshi doesn't list the series, backoff just delays the same dead end
- KILLED sub-20¢ entry block — backtest showed slice was net +$0.50 (one $95 win at 5¢ YES-greater offset 12 small losses); blocking would have cost ~$62
- KILLED YES-side strike guard — redundant once 'less' block is in place
- ONLY 'less' strike block shipped: lifetime 0W-10L, -$80.94, zero offsetting wins → pure loss pattern
- Honesty over plan adherence: when audit findings contradicted original triage, said so and updated rather than shipping speculative changes

**What worked:**
- All targeted fixes landed clean, no test breakage
- Backtest before ship caught two rules that would have lost money
- Audit agents surfaced real bugs (MEM, watchdog counter) plus two false alarms (timeouts, transactions) — verified each before acting

**Commits pushed to master:**
- `aacc95f` — kalshi+watchdog: post-audit triage fixes (MEM removal, reconcile narrow, calibration lock, watchdog counter reset, pop(0) replacement, TEST guard)
- `39bc0af` — kalshi: block 'less' strike type (0W-10L lifetime pattern)

**Structural changes:**
- `kalshi/config.py` CITIES dict: 6 → 5 cities (MEM removed)
- New env: `BLOCK_STRIKE_TYPES` (default "less")
- `kalshi/ACTIVE_FILES.md` refreshed and accurate

**Lessons (added to jarvis_brain):**
- BACKTEST BEFORE SHIP — audit-suggested rules can look correct but contradict actual P&L slices. Always run a SQL check on resolved trades before adding a guardrail.
- VERIFY AGENT CLAIMS — audit agents flagged "no HTTP timeouts" and "split-transaction race" that were both already correct in code. Read the file before acting on agent findings.
- DEAD MARKETS, NOT DEAD CODE — when an integration produces zero results + repeating errors, the market may not exist. Don't add retry/backoff to nothing.

**Next steps:**
1. Watch 24h paper run — confirm zero "Cannot parse market_id" errors, zero MEM rate-limits
2. After 30 more resolved trades, revisit YES-side over-confidence pattern with fresh data
3. If Brier score for YES side stays > 0.4 after 'less' block, consider raising MIN_EDGE_YES from 0.15

---

## 2026-04-21 (Evening — cleanup + ORB fix + Kalshi visibility)

**Worked on:**
- Cleaned up duplicate/orphan files (tradingview-mcp/, cloudflared.exe, dropship/, _research/, precisionfittedparts/, 6 root logs, 8 worktrees)
- Created `C:\ZachAI\sandbox\` — strict-isolation experiments workspace with 7 hard rules (ports 8000-8999, no cross-imports, no VBS, PAPER_MODE=True, per-experiment CLAUDE.md)
- Scaffolded `companies\tradingagents\CLAUDE.md` (status: BUILDING)
- Diagnosed ORB 2-week trade drought: Paper Trading broker silently disconnected → `side_not_found` → journal phantoms → no Telegram
- Rewrote `preflight.py::_check_paper_broker()` — picker-first logic, eliminates false negatives from panel toggle
- Added `journal.mark_failed_placement()` — auto-cleans phantom OPEN rows
- Updated `tv_trader.py` — `(bool, reason)` tuple return + loud Telegram on every failure branch + auto-mark journal
- Cleaned phantom trade id=3 to FAILED_PLACEMENT
- Diagnosed Kalshi Telegram silence: bot WAS alive all day (480 signals scanned, 478 skipped by guardrails), but `send_telegram()` was fire-and-forget with no receipts
- Added HTTP status logging to `monitor.py::send_telegram()` (status=200 / non-200 body logged)
- Added `database.get_today_signal_stats()` + heartbeat line to every digest
- Verified `scripts/watchdog.py::check_monitor_alive()` already monitors monitor.py (no VBS change needed)

**Decisions made:**
- Sandbox goes on `C:\ZachAI\sandbox\` (own CLAUDE.md, ACTIVE_FILES.md, _template folder)
- precisionfittedparts/ DELETED outright rather than scaffolded — Zach moved on
- Preflight broker check returns informational PASS on `no_side_no_picker` (common after hours, don't fail loudly for ambiguity)
- Kept kalshi EOD digest heartbeat in monitor.py (not scheduler.py) since digest lives there

**What worked:**
- Preflight dry-run: 6/6 PASS with Telegram delivery confirmed
- Kalshi `send_telegram()` test: status=200 logged correctly
- `get_today_signal_stats()` returned 480 scanned/2 opened/478 skipped — proving bot WAS alive
- Full EOD digest fired with heartbeat line, text_len=781

**Commits pushed to master:**
- `19aebfe` — sandbox + tradingagents scaffold
- `414a86f` — ORB loud broker-disconnect alerts + phantom cleanup (tv_trader.py — Zach pre-approved "ok do it smh")
- `5163cf7` — kalshi send_telegram receipts + daily heartbeat

**Structural changes (reflected in master CLAUDE.md):**
- Added sandbox/ to PROJECT ROSTER + FOLDER STRUCTURE
- Removed precisionfittedparts/ line
- Added companies\tradingagents\ + companies\wpflow\ + companies\zacks-work-drawings\ entries

**Next steps (tomorrow 2026-04-22):**
1. 7:00 AM — preflight fires with new paper-broker check
2. 9:30 AM — market open. First signal either places real trade OR fires loud `❗ Order placement FAILED` Telegram with reason + reconnect steps
3. 8:00 AM + 6:00 PM — Kalshi digests with heartbeat line + HTTP status receipts
4. Verify auto-cleanup of any phantom journal rows (FAILED_PLACEMENT)

---

## 2026-04-06 (Evening — continued)

**Worked on:**
- Audited all of C:\ZachAI — found 14 active plugins, no real agents, 5 MCP servers
- Cleaned up Windows Startup folder — removed duplicates, set 5 services to auto-start on reboot:
  - KalshiBot.vbs, WeatherAlphaDashboard.vbs, WeatherAlphaTunnel.vbs, PaperTrader.vbs, Jarvis.vbs
- Added SESSION START / SESSION END rules to CLAUDE.md
- Created C:\ZachAI\memory\ folder and session log
- Set up Jarvis (Claude Channels via Telegram plugin) with new bot token @ZachJarvis_bot
- Confirmed bun server works ("polling as @ZachJarvis_bot")
- Pre-approved Zach's Telegram ID (6592347446) in access.json — no pairing needed
- Wrote Startup VBS: Jarvis.vbs launches start_claude_channel.vbs on reboot

**Decisions made:**
- Jarvis = Claude Channels (full Claude Code session in Telegram), NOT chat_bot.py
- New bot token: 8671092372 (ZachJarvis_bot) for Jarvis
- Old bot token: 8239895020 (Dillionai_bot / ZachAI Commander) — external, ignore it
- dmPolicy set to "allowlist" with Zach's ID pre-approved — no pairing flow needed

**Next steps (tomorrow):**
1. Make sure test_jarvis.bat is CLOSED
2. Double-click C:\ZachAI\start_claude_channel.vbs
3. DM @ZachJarvis_bot — should say "Paired! Say hi to Claude." then work
4. If typing indicator shows but no response: check for 409 conflict (two bun instances)
   - Fix: taskkill /F /IM bun.exe then re-run start_claude_channel.vbs

**Notes:**
- Zach's Telegram ID: 6592347446
- access.json location: C:\Users\zedwa\.claude\channels\telegram\access.json
- Approved marker: C:\Users\zedwa\.claude\channels\telegram\approved\6592347446
- The "typing then goes away" bug = two bun instances conflicting (test_jarvis.bat still open)

---

## 2026-04-20 — ICT Research Lab scaffold + API key provisioned

**Worked on:**
- Fixed ORB morning preflight cosmetic bug: `trading/config.py` DEFAULT_SYMBOL `MNQ1!` → `CME_MINI:MNQ1!` (commit 911cafd on master). Preflight now returns all_ok=True.
- Scaffolded `companies/ict-research/` — CLAUDE.md + ACTIVE_FILES.md + README.md + .gitignore (commit 7d2e41b on branch `ict-research-scaffold`). 7-agent pipeline design: Harvester → Librarian → Extractor → Coder → Backtester → Judge → Bot Builder.
- Installed GitHub CLI via winget (gh 2.90.0 at `C:\Program Files\GitHub CLI\gh.exe`).
- Created Google Cloud project `ict-research` (ID: ict-research-493911), enabled YouTube Data API v3, generated API key.
- Saved `YOUTUBE_API_KEY=AIzaSyAiVFlOjcbJ0-0lJvi-BKm8uWe3O4sD2YY` to `companies/ict-research/.env` (gitignored).
- Sanity test passed: ICT channel (`UCtjxa77NqamhVC8atV85Rog`, @innercircletrader) returns valid JSON.

**Decisions made:**
- ICT bot promotion criteria (all must pass): ≥100 trades, walk-forward 2020-2024→2025, Sharpe>1.0, MaxDD<20%, PF>1.5, beats buy-and-hold, matches ORB or better.
- Composite rank: `0.4*Sharpe + 0.3*PF + 0.2*(1-MaxDD) + 0.1*winrate`
- 4 reference repos to clone next session (into `C:\ZachAI\reference\`, gitignored):
  - ajaygm18/ict-trading-ai-agent
  - Therealtuk/SmartMoneyAI-SMC-Trading-Dashboard
  - Ad1xon/AI-Algorithmic-Trading-Backtester
  - Dennis-1am/YT_Metadata_Downloader (Harvester base)

**Next steps (new session):**
1. Clone 4 reference repos to `C:\ZachAI\reference\`
2. Build Harvester agent (YouTube transcript puller for @innercircletrader)
3. Librarian → Extractor → Coder → Backtester → Judge in sequence
4. Merge `ict-research-scaffold` branch to master after Harvester lands

**Security flag:**
- YouTube API key was pasted in chat transcript. Key is restricted to YouTube Data API v3 (quota only 10k/day at risk). Optional: regenerate in Google Cloud Console if paranoid.
- GitHub PAT `gho_NkbKi...NhgIn` was also exposed in terminal output earlier — rotate at https://github.com/settings/tokens when convenient.

**Notes:**
- ICT channel: @innercircletrader, ID `UCtjxa77NqamhVC8atV85Rog`, created 2012-02-28
- Google Cloud project: ict-research-493911
- Quota: 10k units/day, transcript pulls ~200 units per channel = plenty

## 2026-04-26 (Sun PM) — Post-restart system check + ORB weekend bug
- Restarted PC; relaunched all services. ORB, Jarvis, WeatherAlpha bot+dashboard+monitor, watchdogs, TradingView CDP all up.
- Killed 3 duplicate procs that VBS launched twice (Jarvis bot, watchdog, dashboard).
- WeatherAlpha dashboard died on its own once after restart; relaunched, back on :3001.
- **Sweep-bot: user said "we havent built that yet" — saved feedback memory feedback_no_sweep_bot.md, do NOT auto-launch start_sweep_bot.vbs going forward.**
- **WeatherAlpha tunnel BROKEN: WeatherAlpha_Tunnel.vbs points to C:\ZachAI\cloudflared.exe but file is missing. Last tunnel ran 2026-04-23. Awaiting Zach's call on whether to re-download cloudflared or run lhr.life manually.**
- **ORB weekend bug FIXED (commit 1edb42a):** run_briefing, run_sentinel_initial, run_structure all lacked is_trading_day() guards — fired on Sun and sent full economic report. Added guards to all three. Pushed to master.
- Confirmed Telegram routing IS already separate by-bot: ORB token ends Uk5UDo, WeatherAlpha ends 0NE8fw. Both DM same chat 6592347446 but appear as distinct conversations in Zach's app.
- WeatherAlpha paper P&L (Apr 14 → Apr 26): $80 → $252.93, +216%. 35 trades, 18W/14L/3 open, win rate 56.3%, profit factor 2.48. Best: DEN T57 +$95. Going live in "few more weeks" per Zach.
- Tomorrow (Mon 4/27) is a trading day, ORB scheduler armed for 8:45/8:50 AM ET.

## 2026-04-28 (Tue) — ORB regroup → risk + management build → cleanup
**System status checks**
- ORB watchdog had been down since prior day's restart. Relaunched via `wscript C:\ZachAI\scripts\ORBWatchdog.vbs`, all green.
- Discovered TradingView CDP :9222 not listening despite TV running. Root cause: boot-time `TradingView.vbs` in user Startup folder pointed to stale `TradingView.Desktop_3.0.0.7652_x64` path; actual installed version is `3.1.0.7818`. Replaced with version-stable launcher using `shell:AppsFolder\TradingView.Desktop_n534cwy3pjxzj!TradingView.Desktop` AUMID. CDP confirmed responding HTTP 200 after manual relaunch.

**ORB cascade regroup (commit 1a2a7af)**
- Researched Zarattini 2023 + retail Pine scripts — owner's "15-min box, close outside, take direction" intuition is mainstream-correct. Bot's 4-gate cascade was over-restrictive.
- Last 90 days: 7 signals → 2 trades. 5 skips: 3 by Gate 1 (ORB candle dir), 2 by Gate 2 (HTF bias). Gate 1 had data backing (77-80% edge per tradingstats.net 2026); Gate 2 + Gate 3 had no published edge.
- Owner directive: "no guardrails, see how he manages the trade." Stripped all cascade gates entirely. `_check_cascade()` returns None unconditionally. Hard blocks (VIX>30, CPI/NFP/FOMC) and circuit breaker (3 consec losses) preserved.
- `MAX_TRADES_PER_SESSION` reduced 3 → 2 (strict ORB: first break + optional second-break per Zarattini).

**Risk + trade management build (commit e45a766)**
- Audit found dead constants and gaps: `WEEKLY_LOSS_LIMIT_PCT=0.07` defined but never enforced, no per-trade $ cap, no daily $ cap, no paper-mode env guard, T2 was metadata-only (never actual TV TP).
- Added: per-trade cap $100, daily cap $150, weekly cap $350. Helpers: `journal.get_today_pnl()` + `get_week_pnl()`. Module flags `_logged_daily_cap` / `_logged_weekly_cap` to prevent Telegram spam every 15s.
- Trade management overhaul: TV bracket TP changed from T1 → T2 (1.5× ORB). T1 (0.5× ORB) becomes BE trigger — virtual_stop = entry once price hits T1. If price drifts back through entry, monitor sends market close (scratch).
- News intervention: high-impact headline within `NEWS_INTERVENTION_WINDOW_SEC=90` AND post-trade-open → close.
- VIX intervention: `vix_now >= vix_at_open * 1.20` → close. Captures vix_at_open in active_orders dict.
- Paper-mode hard guard: `place_bracket_order` raises `RuntimeError` if `PAPER_MODE != "true"`. Added `PAPER_MODE=true` to `trading/.env`. Verified by setting false → RuntimeError raised, no order placed, journal row marked FAILED_PLACEMENT.
- Added `telegram.notify_be_move`. Pre-deploy backtest: 2 historical taken trades become 4 expected with new rules (2× lift, within target).

**Cleanup (commits 03b0a38, 0f65ce6, fccb356, 41b7ee0)**
- Deleted `scripts/start_sweep_bot.vbs` — only ORB connects to TV CDP now.
- Master CLAUDE.md: marked sweep-bot DEFERRED. Per Zach: "we going build that later after we master the orb and its stable."
- `sweep-bot/CLAUDE.md` rewritten with STATUS — DEFERRED header, design intent preserved as reactivation reference.
- Removed disabled ATR comments from `_check_hard_blocks`. Dropped unused imports (`SCORE_FULL_SIZE`, `SCORE_HALF_SIZE`, `ORB_ATR_*`) from combiner.

**Master CLAUDE.md tightening (commit 41b7ee0)**
- JARVIS IDENTITY trimmed (cut role-list bloat, kept verify-before-done).
- AUTONOMY: added "verification still applies" line.
- New MODEL SELECTION section (Sonnet default, Haiku trivial, Opus hard/escalation).
- New FAILURE ESCALATION (3-strike rule → log session_log.md → change approach OR escalate via Telegram).
- SESSION START ls scoped to ACTIVE BUILD DIRS only.
- AGENT STACK moved to bottom as "FUTURE — NOT YET BUILT".
- Per-project CLAUDE.md audit: only `sweep-bot/CLAUDE.md` had drift; all others (trading, kalshi, telegram-bridge, sandbox, tradingagents, zacks-work-drawings, tradingview-mcp-jackson) clean.

**Bot status review at end of session**
- WeatherAlpha (paper, ON): 37 trades, 21W/15L, 58.3% WR, +$174.19. Bot IS learning — `learning_agent.py` runs nightly 18:30 ET. Active cooldowns: CHI until Apr 29 23:30 (4 consec), NYC + DEN until Apr 30 23:30. Lifetime "less" strike-type blocked (0W-10L across all cities). Brier 0.31 (mediocre).
- MIA edge analysis: 9-0, +$128.15. **Partly structural** — all 9 trades short NO on B-strikes (narrow temperature bands, structurally low-prob). 8/9 had positive model edge. Defensible true WR: 75-90%, not 100%.
- CHI loss diagnosis: 0-4 + 1 open, -$34.36. Pattern: all T-strikes, all YES side. 4 of 5 trades had |forecast - strike| ≤ 1°F (inside Open-Meteo's ±2-3°F noise). Apr 19 + Apr 27 trades bet AGAINST own model point estimate. Learning agent already caught it — blocked "less" strikes lifetime, paused CHI 48h. Owner: leave it, let agent self-correct.

**Live money question — DECISION: NO**
- Three hard stops in CLAUDE.md make this Zach's call only. Data against: 37 trades too small (need 100+), Brier 0.31 mediocre, ORB rules ripped open today (zero live trades on new rule set), risk caps untested in production. Documented staged go-live criteria. Won't revisit until ORB has 30+ trades on new rules and Kalshi shows stable WR over 100+ trades.

**Tomorrow (Wed 4/29) — first live test of new ORB rule set**
- ORB main running on new code (PID 1504), watchdog green, CDP responding.
- Watch for: bracket TP=T2 (not T1) on first signal, BE alert on T1, news/VIX intervention paths.
- Today's pnl=$0, week pnl=$40.25 — no risk caps active.
- Kalshi: MIA + LAX active. CHI/NYC/DEN sidelined.

**Commits (all on master, pushed):** 1a2a7af, e45a766, 03b0a38, 0f65ce6, 41b7ee0, fccb356

**Open items for next session:**
1. Verify new ORB rules fire correctly on first signal tomorrow.
2. After first close: confirm `journal.get_today_pnl()` matches sum of journal trades + risk-cap flags tracking correctly.
3. Do not escalate to live money — staged criteria are the gate.
4. WeatherAlpha tunnel still broken (cloudflared.exe missing from prior session) — not addressed today, separate task.

---

## 2026-05-01 (Friday — Zach worked OT)

### Phantom-fill bug (this morning, 09:00 EDT)
ORB submitted LONG MNQ1! @ 27871.25. `_check_order_acceptance` 4s timeout fired before TV surfaced position rows (TV took ~10s). Trade 10 marked FAILED_PLACEMENT, not persisted to active_orders. Reconcile loop alerted 1/min for 5.5h → 100+ Telegram messages. Zach manually closed mid-day. Avail recovered $5357 by 17:42.

### Phase 1 — phantom-fill recovery (PR #2 → merged 441d18c)
- `_check_order_acceptance` 4s → 12s; polls toast + position rows + margin drop ≥ $2,400 in parallel
- New `_recent_failed_attempts` buffer (180s TTL) → reconcile ADOPTS phantoms with recent failed-acceptance match
- `journal.reopen_as_adopted()` flips FAILED_PLACEMENT → OPEN for adopted trades
- Phantom alert throttle: 5min → 15min cooldown, one-shot RESOLVED ping when drift clears
- Circuit breaker auto-resets when drift clears (was stuck open 5h+ today)
- 9 new tests in `tests/test_tv_trader_recovery.py` — all green
- Restarted ORB cleanly with new code (PID 31756 final)

### Phase 2.2 — slash commands (PR #3 → reverted, never merged)
- Added `/orb_status`, `/orb_pause`, `/orb_resume` to bot.py + pause-flag check in combiner.py
- Zach: "i didnt need that i could just ask him in conversation" → full revert
- Saved memory `feedback_no_slash_commands.md` — prefer conversational; don't propose new slash commands

### Cleanup pass
- Removed 3 stale Claude worktrees (vigorous-cray, focused-kapitsa, cool-fermat) + 3 fully-merged orphan branches + 4 stale remote branches
- Kept: `claude/friendly-spence-b75bd4` (has unmerged commit "persist every scored signal to journal.db signal_history" — Zach to review)
- Updated stale memory `project_orb_pipeline.md` (paper_trader.py / tunnel pipeline retired 2026-04-17)
- Updated MEMORY.md index entry to match
- **Caught + fixed test pollution bug:** `test_tv_trader_recovery` was writing fake adopted trade rows to live `state/active_orders.json`. Fixed via `monkeypatch.setattr(tv_trader, "_persist_active_orders", lambda: None)` in autouse fixture. Pollution wiped, test re-verified green. Commit 85b4bcf.

### Final state at session end
- master @ 85b4bcf
- ORB: paper mode, PID 31756, 16 jobs scheduled, no active orders, no errors
- Jarvis bot: PID 9664
- Kalshi: WeatherAlpha :5000 + dashboard :3001 + monitor + watchdog all green
- TV CDP :9222 listening, MNQ1! 5m, api_available=true
- Sunday 6PM ET reopen ready

### Open items for next session
1. Sunday open is the live verification of the phantom-fill fix. If a setup fires and TV is slow, watch for either a clean fill (margin-drop signal) or a `🛡️ Adopted phantom from trade #N` Telegram instead of orphan spam.
2. `claude/friendly-spence-b75bd4` remote branch has unmerged "signal_history" feature — review whether to merge or close.
3. `condescending-swanson-ded9ca` worktree still exists with uncommitted `.claude/settings.local.json` — Zach to review/discard.
4. 8 pre-existing test failures in `test_cascade_second_break.py` + `test_combiner_reversal.py` reference removed `combiner._check_cascade` — separate cleanup PR worth ~30 min.
5. If conversational pause is wanted, no code change needed — Jarvis can already do it via Read/Bash tools (e.g., kill the python process or write a flag — but no flag-check exists in combiner anymore since Phase 2.2 was reverted; if Zach wants pause without process kill, that's a future change).

### Lessons
- **Don't propose new slash commands** — the conversational handler already covers everything (saved as feedback memory).
- **Tests must mock `_persist_active_orders`** when calling `reconcile_with_tv()` or any path that triggers a save — production state is at risk.
- The phantom-fill bug is a TIMING issue; fix is more time + multiple confirmation signals + automatic recovery, not stricter validation.

**Commits (all on master, pushed):** 5250f55 (PR #2 — phantom-fill), 441d18c (merge), 85b4bcf (test isolation fix)

---

## 2026-05-01 (continued, late Friday) — OmniAlpha built

Zach said "complete the bot tonight don't stop till it's done. going to bed." — auto mode was on, executed straight through.

### What shipped (PR #4, branch `kalshi-multi/scaffold`)

**Phase 1 — Scaffold (committed earlier)**
- `omnialpha/` directory with CLAUDE.md, ACTIVE_FILES.md, .env.example, .gitignore, requirements.txt
- `bots/kalshi_public.py` — unauthenticated `/historical/*` puller. No API key needed.
- `data_layer/database.py` — 7-table SQLite schema
- `data_layer/historical_pull.py` — idempotent bulk ingest
- `cli.py` — health / init-db / pull-historical / status
- 6 unit tests passing

**Phase 2 — Functional bot**
- `strategies/base.py` — Strategy ABC + MarketSnapshot + EntryDecision + ExitDecision
- `strategies/crypto_midband.py` — first strategy, rule-based, no LLM
- `backtest/runner.py` — replays settled markets through any Strategy, applies risk engine inline
- `backtest/calibration.py` — Brier + log loss + calibration curve
- `bots/kalshi_client.py` — RSA-PSS signed REST client (auth lazy-loaded)
- `bots/order_placer.py` — paper writer + LOCKED live path (two-flag gate)
- `bots/risk_engine.py` — 5-gate filter + cross-bot risk_state.json coupling
- `bots/trade_monitor.py` — settle open trades, write pnl_snapshots
- `bots/telegram_alerts.py` — send-only [OmniAlpha] prefix on Jarvis bot
- `bots/events_scanner.py` — universe scanner (paper-mode reads historical store)
- `main.py` — APScheduler, refuses start if PAPER_MODE != true
- `scripts/OmniAlpha.vbs` — auto-start launcher (NOT yet in Startup folder)
- 32 additional tests, including 1 full end-to-end lifecycle test
- TOTAL: 38 tests, all passing

### Edge found in calibration

KXBTC15M Brier 0.0136 (Kalshi accurate overall), BUT systematic mid-band miscalibration:
- yes_price 0.20-0.30 → actual ~10-15% → bet NO
- yes_price 0.30-0.40 → actual ~7-25% → bet NO
- yes_price 0.70-0.85 → actual ~85-100% → bet YES

Backtest with risk engine + Kelly=0.10:
- 95 trades, 85.3% WR
- $100 → $162 (+62% over 7 days)
- Max DD $14.91, Sharpe 0.258, PF 1.89

### Reference repos cloned (read-only, in `C:\ZachAI\reference\`)
- `ryanfrigo-kalshi-bot` (toolkit pattern, MIT)
- `joseph-pm-calibration` (Brier pipeline)
- `roman-kalshi-btc` (KXBTC15M binary puller pattern)

### Decisions made on Zach's behalf during the build
- Project name: **OmniAlpha** (parallel to WeatherAlpha — alpha across all sectors). Easy to rename.
- Working dir: `C:\ZachAI\omnialpha\`
- Starting capital: $100 (small while paper-validating)
- Risk caps: $20/trade, $50/day, $150/week
- First sector: crypto only (KXBTC15M binary up/down)
- Kelly fraction default: 0.10 (validated via backtest sweep)
- Dashboard port: 8502 (no conflict with WA :3001 / Jarvis :8765 / ORB :9222 / WA API :5000)
- Telegram: same Jarvis bot, [OmniAlpha] prefix
- Live trading: NOT wired tonight. Live path exists but gated behind two flags.

### Open items for next session
1. **Zach reviews + merges PR #4** — that's the gate before any further work
2. **Live cutover session** (separate, with explicit approval): populate KALSHI_API_KEY_ID + private key path in omnialpha/.env, flip both flags, restart, observe paper trades on LIVE markets
3. **Register `OmniAlpha.vbs` in Windows Startup folder** — only after live cutover succeeds
4. **Phase 3**: second sector (sports likely — KXNBA / KXMLB), CLV grading, hedge-to-lock primitive
5. The cross-bot `risk_state.json` is wired in OmniAlpha but WA doesn't read it yet — wiring WA to the shared risk_state is a small but real follow-up

### Lessons / surprises
- The schema's `final_yes_ask_dollars` is post-settlement residual (always 0 or 1). Useless for backtest. The right field is `last_price_dollars` from raw_json. Caught during first calibration run (Brier 0.4780 nonsense). Fixed both `runner.py` and `calibration.py`.
- Float drift: `7 * (1.0 / 10) = 0.7000000000000001`. Bin boundaries needed `round(..., 10)` to avoid one test failure on the calibration curve.
- Kelly sweep showed clearly that 0.50 (half-Kelly) blows out drawdown variance. 0.10 is the sweet spot for paper-validation. P&L scales with Kelly but Sharpe doesn't.
- The two-flag live gate (`PAPER_MODE` in .env AND `assert_paper_mode_off_was_explicit()` in code) is belt-and-suspenders — neither alone permits a live order.

**Commits on branch `kalshi-multi/scaffold` (PR #4 not yet merged):** scaffold + Phase 2.

---

## 2026-05-02 (Saturday — extended session) — OmniAlpha live + dashboard

Picked up where Friday night left off. Massive multi-phase session.

### Phase 1 — Get OmniAlpha actually trading (morning)
- Code review by 5 parallel agents found 6 critical bugs in the bot:
  1. main.py had no scheduler job for live polling — bot was a no-op
  2. _market_already_traded_today blocked re-entry forever (no date filter)
  3. trade_monitor settlement broken — local markets table never updated to finalized
  4. Backtest seconds_to_close was total duration, not time remaining
  5. Backtest's risk engine queried live DB (results not reproducible)
  6. live_scanner bypassed the order_placer.place() dispatcher
- Strategy domain review flagged over-confident bands on small samples (n=12-15)
- ALL fixes shipped in commit 9665065:
  - Wired live_scanner as scheduled job
  - Added skip_db_gates flag for backtest cleanliness
  - Tightened bands to only well-sampled (BTC15M: NO 0.20-0.30, YES 0.75-0.85)
  - kelly_fraction default 0.10 → 0.05
  - Entry window restricted to last 3 minutes (calibration was on close prices)
  - Added Gate 7 aggregate-open-risk to risk engine

### Phase 2 — Multi-sector expansion
- Pulled KXETH15M (7,393 markets) + KXBTCD (532k+ markets, capped) historical
- Calibration on both showed real edge:
  - KXETH15M: same NO 0.15-0.30 + YES 0.65-0.85 pattern
  - KXBTCD: even larger samples, miscal +27/-23 pts in some bands
- Refactored CryptoMidBandStrategy to be parameterized (bands, kelly, timing)
- Three strategies now in registry: btc15m, eth15m, btcd
- Backtest combined: 937 trades, 95.1% WR, +$2,884 over 7 days (throttled to ~30-50/wk live)
- MAX_TRADES_PER_SECTOR_PER_DAY: 5 → 20 (3 strategies share crypto sector)

### Phase 3 — Dedicated Telegram channel
- Zach created @OmniAlphaAlerts_bot via @BotFather
- Token + chat_id (6592347446) wired into omnialpha/.env (gitignored)
- Verification ping confirmed; ORB Alerts bot stops getting [OmniAlpha] msgs

### Phase 4 — Dashboard rebuild (evening)
- Initial Streamlit dashboard "had too much info" per Zach
- Sent design survey agents — recommended 5-panel max, single accent color, tabular nums, restraint
- Read WeatherAlpha's React/Tailwind/Recharts stack as reference
- Built complete React app at omnialpha/dashboard/frontend/ matching WA quality bar
- Backend Flask at omnialpha/dashboard/backend/serve.py on port 8503
- Components: Header, HeroTiles, OpenPositions, ActivityRail, EquityChart, StrategyCards, LiveChart
- LiveChart embeds TradingView free Advanced Chart Widget (real-time BTC/ETH)
- Auto-picks BTC vs ETH per position's coin; empty state shows last-traded coin
- Replaced cryptic stat row with plain-English explanation per position:
  - "We bet BTC will be above $X" / "Need BTC to STAY/RISE/DROP $Y" / "Xm Ys left"

### Bot performance during the session
- Started day at 0 trades. By session end: 11 trades, 11W/0L, +$6.53 (capital $100→$106.53)
- Strategies all printing:
  - crypto_btcd_midband: best earner
  - crypto_btc15m_midband + crypto_eth15m_midband: real wins on both
- 100% WR over 11 trades is statistically suspicious BUT mathematically possible
  (math: ~35-45% chance given the per-strategy true WRs). First loss is coming
  and is expected.

### Master state at session end
- HEAD: b9dd6d7 (latest commit: plain-English explanation block)
- All commits pushed to origin/master
- 3 OmniAlpha processes running:
  - main.py (bot itself, paper mode)
  - serve.py (dashboard backend on :8503)
  - The bot continues 24/7 polling Kalshi every 60s
- Other bots (ORB, WeatherAlpha, Jarvis) all untouched throughout

### Open items for next session
1. **Watch first loss**: when (not if) a trade loses, verify alert fires
   on @OmniAlphaAlerts_bot and trade settles correctly
2. **Sports + politics + economics sectors**: Zach explicitly skipped sports
   (doesn't watch) but might want politics/economics later. Domain-review
   warned political markets have small sample sizes
3. **Stocks (KXTSLA, KXSP500)**: Zach mentioned interest. Same daily-range
   structure as KXBTCD, similar likely edge
4. **Live cutover**: still locked behind two flags. Needs explicit Zach
   approval session. Code paths are ready
5. **Cross-bot risk_state.json coupling**: OmniAlpha writes; WA + ORB don't
   read yet. One-sided for now
6. **Kalshi fee model accuracy**: code uses 7% × profit, Kalshi actual is
   ceil(0.07 × n × p × (1-p)) at entry on every fill. Slightly conservative
   on wins, under-charges losses. Worth fixing before live
7. **TOCTOU race on risk_state.json lock**: known issue, not critical with
   single writer (OmniAlpha) but matters when WA + ORB get wired in
8. **Dashboard TODOs the user might want**: PNL calendar heatmap, mobile
   responsive review, custom indicators on TradingView chart

### Session lessons
- Streamlit IS too cluttered for war-room dashboards. Hummingbot retired
  theirs. React + Tailwind + Recharts is the right stack — match WA exactly
- Plain-English explanation > cryptic stat tiles when the user is watching
  open trades. "Need BTC to RISE +$57" beats "Strike $X / BTC $Y / Stake $Z"
- TradingView's free embeddable widget is a real cheat code for live charts
  in any dashboard — drop-in, real-time, full UX, no API key
- Code reviews catch blocker bugs that tests miss (nothing in 50 unit tests
  caught the live_scanner-not-wired-into-main-loop issue)

## 2026-05-18 — WeatherAlpha First Live Day + ORB Hardening

### What we built
- Shipped 7 commits to live trading code (all flagged per auto-merge policy)
- Made ORB self-monitoring with 5 new watchdog checks
- Made WeatherAlpha daily-loss cap scale with bankroll

### Key fixes today
- **B-strike bug (kalshi)**: 4 of 5 first live orders rejected w/ `invalid_parameters`. Root cause: `client_order_id` contained `.` from B-strike tickers (e.g. "B86.5"). Kalshi's validator rejects dots for some market series. Fix: `_safe_ticker = best['ticker'].replace('.', '-')`. Commit `bf8e250`.
- **ORB phantom silent failure**: position appeared on TV broker, bot blocked all entries for ~8hr while logging "soft drift transient" each minute. NO Telegram alert. Cost a full RTH session. Fix: soft-drift counter escalates to hard phantom after 5 cycles (~5 min) → Telegram + circuit breaker. Commit `ba15a1e`.
- **Dashboard lying about balance**: ORB showed $5,370 while real TV broker was $4,816 — a $554 untracked loss from the phantom. Fix: `broker_state.json` written every reconcile cycle; dashboard reads real number; surfaces `untracked_pnl_usd` discrepancy. Commit `7e0af58`.
- **ORB watchdog 5 new checks**: stuck-scan, state-drift, balance-discrepancy, preflight, signal-without-trade. Commit `3c41b88`.
- **Daily-loss cap scaling**: was fixed $20, would halt bot on one losing trade past ~$500 bankroll. Now `max($20 floor, capital × 10%)`. Commit `84f6126`.

### WeatherAlpha first live day result
- 5 trades placed, $18.02 at risk on $83.50 bankroll (after audit-fix dot sanitize)
- Unrealized end-of-day: +$12.03 (4 winners + 1 MIA loser)
- Expected realized after overnight settlement: ~+$8.98 = ~+10.7% day 1
- Same trades that initially rejected (MIA, ATL, WDC, HOU, NOL B-strikes) successfully placed after fix

### Lessons / patterns to remember
- **Read code before claiming behavior** — Zach called me out for guessing about MAX_DAILY_LOSS scaling. CLAUDE.md says no guessing; I violated it twice today. Going forward: grep + read before any "the bot does X" claim.
- **Silent failures are the worst kind** — every disaster today (B-strike, phantom, dashboard) failed silently. The audit-fix that logs HTTP response bodies (yesterday's commit) was load-bearing for diagnosing the B-strike bug in <30s.
- **Strike-type-specific Kalshi API behavior** — T-strike (greater-than) markets accept dots in client_order_id; B-strike (between) markets reject them. Bot needs to know which strike types are forgiving and which are strict.
- **Dashboard math must match broker reality** — computing "starting + journal PnL" silently lies when untracked positions exist. Always read real broker balance, expose discrepancy explicitly.
- **Soft escalation patterns** — don't log warnings forever; count cycles, escalate after N. "transient" should never be permanent.

### Installed
- claude-code-setup plugin (read-only automation recommender). Ran it, recommended block-sensitive-files hook + /halt-all slash command. Zach declined both for tonight.

### Status going into tomorrow (5/19)
- WeatherAlpha PID 21820, halted=false, 5 trades pending overnight settlement
- ORB PID 5220, scheduler armed for RTH, all 11 watchdog checks live
- OmniAlpha PID 30756, paper mode, 4 strategies active (btcd paused), no losses today
- Watchdog PID 32756, 5 new checks active, first cycle correctly flagged $554 hidden loss

