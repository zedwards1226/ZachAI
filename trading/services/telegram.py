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

# Plain-English labels for score-breakdown keys (used in trade-entry "Why
# we took it" / "Working against us" sections) and skip/block reasons.
# Internal log lines and DB rows keep the raw codenames; only outbound
# Telegram text gets translated. Missing keys fall back to underscore-
# replacement and a logger.warning so we catch any new gates.
_SCORE_KEY_PHRASE: dict[str, str] = {
    "orb_candle_direction": "opening range candle agrees with the breakout direction",
    "htf_bias":             "higher-timeframe bias supports the trade",
    "bias_conflict":        "higher-timeframe bias disagrees with the trade",
    "second_break":         "this is a second-attempt breakout (after a failed first try — strong edge)",
    "open_air":             "no major level in the way for at least 20 points",
    "approaching_wall":     "price is too close to a major level — limited room",
    "at_level":             "price is sitting right on a key level — choppy zone",
    "rvol":                 "trading volume is above average",
    "vwap_alignment":       "price is on the right side of VWAP",
    "vix_regime":           "volatility (VIX) is in the bot's sweet spot",
    "prior_day_direction":  "yesterday closed in the same direction",
    "no_news_block":        "no news block active (clear to trade)",
    "no_truth_block":       "no market-moving social media block (clear to trade)",
    "news_block":           "news block active (high-impact event nearby)",
    "truth_block":          "market-moving news block active",
}


def _score_label(key: str) -> str:
    if key in _SCORE_KEY_PHRASE:
        return _SCORE_KEY_PHRASE[key]
    logger.warning("No plain-English label for score key %r — falling back", key)
    return key.replace("_", " ")


def _humanize_skip_reason(raw: str) -> str:
    """Translate the cascade/skip reason string into a sentence Zach can read.
    Recognized patterns:
      - "risk_too_wide:$540>350"  → "the stop would risk $540, above the $350-per-trade cap"
      - "cascade:htf_bias_conflict" → "higher-timeframe bias disagrees with the trade"
      - bare key   → underscore-replaced fallback (logged as warning)
    """
    if raw.startswith("risk_too_wide:"):
        # format is risk_too_wide:$NNN>MMM
        try:
            tail = raw.split(":", 1)[1]
            risk_part, cap_part = tail.split(">", 1)
            return (
                f"the stop would risk {risk_part}, above the ${cap_part}-per-trade cap"
            )
        except Exception:
            return "the stop is too wide for our per-trade risk cap"
    if raw.startswith("cascade:"):
        key = raw[len("cascade:"):]
        return _SCORE_KEY_PHRASE.get(key, key.replace("_", " "))
    return _SCORE_KEY_PHRASE.get(raw, raw.replace("_", " "))


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

    pos_text = "\n".join(f"  • {_score_label(k)} (+{v})" for k, v in positives[:3]) or "  (none)"
    neg_text = "\n".join(f"  • {_score_label(k)} ({v})" for k, v in negatives[:3]) or "  (none)"

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
    direction_word = "buy" if direction == "LONG" else "short-sell"
    plain_reason = _humanize_skip_reason(reason)
    msg = (
        f"⏭️ <b>Skipped a {direction_word} setup</b>\n\n"
        f"A safety check blocked the trade: <b>{plain_reason}</b>.\n"
        f"<i>(Confidence score was {score}/10 — recorded for review, but the "
        f"safety check is what stopped us, not the score.)</i>\n\n"
        f"<i>No trade placed. Bot is watching for the next setup.</i>"
    )
    return await send(msg)


async def notify_be_move(trade_id: int, direction: str, entry: float) -> bool:
    """Notify that VIRTUAL stop has moved to breakeven after T1 reached.

    NOTE (2026-05-19): chart-side bracket SL is NOT moved yet — Phase 2 of the
    overhaul will add CDP drag of the chart line. Until then the chart shows
    the original SL and the BE is enforced purely by the Python monitor's
    virtual_stop fire (which sends a market close if price drifts back to entry).
    """
    direction_word = "long" if direction == "LONG" else "short"
    msg = (
        f"🎯 <b>First target hit — virtual stop tightened to BE</b>\n\n"
        f"Trade #{trade_id} ({direction_word}) reached its first target.\n"
        f"Virtual safety stop now sits at entry <b>{entry:.2f}</b>.\n\n"
        f"<i>Chart bracket SL is unchanged — the Python monitor will market-close "
        f"if price drifts back through entry. Phase 2 will move the chart line too.</i>"
    )
    return await send(msg)


