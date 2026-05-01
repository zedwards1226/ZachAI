# Production Trading Bot Patterns — Research Findings
**Date:** 2026-04-30
**Source:** Five parallel research agents searched GitHub repos with 100+ stars looking for production-quality trading bot patterns. Findings consolidated here for reference.

**Why this document exists:** After 3 weeks of daily bug-of-the-day cycles in our ORB bot (phantom positions, counter drift, broker disconnects, R:R thinness), owner directive on 2026-04-30: stop, research, design properly, then build. This is the consolidated research that informed the refactor plan.

---

## Agent 1 — Order State Machine Patterns

Five repos with battle-tested order lifecycle handling.

### 1. Hummingbot — `InFlightOrder` (the gold standard for our use case)
- **Repo:** https://github.com/hummingbot/hummingbot
- **Stars:** 18,424 | **Last commit:** 2026-04-21
- **File:** `hummingbot/core/data_type/in_flight_order.py:20-330`

Explicit `OrderState` enum with strict transitions:
```python
class OrderState(Enum):
    PENDING_CREATE = 0
    OPEN = 1
    PENDING_CANCEL = 2
    CANCELED = 3
    PARTIALLY_FILLED = 4
    FILLED = 5
    FAILED = 6
```

State transitions are enforced via `update_with_order_update()` which validates `(client_order_id, exchange_order_id)` match before advancing state. **Client order ID is always required — no orphaned fills.**

Restart recovery: `from_json()` rehydrates the entire `InFlightOrder` from persisted JSON, including all partial fills in `order_fills` dict, and reconstructs state. Orders survive crashes if you persist to disk.

**Gotcha:** `update_with_trade_update()` requires `trade_id` uniqueness (prevents duplicate partial fills). Uses `asyncio.Event` for idempotent waits on fills.

**Why it's the right port for us:** Client order ID is always the lookup key. Exchange order ID is updated on ACK. Zero phantom orders if you persist state. Battle-tested across 8+ exchanges.

### 2. Freqtrade — SQLAlchemy persistence (most mature)
- **Repo:** https://github.com/freqtrade/freqtrade
- **Stars:** 49,621 | **Last commit:** 2026-04-30
- **File:** `freqtrade/persistence/trade_model.py:65-330`, `freqtrade/exchange/exchange.py:1660-1710`

Persists every order to SQLite with uniqueness constraint:
```python
__table_args__ = (UniqueConstraint("ft_pair", "order_id", name="_order_pair_order_id"),)
```

State tracking: `ft_is_open` boolean flips false when status enters `NON_OPEN_EXCHANGE_STATES = ["closed", "canceled", "expired", "rejected", "failed"]`.

Restart recovery: `SELECT FROM orders WHERE ft_is_open = True` then `fetch_order()` against broker for each.

**Why it's notable:** Real DB with unique index, scalable to thousands of orders. Single source of truth on disk.

### 3. Nautilus Trader — strict FSM (Cython)
- **Repo:** https://github.com/nautechsystems/nautilus_trader
- **Stars:** 22,370 | **Last commit:** 2026-05-01
- **File:** `nautilus_trader/core/fsm.pyx:30-120`

Generic `FiniteStateMachine` enforces transitions via lookup table:
```cython
cdef class FiniteStateMachine:
    cpdef void trigger(self, int trigger):
        cdef int next_state = self._state_transition_table.get((self.state, trigger), -1)
        if next_state == -1:
            raise InvalidStateTrigger(...)
        self.state = next_state
```

**Invalid transitions raise immediately** — no silent bugs.

**Why notable:** Production-strict. Built for HFT. Adds Cython build complexity, probably overkill for our use case.

### 4. CCXT — idempotency via `clientOrderId`
- **Repo:** https://github.com/ccxt/ccxt
- **Stars:** 42,148 | **Last commit:** 2026-04-30
- **File:** `python/ccxt/base/exchange.py:5510-5945`

Idempotent order create:
```python
def edit_order_with_client_order_id(self, clientOrderId: str, ...):
    extendedParams = self.extend(params, {'clientOrderId': clientOrderId})
    return self.create_order(...)
```

CCXT delegates idempotency to broker (passes `clientOrderId` through). For brokers that don't support it (IBKR, IB), bots must manage their own.

**Pattern to copy:** Always pass `clientOrderId` (UUID) on every order, store in DB, use as lookup key. We can implement this for TV by including the UUID in our trade journal and re-checking on retry.

### 5. Alpaca-py — clean enum + required field
- **Repo:** https://github.com/alpacahq/alpaca-py
- **Stars:** 1,293 | **Last commit:** 2026-04-27
- **File:** `alpaca/trading/enums.py:148-175`, `alpaca/trading/models.py:168-250`

