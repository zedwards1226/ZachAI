"""Tests for the per-series 429 cooldown in live_scanner.

Verifies the behavior we shipped in commit 6326278 after KXETHD was
hammering Kalshi every scheduler tick all day on 2026-05-11. First 429
parks the series in cooldown; subsequent calls within RATE_LIMIT_COOLDOWN_S
short-circuit and don't hit the wire.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_429_response() -> httpx.Response:
    """Build a real httpx.Response that raise_for_status() will reject with 429."""
    req = httpx.Request("GET", "https://api.elections.kalshi.com/trade-api/v2/markets")
    return httpx.Response(status_code=429, request=req)


def _clear_cooldown_state():
    """Reset the module-level cooldown dict between tests."""
    from bots import live_scanner
    live_scanner._rate_limited_until.clear()


def test_fetch_active_markets_429_sets_cooldown():
    """First 429 should raise httpx.HTTPStatusError (callers handle it)."""
    _clear_cooldown_state()
    from bots import live_scanner

    mock_response = _make_429_response()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=mock_response)

    with patch.object(live_scanner, "_client", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            live_scanner.fetch_active_markets(series_ticker="KXTEST")
        assert excinfo.value.response.status_code == 429


def test_scan_and_trade_429_parks_series_in_cooldown():
    """A 429 inside scan_and_trade should write the cooldown entry."""
    _clear_cooldown_state()
    from bots import live_scanner

    mock_response = _make_429_response()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=mock_response)

    strategy = MagicMock()
    strategy.name = "test_strategy"

    before = datetime.now(timezone.utc)
    with patch.object(live_scanner, "_client", return_value=mock_client):
        result = live_scanner.scan_and_trade(
            strategy, series_ticker="KXTEST", capital_usd=100.0
        )
    after = datetime.now(timezone.utc)

    # Scan returned the all-zero short-circuit dict, no exception escaped
    assert result == {"scanned": 0, "snapshots": 0, "decisions": 0, "approved": 0, "placed": 0}

    # Cooldown entry set for this series ~RATE_LIMIT_COOLDOWN_S in the future
    assert "KXTEST" in live_scanner._rate_limited_until
    cooldown_until = live_scanner._rate_limited_until["KXTEST"]
    expected_min = before + timedelta(seconds=live_scanner.RATE_LIMIT_COOLDOWN_S - 5)
    expected_max = after + timedelta(seconds=live_scanner.RATE_LIMIT_COOLDOWN_S + 5)
    assert expected_min <= cooldown_until <= expected_max, (
        f"cooldown_until {cooldown_until} not in window "
        f"[{expected_min}, {expected_max}]"
    )


def test_second_call_within_cooldown_short_circuits():
    """While a series is in cooldown, fetch_active_markets returns [] WITHOUT
    hitting the HTTP wire. This is the actual bug fix — stops the log spam."""
    _clear_cooldown_state()
    from bots import live_scanner

    # Manually park the series in cooldown
    live_scanner._rate_limited_until["KXTEST"] = (
        datetime.now(timezone.utc) + timedelta(seconds=300)
    )

    # _client() should NEVER be called because the cooldown short-circuits first
    mock_client = MagicMock(side_effect=AssertionError(
        "_client() called during cooldown — short-circuit not working"
    ))
    with patch.object(live_scanner, "_client", mock_client):
        result = live_scanner.fetch_active_markets(series_ticker="KXTEST")

    assert result == []
    mock_client.assert_not_called()


def test_expired_cooldown_re_attempts_fetch():
    """Once cooldown_until is in the past, the next call should hit the wire."""
    _clear_cooldown_state()
    from bots import live_scanner

    # Park cooldown in the PAST so it's expired
    live_scanner._rate_limited_until["KXTEST"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    # Mock a successful 200 response
    req = httpx.Request("GET", "https://api.elections.kalshi.com/trade-api/v2/markets")
    success_response = httpx.Response(
        status_code=200, request=req, json={"markets": []}
    )
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=success_response)

    with patch.object(live_scanner, "_client", return_value=mock_client):
        result = live_scanner.fetch_active_markets(series_ticker="KXTEST")

    # Should have re-attempted (mock_client.get got called) and returned []
    mock_client.get.assert_called_once()
    assert result == []
