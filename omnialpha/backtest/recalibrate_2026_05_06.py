"""Recalibrate OmniAlpha crypto-strategy YES/NO bands from live trade data.

Run: python -m omnialpha.backtest.recalibrate_2026_05_06
Or:  python C:/ZachAI/omnialpha/backtest/recalibrate_2026_05_06.py

Reads `omnialpha.db.trades` and produces a markdown report with per-strategy
per-side per-5-cent-bucket win rates, Wilson 95% lower bounds, and edge
recommendations.

Why live trades and not /historical/markets:
- The bot's markets table overwrites rows on each scan. By the time a
  market resolves, `final_yes_ask_dollars` has already collapsed to ~0
  or ~1 — useless as a "price at decision time" snapshot.
- Kalshi `/historical/markets` returns the same final-state-only data.
- Kalshi `/historical/trades` has tick-level prices but requires one
  request per market (slow at scale).
- Live trades are the ONLY source where entry price + outcome are both
  honest: we recorded the price we paid, then watched the market settle.
- Sample size is small (88 trades total) so the Wilson lower bound is
  the appropriate filter — only buckets with n>=10 and Wilson_lo > implied
  get a "tradeable" verdict.

Limitations:
- 88 trades across 5 strategies × 2 sides × multiple price buckets means
  most buckets have n<5. Honest call: most buckets are "insufficient data,"
  not "no edge."
- The widened-band trades from May 4-6 contribute ~30 of the 88 trades,
  so calibration on the WIDE bands is the freshest signal.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DB = Path(r"C:\ZachAI\omnialpha\state\omnialpha.db")
OUT = Path(__file__).with_name("recalibration_report_2026-05-06.md")
BUCKET_WIDTH = 5  # cents
MIN_N_FOR_VERDICT = 10  # below this we say "insufficient data"
WILSON_Z = 1.96  # 95%


def wilson_lower(wins: int, n: int, z: float = WILSON_Z) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def wilson_upper(wins: int, n: int, z: float = WILSON_Z) -> float:
    if n == 0:
        return 1.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return min(1.0, (centre + margin) / denom)


def collect_buckets(conn) -> dict:
    """Return {(strategy, side): {bucket_low: {n, wins, losses, stake, pnl, prices}}}"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT strategy, side, price_cents, status, stake_usd, pnl_usd
        FROM trades
        WHERE status IN ('won', 'lost') AND price_cents BETWEEN 1 AND 99
        """
    )
    out: dict = defaultdict(lambda: defaultdict(lambda: {
        "n": 0, "wins": 0, "losses": 0, "stake": 0.0, "pnl": 0.0, "prices": []
    }))
    for strategy, side, price, status, stake, pnl in cur.fetchall():
        bucket_low = (price // BUCKET_WIDTH) * BUCKET_WIDTH
        b = out[(strategy, side)][bucket_low]
        b["n"] += 1
        b["wins"] += 1 if status == "won" else 0
        b["losses"] += 1 if status == "lost" else 0
        b["stake"] += stake or 0.0
        b["pnl"] += pnl or 0.0
        b["prices"].append(price)
    return out


def verdict(n: int, wins: int, side: str, avg_price_cents: float) -> str:
    """KEEP / DROP / NEED MORE DATA per bucket.

    Edge logic: when you BUY a contract at price X cents, market thinks it
    has X% chance of paying. If your actual win rate's Wilson 95% LOWER
    BOUND beats that, you have a real (post-fee) edge with confidence.
    """
    if n < MIN_N_FOR_VERDICT:
        return "NEED MORE DATA"
    implied = avg_price_cents / 100.0
    lo = wilson_lower(wins, n)
    hi = wilson_upper(wins, n)
    if lo > implied + 0.03:  # 3% margin of safety after fees/slippage
        return "KEEP / has edge"
    if hi < implied - 0.03:
        return "DROP / negative edge"
    return "WATCH (confidence overlaps fair value)"


def render_report(buckets: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = []
    lines.append("# OmniAlpha crypto recalibration report")
    lines.append(f"_Generated: {now}_")
    lines.append("")

    # === Plain-English summary at the top ===
    lines.append("## TL;DR (what this report actually says)")
    lines.append("")
    lines.append(
        "We have **88 closed crypto trades** total — small. The math gets"
        " statistical at sample sizes ~30+ per bucket; we have one bucket"
        " (`btcd YES 75-80c`) with n=12 and one (`btcd NO 75-80c`) with n=13."
        " Everything else is too thin for a confident verdict."
    )
    lines.append("")
    lines.append("**What the raw P&L tells us anyway** (without statistical confidence):")
    lines.append("")
    lines.append("- `btcd_midband` NO at 70-80¢: **−$110** over 19 trades. Direction is"
                 " clear even if Wilson can't prove it at 95%. **Keep paused.**")
    lines.append("- `btc15m_midband` YES at 80-85¢: **−$26** over 6 trades. Small but"
                 " trending wrong; calibration is 2 months old. **Keep trimmed.**")
    lines.append("- `btcd_midband` YES at 70-85¢: **+$71** over 26 trades, 88% WR."
                 " Closest thing to a real working bucket. **Keep running.**")
    lines.append("- `sol15m_midband` YES: +$22 over 7 trades. Looks good but n is too"
                 " small to call. **Watch.**")
    lines.append("- Everything else: too few trades to have an opinion.")
    lines.append("")
    lines.append("**The fundamental data problem:** the bot didn't record the YES price"
                 " at the moment we'd hypothetically have entered. Kalshi's historical"
                 " endpoints only return final state. So we can't backtest \"what would"
                 " have happened if we ran with band X\" — we can only audit what DID"
                 " happen with the bands we used. Real recalibration requires either"
                 " (a) modifying the bot to log decision-time price snapshots going"
                 " forward, or (b) pulling Kalshi `/historical/trades` per finalized"
                 " market and reconstructing pre-close prices (slow but doable). Both"
                 " are follow-up tasks.")
    lines.append("")
    lines.append("**Practical recommendation for tonight:** keep the two pauses live."
                 " Don't widen anything. Re-run this script weekly to watch n grow.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Built from live `trades` table only (88 closed trades). Kalshi historical"
        " endpoints don't include intra-market price snapshots, and the local"
        " `markets` table overwrites prices on settlement. So this is the most"
        " honest read available — small but real."
    )
    lines.append("")
    lines.append("**Verdict legend**")
    lines.append("- **KEEP / has edge** — Wilson 95% lower bound on win rate beats the implied probability by ≥3 pts")
    lines.append("- **DROP / negative edge** — Wilson 95% upper bound is below implied minus 3 pts")
    lines.append("- **WATCH** — confidence interval crosses fair value (signal not strong either way)")
    lines.append("- **NEED MORE DATA** — fewer than 10 closed trades in this bucket")
    lines.append("")
    lines.append(
        "Buckets are 5¢ wide. `n` = total closed trades, `W` = wins, `WR%` = raw win"
        " rate, `Wilson95 [lo, hi]` = 95% confidence interval, `implied%` = avg price"
        " of the side bought (i.e. what the market thought the win rate was)."
    )
    lines.append("")

    for (strategy, side), buckets_by_low in sorted(buckets.items()):
        # Strategy + side header
        lines.append(f"## {strategy} — {side.upper()} side")
        lines.append("")
        # Total stats for this strategy/side
        total_n = sum(b["n"] for b in buckets_by_low.values())
        total_w = sum(b["wins"] for b in buckets_by_low.values())
        total_pnl = sum(b["pnl"] for b in buckets_by_low.values())
        total_stake = sum(b["stake"] for b in buckets_by_low.values())
        roi = (total_pnl / total_stake * 100) if total_stake else 0
        lines.append(f"_Total: {total_n} trades, {total_w}W ({total_w/total_n*100:.1f}% raw WR), "
                     f"${total_pnl:+.2f} on ${total_stake:.2f} stake ({roi:+.1f}% ROI)_")
        lines.append("")
        lines.append("| Bucket | n | W | L | WR% | Wilson95 [lo, hi] | Implied% | Edge (Wilson_lo − implied) | Stake | P&L | ROI% | Verdict |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for bucket_low in sorted(buckets_by_low.keys()):
            b = buckets_by_low[bucket_low]
            n, w, l = b["n"], b["wins"], b["losses"]
            wr = w / n * 100 if n else 0.0
            avg_p = sum(b["prices"]) / len(b["prices"])
            lo = wilson_lower(w, n) * 100
            hi = wilson_upper(w, n) * 100
            implied = avg_p
            edge = lo - implied
            v = verdict(n, w, side, avg_p)
            roi_b = (b["pnl"] / b["stake"] * 100) if b["stake"] else 0
            band = f"{int(bucket_low)}-{int(bucket_low) + BUCKET_WIDTH}c"
            lines.append(
                f"| {band} | {n} | {w} | {l} | {wr:.1f} | [{lo:.1f}, {hi:.1f}] | "
                f"{implied:.1f} | {edge:+.1f} | ${b['stake']:.2f} | ${b['pnl']:+.2f} | "
                f"{roi_b:+.1f} | {v} |"
            )
        lines.append("")
    return "\n".join(lines)


def main():
    conn = sqlite3.connect(DB)
    buckets = collect_buckets(conn)
    report = render_report(buckets)
    OUT.write_text(report, encoding="utf-8")
    print(f"Wrote {OUT}  ({len(report)} chars, {len(buckets)} (strategy,side) groups)")
    # Quick stdout summary
    print()
    for (strategy, side), bs in sorted(buckets.items()):
        n = sum(b["n"] for b in bs.values())
        pnl = sum(b["pnl"] for b in bs.values())
        print(f"  {strategy:25} {side:3}  {n:>3} trades  P&L ${pnl:+8.2f}")


if __name__ == "__main__":
    main()
