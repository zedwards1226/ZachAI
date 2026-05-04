"""Kalshi trading fee math.

Kalshi's per-trade fee formula (published, charged on every BUY):
    fee_dollars = ceil(0.07 * C * P * (1 - P) * 100) / 100

Where:
    C = number of contracts (positive integer)
    P = contract price in dollars (0 <= P <= 1)

Properties:
- Fee is ZERO at the extremes (P=0 or P=1) — selling at-the-money is cheap
- Fee is MAX at P=0.5 — about $1.75 per 100 contracts at 50¢
- Fee is charged once on entry (no exit fee — contracts settle at $0 or $1)

Examples:
    100 contracts @ $0.11  -> fee = $0.69   (LAX-style longshot YES)
    100 contracts @ $0.50  -> fee = $1.75   (mid-market max-fee)
    20  contracts @ $0.66  -> fee = $0.32   (NO-side bet)
    1   contract  @ $0.50  -> fee = $0.02

NOTE: Kalshi has occasionally adjusted this formula. As of 2025 it is the
standard fee schedule for non-political markets. Source: Kalshi help docs.
"""
from __future__ import annotations

import math


def kalshi_fee_usd(contracts: int, price_cents: int) -> float:
    """Compute the Kalshi trading fee in USD for a single trade.

    Args:
        contracts: number of contracts in the order (must be > 0)
        price_cents: contract price in cents (1-99)

    Returns:
        Fee in USD, rounded UP to the nearest cent (Kalshi's published
        rounding rule).
    """
    if contracts <= 0:
        return 0.0
    p = price_cents / 100.0
    if not 0.0 < p < 1.0:
        # Edge price means the fee floor formula evaluates to 0 anyway
        return 0.0
    raw_cents = 0.07 * contracts * p * (1.0 - p) * 100.0
    fee_cents = math.ceil(raw_cents)
    return fee_cents / 100.0


def net_pnl_after_fee(
    contracts: int,
    price_cents: int,
    won: bool,
) -> float:
    """Compute net P&L for a settled binary contract trade, fees included.

    Win:  payout = $1 per contract, minus stake (price), minus entry fee
    Loss: P&L = -stake - entry fee

    The entry fee is paid on every trade regardless of outcome.
    """
    fee = kalshi_fee_usd(contracts, price_cents)
    stake_dollars = contracts * price_cents / 100.0
    if won:
        payout_dollars = contracts * 1.0  # each contract pays $1 on win
        return payout_dollars - stake_dollars - fee
    return -stake_dollars - fee
