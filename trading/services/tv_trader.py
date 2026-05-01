"""TradingView Paper Trading — place/manage orders on TradingView's demo account via CDP.

Orders appear directly on Zach's chart with real paper fills: entry markers,
stop loss lines, target lines, live P&L. Uses the TradingView Trading Panel DOM.
Starting balance: $5,000 demo on MNQ.

Speed optimization: all DOM steps collapsed into a single CDP evaluate() call
so order placement completes in ~300ms instead of ~4 seconds.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import pytz

from config import (
    TIMEZONE, DEFAULT_SYMBOL, MULTIPLIER, MAX_HOLD_MINUTES, get_hard_close_time,
    VIX_INTERVENTION_PCT,
    TRAIL_DISTANCE_RATIO, POSITION_OPEN_FUNDS_THRESHOLD, STARTING_CAPITAL,
)
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

    Bracket TP is target_2 (1.5x ORB). target_1 is the breakeven trigger —
    when price reaches T1, monitor_trades() flips virtual_stop to entry.
    Single CDP call — opens Trade panel, clicks Buy/Sell, sets Market,
    qty=1, enables TP/SL, sets prices, clicks submit. ~300ms total.
    """
    # Paper-mode guard — refuse to place orders unless explicitly authorized
    if os.getenv("PAPER_MODE", "true").lower() != "true":
        logger.error("PAPER_MODE != true — refusing to place order. "
                     "Set PAPER_MODE=true in trading/.env to confirm paper trading.")
        try:
            journal.mark_failed_placement(trade_id, "PAPER_MODE not authorized")
        except Exception as e:
            logger.error("Failed to mark trade %d FAILED_PLACEMENT: %s", trade_id, e)
        raise RuntimeError("Live trading not authorized — set PAPER_MODE=true in .env")

    tv = await get_client()
    side = "buy" if direction == "LONG" else "sell"

    # Pre-check 1: DOM health — verify TV is in a tradeable state.
    # Stops the side_not_found cascade (2026-04-30) when broker-selection modal is open
    # or Paper Trading session is disconnected.
    dom_ready, dom_reason = await tv_dom_ready(tv)
    if not dom_ready:
        logger.error("Refusing trade %d: TV DOM not ready (reason=%s)", trade_id, dom_reason)
        try:
            journal.mark_failed_placement(trade_id, f"dom_not_ready:{dom_reason}")
        except Exception as e:
            logger.error("Failed to mark trade %d FAILED_PLACEMENT: %s", trade_id, e)
        try:
            await telegram.notify_hard_block(f"TV DOM not ready: {dom_reason}. No order placed.")
        except Exception:
            pass
        return False

    # Pre-check 2: refuse to stack a second open position on top of an existing one.
    # The original phantom-short bug was caused by adding trade #6 while trade #5 still
    # held its margin — TV silently rejected and the bot tracked a non-existent position.
    pre_position = await _has_open_position(tv)
    if pre_position is True:
        logger.error("Refusing trade %d: TV already has an open position (margin in use)", trade_id)
        try:
            journal.mark_failed_placement(trade_id, "position already open on TV")
        except Exception as e:
            logger.error("Failed to mark trade %d FAILED_PLACEMENT: %s", trade_id, e)
        return False

    # Capture pre-submission toast snapshot — needed to diff for the acceptance check.
    before_toasts = await _capture_toast_snapshot(tv)

    # TV bracket TP = T2 (1.5x ORB). Monitor handles the BE move at T1.
    submitted, fail_reason = await _place_via_trading_panel(tv, side, stop_price, target_2)

    success = False
    if submitted:
        # Verify TV actually accepted the order (didn't reject it for funds, etc.)
        accepted, accept_reason = await _check_order_acceptance(tv, before_toasts, timeout=4.0)
        if accepted:
            success = True
            logger.debug("Order accepted by TV: %s", accept_reason)
        else:
            success = False
            fail_reason = f"tv_{accept_reason}"
            logger.error("TV did not accept the order: %s — NOT tracking in active_orders",
                         accept_reason)

    if success:
        # Capture VIX-at-open for mid-trade VIX intervention
        structure = read_state("structure") or {}
        vix_at_open = structure.get("vix")

        _active_orders[trade_id] = {
            "direction": direction,
            "entry": entry_price,
            "stop": stop_price,
            "target_1": target_1,        # BE trigger — informational only
            "target_2": target_2,        # Actual TV TP
            "opened_at": datetime.now(ET).isoformat(),
            "t1_hit": False,
            "virtual_stop": None,        # Set to entry once t1_hit
            "vix_at_open": vix_at_open,
        }
        _persist_active_orders()
        logger.info("Paper order placed: %s 1 %s @ ~%.2f  SL=%.2f TP=%.2f (T1 BE-trigger=%.2f, vix_at_open=%s)",
                     side.upper(), DEFAULT_SYMBOL, entry_price, stop_price, target_2, target_1,
                     f"{vix_at_open:.1f}" if vix_at_open else "n/a")
    else:
        # Clean the phantom journal row so it doesn't sit OPEN forever.
        try:
            journal.mark_failed_placement(trade_id, fail_reason or "unknown")
        except Exception as e:
            logger.error("Failed to mark trade %d FAILED_PLACEMENT: %s", trade_id, e)

    return success


