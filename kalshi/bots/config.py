import os
from pathlib import Path
from dotenv import load_dotenv

# Load from kalshi/.env (one level up from bots/)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

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
# Audit 2026-05-18: MAX_DAILY_LOSS alone is dollar-fixed and stops scaling
# once bankroll grows. At a $5K bankroll a $20 cap halts the bot after one
# small loser. Effective cap = max(MAX_DAILY_LOSS, capital * MAX_DAILY_LOSS_PCT).
# Default 10% keeps the bot trading through normal variance while still
# capping a bad-streak day at a known % of capital.
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.10"))
MAX_CAPITAL_AT_RISK = float(os.getenv("MAX_CAPITAL_AT_RISK", "0.40"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.08"))
# YES-side was anti-predictive in a 22-trade sample (1/13 WR, Brier 0.4151).
# Root cause: GFS ensemble over-extrapolates hot tails. Fix = higher edge bar
# for YES + shrink our probability toward the market's implied probability so
# overconfident ensemble readings get pulled back toward reality.
MIN_EDGE_YES = float(os.getenv("MIN_EDGE_YES", "0.15"))
# 0.0 = trust ensemble fully  |  1.0 = trust market fully
# 0.25 = pull ensemble 25% of the way toward Kalshi's implied probability.
PROB_SHRINK_TO_MARKET = float(os.getenv("PROB_SHRINK_TO_MARKET", "0.25"))
# Competitive Kalshi weather bots use 15% fractional Kelly (suislanchez et al.);
# dropping from 25% cuts drawdown risk ~40% at small cost to compounding.
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.15"))
# Per-trade hard cap as a fraction of LIVE bankroll. 0.05 = 5% — auto-scales
# as bankroll grows so dollars per trade compound with realized P&L.
# Acts together with MAX_BET (absolute $ ceiling) and KELLY_FRACTION.
BANKROLL_PCT_CAP = float(os.getenv("BANKROLL_PCT_CAP", "0.05"))

# Per-city calibration: min resolved trades before we trust historical WR
# instead of the global default. Below this, fall back to global shrinkage.
CALIBRATION_MIN_SAMPLE = int(os.getenv("CALIBRATION_MIN_SAMPLE", "3"))
# Bayesian prior trades (per-side) pulling toward 50% WR. Higher = more stable
# shrinkage when sample is small.
CALIBRATION_PRIOR_WEIGHT = int(os.getenv("CALIBRATION_PRIOR_WEIGHT", "5"))
# Only learn calibration from trades placed on/after this date. Everything
# before 2026-05-22 used downtown coords instead of Kalshi's settlement
# station (fixed 2026-05-21), so those outcomes mis-teach the shrinkage
# table. Floor at the first day all trades use correct station coords.
CALIBRATION_DATA_FLOOR = os.getenv("CALIBRATION_DATA_FLOOR", "2026-05-22")

# Longshot-bias correction via log-odds shrinkage on market prices.
# 0.0 = off  |  0.05 = conservative liquid market  |  0.10 = illiquid weather contracts
# Pulls extreme Kalshi quotes (5c, 95c) symmetrically toward 50c before
# computing edge, reflecting documented longshot bias in prediction markets.
SHIN_Z = float(os.getenv("SHIN_Z", "0.05"))
MIN_PRICE_CENTS = int(os.getenv("MIN_PRICE_CENTS", "5"))     # skip illiquid penny contracts
MAX_CONTRACTS = int(os.getenv("MAX_CONTRACTS", "100"))        # Kalshi weather depth is ~50-200

# Strike-type blocklist informed by lifetime resolved-trade audit (2026-04-24).
# 'less' strikes were 0W-10L, -$80.94. Backtest of remaining slices showed all
# other strike+side combos either profitable or mixed; only 'less' is a pure
# loss pattern with zero offsetting wins. Override via env to re-enable.
BLOCK_STRIKE_TYPES = [
    s.strip().lower()
    for s in os.getenv("BLOCK_STRIKE_TYPES", "less").split(",")
    if s.strip()
]

# Schedule (all times CST = America/Chicago)
TRADE_WINDOW_START_HOUR = 6
TRADE_WINDOW_END_HOUR = 10
TIMEZONE = "America/Chicago"
SCAN_INTERVAL_MINUTES = 15

# Cities: code -> {name, lat, lon, kalshi_series}
# Series tickers verified live against api.elections.kalshi.com on 2026-05-05.
# 20 active KXHIGH series with 12 strike levels each per day — bot picks the
# top edges system-wide and is still capped by MAX_DAILY_TRADES (default 5).
# Learning agent auto-pauses any city after 3/5 losses, so the lineup
# self-selects to whichever cities the strategy actually edges on.
CITIES = {
    # Original 5 (verified 2026-04)
    "NYC": {"name": "New York City",    "lat": 40.7128, "lon": -74.0060,  "kalshi_series": "KXHIGHNY"},
    "CHI": {"name": "Chicago",          "lat": 41.8781, "lon": -87.6298,  "kalshi_series": "KXHIGHCHI"},
    "MIA": {"name": "Miami",            "lat": 25.7617, "lon": -80.1918,  "kalshi_series": "KXHIGHMIA"},
    "LAX": {"name": "Los Angeles",      "lat": 34.0522, "lon": -118.2437, "kalshi_series": "KXHIGHLAX"},
    "DEN": {"name": "Denver",           "lat": 39.7392, "lon": -104.9903, "kalshi_series": "KXHIGHDEN"},
    # Added 2026-05-05 — verified live with 12 open strikes/day each
    "AUS": {"name": "Austin",           "lat": 30.2672, "lon": -97.7431,  "kalshi_series": "KXHIGHAUS"},
    "ATL": {"name": "Atlanta",          "lat": 33.7490, "lon": -84.3880,  "kalshi_series": "KXHIGHTATL"},
    "BOS": {"name": "Boston",           "lat": 42.3601, "lon": -71.0589,  "kalshi_series": "KXHIGHTBOS"},
    "DAL": {"name": "Dallas",           "lat": 32.7767, "lon": -96.7970,  "kalshi_series": "KXHIGHTDAL"},
    "WDC": {"name": "Washington DC",    "lat": 38.9072, "lon": -77.0369,  "kalshi_series": "KXHIGHTDC"},
    "HOU": {"name": "Houston",          "lat": 29.7604, "lon": -95.3698,  "kalshi_series": "KXHIGHTHOU"},
    "LAS": {"name": "Las Vegas",        "lat": 36.1716, "lon": -115.1391, "kalshi_series": "KXHIGHTLV"},
    "MIN": {"name": "Minneapolis",      "lat": 44.9778, "lon": -93.2650,  "kalshi_series": "KXHIGHTMIN"},
    "NOL": {"name": "New Orleans",      "lat": 29.9511, "lon": -90.0715,  "kalshi_series": "KXHIGHTNOLA"},
    "OKC": {"name": "Oklahoma City",    "lat": 35.4676, "lon": -97.5164,  "kalshi_series": "KXHIGHTOKC"},
    "PHX": {"name": "Phoenix",          "lat": 33.4484, "lon": -112.0740, "kalshi_series": "KXHIGHTPHX"},
    "SAT": {"name": "San Antonio",      "lat": 29.4241, "lon": -98.4936,  "kalshi_series": "KXHIGHTSATX"},
    "SEA": {"name": "Seattle",          "lat": 47.6062, "lon": -122.3321, "kalshi_series": "KXHIGHTSEA"},
    "SFO": {"name": "San Francisco",    "lat": 37.7749, "lon": -122.4194, "kalshi_series": "KXHIGHTSFO"},
    "PHL": {"name": "Philadelphia",     "lat": 39.9526, "lon": -75.1652,  "kalshi_series": "KXHIGHPHIL"},
    # MEM removed 2026-04-24: Kalshi doesn't publish KXHIGHMEM markets.
}

# Flask — bind to loopback only. Public dashboard is served by the
# proxy on :3001, which forwards to 127.0.0.1:5000 server-side and
# injects INTERNAL_API_SECRET so write endpoints can't be hit from
# the LAN.
FLASK_PORT = int(os.getenv("PORT", "5000"))
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
DATABASE_PATH = os.getenv("DATABASE_PATH", "weatheralpha.db")

# Shared secret required on every POST to the bot API. The dashboard
# proxy injects it server-side; direct callers (curl/scripts) must
# send it via X-Internal-Secret. Auto-generated if unset so paper
# mode still runs, but a stable value should live in .env.
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")
if not INTERNAL_API_SECRET:
    import secrets
    INTERNAL_API_SECRET = secrets.token_urlsafe(32)

# Ensemble model config (replaces old FORECAST_SIGMA_F = 3.5 normal distribution)
# Probability is now computed by counting GFS ensemble members, not Gaussian CDF.
# FORECAST_SIGMA_F is no longer used.
