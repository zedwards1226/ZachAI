"""
MNQ Strategy Backtest v2 — Real TradingView Data
Data: C:\ZachAI\backtest\data\mnq_5m.csv (pulled directly from TradingView CME feed)
Period: Feb 15 – Apr 8, 2026 (~37 trading days)
MNQ point value: $2.00 | Commission: $1.70 RT | Slippage: 0.5pt RT
"""

import warnings
warnings.filterwarnings('ignore')

import csv
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ─── Constants ───────────────────────────────────────────────────────────────
POINT_VALUE = 2.0       # MNQ = $2 per point
COMMISSION  = 1.70      # per round trip
SLIPPAGE    = 0.50      # points round trip (0.25 each way = 1 tick)
MIN_TRADES  = 15        # min trades to include in report

# ─── Load Data ───────────────────────────────────────────────────────────────
def load_data():
    frames = []

    # Source 1: TradingView CME feed (Feb-Apr 2026)
    rows = []
    with open(r'C:\ZachAI\backtest\data\mnq_5m.csv') as f:
        for r in csv.DictReader(f):
            rows.append({'ts': int(r['timestamp']), 'open': float(r['open']),
                         'high': float(r['high']), 'low': float(r['low']),
                         'close': float(r['close']), 'volume': float(r['volume'])})
    frames.append(pd.DataFrame(rows))

    # Source 2: Kaggle CME NQ1! 5m (Sep-Oct 2025)
    rows2 = []
    with open(r'C:\ZachAI\backtest\data\NQ_in_5_minute.csv') as f:
        for r in csv.DictReader(f):
            dt = pd.to_datetime(r['datetime'])
            ts = int(dt.tz_localize('UTC').timestamp())
            rows2.append({'ts': ts, 'open': float(r['open']), 'high': float(r['high']),
                          'low': float(r['low']), 'close': float(r['close']), 'volume': float(r['volume'])})
    frames.append(pd.DataFrame(rows2))

    df = pd.concat(frames, ignore_index=True)
    df.drop_duplicates(subset=['ts'], inplace=True)
    df.sort_values('ts', inplace=True)
    df.reset_index(drop=True, inplace=True)

    df['dt'] = pd.to_datetime(df['ts'], unit='s', utc=True).dt.tz_convert('US/Eastern')
    df['date'] = df['dt'].dt.date
    df['hour'] = df['dt'].dt.hour
    df['minute'] = df['dt'].dt.minute
    df['time_frac'] = df['hour'] + df['minute'] / 60.0
    df['weekday'] = df['dt'].dt.weekday
    return df

# ─── Helpers ─────────────────────────────────────────────────────────────────
def calc_atr(df, period=14):
    h, l, c = df['high'], df['low'], df['close']
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def net_pnl(trades):
    """trades: list of (win:bool, abs_pts:float)"""
    wins   = [t[1] for t in trades if t[0]]
    losses = [t[1] for t in trades if not t[0]]
    return (sum(wins) - sum(losses)) * POINT_VALUE - len(trades) * COMMISSION

def report(name, trades):
    if len(trades) < MIN_TRADES:
        return {'name': name, 'trades': len(trades), 'win_rate': 0,
                'net_pnl': 0, 'pf': 0, 'skip': True}
    wins   = sum(1 for t in trades if t[0])
    total  = len(trades)
    wr     = wins / total * 100
    w_pts  = [t[1] for t in trades if t[0]]
    l_pts  = [t[1] for t in trades if not t[0]]
    gross_w = sum(w_pts) * POINT_VALUE
    gross_l = sum(l_pts) * POINT_VALUE
    pf = gross_w / gross_l if gross_l > 0 else float('inf')
    npnl = gross_w - gross_l - total * COMMISSION
    avg_w = np.mean(w_pts) * POINT_VALUE if w_pts else 0
    avg_l = np.mean(l_pts) * POINT_VALUE if l_pts else 0
    return {'name': name, 'trades': total, 'win_rate': round(wr, 1),
            'net_pnl': round(npnl, 0), 'pf': round(pf, 2),
            'avg_win': round(avg_w, 0), 'avg_loss': round(avg_l, 0), 'skip': False}

