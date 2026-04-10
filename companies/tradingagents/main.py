"""
TradingAgents — FastAPI gate for NQ/MNQ futures.
Receives TradingView webhooks, runs agent pipeline, logs trades.
Replaces paper_trader.py.
"""
import asyncio
import re
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
from models import Signal, Verdict
from services import telegram_bot as tg
from agents import sentinel, sweep_detector, context as context_agent
from agents.trade_monitor import check_open_trades
from agents.analyst import run_eod_analysis

log = logging.getLogger("tradingagents")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()

    # Trade Monitor: check open positions every 30 seconds
    scheduler.add_job(_monitor_loop, "interval", seconds=30, id="trade_monitor")

    # Analyst: EOD review at 4:15 PM ET
    scheduler.add_job(run_eod_analysis, "cron",
                      hour=config.ANALYST_EOD_HOUR,
                      minute=config.ANALYST_EOD_MINUTE,
                      id="analyst_eod")

    scheduler.start()
    log.info("TradingAgents gate running on port %d", config.PORT)
    log.info("Scheduler started: trade_monitor (30s), analyst_eod (%d:%02d ET)",
             config.ANALYST_EOD_HOUR, config.ANALYST_EOD_MINUTE)
    yield
    scheduler.shutdown()

app = FastAPI(title="TradingAgents Gate", lifespan=lifespan)


# ── Background agent pipeline ────────────────────────────────────────────────

async def _run_background_agents(signal: Signal, signal_id: int, trade_id: int):
    """Run Sentinel, Sweep Detector, and Context agents async (non-blocking)."""
    try:
        # Sentinel
        sv = sentinel.evaluate(signal)
        db.insert_decision(signal_id, sv.agent, sv.verdict.value, sv.reasoning, sv.tokens_used, trade_id)
        if "WARNING" in sv.reasoning:
            await tg.notify_agent_warning("Sentinel", signal.symbol, sv.reasoning)

        # Sweep Detector (no bar data yet — will integrate TradingView MCP later)
        swv = sweep_detector.evaluate(signal)
        db.insert_decision(signal_id, swv.agent, swv.verdict.value, swv.reasoning, swv.tokens_used, trade_id)
        if "CONFLICT" in swv.reasoning:
            await tg.notify_agent_warning("Sweep", signal.symbol, swv.reasoning)

        # Context
        cv = context_agent.evaluate(signal)
        db.insert_decision(signal_id, cv.agent, cv.verdict.value, cv.reasoning, cv.tokens_used, trade_id)

        log.info("Background agents complete for signal #%d", signal_id)
    except Exception as e:
        log.error("Background agent error: %s", e)


async def _monitor_loop():
    """Periodic check of open trade health."""
    warnings = check_open_trades()
    for w in warnings:
        msg = f"Trade #{w['trade_id']} {w['side']} {w['symbol']} @ {w['entry']:.2f}: " + "; ".join(w["warnings"])
        await tg.notify_agent_warning("Monitor", w["symbol"], msg)


# ── Webhook parsing (ported from paper_trader.py) ────────────────────────────

def parse_alert(body: str) -> Signal:
    """
    Parse TradingView webhook — handles two formats:
    1. JSON: {"action":"buy","symbol":"MNQ1!","price":25000,"order_id":"Long","position_size":1}
    2. TV text: "ORB 5m v3: order buy @ 1 filled on CME_MINI:MNQ1!. New strategy position is 1"
    """
    import json

    # Try JSON first
    try:
        data = json.loads(body)
        if data.get("action"):
            action = data["action"].lower()
            order_id = data.get("order_id", "")
            position_size = data.get("position_size")

            # Detect exit signals
            is_exit = False
            if position_size is not None and float(position_size) == 0:
                is_exit = True
            elif order_id:
                oid = order_id.upper()
                if oid in ("LX1", "LX2", "SX1", "SX2", "EOD") or "EXIT" in oid:
                    is_exit = True

            if is_exit:
                action = "close"

            return Signal(
                action=action,
                symbol=data.get("symbol", "MNQ1!"),
                price=float(data.get("price", 0)),
                qty=int(data.get("qty", data.get("contracts", 1))),
                order_id=order_id,
                position_size=position_size,
                strategy=data.get("strategy", "NQ ORB 15m"),
                raw_body=body,
            )
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: parse TradingView default text
    action_m = re.search(r'\border (\w+)\b', body)
    symbol_m = re.search(r'filled on (?:CME_MINI:|BATS:)?([\w!]+)', body)
    position_m = re.search(r'position is (-?\d+\.?\d*)', body)
    price_m = re.search(r'@\s*([\d,.]+)', body)

    if not action_m:
        return Signal(action="unknown", raw_body=body)

    raw_action = action_m.group(1).lower()
    position = float(position_m.group(1)) if position_m else None
    action = "close" if position == 0 else raw_action

    return Signal(
        action=action,
        symbol=symbol_m.group(1) if symbol_m else "MNQ1!",
        price=float(price_m.group(1).replace(",", "")) if price_m else 0.0,
        strategy="NQ ORB 15m",
        raw_body=body,
    )


def get_multiplier(symbol: str) -> float:
    return config.MULTIPLIERS.get(symbol.upper(), 1)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/alert")
