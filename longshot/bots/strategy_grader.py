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

# Hard floor — even on cheap NO entries (e.g. 0.30) we want SOME absolute
# WR signal. 0.50 = "the bot is doing worse than a coinflip" regardless
# of entry price. Used as a max() with the dynamic break-even threshold.
MIN_WINRATE_FLOOR = 0.50

# Margin added to break-even WR. Covers Kalshi fees (~0.5-1c per contract
# on settled trades) + spread/slippage. Without this, a strategy exactly
# at break-even WR would still slowly bleed.
WR_BREAKEVEN_MARGIN = 0.02

# Audit 2026-05-17 fix O1: the old flat MIN_WINRATE=0.50 let btcd run
# 92 paper trades at 68.5% WR with avg entry 75.9c (break-even WR = 75%)
# before any pause triggered. New rule: pause if WR < max(0.50, avg_entry + 2%).


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


# ── Per-SPORT (per-series) grading ────────────────────────────────────────
# A single strategy (e.g. longshot_fade) can run across many sports/series.
# Grading the whole strategy together would pause ALL sports the moment the
# aggregate cracks — even if only one sport (say NHL) is the bleeder. These
# functions grade each SERIES independently, keyed in strategy_state by a
# composite "strategy@SERIES" name so we reuse the same table + pause check.

def _series_key(market_ticker: str) -> str:
    """Series prefix = everything before the first '-'.
    e.g. 'KXMLBGAME-26MAY272210COLLAD-COL' → 'KXMLBGAME'."""
    return market_ticker.split("-", 1)[0] if "-" in market_ticker else market_ticker


def _composite(strategy_name: str, series: str) -> str:
    return f"{strategy_name}@{series}"


def is_series_paused(strategy_name: str, market_ticker: str) -> bool:
    """Cheap hot-path check: is THIS sport auto-paused for THIS strategy?
    Used by the live scanner before evaluating each market."""
    key = _composite(strategy_name, _series_key(market_ticker))
    with get_conn(readonly=True) as conn:
        row = conn.execute(
            "SELECT paused_at FROM strategy_state WHERE strategy_name = ?",
            (key,),
        ).fetchone()
    return bool(row and row["paused_at"])


