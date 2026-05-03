"""Trade monitor — settles open paper trades when their underlying
markets resolve, computes P&L, journals the result, sends Telegram alert.

For paper-mode KXBTC15M markets:
  1. Find all open trades (status='open')
  2. For each, query the historical store (or live API for fresh markets)
     to see if the market resolved
  3. If resolved, compute P&L and call mark_resolved()

For LIVE markets (post-paper cutover): hits the authenticated /portfolio/fills
endpoint to see actual fills + settlement values.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from bots.order_placer import mark_resolved
from data_layer.database import get_conn

logger = logging.getLogger(__name__)

# Kalshi binary fee on winning side
KALSHI_FEE_RATE = 0.07


def _open_trades(paper_only: bool = True) -> Iterable[dict]:
    sql = "SELECT * FROM trades WHERE status = 'open'"
    if paper_only:
        sql += " AND paper = 1"
    with get_conn(readonly=True) as conn:
        for row in conn.execute(sql):
            yield dict(row)


def _market_result(ticker: str) -> Optional[dict]:
    """Return {result, settlement_value_dollars, status} or None if not yet resolved.

    Two-stage lookup:
      1. Local DB — fast path for markets we've already ingested as finalized
      2. Live /markets/{ticker} API — fallback for markets that closed
         after our last ingestion. If we find one settled, we ALSO update
         our local row so subsequent queries hit the fast path.
    """
    # Stage 1: local DB
    with get_conn(readonly=True) as conn:
        row = conn.execute(
            "SELECT result, settlement_value_dollars, status, raw_json "
            "FROM markets WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if row and row["status"] == "finalized" and row["result"] in ("yes", "no"):
        return dict(row)

    # Stage 2: live API fallback
    try:
        from bots.kalshi_public import get_market_status
        live = get_market_status(ticker)
    except Exception as e:
        logger.warning("get_market_status failed for %s: %s", ticker, e)
        return None
    if not live:
        return None
    status = live.get("status")
    result = live.get("result")
    if status != "finalized" or result not in ("yes", "no"):
        return None
    settlement = live.get("settlement_value_dollars") or live.get("settlement_value") or 0
    try:
        settlement_f = float(settlement)
    except (TypeError, ValueError):
        settlement_f = 0.0

    # Update local DB row so future settles use the fast path
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE markets SET status=?, result=?, "
                "settlement_value_dollars=?, last_updated_at=? "
                "WHERE ticker=?",
                (status, result, settlement_f,
                 datetime.now(timezone.utc).isoformat(),
                 ticker),
            )
    except Exception as e:
        logger.warning("could not update local market row %s: %s", ticker, e)

    return {
        "result": result,
        "settlement_value_dollars": settlement_f,
        "status": status,
    }


def _compute_pnl(trade: dict, market: dict) -> tuple[float, bool]:
    """Compute realized P&L for a settled paper trade. Mirrors backtest math."""
    result = market.get("result")
    side = trade["side"]
    p = int(trade["price_cents"])
    n = int(trade["contracts"])
    yes_won = (result == "yes")
    bet_won = (side == "yes" and yes_won) or (side == "no" and not yes_won)
    if bet_won:
        gross_cents = n * (100 - p)
        fee_cents = gross_cents * KALSHI_FEE_RATE
        net_usd = (gross_cents - fee_cents) / 100.0
        return net_usd, True
    loss_usd = (n * p) / 100.0
    return -loss_usd, False


def settle_resolved_trades() -> dict:
    """Walk all open paper trades, settle the ones whose markets have
    resolved. Returns counts."""
    n_settled = 0
    n_pending = 0
    n_won = 0
    n_lost = 0
    total_pnl = 0.0
    for trade in _open_trades(paper_only=True):
        market = _market_result(trade["market_ticker"])
        if not market:
            n_pending += 1
            continue
        pnl, won = _compute_pnl(trade, market)
        try:
            mark_resolved(
                trade_id=trade["id"],
                won=won,
                pnl_usd=pnl,
                settlement_value_dollars=float(market.get("settlement_value_dollars") or 0),
            )
            n_settled += 1
            if won:
                n_won += 1
            else:
                n_lost += 1
            total_pnl += pnl
            logger.info(
                "Settled trade %d: %s on %s → %s, P&L=$%.2f",
                trade["id"], trade["side"], trade["market_ticker"],
                "WON" if won else "LOST", pnl,
            )
            # Send Telegram alert
            try:
                from bots.telegram_alerts import notify_exit
                notify_exit(
                    sector=trade["sector"], strategy=trade["strategy"],
                    market=trade["market_ticker"], side=trade["side"],
                    pnl_usd=pnl, won=won, reason="resolved",
                )
            except Exception as e:
                logger.warning("Telegram exit notify failed: %s", e)
        except Exception as e:
            logger.error("Failed to mark trade %d resolved: %s", trade["id"], e)
    return {
        "settled": n_settled,
        "pending": n_pending,
        "wins": n_won,
        "losses": n_lost,
        "total_pnl_usd": total_pnl,
    }


def write_pnl_snapshot(starting_capital_usd: float) -> dict:
    """Periodic snapshot of capital + open risk. Driven by main.py scheduler."""
    now_iso = datetime.now(timezone.utc).isoformat()
    today = now_iso[:10]
    with get_conn() as conn:
        # Realized totals
        row = conn.execute(
            "SELECT "
            "  COUNT(*) total, "
            "  SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) wins, "
            "  SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) losses, "
            "  COALESCE(SUM(CASE WHEN status IN ('won','lost') THEN pnl_usd END), 0) realized_total, "
            "  SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) open_count, "
            "  COALESCE(SUM(CASE WHEN status='open' THEN stake_usd END), 0) open_risk "
            "FROM trades"
        ).fetchone()
        # Today's realized
        today_pnl_row = conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
            "WHERE substr(timestamp, 1, 10) = ? AND status IN ('won','lost')",
            (today,),
        ).fetchone()
        today_pnl = float(today_pnl_row[0])

        capital = starting_capital_usd + float(row["realized_total"] or 0)
        snap = {
            "timestamp": now_iso,
            "capital_usd": capital,
            "open_risk_usd": float(row["open_risk"] or 0),
            "realized_today": today_pnl,
            "realized_total": float(row["realized_total"] or 0),
            "open_positions": int(row["open_count"] or 0),
            "total_trades": int(row["total"] or 0),
            "total_wins": int(row["wins"] or 0),
            "total_losses": int(row["losses"] or 0),
        }
        conn.execute(
            "INSERT INTO pnl_snapshots ("
            "  timestamp, capital_usd, open_risk_usd, realized_today, realized_total, "
            "  open_positions, total_trades, total_wins, total_losses"
            ") VALUES ("
            "  :timestamp, :capital_usd, :open_risk_usd, :realized_today, :realized_total, "
            "  :open_positions, :total_trades, :total_wins, :total_losses"
            ")",
            snap,
        )
    return snap
