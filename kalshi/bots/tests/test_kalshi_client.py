"""Tests for Kalshi client order placement + reconciliation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import kalshi_client
from kalshi_client import KalshiClient


def _make_client(ready: bool = True) -> KalshiClient:
    c = KalshiClient()
    c._ready = ready
    return c


def test_place_order_paper_mode_returns_synthetic(monkeypatch):
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", True)
    c = _make_client(ready=False)

    # Should NOT call _post
    def fail_post(*a, **kw):
        raise AssertionError("PAPER_MODE should short-circuit before _post")
    monkeypatch.setattr(c, "_post", fail_post)

    out = c.place_order(ticker="KXHIGHNY-T70", side="yes", contracts=5,
                        price_cents=42, client_order_id="wa-NYC-test-1")
    assert out["paper"] is True
    assert out["status"] == "paper_filled"
    assert out["client_order_id"] == "wa-NYC-test-1"
    assert out["contracts"] == 5


def test_place_order_accepts_valid_response(monkeypatch):
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)

    def fake_sign(*a, **kw): return "sig"
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    monkeypatch.setattr(c, "_post",
        lambda path, body: {"order": {"order_id": "abc123", "status": "resting"}})

    out = c.place_order(ticker="KXHIGHNY-T70", side="yes", contracts=5,
                        price_cents=42, client_order_id="wa-NYC-test-2")
    assert out["order_id"] == "abc123"
    assert out["status"] == "resting"


def test_place_order_accepts_flat_response(monkeypatch):
    # Some Kalshi responses may not nest under "order"
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    monkeypatch.setattr(c, "_post",
        lambda path, body: {"order_id": "flat123", "status": "executed"})

    out = c.place_order(ticker="KXHIGHNY-T70", side="yes", contracts=5,
                        price_cents=42, client_order_id="wa-NYC-test-3")
    assert out["order_id"] == "flat123"


def test_place_order_rejects_invalid_response(monkeypatch):
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    monkeypatch.setattr(c, "_post",
        lambda path, body: {"error": "rate_limited"})

    with pytest.raises(RuntimeError) as exc_info:
        c.place_order(ticker="KXHIGHNY-T70", side="yes", contracts=5,
                      price_cents=42, client_order_id="wa-NYC-test-4")
    assert "Kalshi rejected order" in str(exc_info.value)


def test_place_order_unauth_raises(monkeypatch):
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=False)
    with pytest.raises(RuntimeError):
        c.place_order(ticker="KXHIGHNY-T70", side="yes", contracts=5,
                      price_cents=42)


def test_get_orders_filters_by_client_order_id(monkeypatch):
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    monkeypatch.setattr(c, "_get", lambda path, params=None: {"orders": [
        {"order_id": "a", "client_order_id": "wa-NYC-1"},
        {"order_id": "b", "client_order_id": "wa-MIA-2"},
        {"order_id": "c", "client_order_id": "wa-NYC-1"},
    ]})
    out = c.get_orders(client_order_id="wa-NYC-1")
    assert len(out) == 2
    assert all(o["client_order_id"] == "wa-NYC-1" for o in out)


def test_get_orders_returns_empty_when_not_ready():
    c = _make_client(ready=False)
    assert c.get_orders(client_order_id="wa-NYC-1") == []


def test_get_orders_swallows_api_errors(monkeypatch):
    c = _make_client(ready=True)
    def fail_get(*a, **kw): raise RuntimeError("boom")
    monkeypatch.setattr(c, "_get", fail_get)
    # Should not raise — reconciliation path must be resilient
    assert c.get_orders(client_order_id="wa-NYC-1") == []
