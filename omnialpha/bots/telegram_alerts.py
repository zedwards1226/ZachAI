"""Telegram alerts. Uses existing Jarvis bot tokens — falls back to
trading/.env if omnialpha/.env doesn't have its own. Always prefixes
[OmniAlpha] so WeatherAlpha + ORB notifications stay clean.

Sends but never receives. Command-driven control happens through Jarvis
chat (per Zach's no-slash-commands preference).

Anti-spam:
  - notify_error throttles identical errors to once per 30 min — if the
    same problem keeps happening every scan cycle, you get 1 message,
    not 60/hour.
  - notify_startup is rate-limited to 1 per hour so a rapid restart
    loop (e.g. crash + auto-restart) can't spam.
  - notify_entry / notify_exit fire once per actual trade event, no
    dedupe needed (status flips prevent re-notification).
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx
from dotenv import dotenv_values

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

# In-process dedupe cache: {key_hash: last_sent_unix_ts}.
# Reset on bot restart, which is the right scope — a fresh start should
# re-surface a still-broken state once.
_LAST_SENT: dict[str, float] = {}
_ERROR_THROTTLE_SECONDS = 30 * 60          # 30 min between identical errors
_STARTUP_THROTTLE_SECONDS = 60 * 60        # 1 hour between startup pings


def _should_send(key: str, throttle_seconds: float) -> bool:
    """Return True if `key` hasn't been sent in the last `throttle_seconds`."""
    now = time.time()
    last = _LAST_SENT.get(key)
    if last is not None and (now - last) < throttle_seconds:
        return False
    _LAST_SENT[key] = now
    return True


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
    """Surface unexpected errors. Throttled per (where, exc-type, msg)
    tuple so a persistent issue can't spam every scan cycle.

    First occurrence: sent immediately.
    Subsequent occurrences within 30 min of the same error: suppressed
    (logged at INFO so we know it's still happening but Telegram stays
    clean).
    """
    msg = str(exc)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    # Hash the dedupe key so it stays short + handles weird characters.
    key = "err:" + hashlib.sha1(
        f"{where}|{type(exc).__name__}|{msg}".encode("utf-8", errors="replace")
    ).hexdigest()
    if not _should_send(key, _ERROR_THROTTLE_SECONDS):
        logger.info("notify_error throttled (still happening): %s — %s", where, msg[:100])
        return
    send(f"🛑 <b>Error in {where}</b>\n<code>{msg}</code>")


_STARTUP_THROTTLE_FILE = Path("C:/ZachAI/omnialpha/state/.telegram_startup_throttle")


def notify_startup() -> None:
    """Sent on bot start. Rate-limited to 1/hour ACROSS process restarts
    via a sidecar timestamp file — so a crash-restart loop or a manual
    restart sequence can't spam.

    In-process throttle wouldn't help here (each new process has an
    empty cache); the file persists across restarts.
    """
    now = time.time()
    try:
        if _STARTUP_THROTTLE_FILE.exists():
            last = float(_STARTUP_THROTTLE_FILE.read_text().strip() or "0")
            if (now - last) < _STARTUP_THROTTLE_SECONDS:
                logger.info("notify_startup throttled (recent restart, %.0fs ago)", now - last)
                return
    except Exception as e:
        logger.warning("startup throttle file read failed: %s — sending anyway", e)
    try:
        _STARTUP_THROTTLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STARTUP_THROTTLE_FILE.write_text(str(now))
    except Exception as e:
        logger.warning("startup throttle file write failed: %s", e)
    send("🟢 <b>OmniAlpha online</b> — multi-sector Kalshi bot started")


def notify_halt(reason: str) -> None:
    send(f"🛑 <b>HALTED</b>: {reason}\nNew entries blocked. Resolve before resume.")
