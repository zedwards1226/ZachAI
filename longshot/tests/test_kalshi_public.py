"""Unit tests for kalshi_public.py — runs without network.

Mocks httpx.Client so we don't hit Kalshi during CI, but the test data
matches the real API shape (verified against live `/historical/markets`
on 2026-05-01).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots.kalshi_public import (
    classify_sector,
    market_row_from_api,
    iter_historical_markets,
)


def test_classify_sector_known_prefixes():
    assert classify_sector("KXBTC15M-26MAR011845-45") == "crypto"
    assert classify_sector("KXETH-12345") == "crypto"
    assert classify_sector("KXNBAGAME-26MAY02LALHOU-LAL") == "sports"
    assert classify_sector("KXMLBGAME-26MAY02CLEATH-CLE") == "sports"
    assert classify_sector("KXEPLBTTS-26MAY02ARSFUL") == "sports"
    assert classify_sector("KXHIGH-MIA-26MAY02") == "weather"
    assert classify_sector("KXCPI-26JUN") == "economics"
    assert classify_sector("KXPRES2028-NOM") == "politics"


def test_classify_sector_unknown_falls_back_to_other():
    assert classify_sector("KXMVECROSSCATEGORY-X") == "other"
    assert classify_sector("RANDOMTICKER") == "other"
    assert classify_sector("") == "other"


def test_market_row_normalization():
    """The shape Kalshi returns from /historical/markets, mapped to our table."""
    api_payload = {
        "ticker": "KXBTC15M-26MAR011845-45",
        "event_ticker": "KXBTC15M-26MAR011845",
        "title": "BTC up 15min",
        "open_time": "2026-03-01T23:30:00Z",
        "close_time": "2026-03-01T23:45:00Z",
        "expiration_time": "2026-03-01T23:45:00Z",
        "market_type": "binary",
        "strike_type": "greater",
        "status": "finalized",
        "result": "yes",
        "settlement_value_dollars": "1.0000",
        "yes_ask_dollars": "1.0000",
        "no_ask_dollars": "0.0000",
        "volume_fp": "1234.50",
        "open_interest_fp": "0.00",
    }
    row = market_row_from_api(api_payload)
    assert row["ticker"] == "KXBTC15M-26MAR011845-45"
    assert row["sector"] == "crypto"
    assert row["series_ticker"] == "KXBTC15M"
    assert row["status"] == "finalized"
    assert row["result"] == "yes"
    assert row["settlement_value_dollars"] == 1.0
    assert row["volume_fp"] == 1234.5
    assert "raw_json" in row and "KXBTC15M" in row["raw_json"]
    # Time stamps are preserved through unchanged.
    assert row["open_time"] == "2026-03-01T23:30:00Z"


def test_market_row_handles_missing_optional_fields():
    """Some markets are missing strike fields, etc. Should not blow up."""
    api_payload = {"ticker": "KXNBAGAME-26MAY01LALHOU-LAL"}
    row = market_row_from_api(api_payload)
    assert row["sector"] == "sports"
    assert row["floor_strike"] is None
    assert row["cap_strike"] is None
    assert row["result"] is None
    assert row["volume_fp"] is None


def test_iter_historical_markets_paginates_until_no_cursor():
    """Verify the pagination loop terminates and yields the right rows."""
    page1 = {
        "markets": [{"ticker": f"M{i}", "status": "finalized"} for i in range(3)],
        "cursor": "abc123",
    }
    page2 = {
        "markets": [{"ticker": f"M{i}", "status": "finalized"} for i in range(3, 5)],
        "cursor": None,
    }
    fake_responses = [page1, page2]
    call_count = {"n": 0}

    def fake_get(self, url, params=None):
        idx = call_count["n"]
        call_count["n"] += 1
        resp = MagicMock()
        resp.json.return_value = fake_responses[idx]
        resp.raise_for_status.return_value = None
        return resp

    with patch("bots.kalshi_public.httpx.Client.get", new=fake_get), \
         patch("bots.kalshi_public.time.sleep") as fake_sleep:
        results = list(iter_historical_markets(limit_per_page=3))

    assert [m["ticker"] for m in results] == [f"M{i}" for i in range(5)]
    assert call_count["n"] == 2


def test_iter_historical_markets_respects_max_pages():
    page = {
        "markets": [{"ticker": f"P{i}"} for i in range(2)],
        "cursor": "more",
    }

    def fake_get(self, url, params=None):
        resp = MagicMock()
        resp.json.return_value = page
        resp.raise_for_status.return_value = None
        return resp

    with patch("bots.kalshi_public.httpx.Client.get", new=fake_get), \
         patch("bots.kalshi_public.time.sleep"):
        results = list(iter_historical_markets(max_pages=2, limit_per_page=2))

    assert len(results) == 4  # 2 pages × 2 markets each, then stops
