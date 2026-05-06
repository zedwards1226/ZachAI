"""BRIEFING AGENT — Runs at 8:50 AM ET.

Sends Zach the same analysis the agents use to make decisions via Telegram —
but in plain English. Reads structure.json, memory.json, sentinel.json and
compiles a morning report a human can read on a phone in 10 seconds.

Style template = WeatherAlpha's daily digest (see kalshi/bots/monitor.py
send_daily_digest). Section headers + 1-2 sentence narrative bullets.
Abbreviations only appear in parens after their first plain-English use.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pytz

from config import TIMEZONE, SCORE_FULL_SIZE, SCORE_HALF_SIZE, LEARNED_OVERRIDES
from services.state_manager import read_state, is_state_today
from services import telegram
from agents import journal

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


# Plain-English maps for the few internal labels that leak into the briefing.
# Keep these tiny — the briefing should mostly read as prose, not a glossary.
_ZONE_PHRASE = {
    "DISCOUNT":   "lower half of yesterday's range (good for buying)",
    "PREMIUM":    "upper half of yesterday's range (good for selling)",
    "EQUILIBRIUM": "middle of yesterday's range (no edge either way)",
}
_VIX_PHRASE = {
    "SWEET_SPOT": "calm — right in the bot's sweet spot (15-25)",
    "LOW":        "very calm — small ranges expected",
    "NORMAL":     "normal levels",
    "ELEVATED":   "elevated — bigger moves possible",
    "EXTREME":    "wild — VIX above 30, bot will hard-block",
}
_KNOB_PHRASE = {
    "SCORE_HALF_SIZE": "minimum confidence to take a half-size trade",
    "SCORE_FULL_SIZE": "minimum confidence to go full size",
    "RVOL_THRESHOLD":  "minimum volume requirement (vs. average)",
}


async def run() -> bool:
    """Generate and send the morning briefing. Returns True if sent."""
    logger.info("Briefing agent starting")

    structure = read_state("structure")
    memory = read_state("memory")
    sentinel = read_state("sentinel")

    today = datetime.now(ET)
    day_name = today.strftime("%A %b %d")

    lines = [
        f"📊 <b>ORB morning briefing — {day_name}</b>",
        "<i>Here's the lay of the land before today's open.</i>",
        "",
    ]

    # --- WHAT YESTERDAY DID + WHERE PRICE IS NOW ---
    lines.append("<b>The setup</b>")
    if structure.get("error"):
        lines.append(f"  ⚠️ Couldn't read the chart: {structure['error']}")
    elif not is_state_today("structure"):
        lines.append("  ⚠️ Chart data is stale (not from today) — bot may not trade until it refreshes.")
    else:
        pd = structure.get("prior_day", {}) or {}
        pw = structure.get("prior_week", {}) or {}
        on = structure.get("overnight", {}) or {}
        pm = structure.get("premarket", {}) or {}

        if pd.get("close") is not None:
            lines.append(
                f"  • Yesterday closed at {_fmt(pd.get('close'))} — "
                f"high {_fmt(pd.get('high'))}, low {_fmt(pd.get('low'))}."
            )
        if pw.get("high") is not None:
            lines.append(
                f"  • Last week's range: {_fmt(pw.get('low'))} to {_fmt(pw.get('high'))}."
            )
        if on.get("high") is not None:
            lines.append(
                f"  • Overnight stretched from {_fmt(on.get('low'))} to {_fmt(on.get('high'))}."
            )
        if pm.get("high") is not None:
            lines.append(
                f"  • Premarket so far: {_fmt(pm.get('low'))} to {_fmt(pm.get('high'))}."
            )

        zone = structure.get("zone", "?")
        zone_phrase = _ZONE_PHRASE.get(zone)
        if zone_phrase:
            lines.append(f"  • Price is sitting in the {zone_phrase}.")

        nearest = structure.get("nearest_level", {}) or {}
        if nearest.get("name"):
            lines.append(
                f"  • Right now we're {nearest.get('distance_pts', '?')} points from "
                f"{nearest.get('name', '?')} — that's the closest meaningful level."
            )

        vix = structure.get("vix")
        vix_regime = structure.get("vix_regime", "?")
        vix_phrase = _VIX_PHRASE.get(vix_regime, "")
        if vix is not None:
            if vix_phrase:
                lines.append(f"  • Volatility (VIX): {vix} — {vix_phrase}.")
            else:
                lines.append(f"  • Volatility (VIX): {vix}.")

        rvol = structure.get("rvol")
        if rvol:
            descriptor = (
                "below average" if rvol < 0.9
                else "above average" if rvol > 1.1
                else "near average"
            )
            lines.append(f"  • Volume so far is {descriptor} ({rvol:.1f}× normal).")

        atr = structure.get("atr_14")
        if atr:
            lines.append(f"  • Typical daily move (14-day average): {atr:.1f} points.")

    lines.append("")

    # --- WHAT THE BOT REMEMBERS FROM RECENT DAYS ---
    lines.append("<b>What the bot's been seeing lately</b>")
    if memory.get("error"):
        lines.append(f"  ⚠️ Memory unavailable: {memory['error']}")
    elif not memory.get("morning_bias"):
        lines.append("  ⚠️ No memory data yet — bot needs a few sessions to form a view.")
    else:
        bias = memory.get("morning_bias", "?")
        conf = memory.get("bias_confidence", 0)
        reasons = memory.get("bias_reasons", []) or []

        if "BULLISH" in bias:
            bias_phrase = f"leaning <b>bullish</b> ({conf:.0%} confidence)"
        elif "BEARISH" in bias:
            bias_phrase = f"leaning <b>bearish</b> ({conf:.0%} confidence)"
        else:
            bias_phrase = f"<b>neutral</b> ({conf:.0%} confidence)"
        lines.append(f"  • Today's bias: {bias_phrase}.")

        for r in reasons[:3]:
            lines.append(f"    – {r}")

        recent = memory.get("recent_days", []) or []
        if recent:
            day_strs = []
            for d in recent[-3:]:
                day_type = d.get("day_type", "?").lower()
                direction = (d.get("direction") or "?").lower()
                day_strs.append(f"{day_type} day, {direction}")
            lines.append(f"  • Last 3 days: {' / '.join(day_strs)}.")

        rolling = memory.get("rolling_10day", {}) or {}
        if rolling.get("avg_range"):
            lines.append(
                f"  • 10-day average daily range: {rolling['avg_range']} points."
            )

    lines.append("")

    # --- NEWS / EVENTS RISK ---
    lines.append("<b>News &amp; events check</b>")
    if not sentinel:
        lines.append("  ⚠️ Sentinel hasn't run yet — news risk unknown.")
    else:
        news_block = sentinel.get("news_block", False)
        truth_block = sentinel.get("truth_block", False)

        if not news_block and not truth_block:
            lines.append("  ✅ Nothing flagged — bot is free to trade.")
        else:
            if news_block:
                lines.append("  🚫 News block is active — major economic event nearby.")
            if truth_block:
                lines.append("  🚫 Block from a market-moving social-media post.")
            if sentinel.get("block_reason"):
                lines.append(f"    – Reason: {sentinel['block_reason']}")

        events = sentinel.get("economic_events", []) or []
        for ev in events[:2]:
            lines.append(
                f"  • Upcoming: {ev.get('time', '?')} — {ev.get('event', '?')} "
                f"(impact: {ev.get('impact', '?')})"
            )

        truth_posts = sentinel.get("truth_posts", []) or []
        high_posts = [p for p in truth_posts if p.get("impact") == "HIGH_IMPACT"]
        if high_posts:
            lines.append(f"  ⚡ {len(high_posts)} high-impact news item(s) being watched:")
            for p in high_posts[:3]:
                lines.append(f"    – {p['text'][:120]}")
        elif truth_posts:
            lines.append(f"  📰 {len(truth_posts)} news items scanned, none flagged high-impact.")

        if sentinel.get("truth_status") == "UNAVAILABLE":
            lines.append("  ⚠️ News feed temporarily unavailable.")

    lines.append("")

    # --- THE GAME PLAN ---
    lines.append("<b>Game plan</b>")
    bias_dir = memory.get("morning_bias", "NEUTRAL")
    zone = structure.get("zone", "?")
    vix_regime = structure.get("vix_regime", "?")

    if "BULLISH" in bias_dir:
        plan = "Looking to buy if NQ breaks above the opening range high"
        if zone == "DISCOUNT":
            plan += " (price is already in a good zone for that)"
        plan += "."
    elif "BEARISH" in bias_dir:
        plan = "Looking to sell short if NQ breaks below the opening range low"
        if zone == "PREMIUM":
            plan += " (price is already in a good zone for that)"
        plan += "."
    else:
        plan = "No directional bias today — bot will take the first valid breakout in either direction."
    lines.append(f"  • {plan}")

    pd = structure.get("prior_day", {}) or {}
    if pd.get("high") is not None and pd.get("low") is not None:
        lines.append(
            f"  • Key levels to watch: "
            f"{_fmt(pd.get('high'))} (yesterday's high — likely resistance), "
            f"{_fmt(pd.get('low'))} (yesterday's low — likely support)."
        )

    if "BULLISH" in bias_dir:
        lines.append(
            f"  • A clean break above the opening range high would likely score "
            f"{SCORE_FULL_SIZE}+ → bot takes it at full size."
        )
        lines.append(
            f"  • A break the other way would fight the bias and probably "
            f"score below {SCORE_HALF_SIZE} → bot will skip it."
        )
    elif "BEARISH" in bias_dir:
        lines.append(
            f"  • A clean break below the opening range low would likely score "
            f"{SCORE_FULL_SIZE}+ → bot takes it at full size."
        )
        lines.append(
            f"  • A break the other way would fight the bias and probably "
            f"score below {SCORE_HALF_SIZE} → bot will skip it."
        )

    blocks = []
    if vix_regime == "EXTREME":
        blocks.append("VIX is above 30 — too wild")
    if sentinel.get("news_block"):
        blocks.append("news block active")
    if sentinel.get("truth_block"):
        blocks.append("market-moving news block active")
    if blocks:
        lines.append(f"  ⚠️ Hard blocks today: {'; '.join(blocks)}.")
    else:
        lines.append("  ✅ No hard blocks — bot is cleared to trade if a setup appears.")

    # --- LEARNING AGENT FOOTER (only if there's something to say) ---
    pending = _pending_proposals()
    if LEARNED_OVERRIDES or pending:
        lines.append("")
        lines.append("<b>Learning agent</b>")
        if LEARNED_OVERRIDES:
            lines.append("  Active rule changes from recent learning:")
            for k, v in sorted(LEARNED_OVERRIDES.items()):
                pretty = _KNOB_PHRASE.get(k, k.replace("_", " ").lower())
                lines.append(f"    • {pretty}: now <b>{v}</b>")
        if pending:
            lines.append(f"  Waiting on your call ({len(pending)} pending proposal(s)):")
            for p in pending[:3]:
                pretty = _KNOB_PHRASE.get(p["knob"], p["knob"].replace("_", " ").lower())
                lines.append(
                    f"    ⏳ #{p['id']} — change {pretty} from "
                    f"{p['current_value']} to {p['proposed_value']}"
                )

    message = "\n".join(lines)
    success = await telegram.notify_briefing(message)
    if success:
        logger.info("Morning briefing sent successfully")
    else:
        logger.error("Failed to send morning briefing")
    return success


def _fmt(val) -> str:
    """Format a price value."""
    if val is None:
        return "?"
    try:
        return f"{float(val):,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _pending_proposals() -> list[dict]:
    """Safe fetch of pending learning-agent proposals for briefing display."""
    try:
        return journal.get_agent_proposals(status="pending", limit=5)
    except Exception:
        logger.exception("Failed to read pending proposals for briefing")
        return []
