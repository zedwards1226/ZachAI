"""
Pydantic models for TradingAgents.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Verdict(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    REDUCE = "REDUCE"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Signal(BaseModel):
    """Incoming webhook signal from TradingView."""
    action: str                        # buy, sell, close
    symbol: str = "MNQ1!"
    price: float = 0.0
    qty: int = 1
    order_id: str = ""
    position_size: Optional[float] = None
    strategy: str = "NQ ORB 15m"
    raw_body: str = ""                 # original webhook payload


class AgentVerdict(BaseModel):
    """Result from any agent evaluation."""
    agent: str                         # overseer, sentinel, sweep, context, monitor, analyst
    verdict: Verdict
    reasoning: str
    tokens_used: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Trade(BaseModel):
    """Active or closed trade."""
    id: Optional[int] = None
    symbol: str
    side: Side
    entry: float
    qty: int = 1
    strategy: str = "NQ ORB 15m"
    order_id: str = ""
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exit: Optional[float] = None
    closed_at: Optional[datetime] = None
    pnl: Optional[float] = None
    pts: Optional[float] = None
    multiplier: float = 2.0


class Decision(BaseModel):
    """Logged decision from an agent for a given signal."""
    id: Optional[int] = None
    trade_id: Optional[int] = None
    signal_id: Optional[int] = None
    agent: str
    verdict: Verdict
    reasoning: str
    tokens_used: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
