"""
MNQ Futures Strategy Backtester
Tests multiple strategies on NQ=F 5m/15m data
Looking for >65% win rate strategies
"""

import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ─── Data Download ────────────────────────────────────────────────────────────

def get_data(symbol="NQ=F", interval="5m", days=59):
    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.download(symbol, start=start, end=end, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open','High','Low','Close','Volume']].dropna()
    df.index = pd.to_datetime(df.index)
    # Convert to Eastern time
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('US/Eastern')
    else:
        df.index = df.index.tz_convert('US/Eastern')
    return df

# ─── Helper ───────────────────────────────────────────────────────────────────

def calc_atr(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def run_trades(signals, df, sl_pts, tp_pts, direction='long'):
    """Simulate trades. Returns list of (win, pnl_pts)"""
    trades = []
    in_trade = False
    entry_price = None
    for i, (ts, row) in enumerate(df.iterrows()):
        if not in_trade and signals.get(ts, False):
            in_trade = True
            entry_price = row['Close']
            if direction == 'long':
                sl = entry_price - sl_pts
                tp = entry_price + tp_pts
            else:
                sl = entry_price + sl_pts
                tp = entry_price - tp_pts
        elif in_trade:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, -sl_pts))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, tp_pts))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, -sl_pts))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, tp_pts))
                    in_trade = False
    return trades

def report(name, trades, point_value=2.0):
    if not trades:
        return f"{name}: 0 trades"
    wins = sum(1 for t in trades if t[0])
    total = len(trades)
    win_rate = wins / total * 100
    # Net PnL: wins add pts, losses subtract pts
    net_pts = sum(t[1] for t in trades if t[0]) - sum(t[1] for t in trades if not t[0])
    gross_pnl = net_pts * point_value
    avg_win = np.mean([t[1] for t in trades if t[0]]) * point_value if wins > 0 else 0
    avg_loss = np.mean([t[1] for t in trades if not t[0]]) * point_value if (total-wins) > 0 else 0
    pf = (wins * avg_win) / ((total - wins) * avg_loss) if (total-wins) > 0 and avg_loss > 0 else float('inf')
    return {
        'name': name,
        'trades': total,
        'win_rate': round(win_rate, 1),
        'gross_pnl': round(gross_pnl, 0),
        'avg_win': round(avg_win, 0),
        'avg_loss': round(avg_loss, 0),
        'profit_factor': round(pf, 2)
    }

# ─── Strategy 1: ORB (Opening Range Breakout) ─────────────────────────────────

def strategy_orb(df, rr=2.0):
    """
    Opening Range: 9:30-10:00am ET (first 6 bars on 5m)
    Entry: break above/below range with 1-bar confirmation
    Stop: opposite side of range, Target: RR * range size
    """
    signals = {}
    daily_groups = df.groupby(df.index.date)

    for date, day_df in daily_groups:
        # Opening range: 9:30-10:00am ET
        or_bars = day_df.between_time('09:30', '09:59')
        if len(or_bars) < 3:
            continue
        or_high = or_bars['High'].max()
        or_low = or_bars['Low'].min()
        range_size = or_high - or_low
        if range_size < 5:  # too small
            continue

        # After 10am: look for breakout
        session_bars = day_df.between_time('10:00', '15:00')
        broke_high = False
        broke_low = False
        for ts, bar in session_bars.iterrows():
            if not broke_high and not broke_low:
                if bar['Close'] > or_high and bar['Low'] > or_low:
                    signals[ts] = ('long', bar['Close'], range_size * rr, range_size)
                    broke_high = True
                elif bar['Close'] < or_low and bar['High'] < or_high:
                    signals[ts] = ('short', bar['Close'], range_size * rr, range_size)
                    broke_low = True

    trades = []
    in_trade = False
    entry_price = tp = sl = direction = None
    for ts, row in df.iterrows():
        if not in_trade and ts in signals:
            direction, entry_price, tp_pts, sl_pts = signals[ts]
            in_trade = True
            if direction == 'long':
                sl = entry_price - sl_pts
                tp = entry_price + tp_pts
            else:
                sl = entry_price + sl_pts
                tp = entry_price - tp_pts
        elif in_trade:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    in_trade = False
            # Force close at 3pm ET if still open
            if in_trade and ts.hour >= 15:
                pnl = row['Close'] - entry_price if direction == 'long' else entry_price - row['Close']
                trades.append((pnl > 0, abs(pnl)))
                in_trade = False
    return report("ORB 9:30-10am RR2", trades)

