"""
Edge calculation: compare our weather forecast probability vs Kalshi implied probability.

For KXHIGH markets: "Will the high temperature exceed STRIKE °F today?"
Our model: normal distribution around Open-Meteo forecast high, σ = FORECAST_SIGMA_F
Edge = our_prob - kalshi_implied_prob  (positive = we think YES is underpriced)
"""
from scipy.stats import norm
from config import FORECAST_SIGMA_F


def prob_exceeds(forecast_high_f: float, strike_f: float,
                 sigma: float = FORECAST_SIGMA_F) -> float:
    """
    P(actual_high > strike) given forecast_high_f ~ N(forecast_high_f, sigma²).
    Uses survival function of normal distribution.
    """
    return float(norm.sf(strike_f, loc=forecast_high_f, scale=sigma))


def compute_edge(our_prob: float, kalshi_price_cents: int) -> float:
    """
    edge = our_prob - kalshi_implied_prob
    kalshi_price_cents: 0-100 (YES price in cents per contract)
    Positive edge → bet YES.  Negative edge → bet NO.
    """
    kalshi_prob = kalshi_price_cents / 100.0
    return round(our_prob - kalshi_prob, 4)


def best_side(edge: float) -> str:
    """Return 'yes' if positive edge, 'no' if negative."""
    return "yes" if edge >= 0 else "no"


def effective_edge(edge: float) -> float:
    """Absolute edge regardless of side."""
    return abs(edge)


def find_best_market(markets: list[dict], forecast_high_f: float) -> dict | None:
    """
    Given a list of KXHIGH market dicts for a city, find the one with
    the largest absolute edge vs our forecast.

    Each market dict must have:
        ticker, yes_bid (cents), strike_f (parsed from ticker)

    Returns best candidate dict or None.
    """
    if not markets:
        return None

    best = None
    best_edge = 0.0

    for m in markets:
        strike = m.get("strike_f")
        yes_price = m.get("yes_price_cents")
        if strike is None or yes_price is None:
            continue

        our_p = prob_exceeds(forecast_high_f, strike)
        e     = compute_edge(our_p, yes_price)
        ae    = effective_edge(e)

        if ae > best_edge:
            best_edge = ae
            best = {**m, "our_prob": our_p, "edge": e, "abs_edge": ae}

    return best


def prob_between(forecast_high_f: float, floor_f: float, cap_f: float,
                 sigma: float = None) -> float:
    """
    P(floor_f <= actual_high < cap_f) for between-style Kalshi markets.
    Uses CDF difference of normal distribution.
    """
    if sigma is None:
        from config import FORECAST_SIGMA_F
        sigma = FORECAST_SIGMA_F
    return float(norm.cdf(cap_f, loc=forecast_high_f, scale=sigma)
                 - norm.cdf(floor_f, loc=forecast_high_f, scale=sigma))


def parse_strike_from_ticker(ticker: str) -> float | None:
    """
    Extract strike temperature from Kalshi ticker.
    Handles both formats:
      - Threshold: KXHIGHNY-26APR05-T67       → 67.0
      - Between:   KXHIGHNY-26APR05-B60.5     → 60.5 (midpoint of the range)
    Returns float or None.
    """
    try:
        parts = ticker.split("-")
        for part in parts:
            if part.startswith("T") and part[1:].replace(".", "").isdigit():
                return float(part[1:])
            if part.startswith("B") and part[1:].replace(".", "").isdigit():
                # B60.5 means the between range centered at 60.5 (floor=60, cap=61)
                return float(part[1:])
        return None
    except Exception:
        return None
