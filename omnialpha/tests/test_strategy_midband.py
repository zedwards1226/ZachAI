"""Tests for crypto_midband strategy. Pure unit tests — no DB, no network.

Confirms the strategy:
  1. Recognizes the configured NO/YES bands and returns the correct side
  2. Skips markets outside the bands (extremes + middle gap)
  3. Skips thin markets
  4. Skips markets too close to settlement
  5. Computes Kelly stake correctly
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.base import MarketSnapshot, StrategyContext
from strategies.crypto_midband import (
    CryptoMidBandStrategy,
    MIN_VOLUME_FP,
    MIN_SECONDS_TO_CLOSE,
)


def _make_market(*, last_yes_cents: int, volume: float = 5000.0,
                 seconds_to_close: int = 120) -> MarketSnapshot:
    # 120s default = within the new 30-180s entry window.
    return MarketSnapshot(
        ticker="KXBTC15M-26MAR011845-45",
        sector="crypto",
        series_ticker="KXBTC15M",
        title="BTC up 15m",
        open_time="2026-03-01T18:30:00Z",
        close_time="2026-03-01T18:45:00Z",
        yes_ask_cents=last_yes_cents,
        yes_bid_cents=max(0, last_yes_cents - 1),
        no_ask_cents=100 - last_yes_cents,
        no_bid_cents=max(0, 99 - last_yes_cents),
        last_price_cents=last_yes_cents,
        volume_fp=volume,
        open_interest_fp=100.0,
        seconds_to_close=seconds_to_close,
    )


def _ctx() -> StrategyContext:
    return StrategyContext(
        capital_usd=100.0,
        open_positions_count=0,
        daily_realized_pnl_usd=0.0,
        weekly_realized_pnl_usd=0.0,
        sector="crypto",
        consecutive_losses_in_sector=0,
    )


def test_no_band_takes_no_side():
    """yes_price 25c → market overprices YES → bot bets NO"""
    s = CryptoMidBandStrategy()
    decision = s.decide_entry(_make_market(last_yes_cents=25), _ctx())
    assert decision is not None
    assert decision.side == "no"
    assert decision.contracts >= 1
    assert decision.edge > 0
    assert "midband_no" in decision.reason


def test_yes_band_takes_yes_side():
    s = CryptoMidBandStrategy()
    decision = s.decide_entry(_make_market(last_yes_cents=78), _ctx())
    assert decision is not None
    assert decision.side == "yes"
    assert decision.contracts >= 1
    assert decision.edge > 0
    assert "midband_yes" in decision.reason


def test_low_extreme_skipped():
    """yes_price 3c → well-calibrated, no edge → skip"""
    s = CryptoMidBandStrategy()
    assert s.decide_entry(_make_market(last_yes_cents=3), _ctx()) is None


def test_high_extreme_skipped():
    s = CryptoMidBandStrategy()
    assert s.decide_entry(_make_market(last_yes_cents=97), _ctx()) is None


def test_middle_gap_skipped():
    """yes_price 50c — between NO band (20-40) and YES band (70-85), no edge"""
    s = CryptoMidBandStrategy()
    assert s.decide_entry(_make_market(last_yes_cents=50), _ctx()) is None


def test_thin_market_skipped():
    s = CryptoMidBandStrategy()
    thin = _make_market(last_yes_cents=25, volume=MIN_VOLUME_FP - 1)
    assert s.decide_entry(thin, _ctx()) is None


def test_too_close_to_settlement_skipped():
    s = CryptoMidBandStrategy()
    near = _make_market(last_yes_cents=25, seconds_to_close=MIN_SECONDS_TO_CLOSE - 1)
    assert s.decide_entry(near, _ctx()) is None


def test_too_far_from_settlement_skipped():
    """Strategy enters only in the last MAX_SECONDS_TO_CLOSE_FOR_ENTRY (180s)
    window — outside that, the calibration distribution doesn't apply."""
    from strategies.crypto_midband import MAX_SECONDS_TO_CLOSE_FOR_ENTRY
    s = CryptoMidBandStrategy()
    far = _make_market(
        last_yes_cents=25,
        seconds_to_close=MAX_SECONDS_TO_CLOSE_FOR_ENTRY + 60,
    )
    assert s.decide_entry(far, _ctx()) is None


def test_dropped_band_30_40_no_longer_takes():
    """The 0.30-0.40 NO band was DROPPED for sample-size reasons.
    yes_price=35c should now SKIP."""
    s = CryptoMidBandStrategy()
    assert s.decide_entry(_make_market(last_yes_cents=35), _ctx()) is None


def test_dropped_band_70_75_no_longer_takes():
    """The 0.70-0.75 YES band was DROPPED for sample-size reasons.
    yes_price=72c should now SKIP."""
    s = CryptoMidBandStrategy()
    assert s.decide_entry(_make_market(last_yes_cents=72), _ctx()) is None


def test_already_settled_skipped():
    """yes_price 0 or 100 means market settled — skip"""
    s = CryptoMidBandStrategy()
    assert s.decide_entry(_make_market(last_yes_cents=0), _ctx()) is None
    assert s.decide_entry(_make_market(last_yes_cents=100), _ctx()) is None


def test_non_crypto_sector_skipped():
    """Strategy is crypto-only — markets in other sectors should be skipped."""
    s = CryptoMidBandStrategy()
    m = _make_market(last_yes_cents=25)
    m.sector = "sports"
    assert s.decide_entry(m, _ctx()) is None


def test_kelly_fraction_scales_contracts():
    """Lower kelly_fraction → fewer contracts at same price."""
    m = _make_market(last_yes_cents=25)
    s_aggressive = CryptoMidBandStrategy(kelly_fraction=0.20)
    s_conservative = CryptoMidBandStrategy(kelly_fraction=0.05)
    d_aggressive = s_aggressive.decide_entry(m, _ctx())
    d_conservative = s_conservative.decide_entry(m, _ctx())
    assert d_aggressive is not None and d_conservative is not None
    assert d_aggressive.contracts > d_conservative.contracts
