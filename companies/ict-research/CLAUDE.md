# ICT Research Lab

## Mission
Study every ICT (Inner Circle Trader) strategy from his YouTube channel, codify the rules, backtest on MNQ historical data, rank by composite edge score, and — if a strategy survives the gauntlet — spin up a live paper bot that trades it alongside ORB.

**Paper mode ONLY. No live money touches the ICT bot until Zach approves.**

## 7-Agent Pipeline

```
Harvester ─► Librarian ─► Extractor ─► Coder ─► Backtester ─► Judge ─► Bot Builder
 (YT dl)   (tag/dedupe)   (LLM rules)  (py fn)   (MNQ 5yr)    (rank)    (deploy)
```

| Agent | Role | Input | Output |
|---|---|---|---|
| Harvester | Pull ICT YT transcripts (channel + playlists) | channel ID | `data/transcripts/*.json` |
| Librarian | Tag + dedupe by setup name | transcripts | `data/transcripts/index.json` |
| Extractor | LLM → machine-readable rules | tagged transcripts | `data/rules/<setup>.json` |
| Coder | Rules → Python backtest function | rules.json | `forge/strategies/<setup>.py` |
| Backtester | Run on 5yr MNQ 1m/5m/15m | strategies + data | `data/backtests/<setup>.json` |
| Judge | Rank, walk-forward validate | backtest results | `data/judge/leaderboard.json` |
| Bot Builder | Deploy winner as sibling of ORB | winning strategy | new project folder |

## "Best Strategy" Criteria

A strategy is PROMOTED to paper trading only if ALL pass:
- ≥ 100 trades in backtest (statistical significance)
- Walk-forward out-of-sample: train 2020-2024, test 2025 — must hold up
- Realistic costs: 2 ticks slippage + $1.50 commission per MNQ
- Sharpe > 1.0 AND max drawdown < 20% AND profit factor > 1.5
- Beats buy-and-hold MNQ return
- Matches ORB bot or better

Composite rank: `0.4*Sharpe + 0.3*PF + 0.2*(1 - MaxDD) + 0.1*(wins/trades)`

## Folder Layout

```
companies/ict-research/
├── CLAUDE.md              # this file
├── ACTIVE_FILES.md        # manifest
├── scout/                 # Harvester + Librarian + Extractor
├── forge/                 # Coder + Backtester + Judge
│   └── strategies/        # one .py per codified ICT setup
├── data/
│   ├── transcripts/       # YT transcripts (gitignored)
│   ├── rules/             # extracted rules JSON
│   ├── backtests/         # backtest result JSON
│   └── judge/             # leaderboard
├── logs/                  # runtime logs (gitignored)
└── README.md              # human-facing overview
```

## Reference Repos (to clone + study, NOT fork wholesale)

Per build-first rule, these three get cloned into `C:\ZachAI\reference\` (gitignored):
1. **ajaygm18/ict-trading-ai-agent** — full ICT bot w/ ML + backtest + execution
2. **Therealtuk/SmartMoneyAI-SMC-Trading-Dashboard-Strategy-Backtester** — SMC indicator + backtester
3. **Ad1xon/AI-Algorithmic-Trading-Backtester** — recent (2026-03) MT5 + SMC + ML backtester

For transcripts:
4. **Dennis-1am/YT_Metadata_Downloader** — YT Data V3 API + transcript_api, channel-wide pull

## Auto-merge Exceptions
- `forge/strategies/*.py` — BEFORE any strategy is promoted to live paper trading, Zach approves the promotion. Strategy code itself auto-merges.
- Any file in a new `companies/ict-bot/` folder (spun up by Bot Builder) follows the same notify-first policy as `trading/` and `kalshi/`.

## Current Status (2026-04-20)
- 6 / 7 agents live: Harvester, Librarian, Extractor, Coder, Backtester, Judge
- Tech stack hardened: `smartmoneyconcepts` (joshyattridge) for ICT primitives, `vectorbt` for metrics
- Lookahead bias guarded at 3 layers: Coder system prompt rules → AST + smoke gate → truncation-equivalence test
- 2 hand-written reference strategies in `forge/strategies/` (Gemini quota exhausted; LLM regen tomorrow)
- End-to-end Judge run: 0 / 2 strategies promoted (both correctly REJECTED — system working as designed)

## Next Actions
1. Wait for Gemini daily quota reset → re-run Coder on remaining rules JSONs
2. Harvest remaining ICT videos through Extractor for more rule sets
3. Build Agent 7 (Bot Builder) — deploy first PROMOTED strategy as a sibling of `trading/` ORB bot
