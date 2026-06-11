"""Regression test for the 2026-06-10 skip-alert Telegram storm.

On CPI day 2026-06-10 the opening range was 318 points wide, so every
breakout's stop exceeded the per-trade risk cap and was (correctly) skipped.
But the skip *alert* had no dedup: price re-broke the range ~480 times and
each re-break resent an identical "stop too wide" Telegram message.

The fix dedups skip notifications to once per reason per session
(`_notify_skip_once` + `_notified_skip_keys`, reset in `_reset_session`).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import combiner  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_same_reason_notifies_once(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(combiner.telegram, "notify_skip", mock)
    combiner._notified_skip_keys.clear()

    for _ in range(50):
        _run(combiner._notify_skip_once("LONG", 5, "short_against_bullish_bias"))

    assert mock.call_count == 1


def test_risk_too_wide_dedups_across_dollar_amounts(monkeypatch):
    # The $ amount varies poll-to-poll; the dedup key must ignore it.
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(combiner.telegram, "notify_skip", mock)
    combiner._notified_skip_keys.clear()

    _run(combiner._notify_skip_once("SHORT", 4, "risk_too_wide:$694>400"))
    _run(combiner._notify_skip_once("SHORT", 4, "risk_too_wide:$702>400"))
    _run(combiner._notify_skip_once("LONG", 6, "risk_too_wide:$510>400"))

    assert mock.call_count == 1


def test_distinct_reasons_each_notify_once(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(combiner.telegram, "notify_skip", mock)
    combiner._notified_skip_keys.clear()

    _run(combiner._notify_skip_once("LONG", 5, "first_break_skipped_require_second_break"))
    _run(combiner._notify_skip_once("SHORT", 4, "risk_too_wide:$694>400"))
    _run(combiner._notify_skip_once("LONG", 5, "first_break_skipped_require_second_break"))

    assert mock.call_count == 2


def test_session_reset_reenables_one_alert(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(combiner.telegram, "notify_skip", mock)
    combiner._notified_skip_keys.clear()

    _run(combiner._notify_skip_once("SHORT", 4, "risk_too_wide:$694>400"))
    assert mock.call_count == 1
    # New trading day → the dedup set clears → one alert allowed again.
    combiner._notified_skip_keys.clear()
    _run(combiner._notify_skip_once("SHORT", 4, "risk_too_wide:$694>400"))
    assert mock.call_count == 2


def test_telegram_failure_never_raises(monkeypatch):
    mock = AsyncMock(side_effect=RuntimeError("telegram down"))
    monkeypatch.setattr(combiner.telegram, "notify_skip", mock)
    combiner._notified_skip_keys.clear()
    # Must swallow the exception — a Telegram failure can't break the poll.
    _run(combiner._notify_skip_once("LONG", 5, "risk_too_wide:$694>400"))