async def notify_daily_lock(target_or_stop: str, daily_pnl: float, action: str) -> bool:
    """Notify when the daily P&L hit the +$200 target or -$200 stop.

    target_or_stop: 'TARGET' or 'STOP'
    action: human description of what was done (e.g. 'Runner closed at $215')
    """
    icon = "💰" if target_or_stop == "TARGET" else "🛑"
    label = "Daily target +$200 hit" if target_or_stop == "TARGET" else "Daily stop -$200 hit"
    msg = (
        f"{icon} <b>{label}</b>\n\n"
        f"Today's P&L: <b>${daily_pnl:+.2f}</b>\n"
        f"{action}\n\n"
        f"<i>Trading locked for the day. Resets at tomorrow's open.</i>"
    )
    return await send(msg)


async def notify_mfe_giveback(trade_id: int, direction: str, mfe_r: float,
                              mfe_price: float, exit_price: float) -> bool:
    """Notify when the runner was force-closed because price gave back 50% of MFE.

    Fires after the trade has captured at least +1R then retraced through the
    50% giveback band — protects against winners turning into losers.
    """
    direction_word = "long" if direction == "LONG" else "short"
    msg = (
        f"⏬ <b>Runner closed — gave back half the profit</b>\n\n"
        f"Trade #{trade_id} ({direction_word}) peaked at +{mfe_r:.1f}R "
        f"(price <b>{mfe_price:.2f}</b>) then retraced 50%.\n"
        f"Bot flat at <b>{exit_price:.2f}</b>.\n\n"
        f"<i>Locked in part of the move instead of letting it round-trip.</i>"
    )
    return await send(msg)


async def notify_hard_block(reason: str) -> bool:
    """Send notification when trading is hard-blocked (won't take any trades)."""
    msg = (
        f"🚫 <b>Bot is paused — won't trade right now</b>\n\n"
        f"<b>Why:</b> {reason}\n\n"
        f"<i>The block clears automatically once the condition is gone "
        f"(news event passes, VIX cools off, etc).</i>"
    )
    return await send(msg)


async def notify_circuit_breaker(losses: int, daily_pnl: float) -> bool:
    """Send circuit breaker alert — too many losses, stopping for the day."""
    msg = (
        f"⚠️ <b>Stopping for the day</b>\n\n"
        f"We've taken {losses} losses in a row.\n"
        f"Today's net: <b>${daily_pnl:+.2f}</b>\n\n"
        f"The circuit breaker tripped — no more trades until tomorrow.\n"
        f"<i>This protects us from revenge-trading after a bad streak.</i>"
    )
    return await send(msg)


async def notify_sentinel_alert(alert_type: str, details: str) -> bool:
    """Send sentinel alert — news or social media event that may move markets."""
    msg = (
        f"🚨 <b>Heads up — news that could move the market</b>\n\n"
        f"<b>What:</b> {alert_type}\n"
        f"<b>Details:</b> {details}\n\n"
        f"<i>This could shake things up. The bot may pause new entries or "
        f"tighten stops on open trades depending on the rules.</i>"
    )
    return await send(msg)


async def notify_weekly_report(report_text: str) -> bool:
    """Send the Sunday weekly journal report."""
    return await send(f"📈 <b>WEEKLY TRADING REPORT</b>\n\n{report_text}")


async def notify_strategy_review(rolling_wr: float, weeks: int) -> bool:
    """Send alert when rolling win rate drops below threshold."""
    msg = (
        f"⚠️ <b>The strategy might need a review</b>\n\n"
        f"Win rate over the last 20 trades: <b>{rolling_wr:.0%}</b>\n"
        f"It's been below 40% for {weeks} weeks in a row.\n\n"
        f"<i>The strategy might be drifting out of edge. Worth a look at "
        f"recent trades to decide if anything needs adjusting — parameters, "
        f"filters, or pausing live trading until conditions change.</i>"
    )
    return await send(msg)


async def notify_arm_blocked(arm_status: dict) -> bool:
    """9:25 arm gate failed — bot is sitting out the open. Lists the
    failing hard checks and tells Zach how to override."""
    checks = arm_status.get("checks", {}) or {}
    failing_lines = []
    for key, info in checks.items():
        if not info.get("ok"):
            label = {
                "cdp_symbol": "TradingView chart",
                "broker":     "Paper Trading broker",
                "dom_paper":  "Trade panel (DOM)",
            }.get(key, key)
            failing_lines.append(f"  • {label} — {info.get('msg', 'failing')}")

    if not failing_lines:
        # Defensive — should never hit since we only call this when armed=false
        failing_lines.append("  • (no specific failure recorded)")

    msg = (
        f"🚫 <b>Bot didn't arm at 9:25 — sitting out today's open</b>\n\n"
        f"<b>Failing checks:</b>\n"
        + "\n".join(failing_lines)
        + "\n\n"
        f"<i>I won't place any trades until this clears. If you eyeball "
        f"the chart and decide it's actually fine, tell Jarvis: "
        f"\"arm orb anyway\".</i>"
    )
    return await send(msg)


async def close() -> None:
    """Close the httpx client on shutdown."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
