"""Tests for read_recent_exit_fill — booking REAL exit fills from TV order
history instead of guessing (2026-05-22 fix).

Background: the monitor detects closes by sampling the quote every 30s and
books the THEORETICAL level (stop/T2). A fast wick through TP/SL between samples
is missed, and the reconcile loop then *guesses* the exit (the 2026-05-21
trade #34 case: TP filled at 29472.50 on a wick, bot booked +$350 by assuming).
read_recent_exit_fill reads the actual Filled exit row from the account-manager
Order history so the bot books what really happened.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import tv_trader  # noqa: E402


def _tv_with_history(payload):
    """Fake TV client whose evaluate_async() returns the order-history payload."""
    tv = MagicMock()

    async def fake_evaluate_async(js, *a, **kw):
        return payload

    tv.evaluate_async = fake_evaluate_async
    return tv


# Real row shape from TV: side / type / fill / closingTime / orderId
def _row(side, typ, fill, closing, oid="1"):
    return {"side": side, "type": typ, "fill": fill,
            "closingTime": closing, "orderId": oid}


def test_long_take_profit_fill():
    """LONG closes with a Sell; TP fill is read at the real price (not T2 level)."""
    tv = _tv_with_history({"panel": True, "rows": [
        _row("Buy", "Market", "29,300.75", "2026-05-21 10:50:11", "1"),     # entry, excluded
        _row("Sell", "Take Profit", "29,472.50", "2026-05-21 12:22:15", "2"),
        _row("Sell", "Stop Loss", "", "2026-05-21 12:22:15", "3"),          # cancelled has no fill
    ]})
    res = asyncio.run(tv_trader.read_recent_exit_fill(
        tv, direction="LONG", opened_after_iso="2026-05-21T10:50:11"))
    assert res is not None
    assert res["exit_price"] == 29472.50
    assert res["kind"] == "TP"
    assert res["order_id"] == "2"


def test_short_stop_loss_fill():
    """SHORT closes with a Buy; real SL fill (29272.00) read, not the level (29268.50)."""
    tv = _tv_with_history({"panel": True, "rows": [
        _row("Sell", "Market", "29,161.00", "2026-05-21 09:25:10", "1"),    # entry, excluded
        _row("Buy", "Stop Loss", "29,272.00", "2026-05-21 10:43:48", "2"),
    ]})
    res = asyncio.run(tv_trader.read_recent_exit_fill(
        tv, direction="SHORT", opened_after_iso="2026-05-21T09:25:10"))
    assert res is not None
    assert res["exit_price"] == 29272.00
    assert res["kind"] == "SL"


def test_picks_most_recent_exit():
    """With multiple exits, the latest by closing time wins."""
    tv = _tv_with_history({"panel": True, "rows": [
        _row("Sell", "Stop Loss", "29,180.00", "2026-05-21 09:55:00", "1"),
        _row("Sell", "Take Profit", "29,472.50", "2026-05-21 12:22:15", "2"),
    ]})
    res = asyncio.run(tv_trader.read_recent_exit_fill(tv, direction="LONG"))
    assert res["exit_price"] == 29472.50
    assert res["kind"] == "TP"


def test_time_filter_excludes_prior_trade_exit():
    """An exit that closed BEFORE this trade opened must be ignored."""
    tv = _tv_with_history({"panel": True, "rows": [
        _row("Sell", "Stop Loss", "29,180.00", "2026-05-21 09:55:00", "1"),  # prior trade
    ]})
    res = asyncio.run(tv_trader.read_recent_exit_fill(
        tv, direction="LONG", opened_after_iso="2026-05-21T10:50:11"))
    assert res is None


def test_market_close_counts_as_exit():
    """A bot-sent market close (opposite side) is a valid exit fill."""
    tv = _tv_with_history({"panel": True, "rows": [
        _row("Buy", "Market", "29,300.75", "2026-05-21 10:50:11", "1"),     # entry (Buy), excluded
        _row("Sell", "Market", "29,410.00", "2026-05-21 11:30:00", "2"),    # exit (Sell)
    ]})
    res = asyncio.run(tv_trader.read_recent_exit_fill(tv, direction="LONG"))
    assert res["exit_price"] == 29410.00
    assert res["kind"] == "MARKET"


def test_panel_unavailable_returns_none():
    tv = _tv_with_history({"panel": False})
    assert asyncio.run(tv_trader.read_recent_exit_fill(tv, direction="LONG")) is None


def test_no_matching_rows_returns_none():
    """No filled exit on the trade's close side → None (caller falls back)."""
    tv = _tv_with_history({"panel": True, "rows": [
        _row("Buy", "Market", "29,300.75", "2026-05-21 10:50:11", "1"),     # only the entry
    ]})
    assert asyncio.run(tv_trader.read_recent_exit_fill(tv, direction="LONG")) is None


def test_evaluate_async_exception_returns_none():
    """A CDP failure must never raise — caller keeps its fallback price."""
    tv = MagicMock()

    async def boom(js, *a, **kw):
        raise RuntimeError("CDP dropped")

    tv.evaluate_async = boom
    assert asyncio.run(tv_trader.read_recent_exit_fill(tv, direction="LONG")) is None
