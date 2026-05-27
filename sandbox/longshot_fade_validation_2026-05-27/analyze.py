"""Analyze the longshot-fade NO edge from the pulled trades.

For each trade that printed in the longshot band (YES 1-15¢ = NO 85-99¢),
join with the market's eventual result. Bucket by NO price and compute
actual NO-win rate vs implied. Becker 2026 claim: NO outperforms YES at
80 of 99 price levels. We're testing the deep-NO band on Zach's actual
addressable sport universe.

Decision gate (from the main plan):
  GREEN if:
    - Measured NO-WR at 85-95¢ ≥ implied + 1.5pp
    - ≥ 3 markets/day in band across all series (fill-opportunity proxy)
  RED if either fails.

Output: report.md with per-bucket tables and the verdict.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "db" / "markets.db"
REPORT_PATH = HERE / "report.md"


# Buckets: (low, high) inclusive on both ends, NO price in cents.
BUCKETS = [
    (85, 89),
    (90, 94),
    (95, 99),
]

# Convenience: edge threshold for green-light.
EDGE_THRESHOLD_PP = 1.5  # percentage points

# Fill-opportunity proxy: at least N distinct markets/day with at least
# one trade in the band, across the whole sport universe.
MIN_MARKETS_PER_DAY_IN_BAND = 3


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def _bucket_for(no_cents: int) -> tuple[int, int] | None:
    for low, high in BUCKETS:
        if low <= no_cents <= high:
            return (low, high)
    return None


def _safe_pct(num: int, den: int) -> float:
    return 100.0 * num / den if den else 0.0


def analyze_bucket_stats(conn: sqlite3.Connection) -> dict:
    """For each (series, bucket): count trades, distinct markets, NO wins."""
    rows = conn.execute(
        "SELECT series_ticker, no_price_cents, market_result, market_ticker "
        "FROM trades WHERE no_price_cents BETWEEN 85 AND 99"
    ).fetchall()

    by_series_bucket: dict[tuple[str, tuple[int, int]], dict] = defaultdict(
        lambda: {"trades": 0, "no_wins": 0, "yes_wins": 0, "markets": set()}
    )
    by_bucket: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"trades": 0, "no_wins": 0, "yes_wins": 0, "markets": set()}
    )

    for r in rows:
        bucket = _bucket_for(r["no_price_cents"])
        if bucket is None:
            continue
        is_no_win = r["market_result"] == "no"
        for d in (by_series_bucket[(r["series_ticker"], bucket)],
                  by_bucket[bucket]):
            d["trades"] += 1
            if is_no_win:
                d["no_wins"] += 1
            else:
                d["yes_wins"] += 1
            d["markets"].add(r["market_ticker"])

    return {"by_series_bucket": by_series_bucket, "by_bucket": by_bucket}


def _bucket_midpoint(bucket: tuple[int, int]) -> float:
    return (bucket[0] + bucket[1]) / 2.0


def fill_opportunity_per_day(conn: sqlite3.Connection) -> dict:
    """Distinct markets/day with ≥1 trade in the band, based on TRADE
    created_time. Scales the result up to the full universe by the
    inverse sampling fraction (we only pulled trades for 600 of 4,066
    markets so divide by that ratio to estimate live conditions).

    `created_time` on trades is the actual day retail was betting, not the
    market's close date — that's the fill-opportunity timeframe we care about.
    """
    # Per-day distinct markets with band activity in the SAMPLE.
    rows = conn.execute(
        "SELECT substr(created_time, 1, 10) d, "
        "COUNT(DISTINCT market_ticker) n "
        "FROM trades WHERE no_price_cents BETWEEN 85 AND 99 "
        "GROUP BY d ORDER BY d"
    ).fetchall()
    if not rows:
        return {"days": 0, "mean_per_day_sample": 0.0,
                "mean_per_day_scaled": 0.0, "sample_fraction": 1.0,
                "median_per_day": 0, "min_per_day": 0, "max_per_day": 0}

    counts = [r["n"] for r in rows]
    # Scaling: # markets we sampled vs total settled markets in 4 series.
    sampled = conn.execute(
        "SELECT COUNT(DISTINCT market_ticker) FROM trades"
    ).fetchone()[0]
    universe = conn.execute(
        "SELECT COUNT(*) FROM markets WHERE result IN ('yes','no') "
        "AND (series_ticker LIKE 'KXNBA%' OR series_ticker LIKE 'KXNFL%' "
        "OR series_ticker LIKE 'KXEPL%' OR series_ticker LIKE 'KXUFC%')"
    ).fetchone()[0]
    sample_fraction = sampled / universe if universe else 1.0

    sorted_vals = sorted(counts)
    mean_sample = sum(counts) / len(counts)
    return {
        "days": len(counts),
        "mean_per_day_sample": mean_sample,
        "mean_per_day_scaled": mean_sample / sample_fraction if sample_fraction else 0.0,
        "sample_fraction": sample_fraction,
        "sampled_markets": sampled,
        "universe_markets": universe,
        "median_per_day": sorted_vals[len(sorted_vals) // 2],
        "min_per_day": min(counts),
        "max_per_day": max(counts),
    }


def universe_summary(conn: sqlite3.Connection) -> dict:
    by_series = conn.execute(
        "SELECT series_ticker, COUNT(*) n, "
        "SUM(CASE WHEN result='yes' THEN 1 ELSE 0 END) yes_wins, "
        "SUM(CASE WHEN result='no' THEN 1 ELSE 0 END) no_wins "
        "FROM markets WHERE series_ticker IS NOT NULL "
        "GROUP BY series_ticker"
    ).fetchall()
    trades_total = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE no_price_cents BETWEEN 85 AND 99"
    ).fetchone()[0]
    sampled_markets = conn.execute(
        "SELECT COUNT(DISTINCT market_ticker) FROM trades"
    ).fetchone()[0]
    return {
        "by_series": [dict(r) for r in by_series],
        "trades_in_band": trades_total,
        "sampled_markets": sampled_markets,
    }


def build_report(stats: dict, fills: dict, summary: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append("# Longshot-Fade Edge Validation — Report")
    lines.append("")
    lines.append(f"**Generated:** {now}")
    lines.append("**Data window:** 2026-02-26 → 2026-03-28 (Kalshi historical cutoff)")
    lines.append("**Sample:** up to 200 random markets per series")
    lines.append("")
    lines.append("## Universe")
    lines.append("")
    lines.append("| Series | Markets in window | YES-wins | NO-wins |")
    lines.append("|---|---:|---:|---:|")
    for r in summary["by_series"]:
        lines.append(f"| `{r['series_ticker']}` | {r['n']:,} | "
                     f"{r['yes_wins']:,} | {r['no_wins']:,} |")
    lines.append(f"\n**Sampled markets (trades pulled):** {summary['sampled_markets']:,}")
    lines.append(f"**Trades in longshot band (NO 85-99¢):** {summary['trades_in_band']:,}")
    lines.append("")
    lines.append("## Bucket Analysis — Aggregate (all sport series combined)")
    lines.append("")
    lines.append("Implied NO probability = midpoint of bucket / 100. "
                 "Actual NO win rate = fraction of trades in that bucket "
                 "whose market settled NO.")
    lines.append("")
    lines.append("| NO band | Implied | Actual | Edge | Trades | Distinct markets |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    edge_results = []
    for bucket in BUCKETS:
        d = stats["by_bucket"].get(bucket)
        if not d or d["trades"] == 0:
            lines.append(f"| {bucket[0]}-{bucket[1]}¢ | "
                         f"{_bucket_midpoint(bucket):.0f}% | — | — | 0 | 0 |")
            continue
        actual_pct = _safe_pct(d["no_wins"], d["trades"])
        implied_pct = _bucket_midpoint(bucket)
        edge_pp = actual_pct - implied_pct
        edge_results.append((bucket, actual_pct, implied_pct, edge_pp,
                             d["trades"], len(d["markets"])))
        lines.append(
            f"| {bucket[0]}-{bucket[1]}¢ | {implied_pct:.0f}% | "
            f"{actual_pct:.1f}% | {edge_pp:+.1f}pp | {d['trades']:,} | "
            f"{len(d['markets']):,} |"
        )
    lines.append("")
    lines.append("## Bucket Analysis — Per Series")
    lines.append("")
    series_list = sorted({s for (s, _) in stats["by_series_bucket"].keys()})
    for series in series_list:
        lines.append(f"### `{series}`")
        lines.append("")
        lines.append("| NO band | Actual | Edge vs implied | Trades | Markets |")
        lines.append("|---|---:|---:|---:|---:|")
        for bucket in BUCKETS:
            d = stats["by_series_bucket"].get((series, bucket))
            if not d or d["trades"] == 0:
                lines.append(f"| {bucket[0]}-{bucket[1]}¢ | — | — | 0 | 0 |")
                continue
            actual_pct = _safe_pct(d["no_wins"], d["trades"])
            implied_pct = _bucket_midpoint(bucket)
            edge_pp = actual_pct - implied_pct
            lines.append(
                f"| {bucket[0]}-{bucket[1]}¢ | {actual_pct:.1f}% | "
                f"{edge_pp:+.1f}pp | {d['trades']:,} | {len(d['markets']):,} |"
            )
        lines.append("")
    lines.append("## Fill Opportunity (proxy)")
    lines.append("")
    lines.append("Distinct markets per TRADE-day that printed ≥1 trade in the "
                 "NO 85-99¢ band. This is a rough proxy for how many resting "
                 "NO bids could potentially have been filled per day. Real "
                 "fill rate depends on queue position (no orderbook history "
                 "available via `/historical/*`).")
    lines.append("")
    lines.append("**Sample scaling:** we pulled trades for "
                 f"{fills.get('sampled_markets', 0):,} of {fills.get('universe_markets', 0):,} "
                 f"settled sport markets ({fills.get('sample_fraction', 0) * 100:.1f}% sample). "
                 "The 'scaled' figure projects the sample-rate up to the full universe — "
                 "the realistic per-day count if the bot scanned every market.")
    lines.append("")
    lines.append(f"- Days observed: **{fills['days']}**")
    lines.append(f"- Mean markets/day in band (sample): {fills['mean_per_day_sample']:.1f}")
    lines.append(f"- **Mean markets/day in band (scaled to universe): {fills['mean_per_day_scaled']:.1f}**")
    lines.append(f"- Median (sample): {fills['median_per_day']}")
    lines.append(f"- Min / Max (sample): {fills['min_per_day']} / {fills['max_per_day']}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    # Decision gate
    bucket_85_94_results = [r for r in edge_results if r[0] in [(85, 89), (90, 94)]]
    edge_at_85_95_ok = all(
        edge_pp >= EDGE_THRESHOLD_PP
        for (_, _, _, edge_pp, _, _) in bucket_85_94_results
    ) if bucket_85_94_results else False
    fill_ok = fills["mean_per_day_scaled"] >= MIN_MARKETS_PER_DAY_IN_BAND

    # Series-level edge: any series with NEGATIVE edge at 85-95¢ is a problem.
    series_negative = []
    for series in series_list:
        for bucket in [(85, 89), (90, 94)]:
            d = stats["by_series_bucket"].get((series, bucket))
            if not d or d["trades"] == 0:
                continue
            actual_pct = _safe_pct(d["no_wins"], d["trades"])
            implied_pct = _bucket_midpoint(bucket)
            if actual_pct - implied_pct < 0:
                series_negative.append(series)
                break

    green = edge_at_85_95_ok and fill_ok

    lines.append(f"- Aggregate edge ≥ +{EDGE_THRESHOLD_PP}pp at 85-95¢: "
                 f"**{'PASS' if edge_at_85_95_ok else 'FAIL'}**")
    lines.append(f"- Fill opportunity ≥ {MIN_MARKETS_PER_DAY_IN_BAND}/day "
                 f"(scaled to full universe): "
                 f"**{'PASS' if fill_ok else 'FAIL'}** "
                 f"({fills['mean_per_day_scaled']:.1f}/day)")
    if series_negative:
        lines.append(f"- ⚠️ NEGATIVE-edge series detected: "
                     f"**{', '.join(f'`{s}`' for s in series_negative)}** "
                     f"— exclude from strategy whitelist")
    lines.append("")
    if green:
        if series_negative:
            verdict = (f"## **🟡 GREEN-WITH-CAVEATS — proceed to Phase 2 "
                       f"BUT whitelist only positive-edge series**")
        else:
            verdict = "## **🟢 GREEN — proceed to Phase 2**"
    else:
        verdict = "## **🔴 RED — halt, post-mortem**"
    lines.append(verdict)
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- Data window predates 2026-Q2 institutional MM activity by "
                 "~60 days (Kalshi `/historical/cutoff` is always 2 months stale). "
                 "Recent edge could be tighter or wider.")
    lines.append("- Fill-rate proxy is markets/day, NOT actual queue-aware fills. "
                 "Real maker fills depend on bid-ask queue position which "
                 "Kalshi doesn't expose in `/historical/*`.")
    lines.append("- Sample = 200 random markets/series. Full universe is "
                 "4,066 markets; the sample is statistically representative "
                 "but per-bucket counts will scale ~7x if you pull everything.")
    return "\n".join(lines)


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} missing — run pull_markets.py + pull_trades.py first",
              file=sys.stderr)
        return 2
    with _conn() as conn:
        stats = analyze_bucket_stats(conn)
        fills = fill_opportunity_per_day(conn)
        summary = universe_summary(conn)
    report = build_report(stats, fills, summary)
    REPORT_PATH.write_text(report, encoding="utf-8")
    # Don't print to stdout — Windows cp1252 chokes on Unicode arrows/emoji.
    # Read the report file directly: report.md
    print(f"Report written to {REPORT_PATH}", file=sys.stderr)
    print(f"  {len(report.splitlines())} lines, "
          f"{REPORT_PATH.stat().st_size} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
