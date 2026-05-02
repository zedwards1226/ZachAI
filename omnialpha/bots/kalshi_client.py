"""Authenticated Kalshi REST client.

Reuses the public puller's base class for /historical/* and adds RSA-PSS
signed requests for /portfolio, /orders, /markets (live state). Pattern
adapted from ryanfrigo/kalshi-ai-trading-bot (MIT) — RSA signing format
matches Kalshi's documented spec.

CRITICAL: This client only PLACES orders. The actual buy/sell decision
is enforced by `bots/order_placer.py` which holds the PAPER_MODE gate.
This separation lets us test the auth/transport layer without ever risking
a live order.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from config import KALSHI_API_BASE, KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH

logger = logging.getLogger(__name__)


class KalshiAuthError(RuntimeError):
    """Raised when credentials are missing or signing fails."""
    pass


class KalshiClient:
    """Authenticated Kalshi REST client.

    Construct once at startup. Methods are sync (we don't need async for
    this bot's volume — at most a few requests per minute).
    """

    def __init__(
        self,
        api_key_id: Optional[str] = None,
        private_key_path: Optional[Path] = None,
        base_url: str = KALSHI_API_BASE,
    ):
        self.api_key_id = api_key_id or KALSHI_API_KEY_ID
        self.private_key_path = private_key_path or KALSHI_PRIVATE_KEY_PATH
        self.base_url = base_url
        self._private_key = None
        self._client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "ZachAI-OmniAlpha/0.1"},
        )

    def _ensure_key_loaded(self) -> None:
        if self._private_key is not None:
            return
        if not self.api_key_id:
            raise KalshiAuthError(
                "KALSHI_API_KEY_ID not set in .env — cannot make authenticated calls"
            )
        if not self.private_key_path:
            raise KalshiAuthError(
                "KALSHI_PRIVATE_KEY_PATH not set in .env"
            )
        if not self.private_key_path.exists():
            raise KalshiAuthError(
                f"Private key file not found: {self.private_key_path}"
            )
        # Lazy import — keeps cryptography off the import path for
        # public-endpoint-only flows (backtests, calibration).
        from cryptography.hazmat.primitives import serialization
        with open(self.private_key_path, "rb") as fh:
            self._private_key = serialization.load_pem_private_key(
                fh.read(), password=None
            )

    def _sign(self, timestamp_ms: str, method: str, path: str) -> str:
        """RSA-PSS sign `timestamp + method + path`. Kalshi's documented format."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        msg = (timestamp_ms + method.upper() + path).encode("utf-8")
        sig = self._private_key.sign(
            msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode("utf-8")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """Send a signed request, return parsed JSON. Raises on non-2xx."""
        self._ensure_key_loaded()
        ts = str(int(time.time() * 1000))
        # Kalshi signs the path including the API version prefix; full path
        # = "/trade-api/v2/<endpoint>". Our base_url is up to v2, so use the
        # path component only when signing.
        sign_path = "/trade-api/v2" + path
        sig = self._sign(ts, method, sign_path)
        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{self.base_url}{path}"
        body = json.dumps(json_body, separators=(",", ":")) if json_body else None
        r = self._client.request(method, url, headers=headers, params=params, content=body)
        r.raise_for_status()
        return r.json()

    # ─── Account / portfolio ───────────────────────────────────────────
    def get_balance(self) -> dict:
        """Returns {balance, available_balance, withdrawable_balance, ...} in cents."""
        return self._request("GET", "/portfolio/balance")

    def get_positions(self) -> dict:
        """All open positions."""
        return self._request("GET", "/portfolio/positions")

    def get_fills(self, *, limit: int = 100) -> dict:
        return self._request("GET", "/portfolio/fills", params={"limit": limit})

    # ─── Markets (live state, not /historical/*) ───────────────────────
    def get_market(self, ticker: str) -> dict:
        """Live market state — current best bid/ask, last price, volume."""
        return self._request("GET", f"/markets/{ticker}")

    def get_event(self, event_ticker: str) -> dict:
        return self._request("GET", f"/events/{event_ticker}")

    # ─── Orders ────────────────────────────────────────────────────────
    def place_order(
        self,
        *,
        ticker: str,
        side: str,           # 'yes' or 'no'
        action: str,         # 'buy' or 'sell'
        count: int,
        price_cents: int,    # limit price
        order_type: str = "limit",
        time_in_force: str = "fill_or_kill",
        client_order_id: Optional[str] = None,
    ) -> dict:
        """Place a limit order. ALWAYS goes through order_placer.py first
        which enforces paper-mode."""
        body = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if order_type == "limit":
            # Kalshi expects yes_price or no_price depending on side
            if side == "yes":
                body["yes_price"] = price_cents
            else:
                body["no_price"] = price_cents
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/portfolio/orders", json_body=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")

    def close(self) -> None:
        self._client.close()
