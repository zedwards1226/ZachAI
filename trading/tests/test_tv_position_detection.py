"""Regression tests for the recurring FALSE phantom-position bug.

Bug recap (2026-05-19, recurred several times since early May):
On every reboot the bot reported a phantom open MNQ position when the account
was actually FLAT. Root cause: `tv_get_positions` inferred "position open" from
`available_funds < 90% of a $5000 baseline`. That baseline is an in-memory
global that resets to the hardcoded STARTING_CAPITAL ($5000) on every restart.
Once cumulative *realized* losses pushed the real paper account below $4500
(it sat at $4250.16 after −$749.84 realized), the heuristic was permanently
true after any reboot → fabricated a phantom every time, tripping the circuit
breaker and blocking all trading. Worse, when the broker panel wasn't the
visible tab, the whole-body innerText scrape matched Strategy-Tester margin
numbers and flapped.

The fix: read the broker's own **Account margin** figure (capital consumed by
OPEN positions — exactly 0.00 when flat, independent of account balance).
Available funds is reported for the dashboard but no longer decides position
state.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import tv_trader  # noqa: E402


def _tv_returning(payload):
    """Fake TV client whose evaluate_async() returns the given account-manager dict.
    tv_get_positions uses an async IIFE → evaluate_async (awaitPromise=True)."""
    tv = MagicMock()

    async def fake_evaluate_async(js, *a, **kw):
        return payload

    tv.evaluate_async = fake_evaluate_async
    return tv


def test_flat_when_margin_zero_despite_low_funds():
    """THE regression: account at $4250 from realized losses, NO position.
    Account margin is 0.00 → must report FLAT, not a phantom."""
    tv = _tv_returning({
        "panel": True, "acctMargin": 0.0, "avail": 4250.16,
        "unreal": 0.0, "balance": 4250.16,
    })
    res = asyncio.run(tv_trader.tv_get_positions(tv))
    assert res["has_position"] is False
    assert res["count"] == 0
    assert res["available_funds"] == 4250.16


def test_open_when_margin_positive():
    """One MNQ open consumes ~$2720 of account margin → position detected."""
    tv = _tv_returning({
        "panel": True, "acctMargin": 2720.0, "avail": 1530.16,
        "unreal": -12.0, "balance": 4250.16,
    })
    res = asyncio.run(tv_trader.tv_get_positions(tv))
    assert res["has_position"] is True
    assert res["count"] == 1
    assert res["available_funds"] == 1530.16


def test_two_contracts_counted_from_margin():
    tv = _tv_returning({
        "panel": True, "acctMargin": 5440.0, "avail": 1000.0,
        "unreal": 0.0, "balance": 6440.0,
    })
    res = asyncio.run(tv_trader.tv_get_positions(tv))
    assert res["has_position"] is True
    assert res["count"] == 2


def test_unknown_when_panel_closed():
    """Broker panel not in DOM and couldn't be opened → unknown, NOT a phantom.
    Reconcile must skip rather than fabricate drift."""
    tv = _tv_returning({"panel": False})
    res = asyncio.run(tv_trader.tv_get_positions(tv))
    assert res["has_position"] is False
    assert res["count"] == 0
    assert res["signal"] == "panel_unavailable"


def test_unknown_when_margin_unreadable():
    """Panel open but margin figure couldn't be parsed → don't guess a phantom."""
    tv = _tv_returning({"panel": True, "acctMargin": None, "avail": 4250.16})
    res = asyncio.run(tv_trader.tv_get_positions(tv))
    assert res["has_position"] is False
    assert res["signal"] == "margin_unreadable"


def test_reconcile_stays_in_sync_when_flat_with_low_funds():
    """End-to-end: low available funds + zero account margin + bot flat
    must reconcile as in-sync (no phantom, no circuit breaker)."""
    tv_trader._active_orders.clear()
    tv = _tv_returning({
        "panel": True, "acctMargin": 0.0, "avail": 4250.16,
        "unreal": 0.0, "balance": 4250.16,
    })

    import services.tv_trader as t
    orig_get_client = t.get_client

    async def fake_get_client():
        return tv

    t.get_client = fake_get_client
    try:
        res = asyncio.run(t.reconcile_with_tv())
    finally:
        t.get_client = orig_get_client

    assert res["in_sync"] is True
    assert res["drift_type"] == "none"
    assert res["tv_count"] == 0
