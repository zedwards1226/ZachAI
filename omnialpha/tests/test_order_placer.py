"""Tests for order_placer — paper-mode is the safety net.

Critical invariants tested:
  1. Paper-mode placement writes to trades table with paper=1 and status='open'
  2. Live placement is REFUSED unless both PAPER_MODE=false AND
     assert_paper_mode_off_was_explicit() returns True
  3. mark_resolved() correctly transitions open → won/lost with P&L
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_layer.database import get_conn, init_db
from strategies.base import EntryDecision


def _decision() -> EntryDecision:
    return EntryDecision(
        side="no", contracts=10, price_cents=25,
        edge=0.20, forecast_prob=0.85, kelly_frac=0.30,
        reason="test", extras={},
    )


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Use a tmp DB so tests don't pollute production state."""
    from data_layer import database
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)

    # ALSO patch DB_PATH in any module that imported it directly
    from bots import order_placer
    from bots import trade_monitor
    monkeypatch.setattr(order_placer, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(trade_monitor, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))

    init_db(db_path)
    yield db_path


def test_paper_mode_writes_open_row(_isolate):
    from bots.order_placer import place_paper_order
    result = place_paper_order(
        decision=_decision(),
        market_ticker="KXBTC15M-T-1",
        sector="crypto",
        strategy_name="crypto_midband",
    )
    assert result["paper"] is True
    assert result["trade_id"] > 0
    assert result["order_id"].startswith("paper-")

    with get_conn(_isolate, readonly=True) as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (result["trade_id"],)
        ).fetchone()
    assert row is not None
    assert row["paper"] == 1
    assert row["status"] == "open"
    assert row["side"] == "no"
    assert row["contracts"] == 10
    assert row["price_cents"] == 25


def test_live_mode_refused_when_explicit_flag_off(monkeypatch):
    from bots import order_placer
    monkeypatch.setattr(order_placer, "PAPER_MODE", False)
    # assert_paper_mode_off_was_explicit() returns False by default
    with pytest.raises(order_placer.OrderPlacementError) as exc:
        order_placer.place_live_order(
            decision=_decision(),
            market_ticker="KXBTC15M-T-1",
            sector="crypto",
            strategy_name="crypto_midband",
            kalshi_client=None,
        )
    assert "explicit code-level approval" in str(exc.value)


def test_paper_mode_blocks_live_path_too(monkeypatch):
    """Even if explicit flag flipped, PAPER_MODE=true must still block live."""
    from bots import order_placer
    monkeypatch.setattr(order_placer, "PAPER_MODE", True)
    monkeypatch.setattr(order_placer, "assert_paper_mode_off_was_explicit", lambda: True)
    with pytest.raises(order_placer.OrderPlacementError) as exc:
        order_placer.place_live_order(
            decision=_decision(),
            market_ticker="KXBTC15M-T-1",
            sector="crypto",
            strategy_name="crypto_midband",
            kalshi_client=None,
        )
    assert "PAPER_MODE=true" in str(exc.value)


def test_mark_resolved_transitions_won(_isolate):
    from bots.order_placer import place_paper_order, mark_resolved
    r = place_paper_order(
        decision=_decision(), market_ticker="KX-T-W",
        sector="crypto", strategy_name="t",
    )
    mark_resolved(trade_id=r["trade_id"], won=True, pnl_usd=6.98,
                  settlement_value_dollars=0.0)
    with get_conn(_isolate, readonly=True) as conn:
        row = conn.execute(
            "SELECT status, pnl_usd, resolved_at FROM trades WHERE id = ?",
            (r["trade_id"],),
        ).fetchone()
    assert row["status"] == "won"
    assert abs(row["pnl_usd"] - 6.98) < 1e-6
    assert row["resolved_at"] is not None
