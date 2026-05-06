"""Plain-English labels for OmniAlpha codenames.

Single source of truth for translating internal strategy/sector codes into
human-readable phrases used in Telegram messages. Internal logs keep the
short names; only outbound text gets translated.

Pattern mirrors WeatherAlpha's plain-English style — Zach should be able
to read a phone notification and know what happened without decoding the
codename. New strategies must add an entry here OR fall back gracefully
(underscore-replaced) so a missing entry never crashes a notification.
"""
from __future__ import annotations

STRATEGY_LABELS: dict[str, str] = {
    "crypto_btc15m_midband":      "BTC 15-minute middle-band",
    "crypto_eth15m_midband":      "ETH 15-minute middle-band",
    "crypto_sol15m_midband":      "SOL 15-minute middle-band",
    "crypto_btcd_midband":        "BTC daily middle-band",
    "crypto_ethd_midband":        "ETH daily middle-band",
    "crypto_eth_hourly_midband":  "ETH hourly middle-band",
}

SECTOR_LABELS: dict[str, str] = {
    "crypto": "crypto markets",
}


def label_strategy(name: str | None) -> str:
    if not name:
        return "unknown strategy"
    return STRATEGY_LABELS.get(name, name.replace("_", " "))


def label_sector(name: str | None) -> str:
    if not name:
        return "unknown sector"
    return SECTOR_LABELS.get(name, name)


def short_resume_hint(strategy_name: str) -> str:
    """Return the short tag Zach can use when asking Jarvis to resume.

    Uses a stable suffix from the strategy name (e.g. crypto_btcd_midband
    → 'btcd'). Falls back to the full name if the pattern doesn't match.
    """
    if not strategy_name:
        return "(unknown)"
    parts = strategy_name.split("_")
    if len(parts) >= 2 and parts[0] == "crypto":
        # crypto_btcd_midband → "btcd"
        return parts[1]
    return strategy_name
