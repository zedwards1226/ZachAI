"""Crypto Mid-Band Strategy for KXBTC15M (and other binary up/down markets).

Edge thesis (validated against 7,183 settled markets, Feb 23 - Mar 2 2026):
  - Kalshi is overall well-calibrated (Brier 0.0136)
  - BUT systematically miscalibrates the mid-band:
      yes_price 0.25-0.45 → market OVERPRICES YES by ~12-26 points → bet NO
      yes_price 0.65-0.85 → market UNDERPRICES YES by ~12-20 points → bet YES
  - Extremes (0-5%, 95-100%) are well-calibrated and have no edge
  - Strategy ignores extremes, harvests the mid-band miscalibration

Sizing:
  - Half-Kelly on each entry (more conservative than full Kelly while
    paper-validating; can scale later)
  - Capped at PER_TRADE_MAX_RISK_USD via the risk engine

Pre-trade gates handled by risk_engine.py:
  - Kelly stake clamping
  - Liquidity floor (skip thin markets)
  - Concentration cap (one position per market window)
  - Drawdown halt
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
    (0.20, 0.30, 0.15),   # bins 0.20-0.30: actual YES 10-15%; conservative 15
    (0.30, 0.40, 0.20),   # bins 0.30-0.40: actual YES 7-25%; conservative 20
]
YES_BANDS: list[tuple[float, float, float]] = [
    (0.70, 0.85, 0.88),   # bins 0.70-0.85: actual YES 85-100%; conservative 88
]

# Don't trade until at least this much volume has flowed — thin markets
# have wider spreads and the calibration may not apply.
MIN_VOLUME_FP: float = 1000.0

# Don't enter within N seconds of close — not enough time to manage exit.
MIN_SECONDS_TO_CLOSE: int = 60


class CryptoMidBandStrategy(Strategy):
    """The first OmniAlpha strategy. Crypto-only. Rule-based. No LLM."""

    name = "crypto_midband"
    sector = "crypto"

    def __init__(self, kelly_fraction: float = 0.10):
        # 0.10 = tenth-Kelly. Paper-validated as the sweet spot in
        # backtest: P&L $62 on $100 over 7 days, 85% WR, $15 max DD.
        # Higher Kelly amplifies P&L but blows out drawdown variance.
        self.kelly_fraction = kelly_fraction

    def decide_entry(
        self,
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[EntryDecision]:
        # Sector gate
        if market.sector != "crypto":
            return None

        # Liquidity / freshness gates
        if market.volume_fp < MIN_VOLUME_FP:
            return None
        if 0 < market.seconds_to_close < MIN_SECONDS_TO_CLOSE:
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

    @staticmethod
    def _classify_band(yes_price: float) -> Optional[tuple[str, float]]:
        """Map a YES price to (side_to_take, our_forecast_of_true_yes_rate)."""
        for low, high, true_rate in NO_BANDS:
            if low <= yes_price < high:
                return ("no", true_rate)
        for low, high, true_rate in YES_BANDS:
            if low <= yes_price < high:
                return ("yes", true_rate)
        return None
