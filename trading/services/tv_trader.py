"""TradingView Paper Trading — place/manage orders on TradingView's demo account via CDP.

Orders appear directly on Zach's chart with real paper fills: entry markers,
stop loss lines, target lines, live P&L. Uses the TradingView Trading Panel DOM.
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


async def place_bracket_order(direction: str, entry_price: float,
                              stop_price: float, target_1: float, target_2: float,
                              trade_id: int) -> bool:
    """Place a paper trade on TradingView with stop and take profit.

    Uses the Trading Panel DOM: clicks Sell/Buy, sets qty=1, enables TP/SL,
    sets prices, and clicks the submit button. This creates a real paper
    position visible on the chart with fill markers and live P&L.
    """
    tv = await get_client()
    side = "buy" if direction == "LONG" else "sell"

    success = await _place_via_trading_panel(tv, side, stop_price, target_1)

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
        logger.info("Paper order placed: %s 1 %s @ ~%.2f  SL=%.2f TP=%.2f",
                     side.upper(), DEFAULT_SYMBOL, entry_price, stop_price, target_1)

    return success


async def _place_via_trading_panel(tv, side: str, stop: float, tp: float) -> bool:
    """Place order through TradingView's Trading Panel DOM.

    Steps:
    1. Click the Trade tab to open the order ticket
    2. Click Buy or Sell side
    3. Ensure Market order type
    4. Set qty to 1
    5. Enable TP/SL toggles and set prices
    6. Click the submit button
    """
    try:
        # Step 1: Open the Trade tab
        js_open = """
        (function() {
          var tabs = document.querySelectorAll('button');
          for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].textContent.trim() === 'Trade') {
              tabs[i].click();
              return true;
            }
          }
          return false;
        })()
        """
        await tv.evaluate(js_open)
        await asyncio.sleep(0.5)

        # Step 2: Click Buy or Sell side (these are DIVs, not buttons)
        side_class = "buy-" if side == "buy" else "sell-"
        js_side = f"""
        (function() {{
          var els = document.querySelectorAll('*');
          for (var i = 0; i < els.length; i++) {{
            var cls = (els[i].className || '').toString();
            var rect = els[i].getBoundingClientRect();
            if (cls.includes('{side_class}') && cls.includes('OnZ1FRe5') && rect.width > 50) {{
              els[i].click();
              return true;
            }}
          }}
          return false;
        }})()
        """
        await tv.evaluate(js_side)
        await asyncio.sleep(0.3)

        # Step 3: Ensure Market order type
        js_market = """
        (function() {
          var tabs = document.querySelectorAll('button');
          for (var i = 0; i < tabs.length; i++) {
            var t = tabs[i].textContent.trim();
            var rect = tabs[i].getBoundingClientRect();
            if (t === 'Market' && rect.x > 350) {
              tabs[i].click();
              return true;
            }
          }
          return false;
        })()
        """
        await tv.evaluate(js_market)
        await asyncio.sleep(0.3)

        # Step 4: Set qty to 1
        js_qty = """
        (function() {
          var inputs = document.querySelectorAll('input[type="text"]');
          var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          for (var i = 0; i < inputs.length; i++) {
            var rect = inputs[i].getBoundingClientRect();
            if (rect.x > 350 && rect.y > 250 && rect.y < 320 && rect.width > 0) {
              setter.call(inputs[i], '1');
              inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
              inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
              return true;
            }
          }
          return false;
        })()
        """
        await tv.evaluate(js_qty)
        await asyncio.sleep(0.3)

        # Step 5: Enable TP and SL toggles
        js_toggles = """
        (function() {
          var switches = document.querySelectorAll('[role="switch"]');
          var rightSwitches = [];
          for (var i = 0; i < switches.length; i++) {
            var rect = switches[i].getBoundingClientRect();
            if (rect.x > 350 && rect.width > 0) {
              rightSwitches.push({el: switches[i], y: rect.y, checked: switches[i].getAttribute('aria-checked')});
            }
          }
          rightSwitches.sort(function(a,b) { return a.y - b.y; });
          var enabled = 0;
          for (var j = 0; j < rightSwitches.length; j++) {
            if (rightSwitches[j].checked !== 'true') {
              rightSwitches[j].el.click();
            }
            enabled++;
          }
          return enabled;
        })()
        """
        await tv.evaluate(js_toggles)
        await asyncio.sleep(0.3)

        # Step 5b: Ensure TP/SL are in "price" mode (not ticks/USD)
        js_price_mode = """
        (function() {
          var btns = document.querySelectorAll('button');
          for (var i = 0; i < btns.length; i++) {
            var t = btns[i].textContent.trim();
            var rect = btns[i].getBoundingClientRect();
            if (rect.x > 350 && (t === 'Take profit, price' || t === 'Stop loss, price')) continue;
            if (rect.x > 350 && rect.y > 340 && (t.includes('ticks') || t.includes('USD')) && !t.includes('price')) {
              // Click to cycle to price mode - these buttons cycle through modes
              btns[i].click();
            }
          }
          return true;
        })()
        """
        await tv.evaluate(js_price_mode)
        await asyncio.sleep(0.3)

        # Step 6: Set TP and SL prices via triple-click select + type
        js_prices = f"""
        (function() {{
          var inputs = document.querySelectorAll('input');
          var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          var rightInputs = [];
          for (var i = 0; i < inputs.length; i++) {{
            var rect = inputs[i].getBoundingClientRect();
            if (rect.x > 350 && rect.width > 40 && rect.height > 0 && rect.y > 320 && inputs[i].type !== 'checkbox') {{
              rightInputs.push({{el: inputs[i], y: rect.y}});
            }}
          }}
          rightInputs.sort(function(a,b) {{ return a.y - b.y; }});
          var set = 0;
          // First = TP price, Second = SL price
          if (rightInputs.length >= 1) {{
            var tpEl = rightInputs[0].el;
            tpEl.focus();
            tpEl.select();
            setter.call(tpEl, '{tp:.2f}');
            tpEl.dispatchEvent(new Event('input', {{bubbles: true}}));
            tpEl.dispatchEvent(new Event('change', {{bubbles: true}}));
            tpEl.blur();
            set++;
          }}
          if (rightInputs.length >= 2) {{
            var slEl = rightInputs[1].el;
            slEl.focus();
            slEl.select();
            setter.call(slEl, '{stop:.2f}');
            slEl.dispatchEvent(new Event('input', {{bubbles: true}}));
            slEl.dispatchEvent(new Event('change', {{bubbles: true}}));
            slEl.blur();
            set++;
          }}
          return set;
        }})()
        """
        await tv.evaluate(js_prices)
        await asyncio.sleep(0.5)

        # Step 7: Click the submit button (Buy/Sell X MNQ1! MARKET)
        side_word = "Buy" if side == "buy" else "Sell"
        js_submit = f"""
        (function() {{
          var btns = document.querySelectorAll('button');
          for (var i = 0; i < btns.length; i++) {{
            var t = btns[i].textContent.trim();
            if (t.includes('{side_word}') && t.includes('MNQ')) {{
              btns[i].click();
              return {{clicked: true, text: t}};
            }}
          }}
          return {{clicked: false}};
        }})()
        """
        result = await tv.evaluate(js_submit)
        if result and result.get("clicked"):
            logger.info("Trading panel order submitted: %s", result.get("text"))
            return True
        else:
            logger.warning("Could not find submit button, falling back to line drawing")
            return False

    except Exception as e:
        logger.error("Trading panel order failed: %s", e)
        return False


async def close_via_trading_panel(tv, direction: str) -> bool:
    """Close a position by placing an opposite market order via the Trading Panel.

    If position is LONG, places a Sell Market. If SHORT, places a Buy Market.
    """
    try:
        close_side = "sell" if direction == "LONG" else "buy"
        side_class = "sell" if close_side == "sell" else "buy"
        side_word = "Sell" if close_side == "sell" else "Buy"

        # Open Trade tab
        js_open = """
        (function() {
          var tabs = document.querySelectorAll('button');
          for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].textContent.trim() === 'Trade') {
              tabs[i].click();
              return true;
            }
          }
          return false;
        })()
        """
        await tv.evaluate(js_open)
        await asyncio.sleep(0.5)

        # Click opposite side (these are DIVs, not buttons)
        side_cls = "sell-" if close_side == "sell" else "buy-"
        js_side = f"""
        (function() {{
          var els = document.querySelectorAll('*');
          for (var i = 0; i < els.length; i++) {{
            var cls = (els[i].className || '').toString();
            var rect = els[i].getBoundingClientRect();
            if (cls.includes('{side_cls}') && cls.includes('OnZ1FRe5') && rect.width > 50) {{
              els[i].click();
              return true;
            }}
          }}
          return false;
        }})()
        """
        await tv.evaluate(js_side)
        await asyncio.sleep(0.3)

        # Ensure Market
        js_market = """
        (function() {
          var tabs = document.querySelectorAll('button');
          for (var i = 0; i < tabs.length; i++) {
            var t = tabs[i].textContent.trim();
            var rect = tabs[i].getBoundingClientRect();
            if (t === 'Market' && rect.x > 350) {
              tabs[i].click();
              return true;
            }
          }
          return false;
        })()
        """
        await tv.evaluate(js_market)
        await asyncio.sleep(0.3)

        # Disable TP/SL toggles
        js_off = """
        (function() {
          var switches = document.querySelectorAll('[role="switch"]');
          for (var i = 0; i < switches.length; i++) {
            var rect = switches[i].getBoundingClientRect();
            if (rect.x > 350 && rect.width > 0 && switches[i].getAttribute('aria-checked') === 'true') {
              switches[i].click();
            }
          }
          return true;
        })()
        """
        await tv.evaluate(js_off)
        await asyncio.sleep(0.3)

        # Click submit
        js_submit = f"""
        (function() {{
          var btns = document.querySelectorAll('button');
          for (var i = 0; i < btns.length; i++) {{
            var t = btns[i].textContent.trim();
            if (t.includes('{side_word}') && t.includes('MNQ')) {{
              btns[i].click();
              return {{clicked: true, text: t}};
            }}
          }}
          return {{clicked: false}};
        }})()
        """
        result = await tv.evaluate(js_submit)
        if result and result.get("clicked"):
            logger.info("Position closed via trading panel: %s", result.get("text"))
            return True
        return False

    except Exception as e:
        logger.error("Failed to close via trading panel: %s", e)
        return False


async def close_position(trade_id: int, exit_price: float, reason: str = "") -> dict:
    """Close a paper trade position."""
    order = _active_orders.pop(trade_id, None)
    if not order:
        logger.warning("No active order for trade %d", trade_id)
        return {}

    direction = order["direction"]
    entry = order["entry"]

    # Close on TradingView chart
    try:
        tv = await get_client()
        await close_via_trading_panel(tv, direction)
    except Exception as e:
        logger.warning("Failed to close on chart: %s", e)

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

    return result


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

        # Check T1 hit (move stop to breakeven)
        if not order["t1_hit"]:
            t1_hit = (direction == "LONG" and price >= t1) or \
                     (direction == "SHORT" and price <= t1)
            if t1_hit:
                order["t1_hit"] = True
                order["stop"] = entry  # Move to breakeven
                logger.info("T1 hit for trade %d — stop moved to breakeven %.2f", trade_id, entry)

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
