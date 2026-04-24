"""Regression test: midnight date rollover must not trigger a capital_at_risk RESYNC alert.

For 5 nights in a row pre-fix, the watchdog fired:
    "Guardrail DESYNC: capital_at_risk recorded=$0.00 actual=$XX.XX"
Cause: get_guardrail_state(today) creates a fresh row with DEFAULT 0 values
whenever date.today() flips, stomping the running capital_at_risk counter.
Fix: capital_at_risk is no longer a persisted counter — it's computed live
from SUM(stake_usd) of open trades in scheduler._snapshot_job,
trader.scan_and_trade, and guardrails.guardrail_status.

This test locks in that the live-compute path returns the correct value
when a new-day row is created while open trades exist.
"""
import os
import sys
import tempfile

# Use a fresh temp DB per test run so we don't pollute the live weatheralpha.db.
_tmpdir = tempfile.mkdtemp(prefix="weatheralpha_test_")
os.environ["DATABASE_PATH"] = os.path.join(_tmpdir, "test.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta

from database import (
    init_db, insert_trade, get_guardrail_state, get_open_trades,
)
from guardrails import guardrail_status


def _setup_db():
    init_db()


def _insert_open_trade(stake: float, market_id: str = "KXHIGHNY-T70") -> int:
    return insert_trade(
        city="NYC", market_id=market_id, side="YES",
        contracts=10, price_cents=40, edge=0.10, kelly_frac=0.05,
        stake_usd=stake, paper=True, floor_f=70.0, cap_f=None,
        strike_type="greater",
    )


def test_guardrail_status_recomputes_capital_live_on_new_day():
    _setup_db()
    _insert_open_trade(37.40, market_id="KXHIGHNY-TEST-A")

    # Force creation of a row for "tomorrow" — simulates the midnight flip.
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    state = get_guardrail_state(tomorrow)

    # The raw DB row has capital_at_risk_usd=0 (column default) — that's fine.
    # The bug was relying on that raw value. Post-fix, guardrail_status must
    # report the live open-risk regardless of what the raw row says.
    status = guardrail_status()
    expected = round(sum(t["stake_usd"] for t in get_open_trades()), 2)

    assert status["capital_at_risk_usd"] == expected
    assert expected > 0, "test trade wasn't recorded as open"


def test_snapshot_job_uses_live_open_risk_not_cached_counter():
    """_snapshot_job must compute open_risk live — if it used the cached
    counter it would record $0.00 on any snapshot that happens to run right
    after a new-day row is created but before trader.py writes again."""
    _setup_db()
    _insert_open_trade(19.58, market_id="KXHIGHNY-TEST-B")

    # Force new-day row creation, same pattern as midnight.
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    get_guardrail_state(tomorrow)

    import scheduler
    # Patch snapshot_pnl to capture what _snapshot_job tries to persist.
    captured = {}
    orig = scheduler.snapshot_pnl
    scheduler.snapshot_pnl = lambda capital, open_risk: captured.update(
        capital=capital, open_risk=open_risk
    )
    try:
        scheduler._snapshot_job()
    finally:
        scheduler.snapshot_pnl = orig

    expected = round(sum(t["stake_usd"] for t in get_open_trades()), 2)
    assert captured["open_risk"] == expected
    assert expected > 0


def test_update_guardrail_state_no_longer_writes_capital_column():
    """Belt-and-suspenders: even if a stale caller passes capital_at_risk_usd
    as a kwarg, update_guardrail_state must drop it, so nothing round-trips
    stale values through the DB."""
    _setup_db()
    from database import update_guardrail_state
    # Should not raise even though capital_at_risk_usd is passed.
    update_guardrail_state(
        daily_trades=1, daily_pnl_usd=0.0, consecutive_losses=0,
        halted=0, halt_reason=None, capital_at_risk_usd=999.99,
    )
    # Read back — the cached column is whatever the DB default left behind
    # (0.0), NOT 999.99 from the kwarg.
    state = get_guardrail_state()
    assert state["capital_at_risk_usd"] != 999.99
