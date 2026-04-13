"""TradingView Paper Trading — place/manage orders on TradingView's demo account via CDP.

Orders appear directly on Zach's chart: entry markers, stop loss lines, target lines, live P&L.
Starting balance: $5,000 demo on MNQ.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import pytz

from config import TIMEZONE, DEFAULT_SYMBOL, MULTIPLIER, HARD_CLOSE_HOUR, HARD_CLOSE_MINUTE, MAX_HOLD_MINUTES
from services.tv_client import get_client
from agents import journal
from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# Track active chart orders
_active_orders: dict[int, dict] = {}  # trade_id -> order info
_trade_shape_ids: dict[int, list[str]] = {}  # trade_id -> list of shape IDs


async def place_bracket_order(direction: str, entry_price: float,
                              stop_price: float, target_1: float, target_2: float,
                              trade_id: int) -> bool:
    """Place a paper trade on TradingView with stop and target bracket orders.

    Uses TradingView's internal trading panel. Falls back to drawing
    horizontal lines if the trading API is not accessible.
    """
    tv = await get_client()
    side = "buy" if direction == "LONG" else "sell"

    # Try Method 1: TradingView internal trading API
    success = await _try_internal_api(tv, side, stop_price, target_1, target_2)

    if not success:
        # Method 2: Draw levels on chart as visual markers
        logger.info("Using visual markers (lines) for trade display")
        success = await _draw_trade_levels(tv, direction, entry_price, stop_price, target_1, target_2, trade_id)

    if success:
        _active_orders[trade_id] = {
            "direction": direction,
            "entry": entry_price,
            "stop": stop_price,
            "target_1": target_1,
            "target_2": target_2,
            "opened_at": datetime.now(ET).isoformat(),
            "t1_hit": False,
        }

    return success


async def _try_internal_api(tv, side: str, stop: float, t1: float, t2: float) -> bool:
    """Try to place order via TradingView's internal trading controller."""
    js = f"""
    (function() {{
      try {{
        var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
        var tc = chart.model().model().tradingController();
        if (!tc || !tc.placeOrder) return {{success: false, reason: 'No trading controller'}};

        // Place market order
        tc.placeOrder({{
          symbol: '{DEFAULT_SYMBOL}',
          side: '{side}',
          type: 'market',
          qty: 1
        }});

        return {{success: true}};
      }} catch(e) {{
        return {{success: false, reason: e.message}};
      }}
    }})()
    """
    try:
        result = await tv.evaluate(js)
        if result and result.get("success"):
            logger.info("Paper order placed via internal API: %s 1 %s", side, DEFAULT_SYMBOL)
            return True
        else:
            logger.info("Internal API unavailable: %s", result.get("reason", "unknown"))
            return False
    except Exception as e:
        logger.info("Internal API error: %s", e)
        return False


async def _draw_trade_levels(tv, direction: str, entry: float, stop: float,
                              t1: float, t2: float, trade_id: int = 0) -> bool:
    """Draw horizontal lines on chart for entry, stop, and targets."""
    try:
        # Entry line (blue)
        await _draw_hline(tv, entry, "Entry " + direction, "#2196F3", 2, trade_id)
        # Stop line (red)
        await _draw_hline(tv, stop, "Stop", "#F44336", 1, trade_id)
        # Target 1 (green)
        await _draw_hline(tv, t1, "T1", "#4CAF50", 1, trade_id)
        # Target 2 (green dashed)
        await _draw_hline(tv, t2, "T2", "#4CAF50", 1, trade_id)
        logger.info("Trade levels drawn: entry=%.2f stop=%.2f t1=%.2f t2=%.2f", entry, stop, t1, t2)
        return True
    except Exception as e:
        logger.error("Failed to draw trade levels: %s", e)
        return False


async def _draw_hline(tv, price: float, text: str, color: str, width: int,
                      trade_id: Optional[int] = None) -> None:
    """Draw a horizontal line with label via TradingView drawing API."""
    js = f"""
    (function() {{
      try {{
        var chart = window.TradingViewApi._activeChartWidgetWV.value();
        var id = chart.createMultipointShape([{{price: {price}, time: Date.now()/1000}}], {{
          shape: 'horizontal_line',
          overrides: {{
            linecolor: '{color}',
            linewidth: {width},
            linestyle: 0,
            showLabel: true,
            text: '{text} {price:.2f}',
            horzLabelsAlign: 'right',
            textcolor: '{color}',
            fontsize: 10
          }}
        }});
        return {{success: true, id: id ? id.toString() : null}};
      }} catch(e) {{ return {{success: false}}; }}
    }})()
    """
    result = await tv.evaluate(js)
    if result and result.get("id") and trade_id is not None:
        _trade_shape_ids.setdefault(trade_id, []).append(result["id"])


