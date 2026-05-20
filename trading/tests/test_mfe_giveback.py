"""Tests for the MFE 50% giveback exit math in tv_trader.monitor_trades.

Phase 0.5 (2026-05-19). The block lives inside monitor_trades() so we test the
underlying formula in isolation: given (entry, stop, mfe_price, current_price,
direction), does the giveback ratio cross MFE_GIVEBACK_RATIO once mfe_r
exceeds MFE_GIVEBACK_ACTIVATE_R?

These tests are unit-pure — no CDP, no journal, no telegram.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MFE_GIVEBACK_RATIO, MFE_GIVEBACK_ACTIVATE_R  # noqa: E402


def _compute_mfe_state(entry: float, stop: float, mfe: float, price: float,
                      direction: str) -> dict:
    """Mirror the math in tv_trader.monitor_trades MFE-giveback block."""
    mfe_from_entry = abs(mfe - entry)
    risk = abs(entry - stop)
    if risk == 0:
        return {"active": False, "fires": False, "mfe_r": 0.0, "giveback": 0.0}
    mfe_r = mfe_from_entry / risk
    if direction == "LONG":
        giveback = (mfe - price) / mfe_from_entry if mfe_from_entry > 0 else 0
    else:
        giveback = (price - mfe) / mfe_from_entry if mfe_from_entry > 0 else 0
    active = mfe_r >= MFE_GIVEBACK_ACTIVATE_R
    fires = active and giveback >= MFE_GIVEBACK_RATIO
    return {"active": active, "fires": fires, "mfe_r": mfe_r, "giveback": giveback}


def test_long_below_1r_does_not_activate():
    """MFE at 0.5R — giveback module is dormant."""
    state = _compute_mfe_state(
        entry=22000, stop=21900, mfe=22050, price=22000, direction="LONG",
    )
    assert state["mfe_r"] == pytest.approx(0.5)
    assert not state["active"]
    assert not state["fires"]


def test_long_1r_no_giveback_does_not_fire():
    """MFE at +1R but price still at MFE → no giveback yet."""
    state = _compute_mfe_state(
        entry=22000, stop=21900, mfe=22100, price=22100, direction="LONG",
    )
    assert state["mfe_r"] == pytest.approx(1.0)
    assert state["active"]
    assert state["giveback"] == pytest.approx(0.0)
    assert not state["fires"]


def test_long_1r_50pct_giveback_fires():
    """MFE +100pt (1R), price retraced 50pt → 50% giveback → fires."""
    state = _compute_mfe_state(
        entry=22000, stop=21900, mfe=22100, price=22050, direction="LONG",
    )
    assert state["mfe_r"] == pytest.approx(1.0)
    assert state["giveback"] == pytest.approx(0.5)
    assert state["fires"]


def test_long_1r_49pct_giveback_does_not_fire():
    """49% giveback just under the trigger."""
    state = _compute_mfe_state(
        entry=22000, stop=21900, mfe=22100, price=22051, direction="LONG",
    )
    assert 0.48 < state["giveback"] < 0.50
    assert not state["fires"]


def test_long_2r_60pct_giveback_fires():
    """Bigger move, deeper retrace — fires."""
    state = _compute_mfe_state(
        entry=22000, stop=21900, mfe=22200, price=22080, direction="LONG",
    )
    assert state["mfe_r"] == pytest.approx(2.0)
    assert state["giveback"] == pytest.approx(0.60)
    assert state["fires"]


def test_short_1r_50pct_giveback_fires():
    """SHORT symmetry: entry 22000, stop 22100 (100pt risk), MFE 21900,
    price 21950 → giveback 50%."""
    state = _compute_mfe_state(
        entry=22000, stop=22100, mfe=21900, price=21950, direction="SHORT",
    )
    assert state["mfe_r"] == pytest.approx(1.0)
    assert state["giveback"] == pytest.approx(0.5)
    assert state["fires"]


def test_zero_risk_is_safe():
    """Pathological zero-risk trade — must not divide-by-zero or fire."""
    state = _compute_mfe_state(
        entry=22000, stop=22000, mfe=22050, price=22025, direction="LONG",
    )
    assert state["mfe_r"] == 0.0
    assert not state["fires"]
