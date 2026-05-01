"""Recovery-path regression tests for the 2026-05-01 09:00 phantom-fill bug.

Bug recap: ORB submitted a market Buy at 09:00:07. The 4s `_check_order_acceptance`
timed out at 09:00:11 because TV took ~10s to surface the position rendering. The
trade was marked FAILED_PLACEMENT and orphaned. The reconcile loop then alerted
once per minute for 5.5 hours until Zach manually closed the position.

What these tests cover:

1. `_check_order_acceptance` confirms a fill via margin drop even when the
   "Market order executed" toast never appears within the timeout (this is the
   exact code path that should have caught today's bug).

2. `_check_order_acceptance` confirms a fill via position-visible probe when
   the position rows render before the toast.

3. `_check_order_acceptance` correctly returns rejected_funds on the rejection
   toast (no false adoption).

4. `_check_order_acceptance` returns no_position_after_submit when truly nothing
   happened — preserves the existing failure path for the no-fill case.

5. `_record_failed_attempt` + `_claim_recent_failed_attempt` round-trip the
   intended SL/TP.

6. `_claim_recent_failed_attempt` returns None when the TTL has elapsed (so
   reconcile won't adopt a position from a stale attempt that isn't ours).

7. `reconcile_with_tv` ADOPTS a phantom when there's a recent failed attempt
   in the buffer — restores active_orders, reopens the journal row, sends a
   Telegram message, and clears the circuit breaker.

8. `reconcile_with_tv` falls back to halt+alert when there's no recent attempt
   to claim (manual entry, prior-session leftover) — preserves the existing
   safety guarantee.

9. `reconcile_with_tv` sends a single RESOLVED ping and resets the circuit
   breaker when drift clears in a later cycle (no more 1-alert-per-minute spam).
"""
from __future__ import annotations

import asyncio
import sys
import time as _time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from services import tv_trader  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Fixture helpers
# ────────────────────────────────────────────────────────────────────


def _reset_module_state():
    """Wipe global module state so tests don't leak into each other."""
    tv_trader._active_orders.clear()
    tv_trader._recent_failed_attempts.clear()
    tv_trader._FAILURE_WINDOW.clear()
    tv_trader._CIRCUIT_OPEN_UNTIL = 0.0
    tv_trader._RECONCILE_LAST_DRIFT_ALERT_TS = 0.0
    tv_trader._RECONCILE_DRIFT_ACTIVE = False


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    _reset_module_state()
    # Stub out telegram so no real messages get sent during tests.
    fake_telegram = MagicMock()
    fake_telegram.send = AsyncMock(return_value=True)
    fake_telegram.notify_hard_block = AsyncMock(return_value=True)
    monkeypatch.setattr(tv_trader, "telegram", fake_telegram)
    yield fake_telegram
    _reset_module_state()


def _make_tv_with_steps(steps):
    """Build a fake TV client that returns each step's snapshot/positions in order.

    `steps` is a list of dicts:
      {"toast": "<toast text>", "positions": {"has_position": bool, "available_funds": float}}
    Each call to _capture_toast_snapshot consumes one toast value; each call to
    tv_get_positions consumes one positions value. Steps are returned as long as
    they last; after exhaustion, the last step repeats.
    """
    state = {"i": 0}

    def _next():
        idx = min(state["i"], len(steps) - 1)
        state["i"] += 1
        return steps[idx]

    tv = MagicMock()

    async def fake_evaluate(js):
        # _capture_toast_snapshot returns a string; tv_get_positions returns a
        # dict with hasAvgFill+avail. Pick which one based on the JS contents.
        s = _next()
        if "toast" in js:
            return s["toast"]
        # tv_get_positions JS
        return {
            "hasAvgFill": s["positions"].get("has_position", False),
            "avail": s["positions"].get("available_funds"),
        }

    tv.evaluate = fake_evaluate
    return tv


# ────────────────────────────────────────────────────────────────────
# Test 1 — margin-drop confirmation closes today's bug
# ────────────────────────────────────────────────────────────────────


def test_acceptance_confirmed_via_margin_drop(monkeypatch):
    """When TV surfaces no toast and no position rows but available funds
    drop by ≥ one MNQ contract margin, the order is treated as filled.
    """
    # Bypass the 0.5s sleep between polls to keep the test fast.
    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(side_effect=[
        # First poll: no position visible, avail still full
        {"has_position": False, "available_funds": 5357.0, "signal": "full_avail_funds"},
        # Second poll: still no rows, but avail dropped by $2,860 (one MNQ)
        {"has_position": False, "available_funds": 2497.0, "signal": "low_avail_funds"},
    ]))
    monkeypatch.setattr(tv_trader, "_capture_toast_snapshot", AsyncMock(return_value=""))

    async def _run():
        return await tv_trader._check_order_acceptance(
            tv=MagicMock(),
            before_snapshot="",
            before_avail=5357.0,
            timeout=2.0,
        )

    accepted, reason = asyncio.run(_run())
    assert accepted is True
    assert reason == "margin_drop_confirmed"


