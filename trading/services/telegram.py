"""Async Telegram notification service for ORB Trading System.

All trading notifications go to the dedicated ORB Alerts bot.
Jarvis bot (telegram-bridge/bot.py) is separate — commands only.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10)
    return _client


async def send(text: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message to the ORB Alerts chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }
    try:
        resp = await _get_client().post(url, json=payload)
        if resp.status_code != 200:
            logger.error("Telegram send failed: %d %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.error("Telegram send error: %s", e)
        return False


async def notify_briefing(text: str) -> bool:
    """Send the morning briefing report."""
    return await send(text)


async def notify_trade_entry(direction: str, score: int, size: str,
                             entry: float, stop: float, t1: float, t2: float,
                             breakdown: dict) -> bool:
    """Send trade entry notification with full score breakdown."""
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

    pos_text = "\n".join(f"  +{v} {k}" for k, v in positives[:3]) or "  (none)"
    neg_text = "\n".join(f"  {v} {k}" for k, v in negatives[:3]) or "  (none)"

    rr = abs(t1 - entry) / abs(entry - stop) if abs(entry - stop) > 0 else 0

    msg = (
        f"🔔 <b>ORB TRADE — {direction}</b>\n\n"
        f"Score: <b>{score}</b> → {size}\n"
        f"Entry: {entry:.2f}\n"
        f"Stop: {stop:.2f}\n"
        f"T1: {t1:.2f} | T2: {t2:.2f}\n"
        f"R:R = {rr:.1f}\n\n"
        f"<b>Top reasons FOR:</b>\n{pos_text}\n\n"
        f"<b>Top reasons AGAINST:</b>\n{neg_text}"
    )
    return await send(msg)


async def notify_trade_exit(direction: str, entry: float, exit_price: float,
                            pnl: float, pnl_after_slip: float,
                            outcome: str, rr: float) -> bool:
    """Send trade exit notification."""
    emoji = "✅" if outcome == "WIN" else "❌" if outcome == "LOSS" else "➖"
    msg = (
        f"{emoji} <b>TRADE CLOSED — {direction}</b>\n\n"
        f"Entry: {entry:.2f} → Exit: {exit_price:.2f}\n"
        f"P&L: ${pnl:.2f} (after slip: ${pnl_after_slip:.2f})\n"
        f"Outcome: {outcome} | RR: {rr:.1f}"
    )
    return await send(msg)


async def notify_skip(direction: str, score: int, reason: str) -> bool:
    """Send notification when a trade is skipped."""
    msg = (
        f"⏭️ <b>ORB SKIP — {direction}</b>\n\n"
        f"Score: {score} (below threshold)\n"
        f"Reason: {reason}"
    )
    return await send(msg)


async def notify_hard_block(reason: str) -> bool:
    """Send notification when trading is hard-blocked."""
    msg = f"🚫 <b>HARD BLOCK</b>\n\n{reason}"
    return await send(msg)


async def notify_circuit_breaker(losses: int, daily_pnl: float) -> bool:
    """Send circuit breaker alert."""
    msg = (
        f"⚠️ <b>CIRCUIT BREAKER</b>\n\n"
        f"Consecutive losses: {losses}\n"
        f"Daily P&L: ${daily_pnl:.2f}\n"
        f"Trading paused for the day."
    )
    return await send(msg)


async def notify_sentinel_alert(alert_type: str, details: str) -> bool:
    """Send sentinel alert (news/truth social)."""
    msg = f"🚨 <b>SENTINEL — {alert_type}</b>\n\n{details}"
    return await send(msg)


async def notify_sweep(direction: str, level: float, sweep_type: str) -> bool:
    """Send sweep detection alert."""
    msg = (
        f"🌊 <b>SWEEP DETECTED</b>\n\n"
        f"Type: {sweep_type}\n"
        f"Level: {level:.2f}\n"
        f"Direction: {direction}"
    )
    return await send(msg)


async def notify_weekly_report(report_text: str) -> bool:
    """Send the Sunday weekly journal report."""
    return await send(f"📈 <b>WEEKLY ORB REPORT</b>\n\n{report_text}")


async def notify_strategy_review(rolling_wr: float, weeks: int) -> bool:
    """Send alert when rolling win rate drops below threshold."""
    msg = (
        f"⚠️ <b>STRATEGY REVIEW NEEDED</b>\n\n"
        f"Rolling 20-trade win rate: {rolling_wr:.0%}\n"
        f"Below 40% for {weeks} consecutive weeks.\n"
        f"Consider re-evaluating parameters."
    )
    return await send(msg)
