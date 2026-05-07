# OmniAlpha crypto recalibration report
_Generated: 2026-05-06T20:22:30_

## TL;DR (what this report actually says)

We have **88 closed crypto trades** total — small. The math gets statistical at sample sizes ~30+ per bucket; we have one bucket (`btcd YES 75-80c`) with n=12 and one (`btcd NO 75-80c`) with n=13. Everything else is too thin for a confident verdict.

**What the raw P&L tells us anyway** (without statistical confidence):

- `btcd_midband` NO at 70-80¢: **−$110** over 19 trades. Direction is clear even if Wilson can't prove it at 95%. **Keep paused.**
- `btc15m_midband` YES at 80-85¢: **−$26** over 6 trades. Small but trending wrong; calibration is 2 months old. **Keep trimmed.**
- `btcd_midband` YES at 70-85¢: **+$71** over 26 trades, 88% WR. Closest thing to a real working bucket. **Keep running.**
- `sol15m_midband` YES: +$22 over 7 trades. Looks good but n is too small to call. **Watch.**
- Everything else: too few trades to have an opinion.

**The fundamental data problem:** the bot didn't record the YES price at the moment we'd hypothetically have entered. Kalshi's historical endpoints only return final state. So we can't backtest "what would have happened if we ran with band X" — we can only audit what DID happen with the bands we used. Real recalibration requires either (a) modifying the bot to log decision-time price snapshots going forward, or (b) pulling Kalshi `/historical/trades` per finalized market and reconstructing pre-close prices (slow but doable). Both are follow-up tasks.

**Practical recommendation for tonight:** keep the two pauses live. Don't widen anything. Re-run this script weekly to watch n grow.

---

Built from live `trades` table only (88 closed trades). Kalshi historical endpoints don't include intra-market price snapshots, and the local `markets` table overwrites prices on settlement. So this is the most honest read available — small but real.

**Verdict legend**
- **KEEP / has edge** — Wilson 95% lower bound on win rate beats the implied probability by ≥3 pts
- **DROP / negative edge** — Wilson 95% upper bound is below implied minus 3 pts
- **WATCH** — confidence interval crosses fair value (signal not strong either way)
- **NEED MORE DATA** — fewer than 10 closed trades in this bucket

Buckets are 5¢ wide. `n` = total closed trades, `W` = wins, `WR%` = raw win rate, `Wilson95 [lo, hi]` = 95% confidence interval, `implied%` = avg price of the side bought (i.e. what the market thought the win rate was).

## crypto_btc15m_midband — NO side

