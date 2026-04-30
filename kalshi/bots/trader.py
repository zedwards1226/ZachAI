"""
Core trading logic for WeatherAlpha.
Orchestrates: fetch ensemble forecasts -> find markets -> compute edge -> check guardrails -> place orders.

Uses 31-member GFS ensemble for probability (not normal distribution).
"""
import logging
import time
from datetime import date, datetime

import requests

from config import CITIES, PAPER_MODE, STARTING_CAPITAL, MIN_EDGE, MIN_PRICE_CENTS, MIN_EDGE_YES, SHIN_Z
from calibration import get_shrinkage
from edge import shin_adjust
from database import (
    insert_forecast, insert_trade, update_guardrail_state,
    get_guardrail_state, get_summary, snapshot_pnl, has_open_trade_for_market,
    has_trade_for_market_today, has_open_trade_for_city, get_open_trades,
    insert_signal, settle_signal_by_trade
)
from weather import fetch_all_forecasts
from kalshi_client import get_client
from edge import prob_exceeds, prob_between, compute_edge, best_side, effective_edge, parse_strike_from_ticker
from kelly import size_stake
from guardrails import all_checks

log = logging.getLogger(__name__)

# Minimum 24h volume to consider a market tradeable
MIN_VOLUME = 0


def get_capital() -> float:
    summary = get_summary()
    return STARTING_CAPITAL + summary["total_pnl_usd"]


def reconcile_after_exception(*, client, client_order_id: str,
                              insert_kwargs: dict, stake: float,
                              exc: Exception) -> int | None:
    """
    After place_order raised, check if the order actually landed on Kalshi.
    If it did, insert a trade row + update guardrails to match reality.
    Returns the trade_id on successful reconcile, None otherwise.

    Skips the probe entirely in PAPER_MODE (paper orders never touch Kalshi).
    Swallows probe errors so a failed reconcile attempt never crashes the scan.
    """
    if PAPER_MODE:
        return None
    try:
        landed = client.get_orders(client_order_id=client_order_id)
    except (requests.exceptions.RequestException, ValueError) as rec_exc:
        # Network/HTTP/JSON-decode errors during the probe are recoverable —
        # next scan will reconcile. Anything else (auth, schema mismatch,
        # programmer error) should propagate so we hear about it.
        log.error("Reconcile probe failed (%s): %s", client_order_id, rec_exc)
        return None
    if not landed:
        return None
    landed_order = landed[0]
    log.warning(
        "RECONCILE: order landed on Kalshi despite exception "
        "(client_order_id=%s, status=%s, order_id=%s)",
        client_order_id, landed_order.get("status"), landed_order.get("order_id"),
    )
    trade_id = insert_trade(
        **insert_kwargs,
        notes=f"RECONCILED after exception: {exc}. kalshi_status={landed_order.get('status')}",
    )
    if not trade_id or trade_id == -1:
        return None
    gs = get_guardrail_state()
    update_guardrail_state(
        daily_trades=gs["daily_trades"] + 1,
        daily_pnl_usd=gs["daily_pnl_usd"],
        consecutive_losses=gs["consecutive_losses"],
        halted=gs["halted"],
        halt_reason=gs["halt_reason"],
    )
    return trade_id


