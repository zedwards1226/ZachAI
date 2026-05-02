"""Tests for the 5-gate risk engine. Ensures every gate fires correctly
and the per-trade $ cap clamps contract counts as expected.

Mocks:
  - PAPER_MODE flag via monkeypatch
  - get_conn for the sector daily count gate (returns 0 by default)
  - SHARED_RISK_STATE file path → tmp dir (empty = no halt)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.base import EntryDecision, MarketSnapshot, StrategyContext


def _decision(contracts=10, price_cents=25, side="no") -> EntryDecision:
    return EntryDecision(
        side=side, contracts=contracts, price_cents=price_cents,
        edge=0.20, forecast_prob=0.85, kelly_frac=0.30,
        reason="test", extras={},
    )


def _market(volume=5000.0) -> MarketSnapshot:
    return MarketSnapshot(
        ticker="KXBTC15M-X-1", sector="crypto", series_ticker="KXBTC15M",
        title="t", open_time="2026-03-01T00:00:00Z", close_time="2026-03-01T00:15:00Z",
        yes_ask_cents=25, yes_bid_cents=24, no_ask_cents=75, no_bid_cents=74,
        last_price_cents=25, volume_fp=volume, open_interest_fp=10.0,
        seconds_to_close=600,
    )


def _ctx(**overrides) -> StrategyContext:
    base = dict(
        capital_usd=100.0, open_positions_count=0,
        daily_realized_pnl_usd=0.0, weekly_realized_pnl_usd=0.0,
        sector="crypto", consecutive_losses_in_sector=0,
    )
    base.update(overrides)
    return StrategyContext(**base)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Force PAPER_MODE on, point shared risk state at tmp dir, mock DB count."""
    from bots import risk_engine
    monkeypatch.setattr(risk_engine, "PAPER_MODE", True)
    monkeypatch.setattr(risk_engine, "SHARED_RISK_STATE", tmp_path / "risk_state.json")

    # Mock the sector count to 0 so it doesn't fail on missing DB
    monkeypatch.setattr(risk_engine, "_count_today_trades_in_sector", lambda s: 0)
    yield


def test_paper_mode_off_blocks(monkeypatch):
    from bots import risk_engine
    monkeypatch.setattr(risk_engine, "PAPER_MODE", False)
    v = risk_engine.check_entry(_decision(), _market(), _ctx())
    assert not v.approved
    assert v.reason == "paper_mode_off"


def test_per_trade_cap_clamps_contracts():
    """PER_TRADE_MAX_RISK_USD=20 → at 25c entry, max contracts = 20/0.25 = 80.
    We propose 10 contracts (under the cap), should pass with no clamp."""
    from bots import risk_engine
    monkeypatch_clamp = type("M", (), {})()  # no-op
    v = risk_engine.check_entry(_decision(contracts=10, price_cents=25), _market(), _ctx())
    assert v.approved
    assert v.clamped_contracts == 10


def test_per_trade_cap_clamps_when_exceeded(monkeypatch):
    from bots import risk_engine
    # Force a tiny cap to trigger clamping
    monkeypatch.setattr(risk_engine, "PER_TRADE_MAX_RISK_USD", 5.0)
    v = risk_engine.check_entry(_decision(contracts=100, price_cents=25), _market(), _ctx())
    assert v.approved
    # cap=5, price=0.25 → max contracts = 20
    assert v.clamped_contracts == 20


def test_liquidity_floor_blocks():
    from bots import risk_engine
    v = risk_engine.check_entry(_decision(), _market(volume=10.0), _ctx())
    assert not v.approved
    assert v.reason == "liquidity"


def test_concentration_blocks():
    from bots import risk_engine
    v = risk_engine.check_entry(_decision(), _market(),
                                _ctx(open_positions_count=999))
    assert not v.approved
    assert v.reason == "concentration"


def test_daily_loss_cap_blocks():
    from bots import risk_engine
    v = risk_engine.check_entry(_decision(), _market(),
                                _ctx(daily_realized_pnl_usd=-500.0))
    assert not v.approved
    assert v.reason == "daily_loss_cap"


def test_consec_losses_blocks():
    from bots import risk_engine
    v = risk_engine.check_entry(_decision(), _market(),
                                _ctx(consecutive_losses_in_sector=99))
    assert not v.approved
    assert v.reason == "consec_losses_pause"


def test_cross_bot_halt_blocks(monkeypatch, tmp_path):
    """Setting halt_all in shared risk_state.json should block all entries."""
    from bots import risk_engine
    import json
    risk_state_path = tmp_path / "risk_state.json"
    risk_state_path.write_text(json.dumps({"halt_all": True, "reason": "test halt"}))
    monkeypatch.setattr(risk_engine, "SHARED_RISK_STATE", risk_state_path)
    v = risk_engine.check_entry(_decision(), _market(), _ctx())
    assert not v.approved
    assert v.reason == "cross_bot_halt"


def test_update_my_section_writes_and_reads(tmp_path, monkeypatch):
    from bots import risk_engine
    risk_state_path = tmp_path / "risk_state.json"
    monkeypatch.setattr(risk_engine, "SHARED_RISK_STATE", risk_state_path)

    risk_engine.update_my_section(
        bot="omnialpha",
        daily_pnl_usd=12.50,
        weekly_pnl_usd=88.00,
        open_positions=2,
    )
    state = risk_engine._read_cross_bot_state()
    assert state["bots"]["omnialpha"]["daily_pnl_usd"] == 12.50
    assert state["bots"]["omnialpha"]["open_positions"] == 2
    assert "aggregate_daily_pnl_usd" in state


def test_clear_global_halt(tmp_path, monkeypatch):
    from bots import risk_engine
    import json
    risk_state_path = tmp_path / "risk_state.json"
    risk_state_path.write_text(json.dumps({"halt_all": True}))
    monkeypatch.setattr(risk_engine, "SHARED_RISK_STATE", risk_state_path)
    risk_engine.clear_global_halt(reason="test")
    state = risk_engine._read_cross_bot_state()
    assert "halt_all" not in state
    assert state.get("last_halt_clear_reason") == "test"