_Total: 4 trades, 4W (100.0% raw WR), $+5.56 on $19.09 stake (+29.1% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 70-75c | 2 | 2 | 0 | 100.0 | [34.2, 100.0] | 73.5 | -39.3 | $3.67 | $+1.24 | +33.7 | NEED MORE DATA |
| 75-80c | 2 | 2 | 0 | 100.0 | [34.2, 100.0] | 77.5 | -43.3 | $15.42 | $+4.32 | +28.0 | NEED MORE DATA |

## crypto_btc15m_midband — YES side

_Total: 7 trades, 5W (71.4% raw WR), $-25.48 on $69.63 stake (-36.6% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 80-85c | 6 | 4 | 2 | 66.7 | [30.0, 90.3] | 83.0 | -53.0 | $68.78 | $-25.62 | -37.2 | NEED MORE DATA |
| 85-90c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 85.0 | -64.3 | $0.85 | $+0.14 | +16.4 | NEED MORE DATA |

## crypto_btcd_midband — NO side

_Total: 25 trades, 16W (64.0% raw WR), $-87.86 on $399.17 stake (-22.0% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 65-70c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 67.0 | -46.3 | $25.46 | $+11.95 | +46.9 | NEED MORE DATA |
| 70-75c | 6 | 3 | 3 | 50.0 | [18.8, 81.2] | 72.7 | -53.9 | $107.33 | $-36.38 | -33.9 | NEED MORE DATA |
| 75-80c | 13 | 8 | 5 | 61.5 | [35.5, 82.3] | 78.1 | -42.6 | $207.03 | $-73.28 | -35.4 | WATCH (confidence overlaps fair value) |
| 80-85c | 4 | 4 | 0 | 100.0 | [51.0, 100.0] | 81.8 | -30.7 | $56.68 | $+12.55 | +22.1 | NEED MORE DATA |
| 85-90c | 1 | 0 | 1 | 0.0 | [0.0, 79.3] | 89.0 | -89.0 | $2.67 | $-2.70 | -101.1 | NEED MORE DATA |

## crypto_btcd_midband — YES side

_Total: 27 trades, 24W (88.9% raw WR), $+71.17 on $516.31 stake (+13.8% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 70-75c | 8 | 7 | 1 | 87.5 | [52.9, 97.8] | 72.6 | -19.7 | $190.21 | $+25.12 | +13.2 | NEED MORE DATA |
| 75-80c | 12 | 10 | 2 | 83.3 | [55.2, 95.3] | 77.5 | -22.3 | $223.40 | $+25.07 | +11.2 | WATCH (confidence overlaps fair value) |
| 80-85c | 6 | 6 | 0 | 100.0 | [61.0, 100.0] | 81.7 | -20.7 | $90.38 | $+19.41 | +21.5 | NEED MORE DATA |
| 85-90c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 88.0 | -67.3 | $12.32 | $+1.57 | +12.7 | NEED MORE DATA |

## crypto_eth15m_midband — NO side

_Total: 7 trades, 6W (85.7% raw WR), $+8.63 on $87.85 stake (+9.8% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 65-70c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 68.0 | -47.3 | $26.52 | $+11.88 | +44.8 | NEED MORE DATA |
| 75-80c | 4 | 4 | 0 | 100.0 | [51.0, 100.0] | 76.5 | -25.5 | $28.17 | $+8.31 | +29.5 | NEED MORE DATA |
| 80-85c | 2 | 1 | 1 | 50.0 | [9.5, 90.5] | 83.0 | -73.5 | $33.16 | $-11.56 | -34.9 | NEED MORE DATA |

## crypto_eth15m_midband — YES side

_Total: 4 trades, 3W (75.0% raw WR), $-12.10 on $66.61 stake (-18.2% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 65-70c | 3 | 2 | 1 | 66.7 | [20.8, 93.9] | 67.7 | -46.9 | $57.01 | $-14.36 | -25.2 | NEED MORE DATA |
| 80-85c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 80.0 | -59.3 | $9.60 | $+2.26 | +23.5 | NEED MORE DATA |

## crypto_ethd_midband — NO side

_Total: 3 trades, 3W (100.0% raw WR), $+7.17 on $47.36 stake (+15.1% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 85-90c | 3 | 3 | 0 | 100.0 | [43.8, 100.0] | 86.3 | -42.5 | $47.36 | $+7.17 | +15.1 | NEED MORE DATA |

## crypto_ethd_midband — YES side

_Total: 3 trades, 2W (66.7% raw WR), $+4.97 on $32.54 stake (+15.3% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 75-80c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 76.0 | -55.3 | $22.04 | $+6.58 | +29.9 | NEED MORE DATA |
| 85-90c | 2 | 1 | 1 | 50.0 | [9.5, 90.5] | 88.0 | -78.5 | $10.50 | $-1.61 | -15.3 | NEED MORE DATA |

## crypto_sol15m_midband — NO side

_Total: 1 trades, 1W (100.0% raw WR), $+4.35 on $15.40 stake (+28.2% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 75-80c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 77.0 | -56.3 | $15.40 | $+4.35 | +28.2 | NEED MORE DATA |

## crypto_sol15m_midband — YES side

_Total: 7 trades, 5W (71.4% raw WR), $+22.54 on $145.49 stake (+15.5% ROI)_

| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 60-65c | 2 | 2 | 0 | 100.0 | [34.2, 100.0] | 64.0 | -29.8 | $60.16 | $+32.31 | +53.7 | NEED MORE DATA |
| 70-75c | 1 | 1 | 0 | 100.0 | [20.7, 100.0] | 70.0 | -49.3 | $19.60 | $+7.98 | +40.7 | NEED MORE DATA |
| 75-80c | 2 | 2 | 0 | 100.0 | [34.2, 100.0] | 77.0 | -42.8 | $37.73 | $+10.66 | +28.3 | NEED MORE DATA |
| 80-85c | 2 | 0 | 2 | 0.0 | [0.0, 65.8] | 80.0 | -80.0 | $28.00 | $-28.41 | -101.5 | NEED MORE DATA |
