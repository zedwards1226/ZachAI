# ICTBot Setup Library

One file per setup name; this document captures rules in plain text so we can
review and tune without reading code.

## #1 — NY AM FVG (Fair Value Gap, NY AM killzone)

**Status:** active in Phase 1 (only setup)
**Code:** `strategies/ny_am_fvg.py`
**Window:** 09:30–10:30 ET (FVG must form here); entry valid until 11:00 ET

### Detection
- Pull last ~100 5m bars on the configured symbol (default MES1!)
- Find 3-bar FVGs with:
  - `gap_size ≥ FVG_MIN_GAP_POINTS` (default 3.0 ES pts)
  - middle-bar body `≥ DISPLACEMENT_MIN_POINTS` (default 5.0 pts)
- Restrict to FVGs whose middle bar is between 09:30 and 10:30 ET

### HTF bias filter
- `htf_bias` is computed from 1H bars: 50-period EMA vs current close
  - close > EMA × 1.0005 → `long`
  - close < EMA × 0.9995 → `short`
  - else → `neutral` (skip)
- Only take FVG direction matching bias (bullish FVG when bias=long, bearish when bias=short)

### Entry trigger
- Last closed 5m bar must wick INTO the FVG zone
- Bar must close inside the zone OR closed beyond the midpoint in bias direction
- Entry price = last bar's close (market on next open in live)

### Stop / Target
- Stop = opposite extreme of the 3-bar displacement window
  - long: `min(low of bars i-1, i, i+1)` − `STOP_BUFFER_POINTS` (default 3 pts)
  - short: `max(high of bars i-1, i, i+1)` + buffer
- Target = entry + (risk × `DEFAULT_RR_TARGET`) (default 2.0R)
  - capped at PDH/PDL if closer (long: PDH; short: PDL)
- Skip if final R:R < 1.0

### Skip conditions
- VIX > 30 (Phase 2 — needs VIX feed)
- Scheduled CPI / NFP / FOMC today (`config.HIGH_IMPACT_DAYS_2026`)
- Bot already has open position
- Cross-bot halt set in `data/risk_state.json`

### Exit management (handled by `services/trade_manager.py`)
- TP touch → close at TP, log `tp_hit`
- SL touch → close at SL, log `sl_hit`
- 120 minutes elapsed → time exit
- 14:55 ET → hard close
- (BE move at 1R is Phase 2 enhancement)

---

## Future setups (NOT YET ACTIVE)

### #2 Silver Bullet (Phase 3)
FVG entries in 10:00–11:00 ET and 14:00–15:00 ET windows specifically.
Same rules as NY AM FVG but tighter window + slightly tighter stops.

### #3 Judas Swing (Phase 3)
Sweep of pre-9:30 range or RTH-open range in first 30min, then MSS reversal.
- Detect: 9:30–10:00 bar prints low below pre-RTH low (or high above pre-RTH high)
- Confirmation: bar closes back inside the range
- Entry on first 5m close that creates a counter-direction FVG

### #4 Sellside / Buyside Sweep (Phase 3)
Equal highs/lows liquidity grab + reversal.
- Mark equal highs/lows in last 5 sessions where price tagged within 0.5pt
- Wait for sweep bar that takes them out and closes back inside
- Entry on retest of the sweep level