async def handle_alert(request: Request):
    """Main webhook endpoint — TradingView alerts hit here."""
    body = await request.body()
    raw = body.decode("utf-8", errors="replace")
    log.info("Webhook received: %s", raw[:500])

    signal = parse_alert(raw)
    if signal.action == "unknown":
        log.warning("Could not parse alert: %s", raw[:200])
        return JSONResponse({"ok": False, "error": "unparseable"}, status_code=400)

    # Log signal to DB
    signal_id = db.insert_signal(
        symbol=signal.symbol,
        action=signal.action,
        price=signal.price,
        qty=signal.qty,
        order_id=signal.order_id,
        strategy=signal.strategy,
        raw_body=signal.raw_body,
        position_size=signal.position_size,
    )
    log.info("Signal #%d: %s %s @ %.2f (order_id=%s)",
             signal_id, signal.action, signal.symbol, signal.price, signal.order_id)

    if signal.action in ("buy", "sell"):
        return await _handle_entry(signal, signal_id)
    elif signal.action == "close":
        return await _handle_close(signal, signal_id)
    else:
        log.warning("Unknown action: %s", signal.action)
        return JSONResponse({"ok": False, "error": f"unknown action: {signal.action}"}, status_code=400)


async def _handle_entry(signal: Signal, signal_id: int) -> JSONResponse:
    """Process a new trade entry signal through the agent pipeline."""
    from agents.overseer import evaluate as overseer_evaluate
    verdict = overseer_evaluate(signal)
    db.insert_decision(signal_id, verdict.agent, verdict.verdict.value,
                       verdict.reasoning, verdict.tokens_used)

    if verdict.verdict == Verdict.BLOCK:
        log.info("BLOCKED by %s: %s", verdict.agent, verdict.reasoning)
        await tg.notify_block(signal.symbol, signal.action, signal.price, verdict.reasoning)
        return JSONResponse({"ok": True, "verdict": "BLOCK", "reason": verdict.reasoning})

    # PASS or REDUCE — open the trade
    qty = signal.qty
    if verdict.verdict == Verdict.REDUCE:
        qty = max(1, qty // 2)

    multiplier = get_multiplier(signal.symbol)
    side = "BUY" if signal.action == "buy" else "SELL"

    trade_id = db.insert_trade(
        signal_id=signal_id,
        symbol=signal.symbol,
        side=side,
        entry=signal.price,
        qty=qty,
        multiplier=multiplier,
        strategy=signal.strategy,
        order_id=signal.order_id,
    )

    # Update guardrail state
    db.update_guardrail_after_trade()

    log.info("TRADE OPENED #%d: %s %s @ %.2f (qty=%d, $%d/pt)",
             trade_id, side, signal.symbol, signal.price, qty, multiplier)

    await tg.notify_entry(side, signal.symbol, signal.price, qty, multiplier,
                          signal.strategy, verdict.verdict.value, verdict.reasoning, trade_id)

    # Fire background agents (non-blocking)
    asyncio.create_task(_run_background_agents(signal, signal_id, trade_id))

    return JSONResponse({
        "ok": True,
        "verdict": verdict.verdict.value,
        "trade_id": trade_id,
        "side": side,
        "symbol": signal.symbol,
        "entry": signal.price,
    })


async def _handle_close(signal: Signal, signal_id: int) -> JSONResponse:
    """Process a trade close/exit signal."""
    closed = db.close_trades_for_symbol(signal.symbol, signal.price)

    if not closed:
        log.warning("Close signal for %s but no open trades", signal.symbol)
        return JSONResponse({"ok": True, "closed": 0})

    for t in closed:
        pnl = t["pnl"]
        pts = t["pts"]
        multiplier = t["multiplier"]
        emoji = "+" if pnl > 0 else ""

        log.info("TRADE CLOSED #%d: %s %s %.2f -> %.2f | %s$%.2f (%s%.2f pts x $%d)",
                 t["id"], t["side"], signal.symbol, t["entry"], signal.price,
                 emoji, pnl, emoji, pts, multiplier)

        # Update guardrail state with P&L
        db.update_guardrail_after_trade(pnl=pnl)

    summary = db.get_summary()

    for t in closed:
        await tg.notify_close(t["side"], signal.symbol, t["entry"], signal.price,
                              t["pnl"], t["pts"], t["multiplier"], t["id"], summary)

    log.info("Running total: $%.2f P&L | %d trades | %.1f%% win rate",
             summary["total_pnl"], summary["total_trades"], summary["win_rate"])

    return JSONResponse({
        "ok": True,
        "closed": len(closed),
        "trades": closed,
        "summary": summary,
    })


@app.get("/status")
async def status():
    """Dashboard endpoint — current state."""
    summary = db.get_summary()
    open_trades = db.get_open_trades()
    guardrails = db.get_guardrail_state()
    return {
        "status": "running",
        "summary": summary,
        "open_trades": open_trades,
        "guardrails": guardrails,
    }


@app.get("/trades")
async def trades(limit: int = 50):
    return db.get_trades(limit)


@app.get("/trades/today")
async def trades_today():
    return db.get_trades_today()


@app.post("/reset")
async def reset():
    """Reset all trades — for testing only."""
    with db.get_conn() as conn:
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM signals")
        conn.execute("DELETE FROM decisions")
        conn.execute("DELETE FROM guardrail_state")
    log.info("All data reset")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
