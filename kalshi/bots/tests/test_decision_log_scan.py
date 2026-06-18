"""Tests for log_scan_actions — the shared decision-log writer used by BOTH
the manual /api/scan endpoint and the automatic scheduler scan job.

Regression guard for the 2026-06-10 gap: the automatic scan path placed
trades but never wrote decision_log, because logging only lived inline in
the manual endpoint. log_scan_actions is the single source both call.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database


def _temp_db(tmp_path, monkeypatch):
    db = tmp_path / "wa_test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db))
    database.init_db()


def test_logs_trades_and_blocks_skips_duplicates(tmp_path, monkeypatch):
    _temp_db(tmp_path, monkeypatch)
    actions = [
        {"action": "traded", "city": "NYC", "side": "NO", "contracts": 5,
         "price": 45, "edge": 0.25, "stake": 2.25},
        {"action": "blocked", "city": "ATL",
         "reasons": ["Market more bullish than model"], "edge": -0.1},
        {"action": "skipped_duplicate", "city": "PHX", "reason": "open position"},
    ]
    n = database.log_scan_actions(actions)
    rows = database.get_decision_log(limit=50)
    types = sorted(r["type"] for r in rows)

    assert n == 2, f"expected 2 logged (traded+blocked), got {n}"
    assert "traded" in types
    assert "blocked" in types
    assert "skipped_duplicate" not in types, "duplicate-skip noise must NOT be logged"

    traded = next(r for r in rows if r["type"] == "traded")
    assert traded["city"] == "NYC"
    assert traded["side"] == "NO"
    assert traded["price_cents"] == 45
    assert traded["stake_usd"] == 2.25


def test_blocked_message_joins_reasons(tmp_path, monkeypatch):
    _temp_db(tmp_path, monkeypatch)
    database.log_scan_actions([
        {"action": "blocked", "city": "MIN", "reasons": ["edge too small", "strike blocked"]},
    ])
    row = database.get_decision_log(limit=5)[0]
    assert "edge too small; strike blocked" in row["message"]


def test_empty_or_nonlist_is_safe(tmp_path, monkeypatch):
    _temp_db(tmp_path, monkeypatch)
    assert database.log_scan_actions([]) == 0
    assert database.log_scan_actions(None) == 0
    assert database.log_scan_actions("nonsense") == 0
