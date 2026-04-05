"""
Kalshi API client — supports both demo and live.
Paper mode: all orders are logged but never sent to Kalshi.
"""
import logging
import requests
from datetime import date
from config import (
    KALSHI_BASE, KALSHI_EMAIL, KALSHI_PASSWORD,
    KALSHI_DEMO, PAPER_MODE, CITIES
)

log = logging.getLogger(__name__)

# KXHIGH markets follow the pattern: KXHIGH-{TAG}-{YYYYMMDD}-T{STRIKE}
# e.g. KXHIGH-NY-20240601-T75  (will high exceed 75°F today?)


class KalshiClient:
    def __init__(self):
        self.session = requests.Session()
        self.token: str | None = None
        self._logged_in = False

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        if not KALSHI_EMAIL or not KALSHI_PASSWORD:
            log.warning("Kalshi credentials not set — running unauthenticated (public only)")
            return False
        try:
            resp = self.session.post(
                f"{KALSHI_BASE}/login",
                json={"email": KALSHI_EMAIL, "password": KALSHI_PASSWORD},
                timeout=10,
            )
            resp.raise_for_status()
            self.token = resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            self._logged_in = True
            log.info("Kalshi login OK (demo=%s)", KALSHI_DEMO)
            return True
        except Exception as exc:
            log.error("Kalshi login failed: %s", exc)
            return False

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(f"{KALSHI_BASE}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = self.session.post(f"{KALSHI_BASE}{path}", json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── Market discovery ──────────────────────────────────────────────────────

    def get_market(self, ticker: str) -> dict | None:
        """Fetch a single market by ticker. Returns None if not found."""
        try:
            data = self._get(f"/markets/{ticker}")
            return data.get("market")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def search_kxhigh_markets(self, city_code: str, target_date: str | None = None) -> list[dict]:
        """
        Search for KXHIGH markets for a city on a given date (YYYY-MM-DD).
        Returns list of market dicts sorted by strike ascending.
        """
        tag  = CITIES[city_code]["kalshi_tag"]
        dt   = (target_date or date.today().isoformat()).replace("-", "")
        prefix = f"KXHIGH-{tag}-{dt}"
        try:
            data = self._get("/markets", params={"series_ticker": f"KXHIGH-{tag}", "limit": 100})
            markets = data.get("markets", [])
            # Filter to today's date
            filtered = [m for m in markets if m.get("ticker", "").startswith(prefix)]
            filtered.sort(key=lambda m: m.get("ticker", ""))
            return filtered
        except Exception as exc:
            log.warning("Market search failed for %s: %s", city_code, exc)
            return []

    def get_orderbook(self, ticker: str) -> dict | None:
        """Return best YES/NO prices from the orderbook."""
        try:
            data = self._get(f"/markets/{ticker}/orderbook")
            book = data.get("orderbook", {})
            yes_levels = book.get("yes", [])
            no_levels  = book.get("no", [])
            best_yes = yes_levels[0][0] if yes_levels else None
            best_no  = no_levels[0][0]  if no_levels  else None
            return {"yes": best_yes, "no": best_no, "ticker": ticker}
        except Exception:
            return None

    # ── Account ───────────────────────────────────────────────────────────────

    def get_balance(self) -> float:
        """Return available balance in USD."""
        if not self._logged_in:
            return 0.0
        try:
            data = self._get("/portfolio/balance")
            cents = data.get("balance", 0)
            return cents / 100
        except Exception:
            return 0.0

    def get_positions(self) -> list[dict]:
        if not self._logged_in:
            return []
        try:
            data = self._get("/portfolio/positions")
            return data.get("market_positions", [])
        except Exception:
            return []

    # ── Order placement ───────────────────────────────────────────────────────

    def place_order(self, ticker: str, side: str, contracts: int,
                    price_cents: int, client_order_id: str = "") -> dict:
        """
        Place a limit order.
        side: "yes" or "no"
        price_cents: 1-99
        Returns order dict or raises.
        In PAPER_MODE, logs and returns a fake order dict.
        """
        if PAPER_MODE:
            log.info(
                "[PAPER] ORDER: %s %s x%d @ %d¢",
                ticker, side.upper(), contracts, price_cents
            )
            return {
                "order_id":   f"PAPER-{ticker}-{side}-{contracts}",
                "ticker":     ticker,
                "side":       side,
                "contracts":  contracts,
                "price":      price_cents,
                "status":     "paper_filled",
                "paper":      True,
            }

        if not self._logged_in:
            raise RuntimeError("Not logged in to Kalshi")

        body = {
            "ticker":           ticker,
            "action":           "buy",
            "side":             side,
            "type":             "limit",
            "count":            contracts,
            "yes_price":        price_cents if side == "yes" else 100 - price_cents,
            "no_price":         price_cents if side == "no"  else 100 - price_cents,
            "client_order_id":  client_order_id,
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