def grade_series_for_strategy(strategy_name: str) -> dict:
    """Grade each SERIES (sport) the strategy traded over the review window,
    independently. Pauses a series (composite key strategy@SERIES) when its
    win rate is below the dynamic break-even AND its P&L is negative, with a
    real sample. Same conservative both-signals-bad rule as grade_strategies.

    Returns a summary dict for logging + dashboard.
    """
    cutoff_iso = (datetime.now(timezone.utc)
                  - timedelta(days=REVIEW_WINDOW_DAYS)).isoformat()
    summary: dict = {
        "ts": _now_iso(),
        "strategy": strategy_name,
        "window_days": REVIEW_WINDOW_DAYS,
        "by_series": {},
        "paused_this_run": [],
    }

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT market_ticker, status, pnl_usd, price_cents
            FROM trades
            WHERE strategy = ?
              AND status IN ('won','lost')
              AND COALESCE(resolved_at, timestamp, '') >= ?
            """,
            (strategy_name, cutoff_iso),
        ).fetchall()

    # Aggregate by series in Python (sqlite can't easily group by a prefix).
    agg: dict[str, dict] = {}
    for r in rows:
        s = _series_key(r["market_ticker"])
        a = agg.setdefault(s, {"n": 0, "wins": 0, "losses": 0, "pnl": 0.0, "entry_sum": 0})
        a["n"] += 1
        a["pnl"] += float(r["pnl_usd"] or 0)
        a["entry_sum"] += int(r["price_cents"] or 0)
        if r["status"] == "won":
            a["wins"] += 1
        else:
            a["losses"] += 1

    now = _now_iso()
    with get_conn() as conn:
        for series, a in agg.items():
            n = a["n"]
            winrate = a["wins"] / n if n else 0.0
            pnl = a["pnl"]
            avg_entry = (a["entry_sum"] / n / 100.0) if n else 0.0
            break_even_wr = max(MIN_WINRATE_FLOOR, avg_entry + WR_BREAKEVEN_MARGIN)
            key = _composite(strategy_name, series)

            if n < MIN_TRADES:
                decision, reason = "skip", f"not enough trades (n={n} < {MIN_TRADES})"
            elif winrate < break_even_wr and pnl < 0:
                decision, reason = "pause", (
                    f"WR {winrate*100:.1f}% < break-even {break_even_wr*100:.1f}% "
                    f"AND P&L ${pnl:+.2f} < 0 over n={n}"
                )
            elif winrate < break_even_wr:
                decision, reason = "watch", (
                    f"low WR {winrate*100:.1f}% but P&L +${pnl:.2f} (variance)"
                )
            elif pnl < 0:
                decision, reason = "watch", (
                    f"neg P&L ${pnl:+.2f} but WR {winrate*100:.1f}% ok (asymmetric)"
                )
            else:
                decision, reason = "active", f"healthy (WR {winrate*100:.1f}%)"

            entry = {"n": n, "wins": a["wins"], "losses": a["losses"],
                     "winrate": winrate, "pnl_usd": pnl, "avg_entry": avg_entry,
                     "break_even_wr": break_even_wr, "decision": decision,
                     "reason": reason}
            summary["by_series"][series] = entry

            is_pause = decision == "pause"
            if is_pause:
                conn.execute(
                    "INSERT INTO strategy_state (strategy_name, last_review_at, "
                    "last_review_n, last_review_winrate, last_review_pnl, "
                    "pause_reason, paused_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(strategy_name) DO UPDATE SET "
                    "last_review_at=excluded.last_review_at, "
                    "last_review_n=excluded.last_review_n, "
                    "last_review_winrate=excluded.last_review_winrate, "
                    "last_review_pnl=excluded.last_review_pnl, "
                    "pause_reason=excluded.pause_reason, "
                    "paused_at=excluded.paused_at",
                    [key, now, n, winrate, pnl, reason, now],
                )
                summary["paused_this_run"].append(series)
                logger.warning("PAUSING sport %s for %s — %s", series, strategy_name, reason)
                try:
                    from bots import telegram_alerts
                    telegram_alerts.send(
                        f"⚠️ <b>I paused {series}</b>\n"
                        f"The {series} sport has been losing too often for the "
                        f"longshot-fade strategy ({reason}). Stopped trading it so "
                        f"it doesn't keep bleeding.\n\n"
                        f"<i>Other sports keep trading. To re-enable, clear its "
                        f"row in strategy_state.</i>"
                    )
                except Exception as e:
                    logger.warning("series-pause telegram failed: %s", e)
            else:
                conn.execute(
                    "INSERT INTO strategy_state (strategy_name, last_review_at, "
                    "last_review_n, last_review_winrate, last_review_pnl, "
                    "pause_reason) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(strategy_name) DO UPDATE SET "
                    "last_review_at=excluded.last_review_at, "
                    "last_review_n=excluded.last_review_n, "
                    "last_review_winrate=excluded.last_review_winrate, "
                    "last_review_pnl=excluded.last_review_pnl, "
                    "pause_reason=excluded.pause_reason",
                    [key, now, n, winrate, pnl, reason],
                )
                logger.info("grade %s: %s — n=%d WR=%.1f%% pnl=$%+.2f",
                            key, decision, n, winrate * 100, pnl)

    return summary


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
                   COALESCE(SUM(pnl_usd), 0)                                 pnl,
                   COALESCE(AVG(price_cents), 0)                             avg_entry_cents
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
            avg_entry = float(row["avg_entry_cents"] or 0) / 100.0  # 0.0-1.0

            # Dynamic break-even WR: at entry price p, you need to win p
            # fraction of the time just to cover the stake. Add margin
            # to cover fees + slippage. Use MIN_WINRATE_FLOOR as a hard
            # absolute minimum so cheap-NO strategies still get a sanity
            # check.
            break_even_wr = max(MIN_WINRATE_FLOOR, avg_entry + WR_BREAKEVEN_MARGIN)

            entry = {
                "n": n, "wins": wins, "losses": int(row["losses"]),
                "winrate": winrate, "pnl_usd": pnl,
                "avg_entry": avg_entry, "break_even_wr": break_even_wr,
                "decision": "skip", "reason": "",
            }

            # Decide: pause only if BOTH signals are bad (and sample is real).
            if n < MIN_TRADES:
                entry["decision"] = "skip"
                entry["reason"] = f"not enough trades (n={n} < {MIN_TRADES})"
            elif winrate < break_even_wr and pnl < 0:
                entry["decision"] = "pause"
                entry["reason"] = (
                    f"winrate {winrate*100:.1f}% < break_even {break_even_wr*100:.1f}% "
                    f"(avg entry {avg_entry*100:.1f}c + margin) and P&L ${pnl:+.2f} < 0 over n={n}"
                )
            elif winrate < break_even_wr:
                entry["decision"] = "watch"
                entry["reason"] = (
                    f"low winrate {winrate*100:.1f}% vs break_even {break_even_wr*100:.1f}% "
                    f"but P&L positive ${pnl:+.2f} (variance — watch for reversion)"
                )
            elif pnl < 0:
                entry["decision"] = "watch"
                entry["reason"] = (
                    f"negative P&L ${pnl:+.2f} but winrate {winrate*100:.1f}% "
                    f">= break_even {break_even_wr*100:.1f}% (asymmetric losses — investigate)"
                )
            else:
                entry["decision"] = "active"
                entry["reason"] = f"healthy (WR {winrate*100:.1f}% vs break_even {break_even_wr*100:.1f}%)"

            # Persist last_review fields no matter what; only set paused_at
            # on pause. Latent bug fix 2026-05-17: the old f-string built
            # ", paused_at = ?" into the INSERT column list (invalid SQL —
            # column-list entries are bare names). Bug never fired because
            # the old flat MIN_WINRATE never triggered a pause; the new
            # break-even threshold would expose it. Rewritten as two
            # explicit branches.
            now = _now_iso()
            is_pause = entry["decision"] == "pause"
            if is_pause:
                sql = """
                    INSERT INTO strategy_state (
                        strategy_name, last_review_at, last_review_n,
                        last_review_winrate, last_review_pnl, pause_reason,
                        paused_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strategy_name) DO UPDATE SET
                        last_review_at = excluded.last_review_at,
                        last_review_n = excluded.last_review_n,
                        last_review_winrate = excluded.last_review_winrate,
                        last_review_pnl = excluded.last_review_pnl,
                        pause_reason = excluded.pause_reason,
                        paused_at = excluded.paused_at
                """
                params = [name, now, n, winrate, pnl, entry["reason"], now]
            else:
                sql = """
                    INSERT INTO strategy_state (
                        strategy_name, last_review_at, last_review_n,
                        last_review_winrate, last_review_pnl, pause_reason
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strategy_name) DO UPDATE SET
                        last_review_at = excluded.last_review_at,
                        last_review_n = excluded.last_review_n,
                        last_review_winrate = excluded.last_review_winrate,
                        last_review_pnl = excluded.last_review_pnl,
                        pause_reason = excluded.pause_reason
                """
                params = [name, now, n, winrate, pnl, entry["reason"]]
            conn.execute(sql, params)

            if entry["decision"] == "pause":
                summary["paused_this_run"].append(name)
                logger.warning(
                    "PAUSING strategy %s — %s", name, entry["reason"],
                )
                # Telegram alert (best-effort, don't crash the grader on failure)
                try:
                    from bots import telegram_alerts
                    from bots.strategy_labels import label_strategy, short_resume_hint
                    pretty = label_strategy(name)
                    hint = short_resume_hint(name)
                    telegram_alerts.send(
                        f"⚠️ <b>I paused a strategy</b>\n"
                        f"The {pretty} strategy has been losing too often "
                        f"({entry['reason']}). I've stopped it from placing "
                        f"new trades so it doesn't keep bleeding while we "
                        f"figure out what's wrong.\n\n"
                        f"<i>To turn it back on, ask Jarvis: "
                        f"\"resume {hint}\".</i>"
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
