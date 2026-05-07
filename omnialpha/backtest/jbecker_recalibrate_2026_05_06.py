"""Recalibrate ALL OmniAlpha crypto strategies using the jbecker dataset.

Reads parquet files from C:/ZachAI/reference/jbecker-data/data/kalshi/{markets,trades}/
and produces per-strategy proposed bands using the same Wilson 95%
methodology as propose_bands_2026_05_06.py.

Covers all 5 OmniAlpha crypto strategies:
  - crypto_btc15m_midband (KXBTC15M)
  - crypto_btcd_midband   (KXBTCD)
  - crypto_eth15m_midband (KXETH15M)
  - crypto_ethd_midband   (KXETHD)
  - crypto_sol15m_midband (KXSOL15M)
  - crypto_eth_hourly_midband (KXETH)  -- hourly variant if present

Per-bucket verdict:
  TRADEABLE  -- n>=30 AND Wilson_lo > implied + 3pts
  NEAR_FAIR  -- n>=30 AND CI overlaps fair value
  NEGATIVE   -- n>=30 AND Wilson_hi < implied - 3pts
  INSUFFICIENT -- n<30

Approach:
  1. Load markets parquet, filter to crypto series + finalized + has result
  2. For each crypto market: pull all its trades from trades parquet
  3. Find trade closest to close_time - 90s (decision-time anchor)
  4. Bucket by yes_price, compute Wilson, classify
  5. Output: proposed_bands_jbecker_2026-05-06.{md,json}

Run: python C:/ZachAI/omnialpha/backtest/jbecker_recalibrate_2026_05_06.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    import polars as pl
except ImportError:
    print("Installing polars...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "polars"])
    import polars as pl

DATA_ROOT = Path(r"C:\ZachAI\reference\jbecker-data\data\kalshi")
MARKETS_GLOB = str(DATA_ROOT / "markets" / "**" / "*.parquet")
TRADES_GLOB = str(DATA_ROOT / "trades" / "**" / "*.parquet")
OUT_DIR = Path(__file__).parent
REPORT_PATH = OUT_DIR / "proposed_bands_jbecker_2026-05-06.md"
BANDS_JSON_PATH = OUT_DIR / "proposed_bands_jbecker_2026-05-06.json"

# Series prefix → strategy name in OmniAlpha config
STRATEGY_MAP = {
    "KXBTC15M":  "crypto_btc15m_midband",
    "KXBTCD":    "crypto_btcd_midband",
    "KXETH15M":  "crypto_eth15m_midband",
    "KXETHD":    "crypto_ethd_midband",
    "KXSOL15M":  "crypto_sol15m_midband",
    "KXETH":     "crypto_eth_hourly_midband",  # only matched if KXETH15M doesn't already cover it
}

# Order checked: longer prefixes first so KXBTC15M wins over KXBTC (etc.)
PREFIX_ORDER = sorted(STRATEGY_MAP.keys(), key=lambda x: -len(x))

TARGET_OFFSET_S = -90
WINDOW_LO_S = -180
WINDOW_HI_S = -30
BUCKET_WIDTH_CENTS = 5
MIN_N_FOR_VERDICT = 30
EDGE_MARGIN_CENTS = 3
WILSON_Z = 1.96


def classify_ticker(ticker: str) -> str | None:
    """Return strategy name for a Kalshi ticker, or None if not a crypto market we trade."""
    for prefix in PREFIX_ORDER:
        if ticker.startswith(prefix + "-") or ticker.startswith(prefix):
            return STRATEGY_MAP[prefix]
    return None


def wilson(wins: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z = WILSON_Z
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (max(0.0, (centre - margin) / denom),
            min(1.0, (centre + margin) / denom))


def load_crypto_markets() -> pl.DataFrame:
    """Return finalized crypto markets with strategy classification."""
    print(f"  scanning markets at {MARKETS_GLOB}", flush=True)
    df = pl.scan_parquet(MARKETS_GLOB).filter(
        pl.col("status") == "finalized"
    ).filter(
        pl.col("result").is_in(["yes", "no"])
    ).select([
        "ticker", "result", "close_time", "volume",
    ]).collect()
    print(f"  {df.height} finalized markets", flush=True)

    # Classify
    df = df.with_columns([
        pl.col("ticker").map_elements(classify_ticker, return_dtype=pl.Utf8).alias("strategy"),
    ]).filter(pl.col("strategy").is_not_null())
    print(f"  {df.height} crypto markets after classification", flush=True)
    print(df.group_by("strategy").len().sort("len", descending=True), flush=True)
    return df


def find_decision_snapshots(crypto_markets: pl.DataFrame) -> pl.DataFrame:
    """For each crypto market, find the trade closest to close_time-90s.

    Single pass over the trades parquet using join+window approach. Faster
    than per-market trade lookups on large files.
    """
    crypto_tickers = crypto_markets["ticker"].to_list()
    print(f"  scanning trades, filtering to {len(crypto_tickers)} crypto tickers", flush=True)

    # Filter trades to only crypto markets, compute offset from close
    trades = (
        pl.scan_parquet(TRADES_GLOB)
        .filter(pl.col("ticker").is_in(crypto_tickers))
        .select(["ticker", "yes_price", "created_time"])
        .collect()
    )
    print(f"  {trades.height} crypto trades loaded", flush=True)

    # Join on ticker to attach close_time, compute offset_s
    joined = trades.join(
        crypto_markets.select(["ticker", "close_time", "result", "strategy"]),
        on="ticker", how="inner",
    ).with_columns([
        ((pl.col("created_time") - pl.col("close_time")).dt.total_seconds()).alias("offset_s"),
    ])

    # Pick trade closest to TARGET_OFFSET_S per ticker
    joined = joined.with_columns([
        (pl.col("offset_s") - TARGET_OFFSET_S).abs().alias("dist_to_target"),
    ])
    closest = (
        joined.sort(["ticker", "dist_to_target"])
        .group_by("ticker")
        .head(1)
        .with_columns([
            pl.col("offset_s").is_between(WINDOW_LO_S, WINDOW_HI_S).alias("is_in_window"),
        ])
    )
    print(f"  {closest.height} markets have at least one matchable trade", flush=True)
    return closest


def bucket_by_strategy(snapshots: pl.DataFrame) -> dict:
    """Per-strategy: yes-side and no-side bucket analysis."""
    out = {}
    for strategy in snapshots["strategy"].unique().to_list():
        sub = snapshots.filter(pl.col("strategy") == strategy)
        out[strategy] = {
            "n_snapshots": sub.height,
            "n_in_window": int(sub["is_in_window"].sum()),
            "yes_won": int((sub["result"] == "yes").sum()),
            "yes_buckets": _bucket_side(sub, side="yes"),
            "no_buckets": _bucket_side(sub, side="no"),
        }
    return out


def _bucket_side(sub: pl.DataFrame, side: str) -> list[dict]:
    """Bucket the given side. yes_price/(100-yes_price) is implied prob of side winning."""
    rows = sub.to_dicts()
    by_bucket = defaultdict(list)
    for r in rows:
        if side == "yes":
            price = r["yes_price"]
            won = (r["result"] == "yes")
        else:
            price = 100 - r["yes_price"]
            won = (r["result"] == "no")
        if price < 1 or price > 99:
            continue
        bucket_low = (price // BUCKET_WIDTH_CENTS) * BUCKET_WIDTH_CENTS
        by_bucket[bucket_low].append(won)

    out = []
    for bucket_low in sorted(by_bucket.keys()):
        outcomes = by_bucket[bucket_low]
        n = len(outcomes)
        wins = sum(outcomes)
        wr = wins / n if n else 0
        lo, hi = wilson(wins, n)
        implied_pct = bucket_low + BUCKET_WIDTH_CENTS / 2  # mid-bucket cents
        edge_lo = (lo * 100) - implied_pct  # in cent-points
        edge_hi = (hi * 100) - implied_pct
        if n < MIN_N_FOR_VERDICT:
            verdict = "INSUFFICIENT"
        elif edge_lo >= EDGE_MARGIN_CENTS:
            verdict = "TRADEABLE"
        elif edge_hi <= -EDGE_MARGIN_CENTS:
            verdict = "NEGATIVE"
        else:
            verdict = "NEAR_FAIR"
        out.append({
            "bucket_low": int(bucket_low),
            "bucket_high": int(bucket_low + BUCKET_WIDTH_CENTS),
            "n": n,
            "wins": int(wins),
            "wr_pct": round(wr * 100, 1),
            "wilson_lo_pct": round(lo * 100, 1),
            "wilson_hi_pct": round(hi * 100, 1),
            "implied_pct": implied_pct,
            "edge_lo_pts": round(edge_lo, 1),
            "edge_hi_pts": round(edge_hi, 1),
            "verdict": verdict,
        })
    return out


def merge_tradeable(buckets: list[dict]) -> list[list]:
    """Merge consecutive TRADEABLE buckets into bands.

    Returns [(low_decimal, high_decimal, conservative_forecast)] for the JSON shape.
    """
    bands = []
    cur_lo = cur_hi = None
    cur_min_wilson = 100.0
    for b in buckets:
        if b["verdict"] == "TRADEABLE":
            if cur_lo is None:
                cur_lo = b["bucket_low"]
            cur_hi = b["bucket_high"]
            cur_min_wilson = min(cur_min_wilson, b["wilson_lo_pct"])
        else:
            if cur_lo is not None:
                bands.append([round(cur_lo / 100, 2),
                              round(cur_hi / 100, 2),
                              round(cur_min_wilson / 100, 2)])
                cur_lo = cur_hi = None
                cur_min_wilson = 100.0
    if cur_lo is not None:
        bands.append([round(cur_lo / 100, 2),
                      round(cur_hi / 100, 2),
                      round(cur_min_wilson / 100, 2)])
    return bands


def render_report(by_strategy: dict, bands_json: dict) -> str:
    L = []
    L.append("# OmniAlpha proposed-bands report (jbecker dataset)")
    L.append(f"_Generated: {datetime.now().isoformat(timespec='seconds')}_")
    L.append("")
    L.append("## TL;DR")
    L.append("")
    for strategy in sorted(by_strategy.keys()):
        L.append(f"### {strategy}")
        for side in ("yes", "no"):
            recs = bands_json.get(strategy, {}).get(f"{side}_bands", [])
            if not recs:
                L.append(f"- **{side.upper()} side**: no tradeable band — keep paused/off")
            else:
                pretty = ", ".join(f"{int(b[0]*100)}-{int(b[1]*100)}c (forecast {int(b[2]*100)}%)" for b in recs)
                L.append(f"- **{side.upper()} side**: TRADEABLE → {pretty}")
        L.append("")
    L.append("---")
    L.append("")
    L.append("## Methodology")
    L.append(
        "Used the jbecker prediction-market-analysis dataset (largest public Kalshi"
        " trade history). For each finalized crypto market we found the trade"
        " closest to `close_time − 90s` (matches OmniAlpha's strategy entry"
        " window of 30-180s before close). Bucketed by 5¢ price ranges and"
        " evaluated YES + NO sides. A bucket is TRADEABLE only when **n ≥ 30**"
        " AND the Wilson 95% lower bound on win rate beats the implied"
        " probability (= mid-bucket cents) by **≥ 3 points** (covers fees + slippage)."
    )
    L.append("")
    for strategy in sorted(by_strategy.keys()):
        s = by_strategy[strategy]
        L.append(f"## {strategy} — full breakdown")
        L.append(f"_Snapshots: {s['n_snapshots']} total, {s['n_in_window']} in 30-180s window. "
                 f"Resolved YES: {s['yes_won']}/{s['n_snapshots']}._")
        L.append("")
        for side in ("yes", "no"):
            buckets = s[f"{side}_buckets"]
            L.append(f"### {strategy} BUY-{side.upper()}")
            L.append("")
            L.append("| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |")
            L.append("|---|---|---|---|---|---|---|---|")
            for b in buckets:
                band = f"{b['bucket_low']}-{b['bucket_high']}c"
                L.append(
                    f"| {band} | {b['n']} | {b['wins']} | {b['wr_pct']} | "
                    f"[{b['wilson_lo_pct']}, {b['wilson_hi_pct']}] | "
                    f"{b['implied_pct']} | {b['edge_lo_pts']:+} | **{b['verdict']}** |"
                )
            L.append("")
        L.append("")
    L.append("## Recommended JSON for strategy_bands.json")
    L.append("")
    L.append("```json")
    L.append(json.dumps(bands_json, indent=2))
    L.append("```")
    return "\n".join(L)


def main():
    print("=== load crypto markets ===", flush=True)
    crypto = load_crypto_markets()
    if crypto.height == 0:
        print("ERROR: no crypto markets found in dataset", flush=True)
        return

    print()
    print("=== find decision-time snapshots (close-90s) ===", flush=True)
    snaps = find_decision_snapshots(crypto)

    print()
    print("=== bucket per strategy ===", flush=True)
    by_strategy = bucket_by_strategy(snaps)

    bands_json = {}
    for strategy, summary in by_strategy.items():
        bands_json[strategy] = {
            "yes_bands": merge_tradeable(summary["yes_buckets"]),
            "no_bands": merge_tradeable(summary["no_buckets"]),
            "updated_at": datetime.now().isoformat() + "Z",
            "source": "jbecker_dataset_backtest_2026-05-06",
            "note": (
                "Bands derived from jbecker prediction-market-analysis dataset"
                " (largest public Kalshi trade history). Wilson 95% lower bound"
                " must beat implied price by 3 points to qualify."
            ),
        }
        print(f"  {strategy}: yes_bands={len(bands_json[strategy]['yes_bands'])}, "
              f"no_bands={len(bands_json[strategy]['no_bands'])}", flush=True)

    print()
    report = render_report(by_strategy, bands_json)
    REPORT_PATH.write_text(report, encoding="utf-8")
    BANDS_JSON_PATH.write_text(json.dumps(bands_json, indent=2), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {BANDS_JSON_PATH}")


if __name__ == "__main__":
    main()
