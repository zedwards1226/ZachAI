# Sandbox — Experiments Workspace

## PURPOSE
Protected area where Zach (and Jarvis) can build + test new strategies, agents, or services **without any risk of interfering with the live ORB bot, Kalshi bot, Telegram bot, or wpflow server.**

If you are about to edit, run, or import anything inside this folder, you are NOT touching production. Good.

If you need to touch production, you do NOT do it from here — you graduate the proven code into `trading/`, `kalshi/`, etc. via an explicit commit after Zach approves.

## HARD RULES (no exceptions)

| # | Rule | Why |
|---|---|---|
| 1 | **Ports 8000–8999 only.** Never bind 5000, 3001, 9222, 8765, 8766. | 5000=kalshi, 3001=dashboard, 9222=TV CDP, 8766=tradingagents |
| 2 | **No writes to production state.** All `.db` / state files live in `sandbox/<experiment>/db/` or `state/`. Never write to `trading/state/`, `trading/journal.db`, `kalshi/db/`, `kalshi/bots/weatheralpha.db`, `companies/*/db/`. |
| 3 | **No importing live code.** No `from trading import ...`, no `from kalshi.bots import ...`. Copy what you need into the experiment. Live agents start schedulers on import. |
| 4 | **Zero auto-start.** No VBS files in `sandbox/`. No entries in Windows Startup. No cron. Manual `python run.py` only. |
| 5 | **Each experiment = its own subfolder + CLAUDE.md + ACTIVE_FILES.md.** Delete the subfolder when you graduate or abandon the experiment. |
| 6 | **PAPER_MODE=True is mandatory.** Any Kalshi/TradingView API call routes through a demo or mock client. Zero real-money path exists. |
| 7 | **No credentials copied from production.** Each experiment gets its own `.env` with its own test keys. Real `trading/.env` and `kalshi/.env` stay where they are. |

## DIRECTORY LAYOUT

```
sandbox\
├── CLAUDE.md              # this file
├── ACTIVE_FILES.md        # manifest of current experiments
├── README.md              # how to start an experiment
├── requirements.txt       # sandbox-only pip deps
├── .env                   # sandbox-only test tokens (gitignored)
├── .gitignore
└── _template\             # copy this to start a new experiment
    ├── CLAUDE.md
    ├── run.py
    └── db\.gitkeep
```

## HOW TO START AN EXPERIMENT

```bash
# 1. Copy template
cp -r sandbox/_template sandbox/my-experiment

# 2. Edit its CLAUDE.md — describe scope, ports, deps
# 3. Run it (never auto-started)
cd sandbox/my-experiment && python run.py
```

See `README.md` for the full workflow.

## GRADUATION PATH

1. Experiment runs, passes backtest / smoke test.
2. Zach reviews, gives explicit go.
3. Cherry-pick the specific files into `trading/`, `kalshi/`, `telegram-bridge/`, etc.
4. Update production CLAUDE.md + ACTIVE_FILES.md.
5. Delete the sandbox experiment folder.

## IF YOU'RE NOT SURE
Ask. Don't guess. Sandbox exists so "trying something" doesn't crash the live bots at 9:30 AM on a Monday.