# ────────────────────────────────────────────────────────────────────
# Test 2 — position-visible probe also closes the bug
# ────────────────────────────────────────────────────────────────────


def test_acceptance_confirmed_via_position_visible(monkeypatch):
    """When TV renders the position rows mid-poll, acceptance returns True
    immediately even without a toast diff."""
    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(side_effect=[
        {"has_position": False, "available_funds": 5357.0, "signal": "full_avail_funds"},
        {"has_position": True, "available_funds": 2497.0, "signal": "avg_fill_price_visible"},
    ]))
    monkeypatch.setattr(tv_trader, "_capture_toast_snapshot", AsyncMock(return_value=""))

    accepted, reason = asyncio.run(tv_trader._check_order_acceptance(
        tv=MagicMock(),
        before_snapshot="",
        before_avail=5357.0,
        timeout=2.0,
    ))
    assert accepted is True
    assert reason == "position_visible"


# ────────────────────────────────────────────────────────────────────
# Test 3 — explicit rejection toast still wins
# ────────────────────────────────────────────────────────────────────


def test_acceptance_returns_rejected_funds_on_toast(monkeypatch):
    """Toast saying funds-rejected must beat any other signal."""
    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(return_value={
        "has_position": False, "available_funds": 5357.0, "signal": "full_avail_funds",
    }))
    monkeypatch.setattr(tv_trader, "_capture_toast_snapshot", AsyncMock(
        return_value="|Market order rejected: Not enough funds in account",
    ))

    accepted, reason = asyncio.run(tv_trader._check_order_acceptance(
        tv=MagicMock(),
        before_snapshot="",
        before_avail=5357.0,
        timeout=1.0,
    ))
    assert accepted is False
    assert reason == "rejected_funds"


# ────────────────────────────────────────────────────────────────────
# Test 4 — full timeout with no signal still returns no_position_after_submit
# ────────────────────────────────────────────────────────────────────


def test_acceptance_times_out_with_no_signal(monkeypatch):
    """When nothing happens, the existing failure path is preserved."""
    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(return_value={
        "has_position": False, "available_funds": 5357.0, "signal": "full_avail_funds",
    }))
    monkeypatch.setattr(tv_trader, "_capture_toast_snapshot", AsyncMock(return_value=""))

    accepted, reason = asyncio.run(tv_trader._check_order_acceptance(
        tv=MagicMock(),
        before_snapshot="",
        before_avail=5357.0,
        timeout=1.0,
    ))
    assert accepted is False
    assert reason == "no_position_after_submit"


# ────────────────────────────────────────────────────────────────────
# Test 5 — failed-attempt buffer round-trips intended SL/TP
# ────────────────────────────────────────────────────────────────────


def test_failed_attempt_buffer_roundtrip():
    tv_trader._record_failed_attempt(
        trade_id=42, direction="LONG",
        entry_price=27871.25, stop_price=27795.00,
        target_1=27921.50, target_2=27975.00,
        reason="tv_no_position_after_submit",
    )
    claimed = tv_trader._claim_recent_failed_attempt()
    assert claimed is not None
    assert claimed["trade_id"] == 42
    assert claimed["direction"] == "LONG"
    assert claimed["entry"] == 27871.25
    assert claimed["stop"] == 27795.00
    assert claimed["target_1"] == 27921.50
    assert claimed["target_2"] == 27975.00
    assert claimed["reason"] == "tv_no_position_after_submit"
    # Buffer is consumed
    assert tv_trader._claim_recent_failed_attempt() is None


# ────────────────────────────────────────────────────────────────────
# Test 6 — TTL pruning prevents adopting unrelated positions
# ────────────────────────────────────────────────────────────────────


def test_failed_attempt_buffer_prunes_after_ttl():
    tv_trader._record_failed_attempt(
        trade_id=42, direction="LONG", entry_price=1, stop_price=1,
        target_1=1, target_2=1, reason="x",
    )
    # Manually backdate the timestamp past the TTL.
    tv_trader._recent_failed_attempts[42]["ts"] = _time.monotonic() - (
        tv_trader._FAILED_ATTEMPT_TTL_S + 1
    )
    assert tv_trader._claim_recent_failed_attempt() is None
    assert 42 not in tv_trader._recent_failed_attempts


# ────────────────────────────────────────────────────────────────────
# Test 7 — phantom + recent attempt → adoption
# ────────────────────────────────────────────────────────────────────


