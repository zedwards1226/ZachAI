"""
Open-Meteo multi-model ensemble weather forecast fetcher.
Combines GFS (31 members) + ICON-EPS (21 members) = ~52 members total.
Larger ensemble -> tighter probability estimates -> better Brier score.
"""
import os
import requests
import logging
from datetime import date, timedelta
from config import CITIES

log = logging.getLogger(__name__)

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Comma-separated Open-Meteo model IDs. Default: GFS + ICON for 52 members.
# Override with ENSEMBLE_MODELS env var if you want to pin a single model.
ENSEMBLE_MODELS = os.getenv("ENSEMBLE_MODELS", "gfs_seamless,icon_seamless")

# Cache: (city_code, date_str) -> forecast dict, refreshed every 15 min by scheduler
_cache: dict[tuple[str, str], dict] = {}


def fetch_ensemble_forecast(city_code: str, target_date: date | None = None) -> dict:
    """
    Fetch GFS ensemble forecast (31 members) for a city on a given date.
    Returns:
        {
          "city": str,
          "date": str,
          "high_f": float,           # control run high
          "low_f": float,            # control run low
          "member_highs": [float],   # all 31 member highs
          "member_lows": [float],    # all 31 member lows
          "raw": dict,
        }
    """
    city = CITIES[city_code]
    if target_date is None:
        target_date = date.today()

    ds = target_date.isoformat()
    cache_key = (city_code, ds)
    if cache_key in _cache:
        return _cache[cache_key]

    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "start_date": ds,
        "end_date": ds,
        "models": ENSEMBLE_MODELS,
    }

    resp = requests.get(ENSEMBLE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})

    # Extract all member highs: control + member01..member30
    member_highs = []
    member_lows = []

    for key, val in daily.items():
        if key.startswith("temperature_2m_max") and isinstance(val, list) and val:
            member_highs.append(val[0])
        if key.startswith("temperature_2m_min") and isinstance(val, list) and val:
            member_lows.append(val[0])

    # Control run is the plain "temperature_2m_max" key
    control_high = daily.get("temperature_2m_max", [None])[0] if isinstance(daily.get("temperature_2m_max"), list) else None
    control_low = daily.get("temperature_2m_min", [None])[0] if isinstance(daily.get("temperature_2m_min"), list) else None

    if not member_highs:
        raise ValueError(f"No ensemble members returned for {city_code} {ds}")

    result = {
        "city": city_code,
        "date": ds,
        "high_f": round(control_high, 1) if control_high is not None else round(sum(member_highs) / len(member_highs), 1),
        "low_f": round(control_low, 1) if control_low is not None else round(sum(member_lows) / len(member_lows), 1),
        "member_highs": [round(h, 1) for h in member_highs],
        "member_lows": [round(l, 1) for l in member_lows],
        "ensemble_count": len(member_highs),
        "ensemble_spread": round(max(member_highs) - min(member_highs), 1) if member_highs else 0,
        "raw": data,
    }

    _cache[cache_key] = result
    log.info(
        "Ensemble [%s %s]: %d members, high=%.1fF (spread=%.1fF)",
        city_code, ds, len(member_highs),
        result["high_f"], result["ensemble_spread"],
    )
    return result


def fetch_forecast(city_code: str) -> dict:
    """
    Backward-compatible wrapper. Returns ensemble forecast with member_highs.
    Falls back to deterministic forecast if ensemble API fails.
    """
    try:
        return fetch_ensemble_forecast(city_code)
    except Exception as exc:
        log.warning("Ensemble fetch failed for %s, falling back to deterministic: %s", city_code, exc)
        return _fetch_deterministic(city_code)


def _fetch_deterministic(city_code: str) -> dict:
    """Fallback: single-point forecast (no ensemble members)."""
    city = CITIES[city_code]
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": 1,
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    daily = data["daily"]
    high_f = daily["temperature_2m_max"][0]
    low_f = daily["temperature_2m_min"][0]

    return {
        "city": city_code,
        "date": daily["time"][0],
        "high_f": round(high_f, 1),
        "low_f": round(low_f, 1),
        "member_highs": [],  # empty = no ensemble
        "member_lows": [],
        "ensemble_count": 0,
        "ensemble_spread": 0,
        "raw": data,
    }


def fetch_all_forecasts() -> dict[str, dict]:
    """Fetch ensemble forecasts for all configured cities."""
    results = {}
    for code in CITIES:
        try:
            results[code] = fetch_forecast(code)
        except Exception as exc:
            results[code] = {
                "city": code,
                "date": date.today().isoformat(),
                "high_f": None,
                "low_f": None,
                "member_highs": [],
                "member_lows": [],
                "error": str(exc),
            }
    return results


def clear_cache():
    """Clear forecast cache (called at midnight or on demand)."""
    _cache.clear()
