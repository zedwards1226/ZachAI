"""MEMORY AGENT — Runs at 6:00 PM ET daily.

Analyzes last 3 days of daily candles: trend vs chop, sweep levels, direction.
Calculates morning bias for next day. Keeps rolling 10-day history.
Writes output to state/memory.json.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pytz

from config import TIMEZONE
from models import Bias, DayType, CandleDirection
from services.state_manager import read_state, write_state
from services.tv_client import get_client

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


async def run() -> dict:
    """Run the memory agent. Returns the memory data dict."""
    logger.info("Memory agent starting")
    tv = await get_client()

    try:
        # Get last 10+ daily bars
        await tv.set_timeframe("D")
        daily_bars = await tv.get_ohlcv(count=15)

        if len(daily_bars) < 3:
            logger.error("Not enough daily bars for memory analysis: %d", len(daily_bars))
            return _write_error("Not enough daily data")

        # Analyze each of the last 10 days
        analyses = []
        for bar in daily_bars[-10:]:
            analyses.append(_analyze_day(bar))

        # Last 3 days for bias calculation
        last_3 = analyses[-3:]

        # Detect sweep levels across last 5 days
        sweep_levels = _detect_sweep_levels(daily_bars[-5:])

        # Calculate morning bias
        bias, confidence, reasons = _calculate_bias(last_3, daily_bars, sweep_levels)

        # Rolling 10-day stats
        ranges = [a["range_pts"] for a in analyses]
        trend_count = sum(1 for a in analyses if a["day_type"] == DayType.TREND.value)
        chop_count = sum(1 for a in analyses if a["day_type"] == DayType.CHOP.value)

        bullish_count = sum(1 for a in analyses if a["direction"] == CandleDirection.BULLISH.value)
        bearish_count = len(analyses) - bullish_count

        data = {
            "date": datetime.now(ET).strftime("%Y-%m-%d"),
            "morning_bias": bias.value,
            "bias_confidence": round(confidence, 2),
            "bias_reasons": reasons,
            "recent_days": last_3,
            "sweep_levels": sweep_levels,
            "rolling_10day": {
                "avg_range": round(sum(ranges) / len(ranges), 2) if ranges else 0,
                "trend_days": trend_count,
                "chop_days": chop_count,
                "dominant_direction": "BULLISH" if bullish_count > bearish_count else "BEARISH",
                "bullish_days": bullish_count,
                "bearish_days": bearish_count,
            },
        }

        write_state("memory", data)
        logger.info("Memory agent complete: bias=%s, confidence=%.2f", bias.value, confidence)
        return data

    except Exception as e:
        logger.error("Memory agent error: %s", e, exc_info=True)
        return _write_error(str(e))
    finally:
        try:
            await tv.set_timeframe("5")
        except Exception:
            pass


def _analyze_day(bar: dict) -> dict:
    """Classify a daily bar as TREND or CHOP."""
    high = bar["high"]
    low = bar["low"]
    opn = bar["open"]
    close = bar["close"]
    total_range = high - low

    if total_range == 0:
        return _day_dict(bar, DayType.CHOP, CandleDirection.BULLISH, 0, 0)

    body = abs(close - opn)
    body_pct = body / total_range

    # Direction
    direction = CandleDirection.BULLISH if close > opn else CandleDirection.BEARISH

    # TREND: body > 50% of range AND close near high/low (within 20% of range)
    if direction == CandleDirection.BULLISH:
        close_position = (close - low) / total_range  # 1.0 = closed at high
    else:
        close_position = (high - close) / total_range  # 1.0 = closed at low

    day_type = DayType.TREND if (body_pct > 0.50 and close_position > 0.70) else DayType.CHOP

    return _day_dict(bar, day_type, direction, total_range, body_pct)


def _day_dict(bar: dict, day_type: DayType, direction: CandleDirection,
              range_pts: float, body_pct: float) -> dict:
    """Create a day analysis dict."""
    bar_dt = datetime.fromtimestamp(bar["time"], tz=pytz.utc).astimezone(ET)
    return {
        "date": bar_dt.strftime("%Y-%m-%d"),
        "day_type": day_type.value,
        "direction": direction.value,
        "range_pts": round(range_pts, 2),
        "body_pct": round(body_pct, 2),
        "high": round(bar["high"], 2),
        "low": round(bar["low"], 2),
        "close": round(bar["close"], 2),
    }


def _detect_sweep_levels(bars: list[dict]) -> list[dict]:
    """Detect levels where price swept a prior high/low and reversed."""
    sweeps = []

    for i in range(2, len(bars)):
        curr = bars[i]
        prev = bars[i - 1]

        # Bearish sweep: current high exceeds prior high, but closes below it
        if curr["high"] > prev["high"] and curr["close"] < prev["high"]:
            dt = datetime.fromtimestamp(curr["time"], tz=pytz.utc).astimezone(ET)
            sweeps.append({
                "level": round(prev["high"], 2),
                "level_type": "high",
                "swept_date": dt.strftime("%Y-%m-%d"),
                "direction": "bearish_sweep",
            })

        # Bullish sweep: current low breaks prior low, but closes above it
        if curr["low"] < prev["low"] and curr["close"] > prev["low"]:
            dt = datetime.fromtimestamp(curr["time"], tz=pytz.utc).astimezone(ET)
            sweeps.append({
                "level": round(prev["low"], 2),
                "level_type": "low",
                "swept_date": dt.strftime("%Y-%m-%d"),
                "direction": "bullish_sweep",
            })

    return sweeps


def _calculate_bias(last_3: list[dict], all_bars: list[dict],
                    sweeps: list[dict]) -> tuple[Bias, float, list[str]]:
    """Calculate morning bias based on recent days, sweeps, and overnight action."""
    reasons = []
    bull_score = 0
    bear_score = 0

    # Factor 1: Direction of last 3 days
    bull_days = sum(1 for d in last_3 if d["direction"] == CandleDirection.BULLISH.value)
    bear_days = 3 - bull_days

    if bull_days >= 2:
        bull_score += 2
        reasons.append(f"{bull_days}/3 days bullish")
    elif bear_days >= 2:
        bear_score += 2
        reasons.append(f"{bear_days}/3 days bearish")

    # Factor 2: Trend vs chop pattern
    trend_days = sum(1 for d in last_3 if d["day_type"] == DayType.TREND.value)
    if trend_days >= 2:
        # Strong trend continuation signal
        last_trend = next(
            (d for d in reversed(last_3) if d["day_type"] == DayType.TREND.value), None
        )
        if last_trend:
            if last_trend["direction"] == CandleDirection.BULLISH.value:
                bull_score += 1
                reasons.append("Trend continuation (bullish trend days)")
            else:
                bear_score += 1
                reasons.append("Trend continuation (bearish trend days)")

    # Factor 3: Overnight sweep reversal
    for sweep in sweeps:
        if sweep["direction"] == "bullish_sweep":
            bull_score += 1
            reasons.append(f"Swept low at {sweep['level']} and recovered (bullish)")
        elif sweep["direction"] == "bearish_sweep":
            bear_score += 1
            reasons.append(f"Swept high at {sweep['level']} and rejected (bearish)")

    # Factor 4: Close relative to range (last day)
    if last_3:
        last = last_3[-1]
        if last["body_pct"] > 0.6:
            if last["direction"] == CandleDirection.BULLISH.value:
                bull_score += 1
                reasons.append("Strong bullish close yesterday")
            else:
                bear_score += 1
                reasons.append("Strong bearish close yesterday")

    # Calculate bias and confidence
    total = bull_score + bear_score
    if total == 0:
        return Bias.NEUTRAL, 0.5, ["No clear signals"]

    if bull_score > bear_score:
        confidence = bull_score / (total + 1)  # +1 to dampen extreme values
        return Bias.BULLISH_BIAS, min(confidence, 0.9), reasons
    elif bear_score > bull_score:
        confidence = bear_score / (total + 1)
        return Bias.BEARISH_BIAS, min(confidence, 0.9), reasons
    else:
        return Bias.NEUTRAL, 0.5, reasons + ["Bull/bear signals balanced"]


def _write_error(error_msg: str) -> dict:
    data = {
        "date": datetime.now(ET).strftime("%Y-%m-%d"),
        "error": error_msg,
        "morning_bias": Bias.NEUTRAL.value,
        "bias_confidence": 0,
        "bias_reasons": [f"Error: {error_msg}"],
    }
    write_state("memory", data)
    return data
