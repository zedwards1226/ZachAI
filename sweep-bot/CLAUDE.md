# sweep-bot — Standalone Liquidity Sweep Trader

## STATUS — DEFERRED (2026-04-28)
**NOT BUILT, NOT RUNNING, NO LAUNCHER.** This is a scaffold kept for future reference. Per master CLAUDE.md decision (Zach 2026-04-28): "we going build that later after we master the orb and its stable." Until ORB shows consistent profitability, only ORB connects to TradingView CDP — keeps the paper account uncluttered and diagnosis simple.

`scripts/start_sweep_bot.vbs` was deleted (commit 03b0a38). Code remains so we can pick it back up when the time comes — do NOT recreate the launcher or auto-start anything from this folder until the master CLAUDE.md status changes.

## DESIGN INTENT (when activated, not now)
Separate process that would run alongside ORB. Watches for SWEEP_CONFIRMED events (equal highs / equal lows taken out and reversed) and fires its own paper trades. Would share the journal + circuit breaker with ORB but with its own independent 3-trade daily budget.

## MODE (when activated)
- PAPER_MODE: ON — reuses `tv_trader.place_bracket_order`, which now enforces `PAPER_MODE=true` env guard
- Going live remains one of the 3 hard stops in master CLAUDE.md

## SESSION (when activated)
- Start: 09:30 ET
- End: 14:30 ET
- Poll interval: 15s

## BUDGETS (when activated)
- 3 sweep trades/day (independent from ORB's 2 → up to 5 total/day)
- Shared circuit breaker: 3 consecutive losses across ORB + sweep-bot stops both bots

## STARTUP (when activated — currently disabled)
Launcher to recreate: `scripts/start_sweep_bot.vbs` (deleted, see commit 03b0a38 for prior contents).
Manual run for debugging only: `python C:\ZachAI\sweep-bot\main.py`
Dry-run: `python main.py --dry-run`
One-shot: `python main.py --once`
**Reactivation gate:** before recreating the launcher, confirm with Zach that ORB has reached consistent profitability and add sweep-bot back to master CLAUDE.md PROJECT ROSTER as active.

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
