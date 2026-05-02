"""End-to-end smoke: simulates the full lifecycle of one paper trade
through the bot's actual modules. No mocks of internal logic — only the
DB path is redirected to a tmp file.

Sequence:
  1. Init schema in tmp DB
  2. Insert a fake KXBTC15M market into markets table (status='active')
  3. Strategy decides on it → returns EntryDecision
  4. Risk engine approves it
  5. Order placer writes paper trade row → status='open'
  6. Mark market as 'finalized' with result='no'
  7. Trade monitor settles the open trade → status='won'
  8. P&L snapshot writes a row
  9. Verify everything matches

This is the smoke test that proves the bot is wired end-to-end.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_layer.database import get_conn, init_db


def _insert_market(db_path: Path, *, ticker: str, last_yes_cents: int, volume: float = 5000.0):
    raw_json = json.dumps({
        "ticker": ticker,
        "last_price_dollars": last_yes_cents / 100.0,
        "volume_fp": volume,
        "yes_ask_dollars": last_yes_cents / 100.0,
        "no_ask_dollars": (100 - last_yes_cents) / 100.0,
    })
    now_iso = datetime.now(timezone.utc).isoformat()
    open_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    close_iso = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO markets (
                ticker, event_ticker, series_ticker, sector, title,
                open_time, close_time, expiration_time,
                market_type, status, volume_fp,
                final_yes_ask_dollars, final_no_ask_dollars,
                raw_json, first_seen_at, last_updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                ticker, "evt-1", "KXBTC15M", "crypto", "BTC test",
                open_iso, close_iso, close_iso,
                "binary", "active", volume,
                last_yes_cents / 100.0, (100 - last_yes_cents) / 100.0,
                raw_json, now_iso, now_iso,
            ),
        )


def _resolve_market(db_path: Path, ticker: str, result: str):
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE markets SET status='finalized', result=?, "
            "settlement_value_dollars=? WHERE ticker=?",
            (result, 1.0 if result == "yes" else 0.0, ticker),
        )


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Redirect ALL modules' DB path to a tmp file."""
    db_path = tmp_path / "e2e.db"
    init_db(db_path)

    from data_layer import database
    from bots import order_placer, trade_monitor, risk_engine
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(order_placer, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(trade_monitor, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(risk_engine, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    monkeypatch.setattr(risk_engine, "SHARED_RISK_STATE",
                        tmp_path / "risk_state.json")
    # Stop trade monitor's notify_exit from making HTTP calls
    monkeypatch.setattr(
        "bots.telegram_alerts.send", lambda *a, **kw: True
    )
    return db_path


def test_end_to_end_paper_trade_lifecycle(isolated_db):
    """Full lifecycle on a fake market: strategy → risk → place → settle → P&L."""
    from bots import order_placer
    from bots.risk_engine import check_entry
    from bots.trade_monitor import settle_resolved_trades, write_pnl_snapshot
    from strategies.crypto_midband import CryptoMidBandStrategy
    from strategies.base import MarketSnapshot, StrategyContext

    # 1. Insert a market in the NO-band (yes price 25c)
    ticker = "KXBTC15M-E2E-1"
    _insert_market(isolated_db, ticker=ticker, last_yes_cents=25)

    # 2. Build snapshot the way the runner would
    snap = MarketSnapshot(
        ticker=ticker, sector="crypto", series_ticker="KXBTC15M",
        title="BTC test",
        open_time=datetime.now(timezone.utc).isoformat(),
        close_time=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        yes_ask_cents=25, yes_bid_cents=24, no_ask_cents=75, no_bid_cents=74,
        last_price_cents=25, volume_fp=5000.0, open_interest_fp=50.0,
        seconds_to_close=600,
    )
    ctx = StrategyContext(
        capital_usd=100.0, open_positions_count=0,
        daily_realized_pnl_usd=0.0, weekly_realized_pnl_usd=0.0,
        sector="crypto", consecutive_losses_in_sector=0,
    )

    # 3. Strategy decides
    strat = CryptoMidBandStrategy()
    decision = strat.decide_entry(snap, ctx)
    assert decision is not None
    assert decision.side == "no"

    # 4. Risk engine approves
    verdict = check_entry(decision, snap, ctx)
    assert verdict.approved
    assert verdict.clamped_contracts >= 1

    # 5. Place paper order
    from dataclasses import replace
    decision = replace(decision, contracts=verdict.clamped_contracts)
    placed = order_placer.place_paper_order(
        decision=decision, market_ticker=ticker,
        sector="crypto", strategy_name="crypto_midband",
    )
    assert placed["paper"] is True
    trade_id = placed["trade_id"]

    # 6. Resolve the market in the bot's favor (NO wins)
    _resolve_market(isolated_db, ticker, result="no")

    # 7. Trade monitor should settle
    result = settle_resolved_trades()
    assert result["settled"] == 1
    assert result["wins"] == 1
    assert result["total_pnl_usd"] > 0  # NO won, we get the spread minus 7% fee

    # 8. Verify trade row updated
    with get_conn(isolated_db, readonly=True) as conn:
        row = conn.execute(
            "SELECT status, pnl_usd, resolved_at FROM trades WHERE id=?",
            (trade_id,),
        ).fetchone()
    assert row["status"] == "won"
    assert row["pnl_usd"] > 0
    assert row["resolved_at"] is not None

    # 9. P&L snapshot writes a row
    snap_result = write_pnl_snapshot(starting_capital_usd=100.0)
    assert snap_result["total_wins"] == 1
    assert snap_result["realized_total"] > 0
    assert snap_result["capital_usd"] > 100.0
