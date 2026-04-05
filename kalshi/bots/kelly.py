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
from config import KELLY_FRACTION, MAX_BET, STARTING_CAPITAL


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


def size_stake(our_prob: float, price_cents: int, capital_usd: float) -> dict:
    """
    Returns:
        {
          "raw_kelly":  float,
          "frac_kelly": float,  # KELLY_FRACTION * raw_kelly
          "stake_usd":  float,  # capped at MAX_BET
          "contracts":  int,
          "price_cents": int,
        }
    """
    raw_k   = kelly_fraction(our_prob, price_cents)
    frac_k  = raw_k * KELLY_FRACTION
    stake   = min(frac_k * capital_usd, MAX_BET)
    stake   = max(0.0, stake)

    cost_per = price_cents / 100.0
    contracts = int(stake / cost_per) if cost_per > 0 else 0
    actual_stake = contracts * cost_per

    return {
        "raw_kelly":   round(raw_k, 4),
        "frac_kelly":  round(frac_k, 4),
        "stake_usd":   round(actual_stake, 2),
        "contracts":   contracts,
        "price_cents": price_cents,
    }


def size_stake_no(our_prob_yes: float, no_price_cents: int, capital_usd: float) -> dict:
    """
    For betting NO: our_prob_no = 1 - our_prob_yes
    """
    our_prob_no = 1.0 - our_prob_yes
    return size_stake(our_prob_no, no_price_cents, capital_usd)
