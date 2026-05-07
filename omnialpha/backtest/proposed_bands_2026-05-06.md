# OmniAlpha proposed-bands report
_Generated: 2026-05-06T22:14:41_

## TL;DR

### crypto_btc15m_midband
- **YES side**: tradeable bands → 75-80c (forecast 81%)
- **NO side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping NO side off (or paused).

### crypto_btcd_midband
- **YES side**: tradeable bands → 20-25c (forecast 35%)
- **NO side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping NO side off (or paused).

### crypto_eth15m_midband
- **YES side**: tradeable bands → 65-70c (forecast 71%), 80-85c (forecast 86%)
- **NO side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping NO side off (or paused).

### crypto_sol15m_midband
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
_Snapshots: 6192 total, 1257 in target 30-180s window. Resolved YES: 3225/6192 (52.1%)._

### crypto_btcd_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 2829 | 3 | 0.1 | [0.0, 0.3] | 2.5 | -2.5 | **NEAR_FAIR** |
| 5-10c | 48 | 1 | 2.1 | [0.4, 10.9] | 7.5 | -7.1 | **NEAR_FAIR** |
| 10-15c | 26 | 2 | 7.7 | [2.1, 24.1] | 12.5 | -10.4 | **INSUFFICIENT** |
| 15-20c | 17 | 2 | 11.8 | [3.3, 34.3] | 17.5 | -14.2 | **INSUFFICIENT** |
| 20-25c | 31 | 16 | 51.6 | [34.8, 68.0] | 22.5 | +12.3 | **TRADEABLE** |
| 25-30c | 7 | 3 | 42.9 | [15.8, 75.0] | 27.5 | -11.7 | **INSUFFICIENT** |
| 30-35c | 9 | 4 | 44.4 | [18.9, 73.3] | 32.5 | -13.6 | **INSUFFICIENT** |
| 35-40c | 7 | 5 | 71.4 | [35.9, 91.8] | 37.5 | -1.6 | **INSUFFICIENT** |
| 40-45c | 8 | 2 | 25.0 | [7.1, 59.1] | 42.5 | -35.4 | **INSUFFICIENT** |
| 45-50c | 10 | 5 | 50.0 | [23.7, 76.3] | 47.5 | -23.8 | **INSUFFICIENT** |
| 50-55c | 5 | 2 | 40.0 | [11.8, 76.9] | 52.5 | -40.7 | **INSUFFICIENT** |
| 55-60c | 6 | 4 | 66.7 | [30.0, 90.3] | 57.5 | -27.5 | **INSUFFICIENT** |
| 60-65c | 2 | 2 | 100.0 | [34.2, 100.0] | 62.5 | -28.3 | **INSUFFICIENT** |
| 65-70c | 9 | 7 | 77.8 | [45.3, 93.7] | 67.5 | -22.2 | **INSUFFICIENT** |
| 70-75c | 4 | 1 | 25.0 | [4.6, 69.9] | 72.5 | -67.9 | **INSUFFICIENT** |
| 75-80c | 8 | 6 | 75.0 | [40.9, 92.9] | 77.5 | -36.6 | **INSUFFICIENT** |
| 80-85c | 23 | 22 | 95.7 | [79.0, 99.2] | 82.5 | -3.5 | **INSUFFICIENT** |
| 85-90c | 18 | 17 | 94.4 | [74.2, 99.0] | 87.5 | -13.3 | **INSUFFICIENT** |
| 90-95c | 64 | 62 | 96.9 | [89.3, 99.1] | 92.5 | -3.2 | **NEAR_FAIR** |
| 95-100c | 3061 | 3059 | 99.9 | [99.8, 100.0] | 97.5 | +2.3 | **NEAR_FAIR** |

