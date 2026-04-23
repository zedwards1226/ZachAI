"""Regression test for the 2026-04-23 direction-flip bug.

Scenario that caused a missed trade:
  1. Price closes a 5m bar ABOVE the ORB high → combiner scores the LONG
     break, decides to skip (low score), sets _breakout_processed = True.
  2. On the NEXT closed bar, price has already crashed BELOW the ORB low.
     There was no intermediate bar that closed inside the range.
  3. Before the fix, the guard `if _breakout_processed: return None`
     silently swallowed the short break and no SECOND BREAK signal fired.

The fix treats a direction flip while _breakout_processed is true as
equivalent to "price came back inside then broke the other way" — it
sets _first_break_failed = True and clears _breakout_processed so the
next branch can detect it as a SECOND BREAK.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import combiner  # noqa: E402
from models import CandleDirection, Direction, ORBRange  # noqa: E402


def _install_mocks(monkeypatch):
    """Stub out every external dependency so poll() runs in-process."""
    monkeypatch.setattr(combiner, "_persist_session", lambda: None)

    # Replace _log_signal with a version that still appends to _signals so
    # the tests can assert on what the scoring path decided.
    def fake_log_signal(direction, price, breakdown, size, is_second_break,
                       block_reason=None):
        combiner._signals.append({
            "direction": direction.value,
            "price": round(price, 2),
            "was_second_break": is_second_break,
            "block_reason": block_reason,
        })
    monkeypatch.setattr(combiner, "_log_signal", fake_log_signal)

    fake_telegram = MagicMock()
    fake_telegram.notify_skip = AsyncMock()
    fake_telegram.notify_hard_block = AsyncMock()
    fake_telegram.notify_trade_entry = AsyncMock()
    monkeypatch.setattr(combiner, "telegram", fake_telegram)

    monkeypatch.setattr(combiner, "read_all_states", lambda: {
        "structure": {"vix": 19.2, "rvol": 1.0, "vwap": 27000,
                      "price_location": "above_vwap",
                      "nearest_level": {}},
        "memory": {"morning_bias": "BEARISH_BIAS"},
        "sweep": {},
    })
    monkeypatch.setattr(combiner, "_check_hard_blocks", lambda *a, **kw: None)
    # Force the cascade gate to fail so poll() takes the skip branch and
    # does not try to talk to tv_trader.
    monkeypatch.setattr(combiner, "_check_cascade",
                        lambda *a, **kw: "htf_bias_conflict")

    # journal.get_today_stats is called before the breakout logic.
    fake_journal = MagicMock()
    fake_journal.get_today_stats = MagicMock(
        return_value={"consecutive_losses": 0}
    )
    fake_journal.log_signal_history = MagicMock()
    monkeypatch.setattr(combiner, "journal", fake_journal)

    # Force the session-window guard open — tests run outside market hours.
    monkeypatch.setattr(combiner, "ORB_START_HOUR", 0)
    monkeypatch.setattr(combiner, "ORB_START_MINUTE", 0)
    monkeypatch.setattr(combiner, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(combiner, "SESSION_END_MINUTE", 59)


def _install_tv_client(monkeypatch, close_price):
    """Mock tv_client.get_client() to return an async client whose
    get_ohlcv returns a 2-bar list at close_price.

    combiner uses `last_closed = bars[-2] if len(bars) >= 2 else bars[-1]`
    so the tested price goes at index 0.
    """
    fake_tv = MagicMock()
    fake_tv.get_ohlcv = AsyncMock(return_value=[
        {"close": close_price, "high": close_price, "low": close_price,
         "open": close_price},
        {"close": close_price, "high": close_price, "low": close_price,
         "open": close_price},  # forming bar, unused
    ])

    async def fake_get_client():
        return fake_tv

    monkeypatch.setattr(combiner, "get_client", fake_get_client)


def _seed_orb_session():
    """Put the module into "post-ORB, post-first-break-long" state.

    _session_date MUST match today's ET date string or poll() hits the
    day-reset branch and wipes everything.
    """
    combiner._reset_session()
    combiner._orb = ORBRange(
        high=27067.75,
        low=26997.5,
        range=70.25,
        candle_direction=CandleDirection.BULLISH,
        captured_at="2026-04-23T09:45:00-04:00",
    )
    combiner._session_date = datetime.now(combiner.ET).strftime("%Y-%m-%d")
    combiner._first_break_direction = Direction.LONG
    combiner._first_break_failed = False
    combiner._breakout_processed = True  # long was already scored + skipped
    combiner._signals = []
    combiner._trades_today = 0


def test_direction_flip_after_processed_long_clears_guard(monkeypatch):
    """Bar flips from above-OR (processed LONG) directly to below-OR.

    Before the fix: _breakout_processed stayed True, poll() returned None
    on line "if _breakout_processed: return None" and the short leg was
    never evaluated.

    After the fix: poll() detects LONG→SHORT flip, sets _first_break_failed,
    clears _breakout_processed, falls through to scoring.
    """
    _install_mocks(monkeypatch)
    _seed_orb_session()
    # Next closed bar is below OR low → SHORT direction
    _install_tv_client(monkeypatch, close_price=26990.0)

    asyncio.run(combiner.poll())

    assert combiner._first_break_failed is True, (
        "direction flip must mark first break as failed"
    )
    # After scoring the short leg, the skip branch sets _breakout_processed
    # back to True — which is correct. What matters is that the scoring
    # code path was reached at all.
    assert len(combiner._signals) == 1, (
        "short leg should have been scored and logged as one signal, "
        f"got {len(combiner._signals)} signals"
    )
    signal = combiner._signals[0]
    assert signal["direction"] == "SHORT", (
        f"expected SHORT signal from reversal, got {signal['direction']}"
    )
    assert signal["was_second_break"] is True, (
        "reversal from failed long MUST be flagged as second break (+2 bonus)"
    )


def test_no_flip_when_same_direction_still_guarded(monkeypatch):
    """Control case: if the next bar is ALSO above OR (same direction),
    the guard should still hold and no new signal should fire.
    """
    _install_mocks(monkeypatch)
    _seed_orb_session()
    # Still above OR — same direction as the processed break
    _install_tv_client(monkeypatch, close_price=27080.0)

    asyncio.run(combiner.poll())

    assert combiner._breakout_processed is True, (
        "same-direction continuation must NOT clear the guard"
    )
    assert len(combiner._signals) == 0, (
        "no new signal should fire while price stays outside on the "
        "same side as the already-processed break"
    )


def test_inside_range_still_resets_guard_normally(monkeypatch):
    """Control case: the original reset path (price returns inside OR)
    must still work.
    """
    _install_mocks(monkeypatch)
    _seed_orb_session()
    # Inside OR — between low 26997.5 and high 27067.75
    _install_tv_client(monkeypatch, close_price=27030.0)

    asyncio.run(combiner.poll())

    assert combiner._breakout_processed is False, (
        "price closing back inside OR must reset the guard"
    )
    assert combiner._first_break_failed is True, (
        "return-to-range after first break must mark it failed"
    )
