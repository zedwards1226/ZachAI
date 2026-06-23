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


def test_place_order_yes_maps_to_bid(monkeypatch):
    # V2 single-book: a YES bet at 42c -> side="bid", price="0.4200" (YES leg).
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    captured = {}
    def cap_post(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"order": {"order_id": "abc", "status": "resting"}}
    monkeypatch.setattr(c, "_post", cap_post)

    c.place_order(ticker="KXHIGHNY-T70", side="yes", contracts=5,
                  price_cents=42, client_order_id="wa-NYC-yes")
    assert captured["path"] == "/portfolio/events/orders"
    b = captured["body"]
    assert b["side"] == "bid"
    assert b["price"] == "0.4200"
    assert b["count"] == "5"
    assert b["time_in_force"] == "good_till_canceled"
    assert "action" not in b and "yes_price" not in b and "no_price" not in b


def test_place_order_no_maps_to_ask_complement(monkeypatch):
    # V2 single-book: a NO bet at 40c == selling YES at 60c.
    # MUST become side="ask", price="0.6000" — inverting this loses real money.
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    captured = {}
    def cap_post(path, body):
        captured["body"] = body
        return {"order": {"order_id": "abc", "status": "resting"}}
    monkeypatch.setattr(c, "_post", cap_post)

    c.place_order(ticker="KXHIGHNY-B87.5", side="no", contracts=7,
                  price_cents=40, client_order_id="wa-NYC-no")
    b = captured["body"]
    assert b["side"] == "ask"
    assert b["price"] == "0.6000"
    assert b["count"] == "7"


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


def test_place_order_v2_resting_response_no_status(monkeypatch):
    # The real V2 create-order body: flat, order_id present, NO "status",
    # remaining_count>0 (fully resting). This is the shape my 6/20 migration
    # mis-parsed and raised on. Must NOT raise; status derived as "resting".
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    monkeypatch.setattr(c, "_post", lambda path, body: {
        "order_id": "c6f012b5", "client_order_id": "wa-WDC-x",
        "fill_count": "0.00", "remaining_count": "5.00", "ts_ms": 1782040841478,
    })
    out = c.place_order(ticker="KXHIGHTDC-B88.5", side="no", contracts=5,
                        price_cents=56, client_order_id="wa-WDC-x")
    assert out["order_id"] == "c6f012b5"
    assert out["status"] == "resting"


def test_place_order_v2_filled_response_no_status(monkeypatch):
    # Flat V2 body with a (partial) fill and no "status".
    monkeypatch.setattr(kalshi_client, "PAPER_MODE", False)
    c = _make_client(ready=True)
    monkeypatch.setattr(c, "_auth_headers", lambda m, p: {})
    monkeypatch.setattr(c, "_post", lambda path, body: {
        "order_id": "bc9883e4", "fill_count": "33.00", "remaining_count": "0.00",
        "average_fill_price": "0.0600",
    })
    out = c.place_order(ticker="KXHIGHNY-T79", side="yes", contracts=33,
                        price_cents=6, client_order_id="wa-NYC-y")
    assert out["order_id"] == "bc9883e4"
    assert out["status"] == "executed"


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
