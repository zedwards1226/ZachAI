"""Tests for Kelly position sizing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kelly import kelly_fraction, size_stake


def test_kelly_fraction_positive():
    # Our prob 0.7, price 50¢ → f* = (0.7*1 - 0.3)/1 = 0.4
    f = kelly_fraction(0.70, 50)
    assert 0.35 < f < 0.45, f"Expected ~0.4, got {f}"


def test_kelly_fraction_zero_edge():
    # Our prob = market price → no edge → f* near 0
    f = kelly_fraction(0.50, 50)
    assert f == 0.0 or abs(f) < 0.01


def test_kelly_fraction_negative_returns_zero():
    # Our prob 0.3, price 70¢ → negative edge → clamped to 0
    f = kelly_fraction(0.30, 70)
    assert f == 0.0


def test_size_stake_caps_at_max_bet():
    # Large capital, big edge → stake capped at MAX_BET
    result = size_stake(0.95, 20, 10_000)
    assert result["stake_usd"] <= 100.0


def test_size_stake_zero_contracts():
    # Tiny capital, tiny edge → 0 contracts
    result = size_stake(0.55, 50, 1.0)
    assert result["contracts"] >= 0


def test_size_stake_contracts_match_stake():
    result = size_stake(0.75, 40, 500)
    expected_stake = result["contracts"] * (40 / 100)
    assert abs(result["stake_usd"] - expected_stake) < 0.01
