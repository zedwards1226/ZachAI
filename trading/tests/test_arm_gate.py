"""Tests for the 9:25 ORB arm gate.

Four behaviors verified:
  1. All 3 hard checks pass → arm_status.json written with armed=true,
     source="preflight". No Telegram alert on the happy path.
  2. One hard check fails → armed=false, blocker mentions the failing
     check, soft warnings still recorded, alert fires.
  3. combiner.poll() short-circuits when armed=false and fires
     notify_arm_blocked exactly once per day (mirrors the existing
     once-per-day _logged_daily_cap pattern).
  4. Manual override (source="manual", armed=true) lets combiner
     proceed past the arm gate.

Sync test functions calling asyncio.run() — same pattern as
test_learning_agent.py (no pytest-asyncio dependency).
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import pytz

# Allow `pytest` from trading/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import preflight  # noqa: E402
from agents import combiner   # noqa: E402
from services import state_manager  # noqa: E402

ET = pytz.timezone("America/New_York")


@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    """Redirect STATE_DIR so tests don't pollute production state files."""
    monkeypatch.setattr(state_manager, "STATE_DIR", tmp_path)
    yield tmp_path


def test_all_hard_checks_pass_arms_bot(isolated_state_dir):
    """Happy path — CDP, broker, DOM all green → armed=true, no alert."""
    with patch.object(preflight, "_check_cdp_and_symbol",
                      AsyncMock(return_value=(True, "CDP locked on CME_MINI:MNQ1!"))), \
         patch.object(preflight, "_check_paper_broker",
                      AsyncMock(return_value=(True, "Paper Trading broker connected"))), \
         patch.object(preflight, "_check_dom_ready",
                      AsyncMock(return_value=(True, "DOM ready, paper trading active"))), \
         patch.object(preflight, "_check_calendar",
                      return_value=(True, "No high-impact events today")), \
         patch.object(preflight, "_check_disk",
                      return_value=(True, "Disk OK: 200 GB free")), \
         patch.object(preflight, "_check_journal_db",
                      return_value=(True, "journal.db 0.1 MB")), \
         patch.object(preflight.telegram, "notify_arm_blocked",
                      AsyncMock(return_value=True)) as mock_alert:
        status = asyncio.run(preflight.run_arm_check())

    assert status["armed"] is True
    assert status["source"] == "preflight"
    assert status["blocker"] is None
    assert status["checks"]["cdp_symbol"]["ok"] is True
    assert status["checks"]["broker"]["ok"] is True
    assert status["checks"]["dom_paper"]["ok"] is True
    # On the happy path we do NOT page Zach — only failures alert.
    mock_alert.assert_not_called()

    # File written + readable
    on_disk = state_manager.read_state("arm_status")
    assert on_disk["armed"] is True


def test_broker_failure_blocks_arming(isolated_state_dir):
    """Broker check returns False → armed=false, blocker mentions broker,
    soft check warnings still recorded for situational awareness."""
    with patch.object(preflight, "_check_cdp_and_symbol",
                      AsyncMock(return_value=(True, "CDP OK"))), \
         patch.object(preflight, "_check_paper_broker",
                      AsyncMock(return_value=(False, "❗ Paper Trading DISCONNECTED — reconnect before open"))), \
         patch.object(preflight, "_check_dom_ready",
                      AsyncMock(return_value=(True, "DOM ready"))), \
         patch.object(preflight, "_check_calendar",
                      return_value=(True, "FOMC 2:00 PM today")), \
         patch.object(preflight, "_check_disk",
                      return_value=(False, "Low disk: 3.2 GB free on C:")), \
         patch.object(preflight, "_check_journal_db",
                      return_value=(True, "journal.db OK")), \
         patch.object(preflight.telegram, "notify_arm_blocked",
                      AsyncMock(return_value=True)) as mock_alert:
        status = asyncio.run(preflight.run_arm_check())

    assert status["armed"] is False
    assert status["checks"]["broker"]["ok"] is False
    assert "broker" in status["blocker"].lower()
    # Soft check that failed should land in warnings (not hard-block reason).
    assert status["warnings"]["disk"] == "Low disk: 3.2 GB free on C:"
    # Calendar passed so no warning row even though FOMC is today.
    assert status["warnings"]["calendar"] is None
    # Failed-arm fires exactly one Telegram.
    mock_alert.assert_awaited_once()


