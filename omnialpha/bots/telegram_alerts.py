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

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PAPER_MODE
from bots.strategy_labels import label_strategy

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


def _market_metadata(ticker: str) -> dict:
    """Look up human-readable market context: underlying asset, strike,
    direction, close time. Returns {} on failure — alert still sends,
    just without the plain-English bits.
    """
    from data_layer.database import get_conn
    try:
        with get_conn(readonly=True) as conn:
            row = conn.execute(
                "SELECT title, strike_type, floor_strike, cap_strike, close_time, series_ticker "
                "FROM markets WHERE ticker = ?",
                (ticker,),
            ).fetchone()
    except Exception as e:
        logger.warning("market metadata lookup failed for %s: %s", ticker, e)
        return {}
    return dict(row) if row else {}


def _underlying_label(series_ticker: str) -> str:
    """Map Kalshi series ticker to plain-English asset name."""
    if "BTC" in (series_ticker or ""):
        return "BTC"
    if "ETH" in (series_ticker or ""):
        return "ETH"
    return series_ticker or "the market"


def _format_strike(meta: dict) -> str:
    """Build '≥ $78,500' / '≤ $78,500' / '$78,500' depending on strike type."""
    strike = meta.get("floor_strike") or meta.get("cap_strike")
    if strike is None:
        return ""
    s_type = meta.get("strike_type", "")
    if s_type in ("greater", "greater_or_equal"):
        op = "≥"
    elif s_type in ("less", "less_or_equal"):
        op = "≤"
    else:
        op = ""
    return f"{op} ${strike:,.0f}".strip()


def _format_close_local(close_time_iso: str) -> str:
    """Convert ISO UTC close time to America/New_York for display.
    Cross-platform — `%-I` (no leading zero) is Linux-only; we use `%I`
    and strip the leading zero in Python so Windows agrees."""
    if not close_time_iso:
        return ""
    try:
        from datetime import datetime
        import pytz
        dt = datetime.fromisoformat(close_time_iso.replace("Z", "+00:00"))
        et = dt.astimezone(pytz.timezone("America/New_York"))
        # %I gives 01-12 (zero-padded); lstrip('0') makes "01:30 PM" -> "1:30 PM"
        return et.strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return close_time_iso[:16].replace("T", " ") + " UTC"


def notify_entry(
    *, sector: str, strategy: str, market: str, side: str,
    contracts: int, price_cents: int, stake_usd: float, edge: float,
) -> None:
    """Plain-English entry alert. Tells you WHAT was bought and WHAT
    outcome we're betting on."""
    side_emoji = "🟢" if side == "yes" else "🔴"
    payout_usd = contracts * 1.00          # binary contracts pay $1 each on win
    profit_usd = payout_usd - stake_usd
    profit_pct = (profit_usd / stake_usd * 100) if stake_usd > 0 else 0

    meta = _market_metadata(market)
    asset = _underlying_label(meta.get("series_ticker") or market.split("-")[0])
    strike = _format_strike(meta)
    close_at = _format_close_local(meta.get("close_time", ""))

    if strike and close_at:
        # YES = we want condition to happen; NO = we want it to NOT happen
        if side == "yes":
            hope = f"<i>Hoping: {asset} {strike} by {close_at}</i>"
        else:
            # Invert the operator for NO bets
            inverted = strike.replace("≥", "&lt;").replace("≤", "&gt;")
            hope = f"<i>Hoping: {asset} {inverted} by {close_at}</i>"
    else:
        hope = ""

    msg = (
        f"{side_emoji} <b>Trade placed</b>\n"
        f"Bought {contracts}× {side.upper()} on {asset} @ {price_cents}¢\n"
        f"Stake ${stake_usd:.2f} → Pays ${payout_usd:.2f} if we win ({profit_pct:+.0f}%)\n"
    )
    if hope:
        msg += f"\n{hope}\n"
    msg += f"\n<i>{label_strategy(strategy)} · edge {edge:+.1%}</i>"
    send(msg)


def notify_exit(
    *, sector: str, strategy: str, market: str, side: str,
    pnl_usd: float, won: bool, reason: str,
) -> None:
    """Plain-English exit alert. Tells you WIN or LOSE and WHY in
    underlying-asset terms."""
    icon = "✅" if won else "❌"
    word = "WON" if won else "LOST"

    meta = _market_metadata(market)
    asset = _underlying_label(meta.get("series_ticker") or market.split("-")[0])
    strike = _format_strike(meta)

    # Build the "what happened" line in plain English
    if strike:
        if won:
            # We bet YES + got YES, OR bet NO + got NO
            if side == "yes":
                outcome = f"{asset} closed {strike} → {side.upper()} paid out"
            else:
                inv = strike.replace("≥", "&lt;").replace("≤", "&gt;")
                outcome = f"{asset} closed {inv} → {side.upper()} paid out"
        else:
            if side == "yes":
                outcome = f"{asset} did NOT close {strike} → {side.upper()} expired worthless"
            else:
                inv = strike.replace("≥", "&lt;").replace("≤", "&gt;")
                outcome = f"{asset} did NOT close {inv} → {side.upper()} expired worthless"
    else:
        outcome = f"{side.upper()} bet resolved"

    msg = (
        f"{icon} <b>{word} ${abs(pnl_usd):.2f}</b>\n"
        f"{outcome}\n"
        f"\n<i>{label_strategy(strategy)}</i>"
    )
    send(msg)


