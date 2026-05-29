"""Tests for LongshotFadeStrategy.

Covers:
  - Sector gate (only "sports" fires)
  - Series whitelist (NBA + NFL allowed; EPL/UCL blocked; unknown blocked)
  - Price gate (only 85-99¢ NO ask)
  - Liquidity gate (volume_fp < threshold rejected)
  - Time gates (too soon / too far rejected)
  - Bucket forecast + EV-after-fees gate
  - Kelly sizing + $30 hard cap
  - Order details (NO side, price 1¢ inside ask)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.base import MarketSnapshot, StrategyContext
from strategies.longshot_fade import LongshotFadeStrategy, KALSHI_FEE_RATE


def _make_market(
    *,
    ticker: str = "KXNFLGAME-26MAR15KCLA-LA",
    sector: str = "sports",
    no_ask_cents: int = 92,
    volume_fp: float = 5000.0,
    seconds_to_close: int = 3600,
) -> MarketSnapshot:
    yes_ask = 100 - no_ask_cents
    return MarketSnapshot(
        ticker=ticker,
        sector=sector,
        series_ticker=ticker.split("-")[0],
        title="test",
        open_time="2026-03-15T10:00:00Z",
        close_time="2026-03-15T17:00:00Z",
        yes_ask_cents=yes_ask,
        yes_bid_cents=max(0, yes_ask - 1),
        no_ask_cents=no_ask_cents,
        no_bid_cents=max(0, no_ask_cents - 1),
        last_price_cents=yes_ask,
        volume_fp=volume_fp,
        open_interest_fp=100.0,
        seconds_to_close=seconds_to_close,
    )


def _make_ctx(capital_usd: float = 300.0) -> StrategyContext:
    return StrategyContext(
        capital_usd=capital_usd,
        open_positions_count=0,
        daily_realized_pnl_usd=0.0,
        weekly_realized_pnl_usd=0.0,
        sector="sports",
        consecutive_losses_in_sector=0,
    )


# ─── Sector + universe gates ────────────────────────────────────────────

def test_rejects_non_sports_sector():
    s = LongshotFadeStrategy()
    m = _make_market()
    m.sector = "crypto"
    assert s.decide_entry(m, _make_ctx()) is None


def test_rejects_blocked_epl_series():
    s = LongshotFadeStrategy()
    m = _make_market(ticker="KXEPLGAME-26MAR15ARSCHE-ARS")
    assert s.decide_entry(m, _make_ctx()) is None


def test_rejects_unknown_series():
    """KXNCAA isn't in the whitelist — must be skipped even though sport."""
    s = LongshotFadeStrategy()
    m = _make_market(ticker="KXNCAAMBB-26MAR15UCLAGT-GT")
    assert s.decide_entry(m, _make_ctx()) is None


def test_accepts_nba_series():
    s = LongshotFadeStrategy()
    m = _make_market(ticker="KXNBAGAME-26MAR15LALPHX-LAL")
    assert s.decide_entry(m, _make_ctx()) is not None


def test_accepts_nfl_series():
    s = LongshotFadeStrategy()
    m = _make_market(ticker="KXNFLGAME-26MAR15KCLA-LA")
    assert s.decide_entry(m, _make_ctx()) is not None


def test_accepts_mlb_series():
    """MLB added 2026-05-27 (peak season). Not in Phase 1 validation —
    forecasts borrow from NBA buckets. Strategy accepts the series; live
    paper data will validate the edge."""
    s = LongshotFadeStrategy()
    m = _make_market(ticker="KXMLBGAME-26MAY27NYYBOS-NYY")
    assert s.decide_entry(m, _make_ctx()) is not None


# ─── Price gate ─────────────────────────────────────────────────────────

def test_rejects_below_band():
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=70)
    assert s.decide_entry(m, _make_ctx()) is None


def test_rejects_at_100():
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=100)
    assert s.decide_entry(m, _make_ctx()) is None


def test_does_not_post_outside_bucket():
    """When ask is exactly at bucket low (85¢), posting 84¢ would leave the
    bucket and break the calibration assumption — strategy must refuse."""
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=85)
    d = s.decide_entry(m, _make_ctx())
    # Per the strategy: entry_price = no_ask - 1 = 84, which is < bucket low 85
    # → return None.
    assert d is None