### crypto_btcd_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 3061 | 2 | 0.1 | [0.0, 0.2] | 2.5 | -2.5 | **NEAR_FAIR** |
| 5-10c | 55 | 2 | 3.6 | [1.0, 12.3] | 7.5 | -6.5 | **NEAR_FAIR** |
| 10-15c | 27 | 1 | 3.7 | [0.7, 18.3] | 12.5 | -11.8 | **INSUFFICIENT** |
| 15-20c | 18 | 1 | 5.6 | [1.0, 25.8] | 17.5 | -16.5 | **INSUFFICIENT** |
| 20-25c | 12 | 1 | 8.3 | [1.5, 35.4] | 22.5 | -21.0 | **INSUFFICIENT** |
| 25-30c | 7 | 4 | 57.1 | [25.0, 84.2] | 27.5 | -2.5 | **INSUFFICIENT** |
| 30-35c | 7 | 2 | 28.6 | [8.2, 64.1] | 32.5 | -24.3 | **INSUFFICIENT** |
| 35-40c | 2 | 0 | 0.0 | [0.0, 65.8] | 37.5 | -37.5 | **INSUFFICIENT** |
| 40-45c | 5 | 2 | 40.0 | [11.8, 76.9] | 42.5 | -30.7 | **INSUFFICIENT** |
| 45-50c | 4 | 1 | 25.0 | [4.6, 69.9] | 47.5 | -42.9 | **INSUFFICIENT** |
| 50-55c | 9 | 5 | 55.6 | [26.7, 81.1] | 52.5 | -25.8 | **INSUFFICIENT** |
| 55-60c | 11 | 8 | 72.7 | [43.4, 90.3] | 57.5 | -14.1 | **INSUFFICIENT** |
| 60-65c | 7 | 2 | 28.6 | [8.2, 64.1] | 62.5 | -54.3 | **INSUFFICIENT** |
| 65-70c | 9 | 5 | 55.6 | [26.7, 81.1] | 67.5 | -40.8 | **INSUFFICIENT** |
| 70-75c | 2 | 0 | 0.0 | [0.0, 65.8] | 72.5 | -72.5 | **INSUFFICIENT** |
| 75-80c | 30 | 14 | 46.7 | [30.2, 63.9] | 77.5 | -47.3 | **NEGATIVE** |
| 80-85c | 23 | 20 | 87.0 | [67.9, 95.5] | 82.5 | -14.6 | **INSUFFICIENT** |
| 85-90c | 19 | 18 | 94.7 | [75.4, 99.1] | 87.5 | -12.1 | **INSUFFICIENT** |
| 90-95c | 55 | 53 | 96.4 | [87.7, 99.0] | 92.5 | -4.8 | **NEAR_FAIR** |
| 95-100c | 2829 | 2826 | 99.9 | [99.7, 100.0] | 97.5 | +2.2 | **NEAR_FAIR** |


## crypto_eth15m_midband — full breakdown
_Snapshots: 2832 total, 2802 in target 30-180s window. Resolved YES: 1421/2832 (50.2%)._

