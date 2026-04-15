"""
Edge calculation: compare GFS ensemble probability vs Kalshi implied probability.

Uses 31-member GFS ensemble from Open-Meteo. Probability = fraction of members
above/below threshold. No Gaussian assumptions — captures skewness, multimodal
forecasts, and real forecast uncertainty.

Edge = our_prob - kalshi_implied_prob  (positive = YES underpriced)
"""


def prob_exceeds(member_highs: list[float], strike_f: float) -> float:
    """
    P(actual_high > strike) = fraction of ensemble members above strike.
    Kalshi "greater than" is STRICT: YES wins only if actual > strike (not >=).
    Clipped to [0.03, 0.97] to prevent ruin on unanimous-but-wrong ensembles.
    """
    if not member_highs:
        return 0.5
    count = sum(1 for h in member_highs if h > strike_f)
    raw = count / len(member_highs)
    return max(0.03, min(0.97, raw))


def prob_between(member_highs: list[float], floor_f: float, cap_f: float) -> float:
    """
    P(floor_f <= actual_high <= cap_f) for between-style Kalshi markets.
    YES wins if actual high is >= floor AND <= cap.
    Clipped to [0.03, 0.97].
    """
    if not member_highs:
        return 0.5
    count = sum(1 for h in member_highs if floor_f <= h <= cap_f)
    raw = count / len(member_highs)
    return max(0.03, min(0.97, raw))


def compute_edge(our_prob: float, kalshi_price_cents: int) -> float:
    """
    edge = our_prob - kalshi_implied_prob
    Positive edge -> bet YES.  Negative edge -> bet NO.
    """
    kalshi_prob = kalshi_price_cents / 100.0
    return round(our_prob - kalshi_prob, 4)


def best_side(edge: float) -> str:
    """Return 'yes' if positive edge, 'no' if negative."""
    return "yes" if edge >= 0 else "no"


def effective_edge(edge: float) -> float:
    """Absolute edge regardless of side."""
    return abs(edge)


def ensemble_confidence(member_highs: list[float], strike_f: float) -> float:
    """
    Confidence = max(above_fraction, below_fraction).
    High confidence (0.9+) means ensemble strongly agrees.
    Low confidence (0.5) means ensemble is split.
    """
    if not member_highs:
        return 0.5
    above = sum(1 for h in member_highs if h > strike_f)
    total = len(member_highs)
    return max(above, total - above) / total


def parse_strike_from_ticker(ticker: str) -> float | None:
    """
    Extract strike temperature from Kalshi ticker.
    Handles both formats:
      - Threshold: KXHIGHNY-26APR05-T67       -> 67.0
      - Between:   KXHIGHNY-26APR05-B60.5     -> 60.5 (midpoint of the range)
    Returns float or None.
    """
    try:
        parts = ticker.split("-")
        for part in parts:
            if part.startswith("T") and part[1:].replace(".", "").replace("-", "").isdigit():
                return float(part[1:])
            if part.startswith("B") and part[1:].replace(".", "").replace("-", "").isdigit():
                return float(part[1:])
        return None
    except Exception:
        return None
