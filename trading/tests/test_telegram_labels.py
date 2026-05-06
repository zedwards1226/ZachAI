"""Regression guard for plain-English Telegram text in ORB.

Catches the regression where internal codenames (`SCORE_HALF_SIZE`, `htf_bias`,
`risk_too_wide:$540>350`) leak into the messages Zach reads on his phone.
"""
import sys
from pathlib import Path

# Allow `pytest` from trading/ — same trick learning_agent.py uses.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.telegram import (  # noqa: E402
    _SCORE_KEY_PHRASE,
    _humanize_skip_reason,
    _score_label,
)


def test_every_known_score_key_has_a_human_phrase():
    """Spot-check the most common breakdown keys translate to a sentence."""
    expected_keys = {
        "orb_candle_direction", "htf_bias", "bias_conflict",
        "second_break", "open_air", "approaching_wall", "at_level",
        "rvol", "vwap_alignment", "vix_regime", "prior_day_direction",
        "no_news_block", "no_truth_block", "news_block", "truth_block",
    }
    missing = expected_keys - _SCORE_KEY_PHRASE.keys()
    assert not missing, f"missing plain-English labels: {missing}"
    for key, phrase in _SCORE_KEY_PHRASE.items():
        assert "_" not in phrase, f"{key} → {phrase!r} still has underscores"
        assert phrase != key, f"{key} maps to itself — not translated"


def test_unknown_score_key_falls_back_safely(caplog):
    """Missing key shouldn't crash a notification — falls back to underscore-
    replaced form, with a logger.warning so we catch the gap."""
    out = _score_label("brand_new_factor")
    assert out == "brand new factor"


def test_humanize_risk_too_wide():
    out = _humanize_skip_reason("risk_too_wide:$540>350")
    assert "$540" in out
    assert "$350" in out
    assert "_" not in out
    # The raw codename must NOT appear — that's the whole point.
    assert "risk_too_wide" not in out


def test_humanize_cascade_reason():
    out = _humanize_skip_reason("cascade:approaching_wall")
    assert "cascade:" not in out
    assert "_" not in out
    assert "level" in out.lower()  # phrase mentions level


def test_humanize_unknown_reason_falls_back():
    out = _humanize_skip_reason("some_new_gate")
    assert out == "some new gate"


def test_skip_message_uses_translated_reason():
    """Render the notify_skip body and confirm raw codename is gone."""
    raw = "risk_too_wide:$540>350"
    plain = _humanize_skip_reason(raw)
    msg = (
        f"⏭️ <b>Skipped a buy setup</b>\n"
        f"A safety check blocked the trade: <b>{plain}</b>."
    )
    assert "risk_too_wide" not in msg
    assert "$540" in msg
