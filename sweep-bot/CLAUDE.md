# sweep-bot — Standalone Liquidity Sweep Trader

Separate process that runs alongside ORB. Watches for SWEEP_CONFIRMED
events (equal highs / equal lows taken out and reversed) and fires its
own paper trades. Shares the journal + circuit breaker with ORB but
has its own independent 3-trade daily budget.

## MODE
- **PAPER_MODE: ON** (reuses tv_trader paper path — no config of its own for mode)
- Live mode gated by the 3 hard stops in master CLAUDE.md

## SESSION
- Start: 09:30 ET
- End: 14:30 ET
- Poll interval: 15s

## BUDGETS
- 3 sweep trades/day (independent from ORB's 3 → up to 6 total/day)
- Shared circuit breaker: 3 consecutive losses across ORB + sweep-bot stops both bots

## STARTUP
`C:\ZachAI\scripts\start_sweep_bot.vbs` — silent launcher, add to Task Scheduler at 09:20 ET.
Manual: `python C:\ZachAI\sweep-bot\main.py`
Dry-run: `python main.py --dry-run`
One-shot: `python main.py --once`

## ARCHITECTURE
- Reads `C:\ZachAI\trading\state\sweep.json` (sweep.py in ORB process is the single writer).
- Imports shared code via sys.path bootstrap — no duplicate detectors.
- Own state file: `sweep-bot/state/sweep_bot.json` (last_fired_ts, trades_today).
- Own log: `sweep-bot/logs/sweep_bot.log` (rotating, 5MB x 5).

## KEY FILES
- `main.py` — scheduler + CLI (`--once`, `--dry-run`)
- `hunter.py` — score + gate + execute
- `sb_config.py` — session, budgets, scoring floors (named `sb_config` to avoid shadowing `trading/config.py` on sys.path)
- `state/sweep_bot.json` — runtime state
- `logs/sweep_bot.log` — rotating log

## SIGNAL PIPELINE (hunter.py)
1. Read sweep.json; filter to NEW SWEEP_CONFIRMED.
2. Qualify — wick ≥ MIN_WICK_POINTS (5.0), pool ≥ MIN_POOL_BARS (2).
3. Score — htf_bias(+2), rvol(+1), vwap_alignment(+1), vix_regime(+1),
   prior_day_direction(+1), wick_strength(+2), pool_depth(+1);
   penalties at_level(-5), bias_conflict(-2), approaching_wall(-1).
4. Gate — score ≥ SCORE_FLOOR (5), trades_today < 3, circuit breaker < 3,
   no hard blocks (VIX>30, sentinel news/truth block).
5. Compute — entry = close of confirmation bar; stop = level ± (wick + 0.25*ATR);
   T1 = 1R, T2 = 2R. HALF if score 5-7, FULL if ≥8.
6. Fire — journal.log_trade_open(setup_type="SWEEP_REV"),
   telegram.notify_trade_entry(setup_type="SWEEP_REV"),
   tv_trader.place_bracket_order(...).
7. Persist last_fired_ts.

## AUTO-MERGE EXCEPTIONS
- Changes to `hunter.py` affect live paper execution — commit + push but
  notify Zach BEFORE merging to master (same rule as tv_trader.py).
- `sb_config.py` threshold tweaks go direct to master (same as other config).
