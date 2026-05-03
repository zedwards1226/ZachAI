"""OmniAlpha Terminal — Bloomberg-style dark dashboard.

Layout (top → bottom):
  1. Header: capital, day P&L, time
  2. Live BTC / ETH ticker (CoinGecko free)
  3. YOUR open positions with strike-vs-price mini chart
  4. Strategy health row
  5. Kalshi LIVE TAPE — every fill across the platform (left)
     + Kalshi TRENDING events + TOP-VOLUME markets (right)
  6. CRYPTO NEWS feed (bottom, RSS aggregator)
  7. Closed trades log

Auto-refreshes every 10s. All feeds are free, no API keys.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from config import (
    DAILY_MAX_LOSS_USD,
    DB_PATH,
    PAPER_MODE,
    PER_TRADE_MAX_RISK_USD,
    STARTING_CAPITAL_USD,
)
from data_layer.database import get_conn
from dashboard.feeds import (
    fetch_crypto_history,
    fetch_crypto_news,
    fetch_crypto_prices,
    fetch_kalshi_live_trades,
    fetch_kalshi_top_markets,
    fetch_kalshi_trending_events,
)


# ─── Page setup + dark theme ────────────────────────────────────────────
st.set_page_config(
    page_title="OmniAlpha Terminal",
    page_icon="●",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Bloomberg-flavored dark theme. Pure black background, amber headers,
# green for win / red for loss, JetBrains Mono for data.
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@500;700&display=swap');
.main {background-color: #000000;}
.stApp {background-color: #000000;}
.stApp, .stApp p, .stApp div, .stApp span {color: #d4d4d4;}
h1, h2, h3, h4 {color: #ffb000 !important; font-family: 'Inter', sans-serif !important; letter-spacing: 0.04em;}
.stMetricLabel {color: #888 !important; text-transform: uppercase; font-size: 0.7rem !important;}
.stMetricValue {color: #ffb000 !important; font-family: 'JetBrains Mono', monospace !important;}
.stMetricDelta {font-family: 'JetBrains Mono', monospace !important;}
code, pre, .code-block, .stCode {font-family: 'JetBrains Mono', monospace !important; background: #0a0a0a !important;}
hr {border-color: #1a1a1a;}
section[data-testid="stSidebar"] {background: #050505;}
.stDataFrame, .stTable {background-color: #0a0a0a; border: 1px solid #1a1a1a;}
.win {color: #00ff88; font-weight: 700;}
.loss {color: #ff3344; font-weight: 700;}
.neutral {color: #ffb000;}
.muted {color: #666;}
.header-bar {background: linear-gradient(90deg, #1a1100 0%, #000 100%); padding: 0.6rem 1rem; border-left: 3px solid #ffb000; margin-bottom: 1rem;}
.section-bar {background: #0a0a0a; padding: 0.4rem 0.8rem; border-left: 2px solid #ffb000; margin: 0.5rem 0; font-family: 'Inter', sans-serif; color: #ffb000; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.85rem;}
.tape-row {font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; padding: 0.15rem 0.5rem; border-bottom: 1px solid #0a0a0a;}
.news-row {padding: 0.4rem 0.6rem; border-bottom: 1px solid #1a1a1a;}
.news-row a {color: #d4d4d4; text-decoration: none;}
.news-row a:hover {color: #ffb000;}
.position-card {background: #0a0a0a; border: 1px solid #1a1a1a; padding: 1rem; margin-bottom: 0.8rem;}
.position-card.winning {border-left: 4px solid #00ff88;}
.position-card.losing {border-left: 4px solid #ff3344;}
.strategy-card {background: #0a0a0a; border: 1px solid #1a1a1a; padding: 0.6rem; font-family: 'JetBrains Mono', monospace;}
.tag {display: inline-block; padding: 0.1rem 0.4rem; background: #1a1100; color: #ffb000; font-size: 0.65rem; text-transform: uppercase;}
</style>
""",
    unsafe_allow_html=True,
)


# ─── Auto-refresh (10s) ─────────────────────────────────────────────────
# Using the lightweight HTML meta refresh — no extra dep needed.
st.markdown(
    "<meta http-equiv='refresh' content='10'>",
    unsafe_allow_html=True,
)


# ─── Cached data loaders ────────────────────────────────────────────────