async def _capture_toast_snapshot(tv) -> str:
    """Snapshot the current trading-notification toast text. Used to diff for new toasts."""
    js = """
    (function() {
      var groups = document.querySelectorAll('[data-name*="toast"], [class*="toast"]');
      var s = '';
      for (var i = 0; i < groups.length; i++) {
        s += '|' + (groups[i].textContent || '');
      }
      return s;
    })()
    """
    try:
        r = await tv.evaluate(js)
        return r if isinstance(r, str) else ""
    except Exception:
        return ""


async def _check_order_outcome(tv, before_snapshot: str, timeout: float = 4.0) -> str:
    """After submitting an order, wait for TV's confirmation toast and classify it.

    Returns one of: 'executed', 'placed', 'rejected_funds', 'rejected', 'unknown'.
    Uses the diff against before_snapshot so old toasts don't pollute the result.
    """
    import asyncio
    import time as _time
    start = _time.monotonic()
    while _time.monotonic() - start < timeout:
        after = await _capture_toast_snapshot(tv)
        new_text = after.replace(before_snapshot, "") if before_snapshot else after
        if "Market order rejected" in new_text:
            if "Not enough funds" in new_text or "margin exceeds" in new_text:
                return "rejected_funds"
            return "rejected"
        if "Market order executed" in new_text:
            return "executed"
        if "Market order placed" in new_text:
            # Don't return placed yet — wait to see if it executes or is rejected
            pass
        await asyncio.sleep(0.5)
    return "unknown"


async def tv_dom_ready(tv) -> tuple[bool, str]:
    """Pre-flight DOM health check — verify TV is in a tradeable state.

    Returns (ready, reason):
      ready=True, reason='ok' — broker connected, side selectors visible, no blocking modal
      ready=False, reason='broker_modal' — broker-selection modal is open (today's bug)
      ready=False, reason='paper_trading_disconnected' — Paper Trading session not active
      ready=False, reason='side_selectors_missing' — Buy/Sell side tiles not in DOM
      ready=False, reason='unknown' — couldn't determine

    Returning False prevents place_bracket_order / close_via_trading_panel from
    attempting to interact with a broken DOM. Stops the side_not_found cascade.
    """
    js = r"""
    (function() {
      var bodyText = document.body.innerText || '';

      // 1. Broker-selection modal blocking — this is the worst state to trade in.
      //    Detected by today's bug (2026-04-30).
      if (bodyText.includes('Trade with your broker') &&
          bodyText.includes('Brokerage simulator')) {
        return {ready: false, reason: 'broker_modal'};
      }

      // 2. The broker-selection follow-up modal ("Connect" button visible)
      if (bodyText.match(/Paper Trading[\s\S]{0,30}Connect/)) {
        return {ready: false, reason: 'paper_trading_disconnected'};
      }

      // 3. Verify Paper Trading footer/tab is visible — this is the persistent indicator
      //    that Paper Trading session is connected. "Trade" tab next to it = trade panel
      //    is reachable. The trade panel may be collapsed; that's fine — place_bracket_order
      //    opens the Trade tab itself as step 1 of its DOM script.
      var paperTab = false, tradeTab = false;
      var btns = document.querySelectorAll('button, [role="button"], [role="tab"]');
      for (var i = 0; i < btns.length; i++) {
        var t = (btns[i].textContent || '').trim();
        if (t === 'Paper Trading') paperTab = true;
        if (t === 'Trade' || t === 'TradeTrade') tradeTab = true;
        if (paperTab && tradeTab) break;
      }

      if (!paperTab) {
        return {ready: false, reason: 'paper_trading_not_active'};
      }
      if (!tradeTab) {
        return {ready: false, reason: 'trade_tab_missing'};
      }

      return {ready: true, reason: 'ok'};
    })()
    """
    try:
        result = await tv.evaluate(js) or {}
        ready = bool(result.get("ready"))
        reason = result.get("reason", "unknown")
        return (ready, reason)
    except Exception as e:
        logger.warning("tv_dom_ready check failed: %s", e)
        return (False, "exception")


