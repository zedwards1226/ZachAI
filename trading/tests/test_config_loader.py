"""Tests for agents.config_loader — override load, bounds, manual-edit detection.

Every test uses a monkeypatched STATE_DIR pointing at tmp_path so the
real `trading/state/` tree is never touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import config_loader  # noqa: E402


@pytest.fixture
def tmp_state(monkeypatch, tmp_path):
    """Point config_loader paths at a clean tmp directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(config_loader, "_STATE_DIR", state_dir)
    monkeypatch.setattr(config_loader, "_CONFIG_PATH", state_dir / "learned_config.json")
    monkeypatch.setattr(config_loader, "_META_PATH", state_dir / "learned_config.meta.json")
    return state_dir


def test_load_overrides_missing_file_returns_empty(tmp_state):
    assert config_loader.load_overrides() == {}


def test_load_overrides_valid_keys(tmp_state):
    (tmp_state / "learned_config.json").write_text(json.dumps({
        "SCORE_FULL_SIZE": 9,
        "SCORE_HALF_SIZE": 6,
        "RVOL_THRESHOLD": 1.7,
    }))
    overrides = config_loader.load_overrides()
    assert overrides == {
        "SCORE_FULL_SIZE": 9,
        "SCORE_HALF_SIZE": 6,
        "RVOL_THRESHOLD": 1.7,
    }


def test_load_overrides_drops_unknown_keys(tmp_state):
    (tmp_state / "learned_config.json").write_text(json.dumps({
        "SCORE_FULL_SIZE": 9,
        "NOT_A_KNOB": 42,
        "VIX_HARD_BLOCK": 25,  # not learnable — must be ignored
    }))
    overrides = config_loader.load_overrides()
    assert "NOT_A_KNOB" not in overrides
    assert "VIX_HARD_BLOCK" not in overrides
    assert overrides == {"SCORE_FULL_SIZE": 9}


def test_load_overrides_drops_out_of_bounds(tmp_state):
    (tmp_state / "learned_config.json").write_text(json.dumps({
        "SCORE_FULL_SIZE": 99,      # above max=12
        "SCORE_HALF_SIZE": -5,      # below min=3
        "RVOL_THRESHOLD": 5.0,      # above max=2.0
    }))
    assert config_loader.load_overrides() == {}


def test_load_overrides_corrupt_json_returns_empty(tmp_state):
    (tmp_state / "learned_config.json").write_text("not json {{{")
    assert config_loader.load_overrides() == {}


def test_apply_proposal_writes_config_and_meta(tmp_state):
    config_loader.apply_proposal({"SCORE_HALF_SIZE": 6}, source="agent")
    cfg = json.loads((tmp_state / "learned_config.json").read_text())
    meta = json.loads((tmp_state / "learned_config.meta.json").read_text())
    assert cfg == {"SCORE_HALF_SIZE": 6}
    assert meta["last_source"] == "agent"
    assert meta["checksum"]
    assert meta["snapshot"] == {"SCORE_HALF_SIZE": 6}


def test_apply_proposal_rejects_unknown_knob(tmp_state):
    with pytest.raises(ValueError, match="not a learnable knob"):
        config_loader.apply_proposal({"VIX_HARD_BLOCK": 25})


def test_apply_proposal_rejects_out_of_bounds(tmp_state):
    with pytest.raises(ValueError, match="outside bounds"):
        config_loader.apply_proposal({"SCORE_FULL_SIZE": 99})


def test_detect_manual_edit_none_when_file_missing(tmp_state):
    assert config_loader.detect_manual_edit() is None


def test_detect_manual_edit_none_when_matches_meta(tmp_state):
    config_loader.apply_proposal({"SCORE_FULL_SIZE": 9}, source="agent")
    # No external change → no drift
    assert config_loader.detect_manual_edit() is None


def test_detect_manual_edit_detects_drift(tmp_state):
    config_loader.apply_proposal({"SCORE_FULL_SIZE": 9}, source="agent")
    # Simulate Zach editing the file by hand
    (tmp_state / "learned_config.json").write_text(
        json.dumps({"SCORE_FULL_SIZE": 10, "RVOL_THRESHOLD": 1.7})
    )
    drift = config_loader.detect_manual_edit()
    assert drift is not None
    assert drift["before"] == {"SCORE_FULL_SIZE": 9}
    assert drift["after"] == {"SCORE_FULL_SIZE": 10, "RVOL_THRESHOLD": 1.7}


def test_acknowledge_current_clears_drift(tmp_state):
    config_loader.apply_proposal({"SCORE_FULL_SIZE": 9}, source="agent")
    (tmp_state / "learned_config.json").write_text(json.dumps({"SCORE_FULL_SIZE": 10}))
    assert config_loader.detect_manual_edit() is not None
    config_loader.acknowledge_current()
    assert config_loader.detect_manual_edit() is None


def test_revert_key_removes_knob(tmp_state):
    config_loader.apply_proposal({"SCORE_FULL_SIZE": 9, "RVOL_THRESHOLD": 1.7})
    config_loader.revert_key("SCORE_FULL_SIZE")
    cfg = json.loads((tmp_state / "learned_config.json").read_text())
    assert cfg == {"RVOL_THRESHOLD": 1.7}
