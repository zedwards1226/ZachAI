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
    RSA-PSS SHA256 signature of: str(timestamp_ms) + METHOD + FULL_PATH
    Returns base64-encoded signature string.

    FULL_PATH must include the /trade-api/v2/ prefix per Kalshi docs — using
    just /portfolio/balance returns 401. This was a latent bug never caught
    in paper mode (paper-mode orders short-circuit before _sign is called),
    surfaced 2026-05-15 when the first authenticated probe hit the live API.
    """
    # Strip query string + ensure /trade-api/v2 prefix
    path_no_query = path.split("?")[0]
    if not path_no_query.startswith("/trade-api/"):
        path_no_query = "/trade-api/v2" + path_no_query
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

    def _check_response(self, resp, method: str, path: str) -> None:
        """raise_for_status() that ALSO logs Kalshi's response body. The default
        behavior throws away the response text, which is exactly what hid the
        weekend's 400 'invalid_order' error. Now every non-2xx surfaces the
        full error detail in the log AND attaches it to the exception."""
        if resp.status_code >= 400:
            try:
                detail = resp.text[:500]
            except Exception:
                detail = "<no response body>"
            log.error(
                "Kalshi %s %s -> %s: %s",
                method, path, resp.status_code, detail,
            )
            # raise_for_status() with the body embedded in the message
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                e.args = (f"{e.args[0]} | body: {detail}",)
                raise

    def _get(self, path: str, params: dict | None = None) -> dict:
        url  = f"{KALSHI_BASE}{path}"
        hdrs = self._auth_headers("GET", path) if self._ready else {}
        resp = self.session.get(url, params=params, headers=hdrs, timeout=10)
        self._check_response(resp, "GET", path)
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        url  = f"{KALSHI_BASE}{path}"
        hdrs = self._auth_headers("POST", path) if self._ready else {}
        resp = self.session.post(url, json=body, headers=hdrs, timeout=10)
        self._check_response(resp, "POST", path)
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
        """Live Kalshi cash balance in dollars. Raises HTTPError on auth
        failure (401/403) so the caller can distinguish 'auth broken' from
        'empty account'. Network / JSON errors still return 0 (transient).

        Old behavior swallowed ALL exceptions and returned 0.0, hiding
        the 401 from the bad-credentials episode. Caller (trader.get_capital)
        now logs the actual reason."""
        if not self._ready:
            return 0.0
        try:
            data = self._get("/portfolio/balance")
            return data.get("balance", 0) / 100
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in (401, 403):
                # Re-raise so caller surfaces the auth failure instead of
                # falling back silently to STARTING_CAPITAL.
                log.error("Kalshi /portfolio/balance auth failed (%s) — credentials broken", status)
                raise
            # Other HTTP errors (5xx, 429, etc.) are transient — return 0
            # so the caller falls back to STARTING_CAPITAL gracefully.
            log.warning("Kalshi /portfolio/balance HTTP %s — returning 0", status)
            return 0.0
        except Exception as exc:
            log.warning("Kalshi /portfolio/balance failed: %s — returning 0", exc)
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
                "order_id":        f"PAPER-{ticker}-{side}-{contracts}",
                "ticker":          ticker,
                "side":            side,
                "contracts":       contracts,
                "price":           price_cents,
                "status":          "paper_filled",
                "client_order_id": client_order_id,
                "paper":           True,
            }
        if not self._ready:
            raise RuntimeError("Kalshi client not authenticated")

        # Kalshi /portfolio/orders body — current API spec (2026-05-18 verified):
        # Required: ticker, side, action
        # Pricing: exactly one of yes_price | no_price | yes_price_dollars | no_price_dollars
        # Sending price implies LIMIT order — explicit `type` field is no longer
        # recognized by Kalshi's API.
        #
        # Bug history:
        #  2026-05-17: sent BOTH yes_price + no_price → 400 invalid_order (fixed)
        #  2026-05-18 06:00 first live morning: 4 of 5 orders rejected with
        #    "invalid_parameters" — all 4 were B-strike (between) markets,
        #    the one that succeeded was T-strike (greater than). Common factor:
        #    the deprecated `"type": "limit"` field. T-markets ignored it,
        #    B-markets strictly rejected it. Removed the field; per docs an
        #    order with a price field IS a limit order by default. Adding
        #    explicit time_in_force=good_till_canceled to match prior
        #    "limit" semantics (rest on book until filled or cancelled).
        body = {
            "ticker":          ticker,
            "action":          "buy",
            "side":            side,
            "count":           contracts,
            "client_order_id": client_order_id,
            "time_in_force":   "good_till_canceled",
        }
        if side == "yes":
            body["yes_price"] = price_cents
        else:
            body["no_price"] = price_cents
        response = self._post("/portfolio/orders", body)
        order    = response.get("order") or response
        # Acceptable post-place statuses. 'canceled' means Kalshi rejected
        # the order at submission — we must NOT record a trade for it. Old
        # logic let canceled-with-order_id through, creating phantom trades.
        accepted = {"resting", "executed", "open", "pending"}
        status   = order.get("status")
        if status == "canceled":
            raise RuntimeError(
                f"Kalshi canceled order at submission (ticker={ticker}): {response}"
            )
        if not order.get("order_id") or status not in accepted:
            raise RuntimeError(
                f"Kalshi rejected order (ticker={ticker}, status={status}): {response}"
            )
        return order

    def get_orders(self, client_order_id: str | None = None,
                   ticker: str | None = None) -> list[dict]:
        """
        Fetch orders from Kalshi. Used to reconcile after network errors where
        place_order raised but the order may have reached the exchange.
        Filters client-side by client_order_id if given.
        """
        if not self._ready:
            return []
        params: dict = {"limit": 100}
        if ticker:
            params["ticker"] = ticker
        try:
            data   = self._get("/portfolio/orders", params=params)
            orders = data.get("orders", [])
            if client_order_id:
                orders = [o for o in orders if o.get("client_order_id") == client_order_id]
            return orders
        except Exception as exc:
            log.warning("get_orders failed: %s", exc)
            return []


# Singleton
_client: KalshiClient | None = None


def get_client() -> KalshiClient:
    global _client
    if _client is None:
        _client = KalshiClient()
        _client.login()
    return _client