### crypto_eth15m_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 970 | 3 | 0.3 | [0.1, 0.9] | 2.5 | -2.4 | **NEAR_FAIR** |
| 5-10c | 138 | 6 | 4.3 | [2.0, 9.2] | 7.5 | -5.5 | **NEAR_FAIR** |
| 10-15c | 81 | 5 | 6.2 | [2.7, 13.6] | 12.5 | -9.8 | **NEAR_FAIR** |
| 15-20c | 43 | 6 | 14.0 | [6.6, 27.3] | 17.5 | -10.9 | **NEAR_FAIR** |
| 20-25c | 39 | 5 | 12.8 | [5.6, 26.7] | 22.5 | -16.9 | **NEAR_FAIR** |
| 25-30c | 33 | 10 | 30.3 | [17.4, 47.3] | 27.5 | -10.1 | **NEAR_FAIR** |
| 30-35c | 39 | 17 | 43.6 | [29.3, 59.0] | 32.5 | -3.2 | **NEAR_FAIR** |
| 35-40c | 21 | 4 | 19.0 | [7.7, 40.0] | 37.5 | -29.8 | **INSUFFICIENT** |
| 40-45c | 22 | 8 | 36.4 | [19.7, 57.0] | 42.5 | -22.8 | **INSUFFICIENT** |
| 45-50c | 27 | 11 | 40.7 | [24.5, 59.3] | 47.5 | -23.0 | **INSUFFICIENT** |
| 50-55c | 30 | 18 | 60.0 | [42.3, 75.4] | 52.5 | -10.2 | **NEAR_FAIR** |
| 55-60c | 37 | 25 | 67.6 | [51.5, 80.4] | 57.5 | -6.0 | **NEAR_FAIR** |
| 60-65c | 23 | 15 | 65.2 | [44.9, 81.2] | 62.5 | -17.6 | **INSUFFICIENT** |
| 65-70c | 36 | 31 | 86.1 | [71.3, 93.9] | 67.5 | +3.8 | **TRADEABLE** |
| 70-75c | 18 | 14 | 77.8 | [54.8, 91.0] | 72.5 | -17.7 | **INSUFFICIENT** |
| 75-80c | 38 | 29 | 76.3 | [60.8, 87.0] | 77.5 | -16.7 | **NEAR_FAIR** |
| 80-85c | 49 | 47 | 95.9 | [86.3, 98.9] | 82.5 | +3.8 | **TRADEABLE** |
| 85-90c | 65 | 59 | 90.8 | [81.3, 95.7] | 87.5 | -6.2 | **NEAR_FAIR** |
| 90-95c | 167 | 157 | 94.0 | [89.3, 96.7] | 92.5 | -3.2 | **NEAR_FAIR** |
| 95-100c | 956 | 951 | 99.5 | [98.8, 99.8] | 97.5 | +1.3 | **NEAR_FAIR** |

### crypto_eth15m_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 956 | 5 | 0.5 | [0.2, 1.2] | 2.5 | -2.3 | **NEAR_FAIR** |
| 5-10c | 146 | 9 | 6.2 | [3.3, 11.3] | 7.5 | -4.2 | **NEAR_FAIR** |
| 10-15c | 86 | 7 | 8.1 | [4.0, 15.9] | 12.5 | -8.5 | **NEAR_FAIR** |
| 15-20c | 39 | 2 | 5.1 | [1.4, 16.9] | 17.5 | -16.1 | **NEAR_FAIR** |
| 20-25c | 43 | 9 | 20.9 | [11.4, 35.2] | 22.5 | -11.1 | **NEAR_FAIR** |
| 25-30c | 26 | 4 | 15.4 | [6.1, 33.5] | 27.5 | -21.4 | **INSUFFICIENT** |
| 30-35c | 33 | 5 | 15.2 | [6.7, 30.9] | 32.5 | -25.8 | **NEAR_FAIR** |
| 35-40c | 23 | 8 | 34.8 | [18.8, 55.1] | 37.5 | -18.7 | **INSUFFICIENT** |
| 40-45c | 36 | 11 | 30.6 | [18.0, 46.9] | 42.5 | -24.5 | **NEAR_FAIR** |
| 45-50c | 18 | 6 | 33.3 | [16.3, 56.3] | 47.5 | -31.2 | **INSUFFICIENT** |
| 50-55c | 37 | 21 | 56.8 | [40.9, 71.3] | 52.5 | -11.6 | **NEAR_FAIR** |
| 55-60c | 25 | 16 | 64.0 | [44.5, 79.8] | 57.5 | -13.0 | **INSUFFICIENT** |
| 60-65c | 21 | 17 | 81.0 | [60.0, 92.3] | 62.5 | -2.5 | **INSUFFICIENT** |
| 65-70c | 45 | 26 | 57.8 | [43.3, 71.0] | 67.5 | -24.2 | **NEAR_FAIR** |
| 70-75c | 24 | 16 | 66.7 | [46.7, 82.0] | 72.5 | -25.8 | **INSUFFICIENT** |
| 75-80c | 25 | 20 | 80.0 | [60.9, 91.1] | 77.5 | -16.6 | **INSUFFICIENT** |
| 80-85c | 60 | 54 | 90.0 | [79.9, 95.3] | 82.5 | -2.6 | **NEAR_FAIR** |
| 85-90c | 62 | 58 | 93.5 | [84.6, 97.5] | 87.5 | -2.9 | **NEAR_FAIR** |
| 90-95c | 157 | 150 | 95.5 | [91.1, 97.8] | 92.5 | -1.4 | **NEAR_FAIR** |
| 95-100c | 970 | 967 | 99.7 | [99.1, 99.9] | 97.5 | +1.6 | **NEAR_FAIR** |