@st.cache_data(ttl=10)
def _load_db_summary() -> dict:
    if not DB_PATH.exists():
        return {}
    with get_conn(readonly=True) as conn:
        out = {}
        out["trades_total"] = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        out["trades_open"] = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status='open'"
        ).fetchone()[0]
        out["trades_won"] = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status='won'"
        ).fetchone()[0]
        out["trades_lost"] = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status='lost'"
        ).fetchone()[0]
        out["realized_total"] = conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
            "WHERE status IN ('won','lost')"
        ).fetchone()[0]
        out["realized_today"] = conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
            "WHERE substr(timestamp, 1, 10) = date('now') AND status IN ('won','lost')"
        ).fetchone()[0]
    return out


@st.cache_data(ttl=10)
def _load_open_positions() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with get_conn(readonly=True) as conn:
        return pd.read_sql_query(
            "SELECT t.id, t.timestamp, t.sector, t.strategy, t.market_ticker, "
            "  t.side, t.contracts, t.price_cents, t.stake_usd, t.edge, "
            "  m.title AS market_title, m.raw_json AS market_raw "
            "FROM trades t LEFT JOIN markets m ON t.market_ticker = m.ticker "
            "WHERE t.status='open' ORDER BY t.id DESC",
            conn,
        )


@st.cache_data(ttl=10)
def _load_recent_closed(n: int = 15) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with get_conn(readonly=True) as conn:
        return pd.read_sql_query(
            "SELECT id, timestamp, strategy, market_ticker, side, "
            "  contracts, price_cents, status, pnl_usd "
            "FROM trades WHERE status IN ('won','lost') "
            "ORDER BY id DESC LIMIT ?",
            conn,
            params=(n,),
        )


@st.cache_data(ttl=10)
def _load_strategy_health() -> list[dict]:
    """Per-strategy stats from trades table."""
    if not DB_PATH.exists():
        return []
    rows = []
    with get_conn(readonly=True) as conn:
        for r in conn.execute(
            "SELECT strategy, COUNT(*) AS n, "
            "  SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) AS w, "
            "  SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) AS l, "
            "  SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS o, "
            "  COALESCE(SUM(pnl_usd), 0) AS pnl "
            "FROM trades GROUP BY strategy"
        ):
            rows.append(dict(r))
    return rows


@st.cache_data(ttl=10)
def _live_prices() -> dict:
    return fetch_crypto_prices()


@st.cache_data(ttl=30)
def _crypto_history_btc() -> list[tuple[int, float]]:
    return fetch_crypto_history("bitcoin", minutes=30)


@st.cache_data(ttl=30)
def _crypto_history_eth() -> list[tuple[int, float]]:
    return fetch_crypto_history("ethereum", minutes=30)


@st.cache_data(ttl=20)
def _kalshi_tape() -> list:
    return fetch_kalshi_live_trades(limit=30)


@st.cache_data(ttl=120)
def _kalshi_trending() -> list:
    return fetch_kalshi_trending_events(limit=15)


@st.cache_data(ttl=60)
def _kalshi_top_volume() -> list:
    return fetch_kalshi_top_markets(limit=12)


@st.cache_data(ttl=120)
def _crypto_news() -> list:
    return fetch_crypto_news(per_source_limit=5)


# ─── Layout ─────────────────────────────────────────────────────────────


def _strike_from_market_raw(raw_json: str) -> tuple[float | None, str]:
    """Best-effort extract of the strike price and a human-readable description."""
    if not raw_json:
        return (None, "")
    try:
        d = json.loads(raw_json)
    except Exception:
        return (None, "")
    # Different series structure these differently:
    # - KXBTC15M: yes_sub_title = "Target Price: $78,357.85"
    # - KXBTCD: floor_strike + cap_strike, sub_title = "$75,500 or above"
    floor = d.get("floor_strike")
    if floor is not None:
        try:
            return (float(floor), d.get("yes_sub_title") or "")
        except (TypeError, ValueError):
            pass
    sub = d.get("yes_sub_title") or ""
    # Parse "Target Price: $78,357.85" or "Price to beat: $2,039.06"
    import re
    m = re.search(r"\$([\d,]+\.\d+)", sub)
    if m:
        try:
            return (float(m.group(1).replace(",", "")), sub)
        except ValueError:
            pass
    return (None, sub)


