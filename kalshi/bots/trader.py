"""
Core trading logic for WeatherAlpha.
Orchestrates: fetch forecasts → find markets → compute edge → check guardrails → place orders.
"""
import logging
from datetime import date

from config import CITIES, PAPER_MODE, STARTING_CAPITAL, MIN_EDGE
from database import (
    insert_forecast, insert_trade, update_guardrail_state,
    get_guardrail_state, get_summary, snapshot_pnl, has_open_trade_for_market,
    insert_signal, settle_signal_by_trade
)
from weather import fetch_all_forecasts
from kalshi_client import get_client
from edge import prob_exceeds, prob_between, compute_edge, best_side, effective_edge, parse_strike_from_ticker
from kelly import size_stake, size_stake_no
from guardrails import all_checks

log = logging.getLogger(__name__)


def get_capital() -> float:
    summary = get_summary()
    return STARTING_CAPITAL + summary["total_pnl_usd"]


def scan_and_trade() -> list[dict]:
    """
    Main scan loop. Returns list of trade actions taken this cycle.
    Called by APScheduler every SCAN_INTERVAL_MINUTES.
    """
    log.info("=== WeatherAlpha scan starting ===")
    actions = []

    # 1. Fetch all weather forecasts
    forecasts = fetch_all_forecasts()

    # 2. Get Kalshi client
    client = get_client()
    capital = get_capital()

    for city_code, forecast in forecasts.items():
        if forecast.get("error"):
            log.warning("Skipping %s — forecast error: %s", city_code, forecast["error"])
            continue

        high_f = forecast["high_f"]
        low_f  = forecast["low_f"]

        # 3. Search relevant KXHIGH markets
        markets_raw = client.search_kxhigh_markets(city_code)
        if not markets_raw:
            log.debug("No KXHIGH markets found for %s", city_code)
            # Save forecast anyway (no market data)
            insert_forecast(city_code, high_f, low_f)
            continue

        # 4. Enrich market data with strike prices and prices
        # API returns prices in dollars ("0.2700"), strike as floor_strike/cap_strike ints
        # and strike_type as "between" or "greater"
        markets = []
        for m in markets_raw:
            ticker      = m.get("ticker", "")
            strike_type = m.get("strike_type", "greater")  # "between" or "greater"
            floor_f     = m.get("floor_strike")
            cap_f       = m.get("cap_strike")

            # Determine strike: for "between" use midpoint, for "greater" use floor
            if strike_type == "between" and floor_f is not None and cap_f is not None:
                strike = (float(floor_f) + float(cap_f)) / 2.0
            elif floor_f is not None:
                strike = float(floor_f)
            else:
                # Fallback: parse from ticker
                strike = parse_strike_from_ticker(ticker)

            if strike is None:
                continue

            # Price: API returns yes_bid_dollars as a string like "0.2700"
            yes_bid_dollars = m.get("yes_bid_dollars") or m.get("yes_bid")
            if yes_bid_dollars is None:
                # Fallback to orderbook
                ob = client.get_orderbook(ticker)
                if ob and ob.get("yes") is not None:
                    yes_price_cents = int(ob["yes"])
                else:
                    continue
            else:
                yes_price_cents = round(float(yes_bid_dollars) * 100)

            if yes_price_cents <= 0 or yes_price_cents >= 100:
                continue

            markets.append({
                "ticker":          ticker,
                "strike_f":        strike,
                "strike_type":     strike_type,
                "floor_f":         float(floor_f) if floor_f is not None else strike,
                "cap_f":           float(cap_f) if cap_f is not None else strike + 1,
                "yes_price_cents": yes_price_cents,
                "no_price_cents":  100 - yes_price_cents,
            })

        if not markets:
            insert_forecast(city_code, high_f, low_f)
            continue

        # 5. Find market with best edge
        # Use prob_between for "between" markets, prob_exceeds for threshold markets
        best = None
        best_abs_edge = 0.0
        for m in markets:
            if m["strike_type"] == "between":
                our_p = prob_between(high_f, m["floor_f"], m["cap_f"])
            else:
                our_p = prob_exceeds(high_f, m["strike_f"])
            e  = compute_edge(our_p, m["yes_price_cents"])
            ae = effective_edge(e)
            if ae > best_abs_edge:
                best_abs_edge = ae
                best = {**m, "our_prob": our_p, "edge": e, "abs_edge": ae}

        if not best:
            insert_forecast(city_code, high_f, low_f)
            continue

        # 6. Determine side
        side = best_side(best["edge"])
        price_cents = (best["yes_price_cents"] if side == "yes"
                       else best["no_price_cents"])
        our_prob_for_side = best["our_prob"] if side == "yes" else 1 - best["our_prob"]

        # 7. Size position
        sizing = size_stake(our_prob_for_side, price_cents, capital)
        stake  = sizing["stake_usd"]

        # Signal data for calibration tracking
        _sig = dict(
            city=city_code, market_id=best["ticker"],
            direction=side.upper(), model_prob=our_prob_for_side,
            market_price=price_cents / 100, edge=best["edge"],
            kelly_fraction=sizing["frac_kelly"], suggested_size=stake,
            forecast_hi_f=high_f, forecast_lo_f=low_f, strike_f=best["strike_f"],
        )

        # 8. Save forecast record
        # For between markets, store floor as the strike for display purposes
        display_strike = best.get("floor_f", best["strike_f"])
        insert_forecast(
            city_code, high_f, low_f,
            kalshi_market_id   = best["ticker"],
            kalshi_strike_f    = display_strike,
            kalshi_yes_price   = best["yes_price_cents"],
            kalshi_no_price    = best["no_price_cents"],
            implied_prob_yes   = best["yes_price_cents"] / 100,
            our_prob_yes       = best["our_prob"],
            edge               = best["edge"],
            raw_weather        = forecast.get("raw"),
        )

        # 9a. Skip if already have an open position for this market
        if has_open_trade_for_market(best["ticker"]):
            log.info("Skipping %s %s — already have open position", city_code, best["ticker"])
            actions.append({"city": city_code, "ticker": best["ticker"], "action": "skipped_duplicate"})
            insert_signal(**_sig, reason_skipped="duplicate open position")
            continue

        # 9. Guardrail checks
        passed, reasons = all_checks(best["edge"], stake, capital, paper=PAPER_MODE)
        if not passed:
            log.info("Trade blocked [%s %s]: %s", city_code, best["ticker"], "; ".join(reasons))
            actions.append({
                "city":    city_code,
                "ticker":  best["ticker"],
                "action":  "blocked",
                "reasons": reasons,
                "edge":    best["edge"],
            })
            insert_signal(**_sig, reason_skipped="; ".join(reasons))
            continue

        # 10. Place order
        try:
            order = client.place_order(
                ticker        = best["ticker"],
                side          = side,
                contracts     = sizing["contracts"],
                price_cents   = price_cents,
            )
            trade_id = insert_trade(
                city         = city_code,
                market_id    = best["ticker"],
                side         = side.upper(),
                contracts    = sizing["contracts"],
                price_cents  = price_cents,
                edge         = best["edge"],
                kelly_frac   = sizing["frac_kelly"],
                stake_usd    = stake,
                paper        = PAPER_MODE,
                notes        = f"strike={best['strike_f']}F our_prob={best['our_prob']:.3f}",
            )

            # Update guardrail state
            gs = get_guardrail_state()
            update_guardrail_state(
                daily_trades        = gs["daily_trades"] + 1,
                daily_pnl_usd       = gs["daily_pnl_usd"],
                consecutive_losses  = gs["consecutive_losses"],
                capital_at_risk_usd = gs["capital_at_risk_usd"] + stake,
                halted              = gs["halted"],
                halt_reason         = gs["halt_reason"],
            )

            log.info(
                "TRADE [%s] %s %s x%d @ %d¢ edge=%.1f%% stake=$%.2f paper=%s",
                city_code, best["ticker"], side.upper(),
                sizing["contracts"], price_cents,
                best["abs_edge"] * 100, stake, PAPER_MODE
            )

            actions.append({
                "city":      city_code,
                "ticker":    best["ticker"],
                "action":    "traded",
                "side":      side.upper(),
                "contracts": sizing["contracts"],
                "price":     price_cents,
                "edge":      round(best["edge"], 4),
                "stake":     stake,
                "trade_id":  trade_id,
                "paper":     PAPER_MODE,
            })
            insert_signal(**_sig, actionable=True, trade_id=trade_id)

        except Exception as exc:
            log.error("Order failed [%s %s]: %s", city_code, best["ticker"], exc)
            actions.append({
                "city":   city_code,
                "ticker": best["ticker"],
                "action": "error",
                "error":  str(exc),
            })
            insert_signal(**_sig, reason_skipped=f"order error: {exc}")

    snapshot_pnl(capital, get_guardrail_state().get("capital_at_risk_usd", 0))
    log.info("=== Scan complete — %d actions ===", len(actions))
    return actions