async def tv_get_positions(tv) -> dict:
    """Query TV-live for current open position state. SOURCE OF TRUTH for
    'are we flat?' decisions, replacing local-state assumptions.

    Returns a dict:
      {
        "count": int,              # estimated number of open MNQ contracts (0 if flat)
        "has_position": bool,      # True if at least one position open
        "available_funds": float | None,  # margin available for new orders
        "signal": str,             # how we determined the answer (debug)
      }

    The available-funds heuristic is the most reliable signal across TV's
    various trading-panel states (collapsed, expanded, account-info view).
    Positions consume ~$2,720 of margin per MNQ contract, so a drop in
    available funds tells us a position is open even when the position rows
    aren't visible in the current panel tab.
    """
    js = r"""
    (function() {
      var allText = document.body.innerText || '';
      // Strong direct signal: "Avg Fill Price" only appears when a position row is rendered
      var hasAvgFill = allText.includes('Avg Fill Price');
      // Margin display "X / Y" — Y is available funds for new orders
      var m = allText.match(/Margin[\s\S]{1,30}?([\d,]+\.\d+)\s*\/\s*([\d,]+\.\d+)/);
      var avail = m ? parseFloat(m[2].replace(/,/g, '')) : null;
      return {hasAvgFill: hasAvgFill, avail: avail};
    })()
    """
    try:
        r = await tv.evaluate(js) or {}
    except Exception as e:
        logger.warning("tv_get_positions JS failed: %s", e)
        return {"count": 0, "has_position": False, "available_funds": None,
                "signal": "exception"}

    avail = r.get("avail")
    has_avg_fill = bool(r.get("hasAvgFill"))

    # Direct signal — TV is showing position rows
    if has_avg_fill:
        # Estimate count from margin used (each MNQ takes ~$2720 margin)
        if avail is not None:
            margin_used = STARTING_CAPITAL - avail
            est_count = max(1, round(margin_used / 2720))
        else:
            est_count = 1
        return {"count": est_count, "has_position": True,
                "available_funds": avail, "signal": "avg_fill_price_visible"}

    # Heuristic — available funds dropped below threshold = position open
    if avail is not None:
        threshold = STARTING_CAPITAL * POSITION_OPEN_FUNDS_THRESHOLD
        if avail < threshold:
            margin_used = STARTING_CAPITAL - avail
            est_count = max(1, round(margin_used / 2720))
            return {"count": est_count, "has_position": True,
                    "available_funds": avail, "signal": "low_avail_funds"}
        return {"count": 0, "has_position": False,
                "available_funds": avail, "signal": "full_avail_funds"}

    # Couldn't determine — return unknown
    return {"count": 0, "has_position": False, "available_funds": None,
            "signal": "unknown"}


