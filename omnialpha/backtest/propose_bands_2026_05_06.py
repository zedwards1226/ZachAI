"""Analyze historical_decision_snapshots and propose new bands per strategy.

Runs after pull_historical_trades_2026_05_06.py has populated the
`historical_decision_snapshots` table.

For each market series (KXBTC15M, KXBTCD), we evaluate BOTH sides:
- BUY YES side: hypothetical YES purchase at decision-time price.
  Wins if `result == 'yes'`. Implied probability = decision_yes_price.
- BUY NO side: hypothetical NO purchase at decision-time NO price (= 1 - yes).
  Wins if `result == 'no'`. Implied probability = decision_no_price.

Bucket by 5¢ price ranges. Per bucket compute:
- n, wins, raw WR
- Wilson 95% lower bound on WR
- Edge = Wilson_lo − implied probability
- Verdict: TRADEABLE (n>=30 AND edge>=+3pts), NEAR_FAIR, NEGATIVE, INSUFFICIENT

Output:
- omnialpha/backtest/proposed_bands_2026-05-06.md (the report)
- omnialpha/backtest/proposed_bands_2026-05-06.json (recommended bands JSON)

Run: python C:/ZachAI/omnialpha/backtest/propose_bands_2026_05_06.py
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"C:\ZachAI\omnialpha\state\omnialpha.db")
REPORT_PATH = Path(__file__).with_name("proposed_bands_2026-05-06.md")
BANDS_JSON_PATH = Path(__file__).with_name("proposed_bands_2026-05-06.json")
BUCKET_WIDTH = 0.05
MIN_N_FOR_VERDICT = 30
EDGE_MARGIN = 0.03  # 3 cents
WILSON_Z = 1.96


# Map series → strategy name in OmniAlpha config
SERIES_TO_STRATEGY = {
    "KXBTC15M": "crypto_btc15m_midband",
    "KXBTCD": "crypto_btcd_midband",
}


def wilson(wins: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return (lo, hi)


def fetch(conn, series: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT decision_yes_price, decision_no_price, result, is_in_target_window,
               offset_from_close_s, volume_fp
        FROM historical_decision_snapshots
        WHERE series_ticker = ?
        """,
        (series,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def bucket_analysis(snapshots: list[dict], side: str) -> list[dict]:
    """Bucket by 5c price for `side` ('yes' or 'no'). Wins = result matches side."""
    by_bucket: dict[float, list[dict]] = {}
    for s in snapshots:
        if side == "yes":
            price = s["decision_yes_price"]
            won = (s["result"] == "yes")
        else:
            price = s["decision_no_price"]
            won = (s["result"] == "no")
        if price is None or price <= 0 or price >= 1:
            continue
        bucket_low = round(math.floor(price / BUCKET_WIDTH) * BUCKET_WIDTH, 2)
        by_bucket.setdefault(bucket_low, []).append(won)

    out = []
    for bucket_low in sorted(by_bucket.keys()):
        outcomes = by_bucket[bucket_low]
        n = len(outcomes)
        wins = sum(1 for w in outcomes if w)
        wr = wins / n if n else 0
        lo, hi = wilson(wins, n)
        # Implied probability of "side wins" = mid-bucket price
        implied = bucket_low + BUCKET_WIDTH / 2
        edge_lo = lo - implied
        edge_hi = hi - implied
        if n < MIN_N_FOR_VERDICT:
            verdict = "INSUFFICIENT"
        elif lo >= implied + EDGE_MARGIN:
            verdict = "TRADEABLE"
        elif hi <= implied - EDGE_MARGIN:
            verdict = "NEGATIVE"
        else:
            verdict = "NEAR_FAIR"
        out.append({
            "bucket_low": bucket_low,
            "bucket_high": round(bucket_low + BUCKET_WIDTH, 2),
            "n": n,
            "wins": wins,
            "wr": wr,
            "wilson_lo": lo,
            "wilson_hi": hi,
            "implied": implied,
            "edge_lo": edge_lo,
            "edge_hi": edge_hi,
            "verdict": verdict,
        })
    return out


def merge_tradeable(buckets: list[dict]) -> list[tuple[float, float, float]]:
    """Merge consecutive TRADEABLE buckets into contiguous bands.

    Returns list of (low, high, our_forecast_of_true_rate) tuples in
    the format strategy_bands.json expects. our_forecast_of_true_rate
    = the conservative Wilson_lo of the merged region.
    """
    bands = []
    cur_lo = None
    cur_hi = None
    cur_min_wilson = 1.0
    for b in buckets:
        if b["verdict"] == "TRADEABLE":
            if cur_lo is None:
                cur_lo = b["bucket_low"]
            cur_hi = b["bucket_high"]
            cur_min_wilson = min(cur_min_wilson, b["wilson_lo"])
        else:
            if cur_lo is not None:
                bands.append((cur_lo, cur_hi, round(cur_min_wilson, 2)))
                cur_lo = cur_hi = None
                cur_min_wilson = 1.0
    if cur_lo is not None:
        bands.append((cur_lo, cur_hi, round(cur_min_wilson, 2)))
    return bands


def render_report(by_series: dict, bands_json: dict) -> str:
    lines = []
    lines.append("# OmniAlpha proposed-bands report")
    lines.append(f"_Generated: {datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")
    lines.append("## TL;DR")
    lines.append("")
    # Per-strategy summary
    for series, summary in by_series.items():
        strat = SERIES_TO_STRATEGY[series]
        lines.append(f"### {strat}")
        for side in ("yes", "no"):
            recs = bands_json.get(strat, {}).get(f"{side}_bands", [])
            if not recs:
                lines.append(f"- **{side.upper()} side**: NO TRADEABLE band found at n>=30, +3pt edge. Recommend keeping {side.upper()} side off (or paused).")
            else:
                lines.append(f"- **{side.upper()} side**: tradeable bands → " + ", ".join(
                    f"{int(lo*100)}-{int(hi*100)}c (forecast {int(f*100)}%)" for lo, hi, f in recs
                ))
        lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Methodology")
    lines.append(
        "For each finalized market in the last 30 days (data cutoff Mar 7 2026)"
        " we found the trade closest to `close_time − 90s` and used its YES/NO"
        " price as the decision-time snapshot. Markets bucketed by 5¢ price ranges."
        " A bucket is `TRADEABLE` only when n>=30 AND Wilson 95% lower bound on"
        " win rate beats the implied probability by at least 3¢ (covers fees +"
        " slippage). Anything else is INSUFFICIENT, NEAR_FAIR, or NEGATIVE."
    )
    lines.append("")

    # Per-series detail tables
    for series, summary in by_series.items():
        strat = SERIES_TO_STRATEGY[series]
        lines.append(f"## {strat} — full breakdown")
        n_snap = summary["total_snapshots"]
        n_in_win = summary["in_window"]
        lines.append(f"_Snapshots: {n_snap} total, {n_in_win} in target 30-180s window. "
                     f"Resolved YES: {summary['yes_won']}/{n_snap} "
                     f"({summary['yes_won']/max(n_snap,1)*100:.1f}%)._")
        lines.append("")
        for side in ("yes", "no"):
            buckets = summary[f"{side}_buckets"]
            lines.append(f"### {strat} BUY-{side.upper()}")
            lines.append("")
            lines.append("| Bucket | n | W | WR% | Wilson95 [lo, hi] | Implied | Edge (Wilson_lo − implied) | Verdict |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for b in buckets:
                band = f"{int(b['bucket_low']*100)}-{int(b['bucket_high']*100)}c"
                lines.append(
                    f"| {band} | {b['n']} | {b['wins']} | {b['wr']*100:.1f} | "
                    f"[{b['wilson_lo']*100:.1f}, {b['wilson_hi']*100:.1f}] | "
                    f"{b['implied']*100:.1f} | {b['edge_lo']*100:+.1f} | "
                    f"**{b['verdict']}** |"
                )
            lines.append("")
        lines.append("")

    lines.append("## Recommended JSON for strategy_bands.json")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(bands_json, indent=2))
    lines.append("```")
    return "\n".join(lines)


def main():
    conn = sqlite3.connect(DB_PATH)
    summaries = {}
    bands_json = {}
    for series in SERIES_TO_STRATEGY.keys():
        snaps = fetch(conn, series)
        if not snaps:
            print(f"  {series}: no snapshots — skipping")
            continue
        in_win = sum(1 for s in snaps if s["is_in_target_window"])
        yes_won = sum(1 for s in snaps if s["result"] == "yes")
        yes_buckets = bucket_analysis(snaps, "yes")
        no_buckets = bucket_analysis(snaps, "no")
        summaries[series] = {
            "total_snapshots": len(snaps),
            "in_window": in_win,
            "yes_won": yes_won,
            "yes_buckets": yes_buckets,
            "no_buckets": no_buckets,
        }
        strat = SERIES_TO_STRATEGY[series]
        bands_json[strat] = {
            "yes_bands": [list(b) for b in merge_tradeable(yes_buckets)],
            "no_bands": [list(b) for b in merge_tradeable(no_buckets)],
            "updated_at": datetime.now().isoformat() + "Z",
            "source": "historical_backtest_2026-05-06",
            "note": (
                "Bands derived from /historical/trades reconstruction of "
                "decision-time prices (close-90s anchor) over last 30 days "
                "of finalized markets. Wilson 95% lower bound must beat "
                "implied probability by 3pts to qualify."
            ),
        }
        print(f"  {series}: {len(snaps)} snapshots, "
              f"yes_buckets={len(yes_buckets)}, no_buckets={len(no_buckets)}, "
              f"yes_tradeable={len(bands_json[strat]['yes_bands'])}, "
              f"no_tradeable={len(bands_json[strat]['no_bands'])}")

    report = render_report(summaries, bands_json)
    REPORT_PATH.write_text(report, encoding="utf-8")
    BANDS_JSON_PATH.write_text(json.dumps(bands_json, indent=2), encoding="utf-8")
    print()
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {BANDS_JSON_PATH}")


if __name__ == "__main__":
    main()
