"""Tests for the per-sport (per-series) auto-pause grader.

The longshot_fade strategy runs across 9 sports. The grader must pause a
SINGLE losing sport without touching the others. These tests build a tmp DB
with controlled settled trades and assert the right sports get paused.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_layer import database
from bots import strategy_grader


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "grader.db"
    database.init_db(db_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    # strategy_grader calls get_conn() with no path → uses module DB_PATH
    monkeypatch.setattr(strategy_grader, "get_conn",
                        lambda *a, **kw: database.get_conn(db_path, **kw))
    # Silence telegram
    monkeypatch.setattr("bots.telegram_alerts.send", lambda *a, **kw: True)
    return db_path


def _insert_settled(db_path, *, ticker, side, price_cents, won, n_times=1, strategy="longshot_fade"):
    now = datetime.now(timezone.utc).isoformat()
    status = "won" if won else "lost"
    # pnl: win = (100-p)/100 * contracts; loss = -(p/100)*contracts. 1 contract.
    pnl = (100 - price_cents) / 100.0 if won else -(price_cents / 100.0)
    with database.get_conn(db_path) as conn:
        for _ in range(n_times):
            conn.execute(
                "INSERT INTO trades (timestamp, sector, strategy, market_ticker, "
                "side, contracts, price_cents, stake_usd, paper, status, pnl_usd, resolved_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (now, "sports", strategy, ticker, side, 1, price_cents,
                 price_cents / 100.0, 1, status, pnl, now),
            )


def test_healthy_sport_not_paused(isolated_db):
    # 25 NBA trades at 90c NO, 23 wins (92% WR > break-even ~92%) → healthy-ish
    # Use 95c entry so break-even is ~0.97; 24/25 = 96% < 97% but PnL...
    # Keep it clearly healthy: 90c entry (break-even 0.92), 24/25 win = 96%.
    _insert_settled(isolated_db, ticker="KXNBAGAME-26X-A", side="no",
                    price_cents=90, won=True, n_times=24)
    _insert_settled(isolated_db, ticker="KXNBAGAME-26X-A", side="no",
                    price_cents=90, won=False, n_times=1)
    strategy_grader.grade_series_for_strategy("longshot_fade")
    assert not strategy_grader.is_series_paused("longshot_fade", "KXNBAGAME-26X-A")


def test_losing_sport_gets_paused(isolated_db):
    # 25 NHL trades at 90c NO (break-even 0.92), only 15 wins = 60% WR,
    # negative PnL → BOTH signals bad → pause.
    _insert_settled(isolated_db, ticker="KXNHLGAME-26X-B", side="no",
                    price_cents=90, won=True, n_times=15)
    _insert_settled(isolated_db, ticker="KXNHLGAME-26X-B", side="no",
                    price_cents=90, won=False, n_times=10)
    strategy_grader.grade_series_for_strategy("longshot_fade")
    assert strategy_grader.is_series_paused("longshot_fade", "KXNHLGAME-26X-B")


def test_pause_is_per_sport_not_global(isolated_db):
    """Losing NHL must NOT pause healthy NBA — the whole point."""
    # NBA healthy
    _insert_settled(isolated_db, ticker="KXNBAGAME-26X-C", side="no",
                    price_cents=90, won=True, n_times=24)
    _insert_settled(isolated_db, ticker="KXNBAGAME-26X-C", side="no",
                    price_cents=90, won=False, n_times=1)
    # NHL bleeding
    _insert_settled(isolated_db, ticker="KXNHLGAME-26X-D", side="no",
                    price_cents=90, won=True, n_times=14)
    _insert_settled(isolated_db, ticker="KXNHLGAME-26X-D", side="no",
                    price_cents=90, won=False, n_times=11)
    strategy_grader.grade_series_for_strategy("longshot_fade")
    assert strategy_grader.is_series_paused("longshot_fade", "KXNHLGAME-26X-D")
    assert not strategy_grader.is_series_paused("longshot_fade", "KXNBAGAME-26X-C")


def test_insufficient_sample_not_paused(isolated_db):
    """Below MIN_TRADES (20), even a terrible record doesn't pause —
    could be variance."""
    _insert_settled(isolated_db, ticker="KXMLBGAME-26X-E", side="no",
                    price_cents=90, won=False, n_times=5)  # 0/5, awful but tiny
    strategy_grader.grade_series_for_strategy("longshot_fade")
    assert not strategy_grader.is_series_paused("longshot_fade", "KXMLBGAME-26X-E")


def test_low_wr_but_positive_pnl_only_watched(isolated_db):
    """Low WR but positive P&L = variance, not degradation → watch, not pause."""
    # 21 trades at 30c NO (cheap → break-even 0.50). 11 wins = 52% WR.
    # Wins pay 0.70 each, losses cost 0.30. 11*0.70 - 10*0.30 = 7.70-3.00=+4.70
    _insert_settled(isolated_db, ticker="KXMLBGAME-26X-F", side="no",
                    price_cents=30, won=True, n_times=11)
    _insert_settled(isolated_db, ticker="KXMLBGAME-26X-F", side="no",
                    price_cents=30, won=False, n_times=10)
    strategy_grader.grade_series_for_strategy("longshot_fade")
    # 52% WR > break-even 0.50, so it's actually healthy here — not paused
    assert not strategy_grader.is_series_paused("longshot_fade", "KXMLBGAME-26X-F")