def _fetch_actual_high(city_code: str, dt: date) -> float | None:
    """Fetch the actual recorded high temp (°F) for a city on a given date via Open-Meteo archive."""
    import requests
    from config import CITIES
    city = CITIES.get(city_code)
    if not city:
        return None
    try:
        ds = dt.isoformat()
        r = requests.get(
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
        r.raise_for_status()
        return r.json()["daily"]["temperature_2m_max"][0]
    except Exception as exc:
        log.warning("Archive weather fetch failed for %s %s: %s", city_code, dt, exc)
        return None


def _parse_market_id(market_id: str):
    """
    Parse KXHIGH ticker into (city_code, market_date, strike_type, strike_f).
    e.g. KXHIGHNY-26APR06-T54  → ('NYC', date(2026,4,6), 'greater', 54.0)
         KXHIGHMIA-26APR06-B84.5 → ('MIA', date(2026,4,6), 'between', 84.5)
    Returns None on parse failure.
    """
    import re
    from datetime import datetime
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
            parsed = _parse_market_id(trade["market_id"])
            if not parsed:
                log.warning("Cannot parse market_id for resolution: %s", trade["market_id"])
                continue
            city_code, market_date, strike_type, strike_f = parsed
            # Only resolve if market date has FULLY passed — never resolve same-day
            # because the actual high temp isn't final until evening
            if market_date >= today:
                continue
            actual_high = _fetch_actual_high(city_code, market_date)
            if actual_high is None:
                log.warning("No actual temp data for %s %s — skipping resolution", city_code, market_date)
                continue
            # Determine YES outcome
            if strike_type == "greater":
                yes_won = actual_high >= strike_f
            else:  # between: YES wins if actual is within ~1°F below the cap
                yes_won = (strike_f - 1.0) <= actual_high < strike_f
            won = (yes_won and trade["side"] == "YES") or (not yes_won and trade["side"] == "NO")
            pnl = (trade["contracts"] * (1 - trade["price_cents"] / 100) if won
                   else -trade["contracts"] * trade["price_cents"] / 100)
            resolve_trade(trade["id"], won, pnl)
            settle_signal_by_trade(trade["id"], "YES" if yes_won else "NO", won)
            gs = get_guardrail_state()
            update_guardrail_state(
                daily_pnl_usd       = gs["daily_pnl_usd"] + pnl,
                consecutive_losses  = 0 if won else gs["consecutive_losses"] + 1,
                capital_at_risk_usd = max(0, gs["capital_at_risk_usd"] - trade["stake_usd"]),
                halted              = gs["halted"],
                halt_reason         = gs["halt_reason"],
                daily_trades        = gs["daily_trades"],
            )
            log.info(
                "RESOLVED [%s] %s %s — actual %.1f°F vs %.1f°F %s → %s  P&L=$%.2f",
                city_code, trade["market_id"], trade["side"],
                actual_high, strike_f, strike_type,
                "WON" if won else "LOST", pnl,
            )
        else:
            try:
                client = get_client()
                market = client.get_market(trade["market_id"])
                if market and market.get("status") == "finalized":
                    result = market.get("result")  # "yes" or "no"
                    won    = (result == "yes" and trade["side"] == "YES") or \
                             (result == "no"  and trade["side"] == "NO")
                    pnl    = (trade["contracts"] * (1 - trade["price_cents"]/100) if won
                              else -trade["contracts"] * trade["price_cents"]/100)
                    resolve_trade(trade["id"], won, pnl)
                    settle_signal_by_trade(trade["id"], result.upper(), won)
                    gs = get_guardrail_state()
                    update_guardrail_state(
                        daily_pnl_usd       = gs["daily_pnl_usd"] + pnl,
                        consecutive_losses  = 0 if won else gs["consecutive_losses"] + 1,
                        capital_at_risk_usd = max(0, gs["capital_at_risk_usd"] - trade["stake_usd"]),
                        halted              = gs["halted"],
                        halt_reason         = gs["halt_reason"],
                        daily_trades        = gs["daily_trades"],
                    )
            except Exception as exc:
                log.warning("Resolution error for trade %s: %s", trade["id"], exc)
