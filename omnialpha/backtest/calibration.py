"""Calibration analysis — does Kalshi market price = actual probability?

For each settled market we have:
  - final_yes_ask (market's last YES price, ~= implied YES probability)
  - result (yes/no)

Calibration question: when the market priced YES at p, does YES actually
happen at rate p?

If yes → market is well calibrated → no edge from "the market is wrong"
If no → market mispricing in some band → potential strategy edge

This module computes:
  - Brier score (lower = better calibrated)
  - Calibration curve: predicted-prob vs actual-yes-rate, in 10 bins
  - Per-band stats: mean predicted, actual yes rate, count, log-loss

Does NOT need any LLM, any external data, any auth. Pure SQL + math.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Sequence

from data_layer.database import get_conn

logger = logging.getLogger(__name__)


@dataclass
class CalibrationBin:
    """One row of the calibration table."""
    bin_low: float
    bin_high: float
    n: int
    mean_predicted_yes: float
    actual_yes_rate: float
    miscal: float            # actual_yes_rate - mean_predicted_yes (signed)


@dataclass
class CalibrationReport:
    series_ticker: str | None
    sector: str | None
    n_markets: int
    brier_score: float
    log_loss: float
    bins: list[CalibrationBin] = field(default_factory=list)


def _fetch_settled_predictions(
    *,
    series_ticker: str | None,
    sector: str | None,
) -> list[tuple[float, int]]:
    """Pull (predicted_yes_prob, actual_yes) pairs for settled binary markets.

    Uses `last_price_dollars` from raw_json — that's the last actual trade
    price before settlement (in YES dollars), which equals implied YES
    probability at close. The schema's `final_yes_ask_dollars` is post-
    settlement residual (0 or 1) and useless for calibration.
    """
    import json
    sql = (
        "SELECT raw_json, result FROM markets "
        "WHERE status='finalized' AND result IN ('yes','no') "
        "AND market_type = 'binary' "
    )
    params: list = []
    if series_ticker:
        sql += " AND series_ticker = ? "
        params.append(series_ticker)
    if sector:
        sql += " AND sector = ? "
        params.append(sector)

    pairs: list[tuple[float, int]] = []
    with get_conn(readonly=True) as conn:
        for row in conn.execute(sql, params):
            try:
                raw = json.loads(row["raw_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            last_price = raw.get("last_price_dollars")
            if last_price is None or last_price == "":
                continue
            try:
                p = float(last_price)
            except (TypeError, ValueError):
                continue
            # Skip markets that never traded (last_price == 0 with 0 volume
            # is the un-traded state, not a "0% YES" prediction).
            try:
                vol = float(raw.get("volume_fp") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            if vol < 1.0:
                continue
            actual = 1 if row["result"] == "yes" else 0
            pairs.append((p, actual))
    return pairs


def brier_score(pairs: Sequence[tuple[float, int]]) -> float:
    """Mean squared error between predicted probability and outcome (0/1).
    Lower is better. 0.0 = perfect, 0.25 = random coin flip."""
    if not pairs:
        return float("nan")
    return sum((p - actual) ** 2 for p, actual in pairs) / len(pairs)


def log_loss(pairs: Sequence[tuple[float, int]]) -> float:
    """Log loss with p clamped to (0.001, 0.999) to avoid log(0)."""
    if not pairs:
        return float("nan")
    eps = 0.001
    total = 0.0
    for p, actual in pairs:
        p = min(max(p, eps), 1 - eps)
        total += -(actual * math.log(p) + (1 - actual) * math.log(1 - p))
    return total / len(pairs)


def compute_bins(
    pairs: Sequence[tuple[float, int]],
    n_bins: int = 10,
) -> list[CalibrationBin]:
    """Slice predictions into equal-width probability bins, compute stats per bin."""
    bins: list[CalibrationBin] = []
    if not pairs:
        return bins
    bin_width = 1.0 / n_bins
    for i in range(n_bins):
        # Round to avoid float drift at boundaries (e.g. 7*0.1 = 0.7000...001
        # would push 0.7 into bin 8 instead of bin 7)
        lo = round(i * bin_width, 10)
        hi = round((i + 1) * bin_width, 10)
        # Last bin includes upper bound
        if i == n_bins - 1:
            in_bin = [(p, a) for p, a in pairs if lo <= p <= hi]
        else:
            in_bin = [(p, a) for p, a in pairs if lo <= p < hi]
        n = len(in_bin)
        if n == 0:
            mean_pred = (lo + hi) / 2
            actual_rate = 0.0
        else:
            mean_pred = sum(p for p, _ in in_bin) / n
            actual_rate = sum(a for _, a in in_bin) / n
        bins.append(CalibrationBin(
            bin_low=lo,
            bin_high=hi,
            n=n,
            mean_predicted_yes=mean_pred,
            actual_yes_rate=actual_rate,
            miscal=actual_rate - mean_pred,
        ))
    return bins


def analyze(
    *,
    series_ticker: str | None = None,
    sector: str | None = None,
    n_bins: int = 10,
) -> CalibrationReport:
    pairs = _fetch_settled_predictions(series_ticker=series_ticker, sector=sector)
    return CalibrationReport(
        series_ticker=series_ticker,
        sector=sector,
        n_markets=len(pairs),
        brier_score=brier_score(pairs),
        log_loss=log_loss(pairs),
        bins=compute_bins(pairs, n_bins=n_bins),
    )


def format_report(rep: CalibrationReport) -> str:
    target = rep.series_ticker or rep.sector or "ALL"
    lines = [
        f"=== Calibration: {target} ===",
        f"Markets:     {rep.n_markets:,}",
        f"Brier:       {rep.brier_score:.4f}  (0.0 perfect, 0.25 random)",
        f"Log loss:    {rep.log_loss:.4f}",
        "",
        "Bin           Count   Pred%   Actual%   Miscal",
        "----------    -----   -----   -------   ------",
    ]
    for b in rep.bins:
        lines.append(
            f"[{b.bin_low:.2f},{b.bin_high:.2f}] "
            f"{b.n:6d}  "
            f"{b.mean_predicted_yes * 100:5.1f}%  "
            f"{b.actual_yes_rate * 100:6.1f}%   "
            f"{b.miscal * 100:+5.1f}%"
        )
    return "\n".join(lines)