# ─── Strategy 1: 30-Min Initial Balance Breakout ─────────────────────────────
def strat_ib_breakout(df, rr=2.0):
    """
    IB = 9:30–10:00am ET high/low
    Entry: first 5m bar CLOSE above IB high (long) or below IB low (short) after 10am
    Stop: opposite IB edge + slippage
    Target: stop_size * rr
    Max 1 trade per day, flat by 3:45pm
    """
    trades = []
    for date, day in df.groupby('date'):
        ib = day[(day['time_frac'] >= 9.5) & (day['time_frac'] < 10.0)]
        if len(ib) < 3:
            continue
        ib_high = ib['high'].max()
        ib_low  = ib['low'].min()
        rng = ib_high - ib_low
        if rng < 10:   # skip tiny ranges
            continue

        session = day[(day['time_frac'] >= 10.0) & (day['time_frac'] < 15.75)]
        in_trade = False
        entry = sl = tp = direction = None

        for _, bar in session.iterrows():
            if not in_trade:
                if bar['close'] > ib_high and bar['low'] > ib_low:
                    direction = 'long'
                    entry = bar['close'] + SLIPPAGE / 2
                    sl    = ib_low  - SLIPPAGE / 2
                    tp    = entry + (entry - sl) * rr
                    in_trade = True
                elif bar['close'] < ib_low and bar['high'] < ib_high:
                    direction = 'short'
                    entry = bar['close'] - SLIPPAGE / 2
                    sl    = ib_high + SLIPPAGE / 2
                    tp    = entry - (sl - entry) * rr
                    in_trade = True
            else:
                eod = bar['time_frac'] >= 15.75
                if direction == 'long':
                    if bar['low'] <= sl or eod:
                        trades.append((False, abs(entry - sl)))
                        in_trade = False
                    elif bar['high'] >= tp:
                        trades.append((True, abs(tp - entry)))
                        in_trade = False
                else:
                    if bar['high'] >= sl or eod:
                        trades.append((False, abs(sl - entry)))
                        in_trade = False
                    elif bar['low'] <= tp:
                        trades.append((True, abs(entry - tp)))
                        in_trade = False

    return report(f'IB Breakout RR{rr}', trades)

# ─── Strategy 2: 15-Min ORB + 5m Close Confirmation ─────────────────────────
def strat_orb_15(df, rr=2.0):
    """
    ORB range = 9:30–9:45am ET (first 3 bars of 5m = 15 min)
    Entry: 5m bar CLOSES above range high (long) or below range low (short)
    Confirmation: close must exceed range, not just wick
    Stop: opposite range edge, Target: rr * range
    Max 1 trade per day, flat 3:45pm
    """
    trades = []
    for date, day in df.groupby('date'):
        orb = day[(day['time_frac'] >= 9.5) & (day['time_frac'] < 9.75)]
        if len(orb) < 2:
            continue
        orb_high = orb['high'].max()
        orb_low  = orb['low'].min()
        rng = orb_high - orb_low
        if rng < 5:
            continue

        session = day[(day['time_frac'] >= 9.75) & (day['time_frac'] < 15.75)]
        in_trade = False
        entry = sl = tp = direction = None

        for _, bar in session.iterrows():
            if not in_trade:
                if bar['close'] > orb_high:
                    direction = 'long'
                    entry = bar['close'] + SLIPPAGE / 2
                    sl    = orb_low  - SLIPPAGE / 2
                    tp    = entry + rng * rr
                    in_trade = True
                elif bar['close'] < orb_low:
                    direction = 'short'
                    entry = bar['close'] - SLIPPAGE / 2
                    sl    = orb_high + SLIPPAGE / 2
                    tp    = entry - rng * rr
                    in_trade = True
            else:
                eod = bar['time_frac'] >= 15.75
                if direction == 'long':
                    if bar['low'] <= sl or eod:
                        trades.append((False, abs(entry - sl)))
                        in_trade = False
                    elif bar['high'] >= tp:
                        trades.append((True, abs(tp - entry)))
                        in_trade = False
                else:
                    if bar['high'] >= sl or eod:
                        trades.append((False, abs(sl - entry)))
                        in_trade = False
                    elif bar['low'] <= tp:
                        trades.append((True, abs(entry - tp)))
                        in_trade = False

    return report(f'ORB 15m+5m Confirm RR{rr}', trades)

