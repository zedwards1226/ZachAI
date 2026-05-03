"""Crypto Mid-Band Strategy for KXBTC15M binary up/down markets.

Edge thesis — measured against 7,183 settled markets (2026-02-23 to 2026-03-02).
Tightened after Wilson 95%-CI sample-size review:

Only the two bands with adequate sample size are traded:
  yes_price 0.20-0.30 (n=88, actual ~12.4%)  → bet NO
  yes_price 0.75-0.85 (n=94, actual ~96.5%)  → bet YES

Bands DROPPED from the previous version:
  0.30-0.40 (n=27): Wilson upper bound on actual rate ~30% — could mean
                     zero or negative edge. Too thin.
  0.70-0.75 (n=14): Wilson lower bound 60% — could be -edge. Too thin.

Sizing:
  - 0.05 fractional Kelly (was 0.10 — domain review flagged the 0.10
    default as over-fit to one BTC regime). 0.05 still extracts edge,
    survives shocks better.
  - Capped at PER_TRADE_MAX_RISK_USD via the risk engine.

Entry timing:
  - Only enter when 0 < seconds_to_close <= MAX_SECONDS_TO_CLOSE_FOR_ENTRY
    (3 minutes). The calibration was measured on closing prices, so we
    only enter where the price distribution matches.
"""
from __future__ import annotations

import logging
from typing import Optional

from strategies.base import (
    EntryDecision, ExitDecision, MarketSnapshot, Strategy, StrategyContext,
)

logger = logging.getLogger(__name__)


# Edge bands — tightened per backtest variance analysis.
# Only trade where calibration evidence is strongest AND sample sizes
# justify confidence. Mid-mid-band (45-65c) is excluded — too few markets,
# too much noise per the calibration table.
#
# Format: (low_yes_price, high_yes_price, our_forecast_of_true_yes_rate)
# Our forecast is INTENTIONALLY conservative — set to the worst observed
# bin in that range, not the average. Better to under-claim edge than
# over-bet.
NO_BANDS: list[tuple[float, float, float]] = [
    (0.20, 0.30, 0.15),   # n=88, actual 12.4%; conservative forecast 15%
]
YES_BANDS: list[tuple[float, float, float]] = [
    (0.75, 0.85, 0.90),   # n=94, actual 96.5%; conservative forecast 90%
]

# Don't trade until at least this much volume has flowed — thin markets
# have wider spreads and the calibration may not apply.
MIN_VOLUME_FP: float = 1000.0

# Don't enter within N seconds of close — not enough time to manage exit
# AND the spread typically widens in the last few seconds.
MIN_SECONDS_TO_CLOSE: int = 30

# Only enter in the FINAL stretch of the market's life. Calibration was
# measured at closing prices — entering 10 min before close applies the
# model to the wrong distribution.
MAX_SECONDS_TO_CLOSE_FOR_ENTRY: int = 180


