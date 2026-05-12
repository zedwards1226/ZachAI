"""Morning Preflight Agent.

Two entry points:

`run()` — 7:00 AM ET informational brief. Runs every check (CDP, symbol,
broker, calendar, disk, journal, quote) and sends a PASS/FAIL Telegram.
Situational awareness only; does NOT gate trading.

`run_arm_check()` — 9:25 AM ET arm gate. Runs ONLY the 3 hard at-open
checks (CDP/symbol, broker connected, DOM ready) and writes
`state/arm_status.json`. The combiner reads that file on every poll and
short-circuits if `armed=false` so it doesn't waste attempts at the open
when the chart is in a broken state. Soft checks (calendar/disk/journal)
are recorded as warnings but never block arming. Manual override path:
Jarvis writes `arm_status.json` with `source="manual"` when Zach asks
"arm orb anyway" after eyeballing.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

import pytz

from config import DEFAULT_SYMBOL, JOURNAL_DB, TIMEZONE
from services import telegram
from services.state_manager import write_state
from services.tv_client import get_client

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# 2026 High-impact calendar (from CLAUDE.md)
CPI_DATES = {"2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10", "2026-05-12",
             "2026-06-10", "2026-07-14", "2026-08-12", "2026-09-11", "2026-10-14",
             "2026-11-10", "2026-12-10"}
NFP_DATES = {"2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03", "2026-05-08",
             "2026-06-05", "2026-07-02", "2026-08-07", "2026-09-04", "2026-10-02",
             "2026-11-06", "2026-12-04"}
FOMC_DATES = {"2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
              "2026-09-16", "2026-10-28", "2026-12-09"}


async def _check_cdp_and_symbol() -> tuple[bool, str]:
    try:
        tv = await get_client()
        symbol = await tv.get_symbol()
        if symbol != DEFAULT_SYMBOL:
            return False, f"CDP symbol is {symbol}, expected {DEFAULT_SYMBOL}"
        return True, f"CDP locked on {symbol}"
    except Exception as e:
        return False, f"CDP check failed: {e}"


async def _check_quote() -> tuple[bool, str]:
    try:
        tv = await get_client()
        q = await tv.get_quote()
        price = q.get("last") or q.get("close", 0)
        if price > 0:
            return True, f"Quote pull OK — last={price}"
        return False, "Quote pull returned 0"
    except Exception as e:
        return False, f"Quote pull failed: {e}"


async def _check_paper_broker() -> tuple[bool, str]:
    """Verify Paper Trading broker session is connected.

    Strategy (order of precedence, simplest wins):
    1. If broker-picker modal ("Trade with your broker" / "Need a broker?")
       is visible anywhere on the page → disconnected, fail loud.
    2. If Buy/Sell side elements (buy-OnZ1FRe5 / sell-OnZ1FRe5 with width>50)
       are already visible → panel is open and broker is connected.
    3. Otherwise, open the Order Panel via the top-right Trade button and
       re-check. If still no side elements and still no picker, assume the
       panel layout changed and return an informational state (not fail).

    We intentionally do NOT depend on count-before vs count-after — that
    toggles the panel, which can close a panel the user intentionally
    had open and causes false negatives when the panel was already open.
    """
    try:
        tv = await get_client()
        js = """
        (async function() {
          var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };

          var pickerVisible = function() {
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
              var txt = (all[i].textContent || '').trim();
              if (txt === 'Trade with your broker' || txt === 'Need a broker?') {
                var r = all[i].getBoundingClientRect();
                if (r.width > 50 && r.height > 20) return true;
              }
            }
            return false;
          };

          var sideVisible = function() {
            var buys = document.querySelectorAll('[class*="buy-OnZ1FRe5"]');
            for (var i = 0; i < buys.length; i++) {
              var r = buys[i].getBoundingClientRect();
              if (r.width > 50) return true;
            }
            return false;
          };

          // 1. Picker modal already up? Disconnected.
          if (pickerVisible()) return {ok: false, state: 'picker_visible'};

          // 2. Panel already open with side elements? Connected.
          if (sideVisible()) return {ok: true, state: 'panel_already_open'};

          // 3. Try opening the panel.
          var btns = document.querySelectorAll('button');
          var tradeBtn = null;
          for (var i = 0; i < btns.length; i++) {
            var t = (btns[i].textContent || '').trim();
            var r = btns[i].getBoundingClientRect();
            if (t === 'Trade' && r.y < 50 && r.x > 1000) { tradeBtn = btns[i]; break; }
          }
          if (!tradeBtn) return {ok: false, state: 'trade_button_not_found'};

          tradeBtn.click();
          await sleep(500);

          if (pickerVisible()) {
            // Close modal if possible, then report
            tradeBtn.click();
            return {ok: false, state: 'picker_appeared_after_click'};
          }
          if (sideVisible()) {
            // Restore: click again to close what we opened
            tradeBtn.click();
            return {ok: true, state: 'opened_and_verified'};
          }
          // Neither side elements nor picker — unknown layout.
          tradeBtn.click();
          return {ok: false, state: 'no_side_no_picker'};
        })()
        """
        result = await tv.evaluate_async(js) or {}
        state = result.get("state", "unknown")
        if result.get("ok"):
            return True, f"Paper Trading broker connected ({state})"
        if state in ("picker_visible", "picker_appeared_after_click"):
            return False, "❗ Paper Trading DISCONNECTED — reconnect before open"
        if state == "trade_button_not_found":
            return False, "Trade button not found — TV layout changed or chart not loaded"
        if state == "no_side_no_picker":
            # Inconclusive — don't fail preflight on this alone since it
            # commonly happens after hours when Order panel stays hidden.
            return True, "Broker state inconclusive (no picker) — OK for preflight"
        return False, f"Broker check failed: state={state}"
    except Exception as e:
        return False, f"Broker check error: {e}"


async def _reconnect_paper_broker() -> tuple[bool, str]:
    """Click the 'Paper Trading' tile in the broker-picker modal to restore
    the Trading Panel session. Used by run_broker_watch in main.py to auto-recover
    from overnight broker disconnects (the 2026-05-11 morning incident).

    The CDP JS literal here is the same one Claude executed manually at
    8:50 AM ET on 2026-05-11 — proven to work against TV Desktop 3.1.0.7818.

    Strategy: walk up from the 'Paper Trading' text node to find the clickable
    card container (width > 150, height > 150) and click it. Then sleep 1.5s
    for TV to render the panel, and re-check broker state to confirm recovery.
    """
    try:
        tv = await get_client()
        click_js = """
        (function() {
          var target = null;
          var all = document.querySelectorAll('*');
          for (var i = 0; i < all.length; i++) {
            if (target) break;
            var el = all[i];
            if (el.children.length > 0) continue;
            var t = (el.textContent || '').trim();
            if (t === 'Paper Trading') {
              var cur = el;
              for (var j = 0; j < 6; j++) {
                if (!cur) break;
                var r = cur.getBoundingClientRect();
                if (r.width > 150 && r.height > 150) { target = cur; break; }
                cur = cur.parentElement;
              }
            }
          }
          if (!target) return {clicked: false, reason: 'paper_trading_tile_not_found'};
          target.click();
          return {clicked: true};
        })()
        """
        click_result = await tv.evaluate_async(click_js) or {}
        if not click_result.get("clicked"):
            reason = click_result.get("reason", "unknown")
            return False, f"Could not click Paper Trading tile: {reason}"

        # Wait for TV to re-render the trading panel
        await asyncio.sleep(1.5)

        # Re-check to confirm reconnect succeeded
        ok, msg = await _check_paper_broker()
        if ok:
            return True, f"Reconnected ({msg})"
        return False, f"Reconnect clicked but check still fails: {msg}"
    except Exception as e:
        return False, f"Reconnect error: {e}"


def _check_calendar() -> tuple[bool, str]:
    today = datetime.now(ET).strftime("%Y-%m-%d")
    events = []
    if today in CPI_DATES:
        events.append("CPI 8:30 AM")
    if today in NFP_DATES:
        events.append("NFP 8:30 AM")
    if today in FOMC_DATES:
        events.append("FOMC 2:00 PM")
    if events:
        return True, f"⚠️ High-impact today: {', '.join(events)}"
    return True, "No high-impact events today"


def _check_disk() -> tuple[bool, str]:
    try:
        total, used, free = shutil.disk_usage("C:\\")
        free_gb = free / 1e9
        if free_gb < 5:
            return False, f"Low disk: {free_gb:.1f} GB free on C:"
        return True, f"Disk OK: {free_gb:.0f} GB free"
    except Exception as e:
        return False, f"Disk check failed: {e}"


def _check_journal_db() -> tuple[bool, str]:
    if not JOURNAL_DB.exists():
        return False, "journal.db missing"
    size_mb = JOURNAL_DB.stat().st_size / 1e6
    return True, f"journal.db {size_mb:.1f} MB"


async def _check_dom_ready() -> tuple[bool, str]:
    """Mirror the per-placement DOM probe from tv_trader.tv_dom_ready so the
    arm gate catches the same `dom_not_ready:paper_trading_not_active` state
    that produced the 5/4 cluster failures BEFORE the bot starts polling,
    not after it logs three FAILED_PLACEMENT rows."""
    try:
        from services.tv_trader import tv_dom_ready
        tv = await get_client()
        ready, reason = await tv_dom_ready(tv)
        if ready:
            return True, "DOM ready, paper trading active"
        return False, f"DOM not ready: {reason}"
    except Exception as e:
        return False, f"DOM check error: {e}"


async def run_arm_check() -> dict:
    """9:25 AM arm gate. Runs the 3 HARD checks only and writes
    `state/arm_status.json`. Returns the same dict it wrote.

    `armed=true` only if CDP/symbol AND broker AND DOM/paper all pass.
    Soft checks (calendar/disk/journal) are recorded as warnings — they
    never affect `armed`.

    Sends a Telegram alert ONLY if armed=false (situational alert; the
    7 AM informational brief covers the green-arm case).
    """
    logger.info("Arm check starting (9:25 gate)")

    # Hard checks — these gate arming
    cdp_ok, cdp_msg = await _check_cdp_and_symbol()
    broker_ok, broker_msg = await _check_paper_broker()
    dom_ok, dom_msg = await _check_dom_ready()

    # Soft checks — informational only, do not gate
    calendar_ok, calendar_msg = _check_calendar()
    disk_ok, disk_msg = _check_disk()
    journal_ok, journal_msg = _check_journal_db()

    armed = cdp_ok and broker_ok and dom_ok
    now = datetime.now(ET)

    # Build a short blocker line for the Telegram
    failing = []
    if not cdp_ok:    failing.append(f"CDP/symbol: {cdp_msg}")
    if not broker_ok: failing.append(f"broker: {broker_msg}")
    if not dom_ok:    failing.append(f"DOM/paper: {dom_msg}")
    blocker = " | ".join(failing) if failing else None

    status = {
        "date": now.strftime("%Y-%m-%d"),
        "armed": armed,
        "source": "preflight",
        "checks": {
            "cdp_symbol": {"ok": cdp_ok,    "msg": cdp_msg},
            "broker":     {"ok": broker_ok, "msg": broker_msg},
            "dom_paper":  {"ok": dom_ok,    "msg": dom_msg},
        },
        "warnings": {
            "calendar": calendar_msg if not calendar_ok else None,
            "disk":     disk_msg     if not disk_ok     else None,
            "journal":  journal_msg  if not journal_ok  else None,
        },
        "armed_at": now.isoformat(),
        "blocker": blocker,
    }

    write_state("arm_status", status)
    logger.info("Arm check complete: armed=%s, blocker=%s", armed, blocker)

    if not armed:
        try:
            await telegram.notify_arm_blocked(status)
        except Exception as e:
            logger.warning("notify_arm_blocked failed: %s", e)

    return status


async def run() -> None:
    """Execute preflight and send Telegram brief."""
    logger.info("Morning preflight starting")

    calendar_ok, calendar_msg = _check_calendar()
    disk_ok, disk_msg = _check_disk()
    journal_ok, journal_msg = _check_journal_db()
    cdp_ok, cdp_msg = await _check_cdp_and_symbol()
    quote_ok, quote_msg = await _check_quote()
    broker_ok, broker_msg = await _check_paper_broker()

    checks = [
        ("CDP/symbol", cdp_ok, cdp_msg),
        ("quote pull", quote_ok, quote_msg),
        ("paper broker", broker_ok, broker_msg),
        ("calendar", calendar_ok, calendar_msg),
        ("disk space", disk_ok, disk_msg),
        ("journal DB", journal_ok, journal_msg),
    ]

    all_ok = all(ok for _, ok, _ in checks)
    now = datetime.now(ET).strftime("%H:%M %Z")

    lines = [
        f"{'🟢' if all_ok else '🟡'} <b>Morning Preflight</b> — {now}",
        "",
    ]
    for name, ok, msg in checks:
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} {name}: {msg}")
    lines.append("")
    lines.append("Open: 9:30 AM ET" if all_ok else "⚠️ Fix failed checks before open")

    brief = "\n".join(lines)
    await telegram.send(brief)
    logger.info("Preflight complete — all_ok=%s", all_ok)
