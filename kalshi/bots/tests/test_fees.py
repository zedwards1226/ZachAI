"""Tests for Kalshi fee math.

Sanity-checks the per-trade fee formula against published examples.
Critical because this fee feeds straight into paper P&L — wrong formula =
wrong forecast of live results.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fees import kalshi_fee_usd, net_pnl_after_fee


class TestKalshiFee:
    def test_zero_contracts_zero_fee(self):
        assert kalshi_fee_usd(0, 50) == 0.0

    def test_extreme_prices_zero_fee(self):
        # P=0 or P=1 -> P*(1-P)=0 -> fee=0
        assert kalshi_fee_usd(100, 0) == 0.0
        assert kalshi_fee_usd(100, 100) == 0.0

    def test_max_fee_at_50c(self):
        # 100 contracts @ 50¢: 0.07*100*0.5*0.5*100 = 175.0 mathematically;
        # but 0.07 is not exactly representable in float so the product is
        # 175.0000000000003 → ceil = 176 → $1.76. Correct per Kalshi's
        # published rounding rule (always round UP).
        assert kalshi_fee_usd(100, 50) == 1.76

    def test_lax_longshot_real_example(self):
        # The actual LAX trade: 100ct @ 11¢
        # 0.07 * 100 * 0.11 * 0.89 = 0.6853 -> ceil cents = 69 -> $0.69
        assert kalshi_fee_usd(100, 11) == 0.69

    def test_small_size_rounds_up(self):
        # 1 contract @ 50¢: 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> ceil cent = 2 -> $0.02
        assert kalshi_fee_usd(1, 50) == 0.02

    def test_no_side_bet_around_two_thirds(self):
        # 20 contracts @ 66¢: 0.07 * 20 * 0.66 * 0.34 = 0.31416 -> ceil = $0.32
        assert kalshi_fee_usd(20, 66) == 0.32


class TestNetPnLAfterFee:
    def test_lax_winner_after_fee(self):
        # 100ct @ 11¢ WIN: gross = 100 - 11 = $89, fee = $0.69 -> $88.31
        assert net_pnl_after_fee(100, 11, won=True) == pytest.approx(88.31, abs=0.01)

    def test_at_money_winner_after_fee(self):
        # 100ct @ 50¢ WIN: gross = 100 - 50 = $50, fee = $1.76 -> $48.24
        assert net_pnl_after_fee(100, 50, won=True) == pytest.approx(48.24, abs=0.01)

    def test_loss_subtracts_stake_and_fee(self):
        # 100ct @ 11¢ LOSS: stake = $11, fee = $0.69 -> -$11.69
        assert net_pnl_after_fee(100, 11, won=False) == pytest.approx(-11.69, abs=0.01)

    def test_loss_at_money(self):
        # 100ct @ 50¢ LOSS: stake = $50, fee = $1.76 -> -$51.76
        assert net_pnl_after_fee(100, 50, won=False) == pytest.approx(-51.76, abs=0.01)

    def test_no_side_winner(self):
        # 22ct @ 59¢ NO that won (the DEN +$9.02 paper trade):
        # gross = 22*(1-0.59) = $9.02
        # fee = ceil(0.07*22*0.59*0.41*100)/100 = ceil(37.25)/100 = $0.38
        # net = $9.02 - $0.38 = $8.64 (real money equivalent)
        result = net_pnl_after_fee(22, 59, won=True)
        assert result == pytest.approx(8.64, abs=0.01)
