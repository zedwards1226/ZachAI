"""Pydantic data models for ORB Multi-Agent Trading System."""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Bias(str, Enum):
    BULLISH_BIAS = "BULLISH_BIAS"
    BEARISH_BIAS = "BEARISH_BIAS"
    NEUTRAL = "NEUTRAL"


class PriceLocation(str, Enum):
    OPEN_AIR = "OPEN_AIR"
    APPROACHING_WALL = "APPROACHING_WALL"
    AT_LEVEL = "AT_LEVEL"


class SweepType(str, Enum):
    SWEEP_CONFIRMED = "SWEEP_CONFIRMED"
    GENUINE_BREAK = "GENUINE_BREAK"


class TradeSize(str, Enum):
    FULL = "FULL"
    HALF = "HALF"
    SKIP = "SKIP"


class Outcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    SCRATCH = "SCRATCH"
    OPEN = "OPEN"


class DayType(str, Enum):
    TREND = "TREND"
    CHOP = "CHOP"


class CandleDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


# --- Data Models ---

class Bar(BaseModel):
    time: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class Quote(BaseModel):
    symbol: str
    time: float = 0
    open: float = 0
    high: float = 0
    low: float = 0
    close: float = 0
    last: float = 0
    volume: float = 0


class Level(BaseModel):
    name: str
    price: float
    distance_pts: float = 0


class ORBRange(BaseModel):
    high: float
    low: float
    range: float
    candle_direction: CandleDirection
    captured_at: str


class ScoreBreakdown(BaseModel):
    orb_candle_direction: int = 0
    htf_bias: int = 0
    second_break: int = 0
    sweep_opposite: int = 0
    open_air: int = 0
    rvol: int = 0
    vwap_alignment: int = 0
    vix_regime: int = 0
    prior_day_direction: int = 0
    no_news_block: int = 0
    no_truth_block: int = 0
    approaching_wall: int = 0
    bias_conflict: int = 0
    sweep_trap: int = 0
    news_block: int = 0
    truth_block: int = 0
    at_level: int = 0
    total: int = 0
    details: dict = Field(default_factory=dict)

    def compute_total(self) -> int:
        self.total = (
            self.orb_candle_direction + self.htf_bias + self.second_break
            + self.sweep_opposite + self.open_air + self.rvol
            + self.vwap_alignment + self.vix_regime + self.prior_day_direction
            + self.no_news_block + self.no_truth_block
            + self.approaching_wall + self.bias_conflict + self.sweep_trap
            + self.news_block + self.truth_block + self.at_level
        )
        return self.total


class Signal(BaseModel):
    time: str
    direction: Direction
    breakout_price: float
    score: int
    size: TradeSize
    breakdown: ScoreBreakdown
    entry: float
    stop: float
    target_1: float
    target_2: float
    risk_reward: float
    orb: ORBRange
    was_second_break: bool = False
    vix_at_entry: Optional[float] = None
    rvol_at_entry: Optional[float] = None
    status: str = "OPEN"


class DayAnalysis(BaseModel):
    date: str
    day_type: DayType
    direction: CandleDirection
    range_pts: float
    body_pct: float
    high: float
    low: float
    close: float


class SweepLevel(BaseModel):
    level: float
    level_type: str  # "high" or "low"
    swept_date: str
    direction: str


class FVG(BaseModel):
    fvg_type: str  # "bullish" or "bearish"
    high: float
    low: float
    date: str


class LiquidityPool(BaseModel):
    pool_type: str  # "equal_highs" or "equal_lows"
    level: float
    bar_count: int
    first_seen: str


class SweepEvent(BaseModel):
    time: str
    sweep_type: SweepType
    direction: str  # "BULLISH" or "BEARISH"
    level: float
    pool_type: str
    wick_size: float = 0
    reversal_candles: int = 0
