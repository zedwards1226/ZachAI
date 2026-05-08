"""ICTBot CLI — quick status / health / journal queries.

Usage:
    python cli.py status
    python cli.py health
    python cli.py last-trade
    python cli.py today-setups
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

import pytz

from config import TIMEZONE, PAPER_MODE, SCAN_ONLY, ICT_SYMBOL
from data_layer.database import (
    init_db, fetch_recent_trades, fetch_today_setups, equity_curve,
    fetch_open_position,
)
from services.state_manager import (
    read_arm_status, can_trade_now, pnl_today, pnl_week, trades_today,
    consecutive_losses, is_cross_bot_halted, orb_arm_status,
)
from services.ict_tv_client import health_check as cdp_health


ET = pytz.timezone(TIMEZONE)


def cmd_status() -> int:
    init_db()
    arm = read_arm_status()
    halted, halt_reason = is_cross_bot_halted()
    can, reason = can_trade_now()
    open_pos = fetch_open_position(ICT_SYMBOL)
    print(json.dumps({
        "now_et": datetime.now(ET).isoformat(),
        "symbol": ICT_SYMBOL,
        "paper_mode": PAPER_MODE,
        "scan_only": SCAN_ONLY,
        "arm": arm,
        "cross_bot_halted": halted,
        "halt_reason": halt_reason,
        "trades_today": trades_today(),
        "pnl_today": pnl_today(),
        "pnl_week": pnl_week(),
        "consecutive_losses": consecutive_losses(),
        "can_trade": can,
        "can_trade_reason": reason,
        "open_position": open_pos,
        "orb_arm": orb_arm_status(),
    }, indent=2, default=str))
    return 0


def cmd_health() -> int:
    init_db()
    ok, msg = cdp_health()
    print(json.dumps({
        "cdp_9223": {"ok": ok, "message": msg},
        "paper_mode": PAPER_MODE,
        "scan_only": SCAN_ONLY,
    }, indent=2))
    return 0 if ok and PAPER_MODE else 1


def cmd_last_trade() -> int:
    init_db()
    trades = fetch_recent_trades(1)
    if not trades:
        print("no trades yet")
        return 0
    print(json.dumps(trades[0], indent=2, default=str))
    return 0


def cmd_today_setups() -> int:
    init_db()
    today = datetime.now(ET).strftime("%Y-%m-%d")
    setups = fetch_today_setups(today)
    print(json.dumps({"date": today, "setups": setups}, indent=2, default=str))
    return 0


COMMANDS = {
    "status": cmd_status,
    "health": cmd_health,
    "last-trade": cmd_last_trade,
    "today-setups": cmd_today_setups,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: python cli.py [{' | '.join(COMMANDS.keys())}]")
        return 2
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
