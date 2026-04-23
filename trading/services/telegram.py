"""Async Telegram notification service for ORB Trading System.

All trading notifications go to the dedicated ORB Alerts bot.
Jarvis bot (telegram-bridge/bot.py) is separate — commands only.

Message style: plain English, no abbreviations on first use, always explain
WHY an alert is firing so Zach doesn't have to decode it from his phone.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None

# MNQ contract: $2 per point. Used to convert price moves into dollars in
# the message text so Zach sees "$50 risk" instead of "1.0 R:R".
MNQ_POINT_VALUE = 2.00


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10)
    return _client


async def send(text: str, parse_mode: str = "HTML", max_retries: int = 3) -> bool:
    """Send a Telegram message with exponential backoff retry."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }

    delay = 1.0
    for attempt in range(max_retries):
        try:
            resp = await _get_client().post(url, json=payload)
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:  # Rate limited
                retry_after = int(resp.headers.get("Retry-After", delay))
                logger.warning("Telegram rate limited, retrying in %ds", retry_after)
                await asyncio.sleep(retry_after)
                delay = retry_after * 2
                continue
            logger.error("Telegram send failed (attempt %d/%d): %d %s",
                         attempt + 1, max_retries, resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("Telegram send error (attempt %d/%d): %s",
                         attempt + 1, max_retries, e)

        if attempt < max_retries - 1:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    return False


async def notify_briefing(text: str) -> bool:
    """Send the morning briefing report."""
    return await send(text)


async def notify_trade_entry(direction: str, score: int, size: str,
                             entry: float, stop: float, t1: float, t2: float,
                             breakdown: dict,
                             orb_high: float, orb_low: float,
                             setup_type: str = "ORB") -> bool:
    """Send trade entry notification with full score breakdown.

    Plain-English version: spells out targets, converts risk/reward into
    dollars, lists the top 3 reasons we took the trade and the top 3 reasons
    against. Direction comes in as 'LONG' or 'SHORT'.
    """
    # Sort breakdown into reasons-for and reasons-against
    positives = []
    negatives = []
    for key, val in breakdown.items():
        if key in ("total", "details"):
            continue
        if val > 0:
            positives.append((key, val))
        elif val < 0:
            negatives.append((key, val))
    positives.sort(key=lambda x: x[1], reverse=True)
    negatives.sort(key=lambda x: x[1])

    pos_text = "\n".join(f"  • {k.replace('_', ' ')} (+{v})" for k, v in positives[:3]) or "  (none)"
    neg_text = "\n".join(f"  • {k.replace('_', ' ')} ({v})" for k, v in negatives[:3]) or "  (none)"

    # Risk vs reward in dollars (MNQ = $2/point)
    risk_pts = abs(entry - stop)
    reward_pts = abs(t1 - entry)
    risk_dollars = risk_pts * MNQ_POINT_VALUE
    reward_dollars = reward_pts * MNQ_POINT_VALUE
    rr = reward_pts / risk_pts if risk_pts > 0 else 0

    direction_word = "buying" if direction == "LONG" else "selling short"
    arrow = "📈" if direction == "LONG" else "📉"

    if setup_type == "SWEEP_REV":
        swept_level = orb_high if direction == "LONG" else orb_low
        margin = abs(entry - swept_level)
        level_ref = f"Swept level ({swept_level:.2f})"
    elif direction == "LONG":
        margin = entry - orb_high
        level_ref = f"ORB high ({orb_high:.2f})"
        direction_text = "above"
    else:
        margin = orb_low - entry
        level_ref = f"ORB low ({orb_low:.2f})"
        direction_text = "below"
    if margin < 3.0:
        margin_label = "MARGINAL"
    elif margin <= 10.0:
        margin_label = "CLEAN"
    else:
        margin_label = "STRONG"

    if setup_type == "SWEEP_REV":
        headline = f"🌊 <b>NEW SWEEP-REVERSAL TRADE — {direction_word.upper()}</b>"
        level_line = f"{level_ref} — reversed by {margin:.2f} pts — <b>{margin_label}</b>"
    else:
        headline = f"{arrow} <b>NEW TRADE — {direction_word.upper()}</b>"
        level_line = f"Broke {direction_text} {level_ref} by {margin:.2f} pts — <b>{margin_label}</b>"

    msg = (
        f"{headline}\n\n"
        f"<b>Confidence score:</b> {score}/10 → {size} position\n"
        f"<i>(higher score = stronger setup; size scales with score)</i>\n\n"
        f"{level_line}\n\n"
        f"<b>The plan:</b>\n"
        f"  Entry price: {entry:.2f}\n"
        f"  Stop loss: {stop:.2f}  (if hit, we lose ${risk_dollars:.0f})\n"
        f"  First exit (close half): {t1:.2f}  (if hit, we make ${reward_dollars:.0f} on that half)\n"
        f"  Final exit (close rest): {t2:.2f}\n"
        f"  Risking ${risk_dollars:.0f} to make ${reward_dollars:.0f} on first target ({rr:.1f}x)\n\n"
        f"<b>Why we took it:</b>\n{pos_text}\n\n"
        f"<b>What's working against us:</b>\n{neg_text}"
    )
    return await send(msg)


async def notify_trade_exit(direction: str, entry: float, exit_price: float,
                            pnl: float, pnl_after_slip: float,
                            outcome: str, rr: float) -> bool:
    """Send trade exit notification in plain English."""
    if outcome == "WIN":
        emoji = "✅"
        outcome_word = "WIN"
        result_phrase = f"made ${pnl_after_slip:.2f}"
    elif outcome == "LOSS":
        emoji = "❌"
        outcome_word = "LOSS"
        result_phrase = f"lost ${abs(pnl_after_slip):.2f}"
    else:
        emoji = "➖"
        outcome_word = "BREAKEVEN"
        result_phrase = f"closed flat (${pnl_after_slip:+.2f})"

    direction_word = "long" if direction == "LONG" else "short"
    move_pts = (exit_price - entry) if direction == "LONG" else (entry - exit_price)

    # Slippage = the difference between theoretical pnl and actual after slippage
    slippage_cost = pnl - pnl_after_slip

    msg = (
        f"{emoji} <b>TRADE CLOSED — {outcome_word}</b>\n\n"
        f"Direction: {direction_word}\n"
        f"Entered at {entry:.2f}, exited at {exit_price:.2f} ({move_pts:+.2f} points)\n"
        f"Result: {result_phrase}\n"
        f"Reward-to-risk ratio: {rr:.1f}x  "
        f"<i>(how much we made compared to what we risked)</i>\n"
        f"Slippage cost: ${slippage_cost:.2f}"
    )
    return await send(msg)


async def notify_skip(direction: str, score: int, reason: str) -> bool:
    """Send notification when a trade is skipped by a cascade gate.

    The system uses 3 hard AND-gates (ORB candle, HTF bias, level proximity),
    not a score threshold. Skip means ONE gate failed; score is kept for
    context only.
    """
    direction_word = "long" if direction == "LONG" else "short"
    gate_name = reason.replace("cascade:", "").replace("_", " ")
    msg = (
        f"⏭️ <b>SKIPPED A {direction_word.upper()} SETUP</b>\n\n"
        f"A safety gate blocked the trade: <b>{gate_name}</b>\n"
        f"<i>(score {score}/10, kept for review — not the reason for skipping)</i>\n\n"
        f"<i>No trade placed. Watching for the next setup.</i>"
    )
    return await send(msg)


async def notify_hard_block(reason: str) -> bool:
    """Send notification when trading is hard-blocked (won't take any trades)."""
    msg = (
        f"🚫 <b>TRADING BLOCKED</b>\n\n"
        f"Not taking any new trades right now.\n\n"
        f"<b>Reason:</b> {reason}\n\n"
        f"<i>Block clears automatically when the condition resolves.</i>"
    )
    return await send(msg)


async def notify_circuit_breaker(losses: int, daily_pnl: float) -> bool:
    """Send circuit breaker alert — too many losses, stopping for the day."""
    msg = (
        f"⚠️ <b>STOPPING TRADING FOR TODAY</b>\n\n"
        f"We've hit {losses} losses in a row.\n"
        f"Today's profit/loss: ${daily_pnl:+.2f}\n\n"
        f"Circuit breaker tripped — no more trades until tomorrow.\n"
        f"<i>This protects us from revenge trading after a bad streak.</i>"
    )
    return await send(msg)


async def notify_sentinel_alert(alert_type: str, details: str) -> bool:
    """Send sentinel alert — news or social media event that may move markets."""
    msg = (
        f"🚨 <b>MARKET-MOVING NEWS DETECTED</b>\n\n"
        f"<b>Type:</b> {alert_type}\n"
        f"<b>Details:</b> {details}\n\n"
        f"<i>Heads up — this could shake things up. The bot may pause or "
        f"tighten stops depending on the rules.</i>"
    )
    return await send(msg)


async def notify_sweep(direction: str, level: float, sweep_type: str) -> bool:
    """Send liquidity sweep / genuine-break alert.

    direction is "BULLISH" or "BEARISH" (from sweep.py), which describes the
    trade setup direction implied by the event — NOT the direction price moved.
    A BEARISH sweep means bulls got trapped above, price reversed down, bias
    is short. A BULLISH break means price broke up and held, bias is long.
    """
    is_break = "GENUINE_BREAK" in sweep_type or "BATCH" in sweep_type
    action = "broke through and held" if is_break else "ran the stops and reversed"
    trade_side = "LONG" if direction == "BULLISH" else "SHORT"
    flow = (
        "smart money pushing higher" if direction == "BULLISH"
        else "smart money distributing"
    )
    msg = (
        f"🌊 <b>LIQUIDITY SWEEP</b>\n\n"
        f"Price {action} at <b>{level:.2f}</b> ({sweep_type}).\n"
        f"This is a <b>{direction.lower()}</b> signal — {flow}.\n\n"
        f"<i>Watching for a {trade_side} setup.</i>"
    )
    return await send(msg)


async def notify_weekly_report(report_text: str) -> bool:
    """Send the Sunday weekly journal report."""
    return await send(f"📈 <b>WEEKLY TRADING REPORT</b>\n\n{report_text}")


async def notify_strategy_review(rolling_wr: float, weeks: int) -> bool:
    """Send alert when rolling win rate drops below threshold."""
    msg = (
        f"⚠️ <b>STRATEGY MAY NEED A REVIEW</b>\n\n"
        f"Win rate over the last 20 trades: <b>{rolling_wr:.0%}</b>\n"
        f"It's been below 40% for {weeks} weeks in a row.\n\n"
        f"<i>The strategy might be drifting. Time to look at recent trades "
        f"and decide if anything needs adjusting (parameters, filters, or "
        f"pausing live trading until conditions change).</i>"
    )
    return await send(msg)


async def close() -> None:
    """Close the httpx client on shutdown."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