def _coin_id_from_ticker(ticker: str) -> str | None:
    if "BTC" in ticker.upper():
        return "bitcoin"
    if "ETH" in ticker.upper():
        return "ethereum"
    return None


def _is_winning(side: str, current_price: float, strike: float) -> bool | None:
    """For 'BTC > strike' style markets:
      YES bet wins if current >= strike
      NO bet wins if current < strike"""
    if current_price <= 0 or strike <= 0:
        return None
    above = current_price >= strike
    return above if side.lower() == "yes" else (not above)


def _header():
    summary = _load_db_summary()
    cap = STARTING_CAPITAL_USD + (summary.get("realized_total", 0) or 0)
    today = summary.get("realized_today", 0) or 0
    today_pct = (today / STARTING_CAPITAL_USD * 100) if STARTING_CAPITAL_USD else 0
    now = time.strftime("%H:%M:%S")
    st.markdown(
        f"<div class='header-bar'>"
        f"<span style='color:#ffb000;font-family:Inter;font-weight:700;letter-spacing:0.1em;font-size:1.1rem;'>"
        f"OMNIALPHA TERMINAL</span>"
        f"<span class='muted'> · </span>"
        f"<span class='tag'>{'PAPER' if PAPER_MODE else 'LIVE'}</span>"
        f"<span class='muted' style='float:right;font-family:JetBrains Mono;'>{now} ET</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital", f"${cap:,.2f}")
    c2.metric("Today P&L", f"${today:+,.2f}", f"{today_pct:+.2f}%")
    c3.metric("Open / Closed", f"{summary.get('trades_open', 0)} / {summary.get('trades_won', 0) + summary.get('trades_lost', 0)}")
    closed = (summary.get("trades_won", 0) or 0) + (summary.get("trades_lost", 0) or 0)
    wr = (summary.get("trades_won", 0) / closed * 100) if closed else 0
    c4.metric("Win Rate", f"{wr:.1f}%" if closed else "—")


def _crypto_ticker():
    st.markdown(
        "<div class='section-bar'>Live Crypto Prices · CoinGecko</div>",
        unsafe_allow_html=True,
    )
    prices = _live_prices()
    if not prices:
        st.markdown("<span class='muted'>price feed unavailable</span>", unsafe_allow_html=True)
        return
    c1, c2 = st.columns(2)
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    btc_price = btc.get("usd", 0)
    btc_chg = btc.get("usd_24h_change", 0) or 0
    eth_price = eth.get("usd", 0)
    eth_chg = eth.get("usd_24h_change", 0) or 0
    c1.metric("BTC", f"${btc_price:,.2f}", f"{btc_chg:+.2f}% (24h)")
    c2.metric("ETH", f"${eth_price:,.2f}", f"{eth_chg:+.2f}% (24h)")


