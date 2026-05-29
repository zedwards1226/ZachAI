"""Longshot-Fade NO Maker Strategy — sports edition.

Trade thesis (Becker 2026, Whelan 2026, validated 2026-05-27 on Zach's data):

Retail systematically OVERPRICES longshot YES contracts on retail-heavy
sport markets — the $0.05 → $1.00 lottery-ticket dynamic. The mirror is
NO at 85-99¢: structurally UNDERPRICED relative to actual settle rate.
A maker sitting on the NO bid 1¢ inside the lowest ask collects the
spread when impulsive YES takers cross.

PHASE 1 VALIDATION (873k trades, sandbox/longshot_fade_validation_2026-05-27):
                  IMPLIED   ACTUAL   EDGE
  NO 85-89¢       87%       90.3%    +3.3pp
  NO 90-94¢       92%       94.9%    +2.9pp
  NO 95-99¢       97%       98.3%    +1.3pp

PER-SERIES VERDICT:
  KXNFLGAME — STRONGEST (+6.1 / +4.6 / +1.9pp). NFL off-season props.
  KXNBAGAME — clean Becker fade  (+0.9 / +3.0 / +1.7pp).
  KXEPLGAME — NEGATIVE EDGE (-8.4 / -7.1 / -2.3pp). Soccer's high draw rate
              inverts the longshot pattern. **BLOCKED at code level.**

Strategy mechanics:
  1. Universe filter: sector == "sports" AND series in the 9-sport allowlist
     (NBA/NFL Phase-1 validated; MLB/NHL/WNBA/UFC/ATP/WTA/boxing paper-mode
     experimental; all soccer leagues blocked).
  2. Price gate: no_ask_cents in [85, 99].
  3. Liquidity gate: volume_fp >= 1000.
  4. Time gate: seconds_to_close in [1800, 14400]  (30min - 4hr).
     - Lower bound: enough time for a maker order to actually fill before close.
     - Upper bound: avoid early-game prices that haven't converged to the
       longshot band via game-state attrition.
  5. Forecast probability: per-bucket actual rate from Phase 1, shrunk 1pp
     toward implied to leave a margin for 2026-Q2 institutional MM
     compression (data was 60 days stale at validation time).
  6. EV gate: ≥ 1¢ expected value per $1 risked AFTER 7% Kalshi fee on
     winnings.
  7. Kelly sizing: 0.10 fraction (bumped from 0.05 on 2026-05-28). Hard $30/trade cap.
  8. Order: post NO bid at `no_ask_cents - 1` (maker, near-zero fees).

Per-position rule: max 8 concurrent (enforced by risk engine, not here).
"""
from __future__ import annotations

import math
import logging
from typing import Optional

from strategies.base import (
    EntryDecision, ExitDecision, MarketSnapshot, Strategy, StrategyContext,
)

logger = logging.getLogger(__name__)


# ─── Universe filter ────────────────────────────────────────────────────
# Whitelist of series we'll trade. Phase 1 validated NBA + NFL only.
# Everything else is unvalidated paper-mode experimentation — the per-bucket
# forecasts (89.3%/93.9%/97.3%) come from NBA and may not transfer cleanly
# to other sport dynamics. Watch per-series PnL in the dashboard; if any
# series drifts negative over 30+ trades, drop it from this list.
#
# 2026-05-27: expanded from {NBA, NFL} to the full live-Kalshi sport
# universe (excluding soccer — Phase 1 showed EPL has structural -8pp edge
# from soccer's high draw rate; all soccer leagues blocked below).
ALLOWED_SERIES_PREFIXES: tuple[str, ...] = (
    "KXNBA",      # Phase 1 validated ✓
    "KXNFL",      # Phase 1 validated ✓
    "KXMLB",      # peak season — NOT validated
    "KXNHL",      # Stanley Cup playoffs — NOT validated
    "KXWNBA",     # season starting — NOT validated
    "KXUFC",      # weekly fights — NOT validated
    "KXATP",      # men's tennis (French Open active) — NOT validated
    "KXWTA",      # women's tennis (French Open active) — NOT validated
    "KXBOXING",   # active card schedule — NOT validated
    # KXF1 removed 2026-05-27 — F1 markets are season-championship futures,
    # not head-to-head binaries. The longshot-fade thesis (fade a favorite
    # mid-game) doesn't apply to "who wins the championship" markets.
)

