# ORB TRADING SYSTEM — Project Brain

## OVERVIEW
NQ/MNQ futures ORB scalp system. Captures 15-min opening range (9:30-9:45 ET), waits for closed 5-min bar breakout, scores with multi-agent context, executes via direct CDP to TradingView chart.

- Main controller: `C:\ZachAI\trading\main.py` (APScheduler, PID lock)
- PID lock: `trading/state/orb.pid` — only ONE instance runs at a time
- VBS auto-start: `scripts/ORBAgents.vbs` → git pull → python main.py
- Watchdog: `scripts/ORBWatchdog.vbs` → `scripts/orb_watchdog.py` (auto-restart + Telegram alerts)
- Telegram bot: `C:\ZachAI\telegram-bridge\bot.py` (auto-start via Jarvis_Bot.vbs)
- **Paper mode: ON** (NEVER change without explicit approval — one of the 3 hard stops)

## AGENT SCHEDULE (all ET, source of truth: `trading/main.py`)
- **preflight** — 7:00 AM (stack verification)
- **memory_morning** — 7:30 AM (pre-market refresh)
- **sentinel** — 8:00 AM initial + every 60s poll
- **structure** — 8:45 AM (daily levels, VIX, ATR)
- **briefing** — 8:50 AM (Telegram morning report)
- **briefing_heartbeat** — 8:55 AM (Telegram ping confirming morning agents ran)
- **combiner_heartbeat** — 9:31 AM (Telegram ping at market open)
- **combiner** — every 15s during 9:30-15:00 (ORB scoring + trade execution)
- **trade_monitor** — every 30s (stop/TP reconciliation, time exits)
- **memory** — 6:00 PM daily
- **learning_agent** — 6:30 PM daily (reviews trades, proposes knob changes, Telegram heartbeat)
- **learning_weekly** — Sunday 7:05 AM (weekly learning-agent digest)
- **journal_backup** — 6:00 AM daily (copy journal.db, keep 30 days)
- **journal_weekly** — Sunday 7:00 AM (weekly report)

Scheduler: `misfire_grace_time=3600` — jobs run up to 1h late instead of silently skipping on clock drift.
Startup ping: "ORB online @ <ET>" via Telegram. If you reboot and don't see it, boot failed.

## ORB MECHANICS (regrouped 2026-04-28)
- **Range:** 15-min opening range (`ORB_MINUTES=15`, 9:30-9:45)
- **Breakout confirmation:** closed 5-min bar outside the range (prevents wick fakeouts)
- **Chart:** MNQ1! on 5m timeframe
- **Position size:** 1 MNQ contract (paper, $5,000 demo, $2/pt)
- **Stop:** ORB ± `STOP_EXTENSION_MULT` × range = 0.25× range beyond opposite boundary
- **Bracket TP:** **T2** (1.5× ORB range from entry) — TV's bracket runs the trade to T2, not T1
- **T1 = breakeven trigger** (0.5× ORB range from entry) — when price reaches T1, monitor sets virtual_stop=entry; if price drifts back through entry, monitor sends a market close (BE scratch)
- **Order placement:** direct CDP via `trading/services/tv_trader.py::place_bracket_order` — NOT webhooks or alerts. CDP :9222 must be reachable. Single CDP evaluate() call, ~750ms place / ~375ms close

## RISK RULES (active hard caps, all enforced)
- **Per-trade max risk: $100** — `MAX_RISK_PER_TRADE_DOLLARS` — skip if `abs(entry-stop) × MULTIPLIER > $100`
- **Daily max loss: $150** — `DAILY_LOSS_LIMIT_DOLLARS` — pause day when today's `pnl_after_slippage` total ≤ -$150
- **Weekly max loss: $350** — `STARTING_CAPITAL × WEEKLY_LOSS_LIMIT_PCT` (7%) — pause week when 7-day total ≤ -$350
- **3 consecutive losses** — `MAX_CONSECUTIVE_LOSSES=3` — pause day
- **Max trades/session: 2** — strict ORB rules (first break + optional second-break, never a third)
- **VIX > 30** — `VIX_HARD_BLOCK=30` — pause day
- **High-impact news day** — CPI/NFP/FOMC scheduled in session window — pause day

