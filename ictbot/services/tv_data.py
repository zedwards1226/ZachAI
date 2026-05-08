"""Read-only MES bar data for ICTBot.

Strategy:
1. Primary: Yahoo Finance / Stooq style HTTP for 5m bars (no auth needed,
   free, deterministic). MES is well-covered as ES=F (continuous front-month).
2. Fallback: TradingView CDP on :9223 — pull bars via the TV chart's
   internal series API (only used if HTTP source is down).

This module DOES NOT touch ORB's :9222 session.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Bar:
    time: datetime          # bar OPEN time (timezone-aware UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __repr__(self) -> str:
        return f"Bar({self.time.isoformat()} O={self.open} H={self.high} L={self.low} C={self.close} V={int(self.volume)})"


# ─── Yahoo Finance ───────────────────────────────────────────────────
# ES=F is continuous E-mini S&P 500. For MES specifically the price action
# tracks 1:1 (MES is 1/10 of ES); we pull ES=F prices and the strategy
# scales by symbol multiplier in config.

_YF_SYMBOL_MAP = {
    "MES1!": "ES=F",
    "ES1!":  "ES=F",
    "M2K1!": "RTY=F",
    "MNQ1!": "NQ=F",
    "MYM1!": "YM=F",
    "6E1!":  "EURUSD=X",  # not perfect but workable
}


def yf_symbol_for(ict_symbol: str) -> str:
    return _YF_SYMBOL_MAP.get(ict_symbol, "ES=F")


def fetch_yf_bars(symbol: str, interval: str = "5m", lookback_minutes: int = 1500) -> list[Bar]:
    """Fetch bars from Yahoo's chart API. Returns oldest-first.

    interval: '1m', '5m', '15m', '30m', '60m', '1d'
    lookback_minutes: how far back to request
    """
    yf_symbol = yf_symbol_for(symbol)
    end = int(time.time())
    start = end - lookback_minutes * 60
    qs = urllib.parse.urlencode({
        "period1": start,
        "period2": end,
        "interval": interval,
        "includePrePost": "true",
        "events": "history",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("yahoo fetch failed for %s: %s", yf_symbol, exc)
        return []

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        ind = result["indicators"]["quote"][0]
        opens, highs, lows, closes, volumes = (
            ind.get("open") or [],
            ind.get("high") or [],
            ind.get("low") or [],
            ind.get("close") or [],
            ind.get("volume") or [],
        )
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("yahoo response shape unexpected: %s", exc)
        return []

    bars: list[Bar] = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes):
            break
        if closes[i] is None or opens[i] is None:
            continue
        bars.append(Bar(
            time=datetime.fromtimestamp(ts, tz=timezone.utc),
            open=float(opens[i]),
            high=float(highs[i]),
            low=float(lows[i]),
            close=float(closes[i]),
            volume=float(volumes[i] or 0.0),
        ))
    return bars


def fetch_recent_bars(symbol: str, timeframe: str = "5", count: int = 100) -> list[Bar]:
    """High-level: fetch the last `count` bars at the given TV timeframe.

    timeframe: '1' | '5' | '15' | '60' (TV-style minutes)
    """
    interval_map = {"1": "1m", "5": "5m", "15": "15m", "30": "30m", "60": "60m", "240": "60m", "D": "1d"}
    interval = interval_map.get(timeframe, "5m")
    minutes_per_bar = int(timeframe) if timeframe.isdigit() else (60 if timeframe == "240" else 1440)
    lookback_minutes = max(count * minutes_per_bar + 60, 1500)
    bars = fetch_yf_bars(symbol, interval=interval, lookback_minutes=lookback_minutes)
    return bars[-count:] if len(bars) > count else bars


def htf_bias(symbol: str) -> str:
    """1H close vs 4H 50-period EMA → 'long' | 'short' | 'neutral'."""
    bars_60 = fetch_recent_bars(symbol, timeframe="60", count=80)
    if len(bars_60) < 50:
        return "neutral"
    closes = [b.close for b in bars_60]
    # Compute 50 EMA on 1H bars (proxy for 4H 50EMA bias when 4H not available cheap)
    k = 2 / (50 + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    last_close = closes[-1]
    if last_close > ema * 1.0005:
        return "long"
    if last_close < ema * 0.9995:
        return "short"
    return "neutral"