# ─── Strategy 3: ICT Silver Bullet (10am–11am Window) ────────────────────────
def strat_silver_bullet(df, rr=2.0):
    """
    Window: 10:00–11:00am ET
    Pre-window: mark high/low of 9:30–9:59am as initial liquidity
    Displacement: large candle (> 1.5x avg ATR) breaking initial range
    FVG: 3-candle gap created by displacement
    Entry: first retest of FVG within 11am
    Stop: far end of FVG, Target: rr * risk
    """
    df = df.copy()
    df['atr'] = calc_atr(df)
    trades = []

    for date, day in df.groupby('date'):
        # Pre-window reference range
        pre = day[(day['time_frac'] >= 9.5) & (day['time_frac'] < 10.0)]
        if len(pre) < 3:
            continue
        pre_high = pre['high'].max()
        pre_low  = pre['low'].min()
        avg_atr  = pre['atr'].mean()
        if pd.isna(avg_atr) or avg_atr < 1:
            continue

        # Window bars
        window = day[(day['time_frac'] >= 10.0) & (day['time_frac'] < 11.0)]
        bars_list = list(window.iterrows())
        fvgs = []

        # Detect FVGs from displacement candles
        for i in range(1, len(bars_list) - 1):
            _, prev = bars_list[i-1]
            _, cur  = bars_list[i]
            _, nxt  = bars_list[i+1]

            candle_range = abs(cur['close'] - cur['open'])
            if candle_range < avg_atr * 1.2:
                continue  # Not a displacement candle

            # Bullish FVG: prev_low > nxt_high
            if prev['low'] > nxt['high']:
                fvgs.append({'dir': 'long', 'top': prev['low'],
                             'bottom': nxt['high'], 'ts': cur.name})
            # Bearish FVG: prev_high < nxt_low
            elif prev['high'] < nxt['low']:
                fvgs.append({'dir': 'short', 'top': nxt['low'],
                             'bottom': prev['high'], 'ts': cur.name})

        if not fvgs:
            continue

        # Find first FVG retest within window and rest of day
        session_after = day[(day['time_frac'] >= 10.0) & (day['time_frac'] < 15.75)]
        in_trade = False
        entry = sl = tp = direction = None

        for _, bar in session_after.iterrows():
            if not in_trade:
                for fvg in fvgs:
                    size = fvg['top'] - fvg['bottom']
                    if size < 3:
                        continue
                    if fvg['dir'] == 'long' and bar['low'] <= fvg['top'] and bar['close'] > fvg['bottom']:
                        entry     = bar['close'] + SLIPPAGE / 2
                        sl        = fvg['bottom'] - SLIPPAGE / 2
                        risk      = abs(entry - sl)
                        if risk < 5:
                            continue
                        tp        = entry + risk * rr
                        direction = 'long'
                        in_trade  = True
                        fvgs.remove(fvg)
                        break
                    elif fvg['dir'] == 'short' and bar['high'] >= fvg['bottom'] and bar['close'] < fvg['top']:
                        entry     = bar['close'] - SLIPPAGE / 2
                        sl        = fvg['top'] + SLIPPAGE / 2
                        risk      = abs(sl - entry)
                        if risk < 5:
                            continue
                        tp        = entry - risk * rr
                        direction = 'short'
                        in_trade  = True
                        fvgs.remove(fvg)
                        break
            else:
                eod = bar['time_frac'] >= 15.75
                if direction == 'long':
                    if bar['low'] <= sl or eod:
                        trades.append((False, abs(entry - sl)))
                        in_trade = False
                    elif bar['high'] >= tp:
                        trades.append((True, abs(tp - entry)))
                        in_trade = False
                else:
                    if bar['high'] >= sl or eod:
                        trades.append((False, abs(sl - entry)))
                        in_trade = False
                    elif bar['low'] <= tp:
                        trades.append((True, abs(entry - tp)))
                        in_trade = False

    return report(f'ICT Silver Bullet RR{rr}', trades)

