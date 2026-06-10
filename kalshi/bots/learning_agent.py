"""
Learning Agent — reviews trades nightly, decides pauses + MIN_EDGE moves,
writes to agent_journal, pings Telegram with its reasoning.

Reads:
  - trades, signals, city cooldowns, agent_state
Writes:
  - agent_state (effective_min_edge)
  - city_cooldowns (auto-pause losers)
  - agent_journal (every observation + decision + action)

Scheduled by scheduler.py at 18:30 ET daily (after eod digest).
"""
import logging
from datetime import datetime
from config import CITIES, MIN_EDGE as DEFAULT_MIN_EDGE
from database import (
    agent_get, agent_set, pause_city, city_is_paused,
    journal_write, get_recent_city_trades, get_brier_recent,
    get_city_performance, get_summary,
)

log = logging.getLogger(__name__)

# Guardrail bounds
MIN_EDGE_FLOOR = 0.05   # never go below 5%
MIN_EDGE_CEIL  = 0.20   # never go above 20%
EDGE_STEP      = 0.02
BRIER_POOR     = 0.35
BRIER_GOOD     = 0.25
COOLDOWN_TRADES_WINDOW = 5   # look at last N resolved
COOLDOWN_LOSS_TRIGGER  = 3   # pause if >=3 losses in window
COOLDOWN_STREAK        = 3   # also pause on N-in-a-row losses regardless of window
COOLDOWN_HOURS         = 48


def effective_min_edge() -> float:
    """Read the agent's current MIN_EDGE, or fall back to config default."""
    val = agent_get("min_edge")
    if val is None:
        return DEFAULT_MIN_EDGE
    try:
        return float(val)
    except (TypeError, ValueError):
        return DEFAULT_MIN_EDGE


def _analyze_cities() -> list[dict]:
    """For each city, check streak and flag if it needs pausing."""
    findings = []
    for city in CITIES.keys():
        paused, paused_reason = city_is_paused(city)
        recent = get_recent_city_trades(city, limit=COOLDOWN_TRADES_WINDOW)
        losses = sum(1 for t in recent if t["status"] == "lost")
        wins = sum(1 for t in recent if t["status"] == "won")
        # Consecutive losses from most-recent back (`recent` is sorted DESC)
        streak = 0
        for t in recent:
            if t["status"] == "lost":
                streak += 1
            else:
                break
        findings.append({
            "city": city,
            "paused": paused,
            "paused_reason": paused_reason,
            "recent_losses": losses,
            "recent_wins": wins,
            "recent_samples": len(recent),
            "loss_streak": streak,
        })
    return findings


def _analyze_calibration() -> dict:
    """Rolling Brier + overall stats."""
    recent = get_brier_recent(days=14)
    lifetime_summary = get_summary()
    return {"recent_14d": recent, "lifetime": lifetime_summary}


def _decide_edge_move(brier_recent: dict, current_edge: float) -> tuple[float, str]:
    """Return (new_edge, rationale). new_edge == current_edge means no change."""
    samples = brier_recent.get("samples", 0)
    brier = brier_recent.get("brier")
    if samples < 10 or brier is None:
        return current_edge, f"Not enough settled signals ({samples}/10) to move edge"
    if brier > BRIER_POOR:
        new = min(MIN_EDGE_CEIL, round(current_edge + EDGE_STEP, 3))
        if new == current_edge:
            return current_edge, f"Brier {brier} poor but MIN_EDGE already at ceiling {MIN_EDGE_CEIL}"
        return new, f"Brier {brier} > {BRIER_POOR} — raise MIN_EDGE {current_edge} -> {new}"
    if brier < BRIER_GOOD:
        new = max(MIN_EDGE_FLOOR, round(current_edge - EDGE_STEP, 3))
        if new == current_edge:
            return current_edge, f"Brier {brier} good but MIN_EDGE already at floor {MIN_EDGE_FLOOR}"
        return new, f"Brier {brier} < {BRIER_GOOD} — lower MIN_EDGE {current_edge} -> {new}"
    return current_edge, f"Brier {brier} in normal range — hold MIN_EDGE at {current_edge}"


