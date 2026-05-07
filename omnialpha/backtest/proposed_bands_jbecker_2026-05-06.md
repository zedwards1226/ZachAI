# OmniAlpha proposed-bands report (jbecker dataset)
_Generated: 2026-05-06T21:41:18_

## TL;DR

### crypto_btcd_midband
- **YES side**: TRADEABLE → 70-75c (forecast 81%), 80-95c (forecast 89%)
- **NO side**: TRADEABLE → 70-95c (forecast 83%)

### crypto_eth_hourly_midband
- **YES side**: no tradeable band — keep paused/off
- **NO side**: TRADEABLE → 40-45c (forecast 47%), 50-95c (forecast 62%)

### crypto_ethd_midband
- **YES side**: TRADEABLE → 65-95c (forecast 77%)
- **NO side**: TRADEABLE → 60-95c (forecast 74%)

---

## Methodology
Used the jbecker prediction-market-analysis dataset (largest public Kalshi trade history). For each finalized crypto market we found the trade closest to `close_time − 90s` (matches OmniAlpha's strategy entry window of 30-180s before close). Bucketed by 5¢ price ranges and evaluated YES + NO sides. A bucket is TRADEABLE only when **n ≥ 30** AND the Wilson 95% lower bound on win rate beats the implied probability (= mid-bucket cents) by **≥ 3 points** (covers fees + slippage).

## crypto_btcd_midband — full breakdown
_Snapshots: 43962 total, 13382 in 30-180s window. Resolved YES: 21702/43962._

### crypto_btcd_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 15977 | 36 | 0.2 | [0.2, 0.3] | 2.5 | -2.3 | **NEAR_FAIR** |
| 5-10c | 3505 | 26 | 0.7 | [0.5, 1.1] | 7.5 | -7.0 | **NEGATIVE** |
| 10-15c | 974 | 36 | 3.7 | [2.7, 5.1] | 12.5 | -9.8 | **NEGATIVE** |
| 15-20c | 482 | 42 | 8.7 | [6.5, 11.6] | 17.5 | -11.0 | **NEGATIVE** |
| 20-25c | 359 | 41 | 11.4 | [8.5, 15.1] | 22.5 | -14.0 | **NEGATIVE** |
| 25-30c | 266 | 24 | 9.0 | [6.1, 13.1] | 27.5 | -21.4 | **NEGATIVE** |
| 30-35c | 197 | 43 | 21.8 | [16.6, 28.1] | 32.5 | -15.9 | **NEGATIVE** |
| 35-40c | 157 | 47 | 29.9 | [23.3, 37.5] | 37.5 | -14.2 | **NEAR_FAIR** |
| 40-45c | 148 | 54 | 36.5 | [29.2, 44.5] | 42.5 | -13.3 | **NEAR_FAIR** |
| 45-50c | 140 | 64 | 45.7 | [37.7, 54.0] | 47.5 | -9.8 | **NEAR_FAIR** |
| 50-55c | 138 | 70 | 50.7 | [42.5, 58.9] | 52.5 | -10.0 | **NEAR_FAIR** |
| 55-60c | 150 | 88 | 58.7 | [50.7, 66.2] | 57.5 | -6.8 | **NEAR_FAIR** |
| 60-65c | 148 | 97 | 65.5 | [57.6, 72.7] | 62.5 | -4.9 | **NEAR_FAIR** |
| 65-70c | 189 | 145 | 76.7 | [70.2, 82.2] | 67.5 | +2.7 | **NEAR_FAIR** |
| 70-75c | 238 | 205 | 86.1 | [81.2, 90.0] | 72.5 | +8.7 | **TRADEABLE** |
| 75-80c | 315 | 264 | 83.8 | [79.3, 87.5] | 77.5 | +1.8 | **NEAR_FAIR** |
| 80-85c | 472 | 432 | 91.5 | [88.7, 93.7] | 82.5 | +6.2 | **TRADEABLE** |
| 85-90c | 845 | 812 | 96.1 | [94.6, 97.2] | 87.5 | +7.1 | **TRADEABLE** |
| 90-95c | 2438 | 2403 | 98.6 | [98.0, 99.0] | 92.5 | +5.5 | **TRADEABLE** |
| 95-100c | 16824 | 16773 | 99.7 | [99.6, 99.8] | 97.5 | +2.1 | **NEAR_FAIR** |

### crypto_btcd_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 15521 | 45 | 0.3 | [0.2, 0.4] | 2.5 | -2.3 | **NEAR_FAIR** |
| 5-10c | 3367 | 26 | 0.8 | [0.5, 1.1] | 7.5 | -7.0 | **NEGATIVE** |
| 10-15c | 1070 | 39 | 3.6 | [2.7, 4.9] | 12.5 | -9.8 | **NEGATIVE** |
| 15-20c | 524 | 37 | 7.1 | [5.2, 9.6] | 17.5 | -12.3 | **NEGATIVE** |
| 20-25c | 350 | 53 | 15.1 | [11.8, 19.3] | 22.5 | -10.7 | **NEGATIVE** |
| 25-30c | 235 | 34 | 14.5 | [10.5, 19.5] | 27.5 | -17.0 | **NEGATIVE** |
| 30-35c | 210 | 41 | 19.5 | [14.7, 25.4] | 32.5 | -17.8 | **NEGATIVE** |
| 35-40c | 151 | 49 | 32.5 | [25.5, 40.3] | 37.5 | -12.0 | **NEAR_FAIR** |
| 40-45c | 155 | 60 | 38.7 | [31.4, 46.6] | 42.5 | -11.1 | **NEAR_FAIR** |
| 45-50c | 128 | 63 | 49.2 | [40.7, 57.8] | 47.5 | -6.8 | **NEAR_FAIR** |
| 50-55c | 151 | 75 | 49.7 | [41.8, 57.6] | 52.5 | -10.7 | **NEAR_FAIR** |
| 55-60c | 143 | 88 | 61.5 | [53.4, 69.1] | 57.5 | -4.1 | **NEAR_FAIR** |
| 60-65c | 153 | 105 | 68.6 | [60.9, 75.4] | 62.5 | -1.6 | **NEAR_FAIR** |
| 65-70c | 187 | 137 | 73.3 | [66.5, 79.1] | 67.5 | -1.0 | **NEAR_FAIR** |
| 70-75c | 246 | 224 | 91.1 | [86.8, 94.0] | 72.5 | +14.3 | **TRADEABLE** |
| 75-80c | 320 | 278 | 86.9 | [82.7, 90.1] | 77.5 | +5.2 | **TRADEABLE** |
| 80-85c | 460 | 420 | 91.3 | [88.4, 93.5] | 82.5 | +5.9 | **TRADEABLE** |
| 85-90c | 780 | 747 | 95.8 | [94.1, 97.0] | 87.5 | +6.6 | **TRADEABLE** |
| 90-95c | 2512 | 2481 | 98.8 | [98.3, 99.1] | 92.5 | +5.8 | **TRADEABLE** |
| 95-100c | 17299 | 17258 | 99.8 | [99.7, 99.8] | 97.5 | +2.2 | **NEAR_FAIR** |


## crypto_eth_hourly_midband — full breakdown
_Snapshots: 14600 total, 3108 in 30-180s window. Resolved YES: 4211/14600._

### crypto_eth_hourly_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 2293 | 39 | 1.7 | [1.2, 2.3] | 2.5 | -1.3 | **NEAR_FAIR** |
| 5-10c | 2129 | 30 | 1.4 | [1.0, 2.0] | 7.5 | -6.5 | **NEGATIVE** |
| 10-15c | 1572 | 46 | 2.9 | [2.2, 3.9] | 12.5 | -10.3 | **NEGATIVE** |
| 15-20c | 1094 | 47 | 4.3 | [3.2, 5.7] | 17.5 | -14.3 | **NEGATIVE** |
| 20-25c | 872 | 48 | 5.5 | [4.2, 7.2] | 22.5 | -18.3 | **NEGATIVE** |
| 25-30c | 645 | 68 | 10.5 | [8.4, 13.2] | 27.5 | -19.1 | **NEGATIVE** |
| 30-35c | 521 | 73 | 14.0 | [11.3, 17.3] | 32.5 | -21.2 | **NEGATIVE** |
| 35-40c | 390 | 82 | 21.0 | [17.3, 25.3] | 37.5 | -20.2 | **NEGATIVE** |
| 40-45c | 335 | 80 | 23.9 | [19.6, 28.7] | 42.5 | -22.9 | **NEGATIVE** |
| 45-50c | 258 | 89 | 34.5 | [29.0, 40.5] | 47.5 | -18.5 | **NEGATIVE** |
| 50-55c | 332 | 146 | 44.0 | [38.7, 49.4] | 52.5 | -13.8 | **NEGATIVE** |
| 55-60c | 296 | 135 | 45.6 | [40.0, 51.3] | 57.5 | -17.5 | **NEGATIVE** |
| 60-65c | 251 | 152 | 60.6 | [54.4, 66.4] | 62.5 | -8.1 | **NEAR_FAIR** |
| 65-70c | 287 | 180 | 62.7 | [57.0, 68.1] | 67.5 | -10.5 | **NEAR_FAIR** |
| 70-75c | 289 | 218 | 75.4 | [70.2, 80.0] | 72.5 | -2.3 | **NEAR_FAIR** |
| 75-80c | 297 | 236 | 79.5 | [74.5, 83.7] | 77.5 | -3.0 | **NEAR_FAIR** |
| 80-85c | 306 | 262 | 85.6 | [81.2, 89.1] | 82.5 | -1.3 | **NEAR_FAIR** |
| 85-90c | 436 | 385 | 88.3 | [84.9, 91.0] | 87.5 | -2.6 | **NEAR_FAIR** |
| 90-95c | 525 | 497 | 94.7 | [92.4, 96.3] | 92.5 | -0.1 | **NEAR_FAIR** |
| 95-100c | 1472 | 1398 | 95.0 | [93.7, 96.0] | 97.5 | -3.8 | **NEAR_FAIR** |

### crypto_eth_hourly_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 1312 | 69 | 5.3 | [4.2, 6.6] | 2.5 | +1.7 | **NEAR_FAIR** |
| 5-10c | 542 | 22 | 4.1 | [2.7, 6.1] | 7.5 | -4.8 | **NEAR_FAIR** |
| 10-15c | 491 | 52 | 10.6 | [8.2, 13.6] | 12.5 | -4.3 | **NEAR_FAIR** |
| 15-20c | 307 | 36 | 11.7 | [8.6, 15.8] | 17.5 | -8.9 | **NEAR_FAIR** |
| 20-25c | 325 | 67 | 20.6 | [16.6, 25.3] | 22.5 | -5.9 | **NEAR_FAIR** |
| 25-30c | 267 | 61 | 22.8 | [18.2, 28.2] | 27.5 | -9.3 | **NEAR_FAIR** |
| 30-35c | 316 | 103 | 32.6 | [27.7, 37.9] | 32.5 | -4.8 | **NEAR_FAIR** |
| 35-40c | 224 | 88 | 39.3 | [33.1, 45.8] | 37.5 | -4.4 | **NEAR_FAIR** |
| 40-45c | 313 | 165 | 52.7 | [47.2, 58.2] | 42.5 | +4.7 | **TRADEABLE** |
| 45-50c | 296 | 153 | 51.7 | [46.0, 57.3] | 47.5 | -1.5 | **NEAR_FAIR** |
| 50-55c | 312 | 210 | 67.3 | [61.9, 72.3] | 52.5 | +9.4 | **TRADEABLE** |
| 55-60c | 269 | 188 | 69.9 | [64.2, 75.1] | 57.5 | +6.7 | **TRADEABLE** |
| 60-65c | 407 | 327 | 80.3 | [76.2, 83.9] | 62.5 | +13.7 | **TRADEABLE** |
| 65-70c | 461 | 386 | 83.7 | [80.1, 86.8] | 67.5 | +12.6 | **TRADEABLE** |
| 70-75c | 623 | 564 | 90.5 | [88.0, 92.6] | 72.5 | +15.5 | **TRADEABLE** |
| 75-80c | 775 | 714 | 92.1 | [90.0, 93.8] | 77.5 | +12.5 | **TRADEABLE** |
| 80-85c | 1082 | 1034 | 95.6 | [94.2, 96.6] | 82.5 | +11.7 | **TRADEABLE** |
| 85-90c | 1481 | 1428 | 96.4 | [95.3, 97.3] | 87.5 | +7.8 | **TRADEABLE** |
| 90-95c | 1992 | 1967 | 98.7 | [98.2, 99.1] | 92.5 | +5.7 | **TRADEABLE** |
| 95-100c | 2805 | 2755 | 98.2 | [97.7, 98.6] | 97.5 | +0.2 | **NEAR_FAIR** |


## crypto_ethd_midband — full breakdown
_Snapshots: 17803 total, 3783 in 30-180s window. Resolved YES: 8544/17803._

### crypto_ethd_midband BUY-YES

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 3615 | 44 | 1.2 | [0.9, 1.6] | 2.5 | -1.6 | **NEAR_FAIR** |
| 5-10c | 2128 | 15 | 0.7 | [0.4, 1.2] | 7.5 | -7.1 | **NEGATIVE** |
| 10-15c | 1180 | 29 | 2.5 | [1.7, 3.5] | 12.5 | -10.8 | **NEGATIVE** |
| 15-20c | 612 | 17 | 2.8 | [1.7, 4.4] | 17.5 | -15.8 | **NEGATIVE** |
| 20-25c | 458 | 34 | 7.4 | [5.4, 10.2] | 22.5 | -17.1 | **NEGATIVE** |
| 25-30c | 322 | 10 | 3.1 | [1.7, 5.6] | 27.5 | -25.8 | **NEGATIVE** |
| 30-35c | 286 | 47 | 16.4 | [12.6, 21.2] | 32.5 | -19.9 | **NEGATIVE** |
| 35-40c | 156 | 27 | 17.3 | [12.2, 24.0] | 37.5 | -25.3 | **NEGATIVE** |
| 40-45c | 190 | 62 | 32.6 | [26.4, 39.6] | 42.5 | -16.1 | **NEAR_FAIR** |
| 45-50c | 183 | 65 | 35.5 | [28.9, 42.7] | 47.5 | -18.6 | **NEGATIVE** |
| 50-55c | 228 | 123 | 53.9 | [47.5, 60.3] | 52.5 | -5.0 | **NEAR_FAIR** |
| 55-60c | 159 | 94 | 59.1 | [51.4, 66.5] | 57.5 | -6.1 | **NEAR_FAIR** |
| 60-65c | 185 | 133 | 71.9 | [65.0, 77.9] | 62.5 | +2.5 | **NEAR_FAIR** |
| 65-70c | 202 | 167 | 82.7 | [76.9, 87.3] | 67.5 | +9.4 | **TRADEABLE** |
| 70-75c | 303 | 268 | 88.4 | [84.4, 91.6] | 72.5 | +11.9 | **TRADEABLE** |
| 75-80c | 365 | 327 | 89.6 | [86.0, 92.3] | 77.5 | +8.5 | **TRADEABLE** |
| 80-85c | 553 | 520 | 94.0 | [91.7, 95.7] | 82.5 | +9.2 | **TRADEABLE** |
| 85-90c | 876 | 839 | 95.8 | [94.2, 96.9] | 87.5 | +6.7 | **TRADEABLE** |
| 90-95c | 1648 | 1622 | 98.4 | [97.7, 98.9] | 92.5 | +5.2 | **TRADEABLE** |
| 95-100c | 4154 | 4101 | 98.7 | [98.3, 99.0] | 97.5 | +0.8 | **NEAR_FAIR** |

### crypto_ethd_midband BUY-NO

| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |
|---|---|---|---|---|---|---|---|
| 0-5c | 3542 | 46 | 1.3 | [1.0, 1.7] | 2.5 | -1.5 | **NEAR_FAIR** |
| 5-10c | 1896 | 20 | 1.1 | [0.7, 1.6] | 7.5 | -6.8 | **NEGATIVE** |
| 10-15c | 1033 | 37 | 3.6 | [2.6, 4.9] | 12.5 | -9.9 | **NEGATIVE** |
| 15-20c | 602 | 31 | 5.1 | [3.7, 7.2] | 17.5 | -13.8 | **NEGATIVE** |
| 20-25c | 432 | 44 | 10.2 | [7.7, 13.4] | 22.5 | -14.8 | **NEGATIVE** |
| 25-30c | 278 | 27 | 9.7 | [6.8, 13.8] | 27.5 | -20.7 | **NEGATIVE** |
| 30-35c | 284 | 44 | 15.5 | [11.7, 20.2] | 32.5 | -20.8 | **NEGATIVE** |
| 35-40c | 160 | 37 | 23.1 | [17.3, 30.2] | 37.5 | -20.2 | **NEGATIVE** |
| 40-45c | 178 | 75 | 42.1 | [35.1, 49.5] | 42.5 | -7.4 | **NEAR_FAIR** |
| 45-50c | 160 | 58 | 36.2 | [29.2, 43.9] | 47.5 | -18.3 | **NEGATIVE** |
| 50-55c | 245 | 149 | 60.8 | [54.6, 66.7] | 52.5 | +2.1 | **NEAR_FAIR** |
| 55-60c | 155 | 96 | 61.9 | [54.1, 69.2] | 57.5 | -3.4 | **NEAR_FAIR** |
| 60-65c | 200 | 160 | 80.0 | [73.9, 85.0] | 62.5 | +11.4 | **TRADEABLE** |
| 65-70c | 214 | 173 | 80.8 | [75.0, 85.6] | 67.5 | +7.5 | **TRADEABLE** |
| 70-75c | 343 | 324 | 94.5 | [91.5, 96.4] | 72.5 | +19.0 | **TRADEABLE** |
| 75-80c | 421 | 390 | 92.6 | [89.7, 94.8] | 77.5 | +12.2 | **TRADEABLE** |
| 80-85c | 537 | 518 | 96.5 | [94.5, 97.7] | 82.5 | +12.0 | **TRADEABLE** |
| 85-90c | 983 | 964 | 98.1 | [97.0, 98.8] | 87.5 | +9.5 | **TRADEABLE** |
| 90-95c | 1826 | 1799 | 98.5 | [97.9, 99.0] | 92.5 | +5.4 | **TRADEABLE** |
| 95-100c | 4314 | 4267 | 98.9 | [98.6, 99.2] | 97.5 | +1.1 | **NEAR_FAIR** |


## Recommended JSON for strategy_bands.json

```json
{
  "crypto_ethd_midband": {
    "yes_bands": [
      [
        0.65,
        0.95,
        0.77
      ]
    ],
    "no_bands": [
      [
        0.6,
        0.95,
        0.74
      ]
    ],
    "updated_at": "2026-05-06T21:41:18.114135Z",
    "source": "jbecker_dataset_backtest_2026-05-06",
    "note": "Bands derived from jbecker prediction-market-analysis dataset (largest public Kalshi trade history). Wilson 95% lower bound must beat implied price by 3 points to qualify."
  },
  "crypto_btcd_midband": {
    "yes_bands": [
      [
        0.7,
        0.75,
        0.81
      ],
      [
        0.8,
        0.95,
        0.89
      ]
    ],
    "no_bands": [
      [
        0.7,
        0.95,
        0.83
      ]
    ],
    "updated_at": "2026-05-06T21:41:18.114309Z",
    "source": "jbecker_dataset_backtest_2026-05-06",
    "note": "Bands derived from jbecker prediction-market-analysis dataset (largest public Kalshi trade history). Wilson 95% lower bound must beat implied price by 3 points to qualify."
  },
  "crypto_eth_hourly_midband": {
    "yes_bands": [],
    "no_bands": [
      [
        0.4,
        0.45,
        0.47
      ],
      [
        0.5,
        0.95,
        0.62
      ]
    ],
    "updated_at": "2026-05-06T21:41:18.114326Z",
    "source": "jbecker_dataset_backtest_2026-05-06",
    "note": "Bands derived from jbecker prediction-market-analysis dataset (largest public Kalshi trade history). Wilson 95% lower bound must beat implied price by 3 points to qualify."
  }
}
```