"""Regression test for the 2026-04-23 cascade-gate-blocks-second-break bug.

Scenario:
  - ORB candle closed bullish, so Gate 1 normally blocks any SHORT entry.
  - Morning bias is BEARISH, so Gate 2 normally blocks any LONG entry.
  - A confirmed SECOND BREAK (opposite side after a failed first break) is
    the market invalidating exactly those direction assumptions — Zarattini
    shows these setups carry ~72% win rate.

Before the fix: gates 1 + 2 blocked valid second-break reversals.
After the fix: `is_second_break=True` bypasses gates 1 + 2. Gate 3 still
applies (level proximity is not direction-assumption-dependent).
"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import combiner  # noqa: E402
from models import CandleDirection, Direction, ORBRange  # noqa: E402


def _bullish_orb():
    return ORBRange(
        high=27067.75, low=26997.5, range=70.25,
        candle_direction=CandleDirection.BULLISH,
        captured_at="2026-04-23T09:45:00-04:00",
    )


def _bearish_orb():
    return ORBRange(
        high=27067.75, low=26997.5, range=70.25,
        candle_direction=CandleDirection.BEARISH,
        captured_at="2026-04-23T09:45:00-04:00",
    )


def _mock_structure_not_at_level(monkeypatch):
    """Make gate 3 always pass so we isolate gates 1 + 2."""
    mock = MagicMock()
    loc = MagicMock()
    loc.value = "ABOVE_VWAP"
    nearest = MagicMock()
    nearest.name = "none"
    mock.return_value = (loc, nearest)
    monkeypatch.setattr("agents.structure.recompute_price_location", mock)


def test_first_break_short_on_bullish_orb_still_blocked(monkeypatch):
    """Control: non-second-break SHORT on bullish ORB must still be blocked."""
    _mock_structure_not_at_level(monkeypatch)
    result = combiner._check_cascade(
        Direction.SHORT, _bullish_orb(),
        states={"memory": {"morning_bias": "NEUTRAL"}, "structure": {}},
        price=26990.0, is_second_break=False,
    )
    assert result == "orb_candle_wrong_direction"


def test_second_break_short_on_bullish_orb_allowed(monkeypatch):
    """Fix: a confirmed second-break SHORT bypasses gate 1 (ORB candle)."""
    _mock_structure_not_at_level(monkeypatch)
    result = combiner._check_cascade(
        Direction.SHORT, _bullish_orb(),
        states={"memory": {"morning_bias": "BEARISH_BIAS"}, "structure": {}},
        price=26990.0, is_second_break=True,
    )
    assert result is None, (
        f"second-break SHORT after failed LONG should pass all gates, "
        f"got blocked by: {result}"
    )


def test_first_break_long_vs_bearish_bias_still_blocked(monkeypatch):
    """Control: non-second-break LONG vs bearish bias must still be blocked."""
    _mock_structure_not_at_level(monkeypatch)
    result = combiner._check_cascade(
        Direction.LONG, _bullish_orb(),
        states={"memory": {"morning_bias": "BEARISH_BIAS"}, "structure": {}},
        price=27080.0, is_second_break=False,
    )
    assert result == "htf_bias_conflict"


def test_second_break_long_vs_bearish_bias_allowed(monkeypatch):
    """Fix: a confirmed second-break LONG bypasses gate 2 (HTF bias)."""
    _mock_structure_not_at_level(monkeypatch)
    result = combiner._check_cascade(
        Direction.LONG, _bullish_orb(),
        states={"memory": {"morning_bias": "BEARISH_BIAS"}, "structure": {}},
        price=27080.0, is_second_break=True,
    )
    assert result is None, (
        f"second-break LONG after failed SHORT should pass all gates, "
        f"got blocked by: {result}"
    )


def test_second_break_still_blocked_at_strong_level(monkeypatch):
    """Gate 3 is NOT direction-assumption-based — it must still apply
    to second breaks. Price pinned AT a prior day/week level ahead is
    a structural reason to skip regardless of how strong the setup is.
    """
    mock = MagicMock()
    loc = MagicMock()
    loc.value = "AT_LEVEL"
    nearest = MagicMock()
    nearest.name = "PDH"
    mock.return_value = (loc, nearest)
    monkeypatch.setattr("agents.structure.recompute_price_location", mock)

    result = combiner._check_cascade(
        Direction.LONG, _bullish_orb(),
        states={"memory": {"morning_bias": "NEUTRAL"}, "structure": {}},
        price=27080.0, is_second_break=True,
    )
    assert result == "at_strong_level_ahead:PDH", (
        f"gate 3 (level proximity) must apply to second breaks too, "
        f"got: {result}"
    )
