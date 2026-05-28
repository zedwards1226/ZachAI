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

import json

from bots import order_placer, telegram_alerts
from bots.kalshi_public import classify_sector, market_row_from_api
from bots.risk_engine import check_entry
from config import KALSHI_API_BASE
from data_layer.database import get_conn, log_decision
from data_layer.historical_pull import upsert_market
from strategies.base import MarketSnapshot, Strategy, StrategyContext

logger = logging.getLogger(__name__)


# Live polling: 1 req per series per cycle. Kalshi free tier is 100 req/min.
HTTP_TIMEOUT_S = 15.0

# Per-series 429 cooldown. When Kalshi returns 429 for a series, skip that
# series for RATE_LIMIT_COOLDOWN_S seconds instead of spamming retries every
# scheduler tick. Empirically fixes the May-11 log flood on KXETHD where the
# scanner was hammering the same throttled endpoint 30-60x per hour.
RATE_LIMIT_COOLDOWN_S = 300  # 5 minutes
_rate_limited_until: dict[str, datetime] = {}


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
    but may not be tradeable yet.

    Raises httpx.HTTPStatusError on non-2xx. Caller in scan_sector handles
    429 specifically by parking the series in a cooldown.
    """
    # Cooldown short-circuit: if this series was 429'd recently, don't hit
    # the wire — return empty so the scanner skips it for this cycle.
    cooldown_until = _rate_limited_until.get(series_ticker)
    if cooldown_until and datetime.now(timezone.utc) < cooldown_until:
        return []

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
    except httpx.HTTPStatusError as e:
        # 429 = Kalshi throttled this series. Park it in cooldown so the next
        # RATE_LIMIT_COOLDOWN_S of scheduler ticks skip the wire entirely
        # instead of hammering the throttled endpoint and spamming the log.
        if e.response.status_code == 429:
            cooldown_until = datetime.now(timezone.utc).replace(microsecond=0)
            from datetime import timedelta
            cooldown_until = cooldown_until + timedelta(seconds=RATE_LIMIT_COOLDOWN_S)
            _rate_limited_until[series_ticker] = cooldown_until
            logger.info(
                "Kalshi 429 for %s — series cooldown until %s (%ds)",
                series_ticker, cooldown_until.isoformat(), RATE_LIMIT_COOLDOWN_S,
            )
        else:
            logger.warning("fetch_active_markets HTTP error for %s: %s", series_ticker, e)
        return {"scanned": 0, "snapshots": 0, "decisions": 0, "approved": 0, "placed": 0}
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

    # Collect decisions in a list, flush in one write transaction at the end
    # of the pass — same pattern as the upsert above. Avoids one DB round-trip
    # per market, which matters at 100+ markets/cycle.
    decision_rows: list[tuple] = []
    now_iso_factory = lambda: datetime.now(timezone.utc).isoformat()

    for raw, snap in snaps:
        if _market_already_taken(snap.ticker):
            decision_rows.append((
                "skip", snap.sector,
                f"{snap.ticker} | already holding open position",
                json.dumps({"ticker": snap.ticker, "reason_code": "already_taken"}),
            ))
            continue

        if snap.sector not in ctx_cache:
            ctx_cache[snap.sector] = _build_context(
                sector=snap.sector, capital_usd=capital_usd,
            )
        ctx = ctx_cache[snap.sector]

        decision = strategy.decide_entry(snap, ctx)
        if decision is None:
            # Derive the SPECIFIC gate that killed it so the dashboard feed
            # is readable at a glance. Mirrors longshot_fade.py gate order.
            secs = snap.seconds_to_close
            no_ask = snap.no_ask_cents or 0
            vol = snap.volume_fp or 0
            sector = (snap.sector or "").lower()
            series = (snap.series_ticker or "").upper()
            if sector != "sports":
                reason_human = f"sector={snap.sector or '?'} (not sports)"
                reason_code = "sector"
            elif any(series.startswith(p) for p in (
                "KXEPL", "KXUCL", "KXLALIGA", "KXSERIE", "KXBUNDES",
                "KXLIGUE1", "KXMLS", "KXALEAGUE", "KXALLSVENSKAN",
            )):
                reason_human = f"series blocked — soccer ({series[:10]})"
                reason_code = "series_blocked"
            elif not any(series.startswith(p) for p in (
                "KXNBA", "KXNFL", "KXMLB", "KXNHL", "KXWNBA",
                "KXUFC", "KXATP", "KXWTA", "KXBOXING", "KXF1",
            )):
                reason_human = f"series not whitelisted ({series[:10]})"
                reason_code = "series_not_whitelisted"
            elif vol < 1000:
                reason_human = f"vol ${int(vol)} below $1k floor"
                reason_code = "low_volume"
            elif secs <= 0:
                reason_human = "market already closed"
                reason_code = "market_closed"
            elif secs < 1800:
                reason_human = f"{secs // 60}min to settle (need 30min+)"
                reason_code = "too_close_to_settle"
            elif secs > 14400:
                # express in days for far-out futures, hours otherwise
                if secs > 86400:
                    reason_human = f"{secs // 86400}d to settle (need <4hr)"
                else:
                    reason_human = f"{secs // 3600}hr to settle (need <4hr)"
                reason_code = "too_far_from_settle"
            elif no_ask < 85 or no_ask > 99:
                reason_human = f"no_ask {no_ask}¢ outside 85-99 band"
                reason_code = "price_out_of_band"
            else:
                # All universe gates passed, so EV/Kelly killed it
                reason_human = "EV under fee floor"
                reason_code = "ev_under_floor"

            decision_rows.append((
                "skip", snap.sector,
                f"{snap.ticker} | {reason_human}",
                json.dumps({
                    "ticker": snap.ticker,
                    "reason_code": reason_code,
                    "reason_human": reason_human,
                    "no_ask": snap.no_ask_cents,
                    "yes_ask": snap.yes_ask_cents,
                    "volume_fp": snap.volume_fp,
                    "secs_to_close": snap.seconds_to_close,
                }),
            ))
            continue
        n_decisions += 1

        verdict = check_entry(decision, snap, ctx, strategy_name=strategy.name)
        if not verdict.approved:
            n_blocked[verdict.reason] = n_blocked.get(verdict.reason, 0) + 1
            decision_rows.append((
                "risk_cap_hit", snap.sector,
                f"{snap.ticker} | risk gate: {verdict.reason}",
                json.dumps({
                    "ticker": snap.ticker,
                    "reason_code": verdict.reason,
                    "side": decision.side,
                    "contracts": decision.contracts,
                    "price_cents": decision.price_cents,
                }),
            ))
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
            decision_rows.append((
                "enter", snap.sector,
                f"{snap.ticker} | {decision.side.upper()} @ {decision.price_cents}¢ × {decision.contracts} = ${placement['stake_usd']:.2f}",
                json.dumps({
                    "ticker": snap.ticker,
                    "reason_code": "engaged",
                    "side": decision.side,
                    "contracts": decision.contracts,
                    "price_cents": decision.price_cents,
                    "stake_usd": placement["stake_usd"],
                    "edge": decision.edge,
                    "forecast_prob": decision.forecast_prob,
                    "strategy_reason": decision.reason,
                    "extras": decision.extras,
                }),
            ))
            # Invalidate sector context so the next iteration in the same
            # pass rebuilds open_positions_count from the DB and sees the
            # fresh placement. Without this, the concentration gate +
            # aggregate-open-risk gate use stale counts intra-pass and can
            # over-place by N when multiple markets in the same sector pass
            # the gates back-to-back.
            ctx_cache.pop(snap.sector, None)
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

    # Flush all decisions for this scan pass in one write transaction.
    if decision_rows:
        try:
            ts = now_iso_factory()
            with get_conn() as conn:
                for d_type, d_sector, d_summary, d_payload in decision_rows:
                    log_decision(
                        conn,
                        decision_type=d_type,
                        sector=d_sector,
                        summary=d_summary,
                        payload=d_payload,
                        timestamp=ts,
                    )
        except Exception as e:
            logger.warning("decision-log flush failed: %s", e)

    return {
        "scanned": len(markets),
        "snapshots": n_snapshots,
        "decisions": n_decisions,
        "approved": n_approved,
        "placed": n_placed,
        **{f"blocked_{k}": v for k, v in n_blocked.items()},
    }
