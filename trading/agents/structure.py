"""STRUCTURE AGENT — Runs at 8:45 AM ET.

Pulls prior day H/L/C, prior week H/L, overnight H/L, premarket H/L from TradingView.
Calculates premium/discount zones, tags price location, checks VIX regime.
Writes output to state/structure.json.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pytz

from config import (
    VIX_HARD_BLOCK, VIX_SWEET_SPOT_HIGH, VIX_SWEET_SPOT_LOW,
    ATR_LOOKBACK_DAYS, TIMEZONE,
)
from models import PriceLocation, Level
from services.state_manager import write_state
from services.tv_client import get_client

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


async def run() -> dict:
    """Run the structure agent. Returns the structure data dict."""
    logger.info("Structure agent starting")
    tv = await get_client()

    # Save current state to restore later
    original_symbol = await tv.get_symbol()

    try:
        # --- Step 1: Get daily data (prior day H/L/C, ATR) ---
        await tv.set_timeframe("D")
        daily_bars = await tv.get_ohlcv(count=ATR_LOOKBACK_DAYS + 1)

        if len(daily_bars) < 2:
            logger.error("Not enough daily bars: %d", len(daily_bars))
            return _write_error("Not enough daily data")

        prior_day = daily_bars[-2]  # Yesterday (last completed day)
        pd_high = prior_day["high"]
        pd_low = prior_day["low"]
        pd_close = prior_day["close"]
        pd_range = pd_high - pd_low

        # ATR calculation (14-day average true range)
        atr = _calculate_atr(daily_bars[:-1], ATR_LOOKBACK_DAYS)

        # --- Step 2: Get weekly data (prior week H/L) ---
        await tv.set_timeframe("W")
        weekly_bars = await tv.get_ohlcv(count=3)

        pw_high = weekly_bars[-2]["high"] if len(weekly_bars) >= 2 else pd_high
        pw_low = weekly_bars[-2]["low"] if len(weekly_bars) >= 2 else pd_low

        # --- Step 3: Switch to 5-min for premarket/overnight data ---
        await tv.set_timeframe("5")
        five_min_bars = await tv.get_ohlcv(count=200)

        overnight, premarket = _extract_session_ranges(five_min_bars)

        # --- Step 4: Get current price ---
        quote = await tv.get_quote()
        current_price = quote.get("last") or quote.get("close", 0)

        # --- Step 5: Get VIX ---
        vix = await _get_vix(tv)

        # --- Step 6: Get indicator values for VWAP ---
        indicators = await tv.get_study_values()
        vwap = _extract_indicator(indicators, "VWAP", "VWAP")

        # --- Step 7: Get volume for RVOL calculation ---
        rvol = _calculate_rvol(five_min_bars)

        # --- Step 8: Calculate levels and zones ---
        equilibrium = (pd_high + pd_low) / 2
        premium_boundary = equilibrium + (pd_range * 0.25)
        discount_boundary = equilibrium - (pd_range * 0.25)

        # Build all key levels
        levels = {
            "prior_day_high": pd_high,
            "prior_day_low": pd_low,
            "prior_day_close": pd_close,
            "prior_week_high": pw_high,
            "prior_week_low": pw_low,
            "overnight_high": overnight["high"],
            "overnight_low": overnight["low"],
            "premarket_high": premarket["high"],
            "premarket_low": premarket["low"],
            "equilibrium": equilibrium,
        }

        # Determine price location relative to all levels
        price_location, nearest = _tag_price_location(current_price, levels)

        # Zone classification
        if current_price > premium_boundary:
            zone = "PREMIUM"
        elif current_price < discount_boundary:
            zone = "DISCOUNT"
        else:
            zone = "EQUILIBRIUM"

        data = {
            "date": datetime.now(ET).strftime("%Y-%m-%d"),
            "current_price": round(current_price, 2),
            "prior_day": {
                "high": round(pd_high, 2),
                "low": round(pd_low, 2),
                "close": round(pd_close, 2),
                "range": round(pd_range, 2),
            },
            "prior_week": {
                "high": round(pw_high, 2),
                "low": round(pw_low, 2),
            },
            "overnight": {
                "high": round(overnight["high"], 2),
                "low": round(overnight["low"], 2),
            },
            "premarket": {
                "high": round(premarket["high"], 2),
                "low": round(premarket["low"], 2),
            },
            "equilibrium": round(equilibrium, 2),
            "premium_zone": round(premium_boundary, 2),
            "discount_zone": round(discount_boundary, 2),
            "zone": zone,
            "price_location": price_location.value,
            "nearest_level": {
                "name": nearest.name,
                "price": round(nearest.price, 2),
                "distance_pts": round(nearest.distance_pts, 2),
            },
            "atr_14": round(atr, 2),
            "vix": round(vix, 2) if vix else None,
            "vix_regime": _classify_vix(vix),
            "vwap": round(vwap, 2) if vwap else None,
            "rvol": round(rvol, 2) if rvol else None,
        }

        write_state("structure", data)
        logger.info("Structure agent complete: zone=%s, location=%s, vix=%.1f",
                     zone, price_location.value, vix or 0)
        return data

    except Exception as e:
        logger.error("Structure agent error: %s", e, exc_info=True)
        return _write_error(str(e))
    finally:
        # Restore original symbol + 5-min chart for ORB monitoring
        try:
            if original_symbol:
                await tv.set_symbol(original_symbol)
            await tv.set_timeframe("5")
        except Exception as restore_err:
            logger.warning("Failed to restore chart state: %s", restore_err)


def _calculate_atr(bars: list[dict], period: int) -> float:
    """Calculate Average True Range from daily bars."""
    if len(bars) < 2:
        return 0
    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i]["high"]
        low = bars[i]["low"]
        prev_close = bars[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    recent = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(recent) / len(recent) if recent else 0


def _extract_session_ranges(bars: list[dict]) -> tuple[dict, dict]:
    """Extract overnight and premarket ranges from 5-min bars.

    Overnight: 6:00 PM - 8:00 AM ET (prior evening through early morning)
    Premarket: 8:00 AM - 9:30 AM ET
    """
    et = pytz.timezone(TIMEZONE)
    today = datetime.now(et).date()

    on_high, on_low = 0, float("inf")
    pm_high, pm_low = 0, float("inf")

    for bar in bars:
        # Convert Unix timestamp to ET
        bar_dt = datetime.fromtimestamp(bar["time"], tz=pytz.utc).astimezone(et)
        bar_date = bar_dt.date()
        bar_hour = bar_dt.hour

        # Overnight: previous day 6PM to today 8AM
        is_overnight = (
            (bar_date == today and bar_hour < 8)
            or (bar_date < today and bar_hour >= 18)
        )

        # Premarket: today 8AM to 9:30AM
        is_premarket = (
            bar_date == today
            and ((bar_hour == 8) or (bar_hour == 9 and bar_dt.minute < 30))
        )

        if is_overnight:
            on_high = max(on_high, bar["high"])
            on_low = min(on_low, bar["low"])

        if is_premarket:
            pm_high = max(pm_high, bar["high"])
            pm_low = min(pm_low, bar["low"])

    # Default to current price if no data
    if on_low == float("inf"):
        on_low = on_high
    if pm_low == float("inf"):
        pm_low = pm_high

    return (
        {"high": on_high, "low": on_low},
        {"high": pm_high, "low": pm_low},
    )


def _tag_price_location(price: float, levels: dict) -> tuple[PriceLocation, Level]:
    """Determine price location relative to key levels."""
    nearest_name = ""
    nearest_price = 0
    min_distance = float("inf")

    for name, level_price in levels.items():
        if level_price == 0:
            continue
        dist = abs(price - level_price)
        if dist < min_distance:
            min_distance = dist
            nearest_name = name
            nearest_price = level_price

    nearest = Level(name=nearest_name, price=nearest_price, distance_pts=min_distance)

    if min_distance <= 5:
        return PriceLocation.AT_LEVEL, nearest
    elif min_distance <= 20:
        return PriceLocation.APPROACHING_WALL, nearest
    else:
        return PriceLocation.OPEN_AIR, nearest


async def _get_vix(tv) -> float:
    """Fetch VIX value. Tries CBOE:VIX quote, falls back to 0."""
    try:
        # Save current symbol, switch to VIX, read, switch back
        current = await tv.get_symbol()
        await tv.set_symbol("CBOE:VIX")
        quote = await tv.get_quote()
        vix_val = quote.get("last") or quote.get("close", 0)
        await tv.set_symbol(current)
        return vix_val
    except Exception as e:
        logger.warning("Failed to get VIX: %s", e)
        return 0


def _classify_vix(vix: float | None) -> str:
    """Classify VIX regime."""
    if not vix or vix == 0:
        return "UNKNOWN"
    if vix > VIX_HARD_BLOCK:
        return "EXTREME"
    if vix > VIX_SWEET_SPOT_HIGH:
        return "HIGH"
    if vix >= VIX_SWEET_SPOT_LOW:
        return "SWEET_SPOT"
    return "LOW"


def _extract_indicator(indicators: list[dict], study_name: str, value_key: str) -> float | None:
    """Extract a specific indicator value by study name and key."""
    for ind in indicators:
        if study_name.lower() in ind.get("name", "").lower():
            vals = ind.get("values", {})
            for k, v in vals.items():
                if value_key.lower() in k.lower() and isinstance(v, (int, float)):
                    return v
    return None


def _calculate_rvol(bars: list[dict]) -> float | None:
    """Calculate relative volume (current vs average)."""
    if len(bars) < 20:
        return None
    recent_vol = sum(b["volume"] for b in bars[-5:]) / 5
    avg_vol = sum(b["volume"] for b in bars[-100:]) / min(len(bars), 100)
    if avg_vol == 0:
        return None
    return recent_vol / avg_vol


def _write_error(error_msg: str) -> dict:
    """Write error state."""
    data = {
        "date": datetime.now(ET).strftime("%Y-%m-%d"),
        "error": error_msg,
        "status": "ERROR",
    }
    write_state("structure", data)
    return data
