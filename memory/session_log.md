# Session Log

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
