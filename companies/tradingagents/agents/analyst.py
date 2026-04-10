"""
Analyst Agent — End-of-day review and pattern analysis.
Runs via APScheduler at 4:15 PM ET (after session close).

Reviews:
1. All trades from the day (entries, exits, P&L)
2. All agent decisions (PASS/BLOCK reasons)
3. Win rate, avg P&L, best/worst trade
4. Patterns and improvement suggestions

Uses Claude API with no token cap — this is the one agent that gets full context.
Sends EOD summary to Telegram.
"""
import logging
from datetime import date

import database as db
from services.claude_client import ask
from services.telegram_bot import notify_eod_summary

log = logging.getLogger("analyst")

SYSTEM_PROMPT = """You are the Analyst agent for an autonomous NQ/MNQ futures trading system.
You review the day's trades and provide a concise, actionable end-of-day analysis.

Your analysis should include:
1. Performance summary (win rate, total P&L, best/worst trade)
2. Pattern observations (were blocks justified? did sweep warnings help?)
3. One concrete improvement suggestion for tomorrow

Keep it under 200 words. Be direct. Use numbers."""


async def run_eod_analysis() -> str:
    """Run end-of-day analysis. Returns the analysis text."""
    today = date.today().isoformat()
    summary = db.get_summary()
    trades = db.get_trades_today()

    if not trades:
        msg = f"No trades today ({today}). System was idle."
        log.info(msg)
        await notify_eod_summary(summary, msg)
        return msg

    # Build context for Claude
    trade_lines = []
    for t in trades:
        status = t["status"]
        pnl_str = f"${t['pnl']:+,.2f}" if t["pnl"] is not None else "open"
        trade_lines.append(
            f"  #{t['id']} {t['side']} {t['symbol']} @ {t['entry']:.2f} → "
            f"{t.get('exit', '?'):.2f if isinstance(t.get('exit'), (int,float)) else '?'} "
            f"| {pnl_str} ({status})"
        )

    # Get all decisions for today's signals
    decision_lines = []
    for t in trades:
        if t.get("signal_id"):
            decisions = db.get_decisions_for_signal(t["signal_id"])
            for d in decisions:
                decision_lines.append(
                    f"  Signal #{d['signal_id']} → {d['agent']}: {d['verdict']} — {d['reasoning']}"
                )

    user_msg = f"""Date: {today}
Summary: {summary['total_trades']} trades, {summary['wins']}W/{summary['losses']}L, ${summary['total_pnl']:+,.2f} P&L, {summary['win_rate']:.1f}% WR

Trades:
{chr(10).join(trade_lines)}

Agent Decisions:
{chr(10).join(decision_lines) if decision_lines else '  None logged'}
"""

    analysis, tokens = ask(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_output_tokens=500,  # analyst gets more room
    )

    if not analysis:
        analysis = "Claude API unavailable — skipping AI analysis."
        log.warning(analysis)
    else:
        log.info("EOD analysis: %d tokens used", tokens)

    # Log the analysis as a decision
    if trades:
        db.insert_decision(
            signal_id=trades[0].get("signal_id", 0) or 0,
            agent="analyst",
            verdict="PASS",
            reasoning=analysis[:500],
            tokens_used=tokens,
        )

    await notify_eod_summary(summary, analysis)
    return analysis
