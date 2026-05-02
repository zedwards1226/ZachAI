"""OmniAlpha CLI — operational verbs.

    python cli.py health             — check Kalshi public endpoint + DB connectivity
    python cli.py init-db            — create empty SQLite schema
    python cli.py pull-historical    — bulk-pull settled markets into DB
    python cli.py status             — current DB stats (counts, sectors, recent activity)

NO live-trading commands here yet. That's a separate session.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DB_PATH, PAPER_MODE
from data_layer.database import get_conn, init_db


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def cmd_health(args: argparse.Namespace) -> int:
    """Hit Kalshi's /historical/cutoff (no auth needed) + open the DB."""
    from bots.kalshi_public import get_cutoff
    print(f"PAPER_MODE: {PAPER_MODE}")
    print(f"DB_PATH:    {DB_PATH}")
    print(f"DB exists:  {DB_PATH.exists()}")
    try:
        cutoff = get_cutoff()
        print(f"Kalshi /historical/cutoff: {cutoff}")
        print("[ok] public endpoint reachable")
    except Exception as e:
        print(f"[FAIL] public endpoint failed: {e}")
        return 2
    if DB_PATH.exists():
        try:
            with get_conn(readonly=True) as conn:
                n = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
                print(f"[ok] DB readable, {n} markets stored")
        except Exception as e:
            print(f"[FAIL] DB read failed: {e}")
            return 2
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    print(f"Initializing schema at {DB_PATH}")
    init_db()
    print("[ok] schema ready")
    return 0


def cmd_pull_historical(args: argparse.Namespace) -> int:
    from data_layer.historical_pull import pull_historical_markets
    print(f"Pulling historical markets: series={args.series} days={args.days}")
    result = pull_historical_markets(
        series_ticker=args.series,
        days=args.days,
        max_pages=args.max_pages,
    )
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if not DB_PATH.exists():
        print("DB not initialized. Run: python cli.py init-db")
        return 1
    with get_conn(readonly=True) as conn:
        n_markets = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
        n_finalized = conn.execute(
            "SELECT COUNT(*) FROM markets WHERE status='finalized'"
        ).fetchone()[0]
        n_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        n_open = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
        print(f"PAPER_MODE:        {PAPER_MODE}")
        print(f"Markets seen:      {n_markets:,}")
        print(f"Settled markets:   {n_finalized:,}")
        print(f"Trades total:      {n_trades:,}")
        print(f"Trades open:       {n_open:,}")
        print()
        print("By sector:")
        for row in conn.execute(
            "SELECT sector, COUNT(*) n FROM markets GROUP BY sector ORDER BY n DESC"
        ):
            print(f"  {row['sector']:12s}  {row['n']:,}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="omnialpha")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(func=cmd_health)
    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    sub.add_parser("status").set_defaults(func=cmd_status)

    p_pull = sub.add_parser("pull-historical", help="bulk-pull settled markets")
    p_pull.add_argument("--series", help="series ticker, e.g. KXBTC15M")
    p_pull.add_argument("--days", type=int, default=7,
                        help="number of days back from current cutoff (default 7)")
    p_pull.add_argument("--max-pages", type=int, default=None,
                        help="safety cap; None = pull everything in window")
    p_pull.set_defaults(func=cmd_pull_historical)

    args = parser.parse_args()
    _setup_logging(args.log_level)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