# Explicit deny list. Soccer leagues are blocked because the long-tail draw
# rate inverts the longshot pattern (Phase 1: EPL -8.4pp at 85-89¢).
BLOCKED_SERIES_PREFIXES: tuple[str, ...] = (
    "KXEPL",         # English Premier League
    "KXUCL",         # UEFA Champions League
    "KXLALIGA",      # Spanish La Liga
    "KXSERIE",       # Italian Serie A
    "KXBUNDES",      # German Bundesliga
    "KXLIGUE1",      # French Ligue 1
    "KXMLS",         # MLS (US soccer)
    "KXALEAGUE",     # Australian A-League
    "KXALLSVENSKAN", # Swedish Allsvenskan
)


# ─── Per-bucket calibration ─────────────────────────────────────────────
# Phase 1 measured actual NO-win rate per bucket. We shrink each rate 1pp
# toward the implied price to leave room for 2026-Q2 MM-compression slippage
# vs the 60-day-stale validation data. Edges remain positive; risk is honest.
#
# Format: (no_price_low, no_price_high, forecast_no_win_prob)
CALIBRATED_BUCKETS: tuple[tuple[int, int, float], ...] = (
    (85, 89, 0.893),   # measured 90.3% → shrink to 89.3%
    (90, 94, 0.939),   # measured 94.9% → shrink to 93.9%
    (95, 99, 0.973),   # measured 98.3% → shrink to 97.3%
)


# ─── Risk + sizing knobs ────────────────────────────────────────────────
MIN_VOLUME_FP: float = 1000.0          # liquidity gate
MIN_SECONDS_TO_CLOSE: int = 1800       # 30 min — maker fill takes time
MAX_SECONDS_TO_CLOSE: int = 14400      # 4 hr — game already in convergence
# Kelly fraction bumped 0.05 → 0.10 on 2026-05-28 (Zach: trades were only
# making cents). 2× bigger stakes → 2× bigger wins AND losses. Still clamped
# by the risk-engine per-trade $ cap ($24 @ $300 capital) and the strategy
# hard cap below. Reconsider if drawdown gets uncomfortable in paper.
DEFAULT_KELLY_FRACTION: float = 0.10
PER_TRADE_HARD_CAP_USD: float = 30.0
MIN_EV_PER_DOLLAR: float = 0.01        # 1¢ EV per $1 risked AFTER fees

# Kalshi fee on winnings — 7% per published 2026 retail schedule.
KALSHI_FEE_RATE: float = 0.07


