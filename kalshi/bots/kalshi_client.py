"""
Kalshi API client — RSA-PSS authentication (API v2).
Supports demo (demo-api.kalshi.co) and live (api.elections.kalshi.com).
Paper mode: orders logged but never sent to Kalshi.

Auth flow (per Kalshi docs):
  Headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE
  Signature: RSA-PSS SHA256 of (timestamp_ms + METHOD + path_without_query)
"""
import base64
import logging
import time
from datetime import date
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import (
    KALSHI_BASE, KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH,
    KALSHI_DEMO, PAPER_MODE, CITIES
)

log = logging.getLogger(__name__)


def _load_private_key():
    path = Path(KALSHI_PRIVATE_KEY_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Kalshi private key not found: {path}")
    pem = path.read_bytes()
    return serialization.load_pem_private_key(pem, password=None)


def _sign(private_key, timestamp_ms: int, method: str, path: str) -> str:
    """
    RSA-PSS SHA256 signature of: str(timestamp_ms) + METHOD + /path/without/query
    Returns base64-encoded signature string.
    """
    # Strip query string from path
    path_no_query = path.split("?")[0]
    message = f"{timestamp_ms}{method.upper()}{path_no_query}".encode()
    sig = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode()


class KalshiClient:
    def __init__(self):
        self.session = requests.Session()
        self._private_key = None
        self._ready = False

    def login(self) -> bool:
        """Load RSA private key and verify credentials are set."""
        if not KALSHI_API_KEY_ID:
            log.warning("KALSHI_API_KEY_ID not set — market data unavailable (paper mode OK)")
            return False
        if not KALSHI_PRIVATE_KEY_PATH:
            log.warning("KALSHI_PRIVATE_KEY_PATH not set — market data unavailable")
            return False
        try:
            self._private_key = _load_private_key()
            self._ready = True
            log.info("Kalshi RSA key loaded (demo=%s, key=%s…)", KALSHI_DEMO,
                     KALSHI_API_KEY_ID[:8])
            return True
        except Exception as exc:
            log.error("Failed to load Kalshi private key: %s", exc)
            return False

    def _auth_headers(self, method: str, path: str) -> dict:
        ts = int(time.time() * 1000)
        sig = _sign(self._private_key, ts, method, path)
        return {
            "KALSHI-ACCESS-KEY":       KALSHI_API_KEY_ID,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "KALSHI-ACCESS-SIGNATURE": sig,
            "Content-Type":            "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url  = f"{KALSHI_BASE}{path}"
        hdrs = self._auth_headers("GET", path) if self._ready else {}
        resp = self.session.get(url, params=params, headers=hdrs, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        url  = f"{KALSHI_BASE}{path}"
        hdrs = self._auth_headers("POST", path) if self._ready else {}
        resp = self.session.post(url, json=body, headers=hdrs, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── Market discovery (public — no auth needed for market data) ────────────

    def get_market(self, ticker: str) -> dict | None:
        try:
            data = self._get(f"/markets/{ticker}")
            return data.get("market")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def search_kxhigh_markets(self, city_code: str, target_date: str | None = None) -> list[dict]:
        series = CITIES[city_code]["kalshi_series"]
        dt     = (target_date or date.today().isoformat()).replace("-", "")
        # Live ticker format: KXHIGHNY-26APR05-T67 (YYMONDD)
        try:
            data     = self._get("/markets", params={"series_ticker": series, "status": "open", "limit": 100})
            markets  = data.get("markets", [])
            markets.sort(key=lambda m: m.get("ticker", ""))
            return markets
        except Exception as exc:
            log.warning("Market search failed for %s: %s", city_code, exc)
            return []

    def get_orderbook(self, ticker: str) -> dict | None:
        try:
            data       = self._get(f"/markets/{ticker}/orderbook")
            book       = data.get("orderbook", {})
            yes_levels = book.get("yes", [])
            no_levels  = book.get("no", [])
            return {
                "yes":    yes_levels[0][0] if yes_levels else None,
                "no":     no_levels[0][0]  if no_levels  else None,
                "ticker": ticker,
            }
        except Exception:
            return None

    # ── Authenticated endpoints ────────────────────────────────────────────────

    def get_balance(self) -> float:
        if not self._ready:
            return 0.0
        try:
            data = self._get("/portfolio/balance")
            return data.get("balance", 0) / 100
        except Exception:
            return 0.0

    def get_positions(self) -> list[dict]:
        if not self._ready:
            return []
        try:
            return self._get("/portfolio/positions").get("market_positions", [])
        except Exception:
            return []

    def place_order(self, ticker: str, side: str, contracts: int,
                    price_cents: int, client_order_id: str = "") -> dict:
        if PAPER_MODE:
            log.info("[PAPER] %s %s x%d @ %d¢", ticker, side.upper(), contracts, price_cents)
            return {
                "order_id":  f"PAPER-{ticker}-{side}-{contracts}",
                "ticker":    ticker,
                "side":      side,
                "contracts": contracts,
                "price":     price_cents,
                "status":    "paper_filled",
                "paper":     True,
            }
        if not self._ready:
            raise RuntimeError("Kalshi client not authenticated")

        body = {
            "ticker":          ticker,
            "action":          "buy",
            "side":            side,
            "type":            "limit",
            "count":           contracts,
            "yes_price":       price_cents if side == "yes" else 100 - price_cents,
            "no_price":        price_cents if side == "no"  else 100 - price_cents,
            "client_order_id": client_order_id,
        }
        return self._post("/portfolio/orders", body)


# Singleton
_client: KalshiClient | None = None


def get_client() -> KalshiClient:
    global _client
    if _client is None:
        _client = KalshiClient()
        _client.login()
    return _client
