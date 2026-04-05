# WeatherAlpha Kalshi Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully autonomous weather trading bot that compares Open-Meteo temperature forecasts against Kalshi KXHIGH market prices, trades on edges ≥ 8%, enforces 5 hard guardrails, and serves a cyberpunk neon-green React dashboard — all deployable to Railway.

**Architecture:** Python Flask backend with APScheduler drives all trading logic; SQLite persists state across restarts; React + Recharts dashboard polls the REST API every 30 seconds. Paper mode logs trades without touching Kalshi's order endpoint. Both services are served from a single Railway deployment (Flask serves the React build as static files).

**Tech Stack:** Python 3.11, Flask, APScheduler, SQLite (sqlite3), requests, scipy, python-dotenv | React 18, Vite, Recharts, CSS custom properties for theming | Railway (nixpacks, single-service deploy)

---

## File Map

```
C:\ZachAI\kalshi\
├── bots/
│   ├── config.py           # All env-driven config constants
│   ├── database.py         # SQLite schema + CRUD helpers
│   ├── weather.py          # Open-Meteo forecast fetcher
│   ├── kalshi_client.py    # Kalshi v2 REST client (auth + markets + orders)
│   ├── guardrails.py       # Risk check engine (5 rules)
│   ├── trader.py           # Edge calc, Kelly sizing, trade execution
│   ├── app.py              # Flask API + APScheduler orchestration
│   └── tests/
│       ├── test_weather.py
│       ├── test_guardrails.py
│       └── test_trader.py
├── dashboard/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── App.css             # Global cyberpunk theme variables
│       └── components/
│           ├── Header.jsx
│           ├── StatsBar.jsx
│           ├── CityGrid.jsx
│           ├── GuardrailPanel.jsx
│           ├── TradeTable.jsx
│           ├── PnLChart.jsx
│           └── LogFeed.jsx
├── requirements.txt
├── .env.example
├── Procfile
├── railway.toml
├── nixpacks.toml
├── start.bat               # Windows dev launcher
└── start.sh                # Linux/Railway launcher
```

---

## Task 1: Project Scaffolding + Config

**Files:**
- Create: `C:\ZachAI\kalshi\requirements.txt`
- Create: `C:\ZachAI\kalshi\.env.example`
- Create: `C:\ZachAI\kalshi\bots\config.py`

- [ ] **Step 1: Create requirements.txt**

```
flask==3.0.3
flask-cors==4.0.0
apscheduler==3.10.4
requests==2.32.3
scipy==1.13.0
python-dotenv==1.0.1
pytz==2024.1
gunicorn==22.0.0
```

- [ ] **Step 2: Create .env.example**

```
# Kalshi credentials (leave blank to run in market-data-only mode)
KALSHI_EMAIL=
KALSHI_PASSWORD=
KALSHI_DEMO=true

# Trading controls
PAPER_MODE=true
STARTING_CAPITAL=1000.00
MAX_BET=100
MAX_DAILY_TRADES=5
MAX_DAILY_LOSS=150
MAX_CAPITAL_AT_RISK=0.40
MAX_CONSECUTIVE_LOSSES=3
MIN_EDGE=0.08
KELLY_FRACTION=0.25

# App
PORT=5000
DATABASE_PATH=weatheralpha.db
```

- [ ] **Step 3: Create bots/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Kalshi
KALSHI_EMAIL = os.getenv("KALSHI_EMAIL", "")
KALSHI_PASSWORD = os.getenv("KALSHI_PASSWORD", "")
KALSHI_DEMO = os.getenv("KALSHI_DEMO", "true").lower() == "true"
KALSHI_BASE = (
    "https://demo-api.kalshi.co/trade-api/v2"
    if KALSHI_DEMO
    else "https://trading-api.kalshi.com/trade-api/v2"
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
    "CHI": {"name": "Chicago",        "lat": 41.8781, "lon": -87.6298, "kalshi_tag": "CHI"},
    "MIA": {"name": "Miami",          "lat": 25.7617, "lon": -80.1918, "kalshi_tag": "MIA"},
    "LAX": {"name": "Los Angeles",    "lat": 34.0522, "lon": -118.2437, "kalshi_tag": "LAX"},
    "MEM": {"name": "Memphis",        "lat": 35.1495, "lon": -90.0490, "kalshi_tag": "MEM"},
    "DEN": {"name": "Denver",         "lat": 39.7392, "lon": -104.9903, "kalshi_tag": "DEN"},
}

# Flask
FLASK_PORT = int(os.getenv("PORT", "5000"))
FLASK_HOST = "0.0.0.0"
DATABASE_PATH = os.getenv("DATABASE_PATH", "weatheralpha.db")

# Forecast uncertainty (std dev in °F — Open-Meteo day-ahead accuracy)
FORECAST_SIGMA_F = 3.5
```

- [ ] **Step 4: Install dependencies**

```bash
cd C:\ZachAI\kalshi
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 5: Commit**

```bash
cd C:\ZachAI
git add kalshi/requirements.txt kalshi/.env.example kalshi/bots/config.py
git commit -m "feat(weatheralpha): project scaffold + config"
```

---

## Task 2: Database Layer

**Files:**
- Create: `C:\ZachAI\kalshi\bots\database.py`

- [ ] **Step 1: Write database.py**