async def _has_open_position(tv) -> Optional[bool]:
    """Best-effort check: does TV show an open MNQ position?

    Returns True if confident a position is open, False if confident flat,
    None if can't determine. Uses available-funds heuristic: positions consume
    margin (~$2,720 per MNQ contract) so available drops well below the
    starting balance when a position is open.
    """
    js = """
    (function() {
      var allText = document.body.innerText || '';
      // Strong direct signal: "Avg Fill Price" only appears when a position row is rendered
      if (allText.includes('Avg Fill Price')) return {has: true, signal: 'avg_fill_price'};
      // Margin display "X / Y" — Y is available funds for new orders
      var m = allText.match(/Margin[\\s\\S]{1,30}?([\\d,]+\\.\\d+)\\s*\\/\\s*([\\d,]+\\.\\d+)/);
      if (m) {
        var avail = parseFloat(m[2].replace(/,/g, ''));
        return {has: null, signal: 'margin_display', avail: avail};
      }
      return {has: null, signal: 'unknown', avail: null};
    })()
    """
    try:
        r = await tv.evaluate(js) or {}
    except Exception:
        return None
    if r.get("has") is True:
        return True
    avail = r.get("avail")
    if avail is None:
        return None
    threshold = STARTING_CAPITAL * POSITION_OPEN_FUNDS_THRESHOLD
    return avail < threshold


async def _check_order_acceptance(tv, before_snapshot: str, timeout: float = 4.0) -> tuple[bool, str]:
    """Wait for TV order confirmation. Combines toast scan with position-state probe.

    Returns (accepted, reason). reason is 'executed', 'rejected_funds', 'rejected',
    'unknown'. If the toast scan is inconclusive, falls back to checking whether
    a position now exists on TV.
    """
    outcome = await _check_order_outcome(tv, before_snapshot, timeout)
    if outcome == "executed":
        return (True, "executed")
    if outcome in ("rejected_funds", "rejected"):
        return (False, outcome)
    # outcome == 'unknown' — fall back to position-state probe
    has_pos = await _has_open_position(tv)
    if has_pos is True:
        return (True, "position_visible")
    if has_pos is False:
        return (False, "no_position_after_submit")
    # Still unknown — log warning but treat as failure (safer)
    return (False, "unknown")