def scan_and_trade() -> list[dict]:
    """
    Main scan loop. Returns list of trade actions taken this cycle.
    Called by APScheduler every SCAN_INTERVAL_MINUTES.
    """
    log.info("=== WeatherAlpha scan starting ===")
    actions = []

    # 1. Fetch all ensemble forecasts
    forecasts = fetch_all_forecasts()

    # 2. Get Kalshi client
    client = get_client()
    capital = get_capital()

    for city_code, forecast in forecasts.items():
        if forecast.get("error"):
            log.warning("Skipping %s -- forecast error: %s", city_code, forecast["error"])
            continue

        high_f = forecast["high_f"]
        low_f = forecast["low_f"]
        member_highs = forecast.get("member_highs", [])

        if not member_highs:
            log.warning("Skipping %s -- no ensemble members (deterministic fallback has no edge data)", city_code)
            insert_forecast(city_code, high_f, low_f)
            continue

        # 3. Search relevant KXHIGH markets
        markets_raw = client.search_kxhigh_markets(city_code)
        if not markets_raw:
            log.debug("No KXHIGH markets found for %s", city_code)
            insert_forecast(city_code, high_f, low_f)
            continue

        # 4. Enrich market data with strike prices and prices
        markets = []
        for m in markets_raw:
            ticker = m.get("ticker", "")
            strike_type = m.get("strike_type", "greater")
            floor_f = m.get("floor_strike")
            cap_f = m.get("cap_strike")

            # Determine strike
            if strike_type == "between" and floor_f is not None and cap_f is not None:
                strike = (float(floor_f) + float(cap_f)) / 2.0
            elif floor_f is not None:
                strike = float(floor_f)
            else:
                strike = parse_strike_from_ticker(ticker)

            if strike is None:
                continue

            # Price: use ASK (what we'd pay to buy), fall back to bid+1
            yes_ask_dollars = m.get("yes_ask_dollars") or m.get("yes_ask")
            yes_bid_dollars = m.get("yes_bid_dollars") or m.get("yes_bid")
            if yes_ask_dollars is not None:
                yes_price_cents = round(float(yes_ask_dollars) * 100)
            elif yes_bid_dollars is not None:
                yes_price_cents = round(float(yes_bid_dollars) * 100) + 1
            else:
                ob = client.get_orderbook(ticker)
                if ob and ob.get("yes") is not None:
                    yes_price_cents = int(ob["yes"]) + 1
                else:
                    continue

            if yes_price_cents <= 0 or yes_price_cents >= 100:
                continue

            # Skip illiquid penny contracts
            if yes_price_cents < MIN_PRICE_CENTS or (100 - yes_price_cents) < MIN_PRICE_CENTS:
                log.debug("Skipping %s -- price %d/%dc below %dc floor",
                          ticker, yes_price_cents, 100 - yes_price_cents, MIN_PRICE_CENTS)
                continue

            # Volume filter -- skip markets with no trading activity
            volume = m.get("volume", 0) or m.get("volume_24h", 0) or 0
            if volume < MIN_VOLUME:
                log.debug("Skipping %s -- volume %d below minimum %d", ticker, volume, MIN_VOLUME)
                continue

            markets.append({
                "ticker": ticker,
                "strike_f": strike,
                "strike_type": strike_type,
                "floor_f": float(floor_f) if floor_f is not None else strike,
                "cap_f": float(cap_f) if cap_f is not None else strike + 1,
                "yes_price_cents": yes_price_cents,
                "no_price_cents": 100 - yes_price_cents,
                "volume": volume,
            })

        if not markets:
            insert_forecast(city_code, high_f, low_f)
            continue

        # 5. Find market with best edge using ENSEMBLE probabilities.
        # Per-city shrinkage pulls our prob toward the market's implied prob
        # proportional to historical miscalibration for that city + side.
        # Since a market has a YES and a NO view, we evaluate each side with
        # its own shrinkage factor and pick the larger residual edge.
        shrink_yes = get_shrinkage(city_code, "YES")
        shrink_no = get_shrinkage(city_code, "NO")
        best = None
        best_abs_edge = 0.0
        for m in markets:
            if m["strike_type"] == "between":
                raw_p = prob_between(member_highs, m["floor_f"], m["cap_f"])
            else:
                raw_p = prob_exceeds(member_highs, m["strike_f"])
            # Shin-adjusted market probabilities correct for longshot bias
            # before we decide if an edge exists.
            market_p = shin_adjust(m["yes_price_cents"] / 100.0, SHIN_Z)
            market_p_no = shin_adjust(m["no_price_cents"] / 100.0, SHIN_Z)
            # YES view: shrink raw_p toward market_p using YES calibration
            our_p_yes = raw_p + shrink_yes * (market_p - raw_p)
            edge_yes = our_p_yes - market_p
            # NO view: shrink (1-raw_p) toward Shin-adjusted NO market prob
            raw_p_no = 1.0 - raw_p
            our_p_no = raw_p_no + shrink_no * (market_p_no - raw_p_no)
            # Negative edge => side_best will flip to NO downstream via best_side()
            edge_no_as_yes = -(our_p_no - market_p_no)  # same sign convention
            # Pick whichever side has bigger |edge|
            if abs(edge_yes) >= abs(edge_no_as_yes):
                our_p_chosen = our_p_yes
                e = edge_yes
            else:
                our_p_chosen = 1.0 - our_p_no  # express as YES-prob for downstream
                e = edge_no_as_yes
            ae = effective_edge(e)
            if ae > best_abs_edge:
                best_abs_edge = ae
                best = {**m, "our_prob": our_p_chosen, "raw_prob": raw_p,
                        "edge": e, "abs_edge": ae,
                        "shrink_yes": shrink_yes, "shrink_no": shrink_no}

        if not best:
            insert_forecast(city_code, high_f, low_f)
            continue

        # 6. Determine side
        side = best_side(best["edge"])

        # 6a. YES-side needs a bigger edge than NO because raw ensemble has been
        # overconfident on YES. Shrinkage already pulled our_prob toward market,
        # but keep an extra gate on the residual edge.
        if side == "yes" and best["abs_edge"] < MIN_EDGE_YES:
            log.info("Skipping %s %s -- YES edge %.3f below MIN_EDGE_YES %.3f",
                     city_code, best["ticker"], best["abs_edge"], MIN_EDGE_YES)
            actions.append({"city": city_code, "ticker": best["ticker"],
                            "action": "blocked",
                            "reasons": [f"yes_edge_below_{MIN_EDGE_YES}"],
                            "edge": best["edge"]})
            _sig = dict(
                city=city_code, market_id=best["ticker"],
                direction="YES", model_prob=best["our_prob"],
                market_price=best["yes_price_cents"] / 100, edge=best["edge"],
                kelly_fraction=0.0, suggested_size=0.0,
                forecast_hi_f=high_f, forecast_lo_f=low_f, strike_f=best["strike_f"],
            )
            insert_signal(**_sig, reason_skipped=f"yes_edge_below_{MIN_EDGE_YES}")
            continue

        price_cents = (best["yes_price_cents"] if side == "yes"
                       else best["no_price_cents"])
        our_prob_for_side = best["our_prob"] if side == "yes" else 1 - best["our_prob"]

        # 7. Size position
        sizing = size_stake(our_prob_for_side, price_cents, capital)
        stake = sizing["stake_usd"]
        log.info(
            "Sizing %s %s: bankroll=$%.2f raw_kelly=%.1f%% frac_kelly=%.1f%% "
            "kelly$=$%.2f pct_cap$=$%.2f -> stake=$%.2f (%d contracts @ %d¢)",
            city_code, side.upper(), sizing["bankroll_used"],
            sizing["raw_kelly"] * 100, sizing["frac_kelly"] * 100,
            sizing["kelly_dollars"], sizing["pct_cap_dollars"],
            stake, sizing["contracts"], price_cents,
        )

        # Signal data for calibration tracking
        _sig = dict(
            city=city_code, market_id=best["ticker"],
            direction=side.upper(), model_prob=our_prob_for_side,
            market_price=price_cents / 100, edge=best["edge"],
            kelly_fraction=sizing["frac_kelly"], suggested_size=stake,
            forecast_hi_f=high_f, forecast_lo_f=low_f, strike_f=best["strike_f"],
        )

        # 8. Save forecast record
        display_strike = best.get("floor_f", best["strike_f"])
        insert_forecast(
            city_code, high_f, low_f,
            kalshi_market_id=best["ticker"],
            kalshi_strike_f=display_strike,
            kalshi_yes_price=best["yes_price_cents"],
            kalshi_no_price=best["no_price_cents"],
            implied_prob_yes=best["yes_price_cents"] / 100,
            our_prob_yes=best["our_prob"],
            edge=best["edge"],
            raw_weather=forecast.get("raw"),
        )

        # 9a. Skip duplicates
        if has_open_trade_for_market(best["ticker"]):
            log.info("Skipping %s %s -- already have open position", city_code, best["ticker"])
            actions.append({"city": city_code, "ticker": best["ticker"], "action": "skipped_duplicate", "reason": "open position"})
            insert_signal(**_sig, reason_skipped="duplicate open position")
            continue
        if has_trade_for_market_today(best["ticker"]):
            log.info("Skipping %s %s -- already traded this market today", city_code, best["ticker"])
            actions.append({"city": city_code, "ticker": best["ticker"], "action": "skipped_duplicate", "reason": "already traded today"})
            insert_signal(**_sig, reason_skipped="already traded today")
            continue
        if has_open_trade_for_city(city_code):
            log.info("Skipping %s %s -- already have open trade for this city", city_code, best["ticker"])
            actions.append({"city": city_code, "ticker": best["ticker"], "action": "skipped_duplicate", "reason": "city has open trade"})
            insert_signal(**_sig, reason_skipped="city already has open trade")
            continue

        # 9b. Guardrail checks
        passed, reasons = all_checks(
            best["abs_edge"], stake, capital, price_cents, paper=PAPER_MODE,
            our_prob_yes=best["our_prob"],
            yes_price_cents=best["yes_price_cents"],
            ensemble_spread_f=forecast.get("ensemble_spread"),
            strike_type=best.get("strike_type"),
            city=city_code,
        )
        if not passed:
            log.info("Trade blocked [%s %s]: %s", city_code, best["ticker"], "; ".join(reasons))
            actions.append({
                "city": city_code,
                "ticker": best["ticker"],
                "action": "blocked",
                "reasons": reasons,
                "edge": best["edge"],
            })
            insert_signal(**_sig, reason_skipped="; ".join(reasons))
            continue

        # 10. Place order
        # Deterministic client_order_id so we can reconcile if the network drops
        # between us sending the request and receiving a response.
        client_order_id = f"wa-{city_code}-{best['ticker']}-{int(time.time())}"
        try:
            order = client.place_order(
                ticker=best["ticker"],
                side=side,
                contracts=sizing["contracts"],
                price_cents=price_cents,
                client_order_id=client_order_id,
            )
            trade_id = insert_trade(
                city=city_code,
                market_id=best["ticker"],
                side=side.upper(),
                contracts=sizing["contracts"],
                price_cents=price_cents,
                edge=best["abs_edge"],  # Store ABSOLUTE edge (always positive)
                kelly_frac=sizing["frac_kelly"],
                stake_usd=stake,
                paper=PAPER_MODE,
                floor_f=best["floor_f"],
                cap_f=best["cap_f"],
                strike_type=best["strike_type"],
                notes=f"strike={best['strike_f']}F our_prob={our_prob_for_side:.3f} ensemble={len(member_highs)}",
            )

            if trade_id == -1:
                log.warning("DB blocked duplicate for %s %s", city_code, best["ticker"])
                actions.append({"city": city_code, "ticker": best["ticker"], "action": "skipped_duplicate", "reason": "DB duplicate guard"})
                insert_signal(**_sig, reason_skipped="DB unique constraint blocked duplicate")
                continue

            # Update guardrail state
            gs = get_guardrail_state()
            update_guardrail_state(
                daily_trades=gs["daily_trades"] + 1,
                daily_pnl_usd=gs["daily_pnl_usd"],
                consecutive_losses=gs["consecutive_losses"],
                halted=gs["halted"],
                halt_reason=gs["halt_reason"],
            )

            log.info(
                "TRADE [%s] %s %s x%d @ %d cents edge=%.1f%% stake=$%.2f paper=%s ensemble=%d",
                city_code, best["ticker"], side.upper(),
                sizing["contracts"], price_cents,
                best["abs_edge"] * 100, stake, PAPER_MODE, len(member_highs)
            )

            actions.append({
                "city": city_code,
                "ticker": best["ticker"],
                "action": "traded",
                "side": side.upper(),
                "contracts": sizing["contracts"],
                "price": price_cents,
                "edge": round(best["abs_edge"], 4),
                "stake": stake,
                "trade_id": trade_id,
                "paper": PAPER_MODE,
            })
            insert_signal(**_sig, actionable=True, trade_id=trade_id)

        except Exception as exc:
            log.error("Order failed [%s %s]: %s", city_code, best["ticker"], exc)
            # Reconcile: the exception may have fired AFTER Kalshi accepted the order
            # (network drop between request and response). Otherwise we'd have a
            # phantom position — real order on Kalshi, no row in our DB.
            insert_kwargs = dict(
                city=city_code, market_id=best["ticker"], side=side.upper(),
                contracts=sizing["contracts"], price_cents=price_cents,
                edge=best["abs_edge"], kelly_frac=sizing["frac_kelly"],
                stake_usd=stake, paper=PAPER_MODE, floor_f=best["floor_f"],
                cap_f=best["cap_f"], strike_type=best["strike_type"],
            )
            reconciled_trade_id = reconcile_after_exception(
                client=client, client_order_id=client_order_id,
                insert_kwargs=insert_kwargs, stake=stake, exc=exc,
            )
            if reconciled_trade_id:
                actions.append({
                    "city": city_code, "ticker": best["ticker"],
                    "action": "reconciled", "side": side.upper(),
                    "contracts": sizing["contracts"], "price": price_cents,
                    "trade_id": reconciled_trade_id, "original_error": str(exc),
                })
                insert_signal(**_sig, actionable=True, trade_id=reconciled_trade_id)
            else:
                actions.append({
                    "city": city_code, "ticker": best["ticker"],
                    "action": "error", "error": str(exc),
                })
                insert_signal(**_sig, reason_skipped=f"order error: {exc}")

    # Live-compute open risk — no more trusting the cached counter.
    open_risk = round(sum(t["stake_usd"] for t in get_open_trades()), 2)
    snapshot_pnl(capital, open_risk)
    log.info("=== Scan complete -- %d actions ===", len(actions))
    return actions


