# OmniAlpha proposed-bands report
_Generated: 2026-05-06T20:58:18_

## TL;DR

### crypto_btc15m_midband
- **YES side**: tradeable bands → 75-80c (forecast 81%)
- **NO side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping NO side off (or paused).

### crypto_btcd_midband
- **YES side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping YES side off (or paused).
- **NO side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping NO side off (or paused).

---

## Methodology
For each finalized market in the last 30 days (data cutoff Mar 7 2026) we found the trade closest to `close_time − 90s` and used its YES/NO price as the decision-time snapshot. Markets bucketed by 5¢ price ranges. A bucket is `TRADEABLE` only when n>=30 AND Wilson 95% lower bound on win rate beats the implied probability by at least 3¢ (covers fees + slippage). Anything else is INSUFFICIENT, NEAR_FAIR, or NEGATIVE.

## crypto_btc15m_midband — full breakdown
_Snapshots: 2832 total, 2832 in target 30-180s window. Resolved YES: 1427/2832 (50.4%)._

### crypto_btc15m_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 947 | 5 | 0.5 | [0.2, 1.2] | 2.5 | -2.3 | **NEAR_FAIR** |
| 5-10c | 124 | 3 | 2.4 | [0.8, 6.9] | 7.5 | -6.7 | **NEAR_FAIR** |
| 10-15c | 90 | 9 | 10.0 | [5.4, 17.9] | 12.5 | -7.1 | **NEAR_FAIR** |
| 15-20c | 29 | 5 | 17.2 | [7.6, 34.5] | 17.5 | -9.9 | **INSUFFICIENT** |
| 20-25c | 41 | 7 | 17.1 | [8.5, 31.3] | 22.5 | -14.0 | **NEAR_FAIR** |
| 25-30c | 42 | 11 | 26.2 | [15.3, 41.1] | 27.5 | -12.2 | **NEAR_FAIR** |
| 30-35c | 33 | 8 | 24.2 | [12.8, 41.0] | 32.5 | -19.7 | **NEAR_FAIR** |
| 35-40c | 24 | 7 | 29.2 | [14.9, 49.2] | 37.5 | -22.6 | **INSUFFICIENT** |
| 40-45c | 32 | 12 | 37.5 | [22.9, 54.7] | 42.5 | -19.6 | **NEAR_FAIR** |
| 45-50c | 33 | 16 | 48.5 | [32.5, 64.8] | 47.5 | -15.0 | **NEAR_FAIR** |
| 50-55c | 33 | 21 | 63.6 | [46.6, 77.8] | 52.5 | -5.9 | **NEAR_FAIR** |
| 55-60c | 26 | 16 | 61.5 | [42.5, 77.6] | 57.5 | -15.0 | **INSUFFICIENT** |
| 60-65c | 24 | 13 | 54.2 | [35.1, 72.1] | 62.5 | -27.4 | **INSUFFICIENT** |
| 65-70c | 43 | 26 | 60.5 | [45.6, 73.6] | 67.5 | -21.9 | **NEAR_FAIR** |
| 70-75c | 20 | 13 | 65.0 | [43.3, 81.9] | 72.5 | -29.2 | **INSUFFICIENT** |
| 75-80c | 34 | 32 | 94.1 | [80.9, 98.4] | 77.5 | +3.4 | **TRADEABLE** |
| 80-85c | 54 | 46 | 85.2 | [73.4, 92.3] | 82.5 | -9.1 | **NEAR_FAIR** |
| 85-90c | 61 | 52 | 85.2 | [74.3, 92.0] | 87.5 | -13.2 | **NEAR_FAIR** |
| 90-95c | 141 | 130 | 92.2 | [86.6, 95.6] | 92.5 | -5.9 | **NEAR_FAIR** |
| 95-100c | 1001 | 995 | 99.4 | [98.7, 99.7] | 97.5 | +1.2 | **NEAR_FAIR** |

### crypto_btc15m_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 1001 | 6 | 0.6 | [0.3, 1.3] | 2.5 | -2.2 | **NEAR_FAIR** |
| 5-10c | 124 | 10 | 8.1 | [4.4, 14.2] | 7.5 | -3.1 | **NEAR_FAIR** |
| 10-15c | 78 | 10 | 12.8 | [7.1, 22.0] | 12.5 | -5.4 | **NEAR_FAIR** |
| 15-20c | 47 | 6 | 12.8 | [6.0, 25.2] | 17.5 | -11.5 | **NEAR_FAIR** |
| 20-25c | 35 | 3 | 8.6 | [3.0, 22.4] | 22.5 | -19.5 | **NEAR_FAIR** |
| 25-30c | 36 | 9 | 25.0 | [13.8, 41.1] | 27.5 | -13.7 | **NEAR_FAIR** |
| 30-35c | 33 | 16 | 48.5 | [32.5, 64.8] | 32.5 | +0.0 | **NEAR_FAIR** |
| 35-40c | 24 | 11 | 45.8 | [27.9, 64.9] | 37.5 | -9.6 | **INSUFFICIENT** |
| 40-45c | 24 | 9 | 37.5 | [21.2, 57.3] | 42.5 | -21.3 | **INSUFFICIENT** |
| 45-50c | 31 | 10 | 32.3 | [18.6, 49.9] | 47.5 | -28.9 | **NEAR_FAIR** |
| 50-55c | 30 | 16 | 53.3 | [36.1, 69.8] | 52.5 | -16.4 | **NEAR_FAIR** |
| 55-60c | 39 | 24 | 61.5 | [45.9, 75.1] | 57.5 | -11.6 | **NEAR_FAIR** |
| 60-65c | 24 | 17 | 70.8 | [50.8, 85.1] | 62.5 | -11.7 | **INSUFFICIENT** |
| 65-70c | 35 | 27 | 77.1 | [61.0, 87.9] | 67.5 | -6.5 | **NEAR_FAIR** |
| 70-75c | 31 | 24 | 77.4 | [60.2, 88.6] | 72.5 | -12.3 | **NEAR_FAIR** |
| 75-80c | 36 | 27 | 75.0 | [58.9, 86.2] | 77.5 | -18.6 | **NEAR_FAIR** |
| 80-85c | 43 | 36 | 83.7 | [70.0, 91.9] | 82.5 | -12.5 | **NEAR_FAIR** |
| 85-90c | 75 | 66 | 88.0 | [78.7, 93.6] | 87.5 | -8.8 | **NEAR_FAIR** |
| 90-95c | 139 | 136 | 97.8 | [93.8, 99.3] | 92.5 | +1.3 | **NEAR_FAIR** |
| 95-100c | 947 | 942 | 99.5 | [98.8, 99.8] | 97.5 | +1.3 | **NEAR_FAIR** |


