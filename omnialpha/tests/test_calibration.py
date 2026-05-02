"""Tests for calibration analysis. Pure math — no DB needed for these."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.calibration import (
    brier_score,
    log_loss,
    compute_bins,
)


def test_brier_score_perfect():
    """Perfect predictions: prob 1.0 → outcome 1, prob 0.0 → outcome 0."""
    pairs = [(1.0, 1), (1.0, 1), (0.0, 0), (0.0, 0)]
    assert brier_score(pairs) == 0.0


def test_brier_score_random():
    """50/50 predictions on 50/50 outcomes → ~0.25."""
    pairs = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
    assert abs(brier_score(pairs) - 0.25) < 1e-6


def test_brier_score_empty():
    import math
    assert math.isnan(brier_score([]))


def test_log_loss_perfect_close():
    """Near-perfect (clamped at 0.999) gives a small but non-zero loss."""
    pairs = [(1.0, 1), (1.0, 1), (0.0, 0), (0.0, 0)]
    # log(0.999) ≈ -0.001, mean over 4 → ~0.001
    assert log_loss(pairs) < 0.01


def test_compute_bins_basic():
    """Three predictions in three different bins."""
    pairs = [
        (0.05, 0),  # bin 0
        (0.25, 1),  # bin 2
        (0.95, 1),  # bin 9
    ]
    bins = compute_bins(pairs, n_bins=10)
    assert len(bins) == 10
    assert bins[0].n == 1
    assert bins[2].n == 1
    assert bins[9].n == 1
    # Empty bins still have defaults (mean = midpoint)
    assert bins[1].n == 0


def test_compute_bins_calibration_curve():
    """Predictions of 0.7 with 70% actually true → well calibrated → miscal ≈ 0."""
    pairs = [(0.7, 1)] * 7 + [(0.7, 0)] * 3  # 70% YES rate at 70% prediction
    bins = compute_bins(pairs, n_bins=10)
    bin7 = bins[7]
    assert bin7.n == 10
    assert abs(bin7.actual_yes_rate - 0.7) < 1e-6
    assert abs(bin7.miscal) < 1e-6


def test_compute_bins_miscalibration_detected():
    """Predict 80% YES but actual is only 50% → miscal = -30%."""
    pairs = [(0.85, 1)] * 5 + [(0.85, 0)] * 5
    bins = compute_bins(pairs, n_bins=10)
    bin8 = bins[8]  # [0.80, 0.90)
    assert bin8.n == 10
    assert abs(bin8.actual_yes_rate - 0.5) < 1e-6
    # mean predicted is 0.85, actual is 0.5 → miscal -0.35
    assert abs(bin8.miscal - (-0.35)) < 1e-6