20-state `OrderStatus` enum, `client_order_id` is a required field on the Order model.

Restart recovery: filter `status not in [FILLED, CANCELED, REJECTED]` then re-fetch.

**Gotcha:** Order replacement edge cases (`replaced_at`, `replaced_by`, `replaces` fields) — must handle.

---

### Verdict for our bot

**Copy Hummingbot's `InFlightOrder` class directly.** Pattern is straight-port-able into Python. Our 7 states map cleanly:
- `PENDING_SUBMIT` (we sent the JS DOM script)
- `SUBMITTED` (TV's submit button clicked, waiting for ack)
- `ACKNOWLEDGED` (toast says "Market order placed")
- `FILLED` (toast says "Market order executed at X")
- `REJECTED` (toast says "Market order rejected")
- `FAILED_PLACEMENT` (DOM script returned `side_not_found` etc — never even submitted)

Each transition VERIFIED against broker (toast scan + `_has_open_position` query). No more counter-drift bugs.

---

## Agent 2 — Reconciliation Loop Patterns

| Repo | Mechanism | Cadence | Notes |
|---|---|---|---|
| Freqtrade | `update_trades_state()`, `_update_trade_after_fill()` | 15-60s configurable | DB-backed, polling |
| Hummingbot | `_status_polling_loop()`, `update_balances()` | 10s default | Polling + websocket fills |
| Nautilus | Event-driven on fill/execution messages | per-event | No scheduled poll |
| CCXT (toolkit) | `fetch_position`, `fetch_balance` | bot-defined | Primitives only |
| OctoBot-Trading | CCXT wrapper with state sync | polling | Lighter weight |

**Two reconciliation models:**
- **Polling** (freqtrade, hummingbot) — query every N seconds. Race window on partial fills.
- **Event-driven** (nautilus) — react on every broker push. No race window. Requires broker to push.

**For our TV CDP setup:** TradingView doesn't push events to us — we have to poll. So polling it is. Cadence 60s recommended (matches existing watchdog rhythm).

**Limitation flagged:** Agent 2 hit GitHub API rate limits and couldn't extract concrete code. To dig deeper: clone the 3 repos and `grep -r "reconcile\|_drift\|sync.*position\|update.*balance"` locally.

---

## Agent 3 — ORB Strategy Implementations (REAL CONFIGS)

| Repo | Stars | Sample | WR | PF | R:R | Stop | Entry | Trail | Volume Filter |
|---|---|---|---|---|---|---|---|---|---|
| **2d2f/ORB_backtest** | 1 | 82 trades | **56.1%** | 1.0 | **1.5:1** | **100% ORB range** | Stop order on 5-min close | None | ATR-based skip |
| **sam-bateman/trading-orb** | 2 | **4,292 trades, 10 yrs** | **50.3%** | **1.31** | **1.5:1 → 2:1 BE** | 0.75× OR range | Close + 1.2× rel vol | **YES — to BE** | **1.2× RVOL (CRITICAL)** |
| jefrnc/strategy-orb15-momentum | 15 | unclear | n/a | n/a | claims 5.6:1 | 0.25× ORB ext | Close, 9:30-2pm | 0.5× ORB | None |
| vp275/pj_orb_backtester | 10 | not pub | n/a | n/a | 1.5%/0.25% | Fixed % | Close | None | None |
| adnansaify/ORB | 7 | not pub | n/a | n/a | unclear | Time-based | Close past 9:25 | None | None |

### THE CRITICAL FINDING — sam-bateman 4,292-trade backtest

**The single biggest edge in ORB is volume confirmation, not the breakout itself.**

From sam-bateman's 10-year, 4,292-trade backtest:
- Without volume filter: ~50% WR (essentially coin-flip)
- **With 1.2× relative volume filter: 50.3% WR + 1.31 PF + 2.47 Sharpe** — significantly profitable

**This means our current bot is missing THE main edge.** We don't filter by volume at all. Today's trade #9 fired with `RVOL: 0` in the score breakdown — meaning relative volume was below the 1.5× threshold the structure agent already computes. **The data is there; we're just not using it as a hard gate.**

**Owner directive 2026-04-30 explicitly rejected adding volume filter as a hard gate** (no more guardrails / no entry filter reductions). Recording this finding for future reference — if WR becomes an issue, this is the highest-EV change available.

### Other findings vs our setup

| Aspect | Our Setup | sam-bateman best practice |
|---|---|---|
| R:R | ~1:1 | 1.5:1 base, 2:1 after trail |
| Stop | ORB ± 0.25× extension | 0.75× ORB range |
| Entry | 5-min close past box | Close past box + RVOL ≥ 1.2 |
| Trail | Continuous 0.5× ORB | BE only after 1.0× range |
| Volume | None | 1.2× RVOL required |
| ATR norm | None | Skip days outside 0.20-0.50× ATR |
| Window | 9:30-2pm | 10:00-14:30 |

**Approved change:** TARGET_2_MULT 1.5 → 2.0 (Phase 3.1)

**Logged but not approved by owner:**
- Volume filter (would be highest-EV change per evidence, but reduces trade frequency)
- ATR normalization
- Tighter stop (0.75× ORB instead of 1.0× + 0.25× extension)

---

## Agent 4 — Backtest Framework Recommendation

**Pick: `backtesting.py` (8.5/10)**

| Library | Score | Reason |
|---|---|---|
| **`backtesting.py`** | **8.5** | Fast, clean API, good per-trade output. Manual session logic minimal. Recommended for now. |
| `vectorbt` | 7.5 | Vectorized speed, but session/time-mask boilerplate awkward |
| `nautilus_trader` | 9.0 | Best long-term, but overkill for backtest-only iteration. Graduate path for live. |
| `backtrader` | 6.5 | Legacy, last commit 2019. Don't pick. |
| `zipline-reloaded` | 4.0 | Equities-focused, weak futures support |

### Working ORB skeleton (`backtesting.py`)

```python
from datetime import time, timedelta
from backtesting import Backtest, Strategy
import pandas as pd

class ORBStrategy(Strategy):
    n_bars = 3  # 15-min ORB window = 3 × 5-min bars

    def init(self):
        self.orb_high = None
        self.orb_low = None
        self.orb_range = None
        self.daily_trades = 0
        self.entry_price = None
        self.stop_price = None
        self.t1_price = None
        self.t2_price = None
        self.in_position = False

    def next(self):
        bar_time = self.data.index[-1].time()

        if bar_time == time(9, 30):
            self.daily_trades = 0
            self.orb_high = None  # reset

        # ORB capture (9:30-9:45)
        if time(9, 30) <= bar_time <= time(9, 45):
            if self.orb_high is None:
                self.orb_high = self.data.High[-1]
                self.orb_low = self.data.Low[-1]
            else:
                self.orb_high = max(self.orb_high, self.data.High[-1])
                self.orb_low = min(self.orb_low, self.data.Low[-1])
            self.orb_range = self.orb_high - self.orb_low

        # Exits
        if self.in_position:
            if bar_time >= time(15, 0):
                self.position.close()
                self.in_position = False
            elif self.data.High[-1] >= self.t2_price:
                self.position.close()
                self.in_position = False
            elif self.data.Low[-1] <= self.stop_price:
                self.position.close()
                self.in_position = False

        # Entries
        if not self.in_position and self.daily_trades < 2 and self.orb_range:
            if time(9, 50) <= bar_time < time(14, 0):
                if self.data.Close[-1] > self.orb_high:
                    entry = self.data.Close[-1]
                    stop = self.orb_low - (self.orb_range * 0.25)
                    target = entry + (self.orb_range * 2.0)  # T2 at 2.0× ORB
                    risk = entry - stop
                    reward = target - entry
                    if reward / risk >= 1.5:  # min R:R
                        self.entry_price = entry
                        self.stop_price = stop
                        self.t2_price = target
                        self.buy(size=1)
                        self.in_position = True
                        self.daily_trades += 1

df = pd.read_csv('mnq_5min.csv', index_col='Date', parse_dates=True)
bt = Backtest(df, ORBStrategy, cash=5000, commission=.0005, exclusive_orders=True)
stats = bt.run()
print(stats)
bt.plot()
```

**Data sources:**
- Free: Polygon.io free tier (5-min bars, real-time delayed)
- Paid: CME direct, IQFeed (~$150/mo)

**Docs:**
- backtesting.py: https://kernc.github.io/backtesting.py/
- nautilus_trader (graduate): https://nautilustrader.io/

---

## Agent 5 — Circuit Breaker / Watchdog (DOM-broker-aware)

**Critical insight:** every public bot Agent 5 found handles **API broker** failures (TCP socket closes). None handle **DOM broker** failures (button class rotated, modal blocking, page unfocused). Our TV-CDP setup is on the frontier.

### Today's `side_not_found` cascade walkthrough

1. TV showed broker-selection modal (not Paper Trading session)
2. Bot tried trade #1 → DOM script returned `side_not_found` → bot logged "TRADE EXECUTED" + incremented counter
3. Bot tried trade #2 12s later → same DOM state → same failure → counter now 2
4. Daily 2-trade cap hit on zero actual trades

### Three patterns to implement

**Pattern 1: DOM health check before every order**
```python
async def execute_order_with_health_check(order):
    health = await broker.health_check()
    if health.state != "ready":
        circuit_breaker.open()
        logger.error(f"DOM unhealthy: {health.reason}")
        return False
    return await broker.place_order(order)
```
We already have `_has_open_position(tv)` — adding `tv_dom_ready(tv)` is the natural extension. Verify Buy/Sell selectors EXIST and Paper Trading session is connected.

**Pattern 2: Sliding-window failure detector by error TYPE**
```python
class BrokerFailureDetector:
    def __init__(self, window_size=5, threshold=3):
        self.failures = deque(maxlen=window_size)

    def record_failure(self, error_type, error_msg):
        self.failures.append({"type": error_type, "msg": error_msg, "time": time.time()})
        dom_failures = sum(1 for f in self.failures if f["type"] == "dom_state")
        if dom_failures >= self.threshold:
            self.halt_trading()
```

Today's bug: `side_not_found` was treated as retriable instead of recognized as DOM state failure that should halt immediately.

**Pattern 3: Watchdog with last-trade error inspection**
```python
async def health_check_loop(bot):
    while True:
        recent_trades = await bot.get_recent_trades(limit=2)
        if len(recent_trades) > 0:
            last_trade = recent_trades[-1]
            if last_trade.status == "failed" and "side_not_found" in last_trade.notes:
                await bot.emergency_stop()
                await notify_telegram("Circuit open: DOM state mismatch detected")
                break
```

### Why TradingView CDP is different

- **API brokers:** error = immediate socket close = obvious circuit trip
- **DOM brokers:** error = element query fails = invisible state mismatch, trade proceeds with garbage data

### URLs for inspection
- freqtrade retry logic: https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/exchange/exchange.py#L722
- Hummingbot reconnect: https://github.com/hummingbot/hummingbot/tree/master/hummingbot/connector
- Nautilus risk engine: https://github.com/nautechsystems/nautilus_trader/tree/develop/nautilus_trader/core
- TradeNodeX circuit breaker: https://github.com/TradeNodeX/TradeNodeX-AI-Automated-Trading

---

## Synthesis — what to actually build

After reviewing all 5 agents' findings, the highest-leverage changes for our bot are:

### Phase 1 — TV-Live Reads (high priority, low risk)
1. **`tv_dom_ready()`** — preflight DOM check before any order operation (Agent 5 Pattern 1). Would have stopped today's `side_not_found` cascade.
2. **`tv_get_positions()`** — extend `_has_open_position()` to extract full position records.
3. **`tv_get_today_fills()`** — count from journal where outcome is non-FAILED. Same answer as querying TV directly because journal only records on TV-confirmed fill.
4. **Replace local-state checks in combiner.poll()** with TV-live queries.

### Phase 2 — Stability Foundation (medium priority, medium risk)
1. **Order State Machine** — port Hummingbot's `InFlightOrder` (Agent 1).
2. **Reconciliation Loop (60s)** — freqtrade-style polling (Agent 2).
3. **Sliding-Window Circuit Breaker** — Agent 5 Pattern 2.
4. **Watchdog enhancement** — last-trade error inspection (Agent 5 Pattern 3).

### Phase 3 — Trade Management (low priority, trivial)
1. **TARGET_2_MULT 1.5 → 2.0** — addresses today's R:R complaint (Agent 3 evidence).
2. **`backtesting.py` framework** — set up so we can validate any future change before deploying (Agent 4).

### NOT building (per owner directive 2026-04-30)
- Volume filter / RVOL gate (Agent 3's highest-EV finding) — owner: no more entry-quality filters.
- MIN_RR_RATIO filter — same.
- ATR normalization filter — same.

These get logged here for future reference if WR data later justifies revisiting.

---

## Source repositories worth cloning for pattern study

| Repo | Why |
|---|---|
| https://github.com/hummingbot/hummingbot | InFlightOrder pattern (Phase 2.1) |
| https://github.com/freqtrade/freqtrade | Reconciliation pattern (Phase 2.2) |
| https://github.com/nautechsystems/nautilus_trader | Strict FSM if we ever go HFT |
| https://github.com/sam-bateman/trading-orb | ORB reference (10-year backtest) |
| https://github.com/2d2f/ORB_backtest | Alternative ORB ref (smaller but profitable) |
| https://github.com/kernc/backtesting.py | Phase 3 framework |

Clone into `C:\ZachAI\reference\` for offline study. Do not run them — pattern reference only.