class CryptoMidBandStrategy(Strategy):
    """Generic mid-band strategy for binary YES/NO markets where Kalshi
    miscalibrates a price range. Used for KXBTC15M, KXETH15M, KXBTCD —
    each instance gets its own bands tuned to that series's calibration.

    Construct one instance per series. Series-specific tuning in
    main.py's _STRATEGY_REGISTRY.
    """

    name = "crypto_midband"
    sector = "crypto"

    def __init__(
        self,
        kelly_fraction: float = 0.05,
        *,
        name: str | None = None,
        no_bands: list[tuple[float, float, float]] | None = None,
        yes_bands: list[tuple[float, float, float]] | None = None,
        min_volume_fp: float | None = None,
        max_seconds_to_close: int | None = None,
        min_seconds_to_close: int | None = None,
    ):
        # 0.05 = 1/20-Kelly. Validated as the variance/return sweet
        # spot for crypto mid-band. P&L scales linearly with Kelly;
        # risk does not.
        self.kelly_fraction = kelly_fraction
        if name is not None:
            self.name = name
        # Bands default to BTC15M tuning (the original calibration).
        # Override per-series when constructing.
        self._no_bands = no_bands if no_bands is not None else NO_BANDS
        self._yes_bands = yes_bands if yes_bands is not None else YES_BANDS
        self._min_volume_fp = (
            min_volume_fp if min_volume_fp is not None else MIN_VOLUME_FP
        )
        self._max_seconds_to_close = (
            max_seconds_to_close
            if max_seconds_to_close is not None
            else MAX_SECONDS_TO_CLOSE_FOR_ENTRY
        )
        self._min_seconds_to_close = (
            min_seconds_to_close
            if min_seconds_to_close is not None
            else MIN_SECONDS_TO_CLOSE
        )

    def decide_entry(
        self,
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[EntryDecision]:
        # Sector gate
        if market.sector != "crypto":
            return None

        # Liquidity / freshness gates
        if market.volume_fp < self._min_volume_fp:
            return None
        if market.seconds_to_close <= 0:
            return None
        if market.seconds_to_close > self._max_seconds_to_close:
            return None
        if market.seconds_to_close < self._min_seconds_to_close:
            return None

        yes_price = market.last_price_cents / 100.0
        if yes_price <= 0 or yes_price >= 1:
            return None  # un-traded or already settled

        # Find the band
        decision = self._classify_band(yes_price)
        if decision is None:
            return None
        side, true_yes_rate = decision

        # Convert to "our forecast probability of THIS bet winning"
        forecast_p_win = true_yes_rate if side == "yes" else (1.0 - true_yes_rate)

        # Compute Kelly stake.
        # Kalshi binary: pay p, win 1, lose 0. b = (1-p)/p, q = 1-forecast_p_win
        # f* = (b * forecast_p_win - q) / b
        # We use the side's price (yes_ask if YES, no_ask if NO) as `p`.
        if side == "yes":
            entry_price_cents = market.yes_ask_cents
        else:
            entry_price_cents = market.no_ask_cents
        if entry_price_cents <= 0 or entry_price_cents >= 100:
            return None
        p = entry_price_cents / 100.0
        b = (1 - p) / p
        q = 1.0 - forecast_p_win
        full_kelly = (b * forecast_p_win - q) / b
        if full_kelly <= 0:
            return None  # no edge after fees/spread; skip

        kelly_frac = full_kelly * self.kelly_fraction

        # Convert Kelly fraction → stake → contract count.
        # Stake_usd = kelly_frac * capital, but capped by risk engine downstream.
        # Strategy provides desired contract count; risk engine may shrink it.
        stake_usd = min(kelly_frac * context.capital_usd, context.capital_usd)
        if stake_usd <= 0.10:
            return None
        contracts = max(1, int(stake_usd * 100 / entry_price_cents))

        edge = forecast_p_win - p
        return EntryDecision(
            side=side,
            contracts=contracts,
            price_cents=entry_price_cents,
            edge=edge,
            forecast_prob=forecast_p_win,
            kelly_frac=full_kelly,
            reason=f"midband_{side}_{int(p*100)}c",
            extras={
                "true_yes_rate": true_yes_rate,
                "yes_market_price": yes_price,
                "kelly_applied": self.kelly_fraction,
            },
        )

    def decide_exit(
        self,
        position: dict,
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[ExitDecision]:
        """No active exit logic — KXBTC15M is 15-min binary. Hold to settlement.
        Trade monitor handles the resolution write to journal."""
        return None

    def _classify_band(self, yes_price: float) -> Optional[tuple[str, float]]:
        """Map a YES price to (side_to_take, our_forecast_of_true_yes_rate)."""
        for low, high, true_rate in self._no_bands:
            if low <= yes_price < high:
                return ("no", true_rate)
        for low, high, true_rate in self._yes_bands:
            if low <= yes_price < high:
                return ("yes", true_rate)
        return None