```python
import sqlite3
import json
from datetime import datetime, date
import config

def get_conn():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            city        TEXT    NOT NULL,
            market_ticker TEXT  NOT NULL,
            side        TEXT    NOT NULL,   -- YES or NO
            our_prob    REAL    NOT NULL,
            kalshi_prob REAL    NOT NULL,
            edge        REAL    NOT NULL,
            bet_amount  REAL    NOT NULL,
            contracts   INTEGER NOT NULL,
            price_cents INTEGER NOT NULL,   -- Kalshi price 1-99
            status      TEXT    NOT NULL DEFAULT 'open',  -- open|won|lost|cancelled
            resolved_at TEXT,
            pnl         REAL    DEFAULT 0,
            paper       INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS city_scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_at  TEXT    NOT NULL,
            city        TEXT    NOT NULL,
            forecast_f  REAL    NOT NULL,
            threshold_f REAL,
            our_prob    REAL,
            kalshi_prob REAL,
            edge        REAL,
            action      TEXT    NOT NULL DEFAULT 'no_trade'
        );

        CREATE TABLE IF NOT EXISTS daily_state (
            trade_date          TEXT PRIMARY KEY,
            trades_count        INTEGER NOT NULL DEFAULT 0,
            daily_pnl           REAL    NOT NULL DEFAULT 0,
            consecutive_losses  INTEGER NOT NULL DEFAULT 0,
            capital             REAL    NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            level       TEXT    NOT NULL DEFAULT 'INFO',
            message     TEXT    NOT NULL
        );
        """)

def today_str():
    return date.today().isoformat()

# --- Daily state helpers ---

def get_daily_state():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM daily_state WHERE trade_date = ?", (today_str(),)
        ).fetchone()
        if row:
            return dict(row)
        # Bootstrap from previous capital
        prev = conn.execute(
            "SELECT capital FROM daily_state ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        capital = prev["capital"] if prev else config.STARTING_CAPITAL
        conn.execute(
            "INSERT INTO daily_state(trade_date, capital) VALUES (?,?)",
            (today_str(), capital),
        )
        return get_daily_state()

def update_daily_state(**kwargs):
    set_parts = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [today_str()]
    with get_conn() as conn:
        conn.execute(
            f"UPDATE daily_state SET {set_parts} WHERE trade_date=?", vals
        )

# --- Trade helpers ---

def insert_trade(city, market_ticker, side, our_prob, kalshi_prob, edge,
                 bet_amount, contracts, price_cents, paper=True):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO trades
              (created_at,city,market_ticker,side,our_prob,kalshi_prob,edge,
               bet_amount,contracts,price_cents,paper)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (now, city, market_ticker, side, our_prob, kalshi_prob, edge,
              bet_amount, contracts, price_cents, int(paper)))
        return cur.lastrowid

def resolve_trade(trade_id, won: bool):
    with get_conn() as conn:
        trade = conn.execute(
            "SELECT * FROM trades WHERE id=?", (trade_id,)
        ).fetchone()
        if not trade:
            return
        if won:
            # payout = contracts * (100 - price_cents) / 100 if YES, or contracts * price_cents/100 if NO
            if trade["side"] == "YES":
                pnl = trade["contracts"] * (100 - trade["price_cents"]) / 100
            else:
                pnl = trade["contracts"] * trade["price_cents"] / 100
        else:
            pnl = -trade["bet_amount"]
        conn.execute("""
            UPDATE trades SET status=?, resolved_at=?, pnl=?
            WHERE id=?
        """, ("won" if won else "lost", datetime.utcnow().isoformat(), pnl, trade_id))
        return pnl

def get_trades(limit=100, status=None):
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

def get_pnl_series():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT date(created_at) as d, SUM(pnl) as daily_pnl
            FROM trades WHERE status IN ('won','lost')
            GROUP BY d ORDER BY d
        """).fetchall()
        cumulative, running = [], 0
        for r in rows:
            running += r["daily_pnl"]
            cumulative.append({"date": r["d"], "pnl": round(running, 2)})
        return cumulative

# --- Scan helpers ---

def insert_scan(city, forecast_f, threshold_f=None, our_prob=None,
                kalshi_prob=None, edge=None, action="no_trade"):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO city_scans
              (scanned_at,city,forecast_f,threshold_f,our_prob,kalshi_prob,edge,action)
            VALUES (?,?,?,?,?,?,?,?)
        """, (now, city, forecast_f, threshold_f, our_prob, kalshi_prob, edge, action))

def get_latest_scans():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT cs.* FROM city_scans cs
            INNER JOIN (
                SELECT city, MAX(scanned_at) AS latest FROM city_scans GROUP BY city
            ) latest ON cs.city=latest.city AND cs.scanned_at=latest.latest
        """).fetchall()
        return [dict(r) for r in rows]

# --- Log helpers ---

def log(message, level="INFO"):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_log(ts,level,message) VALUES(?,?,?)",
            (now, level, message)
        )

def get_logs(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 2: Smoke-test the DB**

```bash
cd C:\ZachAI\kalshi\bots
python -c "import database; database.init_db(); s=database.get_daily_state(); print('capital:', s['capital'])"
```

Expected output: `capital: 1000.0`

- [ ] **Step 3: Commit**

```bash
cd C:\ZachAI
git add kalshi/bots/database.py
git commit -m "feat(weatheralpha): SQLite schema + CRUD helpers"
```

---

## Task 3: Open-Meteo Weather Client

**Files:**
- Create: `C:\ZachAI\kalshi\bots\weather.py`
- Create: `C:\ZachAI\kalshi\bots\tests\test_weather.py`

- [ ] **Step 1: Write test_weather.py**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import weather

def test_fetch_returns_fahrenheit_for_nyc():
    result = weather.get_forecast_high("NYC")
    assert result is not None, "Expected a temperature, got None"
    assert 0 < result < 130, f"Unrealistic temp: {result}"

def test_all_cities_return_value():
    import config
    for code in config.CITIES:
        val = weather.get_forecast_high(code)
        assert val is not None, f"No forecast for {code}"
        assert 0 < val < 130
```

- [ ] **Step 2: Run test — expect FAIL (module not found)**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/test_weather.py -v
```

Expected: `ModuleNotFoundError: No module named 'weather'`

- [ ] **Step 3: Write weather.py**

```python
"""Open-Meteo free API — no key required.
Returns tomorrow's forecast high temperature in °F for a given city code.
"""
import requests
import config

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9 / 5 + 32

def get_forecast_high(city_code: str) -> float | None:
    """Return tomorrow's forecast daily high in °F, or None on failure."""
    city = config.CITIES.get(city_code)
    if not city:
        return None
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "daily": "temperature_2m_max",
        "temperature_unit": "fahrenheit",
        "timezone": "America/Chicago",
        "forecast_days": 2,  # index 0 = today, index 1 = tomorrow
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        temps = data["daily"]["temperature_2m_max"]
        # Use tomorrow (index 1) during trading window, fall back to today
        return round(float(temps[1]), 1)
    except Exception as exc:
        print(f"[weather] fetch failed for {city_code}: {exc}")
        return None

def get_all_forecasts() -> dict[str, float | None]:
    """Fetch tomorrow's high for all configured cities."""
    return {code: get_forecast_high(code) for code in config.CITIES}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/test_weather.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
cd C:\ZachAI
git add kalshi/bots/weather.py kalshi/bots/tests/test_weather.py
git commit -m "feat(weatheralpha): Open-Meteo weather client + tests"
```

---

## Task 4: Kalshi API Client

**Files:**
- Create: `C:\ZachAI\kalshi\bots\kalshi_client.py`

- [ ] **Step 1: Write kalshi_client.py**

```python
"""Kalshi v2 REST client.

In paper mode the client reads market data but never calls the order endpoint.
If credentials are absent, market data falls back to a simulated price based
on the normal distribution (useful for offline dev/testing).
"""
import requests
import config
from database import log