class LongshotFadeStrategy(Strategy):
    """Sport-market NO-maker for the 85-99¢ longshot fade.

    All knobs are constructor-injected so tests + paper-mode tuning can
    override without editing the class. Production wiring uses the defaults
    above.
    """

    name = "longshot_fade"
    sector = "sports"

    def __init__(
        self,
        *,
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
        per_trade_hard_cap_usd: float = PER_TRADE_HARD_CAP_USD,
        min_ev_per_dollar: float = MIN_EV_PER_DOLLAR,
        min_volume_fp: float = MIN_VOLUME_FP,
        min_seconds_to_close: int = MIN_SECONDS_TO_CLOSE,
        max_seconds_to_close: int = MAX_SECONDS_TO_CLOSE,
        allowed_series_prefixes: tuple[str, ...] = ALLOWED_SERIES_PREFIXES,
        blocked_series_prefixes: tuple[str, ...] = BLOCKED_SERIES_PREFIXES,
        buckets: tuple[tuple[int, int, float], ...] = CALIBRATED_BUCKETS,
    ):
        self.kelly_fraction = kelly_fraction
        self.per_trade_hard_cap_usd = per_trade_hard_cap_usd
        self.min_ev_per_dollar = min_ev_per_dollar
        self.min_volume_fp = min_volume_fp
        self.min_seconds_to_close = min_seconds_to_close
        self.max_seconds_to_close = max_seconds_to_close
        self.allowed_series_prefixes = tuple(p.upper() for p in allowed_series_prefixes)
        self.blocked_series_prefixes = tuple(p.upper() for p in blocked_series_prefixes)
        self.buckets = buckets

    # ─── Filters ────────────────────────────────────────────────────────

    def _series_allowed(self, ticker: str) -> bool:
        """True iff ticker is in our whitelist AND not in our blocklist."""
        if not ticker:
            return False
        upper = ticker.upper()
        if any(upper.startswith(p) for p in self.blocked_series_prefixes):
            return False
        return any(upper.startswith(p) for p in self.allowed_series_prefixes)

    def _bucket_for(self, no_ask_cents: int) -> Optional[tuple[int, int, float]]:
        """Return (low, high, forecast_no_win_prob) for the band the ask is in."""
        for low, high, forecast in self.buckets:
            if low <= no_ask_cents <= high:
                return (low, high, forecast)
        return None

    # ─── Decision ───────────────────────────────────────────────────────

    def decide_entry(
        self,
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[EntryDecision]:
        # Sector gate (the runner sets `sector` from ticker prefix).
        if market.sector != "sports":
            return None

        # Series allowlist (9 sport series; soccer leagues blocked).
        if not self._series_allowed(market.ticker):
            return None

        # Liquidity gate.
        if market.volume_fp < self.min_volume_fp:
            return None

        # Time gates — need enough time for a maker fill but not so far out
        # that the longshot price reflects pre-game uncertainty rather than
        # game-state attrition.
        if market.seconds_to_close <= 0:
            return None
        if market.seconds_to_close < self.min_seconds_to_close:
            return None
        if market.seconds_to_close > self.max_seconds_to_close:
            return None

        # Price gate.
        if market.no_ask_cents <= 0 or market.no_ask_cents >= 100:
            return None
        bucket = self._bucket_for(market.no_ask_cents)
        if bucket is None:
            return None
        low, high, forecast_no_win = bucket

        # We're posting a maker bid 1c inside the ask. Our fill price is
        # one cent below the displayed ask.
        entry_price_cents = market.no_ask_cents - 1
        if entry_price_cents < low:
            # Can't post inside without leaving the bucket — skip.
            return None

        # Edge math:
        #   forecast_p_win   = our estimate of NO winning at this price
        #   p                = our entry price as a probability
        #   payout_on_win    = (100 - p) cents per contract gross
        #   fee_on_win       = 7% of payout_on_win
        #   net_payout       = payout * (1 - fee)
        #   EV_per_dollar    = forecast_p_win * (net_payout / p)  -  (1 - forecast_p_win)
        p = entry_price_cents / 100.0
        gross_payout_per_dollar = (1.0 - p) / p
        net_payout_per_dollar = gross_payout_per_dollar * (1.0 - KALSHI_FEE_RATE)
        ev_per_dollar = forecast_no_win * net_payout_per_dollar - (1.0 - forecast_no_win)

        if ev_per_dollar < self.min_ev_per_dollar:
            return None

        # Fractional Kelly sizing. f* = (b * p_win - q) / b where b is
        # net-of-fees per-dollar payout. Then scale by self.kelly_fraction.
        b = net_payout_per_dollar
        full_kelly = (b * forecast_no_win - (1.0 - forecast_no_win)) / b
        if full_kelly <= 0:
            return None  # shouldn't reach here after EV gate, but defensive
        kelly_stake_usd = min(
            full_kelly * self.kelly_fraction * context.capital_usd,
            self.per_trade_hard_cap_usd,
        )
        if kelly_stake_usd < 0.50:
            return None  # below dust threshold

        contracts = max(1, int(math.floor(kelly_stake_usd * 100 / entry_price_cents)))

        edge = forecast_no_win - p  # signed; positive means NO is mispriced cheap
        return EntryDecision(
            side="no",
            contracts=contracts,
            price_cents=entry_price_cents,
            edge=edge,
            forecast_prob=forecast_no_win,
            kelly_frac=full_kelly,
            reason=f"longshot_fade_no_{entry_price_cents}c",
            extras={
                "bucket_low": low,
                "bucket_high": high,
                "bucket_forecast": forecast_no_win,
                "ev_per_dollar_after_fee": round(ev_per_dollar, 4),
                "kelly_applied": self.kelly_fraction,
                "kalshi_fee_rate": KALSHI_FEE_RATE,
            },
        )

    def decide_exit(
        self,
        position: dict,
        market: MarketSnapshot,
        context: StrategyContext,
    ) -> Optional[ExitDecision]:
        """Hold to settlement. Sport markets self-settle on the same trade
        day; we collect the spread by being patient. trade_monitor handles
        the settlement write to journal.
        """
        return None
