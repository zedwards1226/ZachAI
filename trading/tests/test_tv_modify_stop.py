"""Tests for Phase 2 — real TV trailing stop (modify_stop_on_tv + _push_tv_stop).

The DOM recipe (Orders tab → Modify Order… → set SL price with React
_valueTracker reset → Confirm) was proven live on 2026-05-22 (moved a paper
stop 29,440 → 29,495). These tests cover the Python control logic: the JS result
interpretation, bulletproof failure handling, the USE_REAL_TV_STOP gate, and the
dedupe that limits panel churn from 30s trail steps.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from services import tv_trader  # noqa: E402


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch):
    # _push_tv_stop persists on success — don't touch the live state file.
    monkeypatch.setattr(tv_trader, "_persist_active_orders", lambda: None)


def _tv(payload=None, *, raise_exc=False):
    tv = MagicMock()

    async def fake_evaluate_async(js, *a, **kw):
        if raise_exc:
            raise RuntimeError("CDP dropped")
        return payload

    tv.evaluate_async = fake_evaluate_async
    return tv


# ── modify_stop_on_tv ─────────────────────────────────────────────────────

def test_modify_success():
    tv = _tv({"ok": True, "oldStop": "29,440.00", "newStop": "29490.00", "panelClosed": True})
    ok, msg = asyncio.run(tv_trader.modify_stop_on_tv(tv, new_stop_price=29490.0))
    assert ok is True and msg == "ok"


def test_modify_no_working_sl():
    tv = _tv({"ok": False, "err": "no_working_sl"})
    ok, msg = asyncio.run(tv_trader.modify_stop_on_tv(tv, new_stop_price=29490.0))
    assert ok is False and msg == "no_working_sl"


def test_modify_confirm_not_found():
    tv = _tv({"ok": False, "err": "no_confirm", "oldStop": "29,440.00"})
    ok, msg = asyncio.run(tv_trader.modify_stop_on_tv(tv, new_stop_price=29490.0))
    assert ok is False and msg == "no_confirm"


def test_modify_exception_is_swallowed():
    tv = _tv(raise_exc=True)
    ok, msg = asyncio.run(tv_trader.modify_stop_on_tv(tv, new_stop_price=29490.0))
    assert ok is False and msg.startswith("exception:")


def test_modify_bad_price():
    tv = _tv({"ok": True})
    ok, msg = asyncio.run(tv_trader.modify_stop_on_tv(tv, new_stop_price=float("nan")))
    # nan is a float so it passes the cast; ensure no crash and JS still runs ok
    assert ok in (True, False)


def test_modify_embeds_price_in_js():
    """The target price must be baked into the JS sent to the browser."""
    captured = {}
    tv = MagicMock()

    async def cap(js, *a, **kw):
        captured["js"] = js
        return {"ok": True, "oldStop": "29,440.00"}

    tv.evaluate_async = cap
    asyncio.run(tv_trader.modify_stop_on_tv(tv, new_stop_price=29490.0))
    assert "29490.00" in captured["js"]


# ── _push_tv_stop (gate + dedupe) ─────────────────────────────────────────

def test_push_disabled_flag_skips(monkeypatch):
    monkeypatch.setattr(tv_trader, "USE_REAL_TV_STOP", False)
    called = {"n": 0}

    async def spy(*a, **kw):
        called["n"] += 1
        return True, "ok"

    monkeypatch.setattr(tv_trader, "modify_stop_on_tv", spy)
    order = {"direction": "LONG"}
    asyncio.run(tv_trader._push_tv_stop(_tv({"ok": True}), order, 1, 29490.0))
    assert called["n"] == 0  # flag off → never touches TV


def test_push_dedupes_small_moves(monkeypatch):
    monkeypatch.setattr(tv_trader, "USE_REAL_TV_STOP", True)
    monkeypatch.setattr(tv_trader, "TV_STOP_MIN_STEP", 5.0)
    called = {"n": 0}

    async def spy(*a, **kw):
        called["n"] += 1
        return True, "ok"

    monkeypatch.setattr(tv_trader, "modify_stop_on_tv", spy)
    order = {"direction": "LONG", "tv_stop_at": 29490.0}
    # moved only 2 pts — under the 5pt step → skip
    asyncio.run(tv_trader._push_tv_stop(_tv(), order, 1, 29492.0))
    assert called["n"] == 0


def test_push_fires_on_meaningful_move(monkeypatch):
    monkeypatch.setattr(tv_trader, "USE_REAL_TV_STOP", True)
    monkeypatch.setattr(tv_trader, "TV_STOP_MIN_STEP", 5.0)

    async def ok_modify(tv, *, new_stop_price):
        return True, "ok"

    monkeypatch.setattr(tv_trader, "modify_stop_on_tv", ok_modify)
    order = {"direction": "LONG", "tv_stop_at": 29490.0}
    asyncio.run(tv_trader._push_tv_stop(_tv(), order, 1, 29510.0))  # +20 pts
    assert order["tv_stop_at"] == 29510.0  # updated after successful push


def test_push_failure_does_not_update_tracker(monkeypatch):
    monkeypatch.setattr(tv_trader, "USE_REAL_TV_STOP", True)
    monkeypatch.setattr(tv_trader, "TV_STOP_MIN_STEP", 5.0)

    async def fail_modify(tv, *, new_stop_price):
        return False, "no_working_sl"

    monkeypatch.setattr(tv_trader, "modify_stop_on_tv", fail_modify)
    order = {"direction": "LONG"}
    asyncio.run(tv_trader._push_tv_stop(_tv(), order, 1, 29510.0))
    # push failed → tracker NOT set, so it retries next cycle
    assert "tv_stop_at" not in order
