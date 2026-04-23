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
- **journal_backup** — 6:00 AM daily (copy journal.db, keep 30 days)
- **journal_weekly** — Sunday 7:00 AM (weekly report)

Scheduler: `misfire_grace_time=3600` — jobs run up to 1h late instead of silently skipping on clock drift.
Startup ping: "ORB online @ <ET>" via Telegram. If you reboot and don't see it, boot failed.

## ORB MECHANICS
- **Range:** 15-min opening range (`ORB_MINUTES=15`, 9:30-9:45)
- **Breakout confirmation:** closed 5-min bar outside the range (prevents wick fakeouts)
- **Chart:** MNQ1! on 5m timeframe
- **Order placement:** direct CDP via `trading/services/tv_trader.py::place_bracket_order` — NOT webhooks or alerts. CDP :9222 must be reachable.
- Single CDP evaluate() call, ~750ms place / ~375ms close

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

**Thresholds** (`trading/config.py`):
- Score **≥ 10** → full size
- Score **8-9** → half size
- Score **< 8** → skip + Telegram notify

**Hard blocks** (skip regardless of score):
- VIX > 30 (`VIX_HARD_BLOCK=30`)
- Max 3 trades/session (`MAX_TRADES_PER_SESSION=3`)

## 2026 HIGH-IMPACT CALENDAR (official BLS + Fed dates, hard-coded)
- **CPI** (8:30 AM): Jan 13, Feb 11, Mar 11, Apr 10, May 12, Jun 10, Jul 14, Aug 12, Sep 11, Oct 14, Nov 10, Dec 10
- **NFP** (8:30 AM): Jan 9, Feb 6, Mar 6, Apr 3, May 8, Jun 5, Jul 2, Aug 7, Sep 4, Oct 2, Nov 6, Dec 4
- **FOMC** (2:00 PM): Jan 28, Mar 18, Apr 29, Jun 17, Jul 29, Sep 16, Oct 28, Dec 9

## FILE HYGIENE (trading-specific)
- No local `.pine` files — Pine Scripts live ONLY in TradingView editor
- `paper_trades.json` and `trades_journal.db` are gitignored
- **Auto-merge exception:** any task touching `trading/services/tv_trader.py` must commit and push but notify Zach BEFORE merging (it affects live order execution)

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
