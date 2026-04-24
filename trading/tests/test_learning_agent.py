"""Tests for agents.learning_agent — insufficient data heartbeat, threshold
proposals, cooldown enforcement, idempotency guard.

Each test uses a fresh in-memory-style journal.db in tmp_path and mocks
`telegram.send` so no network traffic leaves the test.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def ephemeral_journal(monkeypatch, tmp_path):
    """Redirect journal.db + state/ paths to tmp_path; init schema."""
    db_path = tmp_path / "journal.db"
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    import config
    monkeypatch.setattr(config, "JOURNAL_DB", db_path)
    monkeypatch.setattr(config, "STATE_DIR", state_dir)

    from agents import journal, config_loader, learning_agent
    monkeypatch.setattr(journal, "JOURNAL_DB", db_path)
    monkeypatch.setattr(config_loader, "_STATE_DIR", state_dir)
    monkeypatch.setattr(config_loader, "_CONFIG_PATH",
                        state_dir / "learned_config.json")
    monkeypatch.setattr(config_loader, "_META_PATH",
                        state_dir / "learned_config.meta.json")

    # No-op Telegram
    fake_telegram = MagicMock()
    fake_telegram.send = AsyncMock(return_value=True)
    monkeypatch.setattr(learning_agent, "telegram", fake_telegram)

    journal.init_db()
    return {"db": db_path, "state_dir": state_dir, "journal": journal,
            "learning_agent": learning_agent, "telegram": fake_telegram}


def _insert_trade(db_path: Path, *, date: str, outcome: str, score: int,
                  direction: str = "LONG", rvol: float = 1.6,
                  entry: float = 27000.0, exit_price: float = 27010.0) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT INTO trades (date, time, direction, score, breakdown,
             entry, stop, target_1, target_2, exit_price, outcome,
             rr, pnl, pnl_after_slippage, size, orb_high, orb_low,
             orb_candle_direction, was_second_break, vix_at_entry,
             rvol_at_entry, setup_type, created_at)
           VALUES (?, '09:45:00', ?, ?, '{}', ?, 26990, 27010, 27030, ?, ?,
                   1.0, 10, 6, 'FULL', 27050, 26980, 'BULLISH',
                   0, 18.0, ?, 'ORB', ?)""",
        (date, direction, score, entry, exit_price, outcome, rvol,
         f"{date}T09:45:00"),
    )
    conn.commit()
    conn.close()


def test_insufficient_data_fires_heartbeat(ephemeral_journal):
    """<20 trades → no proposals, heartbeat row + Telegram heartbeat only."""
    la = ephemeral_journal["learning_agent"]
    # Insert 5 trades — well below the 20 threshold
    today = datetime.now(pytz.timezone("America/New_York"))
    for i in range(5):
        date = (today - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        _insert_trade(ephemeral_journal["db"], date=date, outcome="WIN", score=9)

    result = asyncio.run(la.run(dry_run=False))

    assert result["status"] == "ok"
    assert result["proposals"] == []
    assert result["heartbeat"] and "5/20" in result["heartbeat"]
    # Exactly one heartbeat row, no proposals
    j = ephemeral_journal["journal"]
    with j.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_journal"
        ).fetchall()]
    types = [r["entry_type"] for r in rows]
    assert types == ["heartbeat"]
    # Telegram heartbeat was sent
    ephemeral_journal["telegram"].send.assert_awaited_once()


def test_threshold_proposal_when_half_band_losing(ephemeral_journal):
    """Half-size band (score 5-7) with poor WR → propose raising SCORE_HALF_SIZE."""
    la = ephemeral_journal["learning_agent"]
    today = datetime.now(pytz.timezone("America/New_York"))

    # 12 half-size trades at 25% WR (3W / 9L) → well below 40% floor
    # Plus 15 full-size trades at 60% WR (healthy) to bring total ≥20
    for i in range(12):
        date = (today - timedelta(days=(i % 20) + 1)).strftime("%Y-%m-%d")
        outcome = "WIN" if i < 3 else "LOSS"
        _insert_trade(ephemeral_journal["db"], date=date, outcome=outcome,
                      score=6)
    for i in range(15):
        date = (today - timedelta(days=(i % 20) + 1)).strftime("%Y-%m-%d")
        outcome = "WIN" if i < 9 else "LOSS"
        _insert_trade(ephemeral_journal["db"], date=date, outcome=outcome,
                      score=9)

    result = asyncio.run(la.run(dry_run=False))

    assert result["status"] == "ok"
    knobs = [p["knob"] for p in result["proposals"]]
    assert "SCORE_HALF_SIZE" in knobs, f"expected SCORE_HALF_SIZE proposal, got {knobs}"

    half_proposal = next(p for p in result["proposals"]
                         if p["knob"] == "SCORE_HALF_SIZE")
    assert half_proposal["current"] == 5
    assert half_proposal["proposed"] == 6  # +1 step
    assert half_proposal["sample_size"] >= 12

    # Proposal row + digest row written
    j = ephemeral_journal["journal"]
    with j.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_journal WHERE entry_type='proposal'"
        ).fetchall()]
    assert len(rows) >= 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["knob"] == "SCORE_HALF_SIZE"


