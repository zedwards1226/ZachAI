"""Tests for edge calculation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from edge import (
    prob_exceeds, compute_edge, best_side, effective_edge,
    parse_strike_from_ticker, clamp_edge, passes_min_distance,
)


def test_prob_exceeds_above():
    # All ensemble members above strike 75F → high probability of exceeding
    p = prob_exceeds([80, 81, 79, 82, 80], 75)
    assert p > 0.85, f"Expected >0.85, got {p}"


def test_prob_exceeds_below():
    # All ensemble members below strike 80F → low probability of exceeding
    p = prob_exceeds([65, 64, 66, 63, 67], 80)
    assert p < 0.05, f"Expected <0.05, got {p}"


def test_prob_exceeds_at_strike():
    # 4 of 8 strictly above 75 → 0.5
    p = prob_exceeds([76, 77, 78, 79, 74, 73, 72, 71], 75)
    assert 0.45 < p < 0.55, f"Expected ~0.5, got {p}"


def test_compute_edge_positive():
    # Our prob 0.80, market at 60¢ → positive edge (market underpriced)
    edge = compute_edge(0.80, 60)
    assert edge == pytest_approx(0.20, abs=0.01)


def test_compute_edge_negative():
    # Our prob 0.40, market at 60¢ → negative edge (market overpriced)
    edge = compute_edge(0.40, 60)
    assert edge < 0


def test_best_side_yes():
    assert best_side(0.15) == "yes"


def test_best_side_no():
    assert best_side(-0.12) == "no"


def test_parse_strike():
    assert parse_strike_from_ticker("KXHIGH-NY-20240601-T75") == 75.0
    assert parse_strike_from_ticker("KXHIGH-CHI-20240601-T82") == 82.0
    assert parse_strike_from_ticker("KXHIGH-MIA-20240601-TXYZ") is None


def test_clamp_edge_caps_positive():
    # Claimed 30-point edge gets pulled back to the 15-point cap
    p, e = clamp_edge(0.80, 0.50, 0.15)
    assert e == pytest_approx(0.15)
    assert p == pytest_approx(0.65)


def test_clamp_edge_caps_negative():
    p, e = clamp_edge(0.20, 0.50, 0.15)
    assert e == pytest_approx(-0.15)
    assert p == pytest_approx(0.35)


def test_clamp_edge_passthrough_small_edge():
    # Edge inside the cap is untouched
    p, e = clamp_edge(0.58, 0.50, 0.15)
    assert e == pytest_approx(0.08)
    assert p == pytest_approx(0.58)


def test_clamp_edge_disabled_when_cap_zero():
    p, e = clamp_edge(0.90, 0.50, 0.0)
    assert e == pytest_approx(0.40)
    assert p == pytest_approx(0.90)


def test_min_distance_blocks_center_ladder():
    # Bin 88.5 with forecast 89.2 → 0.7°F away → center ladder, blocked
    assert passes_min_distance(88.5, 89.2, 2.0) is False


def test_min_distance_allows_outer_ladder():
    # Bin 92.5 with forecast 89.2 → 3.3°F away → outer ladder, allowed
    assert passes_min_distance(92.5, 89.2, 2.0) is True


def test_min_distance_exact_boundary_allowed():
    assert passes_min_distance(91.0, 89.0, 2.0) is True


def test_min_distance_disabled_when_zero():
    assert passes_min_distance(89.0, 89.0, 0.0) is True


# pytest_approx helper for simple test
class pytest_approx:
    def __init__(self, val, abs=1e-6):
        self.val = val
        self.abs = abs
    def __eq__(self, other):
        return abs(other - self.val) <= self.abs