def test_posts_inside_bucket_above_low():
    """At no_ask=86, entry=85 — still inside the 85-89 bucket."""
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=86)
    d = s.decide_entry(m, _make_ctx())
    assert d is not None
    assert d.price_cents == 85


# ─── Liquidity + time gates ─────────────────────────────────────────────

def test_rejects_low_volume():
    s = LongshotFadeStrategy()
    m = _make_market(volume_fp=500.0)
    assert s.decide_entry(m, _make_ctx()) is None


def test_rejects_too_close_to_settlement():
    s = LongshotFadeStrategy()
    m = _make_market(seconds_to_close=600)  # 10 min
    assert s.decide_entry(m, _make_ctx()) is None


def test_rejects_too_far_from_settlement():
    s = LongshotFadeStrategy()
    m = _make_market(seconds_to_close=86400)  # 24 hr
    assert s.decide_entry(m, _make_ctx()) is None


def test_rejects_settled_market():
    s = LongshotFadeStrategy()
    m = _make_market(seconds_to_close=-1)
    assert s.decide_entry(m, _make_ctx()) is None


# ─── Order shape ────────────────────────────────────────────────────────

def test_posts_no_side_at_one_cent_inside():
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=92)
    d = s.decide_entry(m, _make_ctx())
    assert d is not None
    assert d.side == "no"
    assert d.price_cents == 91  # 1¢ inside the 92 ask


def test_attaches_bucket_metadata():
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=92)  # 90-94 bucket
    d = s.decide_entry(m, _make_ctx())
    assert d is not None
    assert d.extras["bucket_low"] == 90
    assert d.extras["bucket_high"] == 94
    assert d.extras["bucket_forecast"] == pytest.approx(0.939)
    assert d.extras["kalshi_fee_rate"] == KALSHI_FEE_RATE


# ─── Sizing ─────────────────────────────────────────────────────────────

def test_kelly_fraction_applied():
    """Smaller kelly → smaller stake → fewer contracts."""
    big = LongshotFadeStrategy(kelly_fraction=0.10)
    small = LongshotFadeStrategy(kelly_fraction=0.01)
    m = _make_market(no_ask_cents=92)
    ctx = _make_ctx(capital_usd=300.0)
    db = big.decide_entry(m, ctx)
    ds = small.decide_entry(m, ctx)
    assert db is not None and ds is not None
    assert db.contracts > ds.contracts


def test_per_trade_hard_cap_clamps_contracts():
    """With a tiny hard cap, contracts must be limited."""
    s = LongshotFadeStrategy(per_trade_hard_cap_usd=2.0)
    m = _make_market(no_ask_cents=92)  # entry 91¢
    ctx = _make_ctx(capital_usd=10_000.0)  # large capital
    d = s.decide_entry(m, ctx)
    assert d is not None
    # max stake = $2, entry price = 91¢ → max ~2 contracts.
    assert d.contracts <= 3


def test_rejects_below_dust_stake():
    """If capital × kelly × full_kelly < $0.50, refuse the trade."""
    s = LongshotFadeStrategy(kelly_fraction=0.0001)
    m = _make_market(no_ask_cents=92)
    ctx = _make_ctx(capital_usd=10.0)
    d = s.decide_entry(m, ctx)
    assert d is None


# ─── EV gate ────────────────────────────────────────────────────────────

def test_ev_gate_blocks_thin_edge():
    """Setting min_ev_per_dollar very high should block trades whose EV is
    too thin after fees."""
    s = LongshotFadeStrategy(min_ev_per_dollar=10.0)  # impossible threshold
    m = _make_market(no_ask_cents=92)
    assert s.decide_entry(m, _make_ctx()) is None


# ─── Exit ───────────────────────────────────────────────────────────────

def test_exit_always_holds_to_settlement():
    s = LongshotFadeStrategy()
    m = _make_market(no_ask_cents=92)
    fake_position = {"side": "no", "price_cents": 91, "contracts": 5}
    assert s.decide_exit(fake_position, m, _make_ctx()) is None
