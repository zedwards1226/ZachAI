# ACTIVE FILES MANIFEST
# Every running file must be listed here. If it's not listed, it shouldn't exist.
# Updated: 2026-04-10

## TRADING PIPELINE (MNQ ORB Strategy)

### Signal Flow
```
TradingView "NQ ORB Strategy" (Pine Script, MNQ1! 15m chart, entity WLAawi)
  -> Alert ID 4426604329 (strategy type, 15m, webhook enabled)
  -> Cloudflare Tunnel (clocks-jason-trend-using.trycloudflare.com/alert)
  -> paper_trader.py (:8766/alert)
  -> Telegram notification
```

### Files
| File | Purpose | Port | Auto-start |
|------|---------|------|------------|
| `trading/paper_trader.py` | Webhook receiver, trade logger, Telegram alerts | :8766 | Startup/PaperTrader.vbs |
| `trading/paper_trades.json` | Trade log (auto-managed by paper_trader.py) | — | — |
| `trading/.env` | Telegram bot token (gitignored) | — | — |
| `trading/CloudflareTunnel.vbs` | Source copy of tunnel launcher | — | — |

### Windows Startup Scripts (C:\Users\zedwa\AppData\...\Startup\)
| Script | Launches |
|--------|----------|
| PaperTrader.vbs | `pythonw paper_trader.py` |
| CloudflareTunnel.vbs | `cloudflared.exe tunnel --url http://localhost:8766` |
| TradingView.vbs | TradingView with CDP port 9222 |

### Pine Script (lives ONLY in TradingView editor — NO local files)
- "NQ ORB Strategy" — entity WLAawi on MNQ1! 15m chart
- Settings: R:R=2.0, Both directions, EMA/VWAP/ADX filters off, calc_on_every_tick=true

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

## JARVIS FIELD TECH (v1 scaffold — 2026-04-17)
Mobile PWA for pulling electrical drawings + manuals from Google Drive and troubleshooting toilet paper converting machines with a Jarvis-style HUD and voice. See `jarvis-field-tech/ACTIVE_FILES.md` for the full manifest.

| File | Purpose | Port |
|------|---------|------|
| `jarvis-field-tech/backend/app.py` | Flask API + serves React build | :5050 |
| `jarvis-field-tech/backend/drive_client.py` | Google Drive OAuth + folder cache | — |
| `jarvis-field-tech/backend/claude_client.py` | Claude Opus/Haiku routing for Jarvis persona | — |
| `jarvis-field-tech/backend/pdf_extractor.py` | PDF text extraction for Claude context | — |
| `jarvis-field-tech/frontend/` | React + Vite PWA, builds to `backend/static/` | — |
| `jarvis-field-tech/.env` | ANTHROPIC + Google OAuth + Drive folder ID (gitignored) | — |
| `scripts/JarvisFieldTech.vbs` | Auto-start backend on boot | — |
| `scripts/JarvisFieldTechTunnel.vbs` | Cloudflare tunnel for phone access | — |

Status: scaffolded 2026-04-17. Needs `.env` filled, `pip install -r requirements.txt`, `npm install && npm run build`, OAuth bootstrap via `python drive_client.py --auth`, then VBS added to Windows Startup folder.

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
| `cloudflared.exe` | Cloudflare tunnel binary |
| `.gitignore` | Protects keys, .env, logs |

---

## DELETED FILES LOG (for reference — don't recreate these)
| File | Deleted | Why |
|------|---------|-----|
| `trading/orb_bot.py` | 2026-04-10 | Standalone yfinance bot — replaced by TradingView strategy alert pipeline |
| `trading/orb_bot.log` | 2026-04-10 | Log for deleted bot |
| `trading/ORBBot.vbs` | 2026-04-10 | Launcher for deleted bot |
| `trading/tunnel_watcher.py` | 2026-04-10 | Old localhost.run watcher — replaced by Cloudflare tunnel |
| `trading/tunnel.log` | 2026-04-10 | Old tunnel log |
| `trading/strategies/mnq_orb_5m.pine` | 2026-04-10 | Old 5m Pine Script — live strategy is 15m in TradingView editor |
| `tradingview-mcp-jackson/orb_executor.py` | 2026-04-10 | CDP polling approach — replaced by webhook alert pipeline |
| `scripts/PaperTrader.vbs` | 2026-04-10 | Old version with localhost.run SSH tunnel |
| `Startup/ORBBot.vbs` | 2026-04-10 | Auto-start of deleted bot |
