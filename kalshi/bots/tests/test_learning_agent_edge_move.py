"""Learning agent MIN_EDGE decisions must be graded on realized trade P&L
(2026-06-10 fix). The old Brier-based input held MIN_EDGE at the floor while
live trades lost money — losses concentrate in the selected extreme-edge
trades, which the signal-population Brier never sees."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning_agent import _decide_edge_move, MIN_EDGE_FLOOR, MIN_EDGE_CEIL, EDGE_STEP


def _stats(samples, pnl, wr):
    return {"samples": samples, "pnl_usd": pnl, "win_rate": wr,
            "wins": 0, "losses": 0}


def test_small_sample_holds():
    new, reason = _decide_edge_move(_stats(5, -10.0, 0.40), 0.08)
    assert new == 0.08
    assert "Not enough" in reason


def test_negative_pnl_raises_edge():
    new, _ = _decide_edge_move(_stats(20, -12.50, 0.51), 0.05)
    assert new == 0.05 + EDGE_STEP


def test_negative_pnl_respects_ceiling():
    new, reason = _decide_edge_move(_stats(20, -12.50, 0.51), MIN_EDGE_CEIL)
    assert new == MIN_EDGE_CEIL
    assert "ceiling" in reason


def test_positive_pnl_good_wr_lowers_edge():
    new, _ = _decide_edge_move(_stats(20, 15.0, 0.62), 0.10)
    assert new == 0.10 - EDGE_STEP


def test_positive_pnl_respects_floor():
    new, reason = _decide_edge_move(_stats(20, 15.0, 0.62), MIN_EDGE_FLOOR)
    assert new == MIN_EDGE_FLOOR
    assert "floor" in reason


def test_positive_pnl_mediocre_wr_holds():
    # Profitable but win rate below the bar — don't loosen on a lucky streak
    new, _ = _decide_edge_move(_stats(20, 5.0, 0.52), 0.10)
    assert new == 0.10


def test_breakeven_holds():
    new, _ = _decide_edge_move(_stats(20, 0.0, 0.55), 0.10)
    assert new == 0.10