def _fetch_actual_high(city_code: str, dt: date) -> float | None:
    """Fetch the actual recorded high temp (degF) for a city on a given date via Open-Meteo archive."""
    from weather import _get_with_retry
    city = CITIES.get(city_code)
    if not city:
        return None
    try:
        ds = dt.isoformat()
        r = _get_with_retry(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": city["lat"], "longitude": city["lon"],
                "start_date": ds, "end_date": ds,
                "daily": "temperature_2m_max",
                "temperature_unit": "fahrenheit",
                "timezone": "auto",
            },
            timeout=10,
        )
        return r.json()["daily"]["temperature_2m_max"][0]
    except Exception as exc:
        log.warning("Archive weather fetch failed for %s %s: %s", city_code, dt, exc)
        return None


def _parse_market_id(market_id: str):
    """
    Parse KXHIGH ticker into (city_code, market_date, strike_type, strike_f).
    e.g. KXHIGHNY-26APR06-T54  -> ('NYC', date(2026,4,6), 'greater', 54.0)
         KXHIGHMIA-26APR06-B84.5 -> ('MIA', date(2026,4,6), 'between', 84.5)
    Returns None on parse failure.
    """
    import re
    SERIES_MAP = {
        "KXHIGHNY": "NYC", "KXHIGHCHI": "CHI", "KXHIGHMIA": "MIA",
        "KXHIGHLAX": "LAX", "KXHIGHDEN": "DEN", "KXHIGHMEM": "MEM",
    }
    try:
        parts = market_id.split("-")
        if len(parts) < 3:
            return None
        series, date_part, strike_part = parts[0], parts[1], parts[2]
        city_code = SERIES_MAP.get(series)
        if not city_code:
            return None
        market_date = datetime.strptime(date_part, "%y%b%d").date()
        if strike_part.startswith("T"):
            return city_code, market_date, "greater", float(strike_part[1:])
        elif strike_part.startswith("B"):
            return city_code, market_date, "between", float(strike_part[1:])
        return None
    except Exception:
        return None


