"""OmniAlpha Streamlit dashboard.

Read-only view of:
  - Market universe (count by sector, recent additions, settled outcomes)
  - Trade history (paper + live, filtered by sector + strategy)
  - P&L curve from pnl_snapshots
  - LLM cost ledger (per bot/strategy/day)
  - Sector state (enabled, paused, cooldowns)

NEVER writes to the DB. The bot owns writes; the dashboard is dumb.
Auto-refresh every 10s.

Launch:
    cd C:\\ZachAI\\omnialpha
    streamlit run dashboard/app.py --server.port 8502
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `import config`, `import data_layer.*` work when run from any CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from config import (
    DB_PATH,
    PAPER_MODE,
    STARTING_CAPITAL_USD,
    DAILY_MAX_LOSS_USD,
    PER_TRADE_MAX_RISK_USD,
)
from data_layer.database import get_conn

st.set_page_config(
    page_title="OmniAlpha",
    page_icon="🎯",
    layout="wide",
)


@st.cache_data(ttl=10)
def _load_summary() -> dict:
    """Read top-level counts from DB. Returns empty dict if DB doesn't exist yet."""
    if not DB_PATH.exists():
        return {}
    with get_conn(readonly=True) as conn:
        out: dict = {}
        out["markets_total"] = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
        out["markets_finalized"] = conn.execute(
            "SELECT COUNT(*) FROM markets WHERE status='finalized'"
        ).fetchone()[0]
        out["trades_total"] = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        out["trades_open"] = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status='open'"
        ).fetchone()[0]
        out["llm_calls_total"] = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        out["llm_cost_total"] = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls"
        ).fetchone()[0]
        # sectors seen
        out["sectors"] = [
            (row["sector"], row["n"])
            for row in conn.execute(
                "SELECT sector, COUNT(*) AS n FROM markets GROUP BY sector ORDER BY n DESC"
            )
        ]
    return out


@st.cache_data(ttl=10)
def _load_trades() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with get_conn(readonly=True) as conn:
        try:
            return pd.read_sql_query(
                "SELECT * FROM trades ORDER BY id DESC LIMIT 100",
                conn,
            )
        except Exception:
            return pd.DataFrame()


@st.cache_data(ttl=10)
def _load_pnl_curve() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with get_conn(readonly=True) as conn:
        try:
            return pd.read_sql_query(
                "SELECT timestamp, capital_usd, open_risk_usd, realized_today, realized_total "
                "FROM pnl_snapshots ORDER BY id DESC LIMIT 5000",
                conn,
            )
        except Exception:
            return pd.DataFrame()


@st.cache_data(ttl=10)
def _load_recent_markets(n: int = 50) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with get_conn(readonly=True) as conn:
        try:
            return pd.read_sql_query(
                "SELECT ticker, sector, title, status, result, close_time, "
                "settlement_value_dollars, volume_fp "
                "FROM markets ORDER BY last_updated_at DESC LIMIT ?",
                conn,
                params=(n,),
            )
        except Exception:
            return pd.DataFrame()


def _header() -> None:
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    with col1:
        st.title("🎯 OmniAlpha")
        st.caption("Multi-sector 24/7 Kalshi prediction-market bot")
    with col2:
        st.metric(
            "Mode",
            "📝 PAPER" if PAPER_MODE else "🔥 LIVE",
            help="Paper-mode hard stop. Going live is one of Zach's 3 hard stops.",
        )
    with col3:
        st.metric("Capital", f"${STARTING_CAPITAL_USD:,.0f}")
    with col4:
        st.metric("Daily loss cap", f"${DAILY_MAX_LOSS_USD:,.0f}")


def _summary_panel() -> None:
    summary = _load_summary()
    if not summary:
        st.info(
            "Database not initialized yet. Run `python cli.py pull-historical "
            "--series KXBTC15M --days 7` to populate the markets table."
        )
        return

    cols = st.columns(5)
    cols[0].metric("Markets seen", f"{summary['markets_total']:,}")
    cols[1].metric("Settled", f"{summary['markets_finalized']:,}")
    cols[2].metric("Trades total", f"{summary['trades_total']:,}")
    cols[3].metric("Open positions", f"{summary['trades_open']:,}")
    cols[4].metric("LLM cost so far", f"${summary['llm_cost_total']:,.2f}")

    st.subheader("Markets by sector")
    sectors = summary.get("sectors") or []
    if sectors:
        df = pd.DataFrame(sectors, columns=["sector", "count"])
        st.bar_chart(df.set_index("sector")["count"])
    else:
        st.caption("No markets ingested yet.")


def _trades_panel() -> None:
    st.subheader("Recent trades")
    df = _load_trades()
    if df.empty:
        st.caption("No trades yet — bot is in scaffold phase.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)


def _pnl_panel() -> None:
    st.subheader("P&L curve")
    df = _load_pnl_curve()
    if df.empty:
        st.caption("No P&L snapshots yet.")
        return
    df = df.sort_values("timestamp")
    st.line_chart(df.set_index("timestamp")[["capital_usd", "realized_total"]])


def _markets_panel() -> None:
    st.subheader("Recent market ingestions")
    df = _load_recent_markets(50)
    if df.empty:
        st.caption("Markets table is empty.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)


def main() -> None:
    _header()
    st.divider()
    _summary_panel()
    st.divider()

    tab_trades, tab_pnl, tab_markets = st.tabs(["Trades", "P&L", "Markets"])
    with tab_trades:
        _trades_panel()
    with tab_pnl:
        _pnl_panel()
    with tab_markets:
        _markets_panel()


if __name__ == "__main__":
    main()