## TRADE MANAGEMENT (`monitor_trades` runs every 30s)
- **T1 reached → BE move:** virtual_stop = entry, Telegram alert via `notify_be_move`. Original TV bracket SL stays as backstop.
- **Virtual BE stop:** after t1_hit, if price drifts back to entry → market close (counts as WIN, scratch P&L after slippage).
- **VIX intervention:** `VIX > vix_at_open × (1 + VIX_INTERVENTION_PCT)` (20% spike) → market close.
- **2-hour time exit** — `MAX_HOLD_MINUTES=120`.
- **3pm hard close** (1pm on half days) — `HARD_CLOSE_HOUR/MINUTE`.
- **Reconciliation:** if TV's bracket auto-closes at SL or T2, monitor logs the outcome to journal without sending a duplicate market order.

## PAPER GUARANTEE
- `PAPER_MODE=true` env required in `trading/.env`.
- `tv_trader.place_bracket_order()` raises `RuntimeError` if `PAPER_MODE != "true"` and marks the journal row `FAILED_PLACEMENT`.
- Setting `PAPER_MODE=false` is one of the 3 hard stops in master CLAUDE.md.

## SCORING TABLE
| Factor | Points |
|---|---|
| ORB candle direction matches breakout | +3 |
| HTF bias confirms | +2 |
| Bias conflicts | −2 |
| Second break after failed first (72% edge) | +2 |
| Open air (no level within 20pts) | +1 |
| Approaching wall | −2 |
| At a level (no room) | −5 |
| RVOL ≥ 1.5x | +1 |
| Price aligns with VWAP | +1 |
| VIX in 15-25 sweet spot | +1 |
| Prior day closed in direction | +1 |
| No news block | +1 |
| No truth block | +1 |

Score is recorded to `signal_history` for ML labeling but does not gate entry. Authoritative entry rules live in **RISK RULES** above; the only entry filters are the hard blocks (VIX>30, scheduled CPI/NFP/FOMC, daily/weekly $ caps, per-trade $ cap, 3-consec-loss circuit).

## 2026 HIGH-IMPACT CALENDAR (official BLS + Fed dates, hard-coded)
- **CPI** (8:30 AM): Jan 13, Feb 11, Mar 11, Apr 10, May 12, Jun 10, Jul 14, Aug 12, Sep 11, Oct 14, Nov 10, Dec 10
- **NFP** (8:30 AM): Jan 9, Feb 6, Mar 6, Apr 3, May 8, Jun 5, Jul 2, Aug 7, Sep 4, Oct 2, Nov 6, Dec 4
- **FOMC** (2:00 PM): Jan 28, Mar 18, Apr 29, Jun 17, Jul 29, Sep 16, Oct 28, Dec 9

## FILE HYGIENE (trading-specific)
- No local `.pine` files — Pine Scripts live ONLY in TradingView editor
- `paper_trades.json` and `trades_journal.db` are gitignored
- **Auto-merge exception:** any task touching `trading/services/tv_trader.py` must commit and push but notify Zach BEFORE merging (it affects live order execution)

## LEARNING AGENT
- Runs nightly at 6:30 PM ET — reviews last 30 days of trades and proposes tweaks to `SCORE_FULL_SIZE`, `SCORE_HALF_SIZE`, `RVOL_THRESHOLD`.
- Proposals land in `agent_journal` table (SQLite) as `status='pending'`. They DO NOT auto-apply.
- Nightly heartbeat fires even when <20 trades ("X/20 trades accumulated — no proposal yet") so silence = something broken, not low activity.
- Approved proposals live in `state/learned_config.json`. `config_loader.py` overlays these onto `config.py` at import time.
- **Manual edits to `state/learned_config.json` are detected via SHA256 drift vs `state/learned_config.meta.json`, then logged to `agent_journal` with `source='manual'`.** Do not bypass — keeps the audit trail clean.
- Guardrails: ±1 pt step on scores, ±0.1 on RVOL; 10-trading-day cooldown per knob; bounds clamped to `LEARNABLE_KNOBS` in `config_loader.py`.
- Dry-run: `python -m agents.learning_agent --dry-run` prints proposals without writing or sending Telegram.
- PR #2 (deferred) adds `/approve_orb_agent`, `/reject_orb_agent`, `/revert_orb_agent` Telegram handlers. Until it ships, approve by editing `state/learned_config.json` manually — config_loader will log the drift.