def resolve_expired_trades() -> None:
    """
    Check open trades and resolve them.
    Paper mode: use actual historical weather from Open-Meteo archive.
    Live mode: query Kalshi settlement API.
    """
    from database import get_open_trades, resolve_trade, get_guardrail_state
    open_trades = get_open_trades()
    if not open_trades:
        return

    today = date.today()

    for trade in open_trades:
        if PAPER_MODE:
            mkt_id = trade["market_id"]
            if "TEST" in mkt_id.upper():
                # Test fixtures should never reach the resolver. Skip silently.
                continue
            parsed = _parse_market_id(mkt_id)
            if not parsed:
                log.warning("Cannot parse market_id for resolution: %s", mkt_id)
                continue
            city_code, market_date, strike_type, strike_f = parsed

            # Only resolve if market date has fully passed
            if market_date >= today:
                continue

            actual_high = _fetch_actual_high(city_code, market_date)
            if actual_high is None:
                log.warning("No actual temp data for %s %s -- skipping resolution", city_code, market_date)
                continue

            # Use stored floor/cap from the trade record (not re-derived from ticker)
            trade_floor = trade.get("floor_f")
            trade_cap = trade.get("cap_f")
            trade_strike_type = trade.get("strike_type") or strike_type

            # Determine YES outcome using correct Kalshi rules:
            # - "greater": YES wins if actual > strike (strict)
            # - "between": YES wins if floor <= actual <= cap
            if trade_strike_type == "greater":
                yes_won = actual_high > strike_f  # STRICT greater than
            elif trade_floor is not None and trade_cap is not None:
                yes_won = trade_floor <= actual_high <= trade_cap
            else:
                # Fallback for old trades without floor/cap stored
                # B85.5 midpoint -> floor=85, cap=86
                fallback_floor = strike_f - 0.5
                fallback_cap = strike_f + 0.5
                yes_won = fallback_floor <= actual_high <= fallback_cap
                log.warning(
                    "Using fallback floor/cap for %s: %.1f-%.1f (no stored values)",
                    trade["market_id"], fallback_floor, fallback_cap
                )

            won = (yes_won and trade["side"] == "YES") or (not yes_won and trade["side"] == "NO")
            pnl = (trade["contracts"] * (1 - trade["price_cents"] / 100) if won
                   else -trade["contracts"] * trade["price_cents"] / 100)
            resolve_trade(trade["id"], won, pnl)
            settle_signal_by_trade(trade["id"], "YES" if yes_won else "NO", won)
            gs = get_guardrail_state()
            update_guardrail_state(
                daily_pnl_usd=gs["daily_pnl_usd"] + pnl,
                consecutive_losses=0 if won else gs["consecutive_losses"] + 1,
                halted=gs["halted"],
                halt_reason=gs["halt_reason"],
                daily_trades=gs["daily_trades"],
            )
            log.info(
                "RESOLVED [%s] %s %s -- actual %.1fF vs %.1fF %s -> %s  P&L=$%.2f",
                city_code, trade["market_id"], trade["side"],
                actual_high, strike_f, trade_strike_type,
                "WON" if won else "LOST", pnl,
            )
        else:
            try:
                client = get_client()
                market = client.get_market(trade["market_id"])
                if market and market.get("status") == "finalized":
                    result = market.get("result")  # "yes" or "no"
                    won = (result == "yes" and trade["side"] == "YES") or \
                          (result == "no" and trade["side"] == "NO")
                    pnl = (trade["contracts"] * (1 - trade["price_cents"] / 100) if won
                           else -trade["contracts"] * trade["price_cents"] / 100)
                    resolve_trade(trade["id"], won, pnl)
                    settle_signal_by_trade(trade["id"], result.upper(), won)
                    gs = get_guardrail_state()
                    update_guardrail_state(
                        daily_pnl_usd=gs["daily_pnl_usd"] + pnl,
                        consecutive_losses=0 if won else gs["consecutive_losses"] + 1,
                        halted=gs["halted"],
                        halt_reason=gs["halt_reason"],
                        daily_trades=gs["daily_trades"],
                    )
            except Exception as exc:
                log.warning("Resolution error for trade %s: %s", trade["id"], exc)
