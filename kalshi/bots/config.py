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

# Per-city calibration: min resolved trades before we trust historical WR
# instead of the global default. Below this, fall back to global shrinkage.
CALIBRATION_MIN_SAMPLE = int(os.getenv("CALIBRATION_MIN_SAMPLE", "3"))
# Bayesian prior trades (per-side) pulling toward 50% WR. Higher = more stable
# shrinkage when sample is small.
CALIBRATION_PRIOR_WEIGHT = int(os.getenv("CALIBRATION_PRIOR_WEIGHT", "5"))

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
# Series tickers verified against live api.elections.kalshi.com
CITIES = {
    "NYC": {"name": "New York City", "lat": 40.7128, "lon": -74.0060, "kalshi_series": "KXHIGHNY"},
    "CHI": {"name": "Chicago",       "lat": 41.8781, "lon": -87.6298, "kalshi_series": "KXHIGHCHI"},
    "MIA": {"name": "Miami",         "lat": 25.7617, "lon": -80.1918, "kalshi_series": "KXHIGHMIA"},
    "LAX": {"name": "Los Angeles",   "lat": 34.0522, "lon": -118.2437, "kalshi_series": "KXHIGHLAX"},
    "DEN": {"name": "Denver",        "lat": 39.7392, "lon": -104.9903, "kalshi_series": "KXHIGHDEN"},
    # MEM removed 2026-04-24: Kalshi doesn't publish KXHIGHMEM markets,
    # 255+ rate-limit errors in monitor.log with zero trades placed.
    # Re-add with backoff if Kalshi adds Memphis to weather markets.
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
