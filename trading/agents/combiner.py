"""SIGNAL COMBINER — ORB breakout detection + multi-agent scoring engine.

Captures the 15-min ORB range, watches for breakouts, scores using all agent state files,
and decides whether to execute. Places trades via tv_trader and logs to journal.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz

from config import (
    TIMEZONE, ORB_MINUTES, ORB_START_HOUR, ORB_START_MINUTE,
    SESSION_END_HOUR, SESSION_END_MINUTE, MAX_TRADES_PER_SESSION,
    SCORE_FULL_SIZE, SCORE_HALF_SIZE,
    STOP_EXTENSION_MULT, TARGET_1_MULT, TARGET_2_MULT,
    MAX_HOLD_MINUTES, MAX_CONSECUTIVE_LOSSES,
    VIX_HARD_BLOCK, ORB_ATR_MIN_PCT, ORB_ATR_MAX_PCT,  # ATR_MIN now used in cascade gate
    RVOL_THRESHOLD, VIX_SWEET_SPOT_LOW, VIX_SWEET_SPOT_HIGH,
)
from models import (
    Direction, TradeSize, CandleDirection, ScoreBreakdown, ORBRange, Signal,
)
from services.state_manager import read_all_states, read_state, write_state
from services.tv_client import get_client
from services import telegram
from agents import journal

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

# Session state (reset each day)
_orb: Optional[ORBRange] = None
_first_break_direction: Optional[Direction] = None
_first_break_failed: bool = False
_trades_today: int = 0
_session_date: Optional[str] = None
_signals: list[dict] = []
# Tracks whether the current breakout event has already been acted on.
# Prevents re-scoring / re-executing the same breakout every 15s poll while
# price stays outside the ORB range. Reset whenever price returns inside.
_breakout_processed: bool = False


def _persist_session() -> None:
    """Write combiner session state to disk for crash recovery."""
    write_state("combiner_session", {
        "session_date": _session_date,
        "orb": _orb.model_dump() if _orb else None,
        "first_break_direction": _first_break_direction.value if _first_break_direction else None,
        "first_break_failed": _first_break_failed,
        "trades_today": _trades_today,
        "breakout_processed": _breakout_processed,
        "signals": _signals,
    })


def _try_restore_session() -> bool:
    """Restore combiner session from disk if same calendar day. Returns True if restored."""
    global _orb, _first_break_direction, _first_break_failed
    global _trades_today, _session_date, _signals, _breakout_processed

    data = read_state("combiner_session")
    today = datetime.now(ET).strftime("%Y-%m-%d")
    if not data or data.get("session_date") != today:
        return False

    try:
        orb_data = data.get("orb")
        if orb_data:
            _orb = ORBRange(**orb_data)

        fbd = data.get("first_break_direction")
        _first_break_direction = Direction(fbd) if fbd else None
        _first_break_failed = data.get("first_break_failed", False)
        _trades_today = data.get("trades_today", 0)
        _breakout_processed = data.get("breakout_processed", False)
        _signals = data.get("signals", [])
        _session_date = today

        logger.info("Restored combiner session: ORB=%s, trades=%d, breakout_processed=%s",
                     _orb, _trades_today, _breakout_processed)
        return True
    except Exception as e:
        logger.warning("Failed to restore combiner session: %s — resetting", e)
        return False


def _reset_session():
    """Reset session state for a new day."""
    global _orb, _first_break_direction, _first_break_failed
    global _trades_today, _session_date, _signals, _breakout_processed
    _orb = None
    _first_break_direction = None
    _first_break_failed = False
    _trades_today = 0
    _session_date = datetime.now(ET).strftime("%Y-%m-%d")
    _signals = []
    _breakout_processed = False


async def poll() -> Optional[dict]:
    """Called every 15 seconds during session. Handles ORB capture and breakout detection."""
    global _orb, _first_break_direction, _first_break_failed, _trades_today, _session_date
    global _breakout_processed

    now = datetime.now(ET)
    today = now.strftime("%Y-%m-%d")

    # Reset on new day (or restore from disk if same-day restart)
    if _session_date != today:
        if not _try_restore_session():
            _reset_session()

    # Check session window
    session_start = now.replace(hour=ORB_START_HOUR, minute=ORB_START_MINUTE, second=0)
    session_end = now.replace(hour=SESSION_END_HOUR, minute=SESSION_END_MINUTE, second=0)
    if now < session_start or now > session_end:
        return None

    # Check circuit breaker
    stats = journal.get_today_stats()
    if stats["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        return None

    # Check max trades
    if _trades_today >= MAX_TRADES_PER_SESSION:
        return None

    tv = await get_client()

    # --- Phase 1: ORB Capture (9:30 to 9:30 + ORB_MINUTES) ---
    orb_end = session_start + timedelta(minutes=ORB_MINUTES)

    if _orb is None and now >= orb_end:
        # Capture ORB from the first N minutes of candles
        bars = await tv.get_ohlcv(count=50)
        orb_bars = _filter_bars_in_range(bars, session_start, orb_end)

        if not orb_bars:
            logger.warning("No bars found for ORB window")
            return None

        orb_high = max(b["high"] for b in orb_bars)
        orb_low = min(b["low"] for b in orb_bars)
        orb_range = orb_high - orb_low

        # ORB candle direction (strongest predictor: +3)
        first_open = orb_bars[0]["open"]
        last_close = orb_bars[-1]["close"]
        candle_dir = CandleDirection.BULLISH if last_close > first_open else CandleDirection.BEARISH

        _orb = ORBRange(
            high=orb_high, low=orb_low, range=orb_range,
            candle_direction=candle_dir,
            captured_at=now.isoformat(),
        )
        logger.info("ORB captured: H=%.2f L=%.2f range=%.2f dir=%s",
                     orb_high, orb_low, orb_range, candle_dir.value)
        _persist_session()

    if _orb is None:
        return None  # Still in ORB formation window

    # --- Phase 2: Breakout Watch ---
    # Use most recent CLOSED 5-min bar for breakout confirmation (not live tick).
    # Prevents false breakouts from intrabar wicks.
    bars = await tv.get_ohlcv(count=2)
    if not bars:
        return None
    last_closed = bars[-2] if len(bars) >= 2 else bars[-1]
    price = last_closed["close"]

    breakout_direction = None
    if price > _orb.high:
        breakout_direction = Direction.LONG
    elif price < _orb.low:
        breakout_direction = Direction.SHORT

    if breakout_direction is None:
        # Price back inside range — if we had a first break, it failed
        if _first_break_direction is not None and not _first_break_failed:
            _first_break_failed = True
            logger.info("First break FAILED (double break setup forming)")
            _persist_session()
        # Price returned inside range → this breakout event is over.
        # Clear the processed flag so a future break can fire again.
        _breakout_processed = False
        return None

    # Direction flip: price went straight from above OR to below OR (or vice
    # versa) without a bar closing inside the range. Treat as first-break-failed
    # plus a new breakout event so the second-break setup can fire on fast
    # reversals (e.g. 2026-04-23: failed long → hard short leg, missed before fix).
    if (_breakout_processed and _first_break_direction is not None
            and breakout_direction != _first_break_direction):
        if not _first_break_failed:
            _first_break_failed = True
        logger.info(
            "First break FAILED via direction flip (%s → %s) — "
            "price reversed through OR without pausing inside",
            _first_break_direction.value, breakout_direction.value,
        )
        _breakout_processed = False
        _persist_session()

    # If we already acted on this breakout event, don't re-score every 15s.
    # A new decision only happens after price returns inside the range and
    # breaks out again (which resets _breakout_processed above).
    if _breakout_processed:
        return None

    # --- Double break detection ---
    is_second_break = False
    if _first_break_direction is None:
        _first_break_direction = breakout_direction
    elif _first_break_failed and breakout_direction != _first_break_direction:
        is_second_break = True
        logger.info("SECOND BREAK detected: %s (72%% edge)", breakout_direction.value)

    # --- Phase 3: Score the trade ---
    states = read_all_states()
    structure = states.get("structure", {})
    logger.info(
        "SCORING INPUTS: price_location=%s rvol=%s vwap=%s vix=%s bias=%s nearest_level=%s",
        structure.get("price_location"),
        structure.get("rvol"),
        structure.get("vwap"),
        structure.get("vix"),
        states.get("memory", {}).get("morning_bias"),
        structure.get("nearest_level", {}).get("name"),
    )
    breakdown = _score_trade(breakout_direction, is_second_break, states, _orb, price)

    # --- Hard blocks ---
    block_reason = _check_hard_blocks(states, _orb)
    if block_reason:
        logger.info("Hard block: %s", block_reason)
        await telegram.notify_hard_block(block_reason)
        _log_signal(breakout_direction, price, breakdown, TradeSize.SKIP, is_second_break,
                    block_reason=block_reason)
        _breakout_processed = True
        _persist_session()
        return None

    # --- Cascade filter (4 hard gates, no scoring) ---
    # Replaces the old weighted score threshold. Research (Zarattini ORB paper,
    # freqtrade/backtrader conventions) shows production breakout bots use 3-4
    # AND-gated booleans, not confluence scoring. Score/RVOL/VWAP/VIX etc.
    # still recorded to signal_history for later ML-based meta-labeling.
    score = breakdown.total  # kept for logging/metadata only
    gate_failed = _check_cascade(breakout_direction, _orb, states, price, is_second_break)
    if gate_failed:
        logger.info("Trade skipped: %s (gate failed: %s)",
                    breakout_direction.value, gate_failed)
        await telegram.notify_skip(breakout_direction.value, score, gate_failed)
        _log_signal(breakout_direction, price, breakdown, TradeSize.SKIP, is_second_break,
                    block_reason=f"cascade:{gate_failed}")
        _breakout_processed = True
        _persist_session()
        return None

    # All 4 gates passed → HALF size by default (conservative while we gather data).
    # Will promote to FULL once signal_history shows consistent WR >= 55%.
    size = TradeSize.HALF

    # --- Phase 4: Calculate stop/target ---
    orb_range = _orb.range
    if breakout_direction == Direction.LONG:
        stop = _orb.low - (orb_range * (STOP_EXTENSION_MULT - 1))
        target_1 = price + (orb_range * TARGET_1_MULT)
        target_2 = price + (orb_range * TARGET_2_MULT)
    else:
        stop = _orb.high + (orb_range * (STOP_EXTENSION_MULT - 1))
        target_1 = price - (orb_range * TARGET_1_MULT)
        target_2 = price - (orb_range * TARGET_2_MULT)

    risk = abs(price - stop)
    rr = abs(target_1 - price) / risk if risk > 0 else 0

    # --- Phase 5: Execute ---
    structure = states.get("structure", {})
    vix = structure.get("vix")
    rvol = structure.get("rvol")

    signal = Signal(
        time=now.isoformat(),
        direction=breakout_direction,
        breakout_price=round(price, 2),
        score=score,
        size=size,
        breakdown=breakdown,
        entry=round(price, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        risk_reward=round(rr, 2),
        orb=_orb,
        was_second_break=is_second_break,
        vix_at_entry=vix,
        rvol_at_entry=rvol,
    )

    # Log to journal
    trade_id = journal.log_trade_open(
        direction=breakout_direction.value,
        score=score,
        breakdown=breakdown.model_dump(),
        entry=price, stop=stop, target_1=target_1, target_2=target_2,
        size=size.value, orb_high=_orb.high, orb_low=_orb.low,
        orb_candle_dir=_orb.candle_direction.value,
        was_second_break=is_second_break,
        vix=vix, rvol=rvol,
    )

    # Send Telegram alert
    await telegram.notify_trade_entry(
        direction=breakout_direction.value,
        score=score, size=size.value,
        entry=price, stop=stop, t1=target_1, t2=target_2,
        breakdown=breakdown.model_dump(),
        orb_high=_orb.high, orb_low=_orb.low,
    )

    # Place paper trade on TradingView
    try:
        from services.tv_trader import place_bracket_order
        await place_bracket_order(
            direction=breakout_direction.value,
            entry_price=price,
            stop_price=stop,
            target_1=target_1,
            target_2=target_2,
            trade_id=trade_id,
        )
    except ImportError:
        logger.warning("tv_trader not available yet, skipping chart order placement")
    except Exception as e:
        logger.error("Failed to place chart order: %s", e)

    _trades_today += 1
    _breakout_processed = True
    _log_signal(breakout_direction, price, breakdown, size, is_second_break)
    _persist_session()

    logger.info("TRADE EXECUTED: %s score=%d size=%s entry=%.2f stop=%.2f t1=%.2f t2=%.2f",
                breakout_direction.value, score, size.value, price, stop, target_1, target_2)

    return signal.model_dump()


def _score_trade(direction: Direction, is_second_break: bool,
                 states: dict, orb: ORBRange, price: float) -> ScoreBreakdown:
    """Score a trade using all agent state files. Research-calibrated weights."""
    b = ScoreBreakdown()
    structure = states.get("structure", {})
    memory = states.get("memory", {})
    sentinel = states.get("sentinel", {})

    # +3: ORB candle direction aligns (Finding 3: 77-80% accuracy)
    if orb.candle_direction == CandleDirection.BULLISH and direction == Direction.LONG:
        b.orb_candle_direction = 3
        b.details["orb_candle"] = "Bullish ORB candle confirms LONG"
    elif orb.candle_direction == CandleDirection.BEARISH and direction == Direction.SHORT:
        b.orb_candle_direction = 3
        b.details["orb_candle"] = "Bearish ORB candle confirms SHORT"

    # +2: HTF bias aligns
    bias = memory.get("morning_bias", "NEUTRAL")
    if (bias == "BULLISH_BIAS" and direction == Direction.LONG) or \
       (bias == "BEARISH_BIAS" and direction == Direction.SHORT):
        b.htf_bias = 2
        b.details["htf_bias"] = f"{bias} confirms {direction.value}"
    elif bias != "NEUTRAL" and \
         ((bias == "BULLISH_BIAS" and direction == Direction.SHORT) or
          (bias == "BEARISH_BIAS" and direction == Direction.LONG)):
        b.bias_conflict = -2
        b.details["bias_conflict"] = f"{bias} conflicts with {direction.value}"

    # +2: Second break after double break (Finding 1: 72.2% win rate)
    if is_second_break:
        b.second_break = 2
        b.details["second_break"] = "Second break after failed first (72% edge)"

    # +1: Structure OPEN_AIR — recomputed against breakout price AND trade direction.
    # Only levels in front of the trade count as obstacles; levels already broken
    # through (behind the trade) are ignored. Fixes ORB breakouts getting vetoed
    # for "sitting at level" when the level is the very one the trade just cleared.
    from agents.structure import recompute_price_location
    price_loc_enum, nearest = recompute_price_location(price, structure, direction.value)
    price_loc = price_loc_enum.value
    if price_loc == "OPEN_AIR":
        b.open_air = 1
        b.details["open_air"] = f"No obstacle level within 20 pts (nearest ahead: {nearest.name})"
    elif price_loc == "APPROACHING_WALL":
        b.approaching_wall = -1
        b.details["approaching_wall"] = f"Near {nearest.name} ({nearest.distance_pts:.1f}pts ahead)"
    elif price_loc == "AT_LEVEL":
        b.at_level = -5
        b.details["at_level"] = f"At {nearest.name} ahead — no room to target"

    # +1: RVOL > 1.5 (Finding 6)
    rvol = structure.get("rvol")
    if rvol and rvol >= RVOL_THRESHOLD:
        b.rvol = 1
        b.details["rvol"] = f"RVOL {rvol:.1f}x (above {RVOL_THRESHOLD})"

    # +1: VWAP alignment
    vwap = structure.get("vwap")
    if vwap:
        if (direction == Direction.LONG and price > vwap) or \
           (direction == Direction.SHORT and price < vwap):
            b.vwap_alignment = 1
            b.details["vwap"] = f"Price {'above' if price > vwap else 'below'} VWAP ({vwap:.2f})"

    # +1: VIX sweet spot (Finding 7)
    vix = structure.get("vix", 0)
    if vix and VIX_SWEET_SPOT_LOW <= vix <= VIX_SWEET_SPOT_HIGH:
        b.vix_regime = 1
        b.details["vix"] = f"VIX {vix:.1f} in sweet spot ({VIX_SWEET_SPOT_LOW}-{VIX_SWEET_SPOT_HIGH})"

    # +1: Prior day closed in direction
    pd = structure.get("prior_day", {})
    pd_close = pd.get("close", 0)
    pd_open = pd.get("high", 0) - (pd.get("range", 0) / 2)  # Approximate open
    if pd_close and pd_open:
        if (direction == Direction.LONG and pd_close > pd_open) or \
           (direction == Direction.SHORT and pd_close < pd_open):
            b.prior_day_direction = 1
            b.details["prior_day"] = "Prior day closed in trade direction"

    # News/Truth scoring removed — headlines are informational only now.
    # Sentinel still forwards high-impact headlines to Telegram for awareness.
    b.no_news_block = 1
    b.no_truth_block = 1

    b.compute_total()
    return b


def _check_cascade(direction: Direction, orb: ORBRange,
                   states: dict, price: float,
                   is_second_break: bool = False) -> Optional[str]:
    """Hard entry filter. Returns None if all gates pass, else the failing gate name.

    Gate 1: ORB candle direction matches trade direction (tradingstats.net 2026: 77-80% edge).
    Gate 2: VWAP alignment — long requires price above VWAP, short below (mainstream filter).
    Gate 3: ATR floor — ORB range must be at least ORB_ATR_MIN_PCT of ATR_14 (Zarattini ~0.30).

    HTF bias and level proximity are NOT hard gates — they're soft signals that flow
    into ScoreBreakdown only (still recorded for ML labeling). Removed as hard skips
    after data review showed they killed 2/7 signals over 90 days with no published
    edge backing them (Zarattini paper uses zero filters beyond box close).

    Second-break exception: Gate 1 is a direction filter that assumes the first
    break is the right read. Confirmed second breaks (Zarattini 72% edge) waive
    Gate 1 only — VWAP and ATR are regime filters and always apply.
    """
    if not is_second_break:
        # Gate 1 — ORB candle direction (kept: 77-80% data-backed edge)
        if direction == Direction.LONG and orb.candle_direction != CandleDirection.BULLISH:
            return "orb_candle_wrong_direction"
        if direction == Direction.SHORT and orb.candle_direction != CandleDirection.BEARISH:
            return "orb_candle_wrong_direction"

    structure = states.get("structure", {})

    # Gate 2 — VWAP alignment (skipped if VWAP not yet populated)
    vwap = structure.get("vwap")
    if vwap is not None:
        if direction == Direction.LONG and price < vwap:
            return f"below_vwap_long:{price:.2f}<{vwap:.2f}"
        if direction == Direction.SHORT and price > vwap:
            return f"above_vwap_short:{price:.2f}>{vwap:.2f}"

    # Gate 3 — ATR floor (skip if ORB range too tight to be tradeable)
    atr = structure.get("atr_14", 0)
    if atr and orb.range > 0:
        ratio = orb.range / atr
        if ratio < ORB_ATR_MIN_PCT:
            return f"orb_range_too_tight:{ratio:.0%}<{ORB_ATR_MIN_PCT:.0%}"

    return None


def _check_hard_blocks(states: dict, orb: ORBRange) -> Optional[str]:
    """Check for hard blocks that prevent any trading regardless of score."""
    structure = states.get("structure", {})
    sentinel = states.get("sentinel", {})

    # VIX > 30
    vix = structure.get("vix", 0)
    if vix and vix > VIX_HARD_BLOCK:
        return f"VIX {vix:.1f} above {VIX_HARD_BLOCK} hard block"

    # FOMC/CPI/NFP day — hard block entire day (Finding 8: news days destroy ORB)
    for event in sentinel.get("economic_events", []):
        if event.get("impact") == "HIGH" and event.get("within_session_window"):
            event_name = event.get("event", "").upper()
            if any(kw in event_name for kw in ("CPI", "NFP", "NON-FARM", "FOMC", "FED")):
                return f"High-impact news day: {event.get('event')} — no ORB trades"

    # ORB range ATR filter — disabled (informational only, does not block trades)
    # atr = structure.get("atr_14", 0)
    # if atr and orb.range > 0:
    #     ratio = orb.range / atr
    #     if ratio < ORB_ATR_MIN_PCT:
    #         return f"ORB range too narrow ({ratio:.0%} of ATR, min {ORB_ATR_MIN_PCT:.0%})"
    #     if ratio > ORB_ATR_MAX_PCT:
    #         return f"ORB range too wide ({ratio:.0%} of ATR, max {ORB_ATR_MAX_PCT:.0%})"

    return None


def _filter_bars_in_range(bars: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Filter bars that fall within a time range."""
    result = []
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    for bar in bars:
        # Bar timestamps from TradingView are in seconds
        bar_ts = bar["time"]
        # Handle TradingView's date-only timestamps (daily bars use date at midnight)
        if bar_ts < 1e10:
            bar_ts = bar_ts  # Already seconds
        elif bar_ts > 1e12:
            bar_ts = bar_ts / 1000  # Milliseconds to seconds
        if start_ts <= bar_ts <= end_ts:
            result.append(bar)
    return result


def _log_signal(direction: Direction, price: float, breakdown: ScoreBreakdown,
                size: TradeSize, is_second_break: bool,
                block_reason: Optional[str] = None):
    """Log signal to signal_log.json (session) + journal.db signal_history (30-day)."""
    global _signals
    _signals.append({
        "time": datetime.now(ET).isoformat(),
        "direction": direction.value,
        "price": round(price, 2),
        "score": breakdown.total,
        "size": size.value,
        "was_second_break": is_second_break,
        "block_reason": block_reason,
        "breakdown": breakdown.model_dump(),
    })

    data = {
        "date": datetime.now(ET).strftime("%Y-%m-%d"),
        "orb": _orb.model_dump() if _orb else None,
        "signals": _signals,
        "session_stats": {
            "trades_taken": _trades_today,
            "max_trades": MAX_TRADES_PER_SESSION,
        },
    }
    write_state("signal_log", data)

    try:
        journal.log_signal_history(
            direction=direction.value,
            price=round(price, 2),
            score=breakdown.total,
            size=size.value,
            breakdown=breakdown.model_dump(),
            was_second_break=is_second_break,
            block_reason=block_reason,
        )
    except Exception as e:
        logger.error("Failed to persist signal_history: %s", e)
