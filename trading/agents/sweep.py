"""SWEEP DETECTOR — Real-time liquidity pool detection and sweep classification.

Runs continuously every 15 seconds during 9:00-11:00 AM ET.
Detects equal highs/lows (liquidity pools) on the 5-min chart.
Classifies pool takeouts as SWEEP_CONFIRMED or GENUINE_BREAK.
Writes output to state/sweep.json.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pytz

from config import TIMEZONE, SWEEP_WINDOW
from models import SweepType
from services.state_manager import read_state, write_state
from services.tv_client import get_client
from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# Tolerance for equal highs/lows (MNQ points)
EQUAL_LEVEL_TOLERANCE = 2.0
# Minimum bars with equal levels to form a pool
MIN_POOL_BARS = 2
# Max candles for sweep reversal confirmation
SWEEP_REVERSAL_CANDLES = 2
# Minimum wick percentage for stop hunt detection
STOP_HUNT_WICK_PCT = 0.60

# Session state
_known_pools: list[dict] = []
_sweeps: list[dict] = []
_session_date: Optional[str] = None


def _reset_session():
    global _known_pools, _sweeps, _session_date
    _known_pools = []
    _sweeps = []
    _session_date = datetime.now(ET).strftime("%Y-%m-%d")


async def poll() -> Optional[dict]:
    """Called every 15 seconds. Detects liquidity pools and sweeps."""
    global _session_date

    now = datetime.now(ET)
    today = now.strftime("%Y-%m-%d")

    # Reset on new day
    if _session_date != today:
        _reset_session()

    # Check window
    start_h, start_m = SWEEP_WINDOW[0]
    end_h, end_m = SWEEP_WINDOW[1]
    window_start = now.replace(hour=start_h, minute=start_m, second=0)
    window_end = now.replace(hour=end_h, minute=end_m, second=0)

    if now < window_start or now > window_end:
        return None

    tv = await get_client()

    # Get recent 5-min bars
    bars = await tv.get_ohlcv(count=30)
    if len(bars) < 10:
        return None

    # --- Step 1: Detect equal highs/lows (liquidity pools) ---
    new_pools = _detect_equal_levels(bars)
    for pool in new_pools:
        if not _pool_already_known(pool):
            _known_pools.append(pool)
            logger.info("New liquidity pool: %s at %.2f (%d bars)",
                        pool["pool_type"], pool["level"], pool["bar_count"])

    # --- Step 2: Check if any pool was taken out ---
    latest = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else None
    prev2 = bars[-3] if len(bars) >= 3 else None

    for pool in list(_known_pools):
        sweep_result = _check_pool_takeout(pool, latest, prev, prev2)
        if sweep_result:
            _sweeps.append(sweep_result)
            _known_pools.remove(pool)

            logger.info("SWEEP: %s %s at %.2f — %s",
                        sweep_result["sweep_type"], sweep_result["direction"],
                        sweep_result["level"], sweep_result.get("detail", ""))

            # Send Telegram alert
            await telegram.notify_sweep(
                direction=sweep_result["direction"],
                level=sweep_result["level"],
                sweep_type=sweep_result["sweep_type"],
            )

    # --- Step 3: Detect stop hunt wicks ---
    wick_sweep = _detect_stop_hunt_wick(bars)
    if wick_sweep and not _sweep_already_logged(wick_sweep):
        _sweeps.append(wick_sweep)
        logger.info("Stop hunt wick: %s at %.2f", wick_sweep["direction"], wick_sweep["level"])

    # --- Step 4: Determine sweep bias ---
    bias, bias_reason = _calculate_sweep_bias()

    # Write state
    data = {
        "date": today,
        "active_pools": _known_pools[-10:],  # Keep last 10
        "sweeps": _sweeps[-10:],  # Keep last 10
        "bias": bias,
        "bias_reason": bias_reason,
    }
    write_state("sweep", data)
    return data


def _detect_equal_levels(bars: list[dict]) -> list[dict]:
    """Detect equal highs and equal lows across recent bars."""
    pools = []
    now_str = datetime.now(ET).isoformat()

    # Check for equal highs
    highs = [(i, b["high"]) for i, b in enumerate(bars)]
    equal_high_groups = _find_equal_groups(highs, EQUAL_LEVEL_TOLERANCE)

    for level, count in equal_high_groups:
        if count >= MIN_POOL_BARS:
            pools.append({
                "pool_type": "equal_highs",
                "level": round(level, 2),
                "bar_count": count,
                "first_seen": now_str,
            })

    # Check for equal lows
    lows = [(i, b["low"]) for i, b in enumerate(bars)]
    equal_low_groups = _find_equal_groups(lows, EQUAL_LEVEL_TOLERANCE)

    for level, count in equal_low_groups:
        if count >= MIN_POOL_BARS:
            pools.append({
                "pool_type": "equal_lows",
                "level": round(level, 2),
                "bar_count": count,
                "first_seen": now_str,
            })

    return pools


def _find_equal_groups(indexed_values: list[tuple[int, float]],
                       tolerance: float) -> list[tuple[float, int]]:
    """Find groups of values within tolerance of each other."""
    if not indexed_values:
        return []

    # Sort by value
    sorted_vals = sorted(indexed_values, key=lambda x: x[1])
    groups = []
    current_group = [sorted_vals[0]]

    for i in range(1, len(sorted_vals)):
        if abs(sorted_vals[i][1] - current_group[0][1]) <= tolerance:
            current_group.append(sorted_vals[i])
        else:
            if len(current_group) >= MIN_POOL_BARS:
                avg_level = sum(v for _, v in current_group) / len(current_group)
                groups.append((avg_level, len(current_group)))
            current_group = [sorted_vals[i]]

    if len(current_group) >= MIN_POOL_BARS:
        avg_level = sum(v for _, v in current_group) / len(current_group)
        groups.append((avg_level, len(current_group)))

    return groups


def _check_pool_takeout(pool: dict, latest: dict,
                        prev: Optional[dict], prev2: Optional[dict]) -> Optional[dict]:
    """Check if a liquidity pool was taken out and classify the result."""
    level = pool["level"]
    pool_type = pool["pool_type"]
    now_str = datetime.now(ET).isoformat()

    if pool_type == "equal_highs":
        # Price must have gone above the level
        if latest["high"] <= level:
            return None

        # SWEEP_CONFIRMED: wicked above but closed below (reversal)
        if latest["close"] < level:
            return {
                "time": now_str,
                "sweep_type": SweepType.SWEEP_CONFIRMED.value,
                "direction": "BEARISH",
                "level": level,
                "pool_type": pool_type,
                "wick_size": round(latest["high"] - level, 2),
                "reversal_candles": 1,
                "detail": "Swept equal highs and reversed below",
            }

        # Check if previous bar swept and this bar reversed
        if prev and prev["high"] > level and latest["close"] < level:
            return {
                "time": now_str,
                "sweep_type": SweepType.SWEEP_CONFIRMED.value,
                "direction": "BEARISH",
                "level": level,
                "pool_type": pool_type,
                "wick_size": round(prev["high"] - level, 2),
                "reversal_candles": 2,
                "detail": "Swept equal highs on prior bar, reversed",
            }

        # GENUINE_BREAK: closed above with conviction
        if latest["close"] > level + 5:
            return {
                "time": now_str,
                "sweep_type": SweepType.GENUINE_BREAK.value,
                "direction": "BULLISH",
                "level": level,
                "pool_type": pool_type,
                "wick_size": 0,
                "reversal_candles": 0,
                "detail": "Broke above equal highs and held",
            }

    elif pool_type == "equal_lows":
        if latest["low"] >= level:
            return None

        # SWEEP_CONFIRMED: wicked below but closed above
        if latest["close"] > level:
            return {
                "time": now_str,
                "sweep_type": SweepType.SWEEP_CONFIRMED.value,
                "direction": "BULLISH",
                "level": level,
                "pool_type": pool_type,
                "wick_size": round(level - latest["low"], 2),
                "reversal_candles": 1,
                "detail": "Swept equal lows and recovered above",
            }

        if prev and prev["low"] < level and latest["close"] > level:
            return {
                "time": now_str,
                "sweep_type": SweepType.SWEEP_CONFIRMED.value,
                "direction": "BULLISH",
                "level": level,
                "pool_type": pool_type,
                "wick_size": round(level - prev["low"], 2),
                "reversal_candles": 2,
                "detail": "Swept equal lows on prior bar, recovered",
            }

        if latest["close"] < level - 5:
            return {
                "time": now_str,
                "sweep_type": SweepType.GENUINE_BREAK.value,
                "direction": "BEARISH",
                "level": level,
                "pool_type": pool_type,
                "wick_size": 0,
                "reversal_candles": 0,
                "detail": "Broke below equal lows and held",
            }

    return None


def _detect_stop_hunt_wick(bars: list[dict]) -> Optional[dict]:
    """Detect stop hunt wicks: large wick (>60% of range) through a level, closes back inside."""
    if len(bars) < 2:
        return None

    latest = bars[-1]
    total_range = latest["high"] - latest["low"]
    if total_range == 0:
        return None

    body_top = max(latest["open"], latest["close"])
    body_bottom = min(latest["open"], latest["close"])
    upper_wick = latest["high"] - body_top
    lower_wick = body_bottom - latest["low"]

    now_str = datetime.now(ET).isoformat()

    # Upper wick stop hunt (bearish)
    if upper_wick / total_range > STOP_HUNT_WICK_PCT:
        return {
            "time": now_str,
            "sweep_type": SweepType.SWEEP_CONFIRMED.value,
            "direction": "BEARISH",
            "level": round(latest["high"], 2),
            "pool_type": "stop_hunt_wick",
            "wick_size": round(upper_wick, 2),
            "reversal_candles": 1,
            "detail": f"Upper wick {upper_wick / total_range:.0%} of range (stop hunt)",
        }

    # Lower wick stop hunt (bullish)
    if lower_wick / total_range > STOP_HUNT_WICK_PCT:
        return {
            "time": now_str,
            "sweep_type": SweepType.SWEEP_CONFIRMED.value,
            "direction": "BULLISH",
            "level": round(latest["low"], 2),
            "pool_type": "stop_hunt_wick",
            "wick_size": round(lower_wick, 2),
            "reversal_candles": 1,
            "detail": f"Lower wick {lower_wick / total_range:.0%} of range (stop hunt)",
        }

    return None


def _calculate_sweep_bias() -> tuple[str, str]:
    """Calculate directional bias from recent sweeps."""
    if not _sweeps:
        return "", "No sweeps detected"

    # Look at last 3 confirmed sweeps
    confirmed = [s for s in _sweeps if s["sweep_type"] == SweepType.SWEEP_CONFIRMED.value]
    if not confirmed:
        return "", "No confirmed sweeps"

    recent = confirmed[-3:]
    bullish = sum(1 for s in recent if s["direction"] == "BULLISH")
    bearish = sum(1 for s in recent if s["direction"] == "BEARISH")

    if bullish > bearish:
        return "BULLISH", f"{bullish} bullish sweep(s) confirmed"
    elif bearish > bullish:
        return "BEARISH", f"{bearish} bearish sweep(s) confirmed"
    else:
        return "", "Mixed sweep signals"


def _pool_already_known(pool: dict) -> bool:
    """Check if a pool at this level is already tracked."""
    for known in _known_pools:
        if (known["pool_type"] == pool["pool_type"] and
                abs(known["level"] - pool["level"]) <= EQUAL_LEVEL_TOLERANCE):
            return True
    return False


def _sweep_already_logged(sweep: dict) -> bool:
    """Check if a similar sweep was already logged recently."""
    for existing in _sweeps[-5:]:
        if (existing["direction"] == sweep["direction"] and
                abs(existing["level"] - sweep["level"]) <= EQUAL_LEVEL_TOLERANCE):
            return True
    return False