## crypto_sol15m_midband — full breakdown
_Snapshots: 2831 total, 2793 in target 30-180s window. Resolved YES: 1445/2831 (51.0%)._

### crypto_sol15m_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 959 | 4 | 0.4 | [0.2, 1.1] | 2.5 | -2.3 | **NEAR_FAIR** |
| 5-10c | 122 | 5 | 4.1 | [1.8, 9.2] | 7.5 | -5.7 | **NEAR_FAIR** |
| 10-15c | 66 | 11 | 16.7 | [9.6, 27.4] | 12.5 | -2.9 | **NEAR_FAIR** |
| 15-20c | 46 | 8 | 17.4 | [9.1, 30.7] | 17.5 | -8.4 | **NEAR_FAIR** |
| 20-25c | 48 | 11 | 22.9 | [13.3, 36.5] | 22.5 | -9.2 | **NEAR_FAIR** |
| 25-30c | 38 | 15 | 39.5 | [25.6, 55.3] | 27.5 | -1.9 | **NEAR_FAIR** |
| 30-35c | 35 | 12 | 34.3 | [20.8, 50.8] | 32.5 | -11.7 | **NEAR_FAIR** |
| 35-40c | 21 | 6 | 28.6 | [13.8, 50.0] | 37.5 | -23.7 | **INSUFFICIENT** |
| 40-45c | 30 | 16 | 53.3 | [36.1, 69.8] | 42.5 | -6.4 | **NEAR_FAIR** |
| 45-50c | 35 | 20 | 57.1 | [40.9, 72.0] | 47.5 | -6.6 | **NEAR_FAIR** |
| 50-55c | 28 | 16 | 57.1 | [39.1, 73.5] | 52.5 | -13.4 | **INSUFFICIENT** |
| 55-60c | 33 | 18 | 54.5 | [38.0, 70.2] | 57.5 | -19.5 | **NEAR_FAIR** |
| 60-65c | 32 | 19 | 59.4 | [42.3, 74.5] | 62.5 | -20.2 | **NEAR_FAIR** |
| 65-70c | 39 | 26 | 66.7 | [51.0, 79.4] | 67.5 | -16.5 | **NEAR_FAIR** |
| 70-75c | 31 | 24 | 77.4 | [60.2, 88.6] | 72.5 | -12.3 | **NEAR_FAIR** |
| 75-80c | 46 | 36 | 78.3 | [64.4, 87.7] | 77.5 | -13.1 | **NEAR_FAIR** |
| 80-85c | 42 | 35 | 83.3 | [69.4, 91.7] | 82.5 | -13.1 | **NEAR_FAIR** |
| 85-90c | 59 | 53 | 89.8 | [79.5, 95.3] | 87.5 | -8.0 | **NEAR_FAIR** |
| 90-95c | 141 | 133 | 94.3 | [89.2, 97.1] | 92.5 | -3.3 | **NEAR_FAIR** |
| 95-100c | 980 | 977 | 99.7 | [99.1, 99.9] | 97.5 | +1.6 | **NEAR_FAIR** |