def notify_block(reason: str, detail: str) -> None:
    """Risk-engine refusal or other block — keeps Zach in the loop."""
    send(
        f"⚠️ <b>Skipped a trade</b>\n"
        f"The risk engine blocked it: {reason}\n"
        f"<i>{detail}</i>"
    )


def _today_breakdown_by_strategy() -> list[tuple[str, int, float]]:
    """Per-strategy trade count + realized P&L for today (settled trades only).
    Returns list of (strategy_name, n_trades, pnl_usd) sorted by abs(pnl) desc.
    Failures return [] — caller handles missing-section gracefully.
    """
    from datetime import datetime
    from data_layer.database import get_conn
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        with get_conn(readonly=True) as conn:
            rows = conn.execute(
                "SELECT strategy, COUNT(*) AS n, "
                "       COALESCE(SUM(CASE WHEN status IN ('won','lost') THEN pnl_usd END), 0) AS pnl "
                "FROM trades WHERE substr(timestamp, 1, 10) = ? "
                "GROUP BY strategy ORDER BY ABS(pnl) DESC",
                (today,),
            ).fetchall()
        return [(r["strategy"], int(r["n"]), float(r["pnl"] or 0)) for r in rows]
    except Exception as e:
        logger.warning("daily breakdown lookup failed: %s", e)
        return []


def _open_positions_now() -> tuple[int, float]:
    """(open_count, unrealized_total). Unrealized = stake on open trades —
    we don't mark-to-market here, just surface the at-risk amount."""
    from data_layer.database import get_conn
    try:
        with get_conn(readonly=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(stake_usd), 0) AS at_risk "
                "FROM trades WHERE status = 'open'"
            ).fetchone()
        return int(row["n"] or 0), float(row["at_risk"] or 0)
    except Exception as e:
        logger.warning("open positions lookup failed: %s", e)
        return 0, 0.0


def notify_daily_summary(
    *, capital_usd: float, day_pnl_usd: float,
    trades_today: int, wins: int, losses: int,
) -> None:
    """End-of-day narrative digest, WeatherAlpha-style — full sentences,
    per-strategy breakdown, current at-risk capital. No bare-numbers wall."""
    mode_text = (
        "paper trading (no real money on the line)"
        if PAPER_MODE else "LIVE TRADING (real money)"
    )
    pnl_word = "profit" if day_pnl_usd >= 0 else "loss"
    pnl_amt = f"${abs(day_pnl_usd):.2f}"
    wr = (wins / (wins + losses) * 100) if (wins + losses) else 0

    if trades_today == 0:
        trade_line = "No trades placed today — markets didn't line up with our bands."
    else:
        trade_line = (
            f"Today's {pnl_word}: <b>{pnl_amt}</b> from {trades_today} trade"
            f"{'s' if trades_today != 1 else ''} "
            f"({wins} win{'s' if wins != 1 else ''}, "
            f"{losses} loss{'es' if losses != 1 else ''}, {wr:.0f}% win rate)"
        )

    lines = [
        "🌙 <b>End of day — OmniAlpha</b>",
        "<i>Here's how today landed.</i>",
        "",
        f"<b>Trading mode:</b> {mode_text}",
        f"<b>Account balance:</b> ${capital_usd:,.2f}",
        "",
        trade_line,
    ]

    breakdown = _today_breakdown_by_strategy()
    if breakdown:
        lines.append("")
        lines.append("<b>By strategy today:</b>")
        for name, n, pnl in breakdown:
            sign = "+" if pnl >= 0 else "−"
            lines.append(
                f"  • {label_strategy(name)}: {n} trade{'s' if n != 1 else ''}, "
                f"{sign}${abs(pnl):.2f}"
            )

    open_n, at_risk = _open_positions_now()
    lines.append("")
    if open_n == 0:
        lines.append("<b>Right now:</b> no positions open.")
    else:
        lines.append(
            f"<b>Right now:</b> holding {open_n} position"
            f"{'s' if open_n != 1 else ''}, "
            f"${at_risk:.2f} at risk "
            f"<i>(P&L locks in once each market resolves)</i>"
        )

    send("\n".join(lines))


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
    mode_text = "paper trading" if PAPER_MODE else "LIVE trading"
    send(
        f"🟢 <b>OmniAlpha is online</b>\n"
        f"The multi-sector Kalshi bot just started up "
        f"({mode_text}). I'll watch the markets and let you know when "
        f"trades fire."
    )


def notify_halt(reason: str) -> None:
    send(
        f"🛑 <b>OmniAlpha halted</b>\n"
        f"I've stopped placing new trades. Reason: {reason}\n"
        f"<i>Existing positions are still open and being tracked. "
        f"Trading resumes once the issue is fixed.</i>"
    )
