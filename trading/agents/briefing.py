"""BRIEFING AGENT — Runs at 8:50 AM ET.

Sends Zach the same analysis the agents use to make decisions via Telegram.
Reads structure.json, memory.json, sentinel.json and compiles into a morning report.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pytz

from config import TIMEZONE, SCORE_FULL_SIZE, SCORE_HALF_SIZE
from services.state_manager import read_state, is_state_today
from services import telegram

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)


async def run() -> bool:
    """Generate and send the morning briefing. Returns True if sent."""
    logger.info("Briefing agent starting")

    structure = read_state("structure")
    memory = read_state("memory")
    sentinel = read_state("sentinel")

    today = datetime.now(ET)
    day_name = today.strftime("%a %b %d")

    lines = [f"📊 <b>ORB MORNING BRIEFING — {day_name}</b>", ""]

    # --- STRUCTURE ---
    lines.append("━━━ <b>STRUCTURE</b> ━━━")
    if structure.get("error"):
        lines.append(f"⚠️ Error: {structure['error']}")
    elif not is_state_today("structure"):
        lines.append("⚠️ Stale data (not from today)")
    else:
        pd = structure.get("prior_day", {})
        pw = structure.get("prior_week", {})
        on = structure.get("overnight", {})
        pm = structure.get("premarket", {})

        lines.append(
            f"PDH: {_fmt(pd.get('high'))} | PDL: {_fmt(pd.get('low'))} | PDC: {_fmt(pd.get('close'))}"
        )
        lines.append(f"PWH: {_fmt(pw.get('high'))} | PWL: {_fmt(pw.get('low'))}")
        lines.append(f"ON H: {_fmt(on.get('high'))} | ON L: {_fmt(on.get('low'))}")
        lines.append(f"PM H: {_fmt(pm.get('high'))} | PM L: {_fmt(pm.get('low'))}")
        lines.append(f"Equilibrium: {_fmt(structure.get('equilibrium'))}")
        lines.append(f"Zone: {structure.get('zone', '?')}")

        loc = structure.get("price_location", "?")
        nearest = structure.get("nearest_level", {})
        lines.append(
            f"Price Location: {loc} ({nearest.get('distance_pts', '?')} pts from {nearest.get('name', '?')})"
        )

        vix = structure.get("vix")
        vix_regime = structure.get("vix_regime", "?")
        vix_emoji = "✓" if vix_regime == "SWEET_SPOT" else "⚠️" if vix_regime == "EXTREME" else ""
        lines.append(f"VIX: {vix or '?'} ({vix_regime}) {vix_emoji}")

        rvol = structure.get("rvol")
        if rvol:
            lines.append(f"RVOL: {rvol:.1f}x")

        atr = structure.get("atr_14")
        if atr:
            lines.append(f"ATR(14): {atr:.2f}")

    lines.append("")

    # --- MEMORY ---
    lines.append("━━━ <b>MEMORY</b> ━━━")
    if memory.get("error"):
        lines.append(f"⚠️ Error: {memory['error']}")
    elif not memory.get("morning_bias"):
        lines.append("⚠️ No memory data available")
    else:
        bias = memory.get("morning_bias", "?")
        conf = memory.get("bias_confidence", 0)
        reasons = memory.get("bias_reasons", [])

        bias_emoji = "🟢" if "BULLISH" in bias else "🔴" if "BEARISH" in bias else "⚪"
        lines.append(f"Bias: {bias_emoji} {bias} (confidence {conf:.0%})")
        for r in reasons[:3]:
            lines.append(f"  • {r}")

        recent = memory.get("recent_days", [])
        if recent:
            day_strs = []
            for d in recent[-3:]:
                arrow = "↑" if d.get("direction") == "BULLISH" else "↓"
                day_strs.append(f"{d.get('day_type', '?')} {arrow}")
            lines.append(f"Last 3: {' | '.join(day_strs)}")

        fvgs = memory.get("fvgs", [])
        if fvgs:
            for fvg in fvgs[:2]:
                lines.append(
                    f"FVG: {fvg['fvg_type']} {_fmt(fvg.get('low'))}-{_fmt(fvg.get('high'))}"
                )

        rolling = memory.get("rolling_10day", {})
        if rolling:
            lines.append(f"10-day avg range: {rolling.get('avg_range', '?')} pts")

    lines.append("")

    # --- SENTINEL ---
    lines.append("━━━ <b>SENTINEL</b> ━━━")
    if not sentinel:
        lines.append("⚠️ No sentinel data (not yet run)")
    else:
        news_block = sentinel.get("news_block", False)
        truth_block = sentinel.get("truth_block", False)

        nb_emoji = "🚫" if news_block else "✅"
        tb_emoji = "🚫" if truth_block else "✅"
        lines.append(f"NEWS_BLOCK: {nb_emoji} {'ACTIVE' if news_block else 'Clear'}")
        lines.append(f"TRUTH_BLOCK: {tb_emoji} {'ACTIVE' if truth_block else 'Clear'}")

        if sentinel.get("block_reason"):
            lines.append(f"Reason: {sentinel['block_reason']}")

        events = sentinel.get("economic_events", [])
        if events:
            for ev in events[:2]:
                lines.append(f"  📅 {ev.get('time', '?')} — {ev.get('event', '?')} ({ev.get('impact', '?')})")

        truth_posts = sentinel.get("truth_posts", [])
        high_posts = [p for p in truth_posts if p.get("impact") == "HIGH_IMPACT"]
        if high_posts:
            lines.append(f"  ⚡ {len(high_posts)} high-impact Truth Social post(s)")

    lines.append("")

    # --- GAME PLAN ---
    lines.append("━━━ <b>GAME PLAN</b> ━━━")

    bias_dir = memory.get("morning_bias", "NEUTRAL")
    zone = structure.get("zone", "?")
    price_loc = structure.get("price_location", "?")
    vix_regime = structure.get("vix_regime", "?")

    # Determine preferred direction
    if "BULLISH" in bias_dir:
        pref = "LONG preferred (memory bias bullish"
        if zone == "DISCOUNT":
            pref += " + discount zone"
        pref += ")"
    elif "BEARISH" in bias_dir:
        pref = "SHORT preferred (memory bias bearish"
        if zone == "PREMIUM":
            pref += " + premium zone"
        pref += ")"
    else:
        pref = "No directional preference (neutral bias)"

    lines.append(f"Direction: {pref}")

    # Key levels
    pd = structure.get("prior_day", {})
    if pd:
        lines.append(
            f"Key levels: PDH {_fmt(pd.get('high'))} (resistance), PDL {_fmt(pd.get('low'))} (support)"
        )

    # Expected scoring
    if "BULLISH" in bias_dir:
        lines.append(f"If ORB breaks HIGH → LONG, score likely {SCORE_FULL_SIZE}+ (full size)")
        lines.append(f"If ORB breaks LOW → counter-bias, score likely &lt;{SCORE_HALF_SIZE} (skip)")
    elif "BEARISH" in bias_dir:
        lines.append(f"If ORB breaks LOW → SHORT, score likely {SCORE_FULL_SIZE}+ (full size)")
        lines.append(f"If ORB breaks HIGH → counter-bias, score likely &lt;{SCORE_HALF_SIZE} (skip)")

    # Hard blocks check
    blocks = []
    if vix_regime == "EXTREME":
        blocks.append("VIX > 30")
    if sentinel.get("news_block"):
        blocks.append("News block active")
    if sentinel.get("truth_block"):
        blocks.append("Truth Social block active")

    if blocks:
        lines.append(f"⚠️ Hard blocks: {', '.join(blocks)}")
    else:
        lines.append("Hard blocks: None active ✓")

    # Send
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
