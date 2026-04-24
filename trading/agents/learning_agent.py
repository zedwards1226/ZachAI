"""LEARNING AGENT — Runs 18:30 ET daily + Sunday 7:00 AM weekly digest.

Reviews the last 30 days of trades from journal.db and proposes
adjustments to the 3 learnable scoring knobs (SCORE_FULL_SIZE,
SCORE_HALF_SIZE, RVOL_THRESHOLD). Proposals are written to
`agent_journal` and summarised on Telegram — they do NOT auto-apply.

PR #1 (this file) is outbound-only. Human approval lands in PR #2
(telegram-bridge/bot.py command handlers). Until then, approval is a
manual JSON edit to state/learned_config.json, which gets detected via
checksum and logged to agent_journal with source='manual'.

Safety rails (in order of enforcement):
  1. Idempotency: if agent_journal already has a row for today, skip.
  2. Error wrap: every run is try/except — heartbeat always fires.
  3. Min sample: no proposal below 20 total trades.
  4. Cooldown: a knob cannot be proposed twice within 10 trading days of
     its last applied change.
  5. Step cap: ±1 point on scores, ±0.1 on RVOL.
  6. Bounds: clamped to LEARNABLE_KNOBS min/max.
  7. Approval required: proposals sit as status='pending' forever unless
     explicitly approved (JSON edit or PR #2 Telegram handler).

Manual edits to state/learned_config.json are detected on every run and
logged with source='manual'. Do not bypass this — the audit trail is
the whole point.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytz

# Allow `python -m agents.learning_agent` from trading/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import TIMEZONE, SCORE_FULL_SIZE, SCORE_HALF_SIZE, RVOL_THRESHOLD  # noqa: E402
from agents import config_loader, journal  # noqa: E402
from services import telegram  # noqa: E402

logger = logging.getLogger(__name__)
ET = pytz.timezone(TIMEZONE)

MIN_TRADES_FOR_PROPOSAL = 20
COOLDOWN_DAYS = 10
LOOKBACK_DAYS = 30
HALF_BAND_WR_FLOOR = 0.40   # below this → propose raising SCORE_HALF_SIZE
FULL_BAND_WR_FLOOR = 0.50   # below this → propose raising SCORE_FULL_SIZE
RVOL_FACTOR_MIN_TRADES = 10  # per-side minimum for RVOL delta analysis


def _today_str() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def _get_defaults() -> dict:
    """Return the baseline values BEFORE learned_config overrides."""
    # Re-read config.py defaults by snapshotting what would exist without
    # overrides. Safer than importing duplicate constants.
    from config import LEARNED_OVERRIDES
    defaults = {
        "SCORE_FULL_SIZE": 8,
        "SCORE_HALF_SIZE": 5,
        "RVOL_THRESHOLD": 1.5,
    }
    current = {
        "SCORE_FULL_SIZE": SCORE_FULL_SIZE,
        "SCORE_HALF_SIZE": SCORE_HALF_SIZE,
        "RVOL_THRESHOLD": RVOL_THRESHOLD,
    }
    return {"defaults": defaults, "current": current, "overrides": dict(LEARNED_OVERRIDES)}


def _recent_trades(days: int = LOOKBACK_DAYS) -> list[dict]:
    """All closed trades in the last N calendar days."""
    cutoff = (datetime.now(ET) - timedelta(days=days)).strftime("%Y-%m-%d")
    with journal.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades "
            "WHERE date >= ? AND outcome NOT IN ('OPEN', 'FAILED_PLACEMENT') "
            "ORDER BY date, time",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def _in_cooldown(knob: str) -> tuple[bool, Optional[str]]:
    """Check if knob was changed within the cooldown window.

    Returns (True, 'YYYY-MM-DD') if cooling down, else (False, None).
    """
    last = journal.get_last_knob_change(knob)
    if not last or not last.get("applied_at"):
        return False, None
    try:
        applied = datetime.fromisoformat(last["applied_at"])
    except (ValueError, TypeError):
        return False, None
    if applied.tzinfo is None:
        applied = ET.localize(applied)
    days_since = (datetime.now(ET) - applied).days
    if days_since < COOLDOWN_DAYS:
        return True, last["applied_at"][:10]
    return False, None


def _wr(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.get("outcome") == "WIN")
    return wins / len(trades)


def _analyze_score_bands(trades: list[dict], current: dict) -> list[dict]:
    """Look for underperforming score bands.

    Returns list of proposal dicts (may be empty).
    """
    proposals: list[dict] = []
    full_thresh = current["SCORE_FULL_SIZE"]
    half_thresh = current["SCORE_HALF_SIZE"]

    full_band = [t for t in trades if (t.get("score") or 0) >= full_thresh]
    half_band = [t for t in trades
                 if half_thresh <= (t.get("score") or 0) < full_thresh]

    # --- Half-size band: if WR too low, propose raising the half threshold
    if len(half_band) >= MIN_TRADES_FOR_PROPOSAL // 2:
        half_wr = _wr(half_band)
        if half_wr < HALF_BAND_WR_FLOOR:
            new_val = min(half_thresh + 1, 9)
            if new_val != half_thresh:
                proposals.append({
                    "knob": "SCORE_HALF_SIZE",
                    "current": half_thresh,
                    "proposed": new_val,
                    "sample_size": len(half_band),
                    "confidence": round(1 - half_wr, 2),
                    "reasoning": (
                        f"Half-size band ({half_thresh}-{full_thresh - 1}) "
                        f"win-rate {half_wr:.0%} over {len(half_band)} trades — "
                        f"below {HALF_BAND_WR_FLOOR:.0%} floor. "
                        f"Raising SCORE_HALF_SIZE {half_thresh} → {new_val} "
                        "to tighten entry criteria."
                    ),
                })

    # --- Full-size band: if WR too low, propose raising the full threshold
    if len(full_band) >= MIN_TRADES_FOR_PROPOSAL // 2:
        full_wr = _wr(full_band)
        if full_wr < FULL_BAND_WR_FLOOR:
            new_val = min(full_thresh + 1, 12)
            if new_val != full_thresh:
                proposals.append({
                    "knob": "SCORE_FULL_SIZE",
                    "current": full_thresh,
                    "proposed": new_val,
                    "sample_size": len(full_band),
                    "confidence": round(1 - full_wr, 2),
                    "reasoning": (
                        f"Full-size band ({full_thresh}+) win-rate "
                        f"{full_wr:.0%} over {len(full_band)} trades — below "
                        f"{FULL_BAND_WR_FLOOR:.0%} floor. "
                        f"Raising SCORE_FULL_SIZE {full_thresh} → {new_val}."
                    ),
                })

    return proposals


def _analyze_rvol(trades: list[dict], current: dict) -> list[dict]:
    """Does RVOL correlate with outcome?

    Compare WR of trades with rvol_at_entry >= threshold vs < threshold.
    If high-RVOL trades win notably more, consider lowering threshold
    (capture more qualifying signals). If they win less, raise it.
    """
    proposals: list[dict] = []
    threshold = current["RVOL_THRESHOLD"]
    with_rvol = [t for t in trades if t.get("rvol_at_entry") is not None]
    high = [t for t in with_rvol if t["rvol_at_entry"] >= threshold]
    low = [t for t in with_rvol if t["rvol_at_entry"] < threshold]

    if len(high) < RVOL_FACTOR_MIN_TRADES or len(low) < RVOL_FACTOR_MIN_TRADES:
        return proposals

    high_wr = _wr(high)
    low_wr = _wr(low)
    delta = high_wr - low_wr

    if delta < -0.10:  # RVOL filter hurting — raise the bar
        new_val = round(min(threshold + 0.1, 2.0), 2)
        if new_val != threshold:
            proposals.append({
                "knob": "RVOL_THRESHOLD",
                "current": threshold,
                "proposed": new_val,
                "sample_size": len(with_rvol),
                "confidence": round(abs(delta), 2),
                "reasoning": (
                    f"High-RVOL trades WR {high_wr:.0%} ({len(high)}) vs "
                    f"low-RVOL WR {low_wr:.0%} ({len(low)}) — delta "
                    f"{delta:+.0%}. High-RVOL underperforming; raise "
                    f"RVOL_THRESHOLD {threshold} → {new_val}."
                ),
            })
    elif delta > 0.15 and threshold > 1.2:  # RVOL filter working — consider loosening
        new_val = round(max(threshold - 0.1, 1.2), 2)
        if new_val != threshold:
            proposals.append({
                "knob": "RVOL_THRESHOLD",
                "current": threshold,
                "proposed": new_val,
                "sample_size": len(with_rvol),
                "confidence": round(delta, 2),
                "reasoning": (
                    f"High-RVOL trades WR {high_wr:.0%} ({len(high)}) vs "
                    f"low-RVOL WR {low_wr:.0%} ({len(low)}) — delta "
                    f"{delta:+.0%}. RVOL filter effective; loosening "
                    f"RVOL_THRESHOLD {threshold} → {new_val} to qualify "
                    "more setups."
                ),
            })

    return proposals


def _time_of_day_observations(trades: list[dict]) -> list[str]:
    """Flag half-hour windows with poor WR for manual review.

    Diagnostic only — does not propose any config changes.
    """
    notes: list[str] = []
    buckets: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        time_str = t.get("time", "00:00:00")
        try:
            hour, minute = int(time_str[:2]), int(time_str[3:5])
        except (ValueError, IndexError):
            continue
        bucket = f"{hour:02d}:{(minute // 30) * 30:02d}"
        buckets[bucket].append(t)
    for bucket, bt in sorted(buckets.items()):
        if len(bt) >= 5:
            wr = _wr(bt)
            if wr < 0.30:
                notes.append(
                    f"Window {bucket} WR {wr:.0%} over {len(bt)} trades — "
                    "review if this keeps up."
                )
    return notes


async def _send(message: str) -> None:
    """Best-effort Telegram send; swallow failures (heartbeat tolerance)."""
    try:
        await telegram.send(message)
    except Exception:
        logger.exception("Learning agent telegram send failed")


async def _log_manual_edit_if_any() -> None:
    """Detect manual state/learned_config.json edits and audit them."""
    drift = config_loader.detect_manual_edit()
    if drift is None:
        return
    before = drift["before"]
    after = drift["after"]
    changed_keys = sorted(set(before) | set(after))
    diff_lines = []
    for k in changed_keys:
        diff_lines.append(f"{k}: {before.get(k, '—')} → {after.get(k, '—')}")
    reasoning = "Detected external edit to learned_config.json:\n" + "\n".join(diff_lines)
    journal.agent_journal_write(
        entry_type="manual_edit",
        subject="learned_config.json",
        reasoning=reasoning,
        source="manual",
        status="applied",
        data={"before": before, "after": after, "checksum": drift["checksum"]},
    )
    config_loader.acknowledge_current()
    logger.info("Manual learned_config edit logged to agent_journal")


async def run(dry_run: bool = False) -> dict:
    """Main nightly entry. Idempotent per day, error-wrapped.

    Returns a summary dict for the Sunday weekly digest + tests.
    """
    logger.info("Learning agent run starting (dry_run=%s)", dry_run)
    today = _today_str()
    summary = {"date": today, "status": "ok", "proposals": [], "heartbeat": None}

    try:
        # ─── 1. Idempotency guard ───
        if not dry_run and journal.agent_journal_has_today():
            logger.info("Learning agent already ran today; skipping")
            summary["status"] = "already_ran"
            return summary

        # ─── 2. Manual edit detection (runs every time) ───
        await _log_manual_edit_if_any()

        # ─── 3. Pull trades ───
        trades = _recent_trades(LOOKBACK_DAYS)
        total = len(trades)
        current = _get_defaults()["current"]

        # ─── 4. Sample check + heartbeat ───
        if total < MIN_TRADES_FOR_PROPOSAL:
            heartbeat = (
                f"🧠 ORB Learning Agent — ran at {datetime.now(ET).strftime('%I:%M %p ET')}"
                f" — {total}/{MIN_TRADES_FOR_PROPOSAL} trades accumulated —"
                " no proposal yet"
            )
            if not dry_run:
                journal.agent_journal_write(
                    entry_type="heartbeat",
                    subject="insufficient_data",
                    reasoning=f"{total}/{MIN_TRADES_FOR_PROPOSAL} trades in last "
                              f"{LOOKBACK_DAYS}d — below threshold, no analysis run.",
                    sample_size=total,
                    status="applied",
                )
                await _send(heartbeat)
            summary["heartbeat"] = heartbeat
            summary["trade_count"] = total
            return summary

        # ─── 5. Run analyses ───
        proposals: list[dict] = []
        proposals.extend(_analyze_score_bands(trades, current))
        proposals.extend(_analyze_rvol(trades, current))

        # ─── 6. Apply cooldown + step caps ───
        filtered: list[dict] = []
        skipped_for_cooldown: list[dict] = []
        for p in proposals:
            cooling, since = _in_cooldown(p["knob"])
            if cooling:
                skipped_for_cooldown.append({**p, "cooldown_since": since})
                continue
            filtered.append(p)

        # ─── 7. Observations (diagnostic, not proposed) ───
        observations = _time_of_day_observations(trades)

        # ─── 8. Write rows + Telegram digest ───
        digest_lines = [
            f"🧠 <b>ORB Learning Agent</b> — {datetime.now(ET).strftime('%a %b %d %I:%M %p ET')}",
            f"Reviewed {total} trades over last {LOOKBACK_DAYS} days",
            "",
        ]

        proposal_ids: list[int] = []
        if not filtered:
            digest_lines.append("✅ No rule changes proposed today.")
        else:
            digest_lines.append("<b>Proposals:</b>")
            for p in filtered:
                if not dry_run:
                    pid = journal.agent_journal_write(
                        entry_type="proposal",
                        subject=p["knob"],
                        knob=p["knob"],
                        current_value=p["current"],
                        proposed_value=p["proposed"],
                        sample_size=p["sample_size"],
                        confidence=p["confidence"],
                        reasoning=p["reasoning"],
                        status="pending",
                    )
                    proposal_ids.append(pid)
                    p["id"] = pid
                digest_lines.append(
                    f"• #{p.get('id', '?')} {p['knob']}: {p['current']} → "
                    f"{p['proposed']}"
                )
                digest_lines.append(f"  {p['reasoning']}")
            digest_lines.append("")
            digest_lines.append(
                "To apply: edit state/learned_config.json with the new value "
                "(logged as source='manual'), or wait for Telegram approval "
                "handlers (PR #2)."
            )

        if skipped_for_cooldown:
            digest_lines.append("")
            digest_lines.append("<b>Skipped (cooldown):</b>")
            for p in skipped_for_cooldown:
                digest_lines.append(
                    f"• {p['knob']} — last changed {p['cooldown_since']}, "
                    f"within {COOLDOWN_DAYS}d cooldown"
                )

        if observations:
            digest_lines.append("")
            digest_lines.append("<b>Observations (not proposed):</b>")
            for obs in observations:
                digest_lines.append(f"• {obs}")

        digest = "\n".join(digest_lines)
        summary["proposals"] = filtered
        summary["digest"] = digest

        if not dry_run:
            journal.agent_journal_write(
                entry_type="digest",
                subject="review_end",
                reasoning=digest,
                sample_size=total,
                status="applied",
                data={"proposal_ids": proposal_ids,
                      "skipped_for_cooldown": skipped_for_cooldown,
                      "observations": observations},
            )
            await _send(digest)
        else:
            print(digest)

        logger.info("Learning agent complete: %d proposal(s)", len(filtered))
        return summary

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("Learning agent FAILED: %s\n%s", exc, tb)
        summary["status"] = "error"
        summary["error"] = str(exc)
        try:
            if not dry_run:
                journal.agent_journal_write(
                    entry_type="error",
                    reasoning=f"{exc}\n\n{tb}",
                    status="applied",
                )
        except Exception:
            logger.exception("Could not write error row to agent_journal")
        await _send(f"🚨 ORB Learning Agent errored — {exc}")
        return summary


async def run_weekly_digest() -> bool:
    """Sunday 7:00 AM — summarise last 7 days of agent_journal activity."""
    try:
        cutoff = (datetime.now(ET) - timedelta(days=7)).strftime("%Y-%m-%d")
        with journal.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_journal WHERE date >= ? ORDER BY id",
                (cutoff,),
            ).fetchall()
            rows = [dict(r) for r in rows]

        heartbeats = sum(1 for r in rows if r["entry_type"] == "heartbeat")
        proposals = [r for r in rows if r["entry_type"] == "proposal"]
        manual = [r for r in rows if r["entry_type"] == "manual_edit"]
        errors = [r for r in rows if r["entry_type"] == "error"]

        lines = [
            "🧠 <b>ORB Learning Agent — Weekly Digest</b>",
            f"Week ending {datetime.now(ET).strftime('%b %d')}",
            "",
            f"Runs: {heartbeats + len([r for r in rows if r['entry_type'] == 'digest'])} "
            f"({heartbeats} heartbeat-only)",
            f"Proposals: {len(proposals)}",
            f"Manual edits: {len(manual)}",
            f"Errors: {len(errors)}",
        ]

        if proposals:
            lines.append("")
            lines.append("<b>This week's proposals:</b>")
            for p in proposals:
                status_emoji = {"pending": "⏳", "approved": "✅",
                                "rejected": "❌", "reverted": "↩️"}.get(
                    p.get("status", "pending"), "•"
                )
                lines.append(
                    f"{status_emoji} #{p['id']} {p['knob']}: "
                    f"{p['current_value']} → {p['proposed_value']} "
                    f"({p.get('status', 'pending')})"
                )

        if errors:
            lines.append("")
            lines.append("⚠️ <b>Errors this week:</b>")
            for e in errors[-3:]:
                reason = (e.get("reasoning") or "")[:120]
                lines.append(f"• {e['date']}: {reason}")

        await telegram.send("\n".join(lines))
        return True
    except Exception:
        logger.exception("Weekly digest failed")
        return False


def _cli() -> None:
    parser = argparse.ArgumentParser(description="ORB Learning Agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print proposals without writing to DB or Telegram")
    parser.add_argument("--weekly", action="store_true",
                        help="Run weekly digest instead of nightly review")
    args = parser.parse_args()

    # Windows console defaults to cp1252 which chokes on emoji. Switch
    # stdout/stderr to utf-8 so dry-run output is readable.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    journal.init_db()

    if args.weekly:
        result = asyncio.run(run_weekly_digest())
    else:
        result = asyncio.run(run(dry_run=args.dry_run))
    try:
        print(result)
    except UnicodeEncodeError:
        print(repr(result).encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    _cli()