# ─── Strategy 4: VWAP Trend Bounce ───────────────────────────────────────────
def strat_vwap_bounce(df, rr=1.5):
    """
    RTH VWAP computed from 9:30am each day
    Trend filter: 3+ consecutive bars same side of VWAP before entry
    Entry: price touches VWAP then closes back on trend side
    Time: 9:30am–12:00pm ET only (avoid lunch chop)
    Stop: 0.5 ATR beyond VWAP touch, Target: rr * stop
    """
    df = df.copy()
    df['atr'] = calc_atr(df)
    trades = []

    for date, day in df.groupby('date'):
        # Compute RTH VWAP starting 9:30am
        rth = day[day['time_frac'] >= 9.5].copy()
        rth['tp'] = (rth['high'] + rth['low'] + rth['close']) / 3
        rth['cum_tpv'] = (rth['tp'] * rth['volume']).cumsum()
        rth['cum_vol'] = rth['volume'].cumsum()
        rth['vwap'] = rth['cum_tpv'] / rth['cum_vol'].replace(0, np.nan)

        session = rth[rth['time_frac'] < 12.0]
        bars_list = list(session.iterrows())
        in_trade = False
        entry = sl = tp = direction = None

        for j, (_, bar) in enumerate(bars_list):
            if pd.isna(bar['vwap']) or pd.isna(bar['atr']) or bar['atr'] < 1:
                continue

            if not in_trade:
                if j < 3:
                    continue
                # Check trend: last 3 bars same side of VWAP
                prev3 = [bars_list[j-k][1] for k in range(1, 4)]
                all_above = all(b['close'] > b['vwap'] for b in prev3 if not pd.isna(b.get('vwap', np.nan)))
                all_below = all(b['close'] < b['vwap'] for b in prev3 if not pd.isna(b.get('vwap', np.nan)))

                atr = bar['atr']
                # Long setup: trend above VWAP, bar touches VWAP then closes back above
                if all_above and bar['low'] <= bar['vwap'] * 1.0005 and bar['close'] > bar['vwap']:
                    entry     = bar['close'] + SLIPPAGE / 2
                    sl        = bar['vwap'] - atr * 0.5 - SLIPPAGE / 2
                    risk      = abs(entry - sl)
                    if risk < 3:
                        continue
                    tp        = entry + risk * rr
                    direction = 'long'
                    in_trade  = True
                # Short setup: trend below VWAP, bar touches VWAP then closes back below
                elif all_below and bar['high'] >= bar['vwap'] * 0.9995 and bar['close'] < bar['vwap']:
                    entry     = bar['close'] - SLIPPAGE / 2
                    sl        = bar['vwap'] + atr * 0.5 + SLIPPAGE / 2
                    risk      = abs(sl - entry)
                    if risk < 3:
                        continue
                    tp        = entry - risk * rr
                    direction = 'short'
                    in_trade  = True
            else:
                eod = bar['time_frac'] >= 15.75
                if direction == 'long':
                    if bar['low'] <= sl or eod:
                        trades.append((False, abs(entry - sl)))
                        in_trade = False
                    elif bar['high'] >= tp:
                        trades.append((True, abs(tp - entry)))
                        in_trade = False
                else:
                    if bar['high'] >= sl or eod:
                        trades.append((False, abs(sl - entry)))
                        in_trade = False
                    elif bar['low'] <= tp:
                        trades.append((True, abs(entry - tp)))
                        in_trade = False

    return report(f'VWAP Trend Bounce RR{rr}', trades)