async def _place_via_trading_panel(tv, side: str, stop: float, tp: float) -> tuple[bool, str]:
    """Place order through TradingView's Trading Panel DOM — single CDP call.

    All 7 steps run in one async IIFE with minimal internal delays (~50ms)
    for React to process state changes between critical steps.

    Returns (success, reason). reason is empty on success, otherwise one of:
    side_not_found, submit_not_found, submit_not_found_after_retry, exception,
    or 'unknown' if the DOM result was malformed.
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

      // Step 2: Click Buy/Sell side (DIVs, not buttons).
      // Two-pass selector — primary uses the hashed TV class (precise);
      // fallback relies on the semantic `buy-`/`sell-` prefix + panel
      // position, so a TV UI update that rotates the hash doesn't break
      // order placement. sideMatch tells Python which path hit.
      var sideFound = false;
      var sideMatch = 'none';
      var els = document.querySelectorAll('*');
      for (var i = 0; i < els.length; i++) {{
        var cls = (els[i].className || '').toString();
        var rect = els[i].getBoundingClientRect();
        if (cls.includes('{side_class}') && cls.includes('OnZ1FRe5') && rect.width > 50) {{
          els[i].click();
          sideFound = true;
          sideMatch = 'hashed';
          break;
        }}
      }}
      if (!sideFound) {{
        for (var i = 0; i < els.length; i++) {{
          var cls = (els[i].className || '').toString();
          var rect = els[i].getBoundingClientRect();
          // Trade-panel tile shape: right-hand column, clickable DIV,
          // moderate width/height (not a container or a thin border).
          if (cls.includes('{side_class}') &&
              rect.x > 350 &&
              rect.width > 50 && rect.width < 400 &&
              rect.height > 20 && rect.height < 150) {{
            els[i].click();
            sideFound = true;
            sideMatch = 'semantic';
            break;
          }}
        }}
      }}
      if (!sideFound) return {{clicked: false, reason: 'side_not_found', sideMatch: sideMatch}};
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
            return {{clicked: true, text: t, pricesSet: pricesSet, sideMatch: sideMatch}};
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
        return {{clicked: false, reason: 'submit_not_found', pricesSet: pricesSet, sideMatch: sideMatch}};
      }};

      var result = findAndClickSubmit();
      if (result) return result;

      // "Start creating order" was clicked — wait for actual submit button
      await sleep(200);
      result = findAndClickSubmit();
      return result || {{clicked: false, reason: 'submit_not_found_after_retry', pricesSet: pricesSet, sideMatch: sideMatch}};
    }})()
    """
    try:
        result = await tv.evaluate_async(js)
        if result and result.get("clicked"):
            logger.info("Trading panel order submitted: %s", result.get("text"))
            # If the semantic fallback hit, the hashed selector is stale —
            # alert so Zach can refresh the TV class hash in the source.
            if result.get("sideMatch") == "semantic":
                logger.warning("DOM fallback used — TradingView class hash rotated")
                try:
                    await telegram.send(
                        "⚠️ <b>TV DOM drift detected</b>\n"
                        "Order placed using the semantic fallback selector — the "
                        "hashed <code>OnZ1FRe5</code> class is stale. TradingView "
                        "likely shipped a UI update. Refresh the hash in "
                        "<code>services/tv_trader.py</code> when convenient; orders "
                        "still work via fallback in the meantime."
                    )
                except Exception:
                    pass
            return True, ""
        else:
            reason = (result or {}).get("reason", "unknown")
            logger.warning("Order placement failed: %s", result)
            # Fail loud — journal already has a phantom OPEN trade row at this point.
            # Zach needs to know immediately so he can reconnect broker / kill the row.
            try:
                await telegram.send(
                    f"❗ <b>Order placement FAILED</b>\n"
                    f"Reason: <code>{reason}</code>\n"
                    f"Side: {side.upper()}  Stop: {stop:.2f}  TP: {tp:.2f}\n\n"
                    f"Likely cause: Paper Trading broker disconnected. "
                    f"Open TradingView → click 'Trade' top-right → reconnect Paper Trading. "
                    f"Journal row will be marked FAILED_PLACEMENT automatically."
                )
            except Exception:
                pass
            return False, reason
    except Exception as e:
        logger.error("Trading panel order failed: %s", e)
        try:
            await telegram.send(f"❗ Order placement exception: <code>{e}</code>")
        except Exception:
            pass
        return False, f"exception: {e}"


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

      // Step 2: Click opposite side — same two-pass selector as place_bracket.
      var sideFound = false;
      var sideMatch = 'none';
      var els = document.querySelectorAll('*');
      for (var i = 0; i < els.length; i++) {{
        var cls = (els[i].className || '').toString();
        var rect = els[i].getBoundingClientRect();
        if (cls.includes('{side_class}') && cls.includes('OnZ1FRe5') && rect.width > 50) {{
          els[i].click();
          sideFound = true;
          sideMatch = 'hashed';
          break;
        }}
      }}
      if (!sideFound) {{
        for (var i = 0; i < els.length; i++) {{
          var cls = (els[i].className || '').toString();
          var rect = els[i].getBoundingClientRect();
          if (cls.includes('{side_class}') &&
              rect.x > 350 &&
              rect.width > 50 && rect.width < 400 &&
              rect.height > 20 && rect.height < 150) {{
            els[i].click();
            sideFound = true;
            sideMatch = 'semantic';
            break;
          }}
        }}
      }}
      if (!sideFound) return {{clicked: false, reason: 'side_not_found', sideMatch: sideMatch}};
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
            return {{clicked: true, text: t, sideMatch: sideMatch}};
          }}
        }}
        for (var i = 0; i < btns.length; i++) {{
          var t = btns[i].textContent.trim();
          if (t === 'Start creating order') {{
            btns[i].click();
            return null;
          }}
        }}
        return {{clicked: false, reason: 'submit_not_found', sideMatch: sideMatch}};
      }};

      var result = findAndClick();
      if (result) return result;
      await sleep(200);
      result = findAndClick();
      return result || {{clicked: false, reason: 'submit_not_found_after_retry', sideMatch: sideMatch}};
    }})()
    """
    try:
        result = await tv.evaluate_async(js)
        if result and result.get("clicked"):
            logger.info("Position closed via trading panel: %s", result.get("text"))
            if result.get("sideMatch") == "semantic":
                logger.warning("DOM fallback used on close — TradingView class hash rotated")
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
            # DOM health pre-flight — if TV is in a broken state, don't try to send a
            # close order (would fail with side_not_found or open phantom positions).
            dom_ready, dom_reason = await tv_dom_ready(tv)
            if not dom_ready:
                logger.warning(
                    "close_position(trade %d): TV DOM not ready (reason=%s) — "
                    "skipping chart close, reconciling journal only. "
                    "Reconciliation loop will catch any drift.",
                    trade_id, dom_reason,
                )
            else:
                # Verify there's actually a position to close — guards against the
                # phantom-position bug where a market sell on a flat account opens a
                # fresh short instead of closing.
                has_pos = await _has_open_position(tv)
                if has_pos is False:
                    logger.warning(
                        "close_position(trade %d): TV shows no open position — "
                        "skipping chart close, reconciling journal only",
                        trade_id,
                    )
                else:
                    # Either has position or unclear — send close. Capture toasts to
                    # detect rejection.
                    before_toasts = await _capture_toast_snapshot(tv)
                    await close_via_trading_panel(tv, direction)
                    # Best-effort post-close verification (logs only — don't reopen).
                    outcome_text = await _check_order_outcome(tv, before_toasts, timeout=3.0)
                    if outcome_text in ("rejected_funds", "rejected"):
                        logger.warning(
                            "close_position(trade %d): TV rejected the close order (%s) — "
                            "no phantom position created",
                            trade_id, outcome_text,
                        )
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

    TV's bracket runs to T2 (1.5x ORB). This monitor adds:
      - BE move at T1: once price reaches T1, virtual_stop = entry. If price
        then drifts back through entry, monitor sends a market close.
      - Continuous trail after T1: virtual_stop trails price by 0.5x ORB.
      - VIX intervention: VIX up 20%+ from trade-open VIX -> close.
      - Reconciles TV bracket auto-closes (SL hit, T2 hit) into the journal.
      - Explicit closes for 2-hour time exit and 3pm hard close.
    """
    if not _active_orders:
        return

    now = datetime.now(ET)
    tv = await get_client()
    quote = await tv.get_quote()
    price = quote.get("last") or quote.get("close", 0)
    if price == 0:
        return

    # Fresh structure state for VIX intervention
    structure = read_state("structure") or {}

    for trade_id, order in list(_active_orders.items()):
        direction = order["direction"]
        entry = order["entry"]
        stop = order["stop"]
        t1 = order["target_1"]
        t2 = order["target_2"]
        opened_at = datetime.fromisoformat(order["opened_at"])

        # Hard close — 3 PM normally, 1 PM on half days
        close_h, close_m = get_hard_close_time(now)
        close_time = now.replace(hour=close_h, minute=close_m, second=0)
        if now >= close_time:
            logger.info("%d:%02d hard close for trade %d", close_h, close_m, trade_id)
            await close_position(trade_id, price, f"{close_h}:{close_m:02d} session close")
            continue

        # 2-hour time exit
        minutes_held = (now - opened_at).total_seconds() / 60
        if minutes_held >= MAX_HOLD_MINUTES:
            logger.info("2-hour time exit for trade %d (held %.0f min)", trade_id, minutes_held)
            await close_position(trade_id, price, "2-hour time exit")
            continue

        # VIX intervention — VIX spike since trade open
        vix_now = structure.get("vix")
        vix_at_open = order.get("vix_at_open")
        if vix_now and vix_at_open and vix_now >= vix_at_open * (1 + VIX_INTERVENTION_PCT):
            logger.warning("VIX intervention for trade %d: %.1f -> %.1f (+%.0f%%)",
                           trade_id, vix_at_open, vix_now,
                           (vix_now / vix_at_open - 1) * 100)
            outcome = _outcome_from_pnl(direction, entry, price)
            await close_position(trade_id, price,
                                 f"VIX shock {vix_at_open:.1f}->{vix_now:.1f}",
                                 outcome=outcome)
            continue

        # T1 BE trigger — once price reaches T1, raise virtual stop to entry
        if not order.get("t1_hit"):
            t1_reached = (direction == "LONG" and price >= t1) or \
                         (direction == "SHORT" and price <= t1)
            if t1_reached:
                order["t1_hit"] = True
                order["virtual_stop"] = entry
                _persist_active_orders()
                logger.info("T1 reached for trade %d at %.2f — virtual stop moved to BE %.2f",
                            trade_id, price, entry)
                try:
                    await telegram.notify_be_move(trade_id, direction, entry)
                except Exception as e:
                    logger.warning("Telegram notify_be_move failed: %s", e)

        # Continuous trail after T1 hit — lock in profit as price runs further.
        # trail_distance = TRAIL_DISTANCE_RATIO × ORB range (ORB range = |T2 - T1|).
        if order.get("t1_hit"):
            orb_range = abs(t2 - t1)
            trail_distance = orb_range * TRAIL_DISTANCE_RATIO
            current_vstop = order.get("virtual_stop", entry)
            if direction == "LONG":
                new_vstop = price - trail_distance
                if new_vstop > current_vstop:
                    order["virtual_stop"] = new_vstop
                    _persist_active_orders()
                    logger.info("Trailed stop UP for trade %d: %.2f -> %.2f (price %.2f, locked +%.1f pts)",
                                trade_id, current_vstop, new_vstop, price, new_vstop - entry)
            else:  # SHORT
                new_vstop = price + trail_distance
                if new_vstop < current_vstop:
                    order["virtual_stop"] = new_vstop
                    _persist_active_orders()
                    logger.info("Trailed stop DOWN for trade %d: %.2f -> %.2f (price %.2f, locked +%.1f pts)",
                                trade_id, current_vstop, new_vstop, price, entry - new_vstop)

        # Virtual stop — fires when price drifts back through the (possibly trailed) virtual stop
        if order.get("t1_hit"):
            vstop = order["virtual_stop"]
            be_hit = (direction == "LONG" and price <= vstop) or \
                     (direction == "SHORT" and price >= vstop)
            if be_hit:
                # Determine outcome — trail-stop above entry locks a real win;
                # plain BE stop is scratch (logged as WIN per existing convention).
                locked_pts = (vstop - entry) if direction == "LONG" else (entry - vstop)
                outcome = "WIN"
                reason = "Trail stop after T1" if locked_pts > 0.5 else "BE stop after T1"
                logger.info("Virtual stop for trade %d at %.2f (vstop %.2f, entry %.2f, locked %+.1f pts)",
                            trade_id, price, vstop, entry, locked_pts)
                await close_position(trade_id, vstop, reason, outcome=outcome)
                continue

        # Stop hit — TV bracket auto-closed at original SL. Reconcile (no market order).
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

        # T2 hit — TV bracket auto-closed at T2. Reconcile.
        t2_hit = (direction == "LONG" and price >= t2) or \
                 (direction == "SHORT" and price <= t2)
        if t2_hit:
            logger.info("T2 hit for trade %d at %.2f (TV auto-closed)", trade_id, t2)
            await close_position(trade_id, t2, "T2 target hit",
                                 outcome="WIN", skip_chart_close=True)
            continue


def _outcome_from_pnl(direction: str, entry: float, price: float) -> str:
    """WIN if exit is in trade's favor, else LOSS. Used for early-close interventions."""
    if direction == "LONG":
        return "WIN" if price > entry else "LOSS"
    return "WIN" if price < entry else "LOSS"


def get_active_orders() -> dict:
    """Get currently active orders for status check."""
    return dict(_active_orders)