def _open_positions_panel():
    df = _load_open_positions()
    st.markdown(
        f"<div class='section-bar'>Your Open Positions · {len(df)} active</div>",
        unsafe_allow_html=True,
    )
    if df.empty:
        st.markdown(
            "<div class='muted' style='padding:1rem;font-family:JetBrains Mono;'>"
            "No open positions. Bot is selective — only enters when YES price is in "
            "20-30¢ NO band or 75-85¢ YES band, in last 3 min of market life.</div>",
            unsafe_allow_html=True,
        )
        return
    prices = _live_prices()
    btc_price = (prices.get("bitcoin") or {}).get("usd", 0)
    eth_price = (prices.get("ethereum") or {}).get("usd", 0)
    for _, row in df.iterrows():
        strike, sub = _strike_from_market_raw(row["market_raw"] or "")
        coin = _coin_id_from_ticker(row["market_ticker"])
        current = btc_price if coin == "bitcoin" else (eth_price if coin == "ethereum" else 0)
        winning = _is_winning(row["side"], current, strike or 0)

        css_class = "winning" if winning else ("losing" if winning is False else "")
        status_html = (
            "<span class='win'>✓ WINNING</span>" if winning
            else "<span class='loss'>✗ LOSING</span>" if winning is False
            else "<span class='muted'>?</span>"
        )

        # Build the strike-vs-price mini chart
        price_history = (
            _crypto_history_btc() if coin == "bitcoin"
            else _crypto_history_eth() if coin == "ethereum"
            else []
        )

        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(
                f"<div class='position-card {css_class}'>"
                f"<div style='font-family:JetBrains Mono;font-size:0.9rem;'>"
                f"<span class='neutral'>#{row['id']}</span> · "
                f"<span class='neutral'>{row['market_ticker']}</span> · "
                f"<span style='color:{'#00ff88' if row['side'].lower()=='yes' else '#ff3344'};'>"
                f"{row['side'].upper()}</span> @ {row['price_cents']}¢ · "
                f"stake ${row['stake_usd']:.2f} · {row['strategy']}"
                f"</div>"
                f"<div class='muted' style='font-size:0.85rem;'>{sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if price_history and strike:
                # Plotly mini chart with strike line
                import plotly.graph_objects as go
                xs = [pd.to_datetime(t, unit="ms") for t, _ in price_history]
                ys = [p for _, p in price_history]
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines",
                    line=dict(color="#ffb000", width=1.5),
                    name=coin or "price",
                    hovertemplate="%{y:$,.2f}<extra></extra>",
                ))
                fig.add_hline(
                    y=strike,
                    line_dash="dash",
                    line_color="#ff3344" if winning is False else "#00ff88",
                    annotation_text=f"strike ${strike:,.0f}",
                    annotation_position="top right",
                    annotation_font_color="#888",
                )
                if current > 0:
                    fig.add_hline(
                        y=current,
                        line_dash="dot",
                        line_color="#ffb000",
                        annotation_text=f"now ${current:,.0f}",
                        annotation_position="bottom right",
                        annotation_font_color="#ffb000",
                    )
                fig.update_layout(
                    height=160,
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor="#000",
                    plot_bgcolor="#0a0a0a",
                    showlegend=False,
                    xaxis=dict(showgrid=False, color="#666"),
                    yaxis=dict(showgrid=True, gridcolor="#1a1a1a", color="#666"),
                )
                st.plotly_chart(fig, use_container_width=True)
        with col_b:
            need = "above" if row["side"].lower() == "yes" else "below"
            st.markdown(
                f"<div style='padding-top:1rem;'>"
                f"{status_html}<br/>"
                f"<span class='muted' style='font-size:0.7rem;'>need {coin or 'price'} {need} strike</span><br/>"
                f"<span style='font-family:JetBrains Mono;'>${current:,.2f}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _strategy_health_panel():
    st.markdown("<div class='section-bar'>Strategy Health</div>", unsafe_allow_html=True)
    rows = _load_strategy_health()
    if not rows:
        st.markdown("<span class='muted'>No strategies have run yet.</span>", unsafe_allow_html=True)
        return
    cols = st.columns(min(len(rows), 4))
    for i, r in enumerate(rows):
        with cols[i % len(cols)]:
            wr = (r["w"] / max(r["w"] + r["l"], 1) * 100) if (r["w"] + r["l"]) else 0
            color = "#00ff88" if r["pnl"] > 0 else "#ff3344" if r["pnl"] < 0 else "#ffb000"
            st.markdown(
                f"<div class='strategy-card'>"
                f"<div style='font-size:0.75rem;color:#ffb000;'>{r['strategy']}</div>"
                f"<div style='font-size:1.1rem;color:{color};margin-top:0.3rem;'>"
                f"${r['pnl']:+,.2f}</div>"
                f"<div class='muted' style='font-size:0.75rem;margin-top:0.2rem;'>"
                f"{r['w']}W/{r['l']}L · open {r['o'] or 0} · WR {wr:.0f}%</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _kalshi_tape_panel():
    st.markdown(
        "<div class='section-bar'>Kalshi Live Tape · Every fill across the platform</div>",
        unsafe_allow_html=True,
    )
    trades = _kalshi_tape()
    if not trades:
        st.markdown("<span class='muted'>tape unavailable</span>", unsafe_allow_html=True)
        return
    rows_html = []
    for t in trades[:25]:
        side_color = "#00ff88" if t.side == "yes" else "#ff3344"
        rows_html.append(
            f"<div class='tape-row'>"
            f"<span class='muted'>{t.time_str}</span> "
            f"<span style='color:#ffb000;'>{t.ticker[:30]:<30}</span> "
            f"<span style='color:{side_color};'>{t.side.upper():<3}</span> "
            f"<span>${t.yes_price_dollars:.4f}</span> "
            f"<span class='muted'>x{t.count:.1f}</span>"
            f"</div>"
        )
    st.markdown(
        f"<div style='max-height:340px;overflow-y:auto;border:1px solid #1a1a1a;background:#050505;'>"
        + "".join(rows_html) +
        "</div>",
        unsafe_allow_html=True,
    )


def _kalshi_trending_panel():
    st.markdown(
        "<div class='section-bar'>Kalshi Trending Events</div>",
        unsafe_allow_html=True,
    )
    events = _kalshi_trending()
    if not events:
        st.markdown("<span class='muted'>—</span>", unsafe_allow_html=True)
        return
    rows = []
    for e in events[:12]:
        rows.append(
            f"<div class='news-row'>"
            f"<span class='tag'>{e.category[:12]}</span> "
            f"<span style='color:#d4d4d4;'>{e.title[:80]}</span>"
            f"</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def _kalshi_top_volume_panel():
    st.markdown(
        "<div class='section-bar'>Top Volume Today (Kalshi)</div>",
        unsafe_allow_html=True,
    )
    markets = _kalshi_top_volume()
    if not markets:
        st.markdown("<span class='muted'>—</span>", unsafe_allow_html=True)
        return
    rows = []
    for m in markets[:10]:
        rows.append(
            f"<div class='tape-row'>"
            f"<span class='muted'>${m.volume_24h:>10,.0f}</span> "
            f"<span style='color:#ffb000;'>{m.ticker[:30]:<30}</span> "
            f"<span>{m.last_price_dollars:.0%}</span>"
            f"</div>"
        )
    st.markdown(
        f"<div style='border:1px solid #1a1a1a;background:#050505;'>"
        + "".join(rows) +
        "</div>",
        unsafe_allow_html=True,
    )


def _crypto_news_panel():
    st.markdown(
        "<div class='section-bar'>Crypto News · CoinDesk · The Block · Decrypt · Cointelegraph</div>",
        unsafe_allow_html=True,
    )
    items = _crypto_news()
    if not items:
        st.markdown("<span class='muted'>news feed unavailable</span>", unsafe_allow_html=True)
        return
    rows = []
    for n in items[:12]:
        rows.append(
            f"<div class='news-row'>"
            f"<span class='muted'>{n.short_time}</span> "
            f"<span class='tag'>{n.source}</span> "
            f"<a href='{n.url}' target='_blank'>{n.title[:120]}</a>"
            f"</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def _closed_trades_panel():
    df = _load_recent_closed(15)
    st.markdown(
        f"<div class='section-bar'>Closed Trades · {len(df)}</div>",
        unsafe_allow_html=True,
    )
    if df.empty:
        st.markdown("<span class='muted'>no closed trades yet</span>", unsafe_allow_html=True)
        return
    # Format with HTML so we can color win/loss
    rows = []
    for _, r in df.iterrows():
        ts = r["timestamp"][11:19] if r["timestamp"] else ""
        pnl = r["pnl_usd"] or 0
        won = r["status"] == "won"
        color = "#00ff88" if won else "#ff3344"
        icon = "✓" if won else "✗"
        rows.append(
            f"<div class='tape-row'>"
            f"<span style='color:{color};'>{icon}</span> "
            f"<span class='muted'>#{r['id']:<3} {ts}</span> "
            f"<span style='color:{('#00ff88' if r['side']=='yes' else '#ff3344')};'>{r['side'].upper():<3}</span> "
            f"<span style='color:#ffb000;'>{r['market_ticker'][:25]:<25}</span> "
            f"<span class='muted'>@{r['price_cents']:>3}¢</span> "
            f"<span class='muted'>{r['contracts']}x</span> "
            f"<span style='color:{color};'>${pnl:+,.2f}</span>"
            f"</div>"
        )
    st.markdown(
        f"<div style='border:1px solid #1a1a1a;background:#050505;'>"
        + "".join(rows) +
        "</div>",
        unsafe_allow_html=True,
    )


# ─── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    _header()
    _crypto_ticker()

    _open_positions_panel()
    _strategy_health_panel()

    # Two-column block: live tape | trending events + top volume
    col_l, col_r = st.columns([2, 1])
    with col_l:
        _kalshi_tape_panel()
    with col_r:
        _kalshi_top_volume_panel()
        _kalshi_trending_panel()

    _crypto_news_panel()
    _closed_trades_panel()


if __name__ == "__main__":
    main()