# ─── Strategy 2: EMA 9/21 Crossover + RSI Filter ─────────────────────────────

def strategy_ema_cross(df, ema_fast=9, ema_slow=21, rsi_period=14, rr=2.0):
    """
    Long: EMA9 crosses above EMA21, RSI 40-70
    Short: EMA9 crosses below EMA21, RSI 30-60
    Stop: 1 ATR, Target: 2 ATR
    Session: 9:30am-3:30pm ET only
    """
    df = df.copy()
    df['ema_fast'] = df['Close'].ewm(span=ema_fast).mean()
    df['ema_slow'] = df['Close'].ewm(span=ema_slow).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['atr'] = calc_atr(df)

    trades = []
    in_trade = False
    entry_price = tp = sl = direction = None

    prev_fast = prev_slow = None
    for ts, row in df.iterrows():
        if pd.isna(row['ema_fast']) or pd.isna(row['atr']):
            prev_fast, prev_slow = row['ema_fast'], row['ema_slow']
            continue

        hour = ts.hour
        if not (9 <= hour < 15):
            if in_trade:
                # Close at session end
                trades.append((None, row['Close'] - entry_price if direction == 'long' else entry_price - row['Close']))
                in_trade = False
            prev_fast, prev_slow = row['ema_fast'], row['ema_slow']
            continue

        if not in_trade:
            atr = row['atr']
            if atr < 1:
                prev_fast, prev_slow = row['ema_fast'], row['ema_slow']
                continue
            # Long cross
            if prev_fast and prev_slow and prev_fast <= prev_slow and row['ema_fast'] > row['ema_slow']:
                if 40 <= row['rsi'] <= 70:
                    direction = 'long'
                    entry_price = row['Close']
                    sl = entry_price - atr
                    tp = entry_price + atr * rr
                    in_trade = True
            # Short cross
            elif prev_fast and prev_slow and prev_fast >= prev_slow and row['ema_fast'] < row['ema_slow']:
                if 30 <= row['rsi'] <= 60:
                    direction = 'short'
                    entry_price = row['Close']
                    sl = entry_price + atr
                    tp = entry_price - atr * rr
                    in_trade = True
        else:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    in_trade = False

        prev_fast, prev_slow = row['ema_fast'], row['ema_slow']

    def norm(t):
        win, pnl = t if len(t) == 2 else (t[0], t[1])
        if win is None:
            return (pnl > 0, abs(pnl))
        return (win, abs(pnl))
    trades = [norm(t) for t in trades if t[1] != 0]
    return report("EMA 9/21 Cross + RSI", trades)

# ─── Strategy 3: VWAP Mean Reversion ─────────────────────────────────────────

