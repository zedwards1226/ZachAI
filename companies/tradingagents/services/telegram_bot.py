"""
Telegram notification service for TradingAgents.
Sends trade alerts, agent verdicts, and EOD summaries.
Uses direct HTTP API (no polling bot needed — we only send, never receive).
"""
import logging
import httpx

import config

log = logging.getLogger("telegram")

_client = httpx.AsyncClient(timeout=10)


def _enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


async def send(text: str, parse_mode: str = None) -> bool:
    """Send a message to the configured Telegram chat. Returns True on success."""
    if not _enabled():
        log.debug("Telegram not configured, skipping notification")
        return False
    try:
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = await _client.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
        )
        if resp.status_code != 200:
            log.error("Telegram send failed: %d %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as e:
        log.error("Telegram send error: %s", e)
        return False


async def notify_entry(side: str, symbol: str, price: float, qty: int,
                       multiplier: float, strategy: str, verdict: str,
                       reasoning: str, trade_id: int):
    """Notify on trade entry."""
    emoji = "\U0001f4c8" if side == "BUY" else "\U0001f4c9"
    msg = (
        f"{emoji} TRADE OPENED #{trade_id}\n"
        f"{side} {symbol} @ {price:,.2f} (x{qty})\n"
        f"${multiplier}/pt | {strategy}\n"
        f"Overseer: {verdict} — {reasoning}"
    )
    await send(msg)


async def notify_close(side: str, symbol: str, entry: float, exit_price: float,
                       pnl: float, pts: float, multiplier: float, trade_id: int,
                       summary: dict):
    """Notify on trade close."""
    emoji = "\u2705" if pnl > 0 else "\u274c"
    sign = "+" if pnl > 0 else ""
    msg = (
        f"{emoji} TRADE CLOSED #{trade_id}\n"
        f"{side} {symbol}: {entry:,.2f} \u2192 {exit_price:,.2f}\n"
        f"P&L: {sign}${pnl:,.2f} ({sign}{pts:.2f} pts \u00d7 ${multiplier})\n"
        f"Total: ${summary['total_pnl']:,.2f} | {summary['win_rate']:.1f}% WR | {summary['total_trades']} trades"
    )
    await send(msg)


async def notify_block(symbol: str, action: str, price: float, reasoning: str):
    """Notify when Overseer blocks a trade."""
    msg = (
        f"\U0001f6ab BLOCKED\n"
        f"{action.upper()} {symbol} @ {price:,.2f}\n"
        f"Reason: {reasoning}"
    )
    await send(msg)


async def notify_agent_warning(agent: str, symbol: str, message: str):
    """Background agent warning (Sentinel, Sweep, Context)."""
    msg = (
        f"\u26a0\ufe0f {agent.upper()} WARNING\n"
        f"{symbol}: {message}"
    )
    await send(msg)


async def notify_eod_summary(summary: dict, analysis: str = ""):
    """End-of-day summary from Analyst agent."""
    msg = (
        f"\U0001f4ca EOD SUMMARY\n"
        f"Trades: {summary['total_trades']} | W/L: {summary['wins']}/{summary['losses']}\n"
        f"P&L: ${summary['total_pnl']:,.2f} | Win rate: {summary['win_rate']:.1f}%\n"
        f"Open: {summary['open_trades']}"
    )
    if analysis:
        msg += f"\n\n{analysis}"
    await send(msg)
