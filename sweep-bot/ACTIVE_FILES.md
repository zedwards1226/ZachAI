# sweep-bot — Active Files Manifest

Every file in this project must be listed here. If it's not listed,
delete it.

## Python
- `main.py` — entry point (scheduler + CLI)
- `hunter.py` — poll → score → gate → execute
- `sb_config.py` — sweep-bot-specific constants (named `sb_config` to avoid collision with trading/config.py)

## Governance
- `CLAUDE.md` — project brain
- `ACTIVE_FILES.md` — this manifest

## Runtime (gitignored)
- `state/sweep_bot.json` — last_fired_ts, trades_today
- `logs/sweep_bot.log` — rotating log (5MB x 5)

## External (imported via sys.path, NOT copies)
From `C:\ZachAI\trading\`:
- `config.py` (constants: TIMEZONE, MULTIPLIER, VIX_*, RVOL_THRESHOLD, …)
- `agents.journal` (log_trade_open, get_today_stats, mark_failed_placement)
- `agents.sentinel` (is_blocked)
- `services.telegram` (notify_* with setup_type kwarg)
- `services.tv_trader` (place_bracket_order)
- `services.state_manager` (read_state)