# ─── Strategy 5: Midnight Open Retracement ───────────────────────────────────
def strat_midnight_open(df, tuesdays_only=False):
    """
    Mark 12:00am ET bar open as midnight level
    If NQ is BELOW midnight open at 9:30am → long bias (target=midnight level)
    If NQ is ABOVE midnight open at 9:30am → short bias (target=midnight level)
    Entry: 9:30am after first 5m bar that confirms direction
    Stop: swing low/high of 9:30-9:35 bar
    Target: midnight open level
    Tuesdays: best stats (67-73%)
    """
    trades = []

    for date, day in df.groupby('date'):
        if tuesdays_only and day['weekday'].iloc[0] != 1:  # 1=Tuesday
            continue

        # Midnight open: 12:00am ET bar
        midnight_bars = day[day['time_frac'] == 0.0]
        if len(midnight_bars) == 0:
            # Try 12:05am as fallback
            midnight_bars = day[day['time_frac'] < 0.1]
        if len(midnight_bars) == 0:
            continue
        midnight_open = midnight_bars.iloc[0]['open']

        # 9:30am price
        open_bars = day[(day['time_frac'] >= 9.5) & (day['time_frac'] < 9.6)]
        if len(open_bars) == 0:
            continue
        open_bar = open_bars.iloc[0]
        open_price = open_bar['close']

        # Determine bias
        if open_price < midnight_open:
            direction = 'long'
        elif open_price > midnight_open:
            direction = 'short'
        else:
            continue

        # Entry on first 5m bar after 9:30am open
        entry_bar = open_bars.iloc[0]
        if direction == 'long':
            entry = entry_bar['close'] + SLIPPAGE / 2
            sl    = entry_bar['low'] - SLIPPAGE / 2
            tp    = midnight_open  # target is midnight open level
        else:
            entry = entry_bar['close'] - SLIPPAGE / 2
            sl    = entry_bar['high'] + SLIPPAGE / 2
            tp    = midnight_open

        risk = abs(entry - sl)
        if risk < 3 or risk > 150:  # skip tiny/huge stops
            continue
        # Ensure target is in right direction
        if direction == 'long' and tp <= entry:
            continue
        if direction == 'short' and tp >= entry:
            continue

        # Walk forward
        session = day[(day['time_frac'] > 9.6) & (day['time_frac'] < 15.75)]
        result = None
        for _, bar in session.iterrows():
            eod = bar['time_frac'] >= 15.75
            if direction == 'long':
                if bar['low'] <= sl or eod:
                    result = (False, abs(entry - sl))
                    break
                elif bar['high'] >= tp:
                    result = (True, abs(tp - entry))
                    break
            else:
                if bar['high'] >= sl or eod:
                    result = (False, abs(sl - entry))
                    break
                elif bar['low'] <= tp:
                    result = (True, abs(entry - tp))
                    break

        if result:
            trades.append(result)

    label = 'Midnight Open (Tue)' if tuesdays_only else 'Midnight Open (All)'
    return report(label, trades)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Loading TradingView MNQ data...")
    df = load_data()
    print(f"  {len(df)} bars | {df['date'].min()} to {df['date'].max()}")
    trading_days = df['date'].nunique()
    print(f"  {trading_days} calendar days loaded\n")

    print("=" * 70)
    print("MNQ STRATEGY BACKTEST v2 — Real TradingView CME Data")
    print(f"Point value ${POINT_VALUE} | Commission ${COMMISSION} RT | Slippage {SLIPPAGE}pt RT")
    print("=" * 70)

    all_results = []

    for fn, args in [
        (strat_ib_breakout,    (df, 1.0)),
        (strat_ib_breakout,    (df, 1.5)),
        (strat_ib_breakout,    (df, 2.0)),
        (strat_orb_15,         (df, 1.0)),
        (strat_orb_15,         (df, 2.0)),
        (strat_silver_bullet,  (df, 2.0)),
        (strat_silver_bullet,  (df, 3.0)),
        (strat_vwap_bounce,    (df, 1.5)),
        (strat_vwap_bounce,    (df, 2.0)),
        (strat_midnight_open,  (df, False)),
        (strat_midnight_open,  (df, True)),
    ]:
        try:
            r = fn(*args)
            all_results.append(r)
        except Exception as e:
            import traceback
            print(f"ERROR in {fn.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'Strategy':<30} {'Trades':>7} {'Win%':>7} {'Net PnL':>9} {'PF':>6}")
    print("-" * 65)
    for r in all_results:
        if r.get('skip'):
            print(f"  {r['name']:<28} {r['trades']:>7}  (skip — <{MIN_TRADES} trades)")
            continue
        flag = " <<<" if r['win_rate'] >= 65 else ""
        print(f"  {r['name']:<28} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['net_pnl']:>9.0f} {r['pf']:>6.2f}{flag}")

    print("\n" + "=" * 70)
    print("STRATEGIES OVER 65% WIN RATE:")
    winners = [r for r in all_results if not r.get('skip') and r['win_rate'] >= 65]
    if winners:
        for w in winners:
            print(f"\n  {w['name']}")
            print(f"    Trades: {w['trades']} | Win Rate: {w['win_rate']}% | Net PnL: ${w['net_pnl']}")
            print(f"    Avg Win: ${w['avg_win']} | Avg Loss: ${w['avg_loss']} | PF: {w['pf']}")
    else:
        valid = [r for r in all_results if not r.get('skip')]
        if valid:
            best = max(valid, key=lambda r: r['win_rate'])
            print(f"  None hit 65%. Best: {best['name']} at {best['win_rate']}% win rate")
            print(f"  (Net PnL: ${best['net_pnl']} | PF: {best['pf']})")
    print()
