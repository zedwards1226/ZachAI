"""Setup scanner — runs every monitor tick during active killzones.

Reads recent MES bars + HTF bias, dispatches to each strategy module, logs any
detected setup to SQLite, fires Telegram, and (in trade mode) calls the trader.

Phase 1 = NY AM FVG only.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import pytz

from config import (
    TIMEZONE, ICT_SYMBOL, ICT_TIMEFRAME, HTF_TIMEFRAME, SCAN_ONLY,
    is_high_impact_today,
)
from services import tv_data
from services.tv_data import fetch_recent_bars, htf_bias as compute_htf_bias
from data_layer.database import insert_setup, append_journal
from strategies import ny_am_fvg

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# Track which setup IDs we've already pinged Telegram about so we don't spam
_pinged_setups: set[int] = set()


def _today_iso() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def scan_once(telegram_send=None, trader_place=None) -> dict | None:
    """Single scan tick. Returns the detected setup dict (or None).

    `telegram_send`: callable(text:str)->None — set by caller (or None to skip)
    `trader_place`: callable(plan:dict)->dict — set by caller (or None for SCAN_ONLY)
    """
    high_impact, event = is_high_impact_today(_today_iso())
    if high_impact:
        logger.info("scan skipped: high-impact day (%s)", event)
        return None

    bars = fetch_recent_bars(ICT_SYMBOL, timeframe=ICT_TIMEFRAME, count=100)
    if len(bars) < 30:
        logger.warning("not enough bars (%d) — skipping scan", len(bars))
        return None

    bias = compute_htf_bias(ICT_SYMBOL)
    plan = ny_am_fvg.evaluate(bars, htf_bias=bias)
    if plan is None:
        return None

    # Persist as setup
    setup_row = {
        "detected_time": datetime.now(ET).isoformat(),
        "setup_name": plan["setup_name"],
        "symbol": plan["symbol"],
        "timeframe": plan["timeframe"],
        "bias": plan["side"],
        "entry_zone_low": plan["fvg_low"],
        "entry_zone_high": plan["fvg_high"],
        "stop_price": plan["stop"],
        "target_price": plan["target"],
        "rr": plan["rr"],
        "confidence": _confidence_score(plan),
        "triggered": 0,
        "invalidated": 0,
        "payload": json.dumps(plan, default=str),
    }
    setup_id = insert_setup(setup_row)
    plan["setup_id"] = setup_id

    # Fire Telegram once per setup_id
    if telegram_send and setup_id not in _pinged_setups:
        msg = (
            f"setup detected: {plan['setup_name']} {plan['side']} "
            f"@ {plan['entry']}, SL {plan['stop']}, TP {plan['target']}, "
            f"R:R {plan['rr']} (HTF {plan['htf_bias']})"
        )
        try:
            telegram_send(msg)
            _pinged_setups.add(setup_id)
        except Exception as exc:
            logger.warning("telegram send failed: %s", exc)

    append_journal("scanner", "info", f"setup_id={setup_id} {plan['side']} {plan['symbol']}",
                   payload=json.dumps(plan, default=str))

    # Trade execution gated on SCAN_ONLY + injected trader
    if SCAN_ONLY:
        logger.info("SCAN_ONLY=true — not placing trade for setup_id=%s", setup_id)
        return plan

    if trader_place is None:
        logger.warning("SCAN_ONLY=false but no trader_place provided — skipping")
        return plan

    try:
        result = trader_place(plan)
        logger.info("trade placement result: %s", result)
    except Exception as exc:
        logger.error("trade placement failed: %s", exc)
        append_journal("scanner", "error", f"trade placement failed: {exc}")

    return plan


def _confidence_score(plan: dict) -> int:
    """Crude 0-100 score combining R:R, displacement, and bias alignment.

    Used purely for ranking + dashboard display; does not gate entry.
    """
    score = 50
    if plan["rr"] >= 2.0:
        score += 15
    elif plan["rr"] >= 1.5:
        score += 8
    if plan["displacement_pts"] >= 8:
        score += 10
    elif plan["displacement_pts"] >= 5:
        score += 5
    if plan["htf_bias"] in ("long", "short"):
        score += 10
    return max(0, min(100, score))
