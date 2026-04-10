"""
Sweep Detector Agent — Smart money pattern detection.
Pure rule-based, zero Claude tokens. Runs ASYNC after Overseer.

Identifies:
1. Liquidity sweeps (price takes out a prior high/low then reverses)
2. Equal highs/lows taken (engineered liquidity pools)
3. Stop hunt patterns (wick through level then close back inside)

Uses OHLCV data from TradingView MCP when available.
Returns sweep direction + confidence score.
"""
import logging
from models import Signal, AgentVerdict, Verdict

log = logging.getLogger("sweep_detector")


def evaluate(signal: Signal, recent_bars: list[dict] = None) -> AgentVerdict:
    """
    Analyze recent price action for smart money sweep patterns.
    recent_bars: list of OHLCV dicts with keys: open, high, low, close, volume
                 (most recent bar last). Need at least 10 bars for meaningful analysis.
    """
    if not recent_bars or len(recent_bars) < 10:
        return AgentVerdict(
            agent="sweep_detector",
            verdict=Verdict.PASS,
            reasoning="Insufficient bar data for sweep analysis",
        )

    results = []

    # Check for liquidity sweep
    sweep = _detect_liquidity_sweep(recent_bars)
    if sweep:
        results.append(sweep)

    # Check for equal highs/lows taken
    eq_levels = _detect_equal_levels_taken(recent_bars)
    if eq_levels:
        results.append(eq_levels)

    # Check for stop hunt wick
    wick = _detect_stop_hunt_wick(recent_bars)
    if wick:
        results.append(wick)

    if results:
        combined = "; ".join(results)
        # Determine if sweep direction confirms or conflicts with signal
        signal_side = "bullish" if signal.action == "buy" else "bearish"
        sweep_bias = _get_sweep_bias(results)

        if sweep_bias and sweep_bias != signal_side:
            log.info("SWEEP CONFLICT: signal=%s but sweep suggests %s — %s",
                     signal_side, sweep_bias, combined)
            return AgentVerdict(
                agent="sweep_detector",
                verdict=Verdict.PASS,  # warn, don't block
                reasoning=f"SWEEP CONFLICT ({sweep_bias} bias vs {signal_side} signal): {combined}",
            )

        log.info("SWEEP CONFIRMS: %s", combined)
        return AgentVerdict(
            agent="sweep_detector",
            verdict=Verdict.PASS,
            reasoning=f"Sweep confirms {signal_side}: {combined}",
        )

    return AgentVerdict(
        agent="sweep_detector",
        verdict=Verdict.PASS,
        reasoning="No sweep patterns detected",
    )


def _detect_liquidity_sweep(bars: list[dict]) -> str | None:
    """
    Liquidity sweep: price takes out a prior swing high/low, then reverses.
    Look at last 3 bars vs prior 7 bars.
    """
    prior = bars[:-3]
    recent = bars[-3:]

    prior_high = max(b["high"] for b in prior)
    prior_low = min(b["low"] for b in prior)

    # Bearish sweep: price broke above prior high then closed below it
    last_close = recent[-1]["close"]
    if any(b["high"] > prior_high for b in recent) and last_close < prior_high:
        return f"Bearish liquidity sweep (high {prior_high:.2f} taken then rejected)"

    # Bullish sweep: price broke below prior low then closed above it
    if any(b["low"] < prior_low for b in recent) and last_close > prior_low:
        return f"Bullish liquidity sweep (low {prior_low:.2f} taken then rejected)"

    return None


def _detect_equal_levels_taken(bars: list[dict]) -> str | None:
    """
    Equal highs/lows: 2+ bars with nearly identical highs or lows (engineered liquidity).
    Then a subsequent bar sweeps through.
    """
    # Check for equal highs in first 7 bars
    prior = bars[:-3]
    recent = bars[-3:]
    tolerance = 2.0  # points

    highs = [b["high"] for b in prior]
    lows = [b["low"] for b in prior]

    # Find clusters of equal highs
    for i, h in enumerate(highs):
        matches = sum(1 for hh in highs if abs(hh - h) <= tolerance)
        if matches >= 2:
            # Check if recent bars swept through this level
            if any(b["high"] > h + tolerance for b in recent):
                return f"Equal highs at {h:.2f} swept (engineered liquidity)"

    # Find clusters of equal lows
    for i, lo in enumerate(lows):
        matches = sum(1 for ll in lows if abs(ll - lo) <= tolerance)
        if matches >= 2:
            if any(b["low"] < lo - tolerance for b in recent):
                return f"Equal lows at {lo:.2f} swept (engineered liquidity)"

    return None


def _detect_stop_hunt_wick(bars: list[dict]) -> str | None:
    """
    Stop hunt wick: large wick (>60% of bar range) through a level, body closes back inside.
    Check the most recent bar only.
    """
    bar = bars[-1]
    full_range = bar["high"] - bar["low"]
    if full_range == 0:
        return None

    body_top = max(bar["open"], bar["close"])
    body_bottom = min(bar["open"], bar["close"])
    body_range = body_top - body_bottom

    upper_wick = bar["high"] - body_top
    lower_wick = body_bottom - bar["low"]

    # Large upper wick = bearish stop hunt
    if upper_wick > full_range * 0.6:
        return f"Bearish stop hunt wick ({upper_wick:.2f} pt upper wick, {upper_wick/full_range*100:.0f}% of range)"

    # Large lower wick = bullish stop hunt
    if lower_wick > full_range * 0.6:
        return f"Bullish stop hunt wick ({lower_wick:.2f} pt lower wick, {lower_wick/full_range*100:.0f}% of range)"

    return None


def _get_sweep_bias(results: list[str]) -> str | None:
    """Extract directional bias from sweep results."""
    bullish = sum(1 for r in results if "bullish" in r.lower())
    bearish = sum(1 for r in results if "bearish" in r.lower())
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    return None
