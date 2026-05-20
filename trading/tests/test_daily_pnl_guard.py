"""Tests for agents.daily_pnl_guard — daily P&L lock + MFE giveback math.

Phase 0.5 (2026-05-19). Covers:
  - unrealized_pnl math for LONG / SHORT with slippage haircut
  - check() fires TARGET at +$200, STOP at -$200
  - lock is idempotent (only one fire per session)
  - reset_for_new_session() clears the lock
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import daily_pnl_guard  # noqa: E402
from config import (  # noqa: E402
    MULTIPLIER, SLIPPAGE_PTS,
    DAILY_PROFIT_TARGET_DOLLARS, DAILY_LOSS_LIMIT_DOLLARS,
)


@pytest.fixture(autouse=True)
def reset_lock():
    """Clear the in-memory lock between tests."""
    daily_pnl_guard.reset_for_new_session()
    yield
    daily_pnl_guard.reset_for_new_session()


@pytest.fixture
def zero_realized(monkeypatch):
    """Force journal.get_today_pnl() to return 0 so we test the unrealized half."""
    monkeypatch.setattr(daily_pnl_guard.journal, "get_today_pnl", lambda: 0.0)


def _order(direction: str, entry: float) -> dict:
    return {"direction": direction, "entry": entry}


def test_unrealized_long_up(zero_realized):
    """LONG entry 22000, price 22050 → gross 50pt, net 48pt (- SLIPPAGE), × $2/pt = $96."""
    pnl = daily_pnl_guard.unrealized_pnl({1: _order("LONG", 22000)}, 22050)
    assert pnl == (50 - SLIPPAGE_PTS) * MULTIPLIER


def test_unrealized_long_down(zero_realized):
    """LONG entry 22000, price 21950 → gross -50pt, net -52pt, × $2 = -$104."""
    pnl = daily_pnl_guard.unrealized_pnl({1: _order("LONG", 22000)}, 21950)
    assert pnl == (-50 - SLIPPAGE_PTS) * MULTIPLIER


def test_unrealized_short_up(zero_realized):
    """SHORT entry 22000, price 21950 → gross 50pt for short, net 48pt, $96."""
    pnl = daily_pnl_guard.unrealized_pnl({1: _order("SHORT", 22000)}, 21950)
    assert pnl == (50 - SLIPPAGE_PTS) * MULTIPLIER


def test_unrealized_empty_active_orders(zero_realized):
    assert daily_pnl_guard.unrealized_pnl({}, 22000) == 0.0


def test_check_target_fires(monkeypatch):
    # Realized +$100; unrealized must push us over +$200.
    # Need (price - entry - SLIPPAGE) * MULTIPLIER >= 100.
    # With MULTIPLIER=$2, SLIPPAGE=2pt: (delta - 2)*2 >= 100 → delta >= 52
    monkeypatch.setattr(daily_pnl_guard.journal, "get_today_pnl", lambda: 100.0)
    event = daily_pnl_guard.check({1: _order("LONG", 22000)}, 22000 + 60)
    assert event is not None
    kind, total = event
    assert kind == "TARGET"
    assert total >= DAILY_PROFIT_TARGET_DOLLARS
    assert daily_pnl_guard.is_locked()


def test_check_stop_fires(monkeypatch):
    monkeypatch.setattr(daily_pnl_guard.journal, "get_today_pnl", lambda: -100.0)
    event = daily_pnl_guard.check({1: _order("LONG", 22000)}, 22000 - 60)
    assert event is not None
    kind, total = event
    assert kind == "STOP"
    assert total <= -DAILY_LOSS_LIMIT_DOLLARS
    assert daily_pnl_guard.is_locked()


def test_check_idempotent_after_lock(monkeypatch):
    """Once locked, further check() calls return None even if still over threshold."""
    monkeypatch.setattr(daily_pnl_guard.journal, "get_today_pnl", lambda: 250.0)
    first = daily_pnl_guard.check({}, 22000)
    assert first is not None
    second = daily_pnl_guard.check({}, 22000)
    assert second is None


def test_check_no_fire_below_thresholds(monkeypatch):
    monkeypatch.setattr(daily_pnl_guard.journal, "get_today_pnl", lambda: 50.0)
    assert daily_pnl_guard.check({1: _order("LONG", 22000)}, 22005) is None
    assert not daily_pnl_guard.is_locked()


def test_reset_clears_lock(monkeypatch):
    monkeypatch.setattr(daily_pnl_guard.journal, "get_today_pnl", lambda: 250.0)
    daily_pnl_guard.check({}, 22000)
    assert daily_pnl_guard.is_locked()
    daily_pnl_guard.reset_for_new_session()
    assert not daily_pnl_guard.is_locked()
    # And it can fire again after reset.
    event = daily_pnl_guard.check({}, 22000)
    assert event is not None and event[0] == "TARGET"