class KalshiClient:
    def __init__(self):
        self.base = config.KALSHI_BASE
        self.token: str | None = None
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ── Auth ──────────────────────────────────────────────────────────────

    def login(self) -> bool:
        if not config.KALSHI_EMAIL or not config.KALSHI_PASSWORD:
            log("No Kalshi credentials — running in data-simulation mode", "WARN")
            return False
        try:
            resp = self.session.post(
                f"{self.base}/login",
                json={"email": config.KALSHI_EMAIL, "password": config.KALSHI_PASSWORD},
                timeout=10,
            )
            resp.raise_for_status()
            self.token = resp.json()["token"]
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            log("Kalshi login successful")
            return True
        except Exception as exc:
            log(f"Kalshi login failed: {exc}", "ERROR")
            return False

    def _ensure_auth(self):
        if not self.token:
            self.login()

    # ── Market data ───────────────────────────────────────────────────────

    def search_weather_markets(self, city_tag: str, date_str: str) -> list[dict]:
        """
        Search for KXHIGH markets matching city_tag and date_str (YYYYMMDD).
        Returns list of market dicts with at minimum: ticker, yes_bid, yes_ask, title.
        """
        if not self.token:
            return []
        try:
            params = {
                "series_ticker": "KXHIGH",
                "status": "open",
                "limit": 100,
            }
            resp = self.session.get(f"{self.base}/markets", params=params, timeout=10)
            resp.raise_for_status()
            markets = resp.json().get("markets", [])
            tag_upper = city_tag.upper()
            filtered = [
                m for m in markets
                if tag_upper in m.get("ticker", "").upper()
                and date_str in m.get("ticker", "")
            ]
            return filtered
        except Exception as exc:
            log(f"Kalshi market search failed: {exc}", "ERROR")
            return []

    def get_best_market_for_forecast(
        self, city_code: str, forecast_f: float, date_str: str
    ) -> dict | None:
        """
        Find the KXHIGH market whose threshold is closest to the forecast.
        Returns the market dict or None if unavailable.
        """
        city = config.CITIES[city_code]
        markets = self.search_weather_markets(city["kalshi_tag"], date_str)
        if not markets:
            return None
        # Parse threshold from ticker, e.g. KXHIGH-20240601-NY-65 → 65
        def parse_threshold(ticker: str) -> float | None:
            parts = ticker.split("-")
            for p in reversed(parts):
                try:
                    return float(p)
                except ValueError:
                    continue
            return None

        candidates = []
        for m in markets:
            t = parse_threshold(m["ticker"])
            if t is not None:
                candidates.append((abs(t - forecast_f), t, m))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][2]  # closest market

    def get_market_prob(self, market: dict) -> float | None:
        """
        Return Kalshi's implied YES probability (0-1) from yes_ask price.
        Kalshi prices are in cents (0-100); divide by 100.
        """
        try:
            # yes_ask is how much you pay for a YES contract
            return float(market["yes_ask"]) / 100.0
        except (KeyError, TypeError, ValueError):
            return None

    # ── Orders (paper-safe) ───────────────────────────────────────────────

    def place_order(
        self, ticker: str, side: str, count: int, price_cents: int
    ) -> dict | None:
        """
        Place a market order. In PAPER_MODE, logs and returns a simulated response.
        side: 'yes' or 'no'
        count: number of contracts (each contract = $1 max payout)
        price_cents: limit price 1-99
        """
        if config.PAPER_MODE:
            log(
                f"[PAPER] Would place {side.upper()} x{count} @ {price_cents}¢ on {ticker}"
            )
            return {
                "paper": True,
                "ticker": ticker,
                "side": side,
                "count": count,
                "price_cents": price_cents,
            }
        self._ensure_auth()
        if not self.token:
            log("Cannot place order — not authenticated", "ERROR")
            return None
        try:
            body = {
                "ticker": ticker,
                "action": "buy",
                "side": side,
                "count": count,
                "type": "limit",
                "yes_price" if side == "yes" else "no_price": price_cents,
            }
            resp = self.session.post(
                f"{self.base}/portfolio/orders", json=body, timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log(f"Order placement failed: {exc}", "ERROR")
            return None

    def get_balance(self) -> float:
        """Return available balance in dollars. Falls back to 0."""
        if not self.token:
            return 0.0
        try:
            resp = self.session.get(f"{self.base}/portfolio/balance", timeout=10)
            resp.raise_for_status()
            return float(resp.json().get("balance", 0)) / 100  # cents → dollars
        except Exception:
            return 0.0


# Module-level singleton
_client: KalshiClient | None = None

def get_client() -> KalshiClient:
    global _client
    if _client is None:
        _client = KalshiClient()
        _client.login()
    return _client
```

- [ ] **Step 2: Smoke-test client instantiation**

```bash
cd C:\ZachAI\kalshi\bots
python -c "import kalshi_client; c = kalshi_client.get_client(); print('client ok, token:', bool(c.token))"
```

Expected: `client ok, token: False` (no creds yet — that's correct)

- [ ] **Step 3: Commit**

```bash
cd C:\ZachAI
git add kalshi/bots/kalshi_client.py
git commit -m "feat(weatheralpha): Kalshi v2 REST client with paper-mode safety"
```

---

## Task 5: Guardrails Engine

**Files:**
- Create: `C:\ZachAI\kalshi\bots\guardrails.py`
- Create: `C:\ZachAI\kalshi\bots\tests\test_guardrails.py`

- [ ] **Step 1: Write test_guardrails.py**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import guardrails

def _state(trades=0, daily_pnl=0, consecutive_losses=0, capital=1000):
    return {
        "trades_count": trades,
        "daily_pnl": daily_pnl,
        "consecutive_losses": consecutive_losses,
        "capital": capital,
    }

def test_all_clear():
    ok, reason = guardrails.check(_state(), bet_amount=50)
    assert ok is True
    assert reason == ""

def test_max_daily_trades_blocks():
    ok, reason = guardrails.check(_state(trades=5), bet_amount=10)
    assert ok is False
    assert "MAX_DAILY_TRADES" in reason

def test_max_daily_loss_blocks():
    ok, reason = guardrails.check(_state(daily_pnl=-150), bet_amount=10)
    assert ok is False
    assert "MAX_DAILY_LOSS" in reason

def test_max_bet_clamps():
    clamped = guardrails.clamp_bet(500, capital=1000)
    assert clamped <= 100  # MAX_BET cap

def test_capital_at_risk_clamps():
    # 40% of 1000 = 400; bet of 300 should be allowed but 500 should clamp
    clamped = guardrails.clamp_bet(500, capital=1000, at_risk=0)
    assert clamped <= 400

def test_consecutive_losses_blocks():
    ok, reason = guardrails.check(_state(consecutive_losses=3), bet_amount=10)
    assert ok is False
    assert "CONSECUTIVE_LOSSES" in reason
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/test_guardrails.py -v
```

Expected: `ModuleNotFoundError: No module named 'guardrails'`

- [ ] **Step 3: Write guardrails.py**

```python
"""Risk management — 5 hard guardrails enforced before every trade."""
import config
import database

def check(daily_state: dict, bet_amount: float) -> tuple[bool, str]:
    """
    Returns (True, "") if trade is allowed, or (False, reason_string) if blocked.
    Checks: MAX_DAILY_TRADES, MAX_DAILY_LOSS, MAX_CONSECUTIVE_LOSSES,
            MAX_BET, MAX_CAPITAL_AT_RISK.
    """
    # 1. Daily trade count
    if daily_state["trades_count"] >= config.MAX_DAILY_TRADES:
        return False, f"MAX_DAILY_TRADES ({config.MAX_DAILY_TRADES}) reached"

    # 2. Daily loss ceiling
    if daily_state["daily_pnl"] <= -config.MAX_DAILY_LOSS:
        return False, f"MAX_DAILY_LOSS (${config.MAX_DAILY_LOSS}) hit"

    # 3. Consecutive losses
    if daily_state["consecutive_losses"] >= config.MAX_CONSECUTIVE_LOSSES:
        return False, f"MAX_CONSECUTIVE_LOSSES ({config.MAX_CONSECUTIVE_LOSSES}) reached"

    # 4. Single bet size
    if bet_amount > config.MAX_BET:
        return False, f"Bet ${bet_amount:.2f} exceeds MAX_BET ${config.MAX_BET}"

    # 5. Capital at risk — computed at call-site, but sanity-check the amount
    max_risk = daily_state["capital"] * config.MAX_CAPITAL_AT_RISK
    if bet_amount > max_risk:
        return False, f"Bet ${bet_amount:.2f} exceeds MAX_CAPITAL_AT_RISK (${max_risk:.2f})"

    return True, ""

def clamp_bet(desired: float, capital: float, at_risk: float = 0.0) -> float:
    """
    Clamp desired bet to respect MAX_BET and MAX_CAPITAL_AT_RISK.
    at_risk: dollars already at risk today (open positions).
    """
    available_risk = capital * config.MAX_CAPITAL_AT_RISK - at_risk
    return min(desired, config.MAX_BET, max(0.0, available_risk))

def get_status(daily_state: dict) -> dict:
    """Return a snapshot of all guardrail statuses for the dashboard."""
    trades_pct = daily_state["trades_count"] / config.MAX_DAILY_TRADES
    loss_pct   = abs(min(0, daily_state["daily_pnl"])) / config.MAX_DAILY_LOSS
    consec_pct = daily_state["consecutive_losses"] / config.MAX_CONSECUTIVE_LOSSES

    return {
        "daily_trades":  {
            "value": daily_state["trades_count"],
            "limit": config.MAX_DAILY_TRADES,
            "pct":   min(1.0, trades_pct),
            "ok":    daily_state["trades_count"] < config.MAX_DAILY_TRADES,
        },
        "daily_loss": {
            "value": daily_state["daily_pnl"],
            "limit": -config.MAX_DAILY_LOSS,
            "pct":   min(1.0, loss_pct),
            "ok":    daily_state["daily_pnl"] > -config.MAX_DAILY_LOSS,
        },
        "consecutive_losses": {
            "value": daily_state["consecutive_losses"],
            "limit": config.MAX_CONSECUTIVE_LOSSES,
            "pct":   min(1.0, consec_pct),
            "ok":    daily_state["consecutive_losses"] < config.MAX_CONSECUTIVE_LOSSES,
        },
        "max_bet":  {"value": config.MAX_BET, "ok": True},
        "capital_at_risk": {
            "limit_pct": config.MAX_CAPITAL_AT_RISK,
            "ok":        True,
        },
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/test_guardrails.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd C:\ZachAI
git add kalshi/bots/guardrails.py kalshi/bots/tests/test_guardrails.py
git commit -m "feat(weatheralpha): guardrails engine + tests"
```

---

## Task 6: Trading Logic (Edge + Kelly)

**Files:**
- Create: `C:\ZachAI\kalshi\bots\trader.py`
- Create: `C:\ZachAI\kalshi\bots\tests\test_trader.py`

- [ ] **Step 1: Write test_trader.py**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import trader

def test_edge_above_threshold_triggers_yes():
    # Forecast 85°F, threshold 80°F → our_prob > 0.5, kalshi says 0.35 → edge 15%+
    signal = trader.compute_signal(
        forecast_f=85.0, threshold_f=80.0, kalshi_prob=0.35
    )
    assert signal["side"] == "YES"
    assert signal["edge"] >= 0.08

def test_edge_below_threshold_triggers_no():
    # Forecast 60°F, threshold 75°F → our_prob < 0.5, kalshi says 0.65 → NO edge
    signal = trader.compute_signal(
        forecast_f=60.0, threshold_f=75.0, kalshi_prob=0.65
    )
    assert signal["side"] == "NO"
    assert signal["edge"] >= 0.08

def test_no_edge_returns_none():
    # Forecast matches threshold — no significant edge
    signal = trader.compute_signal(
        forecast_f=72.0, threshold_f=72.0, kalshi_prob=0.50
    )
    assert signal is None

def test_kelly_size_capped_at_max_bet():
    size = trader.kelly_bet_size(
        edge=0.40, kalshi_prob=0.50, capital=10000
    )
    assert size <= 100  # MAX_BET cap

def test_kelly_size_is_positive():
    size = trader.kelly_bet_size(
        edge=0.10, kalshi_prob=0.40, capital=1000
    )
    assert size > 0

def test_contracts_from_dollars():
    # $50 bet at 50¢ per contract → 100 contracts
    contracts = trader.dollars_to_contracts(50.0, price_cents=50)
    assert contracts == 100
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/test_trader.py -v
```

Expected: `ModuleNotFoundError: No module named 'trader'`

- [ ] **Step 3: Write trader.py**

```python
"""
Core trading logic.

Edge model:
  - We model the actual high temperature as Normal(forecast_f, FORECAST_SIGMA_F)
  - our_prob = P(actual > threshold_f) = 1 - Φ((threshold_f - forecast_f) / σ)
  - edge = our_prob - kalshi_prob  (positive → bet YES; negative → bet NO)
  - |edge| must exceed config.MIN_EDGE (8%)

Kelly sizing (fractional):
  - For YES: b = (1 - p_k) / p_k  (net odds if we pay p_k per contract)
  - f = (p_our * b - (1 - p_our)) / b  (Kelly fraction of bankroll)
  - quarter_kelly = f * KELLY_FRACTION
  - bet = quarter_kelly * capital  then clamped by guardrails.clamp_bet()
"""
import math
from scipy.stats import norm
import config
import guardrails
import database
import kalshi_client
from datetime import date

def compute_signal(
    forecast_f: float, threshold_f: float, kalshi_prob: float
) -> dict | None:
    """
    Returns a signal dict or None if no tradeable edge.
    Signal keys: side ('YES'|'NO'), edge (float), our_prob, kalshi_prob, threshold_f
    """
    sigma = config.FORECAST_SIGMA_F
    our_prob = 1.0 - norm.cdf((threshold_f - forecast_f) / sigma)
    edge = our_prob - kalshi_prob

    if edge >= config.MIN_EDGE:
        return {
            "side": "YES",
            "edge": edge,
            "our_prob": our_prob,
            "kalshi_prob": kalshi_prob,
            "threshold_f": threshold_f,
        }
    if edge <= -config.MIN_EDGE:
        return {
            "side": "NO",
            "edge": abs(edge),
            "our_prob": 1.0 - our_prob,       # prob we win on NO side
            "kalshi_prob": 1.0 - kalshi_prob,  # implied prob from NO side
            "threshold_f": threshold_f,
        }
    return None

def kelly_bet_size(edge: float, kalshi_prob: float, capital: float) -> float:
    """
    Quarter-Kelly bet in dollars, before guardrail clamping.
    """
    p = kalshi_prob  # price we pay per contract (0-1)
    if p <= 0 or p >= 1:
        return 0.0
    b = (1.0 - p) / p      # net odds
    f = (edge - (1.0 - edge - edge) ) / b  # simplified Kelly
    # Standard Kelly: f = (p_win * b - p_lose) / b
    p_win = edge + p  # our probability of winning
    p_lose = 1.0 - p_win
    f = (p_win * b - p_lose) / b
    f = max(0.0, f)
    quarter_kelly = f * config.KELLY_FRACTION
    return quarter_kelly * capital

def dollars_to_contracts(dollars: float, price_cents: int) -> int:
    """Convert dollar bet amount to integer contract count."""
    if price_cents <= 0:
        return 0
    return max(1, int(dollars * 100 / price_cents))

def evaluate_city(city_code: str) -> dict:
    """
    Full pipeline for one city:
    1. Fetch weather forecast
    2. Find Kalshi market
    3. Compute signal
    4. Check guardrails
    5. Execute (or paper-log) trade
    Returns a status dict for the dashboard.
    """
    import weather

    result = {
        "city": city_code,
        "forecast_f": None,
        "market_ticker": None,
        "signal": None,
        "action": "no_trade",
        "reason": "",
        "trade_id": None,
    }

    # 1. Weather
    forecast_f = weather.get_forecast_high(city_code)
    if forecast_f is None:
        result["reason"] = "weather fetch failed"
        database.insert_scan(city_code, 0, action="error")
        return result
    result["forecast_f"] = forecast_f

    # 2. Kalshi market
    today = date.today().strftime("%Y%m%d")
    client = kalshi_client.get_client()
    market = client.get_best_market_for_forecast(city_code, forecast_f, today)

    if market is None:
        # No live market — simulate for paper mode
        threshold_f = round(forecast_f)
        kalshi_prob = 0.50  # neutral price
        market = {
            "ticker": f"SIM-{city_code}-{today}-{int(threshold_f)}",
            "yes_ask": 50,
            "simulated": True,
        }
        database.log(
            f"[{city_code}] No Kalshi market found — using simulated price", "WARN"
        )
    else:
        threshold_f = float(market["ticker"].split("-")[-1])

    kalshi_prob = client.get_market_prob(market) or 0.50
    result["market_ticker"] = market["ticker"]

    # 3. Signal
    signal = compute_signal(forecast_f, threshold_f, kalshi_prob)
    database.insert_scan(
        city_code, forecast_f, threshold_f, signal["our_prob"] if signal else None,
        kalshi_prob, signal["edge"] if signal else None,
        action=signal["side"].lower() if signal else "no_trade",
    )

    if signal is None:
        result["reason"] = f"edge below {config.MIN_EDGE*100:.0f}%"
        return result
    result["signal"] = signal

    # 4. Guardrails
    daily_state = database.get_daily_state()
    price_cents = int(kalshi_prob * 100) if signal["side"] == "YES" else int((1 - kalshi_prob) * 100)
    raw_bet = kelly_bet_size(signal["edge"], kalshi_prob, daily_state["capital"])
    bet_amount = guardrails.clamp_bet(raw_bet, daily_state["capital"])

    ok, reason = guardrails.check(daily_state, bet_amount)
    if not ok:
        result["action"] = "blocked"
        result["reason"] = reason
        database.log(f"[{city_code}] Trade blocked: {reason}", "WARN")
        return result

    # 5. Execute
    contracts = dollars_to_contracts(bet_amount, price_cents)
    order = client.place_order(
        market["ticker"], signal["side"].lower(), contracts, price_cents
    )

    if order is None:
        result["action"] = "error"
        result["reason"] = "order placement failed"
        return result

    trade_id = database.insert_trade(
        city_code, market["ticker"], signal["side"],
        signal["our_prob"], signal["kalshi_prob"], signal["edge"],
        bet_amount, contracts, price_cents, paper=config.PAPER_MODE,
    )

    # Update daily state
    new_trades = daily_state["trades_count"] + 1
    database.update_daily_state(trades_count=new_trades)

    result["action"] = "traded"
    result["trade_id"] = trade_id
    database.log(
        f"[{city_code}] {'PAPER ' if config.PAPER_MODE else ''}TRADE: "
        f"{signal['side']} {contracts}x {market['ticker']} @ {price_cents}¢ "
        f"edge={signal['edge']*100:.1f}%"
    )
    return result
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/test_trader.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd C:\ZachAI
git add kalshi/bots/trader.py kalshi/bots/tests/test_trader.py
git commit -m "feat(weatheralpha): edge+Kelly trading logic + tests"
```

---

## Task 7: Flask API + APScheduler

**Files:**
- Create: `C:\ZachAI\kalshi\bots\app.py`

- [ ] **Step 1: Write app.py**

```python
"""
WeatherAlpha backend — Flask REST API + APScheduler.

Endpoints:
  GET  /api/status            Bot status + mode
  GET  /api/cities            Latest city scan results
  GET  /api/trades            All trades (last 100)
  GET  /api/trades/active     Open positions
  GET  /api/pnl               Cumulative P&L series
  GET  /api/guardrails        Guardrail status snapshot
  GET  /api/logs              Activity log (last 50)
  POST /api/scan              Trigger manual city scan
  POST /api/mode              Toggle PAPER_MODE (body: {"paper": true/false})
"""
import os
import pytz
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import database
import trader
import guardrails

app = Flask(__name__, static_folder="../dashboard/dist", static_url_path="")
CORS(app)

scheduler = BackgroundScheduler(timezone=pytz.timezone(config.TIMEZONE))

# ── Scheduled jobs ────────────────────────────────────────────────────────────

def scan_all_cities():
    """Run every SCAN_INTERVAL_MINUTES during the trade window."""
    cst = pytz.timezone(config.TIMEZONE)
    now_hour = datetime.now(cst).hour
    if not (config.TRADE_WINDOW_START_HOUR <= now_hour < config.TRADE_WINDOW_END_HOUR):
        return
    database.log("Scheduled city scan started")
    for city_code in config.CITIES:
        try:
            trader.evaluate_city(city_code)
        except Exception as exc:
            database.log(f"Error scanning {city_code}: {exc}", "ERROR")
    database.log("Scheduled city scan complete")

def reset_daily_counters():
    """Midnight reset — carry forward capital balance."""
    state = database.get_daily_state()
    new_capital = state["capital"] + state.get("daily_pnl_realized", 0)
    database.log("Daily counters reset")

scheduler.add_job(
    scan_all_cities,
    CronTrigger(
        minute=f"*/{config.SCAN_INTERVAL_MINUTES}",
        hour=f"{config.TRADE_WINDOW_START_HOUR}-{config.TRADE_WINDOW_END_HOUR-1}",
        timezone=config.TIMEZONE,
    ),
    id="city_scan",
    replace_existing=True,
)
scheduler.add_job(
    reset_daily_counters,
    CronTrigger(hour=0, minute=1, timezone=config.TIMEZONE),
    id="daily_reset",
    replace_existing=True,
)

# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    cst = pytz.timezone(config.TIMEZONE)
    now = datetime.now(cst)
    in_window = config.TRADE_WINDOW_START_HOUR <= now.hour < config.TRADE_WINDOW_END_HOUR
    state = database.get_daily_state()
    return jsonify({
        "bot_name":   "WeatherAlpha",
        "paper_mode": config.PAPER_MODE,
        "active":     in_window,
        "time_cst":   now.strftime("%H:%M:%S"),
        "date":       now.date().isoformat(),
        "trade_window": f"{config.TRADE_WINDOW_START_HOUR:02d}:00–{config.TRADE_WINDOW_END_HOUR:02d}:00 CST",
        "capital":    state["capital"],
        "daily_pnl":  state["daily_pnl"],
        "trades_today": state["trades_count"],
    })

@app.route("/api/cities")
def api_cities():
    scans = database.get_latest_scans()
    return jsonify({"cities": scans})

@app.route("/api/trades")
def api_trades():
    trades = database.get_trades(limit=100)
    return jsonify({"trades": trades})

@app.route("/api/trades/active")
def api_trades_active():
    trades = database.get_trades(status="open")
    return jsonify({"trades": trades})

@app.route("/api/pnl")
def api_pnl():
    series = database.get_pnl_series()
    state  = database.get_daily_state()
    all_trades = database.get_trades(limit=1000)
    won   = [t for t in all_trades if t["status"] == "won"]
    lost  = [t for t in all_trades if t["status"] == "lost"]
    total = len(won) + len(lost)
    win_rate = len(won) / total if total else 0
    total_pnl = sum(t["pnl"] for t in all_trades)
    return jsonify({
        "series":    series,
        "total_pnl": round(total_pnl, 2),
        "win_rate":  round(win_rate, 4),
        "total_trades": total,
        "capital":   state["capital"],
    })

@app.route("/api/guardrails")
def api_guardrails():
    state = database.get_daily_state()
    return jsonify(guardrails.get_status(state))

@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": database.get_logs(limit=50)})

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Trigger an immediate scan (ignores trade window)."""
    results = []
    for city_code in config.CITIES:
        try:
            r = trader.evaluate_city(city_code)
            results.append(r)
        except Exception as exc:
            results.append({"city": city_code, "error": str(exc)})
    return jsonify({"results": results})

@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.get_json(force=True)
    config.PAPER_MODE = bool(data.get("paper", True))
    database.log(f"Mode changed to {'PAPER' if config.PAPER_MODE else 'LIVE'}")
    return jsonify({"paper_mode": config.PAPER_MODE})

# ── SPA fallback ──────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    dist = os.path.join(app.static_folder or "", path)
    if os.path.exists(dist):
        return app.send_static_file(path)
    return app.send_static_file("index.html")

# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    database.init_db()
    database.log("WeatherAlpha bot started")
    scheduler.start()
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        use_reloader=False,
    )

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test that Flask starts**

```bash
cd C:\ZachAI\kalshi\bots
python app.py &
sleep 3
curl http://localhost:5000/api/status
```

Expected: JSON with `bot_name: "WeatherAlpha"`, `paper_mode: true`.
Kill it after: `kill %1` (Linux) or Ctrl+C.

- [ ] **Step 3: Test manual scan endpoint**

```bash
curl -X POST http://localhost:5000/api/scan
```

Expected: JSON array with 6 city results, each with `forecast_f` populated.

- [ ] **Step 4: Commit**

```bash
cd C:\ZachAI
git add kalshi/bots/app.py
git commit -m "feat(weatheralpha): Flask API + APScheduler orchestration"
```

---

## Task 8: React Dashboard — Scaffolding + Cyberpunk Theme

**Files:**
- Create: `C:\ZachAI\kalshi\dashboard\package.json`
- Create: `C:\ZachAI\kalshi\dashboard\vite.config.js`
- Create: `C:\ZachAI\kalshi\dashboard\index.html`
- Create: `C:\ZachAI\kalshi\dashboard\src\main.jsx`
- Create: `C:\ZachAI\kalshi\dashboard\src\App.css`
- Create: `C:\ZachAI\kalshi\dashboard\src\App.jsx`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "weatheralpha-dashboard",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev":   "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.12.7"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.1"
  }
}
```

- [ ] **Step 2: Create vite.config.js**

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:5000",
    },
  },
  build: {
    outDir: "dist",
  },
});
```

- [ ] **Step 3: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>WeatherAlpha</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Create src/main.jsx**

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./App.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 5: Create src/App.css** (global cyberpunk theme)

```css
/* ── Cyberpunk Theme Variables ───────────────────────────────── */
:root {
  --bg:          #050505;
  --surface:     #0d0d0d;
  --surface2:    #111111;
  --border:      #00ff41;
  --glow:        0 0 8px #00ff41, 0 0 20px rgba(0,255,65,0.3);
  --glow-sm:     0 0 4px #00ff41;
  --text:        #00ff41;
  --text-dim:    #4a8c57;
  --text-muted:  #2a4d30;
  --cyan:        #00b8ff;
  --cyan-glow:   0 0 8px #00b8ff;
  --amber:       #ffaa00;
  --red:         #ff0040;
  --red-glow:    0 0 8px #ff0040;
  --font-mono:   'Courier New', 'Lucida Console', monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
  min-height: 100vh;
  overflow-x: hidden;
}

/* Scanline overlay */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.08) 2px,
    rgba(0,0,0,0.08) 4px
  );
  pointer-events: none;
  z-index: 9999;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--glow);
  padding: 12px 16px;
  border-radius: 2px;
}

.panel-title {
  font-size: 11px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-bottom: 10px;
  border-bottom: 1px solid var(--text-muted);
  padding-bottom: 6px;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  border: 1px solid currentColor;
  border-radius: 2px;
}

.badge-green  { color: var(--text); border-color: var(--border); }
.badge-red    { color: var(--red);  border-color: var(--red);   }
.badge-amber  { color: var(--amber); border-color: var(--amber); }
.badge-cyan   { color: var(--cyan); border-color: var(--cyan);  }

.neon-text { text-shadow: var(--glow-sm); }
.glow      { box-shadow: var(--glow); }

/* Progress bar */
.progress-bar {
  height: 6px;
  background: var(--surface2);
  border: 1px solid var(--text-muted);
  border-radius: 1px;
  overflow: hidden;
  margin-top: 4px;
}
.progress-fill {
  height: 100%;
  transition: width 0.4s ease;
  background: var(--text);
}
.progress-fill.warn  { background: var(--amber); }
.progress-fill.danger { background: var(--red); box-shadow: var(--red-glow); }

/* Table */
.cyber-table { width: 100%; border-collapse: collapse; }
.cyber-table th {
  text-align: left;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--text-muted);
  padding: 4px 8px;
}
.cyber-table td {
  padding: 5px 8px;
  border-bottom: 1px solid #111;
  font-size: 12px;
}
.cyber-table tr:hover td { background: var(--surface2); }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--text-muted); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border); }
```

- [ ] **Step 6: Create src/App.jsx**

```jsx
import { useState, useEffect, useCallback } from "react";
import Header from "./components/Header.jsx";
import StatsBar from "./components/StatsBar.jsx";
import CityGrid from "./components/CityGrid.jsx";
import GuardrailPanel from "./components/GuardrailPanel.jsx";
import TradeTable from "./components/TradeTable.jsx";
import PnLChart from "./components/PnLChart.jsx";
import LogFeed from "./components/LogFeed.jsx";

const POLL_MS = 30_000;

export default function App() {
  const [status,     setStatus]     = useState(null);
  const [cities,     setCities]     = useState([]);
  const [trades,     setTrades]     = useState([]);
  const [pnl,        setPnl]        = useState(null);
  const [guardrails, setGuardrails] = useState(null);
  const [logs,       setLogs]       = useState([]);
  const [scanning,   setScanning]   = useState(false);

  const fetchAll = useCallback(async () => {
    const [s, c, t, p, g, l] = await Promise.allSettled([
      fetch("/api/status").then(r => r.json()),
      fetch("/api/cities").then(r => r.json()),
      fetch("/api/trades").then(r => r.json()),
      fetch("/api/pnl").then(r => r.json()),
      fetch("/api/guardrails").then(r => r.json()),
      fetch("/api/logs").then(r => r.json()),
    ]);
    if (s.status === "fulfilled") setStatus(s.value);
    if (c.status === "fulfilled") setCities(c.value.cities || []);
    if (t.status === "fulfilled") setTrades(t.value.trades || []);
    if (p.status === "fulfilled") setPnl(p.value);
    if (g.status === "fulfilled") setGuardrails(g.value);
    if (l.status === "fulfilled") setLogs(l.value.logs || []);
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleScan = async () => {
    setScanning(true);
    await fetch("/api/scan", { method: "POST" });
    await fetchAll();
    setScanning(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", gap: 8, padding: 12 }}>
      <Header status={status} onScan={handleScan} scanning={scanning} />
      <StatsBar status={status} pnl={pnl} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", gap: 8 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <CityGrid cities={cities} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <PnLChart pnl={pnl} />
            <LogFeed logs={logs} />
          </div>
          <TradeTable trades={trades} />
        </div>
        <GuardrailPanel guardrails={guardrails} />
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Install npm deps and verify build**

```bash
cd C:\ZachAI\kalshi\dashboard
npm install
npm run build
```

Expected: `dist/` folder created with `index.html` inside.

- [ ] **Step 8: Commit**

```bash
cd C:\ZachAI
git add kalshi/dashboard/
git commit -m "feat(weatheralpha): React dashboard scaffold + cyberpunk CSS"
```

---

## Task 9: Dashboard Components — Header, StatsBar, CityGrid, GuardrailPanel

**Files:**
- Create: `C:\ZachAI\kalshi\dashboard\src\components\Header.jsx`
- Create: `C:\ZachAI\kalshi\dashboard\src\components\StatsBar.jsx`
- Create: `C:\ZachAI\kalshi\dashboard\src\components\CityGrid.jsx`
- Create: `C:\ZachAI\kalshi\dashboard\src\components\GuardrailPanel.jsx`

- [ ] **Step 1: Create Header.jsx**

```jsx
export default function Header({ status, onScan, scanning }) {
  const paper = status?.paper_mode !== false;
  const active = status?.active;
  return (
    <div className="panel" style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 16px" }}>
      <span style={{ fontSize: 20, marginRight: 4 }}>⚡</span>
      <span style={{ fontSize: 16, letterSpacing: 4, fontWeight: "bold" }} className="neon-text">
        WEATHERALPHA
      </span>
      <span className={`badge ${paper ? "badge-amber" : "badge-red"}`}>
        {paper ? "PAPER MODE" : "⚠ LIVE MODE"}
      </span>
      <span className={`badge ${active ? "badge-green" : "badge-cyan"}`}>
        {active ? "● TRADING" : "○ STANDBY"}
      </span>
      <span style={{ color: "var(--text-dim)", marginLeft: 4 }}>
        {status?.trade_window}
      </span>
      <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
        <span style={{ color: "var(--text-dim)" }}>{status?.time_cst} CST</span>
        <button
          onClick={onScan}
          disabled={scanning}
          style={{
            background: "none",
            border: "1px solid var(--border)",
            color: "var(--text)",
            padding: "4px 14px",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            letterSpacing: 2,
            cursor: scanning ? "not-allowed" : "pointer",
            opacity: scanning ? 0.5 : 1,
            boxShadow: "var(--glow-sm)",
          }}
        >
          {scanning ? "SCANNING..." : "▶ SCAN NOW"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create StatsBar.jsx**

```jsx
function Stat({ label, value, color }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ color: "var(--text-dim)", fontSize: 10, letterSpacing: 2 }}>{label}</span>
      <span style={{ fontSize: 18, color: color || "var(--text)", textShadow: "var(--glow-sm)" }}>
        {value ?? "—"}
      </span>
    </div>
  );
}

export default function StatsBar({ status, pnl }) {
  const pnlVal = pnl?.total_pnl ?? 0;
  const pnlColor = pnlVal >= 0 ? "var(--text)" : "var(--red)";
  const winRate = pnl?.win_rate ? `${(pnl.win_rate * 100).toFixed(1)}%` : "—";
  return (
    <div className="panel" style={{ display: "flex", gap: 40, padding: "8px 16px" }}>
      <Stat label="CAPITAL"      value={`$${(status?.capital ?? 0).toFixed(2)}`} />
      <Stat label="TODAY P&L"    value={`${(status?.daily_pnl ?? 0) >= 0 ? "+" : ""}$${(status?.daily_pnl ?? 0).toFixed(2)}`}
            color={(status?.daily_pnl ?? 0) >= 0 ? "var(--text)" : "var(--red)"} />
      <Stat label="TOTAL P&L"    value={`${pnlVal >= 0 ? "+" : ""}$${pnlVal.toFixed(2)}`} color={pnlColor} />
      <Stat label="WIN RATE"     value={winRate} />
      <Stat label="TOTAL TRADES" value={pnl?.total_trades ?? "—"} />
      <Stat label="TODAY TRADES" value={`${status?.trades_today ?? 0} / 5`} />
    </div>
  );
}
```

- [ ] **Step 3: Create CityGrid.jsx**

```jsx
const CITY_NAMES = {
  NYC: "New York", CHI: "Chicago", MIA: "Miami",
  LAX: "Los Angeles", MEM: "Memphis", DEN: "Denver",
};

function CityCard({ scan }) {
  if (!scan) return null;
  const edge = scan.edge ? (scan.edge * 100).toFixed(1) : null;
  const actionColor = {
    "yes": "var(--text)",
    "no": "var(--cyan)",
    "no_trade": "var(--text-dim)",
    "blocked": "var(--amber)",
    "error": "var(--red)",
  }[scan.action] || "var(--text-dim)";

  return (
    <div className="panel" style={{ minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontWeight: "bold", fontSize: 14, letterSpacing: 2 }}>{scan.city}</span>
        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>{CITY_NAMES[scan.city]}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 0" }}>
        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>FORECAST</span>
        <span style={{ textAlign: "right" }}>
          {scan.forecast_f != null ? `${scan.forecast_f}°F` : "—"}
        </span>
        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>THRESHOLD</span>
        <span style={{ textAlign: "right" }}>
          {scan.threshold_f != null ? `${scan.threshold_f}°F` : "—"}
        </span>
        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>OUR PROB</span>
        <span style={{ textAlign: "right" }}>
          {scan.our_prob != null ? `${(scan.our_prob * 100).toFixed(1)}%` : "—"}
        </span>
        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>KALSHI</span>
        <span style={{ textAlign: "right" }}>
          {scan.kalshi_prob != null ? `${(scan.kalshi_prob * 100).toFixed(1)}%` : "—"}
        </span>
        <span style={{ color: "var(--text-dim)", fontSize: 10 }}>EDGE</span>
        <span style={{ textAlign: "right", color: edge && parseFloat(edge) >= 8 ? "var(--text)" : "var(--text-dim)" }}>
          {edge ? `${edge}%` : "—"}
        </span>
      </div>
      <div style={{ marginTop: 8, borderTop: "1px solid var(--text-muted)", paddingTop: 6, display: "flex", justifyContent: "center" }}>
        <span style={{ color: actionColor, fontSize: 11, letterSpacing: 3, textTransform: "uppercase" }}>
          {scan.action?.replace("_", " ") || "—"}
        </span>
      </div>
    </div>
  );
}

export default function CityGrid({ cities }) {
  const cityMap = Object.fromEntries((cities || []).map(c => [c.city, c]));
  const codes = ["NYC", "CHI", "MIA", "LAX", "MEM", "DEN"];
  return (
    <div>
      <div className="panel-title" style={{ marginBottom: 8 }}>CITY SCANNER</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
        {codes.map(code => (
          <CityCard key={code} scan={cityMap[code] || { city: code, action: "no_data" }} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create GuardrailPanel.jsx**

```jsx
function GuardrailRow({ label, value, limit, pct, ok }) {
  const fillClass = !ok ? "danger" : pct > 0.7 ? "warn" : "";
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
        <span style={{ color: ok ? "var(--text-dim)" : "var(--red)", fontSize: 10, letterSpacing: 1 }}>
          {!ok ? "⚠ " : "✓ "}{label}
        </span>
        <span style={{ fontSize: 11 }}>
          {value} / {limit}
        </span>
      </div>
      <div className="progress-bar">
        <div
          className={`progress-fill ${fillClass}`}
          style={{ width: `${Math.min(100, (pct || 0) * 100)}%` }}
        />
      </div>
    </div>
  );
}

export default function GuardrailPanel({ guardrails }) {
  if (!guardrails) return (
    <div className="panel">
      <div className="panel-title">GUARDRAILS</div>
      <span style={{ color: "var(--text-dim)" }}>Loading...</span>
    </div>
  );

  const dt = guardrails.daily_trades || {};
  const dl = guardrails.daily_loss    || {};
  const cl = guardrails.consecutive_losses || {};
  const allOk = dt.ok && dl.ok && cl.ok;

  return (
    <div className="panel" style={{ height: "fit-content" }}>
      <div className="panel-title">GUARDRAILS</div>

      <div style={{ marginBottom: 16, textAlign: "center" }}>
        <span className={`badge ${allOk ? "badge-green" : "badge-red"}`}>
          {allOk ? "ALL CLEAR" : "BREACHED"}
        </span>
      </div>

      <GuardrailRow
        label="DAILY TRADES"
        value={dt.value ?? 0}
        limit={dt.limit ?? 5}
        pct={dt.pct ?? 0}
        ok={dt.ok !== false}
      />
      <GuardrailRow
        label="DAILY LOSS"
        value={`$${Math.abs(dl.value ?? 0).toFixed(0)}`}
        limit={`$${Math.abs(dl.limit ?? 150)}`}
        pct={dl.pct ?? 0}
        ok={dl.ok !== false}
      />
      <GuardrailRow
        label="CONSEC LOSSES"
        value={cl.value ?? 0}
        limit={cl.limit ?? 3}
        pct={cl.pct ?? 0}
        ok={cl.ok !== false}
      />

      <div style={{ borderTop: "1px solid var(--text-muted)", paddingTop: 10, marginTop: 4 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ color: "var(--text-dim)", fontSize: 10 }}>MAX BET</span>
          <span style={{ color: "var(--cyan)" }}>${guardrails.max_bet?.value ?? 100}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-dim)", fontSize: 10 }}>CAPITAL AT RISK</span>
          <span style={{ color: "var(--cyan)" }}>
            {guardrails.capital_at_risk?.limit_pct ? `${(guardrails.capital_at_risk.limit_pct * 100).toFixed(0)}%` : "40%"}
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Verify dev server loads without errors**

```bash
cd C:\ZachAI\kalshi\dashboard
npm run dev
```

Expected: `Local: http://localhost:5173/` — open in browser, no console errors.

- [ ] **Step 6: Commit**

```bash
cd C:\ZachAI
git add kalshi/dashboard/src/components/
git commit -m "feat(weatheralpha): dashboard Header, StatsBar, CityGrid, GuardrailPanel"
```

---

## Task 10: Dashboard Components — TradeTable, PnLChart, LogFeed

**Files:**
- Create: `C:\ZachAI\kalshi\dashboard\src\components\TradeTable.jsx`
- Create: `C:\ZachAI\kalshi\dashboard\src\components\PnLChart.jsx`
- Create: `C:\ZachAI\kalshi\dashboard\src\components\LogFeed.jsx`

- [ ] **Step 1: Create TradeTable.jsx**

```jsx
const STATUS_COLOR = {
  open:      "var(--cyan)",
  won:       "var(--text)",
  lost:      "var(--red)",
  cancelled: "var(--text-dim)",
};

export default function TradeTable({ trades }) {
  return (
    <div className="panel">
      <div className="panel-title">TRADE HISTORY</div>
      {(!trades || trades.length === 0) ? (
        <div style={{ color: "var(--text-dim)", padding: "12px 0", textAlign: "center" }}>
          No trades yet.
        </div>
      ) : (
        <div style={{ overflowX: "auto", maxHeight: 240, overflowY: "auto" }}>
          <table className="cyber-table">
            <thead>
              <tr>
                <th>CITY</th><th>SIDE</th><th>EDGE</th><th>BET</th>
                <th>PRICE</th><th>CONTRACTS</th><th>STATUS</th><th>P&L</th><th>TIME</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.id}>
                  <td style={{ fontWeight: "bold" }}>{t.city}</td>
                  <td style={{ color: t.side === "YES" ? "var(--text)" : "var(--cyan)" }}>
                    {t.side}
                  </td>
                  <td>{(t.edge * 100).toFixed(1)}%</td>
                  <td>${t.bet_amount.toFixed(2)}</td>
                  <td>{t.price_cents}¢</td>
                  <td>{t.contracts}</td>
                  <td style={{ color: STATUS_COLOR[t.status] || "var(--text)" }}>
                    {t.paper ? "[P] " : ""}{t.status.toUpperCase()}
                  </td>
                  <td style={{ color: t.pnl >= 0 ? "var(--text)" : "var(--red)" }}>
                    {t.pnl !== 0 ? `${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(2)}` : "—"}
                  </td>
                  <td style={{ color: "var(--text-dim)" }}>
                    {t.created_at?.slice(11, 16)}Z
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create PnLChart.jsx**

```jsx
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      padding: "6px 10px", fontFamily: "var(--font-mono)", fontSize: 11,
    }}>
      <div style={{ color: "var(--text-dim)" }}>{label}</div>
      <div style={{ color: val >= 0 ? "var(--text)" : "var(--red)" }}>
        {val >= 0 ? "+" : ""}${val.toFixed(2)}
      </div>
    </div>
  );
};

export default function PnLChart({ pnl }) {
  const series = pnl?.series || [];
  const totalPnl = pnl?.total_pnl ?? 0;
  const lineColor = totalPnl >= 0 ? "#00ff41" : "#ff0040";

  return (
    <div className="panel">
      <div className="panel-title">CUMULATIVE P&L</div>
      {series.length === 0 ? (
        <div style={{ color: "var(--text-dim)", textAlign: "center", padding: "24px 0" }}>
          No resolved trades yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={lineColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" tick={{ fill: "#4a8c57", fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: "#4a8c57", fontSize: 9 }} tickLine={false} axisLine={false}
                   tickFormatter={v => `$${v}`} width={40} />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={0} stroke="#2a4d30" strokeDasharray="3 3" />
            <Area type="monotone" dataKey="pnl" stroke={lineColor} strokeWidth={2}
                  fill="url(#pnlGrad)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create LogFeed.jsx**

```jsx
const LEVEL_COLOR = {
  INFO:  "var(--text-dim)",
  WARN:  "var(--amber)",
  ERROR: "var(--red)",
};

export default function LogFeed({ logs }) {
  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
      <div className="panel-title">ACTIVITY LOG</div>
      <div style={{ overflowY: "auto", maxHeight: 180, display: "flex", flexDirection: "column", gap: 3 }}>
        {(!logs || logs.length === 0) ? (
          <span style={{ color: "var(--text-dim)" }}>No activity yet.</span>
        ) : (
          logs.map(entry => (
            <div key={entry.id} style={{ display: "flex", gap: 8, fontSize: 11 }}>
              <span style={{ color: "var(--text-muted)", flexShrink: 0 }}>
                {entry.ts?.slice(11, 19)}Z
              </span>
              <span style={{ color: LEVEL_COLOR[entry.level] || "var(--text-dim)", flexShrink: 0 }}>
                [{entry.level}]
              </span>
              <span style={{ color: "var(--text-dim)", wordBreak: "break-word" }}>
                {entry.message}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Final build check**

```bash
cd C:\ZachAI\kalshi\dashboard
npm run build
```

Expected: `dist/index.html` with no build errors.

- [ ] **Step 5: End-to-end test (run Flask + dev server together)**

Terminal 1:
```bash
cd C:\ZachAI\kalshi\bots
python app.py
```

Terminal 2:
```bash
cd C:\ZachAI\kalshi\dashboard
npm run dev
```

Open `http://localhost:5173` — dashboard should load with all panels, `SCAN NOW` button should work.

- [ ] **Step 6: Commit**

```bash
cd C:\ZachAI
git add kalshi/dashboard/src/components/TradeTable.jsx \
        kalshi/dashboard/src/components/PnLChart.jsx \
        kalshi/dashboard/src/components/LogFeed.jsx
git commit -m "feat(weatheralpha): TradeTable, PnLChart, LogFeed components"
```

---

## Task 11: Railway Deployment Config

**Files:**
- Create: `C:\ZachAI\kalshi\railway.toml`
- Create: `C:\ZachAI\kalshi\nixpacks.toml`
- Create: `C:\ZachAI\kalshi\Procfile`
- Create: `C:\ZachAI\kalshi\start.sh`
- Create: `C:\ZachAI\kalshi\start.bat`

- [ ] **Step 1: Create railway.toml**

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "bash start.sh"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

- [ ] **Step 2: Create nixpacks.toml**

```toml
[phases.setup]
nixPkgs = ["nodejs_20", "python311"]

[phases.install]
cmds = [
  "pip install -r requirements.txt",
  "cd dashboard && npm ci && npm run build"
]

[start]
cmd = "cd bots && python app.py"
```

- [ ] **Step 3: Create Procfile**

```
web: bash start.sh
```

- [ ] **Step 4: Create start.sh**

```bash
#!/usr/bin/env bash
set -e
echo "==> Building React dashboard..."
cd /app/dashboard
npm ci --silent
npm run build
echo "==> Starting WeatherAlpha bot..."
cd /app/bots
exec python app.py
```

- [ ] **Step 5: Create start.bat** (Windows dev launcher)

```bat
@echo off
echo === WeatherAlpha Launcher ===
echo.
echo [1/2] Starting Flask backend...
start "WeatherAlpha Bot" cmd /k "cd /d C:\ZachAI\kalshi\bots && python app.py"
echo [2/2] Starting React dashboard dev server...
start "WeatherAlpha Dashboard" cmd /k "cd /d C:\ZachAI\kalshi\dashboard && npm run dev"
echo.
echo Backend:   http://localhost:5000/api/status
echo Dashboard: http://localhost:5173
echo.
pause
```

- [ ] **Step 6: Commit all deployment files**

```bash
cd C:\ZachAI
git add kalshi/railway.toml kalshi/nixpacks.toml kalshi/Procfile kalshi/start.sh kalshi/start.bat
git commit -m "feat(weatheralpha): Railway + Windows deployment config"
```

---

## Task 12: Integration Test + Final Verification

- [ ] **Step 1: Run all Python tests**

```bash
cd C:\ZachAI\kalshi\bots
python -m pytest tests/ -v
```

Expected: `14 passed` (weather×2, guardrails×6, trader×6)

- [ ] **Step 2: Verify all API endpoints respond**

```bash
# Start bot first
cd C:\ZachAI\kalshi\bots && python app.py &
sleep 3

curl -s http://localhost:5000/api/status    | python -m json.tool | head -5
curl -s http://localhost:5000/api/guardrails| python -m json.tool | head -5
curl -s http://localhost:5000/api/cities   | python -m json.tool | head -5
curl -sX POST http://localhost:5000/api/scan | python -m json.tool | head -20
```

Expected: All return valid JSON, scan returns 6 city results.

- [ ] **Step 3: Verify dashboard prod build is served by Flask**

```bash
cd C:\ZachAI\kalshi\dashboard && npm run build
cp -r dist/ ../bots/../dashboard/dist/  # already at correct path
curl http://localhost:5000/
```

Expected: Returns HTML (the React app's `index.html`).

- [ ] **Step 4: Run start.bat (Windows)**

Double-click `C:\ZachAI\kalshi\start.bat` or:
```bat
C:\ZachAI\kalshi\start.bat
```

Expected: Two cmd windows open — bot on 5000, dashboard on 5173.

- [ ] **Step 5: Final commit + push**

```bash
cd C:\ZachAI
git add -A
git commit -m "feat(weatheralpha): complete WeatherAlpha Kalshi trading bot v1.0"
git push origin master
```

---

## Spec Coverage Checklist

| Requirement | Task |
|---|---|
| Python bot + Flask API | Task 7 |
| SQLite database | Task 2 |
| APScheduler | Task 7 |
| NYC, CHI, MIA, LAX, MEM, DEN cities | Task 1 (config), Task 6 |
| Open-Meteo forecast | Task 3 |
| Kalshi KXHIGH market comparison | Task 4 |
| Edge ≥ 8% threshold | Task 6 |
| Quarter-Kelly sizing | Task 6 |
| MAX_BET=$100 | Task 5 |
| MAX_DAILY_TRADES=5 | Task 5 |
| MAX_DAILY_LOSS=$150 | Task 5 |
| MAX_CAPITAL_AT_RISK=40% | Task 5 |
| MAX_CONSECUTIVE_LOSSES=3 | Task 5 |
| 6AM–10AM CST trade window | Task 7 |
| Paper mode first | Task 1 (config), Task 4 |
| Cyberpunk dark theme React dashboard | Tasks 8–10 |
| Neon green accents | Task 8 (App.css) |
| Trade monitoring panel | Task 10 (TradeTable) |
| P&L tracking | Task 10 (PnLChart) |
| Guardrail status display | Task 9 (GuardrailPanel) |
| Store in C:\ZachAI\kalshi | All tasks |
| Railway deployable | Task 11 |
| All tests pass | Task 12 |
