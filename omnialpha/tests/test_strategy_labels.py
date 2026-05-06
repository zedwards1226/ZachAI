"""Regression guard for plain-English strategy labels in Telegram messages.

Catches the regression where internal codenames like `crypto_btc15m_midband`
leak into Telegram text Zach reads on his phone.
"""
from bots.strategy_labels import (
    STRATEGY_LABELS,
    label_strategy,
    label_sector,
    short_resume_hint,
)


def test_known_strategy_labels_are_human_readable():
    """Every registered strategy translates to a phrase that doesn't
    contain underscore-separated codename fragments."""
    for code, pretty in STRATEGY_LABELS.items():
        assert "_" not in pretty, f"{code} → {pretty!r} still has underscores"
        assert pretty != code, f"{code} maps to itself — not translated"
        # Asset name should appear in the label (BTC/ETH/SOL etc.)
        assert any(c.isupper() for c in pretty), (
            f"{pretty!r} has no uppercase asset name — likely not translated"
        )


def test_unknown_strategy_falls_back_to_underscore_replace():
    out = label_strategy("crypto_doge_midband")
    assert "_" not in out
    assert "doge" in out


def test_label_strategy_handles_none_or_empty():
    assert label_strategy(None) == "unknown strategy"
    assert label_strategy("") == "unknown strategy"


def test_label_sector_known_and_unknown():
    assert label_sector("crypto") == "crypto markets"
    assert label_sector("politics") == "politics"  # passthrough
    assert label_sector(None) == "unknown sector"


def test_short_resume_hint_extracts_asset_tag():
    assert short_resume_hint("crypto_btcd_midband") == "btcd"
    assert short_resume_hint("crypto_eth15m_midband") == "eth15m"
    # Non-pattern names fall back to full name (still usable).
    assert short_resume_hint("standalone") == "standalone"
    assert short_resume_hint("") == "(unknown)"


def test_pause_alert_uses_label_not_codename():
    """Render the strategy-grader pause message and confirm the codename
    does NOT appear and the human label DOES."""
    code = "crypto_btcd_midband"
    pretty = label_strategy(code)
    hint = short_resume_hint(code)
    # Mirror the message body in strategy_grader.py:158
    msg = (
        f"⚠️ <b>I paused a strategy</b>\n"
        f"The {pretty} strategy has been losing too often. "
        f"To turn it back on, ask Jarvis: \"resume {hint}\"."
    )
    assert code not in msg, f"raw codename {code!r} leaked into message"
    assert pretty in msg
    assert hint in msg