def test_reconcile_adopts_phantom_when_recent_attempt_exists(monkeypatch, _isolate):
    """The exact 2026-05-01 09:00 scenario: trade submitted, acceptance check
    reported no_position_after_submit, reconcile 60s later sees the position.
    Bot should ADOPT instead of halting."""
    fake_telegram = _isolate

    # Recent failed attempt sitting in the buffer (just like the failure path
    # would leave it after place_bracket_order timed out).
    tv_trader._record_failed_attempt(
        trade_id=10, direction="LONG",
        entry_price=27871.25, stop_price=27795.00,
        target_1=27921.50, target_2=27975.00,
        reason="tv_no_position_after_submit",
    )

    monkeypatch.setattr(tv_trader, "get_client", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(return_value={
        "count": 1, "has_position": True,
        "available_funds": 2497.88, "signal": "low_avail_funds",
    }))
    monkeypatch.setattr(tv_trader, "read_state", lambda *a, **kw: {"vix": 16.77})

    fake_journal = MagicMock()
    fake_journal.reopen_as_adopted = MagicMock(return_value=True)
    monkeypatch.setattr(tv_trader, "journal", fake_journal)

    # Pre-condition: circuit breaker is open from prior failures.
    tv_trader._CIRCUIT_OPEN_UNTIL = _time.monotonic() + 60

    result = asyncio.run(tv_trader.reconcile_with_tv())

    assert result["drift_type"] == "adopted"
    assert result["action_taken"] == "adopted_trade_10"
    # Adopted trade is now active and managed.
    assert 10 in tv_trader._active_orders
    order = tv_trader._active_orders[10]
    assert order["direction"] == "LONG"
    assert order["entry"] == 27871.25
    assert order["stop"] == 27795.00
    assert order["target_1"] == 27921.50
    assert order["target_2"] == 27975.00
    assert order["adopted"] is True
    assert order["vix_at_open"] == 16.77
    # Journal row was reopened (so learning agent counts the trade).
    fake_journal.reopen_as_adopted.assert_called_once()
    # Circuit breaker was reset — combiner can take new entries again.
    assert tv_trader._CIRCUIT_OPEN_UNTIL == 0.0
    assert len(tv_trader._FAILURE_WINDOW) == 0
    # Telegram informed user of the adoption.
    fake_telegram.send.assert_called_once()
    msg = fake_telegram.send.call_args[0][0]
    assert "Adopted phantom" in msg
    assert "trade 10" in msg
    # Buffer was consumed.
    assert 10 not in tv_trader._recent_failed_attempts


# ────────────────────────────────────────────────────────────────────
# Test 8 — phantom WITHOUT recent attempt → halt+alert (existing safety)
# ────────────────────────────────────────────────────────────────────


def test_reconcile_halts_phantom_with_no_recent_attempt(monkeypatch, _isolate):
    """Manual entry / prior-session leftover: no recent submission to claim,
    so the original safety path (halt + alert + circuit breaker) is preserved."""
    fake_telegram = _isolate
    monkeypatch.setattr(tv_trader, "get_client", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(return_value={
        "count": 1, "has_position": True,
        "available_funds": 2497.88, "signal": "low_avail_funds",
    }))

    result = asyncio.run(tv_trader.reconcile_with_tv())

    assert result["drift_type"] == "phantom_position"
    assert result["action_taken"] == "circuit_breaker_tripped_alerted"
    # active_orders stays empty — no auto-claim of unknown positions.
    assert len(tv_trader._active_orders) == 0
    # Circuit breaker is open.
    assert tv_trader._CIRCUIT_OPEN_UNTIL > _time.monotonic()
    # Hard-block telegram fired exactly once.
    assert fake_telegram.notify_hard_block.call_count == 1


# ────────────────────────────────────────────────────────────────────
# Test 9 — RESOLVED ping fires once when drift clears + CB resets
# ────────────────────────────────────────────────────────────────────


def test_reconcile_sends_resolved_when_drift_clears(monkeypatch, _isolate):
    fake_telegram = _isolate
    monkeypatch.setattr(tv_trader, "get_client", AsyncMock(return_value=MagicMock()))

    # Simulate the scenario where drift was active and now TV is flat again.
    tv_trader._RECONCILE_DRIFT_ACTIVE = True
    tv_trader._CIRCUIT_OPEN_UNTIL = _time.monotonic() + 60
    tv_trader._FAILURE_WINDOW.append({"type": "unknown", "reason": "x", "ts": _time.monotonic()})

    monkeypatch.setattr(tv_trader, "tv_get_positions", AsyncMock(return_value={
        "count": 0, "has_position": False,
        "available_funds": 5357.92, "signal": "full_avail_funds",
    }))

    result = asyncio.run(tv_trader.reconcile_with_tv())
    assert result["in_sync"] is True
    assert tv_trader._RECONCILE_DRIFT_ACTIVE is False
    assert tv_trader._CIRCUIT_OPEN_UNTIL == 0.0
    assert len(tv_trader._FAILURE_WINDOW) == 0
    # Exactly one RESOLVED ping (not 100/min).
    assert fake_telegram.send.call_count == 1
    msg = fake_telegram.send.call_args[0][0]
    assert "RESOLVED" in msg
