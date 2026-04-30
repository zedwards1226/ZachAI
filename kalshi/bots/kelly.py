"""
Quarter-Kelly position sizing for binary Kalshi contracts.

Kelly formula for binary bet:
    f* = (p*b - q) / b
where:
    p = our win probability
    q = 1 - p
    b = net odds (payout per unit staked)

For a Kalshi YES contract at price P cents:
    cost per contract  = P / 100
    payout if wins     = 1.00
    net odds b         = (1 - P/100) / (P/100)

Quarter-Kelly: stake = f* * 0.25 * capital
Capped at MAX_BET.
"""
from config import (
    KELLY_FRACTION, MAX_BET, MAX_CONTRACTS, STARTING_CAPITAL,
    BANKROLL_PCT_CAP,
)


def kelly_fraction(our_prob: float, price_cents: int) -> float:
    """
    Compute raw Kelly fraction (0-1) for a YES bet.
    our_prob: our estimated P(yes)
    price_cents: Kalshi YES price in cents (1-99)
    """
    p = max(0.0, min(1.0, our_prob))
    q = 1.0 - p
    cost = price_cents / 100.0
    if cost <= 0 or cost >= 1:
        return 0.0
    b = (1.0 - cost) / cost   # net odds per $ staked
    f = (p * b - q) / b
    return max(0.0, f)


def size_stake(our_prob: float, price_cents: int, bankroll_usd: float) -> dict:
    """
    Stake = min(KELLY_FRACTION × raw_Kelly × bankroll,
                bankroll × BANKROLL_PCT_CAP,
                MAX_BET).

    The middle term (bankroll × 5%) is the hard per-trade ceiling — auto-scales
    as bankroll compounds. MAX_BET is a runaway-bug safety stop, not the
    binding constraint at small bankrolls.
    """
    raw_k        = kelly_fraction(our_prob, price_cents)
    frac_k       = raw_k * KELLY_FRACTION
    kelly_usd    = frac_k * bankroll_usd
    pct_cap_usd  = bankroll_usd * BANKROLL_PCT_CAP
    stake        = min(kelly_usd, pct_cap_usd, MAX_BET)
    stake        = max(0.0, stake)

    cost_per = price_cents / 100.0
    contracts = int(stake / cost_per) if cost_per > 0 else 0
    contracts = min(contracts, MAX_CONTRACTS)  # cap for liquidity
    actual_stake = contracts * cost_per

    return {
        "raw_kelly":     round(raw_k, 4),
        "frac_kelly":    round(frac_k, 4),
        "stake_usd":     round(actual_stake, 2),
        "contracts":     contracts,
        "price_cents":   price_cents,
        "bankroll_used": round(bankroll_usd, 2),
        "kelly_dollars": round(kelly_usd, 2),
        "pct_cap_dollars": round(pct_cap_usd, 2),
    }
