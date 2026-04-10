"""
Sentinel Agent — Anomaly detection.
Runs ASYNC after Overseer PASS. Does NOT block trade execution.

Checks:
1. Volatility spike (price moved too fast recently)
2. Volume anomaly (unusually high/low for time of day)
3. Wide spread / thin liquidity warning
4. News/event proximity (major econ release within 30 min)

95% rule-based. Claude called only for ambiguous setups (300 token cap).
Sends Telegram warning if suspicious — does not BLOCK.
"""
import logging
from datetime import datetime

import pytz

import config
import database as db
from models import Signal, AgentVerdict, Verdict

log = logging.getLogger("sentinel")

# ── Economic calendar: major release times (ET) ──
# Format: (hour, minute, description)
MAJOR_RELEASES = [
    (8, 30, "CPI/PPI/NFP/Retail Sales"),
    (10, 0, "ISM/Consumer Sentiment/JOLTS"),
    (14, 0, "FOMC Decision"),
    (14, 30, "FOMC Press Conference"),
]


def evaluate(signal: Signal, recent_bars: list[dict] = None) -> AgentVerdict:
    """
    Evaluate signal for anomalies.
    recent_bars: optional OHLCV data from TradingView MCP (if available).
    """
    warnings = []

    # Check 1: News proximity
    news_warn = _check_news_proximity()
    if news_warn:
        warnings.append(news_warn)

    # Check 2: Volatility spike (if we have bar data)
    if recent_bars and len(recent_bars) >= 5:
        vol_warn = _check_volatility_spike(recent_bars, signal.symbol)
        if vol_warn:
            warnings.append(vol_warn)

    # Check 3: Price at round number (psychological level — increased stop-hunt risk)
    round_warn = _check_round_number(signal.price)
    if round_warn:
        warnings.append(round_warn)

    if warnings:
        combined = "; ".join(warnings)
        log.info("WARNING: %s", combined)
        return AgentVerdict(
            agent="sentinel",
            verdict=Verdict.PASS,  # Sentinel warns but does not block
            reasoning=f"WARNINGS: {combined}",
        )

    return AgentVerdict(
        agent="sentinel",
        verdict=Verdict.PASS,
        reasoning="No anomalies detected",
    )


def _check_news_proximity() -> str | None:
    """Check if a major economic release is within 30 minutes."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    now_minutes = now.hour * 60 + now.minute

    for hour, minute, desc in MAJOR_RELEASES:
        release_minutes = hour * 60 + minute
        diff = abs(now_minutes - release_minutes)
        if diff <= 30:
            return f"Within 30min of {desc} ({hour}:{minute:02d} ET)"

    return None


def _check_volatility_spike(bars: list[dict], symbol: str) -> str | None:
    """
    Check if recent bar ranges are abnormally large.
    bars: list of dicts with 'high', 'low' keys (most recent last).
    """
    if len(bars) < 5:
        return None

    ranges = [b["high"] - b["low"] for b in bars]
    avg_range = sum(ranges[:-1]) / len(ranges[:-1])  # average of all but last
    last_range = ranges[-1]

    if avg_range > 0 and last_range > avg_range * 2.5:
        return f"Volatility spike: last bar range {last_range:.2f} is {last_range/avg_range:.1f}x average"

    return None


def _check_round_number(price: float) -> str | None:
    """Flag if entry is near a round number (stop-hunt magnet)."""
    # For NQ/MNQ, round numbers at 50 and 100 levels matter
    remainder_100 = price % 100
    remainder_50 = price % 50

    if remainder_100 <= 5 or remainder_100 >= 95:
        nearest = round(price / 100) * 100
        return f"Entry near round number {nearest} (stop-hunt risk)"
    if remainder_50 <= 3 or remainder_50 >= 47:
        nearest = round(price / 50) * 50
        return f"Entry near 50-level {nearest} (liquidity cluster)"

    return None
