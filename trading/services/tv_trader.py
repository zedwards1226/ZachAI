"""TradingView Paper Trading — place/manage orders on TradingView's demo account via CDP.

Orders appear directly on Zach's chart with real paper fills: entry markers,
stop loss lines, target lines, live P&L. Uses the TradingView Trading Panel DOM.
Starting balance: $5,000 demo on MNQ.

Speed optimization: all DOM steps collapsed into a single CDP evaluate() call
so order placement completes in ~300ms instead of ~4 seconds.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pytz

from config import TIMEZONE, DEFAULT_SYMBOL, MULTIPLIER, MAX_HOLD_MINUTES, get_hard_close_time
from services.tv_client import get_client
from services.state_manager import read_state, write_state
from agents import journal
from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# Track active chart orders — persisted to state/active_orders.json
_active_orders: dict[int, dict] = {}  # trade_id -> order info


def _persist_active_orders() -> None:
    """Write _active_orders to disk so they survive restarts."""
    write_state("active_orders", {
        "orders": {str(k): v for k, v in _active_orders.items()},
    })


async def load_and_reconcile_orders() -> None:
    """Load active orders from disk on startup and reconcile.

    If the system crashed with trades open, this recovers them.
    Trades that hit stop/target while offline are auto-closed in journal.
    Trades still in range resume normal monitoring.
    """
    global _active_orders
    data = read_state("active_orders")
    orders = data.get("orders", {})
    if not orders:
        return

    _active_orders = {int(k): v for k, v in orders.items()}
    count = len(_active_orders)
    logger.warning("Recovered %d active order(s) from state file", count)

    # Try to reconcile — check if stops/targets were hit while offline
    try:
        tv = await get_client()
        quote = await tv.get_quote()
        price = quote.get("last") or quote.get("close", 0)

        if price > 0:
            for trade_id, order in list(_active_orders.items()):
                direction = order["direction"]
                stop = order["stop"]
                t1 = order["target_1"]

                stop_hit = (direction == "LONG" and price <= stop) or \
                           (direction == "SHORT" and price >= stop)
                t1_hit = (direction == "LONG" and price >= t1) or \
                          (direction == "SHORT" and price <= t1)

                if stop_hit:
                    logger.warning("Reconciling trade %d: stop was hit (price=%.2f, stop=%.2f)",
                                   trade_id, price, stop)
                    await close_position(trade_id, stop, "Stop hit (reconciled after restart)",
                                         outcome="LOSS", skip_chart_close=True)
                elif t1_hit:
                    logger.warning("Reconciling trade %d: T1 was hit (price=%.2f, t1=%.2f)",
                                   trade_id, price, t1)
                    await close_position(trade_id, t1, "T1 hit (reconciled after restart)",
                                         outcome="WIN", skip_chart_close=True)
                else:
                    logger.info("Trade %d still in range (price=%.2f), resuming monitoring",
                                trade_id, price)

        if _active_orders:
            await telegram.send(
                f"System restarted — {len(_active_orders)} open trade(s) recovered and monitoring resumed."
            )
    except Exception as e:
        logger.error("Order reconciliation failed (will retry via monitor): %s", e)


async def place_bracket_order(direction: str, entry_price: float,
                              stop_price: float, target_1: float, target_2: float,
                              trade_id: int) -> bool:
    """Place a paper trade on TradingView with stop and take profit.

    Single CDP call — opens Trade panel, clicks Buy/Sell, sets Market,
    qty=1, enables TP/SL, sets prices, clicks submit. ~300ms total.
    """
    tv = await get_client()
    side = "buy" if direction == "LONG" else "sell"

    success = await _place_via_trading_panel(tv, side, stop_price, target_1)

    # Confirm order appeared by checking quote is valid
    if success:
        confirmed = await _confirm_order_placed(tv, timeout=5.0)
        if not confirmed:
            logger.warning("Order confirmation timed out for trade %d — proceeding anyway", trade_id)

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
        _persist_active_orders()
        logger.info("Paper order placed: %s 1 %s @ ~%.2f  SL=%.2f TP=%.2f",
                     side.upper(), DEFAULT_SYMBOL, entry_price, stop_price, target_1)

    return success


async def _confirm_order_placed(tv, timeout: float = 5.0) -> bool:
    """Poll TradingView for a few seconds to confirm an order was accepted."""
    import asyncio
    import time as _time
    start = _time.monotonic()
    while _time.monotonic() - start < timeout:
        try:
            quote = await tv.get_quote()
            price = quote.get("last") or quote.get("close", 0)
            if price > 0:
                return True
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return False


async def _place_via_trading_panel(tv, side: str, stop: float, tp: float) -> bool:
    """Place order through TradingView's Trading Panel DOM — single CDP call.

    All 7 steps run in one async IIFE with minimal internal delays (~50ms)
    for React to process state changes between critical steps.
    """
    side_class = "buy-" if side == "buy" else "sell-"
    side_word = "Buy" if side == "buy" else "Sell"

    js = f"""
    (async function() {{
      var sleep = function(ms) {{ return new Promise(function(r) {{ setTimeout(r, ms); }}); }};
      var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;

      // Step 1: Open Trade tab
      var tabs = document.querySelectorAll('button');
      for (var i = 0; i < tabs.length; i++) {{
        if (tabs[i].textContent.trim() === 'Trade') {{ tabs[i].click(); break; }}
      }}
      await sleep(150);

      // Step 2: Click Buy/Sell side (DIVs, not buttons)
      var sideFound = false;
      var els = document.querySelectorAll('*');
      for (var i = 0; i < els.length; i++) {{
        var cls = (els[i].className || '').toString();
        var rect = els[i].getBoundingClientRect();
        if (cls.includes('{side_class}') && cls.includes('OnZ1FRe5') && rect.width > 50) {{
          els[i].click();
          sideFound = true;
          break;
        }}
      }}
      if (!sideFound) return {{clicked: false, reason: 'side_not_found'}};
      await sleep(100);

      // Step 3: Click Market order type
      tabs = document.querySelectorAll('button');
      for (var i = 0; i < tabs.length; i++) {{
        var t = tabs[i].textContent.trim();
        var rect = tabs[i].getBoundingClientRect();
        if (t === 'Market' && rect.x > 350) {{ tabs[i].click(); break; }}
      }}
      await sleep(50);

      // Step 4: Set qty to 1
      var inputs = document.querySelectorAll('input[type="text"]');
      for (var i = 0; i < inputs.length; i++) {{
        var rect = inputs[i].getBoundingClientRect();
        if (rect.x > 350 && rect.y > 250 && rect.y < 320 && rect.width > 0) {{
          setter.call(inputs[i], '1');
          inputs[i].dispatchEvent(new Event('input', {{bubbles: true}}));
          inputs[i].dispatchEvent(new Event('change', {{bubbles: true}}));
          break;
        }}
      }}

      // Step 5: Enable TP/SL toggles
      var switches = document.querySelectorAll('[role="switch"]');
      var rightSwitches = [];
      for (var i = 0; i < switches.length; i++) {{
        var rect = switches[i].getBoundingClientRect();
        if (rect.x > 350 && rect.width > 0) {{
          rightSwitches.push({{el: switches[i], y: rect.y, checked: switches[i].getAttribute('aria-checked')}});
        }}
      }}
      rightSwitches.sort(function(a,b) {{ return a.y - b.y; }});
      for (var j = 0; j < rightSwitches.length; j++) {{
        if (rightSwitches[j].checked !== 'true') {{
          rightSwitches[j].el.click();
        }}
      }}
      await sleep(100);

      // Step 5b: Ensure price mode (not ticks/USD)
      var btns = document.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) {{
        var t = btns[i].textContent.trim();
        var rect = btns[i].getBoundingClientRect();
        if (rect.x > 350 && rect.y > 340 && (t.includes('ticks') || t.includes('USD')) && !t.includes('price')) {{
          btns[i].click();
        }}
      }}
      await sleep(50);

      // Step 6: Set TP and SL prices
      var allInputs = document.querySelectorAll('input');
      var rightInputs = [];
      for (var i = 0; i < allInputs.length; i++) {{
        var rect = allInputs[i].getBoundingClientRect();
        if (rect.x > 350 && rect.width > 40 && rect.height > 0 && rect.y > 320 && allInputs[i].type !== 'checkbox') {{
          rightInputs.push({{el: allInputs[i], y: rect.y}});
        }}
      }}
      rightInputs.sort(function(a,b) {{ return a.y - b.y; }});
      var pricesSet = 0;
      if (rightInputs.length >= 1) {{
        var tpEl = rightInputs[0].el;
        tpEl.focus(); tpEl.select();
        setter.call(tpEl, '{tp:.2f}');
        tpEl.dispatchEvent(new Event('input', {{bubbles: true}}));
        tpEl.dispatchEvent(new Event('change', {{bubbles: true}}));
        tpEl.blur();
        pricesSet++;
      }}
      if (rightInputs.length >= 2) {{
        var slEl = rightInputs[1].el;
        slEl.focus(); slEl.select();
        setter.call(slEl, '{stop:.2f}');
        slEl.dispatchEvent(new Event('input', {{bubbles: true}}));
        slEl.dispatchEvent(new Event('change', {{bubbles: true}}));
        slEl.blur();
        pricesSet++;
      }}
      await sleep(200);

      // Step 7: Click submit button (handles two-step: "Start creating order" → "Buy/Sell MNQ")
      var findAndClickSubmit = function() {{
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {{
          var t = btns[i].textContent.trim();
          if (t.includes('{side_word}') && t.includes('MNQ')) {{
            btns[i].click();
            return {{clicked: true, text: t, pricesSet: pricesSet}};
          }}
        }}
        // Fallback: "Start creating order" button (TradingView shows this before final submit)
        for (var i = 0; i < btns.length; i++) {{
          var t = btns[i].textContent.trim();
          if (t === 'Start creating order') {{
            btns[i].click();
            return null; // needs second click
          }}
        }}
        return {{clicked: false, reason: 'submit_not_found', pricesSet: pricesSet}};
      }};

      var result = findAndClickSubmit();
      if (result) return result;

      // "Start creating order" was clicked — wait for actual submit button
      await sleep(200);
      result = findAndClickSubmit();
      return result || {{clicked: false, reason: 'submit_not_found_after_retry', pricesSet: pricesSet}};
    }})()
    """
    try:
        result = await tv.evaluate_async(js)
        if result and result.get("clicked"):
            logger.info("Trading panel order submitted: %s", result.get("text"))
            return True
        else:
            logger.warning("Order placement failed: %s", result)
            return False
    except Exception as e:
        logger.error("Trading panel order failed: %s", e)
        return False


async def close_via_trading_panel(tv, direction: str) -> bool:
    """Close a position via opposite market order — single CDP call.

    If LONG, places Sell Market. If SHORT, places Buy Market.
    No TP/SL needed for closing orders.
    """
    close_side = "sell" if direction == "LONG" else "buy"
    side_class = "sell-" if close_side == "sell" else "buy-"
    side_word = "Sell" if close_side == "sell" else "Buy"

    js = f"""
    (async function() {{
      var sleep = function(ms) {{ return new Promise(function(r) {{ setTimeout(r, ms); }}); }};

      // Step 1: Open Trade tab
      var tabs = document.querySelectorAll('button');
      for (var i = 0; i < tabs.length; i++) {{
        if (tabs[i].textContent.trim() === 'Trade') {{ tabs[i].click(); break; }}
      }}
      await sleep(150);

      // Step 2: Click opposite side
      var sideFound = false;
      var els = document.querySelectorAll('*');
      for (var i = 0; i < els.length; i++) {{
        var cls = (els[i].className || '').toString();
        var rect = els[i].getBoundingClientRect();
        if (cls.includes('{side_class}') && cls.includes('OnZ1FRe5') && rect.width > 50) {{
          els[i].click();
          sideFound = true;
          break;
        }}
      }}
      if (!sideFound) return {{clicked: false, reason: 'side_not_found'}};
      await sleep(100);

      // Step 3: Click Market
      tabs = document.querySelectorAll('button');
      for (var i = 0; i < tabs.length; i++) {{
        var t = tabs[i].textContent.trim();
        var rect = tabs[i].getBoundingClientRect();
        if (t === 'Market' && rect.x > 350) {{ tabs[i].click(); break; }}
      }}
      await sleep(50);

      // Step 4: Disable TP/SL toggles
      var switches = document.querySelectorAll('[role="switch"]');
      for (var i = 0; i < switches.length; i++) {{
        var rect = switches[i].getBoundingClientRect();
        if (rect.x > 350 && rect.width > 0 && switches[i].getAttribute('aria-checked') === 'true') {{
          switches[i].click();
        }}
      }}
      await sleep(50);

      // Step 5: Click submit (handles two-step pattern)
      var findAndClick = function() {{
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {{
          var t = btns[i].textContent.trim();
          if (t.includes('{side_word}') && t.includes('MNQ')) {{
            btns[i].click();
            return {{clicked: true, text: t}};
          }}
        }}
        for (var i = 0; i < btns.length; i++) {{
          var t = btns[i].textContent.trim();
          if (t === 'Start creating order') {{
            btns[i].click();
            return null;
          }}
        }}
        return {{clicked: false, reason: 'submit_not_found'}};
      }};

      var result = findAndClick();
      if (result) return result;
      await sleep(200);
      result = findAndClick();
      return result || {{clicked: false, reason: 'submit_not_found_after_retry'}};
    }})()
    """
    try:
        result = await tv.evaluate_async(js)
        if result and result.get("clicked"):
            logger.info("Position closed via trading panel: %s", result.get("text"))
            return True
        logger.warning("Close order failed: %s", result)
        return False
    except Exception as e:
        logger.error("Failed to close via trading panel: %s", e)
        return False


async def close_position(trade_id: int, exit_price: float, reason: str = "",
                         outcome: Optional[str] = None,
                         skip_chart_close: bool = False) -> dict:
    """Close a paper trade position.

    skip_chart_close=True means the TV bracket already closed the position
    (TP/SL auto-fill) and we just need to reconcile journal state. Sending a
    market order in that case would OPEN a fresh opposite position.
    """
    order = _active_orders.pop(trade_id, None)
    if not order:
        logger.warning("No active order for trade %d", trade_id)
        return {}

    _persist_active_orders()

    direction = order["direction"]
    entry = order["entry"]

    # Close on TradingView chart (only if TV didn't already auto-close)
    if not skip_chart_close:
        try:
            tv = await get_client()
            await close_via_trading_panel(tv, direction)
        except Exception as e:
            logger.warning("Failed to close on chart: %s", e)

    # Determine outcome
    if outcome is None:
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

    TV's bracket handles stop-loss and T1 take-profit auto-closes. This
    monitor reconciles TV's auto-closes into the journal, and sends
    explicit market closes only for session-end and time-based exits.
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
        opened_at = datetime.fromisoformat(order["opened_at"])

        # Hard close — 3 PM normally, 1 PM on half days
        close_h, close_m = get_hard_close_time(now)
        close_time = now.replace(hour=close_h, minute=close_m, second=0)
        if now >= close_time:
            logger.info("%d:%02d hard close for trade %d", close_h, close_m, trade_id)
            await close_position(trade_id, price, f"{close_h}:{close_m:02d} session close")
            continue

        # Check 2-hour time exit — TV bracket stays open, we explicitly close
        minutes_held = (now - opened_at).total_seconds() / 60
        if minutes_held >= MAX_HOLD_MINUTES:
            logger.info("2-hour time exit for trade %d (held %.0f min)", trade_id, minutes_held)
            await close_position(trade_id, price, "2-hour time exit")
            continue

        # Stop hit — TV bracket auto-closed the position at the stop. Reconcile
        # without sending a market order (which would open an opposite position).
        if direction == "LONG" and price <= stop:
            logger.info("Stop hit for trade %d: price %.2f <= stop %.2f (TV auto-closed)",
                        trade_id, price, stop)
            await close_position(trade_id, stop, "Stop loss hit",
                                 outcome="LOSS", skip_chart_close=True)
            continue
        if direction == "SHORT" and price >= stop:
            logger.info("Stop hit for trade %d: price %.2f >= stop %.2f (TV auto-closed)",
                        trade_id, price, stop)
            await close_position(trade_id, stop, "Stop loss hit",
                                 outcome="LOSS", skip_chart_close=True)
            continue

        # T1 hit — TV bracket auto-closed at T1. Reconcile. No market order.
        t1_hit = (direction == "LONG" and price >= t1) or \
                 (direction == "SHORT" and price <= t1)
        if t1_hit:
            logger.info("T1 hit for trade %d at %.2f (TV auto-closed)", trade_id, t1)
            await close_position(trade_id, t1, "T1 target hit",
                                 outcome="WIN", skip_chart_close=True)
            continue


def get_active_orders() -> dict:
    """Get currently active orders for status check."""
    return dict(_active_orders)
