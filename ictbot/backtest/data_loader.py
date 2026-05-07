"""Historical bar loader for backtests.

Sources:
1. Yahoo Finance — works out of the box for ES=F (proxy for MES)
2. Local CSV — pass a path; expected columns: time,open,high,low,close,volume
3. Google Drive archive — Phase 2+ (placeholder; uses gdrive MCP at runtime)
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from services.tv_data import Bar, fetch_yf_bars

logger = logging.getLogger(__name__)


def load_yf(symbol: str, interval: str = "5m",
            lookback_minutes: int = 30 * 24 * 60) -> list[Bar]:
    """Fetch up to ~30 days of bars via Yahoo. Yahoo caps 1m lookback at 7d
    and 5m at 60d, but the chart endpoint accepts shorter windows fine.
    """
    return fetch_yf_bars(symbol, interval=interval, lookback_minutes=lookback_minutes)


def load_csv(path: Path, time_format: str = "%Y-%m-%dT%H:%M:%S%z") -> list[Bar]:
    """Load bars from a CSV. Auto-detects ISO timestamps with or without TZ."""
    out: list[Bar] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t_raw = row.get("time") or row.get("timestamp") or ""
            try:
                if t_raw.isdigit():
                    t = datetime.fromtimestamp(int(t_raw), tz=timezone.utc)
                else:
                    try:
                        t = datetime.strptime(t_raw, time_format)
                    except ValueError:
                        # Fallback: ISO without TZ
                        t = datetime.fromisoformat(t_raw)
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
            except Exception as exc:
                logger.warning("skipping bad row %s: %s", row, exc)
                continue
            try:
                out.append(Bar(
                    time=t,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                ))
            except Exception as exc:
                logger.warning("bad ohlc in %s: %s", row, exc)
                continue
    return out


def filter_window(bars: Iterable[Bar], start: datetime, end: datetime) -> list[Bar]:
    """Keep only bars whose open time is within [start, end]."""
    return [b for b in bars if start <= b.time <= end]
