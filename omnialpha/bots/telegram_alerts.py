"""Telegram alerts. Uses existing Jarvis bot tokens — falls back to
trading/.env if omnialpha/.env doesn't have its own. Always prefixes
[OmniAlpha] so WeatherAlpha + ORB notifications stay clean.

Sends but never receives. Command-driven control happens through Jarvis
chat (per Zach's no-slash-commands preference).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import dotenv_values

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _resolve_credentials() -> tuple[Optional[str], Optional[str]]:
    """Use omnialpha/.env first, fall back to trading/.env (which already
    has Zach's working ORB Alerts bot token).
    """
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        return TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    fallback_env = Path("C:/ZachAI/trading/.env")
    if fallback_env.exists():
        vals = dotenv_values(fallback_env)
        return (
            vals.get("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN,
            vals.get("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID,
        )
    return TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


PREFIX = "<b>[OmniAlpha]</b> "


def send(text: str, *, parse_mode: str = "HTML") -> bool:
    """Best-effort send. Returns True on success."""
    token, chat_id = _resolve_credentials()
    if not token or not chat_id:
        logger.warning("No Telegram credentials available; skipping send: %s", text[:80])
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": PREFIX + text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload)
            if r.status_code == 200:
                return True
            logger.warning("Telegram send failed %d: %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


def notify_entry(
    *, sector: str, strategy: str, market: str, side: str,
    contracts: int, price_cents: int, stake_usd: float, edge: float,
) -> None:
    side_emoji = "🟢" if side == "yes" else "🔴"
    send(
        f"{side_emoji} <b>Entry</b>: {side.upper()} {contracts}× {market} @{price_cents}c\n"
        f"Stake ${stake_usd:.2f} | Edge {edge:+.2%} | {strategy} ({sector})"
    )


def notify_exit(
    *, sector: str, strategy: str, market: str, side: str,
    pnl_usd: float, won: bool, reason: str,
) -> None:
    icon = "✅" if won else "❌"
    send(
        f"{icon} <b>Exit</b>: {side.upper()} {market}\n"
        f"P&L ${pnl_usd:+.2f} | {reason} | {strategy} ({sector})"
    )


def notify_block(reason: str, detail: str) -> None:
    """Risk-engine refusal or other block — keeps Zach in the loop."""
    send(f"⚠️ <b>Blocked</b>: {reason}\n{detail}")


def notify_daily_summary(
    *, capital_usd: float, day_pnl_usd: float,
    trades_today: int, wins: int, losses: int,
) -> None:
    sign = "+" if day_pnl_usd >= 0 else ""
    wr = wins / max(wins + losses, 1) * 100
    send(
        f"📊 <b>Daily Summary</b>\n"
        f"Capital: ${capital_usd:,.2f}\n"
        f"Today's P&L: {sign}${day_pnl_usd:.2f}\n"
        f"Trades: {trades_today} ({wins}W/{losses}L, {wr:.0f}% WR)"
    )


def notify_error(where: str, exc: BaseException) -> None:
    """Surface unexpected errors. Truncates long stack traces."""
    msg = str(exc)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    send(f"🛑 <b>Error in {where}</b>\n<code>{msg}</code>")


def notify_startup() -> None:
    send("🟢 <b>OmniAlpha online</b> — multi-sector Kalshi bot started")


def notify_halt(reason: str) -> None:
    send(f"🛑 <b>HALTED</b>: {reason}\nNew entries blocked. Resolve before resume.")