### crypto_sol15m_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 980 | 3 | 0.3 | [0.1, 0.9] | 2.5 | -2.4 | **NEAR_FAIR** |
| 5-10c | 120 | 6 | 5.0 | [2.3, 10.5] | 7.5 | -5.2 | **NEAR_FAIR** |
| 10-15c | 80 | 8 | 10.0 | [5.2, 18.5] | 12.5 | -7.3 | **NEAR_FAIR** |
| 15-20c | 35 | 6 | 17.1 | [8.1, 32.7] | 17.5 | -9.4 | **NEAR_FAIR** |
| 20-25c | 47 | 9 | 19.1 | [10.4, 32.5] | 22.5 | -12.1 | **NEAR_FAIR** |
| 25-30c | 41 | 9 | 22.0 | [12.0, 36.7] | 27.5 | -15.5 | **NEAR_FAIR** |
| 30-35c | 35 | 13 | 37.1 | [23.2, 53.7] | 32.5 | -9.3 | **NEAR_FAIR** |
| 35-40c | 32 | 13 | 40.6 | [25.5, 57.7] | 37.5 | -12.0 | **NEAR_FAIR** |
| 40-45c | 30 | 14 | 46.7 | [30.2, 63.9] | 42.5 | -12.3 | **NEAR_FAIR** |
| 45-50c | 26 | 9 | 34.6 | [19.4, 53.8] | 47.5 | -28.1 | **INSUFFICIENT** |
| 50-55c | 26 | 9 | 34.6 | [19.4, 53.8] | 52.5 | -33.1 | **INSUFFICIENT** |
| 55-60c | 44 | 24 | 54.5 | [40.1, 68.3] | 57.5 | -17.4 | **NEAR_FAIR** |
| 60-65c | 21 | 15 | 71.4 | [50.0, 86.2] | 62.5 | -12.5 | **INSUFFICIENT** |
| 65-70c | 43 | 27 | 62.8 | [47.9, 75.6] | 67.5 | -19.6 | **NEAR_FAIR** |
| 70-75c | 23 | 14 | 60.9 | [40.8, 77.8] | 72.5 | -31.7 | **INSUFFICIENT** |
| 75-80c | 40 | 28 | 70.0 | [54.6, 81.9] | 77.5 | -22.9 | **NEAR_FAIR** |
| 80-85c | 61 | 52 | 85.2 | [74.3, 92.0] | 82.5 | -8.2 | **NEAR_FAIR** |
| 85-90c | 60 | 51 | 85.0 | [73.9, 91.9] | 87.5 | -13.6 | **NEAR_FAIR** |
| 90-95c | 128 | 121 | 94.5 | [89.1, 97.3] | 92.5 | -3.4 | **NEAR_FAIR** |
| 95-100c | 959 | 955 | 99.6 | [98.9, 99.8] | 97.5 | +1.4 | **NEAR_FAIR** |


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
    "updated_at": "2026-05-06T22:14:41.342733Z",
    "source": "historical_backtest_2026-05-06",
    "note": "Bands derived from /historical/trades reconstruction of decision-time prices (close-90s anchor) over last 30 days of finalized markets. Wilson 95% lower bound must beat implied probability by 3pts to qualify."
  },
  "crypto_btcd_midband": {
    "yes_bands": [
      [
        0.2,
        0.25,
        0.35
      ]
    ],
    "no_bands": [],
    "updated_at": "2026-05-06T22:14:41.357748Z",
    "source": "historical_backtest_2026-05-06",
    "note": "Bands derived from /historical/trades reconstruction of decision-time prices (close-90s anchor) over last 30 days of finalized markets. Wilson 95% lower bound must beat implied probability by 3pts to qualify."
  },
  "crypto_eth15m_midband": {
    "yes_bands": [
      [
        0.65,
        0.7,
        0.71
      ],
      [
        0.8,
        0.85,
        0.86
      ]
    ],
    "no_bands": [],
    "updated_at": "2026-05-06T22:14:41.365454Z",
    "source": "historical_backtest_2026-05-06",
    "note": "Bands derived from /historical/trades reconstruction of decision-time prices (close-90s anchor) over last 30 days of finalized markets. Wilson 95% lower bound must beat implied probability by 3pts to qualify."
  },
  "crypto_sol15m_midband": {
    "yes_bands": [],
    "no_bands": [],
    "updated_at": "2026-05-06T22:14:41.373902Z",
    "source": "historical_backtest_2026-05-06",
    "note": "Bands derived from /historical/trades reconstruction of decision-time prices (close-90s anchor) over last 30 days of finalized markets. Wilson 95% lower bound must beat implied probability by 3pts to qualify."
  }
}
```