def test_combiner_short_circuits_when_not_armed(isolated_state_dir):
    """combiner.poll() reads arm_status.json. When armed=false:
      - returns None
      - fires notify_arm_blocked exactly once per day (subsequent polls quiet)
      - never reaches the active-orders check
    """
    today = datetime.now(ET).strftime("%Y-%m-%d")
    state_manager.write_state("arm_status", {
        "date": today,
        "armed": False,
        "source": "preflight",
        "checks": {
            "cdp_symbol": {"ok": True,  "msg": "CDP OK"},
            "broker":     {"ok": False, "msg": "Paper Trading DISCONNECTED"},
            "dom_paper":  {"ok": True,  "msg": "DOM ready"},
        },
        "warnings": {},
        "armed_at": datetime.now(ET).isoformat(),
        "blocker": "broker: Paper Trading DISCONNECTED",
    })

    # Make sure combiner thinks today is fresh.
    combiner._session_date = today
    combiner._logged_arm_block = False

    # Force combiner's view of "now" into the trading window (10:00 ET).
    fake_now = datetime.now(ET).replace(hour=10, minute=0, second=0, microsecond=0)

    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            return fake_now

    with patch.object(combiner, "datetime", _FakeDatetime), \
         patch.object(combiner, "read_state", state_manager.read_state), \
         patch.object(combiner.telegram, "notify_arm_blocked",
                      AsyncMock(return_value=True)) as mock_alert, \
         patch("services.tv_trader.get_active_orders") as mock_active, \
         patch("services.tv_trader.tv_get_positions",
               AsyncMock(return_value={"has_position": False})):

        # First poll — should block, fire alert once
        result1 = asyncio.run(combiner.poll())
        assert result1 is None
        assert mock_alert.await_count == 1
        # tv_trader's get_active_orders should NOT have been hit — short
        # circuit happens before the one-position check.
        mock_active.assert_not_called()

        # Second + third polls — still blocked, NO additional alerts
        asyncio.run(combiner.poll())
        asyncio.run(combiner.poll())
        assert mock_alert.await_count == 1


def test_manual_override_arms_bot(isolated_state_dir):
    """Jarvis writes arm_status.json with source='manual', armed=true.
    combiner.poll() picks it up on next tick — no alert, proceeds past
    the arm gate to the next guard."""
    today = datetime.now(ET).strftime("%Y-%m-%d")
    state_manager.write_state("arm_status", {
        "date": today,
        "armed": True,
        "source": "manual",
        "checks": {
            "cdp_symbol": {"ok": True, "msg": "CDP OK"},
            "broker":     {"ok": True, "msg": "Manually overridden by Zach"},
            "dom_paper":  {"ok": True, "msg": "DOM ready"},
        },
        "warnings": {},
        "armed_at": datetime.now(ET).isoformat(),
        "blocker": None,
    })

    combiner._session_date = today
    combiner._logged_arm_block = False

    fake_now = datetime.now(ET).replace(hour=10, minute=0, second=0, microsecond=0)

    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            return fake_now

    with patch.object(combiner, "datetime", _FakeDatetime), \
         patch.object(combiner, "read_state", state_manager.read_state), \
         patch.object(combiner.telegram, "notify_arm_blocked",
                      AsyncMock(return_value=True)) as mock_alert, \
         patch("services.tv_trader.get_active_orders", return_value=[]), \
         patch("services.tv_trader.tv_get_positions",
               AsyncMock(return_value={"has_position": False})), \
         patch("agents.journal.get_today_stats",
               return_value={"consecutive_losses": 0}), \
         patch("agents.journal.get_today_pnl", return_value=0.0), \
         patch("agents.journal.get_week_pnl", return_value=0.0), \
         patch("agents.journal.get_today_filled_count", return_value=0), \
         patch("services.tv_trader.get_client",
               AsyncMock(side_effect=RuntimeError("stop here — past the arm gate"))):

        # The arm gate should let us through; we then hit the get_client
        # stub. Catching the RuntimeError proves the arm gate did NOT
        # short-circuit.
        with pytest.raises(RuntimeError, match="past the arm gate"):
            asyncio.run(combiner.poll())

        mock_alert.assert_not_called()