## crypto_btcd_midband — full breakdown
_Snapshots: 400 total, 61 in target 30-180s window. Resolved YES: 129/400 (32.2%)._

### crypto_btcd_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 264 | 0 | 0.0 | [0.0, 1.4] | 2.5 | -2.5 | **NEAR_FAIR** |
| 5-10c | 3 | 0 | 0.0 | [0.0, 56.2] | 7.5 | -7.5 | **INSUFFICIENT** |
| 10-15c | 1 | 0 | 0.0 | [0.0, 79.3] | 12.5 | -12.5 | **INSUFFICIENT** |
| 25-30c | 1 | 0 | 0.0 | [0.0, 79.3] | 27.5 | -27.5 | **INSUFFICIENT** |
| 45-50c | 1 | 0 | 0.0 | [0.0, 79.3] | 47.5 | -47.5 | **INSUFFICIENT** |
| 50-55c | 1 | 1 | 100.0 | [20.7, 100.0] | 52.5 | -31.8 | **INSUFFICIENT** |
| 65-70c | 1 | 0 | 0.0 | [0.0, 79.3] | 67.5 | -67.5 | **INSUFFICIENT** |
| 75-80c | 1 | 1 | 100.0 | [20.7, 100.0] | 77.5 | -56.8 | **INSUFFICIENT** |
| 80-85c | 2 | 2 | 100.0 | [34.2, 100.0] | 82.5 | -48.3 | **INSUFFICIENT** |
| 90-95c | 2 | 2 | 100.0 | [34.2, 100.0] | 92.5 | -58.3 | **INSUFFICIENT** |
| 95-100c | 123 | 123 | 100.0 | [97.0, 100.0] | 97.5 | -0.5 | **NEAR_FAIR** |

### crypto_btcd_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 123 | 0 | 0.0 | [0.0, 3.0] | 2.5 | -2.5 | **NEAR_FAIR** |
| 5-10c | 1 | 0 | 0.0 | [0.0, 79.3] | 7.5 | -7.5 | **INSUFFICIENT** |
| 10-15c | 1 | 0 | 0.0 | [0.0, 79.3] | 12.5 | -12.5 | **INSUFFICIENT** |
| 15-20c | 1 | 0 | 0.0 | [0.0, 79.3] | 17.5 | -17.5 | **INSUFFICIENT** |
| 20-25c | 2 | 0 | 0.0 | [0.0, 65.8] | 22.5 | -22.5 | **INSUFFICIENT** |
| 30-35c | 1 | 1 | 100.0 | [20.7, 100.0] | 32.5 | -11.8 | **INSUFFICIENT** |
| 45-50c | 1 | 0 | 0.0 | [0.0, 79.3] | 47.5 | -47.5 | **INSUFFICIENT** |
| 50-55c | 1 | 1 | 100.0 | [20.7, 100.0] | 52.5 | -31.8 | **INSUFFICIENT** |
| 75-80c | 1 | 1 | 100.0 | [20.7, 100.0] | 77.5 | -56.8 | **INSUFFICIENT** |
| 90-95c | 4 | 4 | 100.0 | [51.0, 100.0] | 92.5 | -41.5 | **INSUFFICIENT** |
| 95-100c | 264 | 264 | 100.0 | [98.6, 100.0] | 97.5 | +1.1 | **NEAR_FAIR** |


## Recommended JSON for strategy_bands.json

```json
{
  "crypto_btc15m_midband": {
    "yes_bands": [
      [
        0.75,
        0.8,
        0.81
      ]
    ],
    "no_bands": [],
    "updated_at": "2026-05-06T20:58:18.760415Z",
    "source": "historical_backtest_2026-05-06",
    "note": "Bands derived from /historical/trades reconstruction of decision-time prices (close-90s anchor) over last 30 days of finalized markets. Wilson 95% lower bound must beat implied probability by 3pts to qualify."
  },
  "crypto_btcd_midband": {
    "yes_bands": [],
    "no_bands": [],
    "updated_at": "2026-05-06T20:58:18.761526Z",
    "source": "historical_backtest_2026-05-06",
    "note": "Bands derived from /historical/trades reconstruction of decision-time prices (close-90s anchor) over last 30 days of finalized markets. Wilson 95% lower bound must beat implied probability by 3pts to qualify."
  }
}
```