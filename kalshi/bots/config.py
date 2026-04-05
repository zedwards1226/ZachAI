import os
from dotenv import load_dotenv

load_dotenv()

# Kalshi — RSA key auth (API v2)
# Get keys at: https://demo.kalshi.co (demo) or https://kalshi.com (live)
# Settings > API Keys > Generate Key → download private key PEM file
KALSHI_API_KEY_ID      = os.getenv("KALSHI_API_KEY_ID", "")       # UUID from Kalshi settings
KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "") # path to .pem file
KALSHI_DEMO = os.getenv("KALSHI_DEMO", "true").lower() == "true"
KALSHI_BASE = (
    "https://demo-api.kalshi.co/trade-api/v2"
    if KALSHI_DEMO
    else "https://api.elections.kalshi.com/trade-api/v2"
)

# Trading
PAPER_MODE = os.getenv("PAPER_MODE", "true").lower() == "true"
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", "1000"))
MAX_BET = float(os.getenv("MAX_BET", "100"))
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "5"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "150"))
MAX_CAPITAL_AT_RISK = float(os.getenv("MAX_CAPITAL_AT_RISK", "0.40"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.08"))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.25"))

# Schedule (all times CST = America/Chicago)
TRADE_WINDOW_START_HOUR = 6
TRADE_WINDOW_END_HOUR = 10
TIMEZONE = "America/Chicago"
SCAN_INTERVAL_MINUTES = 15

# Cities: code -> {name, lat, lon, kalshi_tag}
CITIES = {
    "NYC": {"name": "New York City", "lat": 40.7128, "lon": -74.0060, "kalshi_tag": "NY"},
    "CHI": {"name": "Chicago",       "lat": 41.8781, "lon": -87.6298, "kalshi_tag": "CHI"},
    "MIA": {"name": "Miami",         "lat": 25.7617, "lon": -80.1918, "kalshi_tag": "MIA"},
    "LAX": {"name": "Los Angeles",   "lat": 34.0522, "lon": -118.2437, "kalshi_tag": "LAX"},
    "MEM": {"name": "Memphis",       "lat": 35.1495, "lon": -90.0490, "kalshi_tag": "MEM"},
    "DEN": {"name": "Denver",        "lat": 39.7392, "lon": -104.9903, "kalshi_tag": "DEN"},
}

# Flask
FLASK_PORT = int(os.getenv("PORT", "5000"))
FLASK_HOST = "0.0.0.0"
DATABASE_PATH = os.getenv("DATABASE_PATH", "weatheralpha.db")

# Forecast uncertainty (std dev in °F — Open-Meteo day-ahead typical accuracy)
FORECAST_SIGMA_F = 3.5
