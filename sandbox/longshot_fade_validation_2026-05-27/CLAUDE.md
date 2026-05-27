# Experiment: Longshot-Fade Edge Validation

## Goal
Confirm the **NO-side longshot-fade edge** on Kalshi sports markets exists in real data before writing any new bot code. Becker 2026 + Whelan 2026 papers say it does at aggregate. This experiment proves (or disproves) it on Zach's actual addressable universe.

## Method
1. Pull 30 days of **settled markets** for the 4 highest-volume sport series via Kalshi's free `/historical/markets` endpoint (no auth, no money, read-only).
   - KXNBAGAME (NBA games)
   - KXNFLGAME (NFL games — likely sparse, off-season)
   - KXEPLGAME (Premier League soccer)
   - KXUFC (UFC fights)
2. For each settled market, record:
   - `series_ticker`, `ticker`, `close_time`
   - `last_price_dollars` (= implied YES probability at close)
   - `result` (`yes` or `no`)
   - `volume_fp` (total $ flowed — liquidity proxy)
3. Bucket trades by **NO price** = `1 - last_yes`:
   - 85-89¢ (deep longshot fade)
   - 90-94¢ (very deep)
   - 95-99¢ (extreme)
4. For each bucket compute: actual NO-win rate vs implied. Edge = actual − implied.
5. Estimate fill rate: count markets/day in each bucket as a proxy (no orderbook history available).
6. Write report. Decision gate per main plan.

## Decision Gate
**GREEN** if BOTH:
- Measured NO win rate at 85-95¢ ≥ implied + 1.5 percentage points
- ≥ 3 markets/day in the band across all 4 series (proxy for fill opportunity)

**RED** if either fails — post-mortem, no Phase 2.

## Data window
- Kalshi `/historical/cutoff` reports data through **2026-03-28**
- Pulling 30 days back from cutoff: **2026-02-26 → 2026-03-28**
- 60 days stale vs today — note in report. Recent institutional MM activity may have shifted the edge.

## Sandbox rule compliance
- **Rule 1 (ports 8000-8999)** — N/A, no server runs in this experiment
- **Rule 2 (no writes to production state)** — local SQLite at `db/markets.db` only
- **Rule 3 (no live-code imports)** — imports `omnialpha.bots.kalshi_public` only (now a shared library, not a live bot; no scheduler side effects)
- **Rule 4 (no auto-start)** — manual `python run.py` only
- **Rule 6 (PAPER_MODE)** — no orders placed; pure read-only HTTP

## Files
- `run.py` — orchestrator: pull → analyze → report
- `pull_markets.py` — paginated `/historical/markets` puller, writes to `db/markets.db`
- `analyze.py` — reads SQLite, computes WR-by-bucket, fill-rate proxy, writes `report.md`
- `report.md` — output: tables + decision (created by `analyze.py`)
- `db/markets.db` — SQLite cache (gitignored via sandbox patterns)

## Lifecycle
This experiment graduates when:
- Report exists with a green/red verdict
- Verdict has been reviewed by Zach
- Either the new longshot bot ships (delete this dir), or the post-mortem is filed (delete this dir)

Per sandbox rule 5: delete the subfolder on graduation or abandonment.
