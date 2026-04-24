"""Regression test: between-market disagreement guardrail.

Locks in the fix for the 2026-04-23 incident where LAX/MIA/NYC NO trades
slipped past check_market_disagreement because of a blanket `between` bypass.
"""
from kalshi.bots.guardrails import check_market_disagreement


def test_between_market_blocks_when_market_disagrees():
    # Today's actual NYC entry: market YES=58¢, our YES prob≈0.138. Gap=44¢ > 30¢ → MUST BLOCK.
    ok, reason = check_market_disagreement(
        our_prob_yes=0.138, yes_price_cents=58, strike_type="between"
    )
    assert ok is False, f"between market with 44¢ gap should block, got: {reason}"


def test_between_market_blocks_lax_pattern():
    # LAX: market YES=42¢ (100-58), our YES prob≈0.101. But between markets use yes_price
    # directly. Market YES=42 vs our=10 → gap=32¢ → MUST BLOCK.
    ok, _ = check_market_disagreement(
        our_prob_yes=0.10, yes_price_cents=42, strike_type="between"
    )
    assert ok is False


def test_between_longshot_passes():
    # Real longshot band: market prices YES < 10¢ (e.g. 4¢), our model also low (3¢) — bypass.
    ok, _ = check_market_disagreement(
        our_prob_yes=0.03, yes_price_cents=4, strike_type="between"
    )
    assert ok is True


def test_greater_market_blocks_when_market_disagrees():
    # Same rule applies to threshold markets.
    ok, _ = check_market_disagreement(
        our_prob_yes=0.10, yes_price_cents=55, strike_type="greater"
    )
    assert ok is False


def test_model_more_bullish_than_market_passes():
    # Our model says YES=80%, market prices YES=30% — that's our edge, don't block.
    ok, _ = check_market_disagreement(
        our_prob_yes=0.80, yes_price_cents=30, strike_type="between"
    )
    assert ok is True