def _send_digest(lines: list[str]) -> None:
    """Best-effort Telegram digest. Uses monitor.send_telegram if available."""
    try:
        from monitor import send_telegram
        send_telegram("<b>WeatherAlpha Learning Agent</b>\n" + "\n".join(lines))
    except Exception as exc:
        log.warning("Digest send failed: %s", exc)


def run_review() -> dict:
    """Main entry — returns a summary dict for the API/Telegram."""
    started = datetime.utcnow().isoformat()
    log.info("Learning agent review starting at %s", started)

    calibration = _analyze_calibration()
    city_findings = _analyze_cities()
    current_edge = effective_min_edge()

    journal_write(
        "observation",
        f"Review started. Lifetime WR={calibration['lifetime']['win_rate']} "
        f"PnL=${calibration['lifetime']['total_pnl_usd']}. "
        f"Recent 14d Brier={calibration['recent_14d'].get('brier')} "
        f"samples={calibration['recent_14d'].get('samples')}",
        subject="review_start",
        data={"calibration": calibration, "cities": city_findings, "current_min_edge": current_edge},
    )

    actions = []
    digest_lines = []

    # --- Decision 1: per-city cooldowns ---
    for f in city_findings:
        if f["paused"]:
            digest_lines.append(f"⏸ {f['city']} already paused: {f['paused_reason']}")
            continue
        trigger_reason = None
        if f["loss_streak"] >= COOLDOWN_STREAK:
            trigger_reason = f"{f['loss_streak']} consecutive losses"
        elif (f["recent_samples"] >= COOLDOWN_TRADES_WINDOW
              and f["recent_losses"] >= COOLDOWN_LOSS_TRIGGER):
            trigger_reason = f"{f['recent_losses']}/{f['recent_samples']} losses in last {COOLDOWN_TRADES_WINDOW}"
        if trigger_reason:
            pause_city(f["city"], COOLDOWN_HOURS, trigger_reason)
            journal_write(
                "action",
                f"Paused {f['city']} for {COOLDOWN_HOURS}h — {trigger_reason}",
                subject=f["city"],
                data=f,
            )
            actions.append(f"Paused {f['city']}: {trigger_reason}")
            digest_lines.append(f"🛑 PAUSED {f['city']} 48h — {trigger_reason}")

    # --- Decision 2: dynamic MIN_EDGE move ---
    new_edge, edge_reason = _decide_edge_move(calibration["recent_14d"], current_edge)
    if new_edge != current_edge:
        agent_set("min_edge", new_edge)
        journal_write(
            "action",
            edge_reason,
            subject="min_edge",
            data={"from": current_edge, "to": new_edge,
                  "brier": calibration["recent_14d"].get("brier"),
                  "samples": calibration["recent_14d"].get("samples")},
        )
        actions.append(f"MIN_EDGE {current_edge} -> {new_edge}")
        digest_lines.append(f"📊 MIN_EDGE: {current_edge} -> {new_edge} ({edge_reason})")
    else:
        digest_lines.append(f"📊 MIN_EDGE held at {current_edge} ({edge_reason})")

    if not actions:
        digest_lines.append("✅ No rule changes today.")

    # City snapshot in digest
    perf = get_city_performance()
    if perf:
        snapshot = ", ".join(
            f"{p['city']}:{p['wins']}-{p['losses']}({'+' if p['pnl_usd']>=0 else ''}${p['pnl_usd']:.0f})"
            for p in perf
        )
        digest_lines.append(f"Cities: {snapshot}")

    summary = {
        "timestamp": started,
        "actions": actions,
        "city_findings": city_findings,
        "calibration": calibration,
        "min_edge_before": current_edge,
        "min_edge_after": effective_min_edge(),
    }

    journal_write(
        "digest",
        " | ".join(digest_lines),
        subject="review_end",
        data=summary,
    )
    agent_set("last_review_at", started)

    _send_digest(digest_lines)
    log.info("Learning agent review complete: %d action(s)", len(actions))
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_review()
    print(result)
