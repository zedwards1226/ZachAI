"""Sweep hunter — read sweep.json, score, gate, execute.

Pipeline per poll:
  1. Read trading/state/sweep.json
  2. Find NEW SWEEP_CONFIRMED events (ts > last_fired_ts)
  3. Qualify (wick size, pool depth)
  4. Score (reuses ORB-style factors + sweep-specific)
  5. Gate (budget, circuit breaker, hard blocks)
  6. Compute levels (entry/stop/t1/t2)
  7. Fire: journal + tv_trader + telegram
  8. Persist last_fired_ts
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz

# Shared trading modules (added to sys.path by main.py)
from services.state_manager import read_state
from services import telegram, tv_trader
from agents import journal, sentinel
from config import (
    TIMEZONE, MULTIPLIER, MAX_CONSECUTIVE_LOSSES,
    VIX_HARD_BLOCK, VIX_SWEET_SPOT_LOW, VIX_SWEET_SPOT_HIGH,
    RVOL_THRESHOLD,
)

# Sweep-bot config
import sb_config as sb

logger = logging.getLogger("sweep_bot.hunter")
ET = pytz.timezone(TIMEZONE)


@dataclass
class SweepSignal:
    direction: str        # "LONG" or "SHORT"
    swept_level: float
    entry: float
    stop: float
    target_1: float
    target_2: float
    wick_points: float
    score: int
    size: str             # "FULL" or "HALF"
    breakdown: dict = field(default_factory=dict)


def _load_state() -> dict:
    if not sb.STATE_FILE.exists():
        return {"last_fired_ts": None, "trades_today": 0, "date": ""}
    try:
        return json.loads(sb.STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"last_fired_ts": None, "trades_today": 0, "date": ""}


def _save_state(state: dict) -> None:
    sb.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    sb.STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _roll_date_if_new(state: dict, now: datetime) -> dict:
    today = now.strftime("%Y-%m-%d")
    if state.get("date") != today:
        state = {"last_fired_ts": None, "trades_today": 0, "date": today}
    return state


def _read_sweep_state() -> dict:
    if not sb.SWEEP_STATE_FILE.exists():
        return {}
    try:
        return json.loads(sb.SWEEP_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _in_session(now: datetime) -> bool:
    start = now.replace(hour=sb.SESSION_START_HOUR, minute=sb.SESSION_START_MINUTE,
                        second=0, microsecond=0)
    end = now.replace(hour=sb.SESSION_END_HOUR, minute=sb.SESSION_END_MINUTE,
                      second=0, microsecond=0)
    return start <= now <= end


def _find_active_pool(sweep_state: dict, level: float) -> Optional[dict]:
    """Return the pool that matches the swept level (if still in active_pools)."""
    for pool in sweep_state.get("active_pools", []):
        if abs(pool.get("level", 0) - level) < 2.0:
            return pool
    return None


def _score_sweep(sweep: dict, structure: dict, memory: dict,
                 sweep_state: dict) -> dict:
    """Score a sweep signal. Returns breakdown dict with 'total' key."""
    b: dict = {}
    direction = "LONG" if sweep["direction"] == "BULLISH" else "SHORT"

    # HTF bias alignment (+2)
    morning_bias = (memory.get("morning_bias") or "").upper()
    if (direction == "LONG" and morning_bias == "LONG") or \
       (direction == "SHORT" and morning_bias == "SHORT"):
        b["htf_bias"] = 2
    elif morning_bias and morning_bias != "NEUTRAL":
        b["bias_conflict"] = -2

    # RVOL (+1)
    rvol = structure.get("rvol") or 0
    if rvol >= RVOL_THRESHOLD:
        b["rvol"] = 1

    # VWAP alignment (+1): long wants price ≥ VWAP, short wants ≤
    vwap = structure.get("vwap")
    close = sweep.get("close") or sweep["level"]
    if vwap:
        if direction == "LONG" and close >= vwap:
            b["vwap_alignment"] = 1
        elif direction == "SHORT" and close <= vwap:
            b["vwap_alignment"] = 1

    # VIX regime (+1 in sweet spot)
    vix = structure.get("vix") or 0
    if VIX_SWEET_SPOT_LOW <= vix <= VIX_SWEET_SPOT_HIGH:
        b["vix_regime"] = 1

    # Prior day direction (+1 if aligned)
    prior = structure.get("prior_day") or {}
    pd_close = prior.get("close")
    pd_open = prior.get("open")
    if pd_close and pd_open:
        pd_dir = "LONG" if pd_close > pd_open else "SHORT"
        if pd_dir == direction:
            b["prior_day_direction"] = 1

    # Sweep-specific: wick strength
    wick = sweep.get("wick_size", 0)
    if wick >= 10.0:
        b["wick_strength"] = 2
    elif wick >= 7.0:
        b["wick_strength"] = 1

    # Pool depth — look up pool bar count
    pool = _find_active_pool(sweep_state, sweep["level"])
    if pool and pool.get("touches", 0) >= 3:
        b["pool_depth"] = 1

    # Nearest-level conflict penalty (approaching opposing wall)
    nearest = structure.get("nearest_level") or {}
    nl_price = nearest.get("price")
    if nl_price and close:
        distance = abs(close - nl_price)
        if distance < 5.0:
            b["at_level"] = -5
        elif distance < 15.0 and nearest.get("direction", "") not in ("", direction.lower()):
            b["approaching_wall"] = -1

    b["total"] = sum(v for k, v in b.items() if k != "total")
    return b


def _hard_blocks(structure: dict) -> Optional[str]:
    vix = structure.get("vix") or 0
    if vix and vix > VIX_HARD_BLOCK:
        return f"VIX {vix:.1f} above {VIX_HARD_BLOCK}"
    blocked, reason = sentinel.is_blocked()
    if blocked:
        return reason
    return None


def _compute_levels(sweep: dict, structure: dict) -> tuple[float, float, float, float]:
    """Return (entry, stop, target_1, target_2)."""
    direction = "LONG" if sweep["direction"] == "BULLISH" else "SHORT"
    level = sweep["level"]
    wick = sweep.get("wick_size", 0)
    atr = structure.get("atr_14") or 10.0
    entry = sweep.get("close") or level
    buffer = wick + sb.STOP_ATR_BUFFER * atr

    if direction == "LONG":
        stop = level - buffer
        risk = entry - stop
        target_1 = entry + risk * sb.TARGET_1_RR
        target_2 = entry + risk * sb.TARGET_2_RR
    else:
        stop = level + buffer
        risk = stop - entry
        target_1 = entry - risk * sb.TARGET_1_RR
        target_2 = entry - risk * sb.TARGET_2_RR

    return round(entry, 2), round(stop, 2), round(target_1, 2), round(target_2, 2)


async def poll_once(dry_run: bool = False) -> Optional[SweepSignal]:
    """One sweep poll. Returns the fired signal if any, else None."""
    now = datetime.now(ET)

    if not _in_session(now):
        return None

    state = _load_state()
    state = _roll_date_if_new(state, now)

    if state["trades_today"] >= sb.MAX_SWEEP_TRADES:
        return None

    # Circuit breaker — shared across ORB + sweep-bot via journal
    today_stats = journal.get_today_stats()
    if today_stats.get("consecutive_losses", 0) >= MAX_CONSECUTIVE_LOSSES:
        return None

    sweep_state = _read_sweep_state()
    sweeps = [s for s in sweep_state.get("sweeps", [])
              if s.get("sweep_type") == "SWEEP_CONFIRMED"]
    if not sweeps:
        return None

    # Latest sweep, newer than last_fired
    latest = sweeps[-1]
    last_ts = state.get("last_fired_ts")
    if last_ts and latest["time"] <= last_ts:
        return None

    # Qualify
    if latest.get("wick_size", 0) < sb.MIN_WICK_POINTS:
        logger.info("Skip: wick %.2f < min %.1f", latest.get("wick_size", 0), sb.MIN_WICK_POINTS)
        return None

    pool = _find_active_pool(sweep_state, latest["level"])
    if pool and pool.get("touches", 0) < sb.MIN_POOL_BARS:
        logger.info("Skip: pool touches %d < min %d", pool.get("touches", 0), sb.MIN_POOL_BARS)
        return None

    # Score
    structure = read_state("structure") or {}
    memory = read_state("memory") or {}
    breakdown = _score_sweep(latest, structure, memory, sweep_state)
    score = breakdown["total"]

    # Hard blocks
    block_reason = _hard_blocks(structure)
    if block_reason:
        logger.info("Hard block: %s", block_reason)
        if not dry_run:
            await telegram.notify_hard_block(block_reason)
            state["last_fired_ts"] = latest["time"]
            _save_state(state)
        return None

    # Gate
    if score < sb.SCORE_FLOOR:
        logger.info("Skip: score %d < floor %d", score, sb.SCORE_FLOOR)
        direction = "LONG" if latest["direction"] == "BULLISH" else "SHORT"
        if not dry_run:
            top_reason = min(
                ((k, v) for k, v in breakdown.items() if k != "total" and v < 0),
                key=lambda x: x[1], default=("low confluence", 0),
            )[0].replace("_", " ")
            await telegram.notify_skip(direction, score, f"sweep: {top_reason}")
            state["last_fired_ts"] = latest["time"]
            _save_state(state)
        return None

    # Compute levels
    entry, stop, t1, t2 = _compute_levels(latest, structure)
    direction = "LONG" if latest["direction"] == "BULLISH" else "SHORT"
    size = "FULL" if score >= sb.SCORE_FULL_SIZE else "HALF"

    signal = SweepSignal(
        direction=direction,
        swept_level=latest["level"],
        entry=entry, stop=stop, target_1=t1, target_2=t2,
        wick_points=latest.get("wick_size", 0),
        score=score, size=size, breakdown=breakdown,
    )

    logger.info("SWEEP SIGNAL: %s score=%d entry=%.2f stop=%.2f t1=%.2f t2=%.2f",
                direction, score, entry, stop, t1, t2)

    if dry_run:
        return signal

    # For telegram notify_trade_entry: orb_high/orb_low doubles as swept level
    # when setup_type="SWEEP_REV" (both get set to the same value).
    swept = latest["level"]

    trade_id = journal.log_trade_open(
        direction=direction, score=score, breakdown=breakdown,
        entry=entry, stop=stop, target_1=t1, target_2=t2,
        size=size, orb_high=swept, orb_low=swept,
        orb_candle_dir="", was_second_break=False,
        vix=structure.get("vix"), rvol=structure.get("rvol"),
        setup_type="SWEEP_REV",
    )

    await telegram.notify_trade_entry(
        direction=direction, score=score, size=size,
        entry=entry, stop=stop, t1=t1, t2=t2,
        breakdown=breakdown,
        orb_high=swept, orb_low=swept,
        setup_type="SWEEP_REV",
    )

    try:
        ok = await tv_trader.place_bracket_order(
            direction=direction, entry_price=entry,
            stop_price=stop, target_1=t1, target_2=t2,
            trade_id=trade_id,
        )
        if not ok:
            journal.mark_failed_placement(trade_id, "sweep-bot bracket order failed")
    except Exception as e:
        logger.exception("Order placement error: %s", e)
        journal.mark_failed_placement(trade_id, f"exception: {e}")

    state["last_fired_ts"] = latest["time"]
    state["trades_today"] = state.get("trades_today", 0) + 1
    _save_state(state)
    return signal
