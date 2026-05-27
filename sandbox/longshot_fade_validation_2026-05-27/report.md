# Longshot-Fade Edge Validation — Report

**Generated:** 2026-05-27 23:58 UTC
**Data window:** 2026-02-26 → 2026-03-28 (Kalshi historical cutoff)
**Sample:** up to 200 random markets per series

## Universe

| Series | Markets in window | YES-wins | NO-wins |
|---|---:|---:|---:|
| `KXEPLGAME` | 948 | 316 | 632 |
| `KXNBAGAME` | 2,452 | 1,223 | 1,223 |
| `KXNFLGAME` | 666 | 329 | 329 |

**Sampled markets (trades pulled):** 417
**Trades in longshot band (NO 85-99¢):** 873,686

## Bucket Analysis — Aggregate (all sport series combined)

Implied NO probability = midpoint of bucket / 100. Actual NO win rate = fraction of trades in that bucket whose market settled NO.

| NO band | Implied | Actual | Edge | Trades | Distinct markets |
|---|---:|---:|---:|---:|---:|
| 85-89¢ | 87% | 90.3% | +3.3pp | 359,028 | 406 |
| 90-94¢ | 92% | 94.9% | +2.9pp | 285,159 | 393 |
| 95-99¢ | 97% | 98.3% | +1.3pp | 229,499 | 368 |

## Bucket Analysis — Per Series

### `KXEPLGAME`

| NO band | Actual | Edge vs implied | Trades | Markets |
|---|---:|---:|---:|---:|
| 85-89¢ | 78.6% | -8.4pp | 28,308 | 158 |
| 90-94¢ | 84.9% | -7.1pp | 28,941 | 163 |
| 95-99¢ | 94.7% | -2.3pp | 25,431 | 150 |

### `KXNBAGAME`

| NO band | Actual | Edge vs implied | Trades | Markets |
|---|---:|---:|---:|---:|
| 85-89¢ | 87.9% | +0.9pp | 116,040 | 126 |
| 90-94¢ | 95.0% | +3.0pp | 95,651 | 118 |
| 95-99¢ | 98.7% | +1.7pp | 96,948 | 111 |

### `KXNFLGAME`

| NO band | Actual | Edge vs implied | Trades | Markets |
|---|---:|---:|---:|---:|
| 85-89¢ | 93.1% | +6.1pp | 214,680 | 122 |
| 90-94¢ | 96.6% | +4.6pp | 160,567 | 112 |
| 95-99¢ | 98.9% | +1.9pp | 107,120 | 107 |

## Fill Opportunity (proxy)

Distinct markets per TRADE-day that printed ≥1 trade in the NO 85-99¢ band. This is a rough proxy for how many resting NO bids could potentially have been filled per day. Real fill rate depends on queue position (no orderbook history available via `/historical/*`).

**Sample scaling:** we pulled trades for 417 of 4,052 settled sport markets (10.3% sample). The 'scaled' figure projects the sample-rate up to the full universe — the realistic per-day count if the bot scanned every market.

- Days observed: **228**
- Mean markets/day in band (sample): 3.4
- **Mean markets/day in band (scaled to universe): 32.8**
- Median (sample): 3
- Min / Max (sample): 1 / 12

## Verdict

- Aggregate edge ≥ +1.5pp at 85-95¢: **PASS**
- Fill opportunity ≥ 3/day (scaled to full universe): **PASS** (32.8/day)
- ⚠️ NEGATIVE-edge series detected: **`KXEPLGAME`** — exclude from strategy whitelist

## **🟡 GREEN-WITH-CAVEATS — proceed to Phase 2 BUT whitelist only positive-edge series**

## Caveats

- Data window predates 2026-Q2 institutional MM activity by ~60 days (Kalshi `/historical/cutoff` is always 2 months stale). Recent edge could be tighter or wider.
- Fill-rate proxy is markets/day, NOT actual queue-aware fills. Real maker fills depend on bid-ask queue position which Kalshi doesn't expose in `/historical/*`.
- Sample = 200 random markets/series. Full universe is 4,066 markets; the sample is statistically representative but per-bucket counts will scale ~7x if you pull everything.