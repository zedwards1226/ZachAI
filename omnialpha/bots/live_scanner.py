"""Live universe scanner — pulls ACTIVE markets from Kalshi's PUBLIC
/markets endpoint, builds MarketSnapshots, hands them to the strategy.

`/markets` is unauthenticated for the basic listing — same as
`/historical/markets`. So OmniAlpha can poll the live universe and run
strategies against it WITHOUT needing the user to populate Kalshi
credentials in .env. Order placement is what needs credentials, but
since we're paper-mode-only right now, no auth needed at all.

This module is the missing piece between Phase 2 (backtest works) and
"the bot actually trades" (paper). Adds one APScheduler job that runs
every 60s during the trading window, snapshots active markets in
enabled sectors, and runs each through the strategy.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterator

import httpx

from bots import order_placer, telegram_alerts
from bots.kalshi_public import classify_sector, market_row_from_api
from bots.risk_engine import check_entry
from config import KALSHI_API_BASE
from data_layer.database import get_conn
from data_layer.historical_pull import upsert_market
from strategies.base import MarketSnapshot, Strategy, StrategyContext

logger = logging.getLogger(__name__)


# Live polling: 1 req per series per cycle. Kalshi free tier is 100 req/min.
HTTP_TIMEOUT_S = 15.0


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=KALSHI_API_BASE,
        timeout=HTTP_TIMEOUT_S,
        headers={"User-Agent": "ZachAI-OmniAlpha/0.1"},
    )


def fetch_active_markets(
    *,
    series_ticker: str,
    limit: int = 200,
) -> list[dict]:
    """Pull active markets in a series. status=open returns markets still
    accepting trades; status=active also returns markets that have opened
    but may not be tradeable yet."""
    with _client() as client:
        r = client.get(
            "/markets",
            params={
                "limit": limit,
                "series_ticker": series_ticker,
                "status": "open",  # actively trading right now
            },
        )
        r.raise_for_status()
        return r.json().get("markets", []) or []


def _market_to_snapshot(m: dict) -> MarketSnapshot | None:
    """Build a MarketSnapshot from a live /markets response payload.
    Returns None if the market is malformed or already closed."""
    ticker = m.get("ticker") or ""
    if not ticker:
        return None
    # Skip markets that aren't real binary trades (e.g. multivariate
    # cross-category combos, scalar markets we don't model)
    if m.get("market_type") != "binary":
        return None

    last = _safe_float(m.get("last_price_dollars"))
    yes_ask = _safe_float(m.get("yes_ask_dollars"))
    yes_bid = _safe_float(m.get("yes_bid_dollars"))
    no_ask = _safe_float(m.get("no_ask_dollars"))
    no_bid = _safe_float(m.get("no_bid_dollars"))
    volume = _safe_float(m.get("volume_fp")) or 0.0

    # If the market hasn't traded yet, fall back to mid of bid/ask
    if last is None or last == 0:
        if yes_ask and yes_bid:
            last = (yes_ask + yes_bid) / 2
        elif yes_ask:
            last = yes_ask
        else:
            return None  # un-traded, no quotes
    last_cents = int(round(last * 100))

    yes_ask_cents = int(round((yes_ask or last) * 100))
    no_ask_cents = int(round((no_ask or (1 - last)) * 100))
    yes_bid_cents = int(round((yes_bid or max(0, last - 0.01)) * 100))
    no_bid_cents = int(round((no_bid or max(0, (1 - last) - 0.01)) * 100))

    open_time = m.get("open_time") or ""
    close_time = m.get("close_time") or ""
    seconds_to_close = _seconds_until(close_time)

    return MarketSnapshot(
        ticker=ticker,
        sector=classify_sector(ticker),
        series_ticker=ticker.split("-", 1)[0] if "-" in ticker else None,
        title=m.get("title") or m.get("yes_sub_title") or "",
        open_time=open_time,
        close_time=close_time,
        yes_ask_cents=yes_ask_cents,
        yes_bid_cents=yes_bid_cents,
        no_ask_cents=no_ask_cents,
        no_bid_cents=no_bid_cents,
        last_price_cents=last_cents,
        volume_fp=volume,
        open_interest_fp=_safe_float(m.get("open_interest_fp")) or 0.0,
        seconds_to_close=seconds_to_close,
        extras={
            "strike_type": m.get("strike_type"),
            "floor_strike": _safe_float(m.get("floor_strike")),
            "cap_strike": _safe_float(m.get("cap_strike")),
            "yes_sub_title": m.get("yes_sub_title"),
        },
    )


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _seconds_until(iso_ts: str) -> int:
    if not iso_ts:
        return 0
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return int((dt - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return 0


def _build_context(sector: str, capital_usd: float) -> StrategyContext:
    """Read live state from DB to populate StrategyContext.

    Single read-only connection, four queries. Caller should cache the
    result per scan-pass — context is sector-scoped, not per-market.
    """
    from datetime import timedelta
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    with get_conn(readonly=True) as conn:
        daily_pnl = float(conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
            "WHERE substr(timestamp, 1, 10) = ? AND status IN ('won','lost')",
            (today,),
        ).fetchone()[0])
        weekly_pnl = float(conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
            "WHERE timestamp >= ? AND status IN ('won','lost')",
            (week_ago,),
        ).fetchone()[0])
        open_count = int(conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status = 'open'"
        ).fetchone()[0])
        recent = conn.execute(
            "SELECT status FROM trades WHERE sector = ? AND status IN ('won','lost') "
            "ORDER BY id DESC LIMIT 20",
            (sector,),
        ).fetchall()
    consec = 0
    for r in recent:
        if r["status"] == "lost":
            consec += 1
        else:
            break
    return StrategyContext(
        capital_usd=capital_usd,
        open_positions_count=open_count,
        daily_realized_pnl_usd=daily_pnl,
        weekly_realized_pnl_usd=weekly_pnl,
        sector=sector,
        consecutive_losses_in_sector=consec,
    )


def _market_already_taken(ticker: str) -> bool:
    """Refuse re-entry to a market we already have a position in.

    KXBTC15M tickers are unique per 15-minute window — Kalshi never reuses
    them. So checking by ticker alone is correct semantics: if we have ANY
    non-failed trade against this ticker (even from yesterday), we don't
    re-enter — that ticker's market is gone.
    """
    with get_conn(readonly=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM trades WHERE market_ticker = ? "
            "AND status != 'failed_placement' LIMIT 1",
            (ticker,),
        ).fetchone()
    return row is not None


def scan_and_trade(
    strategy: Strategy,
    *,
    series_ticker: str,
    capital_usd: float,
) -> dict:
    """One scanner pass: pull active markets in a series, run strategy on
    each, place paper orders for approved entries. Returns counts.

    Side effects:
      - Upserts each scanned market into the markets table so
        `trade_monitor` can later look up its resolution and settle the trade.
      - Routes order placement through `order_placer.place()` (the dispatcher)
        so the live-mode gate is honored on the same path the live cutover
        will use.
    """
    try:
        markets = fetch_active_markets(series_ticker=series_ticker)
    except Exception as e:
        logger.warning("fetch_active_markets failed for %s: %s", series_ticker, e)
        return {"scanned": 0, "snapshots": 0, "decisions": 0, "approved": 0, "placed": 0}

    n_snapshots = 0
    n_decisions = 0
    n_approved = 0
    n_placed = 0
    n_blocked: dict[str, int] = {}

    # Build StrategyContext ONCE per sector — context is sector-scoped so
    # rebuilding per market just multiplies DB round-trips (200 markets ×
    # 4 queries = 800 round-trips/cycle). One sector here = "crypto", but
    # generalizing for the day a multi-sector poll is added.
    ctx_cache: dict[str, StrategyContext] = {}

    # First pass: upsert all markets in ONE write transaction, then release.
    # Holding the write conn open across order_placer.place() causes SQLite
    # lock contention since order_placer opens its own write connection.
    snaps: list[tuple[dict, MarketSnapshot]] = []
    with get_conn() as conn:
        for raw in markets:
            snap = _market_to_snapshot(raw)
            if snap is None:
                continue
            n_snapshots += 1
            try:
                upsert_market(conn, market_row_from_api(raw))
            except Exception as e:
                logger.warning("upsert_market failed for %s: %s", snap.ticker, e)
            snaps.append((raw, snap))
    # Write lock released. Now run strategy + place orders.

    for raw, snap in snaps:
        if _market_already_taken(snap.ticker):
            continue

        if snap.sector not in ctx_cache:
            ctx_cache[snap.sector] = _build_context(
                sector=snap.sector, capital_usd=capital_usd,
            )
        ctx = ctx_cache[snap.sector]

        decision = strategy.decide_entry(snap, ctx)
        if decision is None:
            continue
        n_decisions += 1

        verdict = check_entry(decision, snap, ctx)
        if not verdict.approved:
            n_blocked[verdict.reason] = n_blocked.get(verdict.reason, 0) + 1
            continue
        n_approved += 1

        if verdict.clamped_contracts != decision.contracts:
            decision = replace(decision, contracts=verdict.clamped_contracts)

        try:
            placement = order_placer.place(
                decision=decision,
                market_ticker=snap.ticker,
                sector=snap.sector,
                strategy_name=strategy.name,
                kalshi_client=None,
            )
            n_placed += 1
            stake = placement["stake_usd"]
            try:
                telegram_alerts.notify_entry(
                    sector=snap.sector,
                    strategy=strategy.name,
                    market=snap.ticker,
                    side=decision.side,
                    contracts=decision.contracts,
                    price_cents=decision.price_cents,
                    stake_usd=stake,
                    edge=decision.edge,
                )
            except Exception as e:
                logger.warning("entry telegram failed: %s", e)
        except Exception as e:
            logger.exception("place order failed: %s", e)

    return {
        "scanned": len(markets),
        "snapshots": n_snapshots,
        "decisions": n_decisions,
        "approved": n_approved,
        "placed": n_placed,
        **{f"blocked_{k}": v for k, v in n_blocked.items()},
    }
