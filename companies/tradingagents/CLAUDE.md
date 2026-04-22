# TradingAgents — Project Brain

## STATUS
**BUILDING** — scaffolded 2026-04-10. Not auto-started. Not wired to live ORB pipeline. No VBS launcher. Do NOT start alongside ORB (`trading/main.py`) — both would place orders on the same MNQ chart.

## PURPOSE
Multi-agent FastAPI gate that sits in front of TradingView webhook alerts. Rule-based overseer + Claude-assisted context agents score each signal before allowing order placement. Designed to eventually replace or augment the ORB pipeline (`trading/`).

## PAPER MODE
ON. `config.py` hard-codes `PAPER_MODE=True`. No real money path exists.

## ENTRY POINTS
- `main.py` — FastAPI on port 8766 (gate + webhook receiver)
- `database.py` — SQLite at `db/tradingagents.db`

## AGENTS (phased build)
| File | Phase | Status |
|---|---|---|
| `agents/overseer.py` | 2 | BUILT — rule-based guardrails |
| `agents/sentinel.py` | 4 | scaffolded |
| `agents/sweep_detector.py` | 5 | scaffolded |
| `agents/context.py` | 6 | scaffolded |
| `agents/trade_monitor.py` | 7 | scaffolded |
| `agents/analyst.py` | 8 | scaffolded |

## COLLISION RULES
- **DO NOT** import from `C:\ZachAI\trading\` — it starts a scheduler on import.
- **DO NOT** bind to port 9222 — TradingView CDP uses it.
- Port 8766 is reserved for this project only.

## KEYS REQUIRED (before going live)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env`
- `ANTHROPIC_API_KEY` in `.env`

## AUTO-MERGE
Safe — no live trade path touches master. But if a VBS is ever added and this goes live, promote to the auto-merge exception list in master CLAUDE.md.

## SEE ALSO
- `ACTIVE_FILES.md` — file manifest
- `C:\ZachAI\CLAUDE.md` — master brain