async def close_position(trade_id: int, exit_price: float, reason: str = "") -> dict:
    """Close a paper trade position. Cleans up chart drawings."""
    order = _active_orders.pop(trade_id, None)
    if not order:
        logger.warning("No active order for trade %d", trade_id)
        return {}

    direction = order["direction"]
    entry = order["entry"]

    # Determine outcome
    if direction == "LONG":
        pts = exit_price - entry
    else:
        pts = entry - exit_price

    if pts > 0:
        outcome = "WIN"
    elif pts < 0:
        outcome = "LOSS"
    else:
        outcome = "SCRATCH"

    # Log to journal
    result = journal.log_trade_close(trade_id, exit_price, outcome, reason)

    # Send Telegram notification
    if result:
        await telegram.notify_trade_exit(
            direction=direction,
            entry=entry,
            exit_price=exit_price,
            pnl=result.get("pnl", 0),
            pnl_after_slip=result.get("pnl_after_slippage", 0),
            outcome=outcome,
            rr=result.get("rr", 0),
        )

    # Clean chart drawings
    try:
        tv = await get_client()
        await _clear_trade_drawings(tv, trade_id)
    except Exception as e:
        logger.warning("Failed to clear chart drawings: %s", e)

    return result


async def _clear_trade_drawings(tv, trade_id: Optional[int] = None) -> None:
    """Remove trade-related drawings from the chart using tracked shape IDs."""
    # Remove by tracked IDs (reliable)
    if trade_id and trade_id in _trade_shape_ids:
        ids = _trade_shape_ids.pop(trade_id)
        for shape_id in ids:
            js = f"""
            (function() {{
              try {{
                var chart = window.TradingViewApi._activeChartWidgetWV.value();
                chart.removeEntity('{shape_id}');
                return true;
              }} catch(e) {{ return false; }}
            }})()
            """
            await tv.evaluate(js)
        return

    # Fallback: remove all tracked shape IDs
    for tid, ids in list(_trade_shape_ids.items()):
        for shape_id in ids:
            js = f"""
            (function() {{
              try {{
                var chart = window.TradingViewApi._activeChartWidgetWV.value();
                chart.removeEntity('{shape_id}');
                return true;
              }} catch(e) {{ return false; }}
            }})()
            """
            await tv.evaluate(js)
    _trade_shape_ids.clear()


async def monitor_trades() -> None:
    """Trade monitor — runs every 30 seconds to manage open positions.

    Checks: stop hit, target hit, time exit, session close.
    Moves stop to breakeven after T1 hit. Closes all at 3 PM ET.
    """
    if not _active_orders:
        return

    now = datetime.now(ET)
    tv = await get_client()
    quote = await tv.get_quote()
    price = quote.get("last") or quote.get("close", 0)
    if price == 0:
        return

    for trade_id, order in list(_active_orders.items()):
        direction = order["direction"]
        entry = order["entry"]
        stop = order["stop"]
        t1 = order["target_1"]
        t2 = order["target_2"]
        opened_at = datetime.fromisoformat(order["opened_at"])

        # Check 3 PM hard close
        close_time = now.replace(hour=HARD_CLOSE_HOUR, minute=HARD_CLOSE_MINUTE, second=0)
        if now >= close_time:
            logger.info("3 PM hard close for trade %d", trade_id)
            await close_position(trade_id, price, "3 PM session close")
            continue

        # Check 2-hour time exit
        minutes_held = (now - opened_at).total_seconds() / 60
        if minutes_held >= MAX_HOLD_MINUTES:
            logger.info("2-hour time exit for trade %d (held %.0f min)", trade_id, minutes_held)
            await close_position(trade_id, price, "2-hour time exit")
            continue

        # Check stop hit
        if direction == "LONG" and price <= stop:
            logger.info("Stop hit for trade %d: price %.2f <= stop %.2f", trade_id, price, stop)
            await close_position(trade_id, price, "Stop loss hit")
            continue
        elif direction == "SHORT" and price >= stop:
            logger.info("Stop hit for trade %d: price %.2f >= stop %.2f", trade_id, price, stop)
            await close_position(trade_id, price, "Stop loss hit")
            continue

        # Check T1 hit (close 50%, move stop to breakeven)
        if not order["t1_hit"]:
            t1_hit = (direction == "LONG" and price >= t1) or \
                     (direction == "SHORT" and price <= t1)
            if t1_hit:
                order["t1_hit"] = True
                order["stop"] = entry  # Move to breakeven
                logger.info("T1 hit for trade %d — stop moved to breakeven %.2f", trade_id, entry)
                # Update chart
                try:
                    await _draw_hline(tv, entry, "BE Stop", "#FF9800", 1, trade_id)
                except Exception:
                    pass

        # Check T2 hit
        t2_hit = (direction == "LONG" and price >= t2) or \
                 (direction == "SHORT" and price <= t2)
        if t2_hit:
            logger.info("T2 hit for trade %d", trade_id)
            await close_position(trade_id, price, "Target 2 hit")
            continue


def get_active_orders() -> dict:
    """Get currently active orders for status check."""
    return dict(_active_orders)
