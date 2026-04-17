# ACTIVE FILES MANIFEST
# Every running file must be listed here. If it's not listed, it shouldn't exist.
# Updated: 2026-04-17

## TRADING PIPELINE (MNQ ORB Strategy — direct CDP)

### Signal Flow
```
trading/main.py (APScheduler)
  -> agents/sentinel + sweep + combiner score ORB setup
  -> services/tv_trader.place_bracket_order
  -> CDP evaluate() clicks Buy/Sell on TradingView chart (paper account)
  -> Telegram entry/exit alerts via services/telegram
```

### Files
| File | Purpose | Auto-start |
|------|---------|------------|
| `trading/main.py` | ORB multi-agent controller (APScheduler, PID lock) | Startup/ORBAgents.vbs |
| `trading/agents/` | sentinel, sweep, combiner, briefing, structure, memory, journal, preflight | — |
| `trading/services/tv_client.py` | CDP WebSocket client (auto-reconnect) | — |
| `trading/services/tv_trader.py` | Places bracket orders via CDP evaluate() | — |
| `trading/services/telegram.py` | Telegram alert sender | — |
| `trading/services/state_manager.py` | Per-agent JSON state + file locks | — |
| `trading/.env` | Telegram bot token + chat ID (gitignored) | — |

### Windows Startup Scripts (C:\Users\zedwa\AppData\...\Startup\)
| Script | Launches |
|--------|----------|
| ORBAgents.vbs | git pull + `python trading/main.py` |
| TradingView.vbs | TradingView Desktop with `--remote-debugging-port=9222` |
| Jarvis_Bot.vbs | `python telegram-bridge/bot.py` |

### Pine Script (lives ONLY in TradingView editor — NO local files)
- "NQ ORB Strategy" — entity WLAawi on MNQ1! 5m chart

---

## TRADINGVIEW MCP SERVER
| File | Purpose |
|------|---------|
| `tradingview-mcp-jackson/` | Full MCP server (78 tools) — Node.js |
| `tradingview-mcp-jackson/src/core/pine.js` | Pine Editor helper (modified: spinner overlay fix) |
| `tradingview-mcp-jackson/scalper-run.js` | Bitget crypto scalper (separate project) |
| `tradingview-mcp-jackson/rules.json` | Scalper config (separate project) |

---

## WEATHERALPHA (Kalshi)
| File | Purpose | Port |
|------|---------|------|
| `kalshi/bots/trader.py` | Flask API + trading bot | :5000 |
| `kalshi/dashboard/` | React frontend + Flask proxy | :3001 |
| `kalshi/keys/` | Private keys (gitignored) | — |

---

## TELEGRAM
| File | Purpose |
|------|---------|
| `telegram-bridge/bot.py` | Jarvis Telegram bot (/claude, /run, /tasks, approvals) |
| `telegram-bridge/config.json` | Chat ID config (gitignored) |
| `telegram-bridge/hooks/` | Notification hooks |

---

## INFRASTRUCTURE
| File | Purpose |
|------|---------|
| `CLAUDE.md` | Master brain — read every session |
| `ACTIVE_FILES.md` | This manifest — update on every file create/delete |
| `RULES.md` | Operating rules |
| `backup.bat` | Auto git push |
| `.gitignore` | Protects keys, .env, logs |

## WATCHDOGS & RELIABILITY
| File | Purpose |
|------|---------|
| `scripts/orb_watchdog.py` | Monitors ORB stack (main.py PID, CDP :9222, Jarvis bot) — auto-restart + Telegram alerts |
| `scripts/ORBWatchdog.vbs` | Auto-start for orb_watchdog.py |
| `scripts/watchdog.py` | WeatherAlpha watchdog |
| `scripts/WeatherAlpha_Watchdog.vbs` | Auto-start for WeatherAlpha watchdog |
| `trading/agents/preflight.py` | 7:00 AM ET stack verification (CDP, disk, calendar, journal) |

---

## DELETED FILES LOG (for reference — don't recreate these)
| File | Deleted | Why |
|------|---------|-----|
| `trading/orb_bot.py` | 2026-04-10 | Standalone yfinance bot — replaced by TradingView strategy alert pipeline |
| `trading/orb_bot.log` | 2026-04-10 | Log for deleted bot |
| `trading/ORBBot.vbs` | 2026-04-10 | Launcher for deleted bot |
| `trading/tunnel_watcher.py` | 2026-04-10 | Old localhost.run watcher — replaced by Cloudflare tunnel |
| `trading/strategies/mnq_orb_5m.pine` | 2026-04-10 | Old 5m Pine Script — live strategy is 5m in TradingView editor |
| `tradingview-mcp-jackson/orb_executor.py` | 2026-04-10 | CDP polling approach — replaced by webhook alert pipeline |
| `Startup/ORBBot.vbs` | 2026-04-10 | Auto-start of deleted bot |
| `trading/paper_trader.py` | 2026-04-17 | Webhook receiver — ORB migrated to direct CDP order placement in tv_trader.py |
| `trading/paper_trades.json` | 2026-04-17 | Trade log for deleted paper_trader |
| `trading/CloudflareTunnel.vbs` | 2026-04-17 | Tunnel existed only to feed paper_trader |
| `Startup/PaperTrader.vbs` | 2026-04-17 | Auto-start of deleted paper_trader |
| `Startup/CloudflareTunnel.vbs` | 2026-04-17 | Auto-start of deleted tunnel |
| `trading/logs/paper_trader.log` | 2026-04-17 | Log for deleted paper_trader |
| `logs/tunnel.log` | 2026-04-17 | Log for deleted tunnel |
