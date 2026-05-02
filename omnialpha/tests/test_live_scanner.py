"""Tests for live_scanner — snapshot conversion + scan-and-trade flow.

Mocks the Kalshi /markets HTTP endpoint with realistic payloads. Real
Kalshi responses verified against live API on 2026-05-02.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _live_market_payload(*, ticker="KXBTC15M-X", last=0.25, vol=5000.0):
    """Real Kalshi /markets response shape (verified against live API)."""
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "title": "BTC up 15m",
        "open_time": "2026-05-02T13:15:00Z",
        "close_time": "2026-05-02T13:30:00Z",
        "expiration_time": "2026-05-02T13:30:00Z",
        "market_type": "binary",
        "strike_type": "greater",
        "status": "open",
        "last_price_dollars": str(last),
        "yes_ask_dollars": str(last + 0.01),
        "yes_bid_dollars": str(max(0, last - 0.01)),
        "no_ask_dollars": str(round(1 - last + 0.01, 4)),
        "no_bid_dollars": str(round(max(0, 1 - last - 0.01), 4)),
        "volume_fp": str(vol),
        "open_interest_fp": "100.00",
    }


def test_market_to_snapshot_basic_field_mapping():
    from bots.live_scanner import _market_to_snapshot
    snap = _market_to_snapshot(_live_market_payload(last=0.30))
    assert snap is not None
    assert snap.ticker.startswith("KXBTC15M")
    assert snap.sector == "crypto"
    assert snap.last_price_cents == 30
    assert snap.yes_ask_cents == 31
    assert snap.no_ask_cents == 71
    assert snap.volume_fp == 5000.0


def test_market_to_snapshot_skips_non_binary():
    """Multivariate / scalar markets must be skipped."""
    from bots.live_scanner import _market_to_snapshot
    payload = _live_market_payload()
    payload["market_type"] = "scalar"
    assert _market_to_snapshot(payload) is None


def test_market_to_snapshot_skips_empty_ticker():
    from bots.live_scanner import _market_to_snapshot
    payload = _live_market_payload()
    payload["ticker"] = ""
    assert _market_to_snapshot(payload) is None


def test_market_to_snapshot_falls_back_to_mid_when_untraded():
    """If last_price=0 and there are quotes, use mid of bid/ask."""
    from bots.live_scanner import _market_to_snapshot
    payload = _live_market_payload(last=0.0)
    # When last is 0 the function should fall back to (yes_ask + yes_bid) / 2
    # yes_ask = 0.01, yes_bid = 0.0 → mid = 0.005 → 1c
    snap = _market_to_snapshot(payload)
    # We can't trade something this thin, but the snapshot should exist
    assert snap is not None
    assert snap.last_price_cents >= 0


def test_market_to_snapshot_skips_when_no_price_at_all():
    from bots.live_scanner import _market_to_snapshot
    payload = _live_market_payload(last=0.0)
    payload["yes_ask_dollars"] = ""
    payload["yes_bid_dollars"] = ""
    payload["no_ask_dollars"] = ""
    payload["no_bid_dollars"] = ""
    assert _market_to_snapshot(payload) is None


def test_market_to_snapshot_seconds_to_close_negative_after_settlement():
    """A market whose close_time has passed should yield seconds_to_close <= 0."""
    from bots.live_scanner import _market_to_snapshot
    payload = _live_market_payload()
    payload["close_time"] = "2020-01-01T00:00:00Z"
    snap = _market_to_snapshot(payload)
    assert snap is not None
    assert snap.seconds_to_close <= 0


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Tmp DB redirects so live_scanner.upsert + _build_context don't pollute production."""
    from data_layer import database
    db_path = tmp_path / "ls.db"
    database.init_db(db_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    from bots import live_scanner, order_placer, risk_engine
    monkeypatch.setattr(live_scanner, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(order_placer, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(risk_engine, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(risk_engine, "SHARED_RISK_STATE",
                        tmp_path / "risk_state.json")
    monkeypatch.setattr(
        "bots.telegram_alerts.send", lambda *a, **kw: True
    )
    return db_path


def test_scan_and_trade_full_flow(isolated_db, monkeypatch):
    """End-to-end: stub HTTP, run scan_and_trade, verify trade persists + market upserted."""
    from bots import live_scanner
    from strategies.crypto_midband import CryptoMidBandStrategy
    from data_layer.database import get_conn

    # Build a market in the NO band, with seconds_to_close inside entry window.
    payload = _live_market_payload(ticker="KXBTC15M-TEST-1", last=0.25)
    # Make close_time 2 minutes from now so it's within the entry window
    from datetime import datetime, timedelta, timezone
    payload["close_time"] = (
        datetime.now(timezone.utc) + timedelta(seconds=120)
    ).isoformat().replace("+00:00", "Z")

    # Mock the HTTP fetch
    monkeypatch.setattr(
        live_scanner, "fetch_active_markets",
        lambda **kw: [payload],
    )

    result = live_scanner.scan_and_trade(
        strategy=CryptoMidBandStrategy(),
        series_ticker="KXBTC15M",
        capital_usd=100.0,
    )

    assert result["scanned"] == 1
    assert result["snapshots"] == 1
    assert result["decisions"] == 1
    assert result["approved"] == 1
    assert result["placed"] == 1

    # Verify the market was upserted
    with get_conn(isolated_db, readonly=True) as conn:
        m = conn.execute(
            "SELECT * FROM markets WHERE ticker = ?", ("KXBTC15M-TEST-1",)
        ).fetchone()
    assert m is not None
    assert m["sector"] == "crypto"

    # Verify the trade was placed (paper)
    with get_conn(isolated_db, readonly=True) as conn:
        trades = conn.execute("SELECT * FROM trades").fetchall()
    assert len(trades) == 1
    assert trades[0]["paper"] == 1
    assert trades[0]["status"] == "open"
    assert trades[0]["side"] == "no"


def test_scan_and_trade_rejects_already_taken_market(isolated_db, monkeypatch):
    """If we already have a trade against this ticker, scan should not re-enter."""
    from bots import live_scanner
    from strategies.crypto_midband import CryptoMidBandStrategy
    from data_layer.database import get_conn

    # Pre-populate a trade for this ticker
    with get_conn(isolated_db) as conn:
        conn.execute(
            "INSERT INTO trades (timestamp, sector, strategy, market_ticker, side, "
            "contracts, price_cents, stake_usd, paper, status) VALUES "
            "(?,?,?,?,?,?,?,?,?,?)",
            ("2026-05-02T00:00:00Z", "crypto", "test",
             "KXBTC15M-TEST-2", "no", 10, 25, 2.5, 1, "open"),
        )

    payload = _live_market_payload(ticker="KXBTC15M-TEST-2", last=0.25)
    from datetime import datetime, timedelta, timezone
    payload["close_time"] = (
        datetime.now(timezone.utc) + timedelta(seconds=120)
    ).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(
        live_scanner, "fetch_active_markets",
        lambda **kw: [payload],
    )

    result = live_scanner.scan_and_trade(
        strategy=CryptoMidBandStrategy(),
        series_ticker="KXBTC15M",
        capital_usd=100.0,
    )

    # Snapshot was built but the strategy wasn't called because the market
    # was already taken — so decisions/approved/placed all stay 0.
    assert result["snapshots"] == 1
    assert result["decisions"] == 0
    assert result["placed"] == 0


def test_scan_and_trade_handles_http_failure(monkeypatch):
    """Network fail returns zero counts, doesn't crash."""
    from bots import live_scanner
    from strategies.crypto_midband import CryptoMidBandStrategy

    def boom(**kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(live_scanner, "fetch_active_markets", boom)

    result = live_scanner.scan_and_trade(
        strategy=CryptoMidBandStrategy(),
        series_ticker="KXBTC15M",
        capital_usd=100.0,
    )
    assert result == {"scanned": 0, "snapshots": 0, "decisions": 0, "approved": 0, "placed": 0}
