"""
Data loader — fetch MNQ historical bars and return them in the canonical
shape the backtester + strategies expect:
    columns: ['open','high','low','close','volume']  (lowercase)
    index:   tz-aware DatetimeIndex in US/Eastern

Source: yfinance free tier.
  intervals available: 1m (last 7d), 5m/15m/30m/60m (last 60d), 1d (full history)

Usage:
    from forge.data_loader import load_mnq
    df = load_mnq(interval='5m', period='60d')
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

SYMBOL = "MNQ=F"


def load_mnq(interval: str = "5m", period: str = "60d") -> pd.DataFrame:
    raw = yf.download(
        SYMBOL, period=period, interval=interval,
        auto_adjust=False, progress=False, prepost=False,
    )
    if raw.empty:
        raise RuntimeError(f"yfinance returned no data for {SYMBOL} {interval} {period}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    if raw.index.tz is None:
        raw.index = raw.index.tz_localize("UTC")
    raw.index = raw.index.tz_convert("US/Eastern")
    raw = raw.dropna()
    return raw
