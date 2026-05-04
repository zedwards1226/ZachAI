"""Per-strategy auto-pause grader.

Runs nightly. For each strategy that has placed enough settled trades,
computes win rate + realized P&L over the review window. If a strategy
falls below the bar (win rate < MIN_WINRATE *and* P&L < 0, both with
sufficient sample), pauses it. Pauses are auto; resumes are manual
(`UPDATE strategy_state SET paused_at=NULL WHERE strategy_name=...`).

The bot's job_strategy_poll loop calls is_strategy_paused() before each
scan and skips paused strategies entirely.

Why this exists:
  Calibration was a one-shot historical analysis. Live markets shift —
  a strategy that calibrated at 95% YES rate in March can degrade by
  June without anyone noticing until P&L cracks. The grader closes
  that loop: actual settled trades feed back into automated risk-off
  before manual intervention is needed.

Conservative on purpose:
  - Need MIN_TRADES settled trades in review window to trust the signal
  - Pauses ONLY when BOTH win rate is bad AND P&L is negative (one alone
    can be unlucky variance — both together is real degradation)
  - Never auto-resumes (operator decides when fixed)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from data_layer.database import get_conn

logger = logging.getLogger(__name__)

# ── Tunables ─────────────────────────────────────────────────────────────
REVIEW_WINDOW_DAYS = 30      # rolling lookback
MIN_TRADES = 20              # need at least this many settled trades to grade
MIN_WINRATE = 0.50           # below this = candidate for pause
                              # (calibrated bands forecast 60-95%; 50% is "much worse than predicted")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_strategy_paused(strategy_name: str) -> bool:
    """Return True if the strategy has been auto-paused. Cheap O(1) check
    used in the hot path of job_strategy_poll."""
    with get_conn(readonly=True) as conn:
        row = conn.execute(
            "SELECT paused_at FROM strategy_state WHERE strategy_name = ?",
            (strategy_name,),
        ).fetchone()
    return bool(row and row["paused_at"])


def grade_strategies() -> dict:
    """One pass: review every strategy that has settled trades in the
    window and decide whether to pause. Returns a summary dict for logging
    + the dashboard.
    """
    cutoff_iso = (datetime.now(timezone.utc)
                  - timedelta(days=REVIEW_WINDOW_DAYS)).isoformat()
    summary: dict = {
        "ts": _now_iso(),
        "window_days": REVIEW_WINDOW_DAYS,
        "by_strategy": {},
        "paused_this_run": [],
    }

    with get_conn() as conn:
        # Aggregate per strategy over the review window. resolved_at is
        # set when trade_monitor settles the trade.
        rows = conn.execute(
            """
            SELECT strategy,
                   COUNT(*)                                                  n,
                   SUM(CASE WHEN status='won'  THEN 1 ELSE 0 END)            wins,
                   SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END)            losses,
                   COALESCE(SUM(pnl_usd), 0)                                 pnl
            FROM trades
            WHERE status IN ('won','lost')
              AND COALESCE(resolved_at, timestamp, '') >= ?
            GROUP BY strategy
            """,
            (cutoff_iso,),
        ).fetchall()

        for row in rows:
            name = row["strategy"]
            n = int(row["n"])
            wins = int(row["wins"])
            pnl = float(row["pnl"] or 0)
            winrate = wins / n if n else 0.0

            entry = {
                "n": n, "wins": wins, "losses": int(row["losses"]),
                "winrate": winrate, "pnl_usd": pnl,
                "decision": "skip", "reason": "",
            }

            # Decide: pause only if BOTH signals are bad (and sample is real).
            if n < MIN_TRADES:
                entry["decision"] = "skip"
                entry["reason"] = f"not enough trades (n={n} < {MIN_TRADES})"
            elif winrate < MIN_WINRATE and pnl < 0:
                entry["decision"] = "pause"
                entry["reason"] = (
                    f"winrate {winrate*100:.1f}% < {MIN_WINRATE*100:.0f}% "
                    f"and P&L ${pnl:+.2f} < 0 over n={n}"
                )
            elif winrate < MIN_WINRATE:
                entry["decision"] = "watch"
                entry["reason"] = (
                    f"low winrate {winrate*100:.1f}% but P&L positive ${pnl:+.2f} (variance)"
                )
            elif pnl < 0:
                entry["decision"] = "watch"
                entry["reason"] = (
                    f"negative P&L ${pnl:+.2f} but winrate {winrate*100:.1f}% holding"
                )
            else:
                entry["decision"] = "active"
                entry["reason"] = "healthy"

            # Persist last_review fields no matter what; only set paused_at on pause.
            now = _now_iso()
            paused_at_clause = ", paused_at = ?" if entry["decision"] == "pause" else ""
            params: list = [name, now, n, winrate, pnl, entry["reason"]]
            if entry["decision"] == "pause":
                params.append(now)

            # Upsert via INSERT ... ON CONFLICT (SQLite 3.24+, Python ships 3.x bundled).
            sql = f"""
                INSERT INTO strategy_state (
                    strategy_name, last_review_at, last_review_n,
                    last_review_winrate, last_review_pnl, pause_reason
                    {paused_at_clause}
                ) VALUES (?, ?, ?, ?, ?, ? {', ?' if entry['decision'] == 'pause' else ''})
                ON CONFLICT(strategy_name) DO UPDATE SET
                    last_review_at = excluded.last_review_at,
                    last_review_n = excluded.last_review_n,
                    last_review_winrate = excluded.last_review_winrate,
                    last_review_pnl = excluded.last_review_pnl,
                    pause_reason = excluded.pause_reason
                    {(', paused_at = excluded.paused_at') if entry['decision'] == 'pause' else ''}
            """
            conn.execute(sql, params)

            if entry["decision"] == "pause":
                summary["paused_this_run"].append(name)
                logger.warning(
                    "PAUSING strategy %s — %s", name, entry["reason"],
                )
                # Telegram alert (best-effort, don't crash the grader on failure)
                try:
                    from bots import telegram_alerts
                    telegram_alerts.send(
                        f"⚠️ <b>OmniAlpha auto-paused strategy</b>: <code>{name}</code>\n"
                        f"{entry['reason']}\n"
                        f"Resume manually:\n"
                        f"<code>UPDATE strategy_state SET paused_at=NULL "
                        f"WHERE strategy_name='{name}'</code>"
                    )
                except Exception as e:
                    logger.warning("pause telegram failed: %s", e)
            else:
                logger.info(
                    "grade %s: %s — n=%d winrate=%.1f%% pnl=$%+.2f",
                    name, entry["decision"], n, winrate * 100, pnl,
                )

            summary["by_strategy"][name] = entry

    return summary