## TRADINGVIEW MCP NAVIGATION CHEATSHEET

### Alert Editing — Full Workflow
1. `alert_list` → find target alert_id and confirm message/symbol
2. `ui_open_panel panel=alerts action=open`
3. Click center of alert row to reveal action buttons:
   - Get row rect via JS: `alertsWidget.querySelector('.itemBody-bswc3EEA.active-OptuQCiE')`
   - `ui_mouse_click` at center coords from getBoundingClientRect()
4. Find Edit button: `parent.querySelectorAll('[title="Edit"]')[0]` → get coords → `ui_mouse_click`
5. "Edit alert on MNQ1!" dialog opens at `.dialog-qyCw0PaN`

### Edit Alert Dialog — Key Elements
- **Dialog selector:** `.dialog-qyCw0PaN`
- **Message button:** BUTTON inside `.fieldsWrapper-sFcMHof4` containing message text → click opens "Edit message" sub-dialog
- **Notifications button:** BUTTON inside `.fieldsWrapper-sFcMHof4` containing "App, Toasts, Webhook..." → click opens Notifications sub-dialog
- **Save button:** class `submitBtn-m9pp3wEB` — may be off-screen (y>650), use JS `.click()`
- **Back button:** `nav-button-znwuaSC1` with text "Back" — in dialog header

### Edit Message Sub-Dialog
- **Textarea selector:** `textarea.textarea-x5KHDULU`
- **To set value** (React-controlled — `ui_type_text` won't work alone):
```js
const ta = document.querySelector('textarea.textarea-x5KHDULU');
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, 'NEW MESSAGE HERE');
ta.dispatchEvent(new Event('input', {bubbles: true}));
```
- **Back button:** BUTTON text "Back" at ~(181, 223) — use JS `.click()`

### Notifications Sub-Dialog
- **Webhook URL input:** `input.input-RUSovanF` (type=text)
- **To set URL** (React-controlled):
```js
const inp = document.querySelector('input.input-RUSovanF');
const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
setter.call(inp, 'https://YOUR-TUNNEL-URL/alert');
inp.dispatchEvent(new Event('input', {bubbles: true}));
```
- **Apply button:** off-screen at y≈725, use JS:
```js
Array.from(document.querySelector('.dialog-qyCw0PaN').querySelectorAll('button')).find(b => b.textContent.trim() === 'Apply').click()
```

### Off-Screen Buttons Rule
When `getBoundingClientRect().top > 650` — button exists but is below viewport:
- **DON'T** use `ui_mouse_click` with that y coordinate
- **DO** use `ui_evaluate` with JS `.click()`:
```js
Array.from(dialog.querySelectorAll('button')).find(b => b.textContent.trim() === 'Save').click()
```

### Keyboard Trap Warning
TradingView captures keys globally even when dialogs are open:
- `Shift+S` → triggers "Sell Market" order
- `B` → triggers "Buy Market"
- Never use `ui_keyboard` with single letters; use JS `.click()` for off-screen buttons

### Key CSS Selectors
| Element | Selector |
|---|---|
| Alerts widget | `.widgetbar-widget-alerts` |
| Active alert row body | `.itemBody-bswc3EEA.active-OptuQCiE` |
| Edit/Pause/Delete buttons | `[title="Edit"]` / `[title="Pause"]` / `[title="Delete"]` |
| Alert edit dialog | `.dialog-qyCw0PaN` |
| Message textarea | `textarea.textarea-x5KHDULU` |
| Webhook URL input | `input.input-RUSovanF` |

### Legacy Pipeline (retired 2026-04-17)
`paper_trader.py` + cloudflared tunnel + TV alert webhook ID were removed. Do not recreate. All order flow is direct CDP now.
