"""Tests for the order placement + reconciliation path in trader.py.
Covers the phantom-position bug: if place_order raised mid-flight, the order
may still have landed on Kalshi and we must insert a trade row to match."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import trader


class FakeClient:
    """Minimal Kalshi client stub. Only implements what reconcile needs."""
    def __init__(self, landed_orders=None, raise_on_probe=False):
        self._landed = landed_orders or []
        self._raise_on_probe = raise_on_probe
        self.probe_calls = []
    def get_orders(self, client_order_id=None, ticker=None):
        self.probe_calls.append(client_order_id)
        if self._raise_on_probe:
            raise RuntimeError("probe network error")
        if client_order_id:
            return [o for o in self._landed if o.get("client_order_id") == client_order_id]
        return list(self._landed)


def _base_insert_kwargs():
    return dict(
        city="NYC", market_id="KXHIGHNY-26APR22-T70", side="YES",
        contracts=5, price_cents=42, edge=0.10, kelly_frac=0.05,
        stake_usd=2.10, paper=False, floor_f=70.0, cap_f=None,
        strike_type="greater",
    )


def test_reconcile_no_landing_returns_none(monkeypatch):
    """place_order raised AND order never reached Kalshi → no trade inserted."""
    monkeypatch.setattr(trader, "PAPER_MODE", False)

    inserted = []
    monkeypatch.setattr(trader, "insert_trade",
        lambda **kw: inserted.append(kw) or 99)
    monkeypatch.setattr(trader, "get_guardrail_state", lambda: {})
    guardrail_updates = []
    monkeypatch.setattr(trader, "update_guardrail_state",
        lambda **kw: guardrail_updates.append(kw))

    client = FakeClient(landed_orders=[])  # no landing
    result = trader.reconcile_after_exception(
        client=client, client_order_id="wa-NYC-abc-111",
        insert_kwargs=_base_insert_kwargs(), stake=2.10,
        exc=ConnectionError("network dropped"),
    )
    assert result is None
    assert inserted == []
    assert guardrail_updates == []
    assert client.probe_calls == ["wa-NYC-abc-111"]


def test_reconcile_landed_inserts_trade_and_updates_guardrails(monkeypatch):
    """place_order raised BUT order landed on Kalshi → trade row + guardrail bump."""
    monkeypatch.setattr(trader, "PAPER_MODE", False)

    inserted = []
    def fake_insert(**kw):
        inserted.append(kw)
        return 777
    monkeypatch.setattr(trader, "insert_trade", fake_insert)
    monkeypatch.setattr(trader, "get_guardrail_state", lambda: {
        "daily_trades": 2, "daily_pnl_usd": -5.0,
        "consecutive_losses": 1, "capital_at_risk_usd": 10.0,
        "halted": False, "halt_reason": "",
    })
    guardrail_updates = []
    monkeypatch.setattr(trader, "update_guardrail_state",
        lambda **kw: guardrail_updates.append(kw))

    client = FakeClient(landed_orders=[{
        "order_id": "kalshi-xyz-42",
        "client_order_id": "wa-NYC-abc-222",
        "status": "resting",
    }])
    result = trader.reconcile_after_exception(
        client=client, client_order_id="wa-NYC-abc-222",
        insert_kwargs=_base_insert_kwargs(), stake=2.10,
        exc=ConnectionError("timeout after send"),
    )
    assert result == 777
    assert len(inserted) == 1
    assert "RECONCILED" in inserted[0]["notes"]
    assert "timeout after send" in inserted[0]["notes"]
    assert inserted[0]["market_id"] == "KXHIGHNY-26APR22-T70"
    assert len(guardrail_updates) == 1
    assert guardrail_updates[0]["daily_trades"] == 3  # bumped from 2
    assert guardrail_updates[0]["capital_at_risk_usd"] == 12.10  # 10.0 + 2.10


def test_reconcile_paper_mode_skips_probe(monkeypatch):
    """PAPER_MODE → never probe Kalshi, never insert anything."""
    monkeypatch.setattr(trader, "PAPER_MODE", True)
    inserted = []
    monkeypatch.setattr(trader, "insert_trade",
        lambda **kw: inserted.append(kw) or 1)

    client = FakeClient(landed_orders=[{"client_order_id": "w", "status": "resting"}])
    result = trader.reconcile_after_exception(
        client=client, client_order_id="w",
        insert_kwargs=_base_insert_kwargs(), stake=5.0,
        exc=RuntimeError("anything"),
    )
    assert result is None
    assert inserted == []
    assert client.probe_calls == []  # probe never called


def test_reconcile_probe_error_returns_none(monkeypatch):
    """Probe itself raising should not crash the scan loop."""
    monkeypatch.setattr(trader, "PAPER_MODE", False)
    monkeypatch.setattr(trader, "insert_trade", lambda **kw: 1)
    monkeypatch.setattr(trader, "get_guardrail_state", lambda: {})
    monkeypatch.setattr(trader, "update_guardrail_state", lambda **kw: None)

    client = FakeClient(raise_on_probe=True)
    result = trader.reconcile_after_exception(
        client=client, client_order_id="wa-NYC-abc-333",
        insert_kwargs=_base_insert_kwargs(), stake=2.10,
        exc=RuntimeError("original"),
    )
    assert result is None


def test_reconcile_insert_dedup_returns_none(monkeypatch):
    """If insert_trade returns -1 (dedup), do not bump guardrails."""
    monkeypatch.setattr(trader, "PAPER_MODE", False)
    monkeypatch.setattr(trader, "insert_trade", lambda **kw: -1)

    guardrail_updates = []
    monkeypatch.setattr(trader, "get_guardrail_state", lambda: {})
    monkeypatch.setattr(trader, "update_guardrail_state",
        lambda **kw: guardrail_updates.append(kw))

    client = FakeClient(landed_orders=[{
        "order_id": "dup", "client_order_id": "wa-NYC-dup", "status": "resting",
    }])
    result = trader.reconcile_after_exception(
        client=client, client_order_id="wa-NYC-dup",
        insert_kwargs=_base_insert_kwargs(), stake=2.10,
        exc=RuntimeError("x"),
    )
    assert result is None
    assert guardrail_updates == []