def strategy_vwap(df, rr=2.0):
    """
    Long: Price pulls back to VWAP from above, closes back above VWAP
    Short: Price rallies to VWAP from below, closes back below VWAP
    Stop: 0.5 ATR, Target: 1 ATR * RR
    Session: 10am-2pm ET (avoid first/last 30 min noise)
    """
    df = df.copy()
    df['atr'] = calc_atr(df)

    # Compute daily VWAP
    df['date'] = df.index.date
    df['tp'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['cum_tpv'] = df.groupby('date').apply(lambda g: (g['tp'] * g['Volume']).cumsum()).values
    df['cum_vol'] = df.groupby('date')['Volume'].cumsum().values
    df['vwap'] = df['cum_tpv'] / df['cum_vol']

    trades = []
    in_trade = False
    entry_price = tp = sl = direction = None
    prev_above_vwap = None

    for ts, row in df.iterrows():
        if pd.isna(row['vwap']) or pd.isna(row['atr']):
            continue
        hour = ts.hour
        above_vwap = row['Close'] > row['vwap']

        if not in_trade:
            if 10 <= hour < 14 and row['atr'] > 1:
                atr = row['atr']
                # Long: was above VWAP, dipped to VWAP, now back above
                if prev_above_vwap is True and not above_vwap:
                    pass  # still below, wait
                elif prev_above_vwap is False and above_vwap and row['Low'] <= row['vwap'] * 1.001:
                    direction = 'long'
                    entry_price = row['Close']
                    sl = entry_price - atr * 0.5
                    tp = entry_price + atr * rr
                    in_trade = True
                # Short: was below VWAP, rallied to VWAP, now back below
                elif prev_above_vwap is True and not above_vwap and row['High'] >= row['vwap'] * 0.999:
                    direction = 'short'
                    entry_price = row['Close']
                    sl = entry_price + atr * 0.5
                    tp = entry_price - atr * rr
                    in_trade = True
        else:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    in_trade = False

        prev_above_vwap = above_vwap

    return report("VWAP Mean Reversion", trades)

# ─── Strategy 4: ICT Silver Bullet (FVG Entry) ────────────────────────────────

def strategy_silver_bullet(df, rr=2.0):
    """
    ICT Silver Bullet
    Windows: 10:00-11:00am ET and 2:00-3:00pm ET
    Entry: Fair Value Gap (3-candle pattern), enter on retest
    Stop: gap bottom/top, Target: 2R
    """
    df = df.copy()

    # Find FVGs within kill zones
    fvg_zones = []  # (ts, direction, top, bottom)

    bars = list(df.iterrows())
    for i in range(1, len(bars) - 1):
        ts, cur = bars[i]
        _, prev = bars[i-1]
        _, nxt = bars[i+1]
        hour = ts.hour
        minute = ts.minute

        # Kill zones: 10:00-10:55am and 2:00-2:55pm ET
        in_kz = (10 <= hour < 11) or (14 <= hour < 15)
        if not in_kz:
            continue

        # Bullish FVG: prev.low > nxt.high (gap up)
        if prev['Low'] > nxt['High']:
            fvg_zones.append({
                'ts': ts, 'dir': 'long',
                'top': prev['Low'], 'bottom': nxt['High'],
                'date': ts.date(), 'expires': ts + pd.Timedelta(hours=5)
            })
        # Bearish FVG: prev.high < nxt.low (gap down)
        elif prev['High'] < nxt['Low']:
            fvg_zones.append({
                'ts': ts, 'dir': 'short',
                'top': nxt['Low'], 'bottom': prev['High'],
                'date': ts.date(), 'expires': ts + pd.Timedelta(hours=5)
            })

    # Now simulate entries: price retests FVG after formation
    trades = []
    active_fvgs = []
    in_trade = False
    entry_price = tp = sl = direction = None

    for ts, row in df.iterrows():
        # Add newly formed FVGs
        new_fvgs = [f for f in fvg_zones if f['ts'] == ts]
        active_fvgs.extend(new_fvgs)
        # Expire old
        active_fvgs = [f for f in active_fvgs if ts <= f['expires'] and ts.date() == f['date']]

        if not in_trade and 9 <= ts.hour < 15:
            for fvg in active_fvgs[:]:
                mid = (fvg['top'] + fvg['bottom']) / 2
                size = fvg['top'] - fvg['bottom']
                if size < 3:
                    continue
                if fvg['dir'] == 'long' and row['Low'] <= fvg['top'] and row['Close'] > fvg['bottom']:
                    entry_price = row['Close']
                    sl = fvg['bottom'] - size * 0.1
                    tp = entry_price + (entry_price - sl) * rr
                    direction = 'long'
                    in_trade = True
                    active_fvgs.remove(fvg)
                    break
                elif fvg['dir'] == 'short' and row['High'] >= fvg['bottom'] and row['Close'] < fvg['top']:
                    entry_price = row['Close']
                    sl = fvg['top'] + size * 0.1
                    tp = entry_price - (sl - entry_price) * rr
                    direction = 'short'
                    in_trade = True
                    active_fvgs.remove(fvg)
                    break
        elif in_trade:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    in_trade = False

    return report("ICT Silver Bullet FVG", trades)

# ─── Strategy 5: 15m EMA Trend + 5m Pullback ─────────────────────────────────

def strategy_trend_pullback(df5, df15, rr=2.5):
    """
    15m bias: price above/below EMA 50
    5m entry: RSI < 35 (long) or RSI > 65 (short) during trend
    Stop: 1.5 ATR, Target: 2.5 ATR
    """
    df15 = df15.copy()
    df15['ema50'] = df15['Close'].ewm(span=50).mean()
    df15_bias = df15['ema50'].reindex(df5.index, method='ffill')

    df5 = df5.copy()
    delta = df5['Close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df5['rsi'] = 100 - (100 / (1 + rs))
    df5['atr'] = calc_atr(df5)
    df5['bias_ema'] = df15_bias

    trades = []
    in_trade = False
    entry_price = tp = sl = direction = None

    for ts, row in df5.iterrows():
        if pd.isna(row['rsi']) or pd.isna(row['atr']) or pd.isna(row['bias_ema']):
            continue
        hour = ts.hour
        if not (9 <= hour < 15):
            continue

        if not in_trade and row['atr'] > 1:
            atr = row['atr']
            # Long: 15m bullish bias, 5m oversold
            if row['Close'] > row['bias_ema'] and row['rsi'] < 35:
                direction = 'long'
                entry_price = row['Close']
                sl = entry_price - atr * 1.5
                tp = entry_price + atr * rr
                in_trade = True
            # Short: 15m bearish bias, 5m overbought
            elif row['Close'] < row['bias_ema'] and row['rsi'] > 65:
                direction = 'short'
                entry_price = row['Close']
                sl = entry_price + atr * 1.5
                tp = entry_price - atr * rr
                in_trade = True
        elif in_trade:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    in_trade = False

    return report("15m Trend + 5m RSI Pullback", trades)

# ─── Strategy 6: London/NY Session Momentum ───────────────────────────────────

def strategy_session_momentum(df, rr=2.0):
    """
    9:35-9:45am ET: Capture opening momentum
    Direction = first 5m candle close vs open
    Stop: low of first candle (long) or high (short)
    Max 1 trade per day
    """
    trades = []
    daily_groups = df.groupby(df.index.date)

    for date, day_df in daily_groups:
        session = day_df.between_time('09:30', '09:35')
        if len(session) == 0:
            continue
        first_bar = session.iloc[0]
        direction = 'long' if first_bar['Close'] > first_bar['Open'] else 'short'
        body = abs(first_bar['Close'] - first_bar['Open'])
        if body < 5:  # too small
            continue

        if direction == 'long':
            entry_price = first_bar['Close']
            sl = first_bar['Low'] - 2
            tp = entry_price + (entry_price - sl) * rr
        else:
            entry_price = first_bar['Close']
            sl = first_bar['High'] + 2
            tp = entry_price - (sl - entry_price) * rr

        # Walk forward remaining session
        rest = day_df.between_time('09:36', '15:00')
        filled = False
        for ts, bar in rest.iterrows():
            if direction == 'long':
                if bar['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    filled = True
                    break
                elif bar['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    filled = True
                    break
            else:
                if bar['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    filled = True
                    break
                elif bar['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    filled = True
                    break

    return report("Opening 5m Momentum", trades)

# ─── Strategy 7: EMA 20 Bounce (Trend Following) ─────────────────────────────

def strategy_ema20_bounce(df, rr=2.0):
    """
    Trend: EMA 20 slope positive/negative
    Entry: candle closes above EMA20 after touching it (long) or below (short)
    Stop: 0.75 ATR below EMA, Target: 2R
    """
    df = df.copy()
    df['ema20'] = df['Close'].ewm(span=20).mean()
    df['ema50'] = df['Close'].ewm(span=50).mean()
    df['atr'] = calc_atr(df)

    trades = []
    in_trade = False
    entry_price = tp = sl = direction = None
    prev_below = None
    prev_above = None

    for ts, row in df.iterrows():
        if pd.isna(row['ema20']) or pd.isna(row['atr']):
            prev_below = row['Close'] < row['ema20']
            prev_above = row['Close'] > row['ema20']
            continue
        hour = ts.hour
        if not (9 <= hour < 15):
            if in_trade:
                pnl = row['Close'] - entry_price if direction == 'long' else entry_price - row['Close']
                trades.append((pnl > 0, abs(pnl)))
                in_trade = False
            prev_below = row['Close'] < row['ema20']
            prev_above = row['Close'] > row['ema20']
            continue

        if not in_trade and row['atr'] > 1:
            atr = row['atr']
            trend_up = row['ema20'] > row['ema50']
            trend_dn = row['ema20'] < row['ema50']

            # Long bounce: was below EMA20, now above, trend is up
            if prev_below and row['Close'] > row['ema20'] and trend_up:
                if row['Low'] <= row['ema20'] * 1.001:  # touched EMA
                    direction = 'long'
                    entry_price = row['Close']
                    sl = row['ema20'] - atr * 0.75
                    tp = entry_price + (entry_price - sl) * rr
                    in_trade = True
            # Short bounce: was above EMA20, now below, trend is down
            elif prev_above and row['Close'] < row['ema20'] and trend_dn:
                if row['High'] >= row['ema20'] * 0.999:
                    direction = 'short'
                    entry_price = row['Close']
                    sl = row['ema20'] + atr * 0.75
                    tp = entry_price - (sl - entry_price) * rr
                    in_trade = True
        elif in_trade:
            if direction == 'long':
                if row['Low'] <= sl:
                    trades.append((False, abs(entry_price - sl)))
                    in_trade = False
                elif row['High'] >= tp:
                    trades.append((True, abs(tp - entry_price)))
                    in_trade = False
            else:
                if row['High'] >= sl:
                    trades.append((False, abs(sl - entry_price)))
                    in_trade = False
                elif row['Low'] <= tp:
                    trades.append((True, abs(entry_price - tp)))
                    in_trade = False

        prev_below = row['Close'] < row['ema20']
        prev_above = row['Close'] > row['ema20']

    return report("EMA 20 Trend Bounce", trades)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("Downloading NQ=F 5m data (59 days)...")
    df5 = get_data("NQ=F", "5m", 59)
    print(f"  Got {len(df5)} bars from {df5.index[0].date()} to {df5.index[-1].date()}")

    print("Downloading NQ=F 15m data (59 days)...")
    df15 = get_data("NQ=F", "15m", 59)
    print(f"  Got {len(df15)} bars\n")

    print("=" * 60)
    print("STRATEGY BACKTEST RESULTS — MNQ 5m (NQ=F proxy)")
    print("MNQ point value = $2.00 | RR = 2:1 unless noted")
    print("=" * 60)

    results = []
    for fn, args in [
        (strategy_orb, (df5,)),
        (strategy_ema_cross, (df5,)),
        (strategy_vwap, (df5,)),
        (strategy_silver_bullet, (df5,)),
        (strategy_ema20_bounce, (df5,)),
        (strategy_session_momentum, (df5,)),
        (strategy_trend_pullback, (df5, df15)),
    ]:
        try:
            r = fn(*args)
            results.append(r)
        except Exception as e:
            results.append(f"{fn.__name__}: ERROR - {e}")

    print(f"\n{'Strategy':<28} {'Trades':>7} {'Win%':>7} {'PnL$':>8} {'PF':>6}")
    print("-" * 60)
    for r in results:
        if isinstance(r, dict):
            flag = " <<< >65%" if r['win_rate'] >= 65 else ""
            print(f"{r['name']:<28} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['gross_pnl']:>8.0f} {r['profit_factor']:>6.2f}{flag}")
        else:
            print(r)

    print("\n--- Winners (>65% win rate) ---")
    winners = [r for r in results if isinstance(r, dict) and r['win_rate'] >= 65]
    if winners:
        for w in winners:
            print(f"\n{w['name']}")
            print(f"  Trades: {w['trades']}, Win Rate: {w['win_rate']}%")
            print(f"  Net PnL: ${w['gross_pnl']}, PF: {w['profit_factor']}")
    else:
        print("None at 2:1 RR — testing tighter RR ratios for higher win%...\n")

    # ── RR sweep: test EMA cross and trend-pullback at tighter targets ──────
    print("=" * 60)
    print("RR SWEEP — Finding win rate vs RR tradeoff")
    print("=" * 60)
    for rr_val in [1.0, 1.2, 1.5, 2.0]:
        r1 = strategy_ema_cross(df5, rr=rr_val)
        r2 = strategy_trend_pullback(df5, df15, rr=rr_val)
        r3 = strategy_silver_bullet(df5, rr=rr_val)
        r4 = strategy_orb(df5, rr=rr_val)
        for r in [r1, r2, r3, r4]:
            if isinstance(r, dict) and r['trades'] >= 10:
                flag = " <<<" if r['win_rate'] >= 65 else ""
                print(f"RR={rr_val}  {r['name']:<28} {r['trades']:>5}tr  {r['win_rate']:>5.1f}%  ${r['gross_pnl']:>8.0f}  PF={r['profit_factor']}{flag}")

    print("\n--- SUMMARY ---")
    print("Any strategy with win%>=65 AND PF>=1.5 is worth forward testing.")
