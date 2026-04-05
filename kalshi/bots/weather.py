"""
Open-Meteo weather forecast fetcher.
Returns today's high/low forecast in °F for each city.
"""
import requests
from datetime import date
from config import CITIES

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def fetch_forecast(city_code: str) -> dict:
    """
    Fetch today's forecast high and low in °F for the given city code.
    Returns:
        {
          "city": str,
          "date": str,
          "high_f": float,
          "low_f": float,
          "raw": dict   # full Open-Meteo response
        }
    Raises requests.HTTPError on API failure.
    """
    city = CITIES[city_code]
    params = {
        "latitude":    city["lat"],
        "longitude":   city["lon"],
        "daily":       "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone":    "auto",
        "forecast_days": 1,
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    daily   = data["daily"]
    high_f  = daily["temperature_2m_max"][0]
    low_f   = daily["temperature_2m_min"][0]
    dt      = daily["time"][0]

    return {
        "city":   city_code,
        "date":   dt,
        "high_f": round(high_f, 1),
        "low_f":  round(low_f, 1),
        "raw":    data,
    }


def fetch_all_forecasts() -> dict[str, dict]:
    """
    Fetch forecasts for all configured cities.
    Returns dict keyed by city code. Failed cities are skipped with a warning.
    """
    results = {}
    for code in CITIES:
        try:
            results[code] = fetch_forecast(code)
        except Exception as exc:
            results[code] = {
                "city":   code,
                "date":   date.today().isoformat(),
                "high_f": None,
                "low_f":  None,
                "error":  str(exc),
            }
    return results