def test_cooldown_blocks_recent_knob_change(ephemeral_journal):
    """Knob changed 3 days ago → new proposal for it is suppressed."""
    la = ephemeral_journal["learning_agent"]
    j = ephemeral_journal["journal"]
    today = datetime.now(pytz.timezone("America/New_York"))

    # Seed the same losing-half-band scenario as above
    for i in range(12):
        date = (today - timedelta(days=(i % 20) + 1)).strftime("%Y-%m-%d")
        outcome = "WIN" if i < 3 else "LOSS"
        _insert_trade(ephemeral_journal["db"], date=date, outcome=outcome,
                      score=6)
    for i in range(15):
        date = (today - timedelta(days=(i % 20) + 1)).strftime("%Y-%m-%d")
        outcome = "WIN" if i < 9 else "LOSS"
        _insert_trade(ephemeral_journal["db"], date=date, outcome=outcome,
                      score=9)

    # Manually insert an "approved" proposal for SCORE_HALF_SIZE 3 days ago
    three_days_ago = (today - timedelta(days=3)).isoformat()
    with j.get_conn() as conn:
        conn.execute(
            """INSERT INTO agent_journal
               (date, created_at, entry_type, subject, knob,
                current_value, proposed_value, reasoning, source, status, applied_at)
               VALUES (?, ?, 'proposal', 'SCORE_HALF_SIZE', 'SCORE_HALF_SIZE',
                       5, 6, 'prior', 'agent', 'approved', ?)""",
            (three_days_ago[:10], three_days_ago, three_days_ago),
        )

    result = asyncio.run(la.run(dry_run=False))

    knobs = [p["knob"] for p in result["proposals"]]
    assert "SCORE_HALF_SIZE" not in knobs, (
        f"SCORE_HALF_SIZE must be suppressed by cooldown, got proposals: {knobs}"
    )


def test_idempotency_skips_second_run_same_day(ephemeral_journal):
    """Running twice in one day → second run is a no-op."""
    la = ephemeral_journal["learning_agent"]
    # Enough trades to trigger the normal path
    today = datetime.now(pytz.timezone("America/New_York"))
    for i in range(25):
        date = (today - timedelta(days=(i % 20) + 1)).strftime("%Y-%m-%d")
        _insert_trade(ephemeral_journal["db"], date=date,
                      outcome="WIN" if i % 2 == 0 else "LOSS", score=9)

    first = asyncio.run(la.run(dry_run=False))
    second = asyncio.run(la.run(dry_run=False))

    assert first["status"] == "ok"
    assert second["status"] == "already_ran"
    assert second["proposals"] == []


def test_manual_edit_detected_and_logged(ephemeral_journal):
    """Drift in learned_config.json → row with source='manual' + reasoning diff."""
    la = ephemeral_journal["learning_agent"]
    from agents import config_loader

    # Agent sets a value; meta records it
    config_loader.apply_proposal({"SCORE_FULL_SIZE": 9}, source="agent")

    # Zach edits manually
    cfg_path = ephemeral_journal["state_dir"] / "learned_config.json"
    cfg_path.write_text(json.dumps({"SCORE_FULL_SIZE": 10}))

    # Seed enough trades so run proceeds past sample check
    today = datetime.now(pytz.timezone("America/New_York"))
    for i in range(25):
        date = (today - timedelta(days=(i % 20) + 1)).strftime("%Y-%m-%d")
        _insert_trade(ephemeral_journal["db"], date=date,
                      outcome="WIN" if i % 2 == 0 else "LOSS", score=9)

    asyncio.run(la.run(dry_run=False))

    j = ephemeral_journal["journal"]
    with j.get_conn() as conn:
        manual_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_journal WHERE entry_type='manual_edit'"
        ).fetchall()]
    assert len(manual_rows) == 1
    assert manual_rows[0]["source"] == "manual"
    assert "9" in manual_rows[0]["reasoning"]
    assert "10" in manual_rows[0]["reasoning"]
