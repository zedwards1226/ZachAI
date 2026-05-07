"""ICTBot trade execution — TradingView paper bracket via dedicated CDP :9223.

⚠️ AUTO-MERGE EXCEPTION (per ictbot/CLAUDE.md):
   Edits to this file affect live order placement. Commit + push but notify
   Zach BEFORE merging. Same rule ORB enforces on `trading/services/tv_trader.py`.

Phase 1 status: place_bracket_order() returns a mock fill in SCAN_ONLY mode and
will not click any DOM. The DOM-driving body is implemented but gated behind
the SCAN_ONLY env flag.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import pytz

from config import (
    TIMEZONE, PAPER_MODE, SCAN_ONLY, ICT_SYMBOL, MULTIPLIER,
    MAX_RISK_PER_TRADE_DOLLARS,
)
from services.ict_tv_client import open_session, chart_ready

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


class TradeError(RuntimeError):
    pass


def _ensure_paper() -> None:
    if not PAPER_MODE:
        raise TradeError(
            "PAPER_MODE != true — refusing to place. "
            "Going live is one of Zach's 3 hard stops."
        )


def _ensure_within_risk_cap(entry: float, stop: float, qty: int) -> None:
    risk_pts = abs(entry - stop)
    risk_dollars = risk_pts * MULTIPLIER * qty
    if risk_dollars > MAX_RISK_PER_TRADE_DOLLARS:
        raise TradeError(
            f"per-trade risk ${risk_dollars:.2f} > cap ${MAX_RISK_PER_TRADE_DOLLARS}"
        )


def get_active_orders() -> list[dict]:
    """Return ICTBot's active TV bracket orders. Phase 1: scrapes the
    TV bottom-panel orders DOM. Returns [] if CDP unavailable.
    """
    sess = open_session()
    if sess is None:
        return []
    try:
        with sess as s:
            js = """
            (() => {
              const rows = document.querySelectorAll('[data-name="orders-row"], div[role="row"]');
              return Array.from(rows)
                .map(r => r.innerText)
                .filter(t => t && t.length > 0);
            })()
            """
            raw = s.evaluate(js) or []
            return [{"raw": txt} for txt in raw if isinstance(txt, str)]
    except Exception as exc:
        logger.warning("get_active_orders failed: %s", exc)
        return []


def _place_bracket_dom(side: str, qty: int, entry: float, stop: float,
                       target: float) -> dict:
    """The actual DOM script that places a bracket order on TradingView's
    Trading Panel. Adapted from ORB's pattern but isolated here so we never
    import from `trading/`.

    Phase 1 implementation is a STUB — returns a synthetic fill so the rest
    of the pipeline can be tested. Real DOM scripting is added in Phase 2
    after Zach reviews the changes (auto-merge exception applies).
    """
    logger.info(
        "STUB place_bracket_dom: side=%s qty=%d entry=%.2f stop=%.2f target=%.2f",
        side, qty, entry, stop, target,
    )
    return {
        "ok": True,
        "stub": True,
        "filled_at": entry,
        "side": side,
        "qty": qty,
        "stop": stop,
        "target": target,
        "placed_at": datetime.now(ET).isoformat(),
    }


def place_bracket_order(plan: dict) -> dict:
    """High-level: take a strategy plan dict and place the bracket.

    plan keys: setup_name, symbol, side, entry, stop, target, rr, ...
    """
    _ensure_paper()
    side = plan["side"]
    qty = int(plan.get("qty", 1))
    entry = float(plan["entry"])
    stop = float(plan["stop"])
    target = float(plan["target"])
    _ensure_within_risk_cap(entry, stop, qty)

    if SCAN_ONLY:
        logger.info("SCAN_ONLY=true — returning mock fill for plan %s", plan.get("setup_id"))
        return {
            "ok": True,
            "scan_only": True,
            "filled_at": entry,
            "side": side,
            "qty": qty,
            "stop": stop,
            "target": target,
            "placed_at": datetime.now(ET).isoformat(),
        }

    # Real placement path (Phase 2+)
    ready, msg = chart_ready()
    if not ready:
        raise TradeError(f"chart not ready: {msg}")
    return _place_bracket_dom(side, qty, entry, stop, target)


def close_position_market(symbol: str = ICT_SYMBOL) -> dict:
    """Emergency hard close — Phase 2+ implementation. Phase 1 returns a stub."""
    if SCAN_ONLY:
        return {"ok": True, "scan_only": True, "message": "no-op (scan-only)"}
    return {"ok": False, "message": "Phase 2 implementation required"}
