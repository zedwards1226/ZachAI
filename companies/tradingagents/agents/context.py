"""
Context Agent — Market regime and session quality assessment.
Runs ASYNC after Overseer. Rule-based for clear regimes, Claude for ambiguous.

Evaluates:
1. Session quality (London/NY overlap, dead zones, power hour)
2. Volatility regime (low/normal/high based on ATR)
3. Trend bias (bullish/neutral/bearish from EMA alignment)
4. Time-of-day edge (best and worst times for ORB strategy)

Returns: market_bias, confidence, session_quality
"""
import logging
from datetime import datetime

import pytz

import config
from models import Signal, AgentVerdict, Verdict

log = logging.getLogger("context")

# ── Session quality map (ET hours) ──
# A = prime, B = good, C = avoid
SESSION_QUALITY = {
    # Pre-market
    4: "C", 5: "C", 6: "C", 7: "B", 8: "B",
    # NY session
    9: "A",   # NY open — highest volume
    10: "A",  # ORB prime window
    11: "B",  # lunch drift starts
    12: "C",  # lunch dead zone
    13: "C",  # lunch dead zone
    14: "B",  # post-lunch recovery
    15: "A",  # power hour
    16: "C",  # after hours
}


def evaluate(signal: Signal, indicators: dict = None) -> AgentVerdict:
    """
    Assess market context.
    indicators: optional dict with keys like 'atr', 'ema_20', 'ema_50', 'ema_200', 'rsi'
                from TradingView MCP data_get_study_values.
    """
    assessments = []

    # 1. Session quality
    session = _assess_session_quality()
    assessments.append(session)

    # 2. Volatility regime (if ATR available)
    if indicators and "atr" in indicators:
        vol = _assess_volatility(indicators["atr"], signal.symbol)
        assessments.append(vol)

    # 3. Trend bias (if EMAs available)
    if indicators and all(k in indicators for k in ("ema_20", "ema_50")):
        trend = _assess_trend(indicators, signal.price)
        assessments.append(trend)

    # 4. RSI extreme check
    if indicators and "rsi" in indicators:
        rsi = _assess_rsi(indicators["rsi"], signal.action)
        if rsi:
            assessments.append(rsi)

    combined = "; ".join(assessments)
    log.info("Context: %s", combined)

    return AgentVerdict(
        agent="context",
        verdict=Verdict.PASS,
        reasoning=combined,
    )


def _assess_session_quality() -> str:
    """Rate current session window quality."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    hour = now.hour
    quality = SESSION_QUALITY.get(hour, "C")

    labels = {"A": "PRIME", "B": "GOOD", "C": "DEAD ZONE"}
    return f"Session: {labels[quality]} ({now.strftime('%I:%M%p')} ET)"


def _assess_volatility(atr: float, symbol: str) -> str:
    """Classify volatility regime based on ATR."""
    # Typical ATR ranges for NQ (15min bars):
    # Low: <15, Normal: 15-40, High: >40
    # For MNQ same points, just smaller dollar impact
    thresholds = {
        "NQ1!": (15, 40),
        "MNQ1!": (15, 40),
        "ES1!": (5, 15),
        "MES1!": (5, 15),
    }
    low, high = thresholds.get(symbol.upper(), (10, 30))

    if atr < low:
        return f"Volatility: LOW (ATR={atr:.1f}, <{low})"
    elif atr > high:
        return f"Volatility: HIGH (ATR={atr:.1f}, >{high})"
    return f"Volatility: NORMAL (ATR={atr:.1f})"


def _assess_trend(indicators: dict, price: float) -> str:
    """Assess trend from EMA alignment."""
    ema_20 = indicators["ema_20"]
    ema_50 = indicators["ema_50"]
    ema_200 = indicators.get("ema_200")

    if ema_200:
        if price > ema_20 > ema_50 > ema_200:
            return "Trend: STRONG BULLISH (price > 20 > 50 > 200 EMA)"
        if price < ema_20 < ema_50 < ema_200:
            return "Trend: STRONG BEARISH (price < 20 < 50 < 200 EMA)"

    if price > ema_20 > ema_50:
        return "Trend: BULLISH (price > 20 > 50 EMA)"
    if price < ema_20 < ema_50:
        return "Trend: BEARISH (price < 20 < 50 EMA)"

    return "Trend: NEUTRAL/CHOPPY (EMAs tangled)"


def _assess_rsi(rsi: float, action: str) -> str | None:
    """Warn if RSI is extreme and conflicts with signal direction."""
    if action == "buy" and rsi > 75:
        return f"RSI WARNING: overbought ({rsi:.1f}) on buy signal"
    if action == "sell" and rsi < 25:
        return f"RSI WARNING: oversold ({rsi:.1f}) on sell signal"
    return None
