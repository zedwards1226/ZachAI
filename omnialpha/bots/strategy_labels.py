"""Plain-English labels for strategy codenames.

Single source of truth for translating internal strategy/sector codes into
human-readable phrases used in Telegram messages. Internal logs keep the
short names; only outbound text gets translated.

Pattern mirrors WeatherAlpha's plain-English style — Zach should read a
phone notification and know what happened without decoding the codename.
New strategies add an entry here OR fall back gracefully (underscore-
replaced) so a missing entry never crashes a notification.

Crypto labels removed 2026-05-27 when OmniAlpha crypto bot was deleted.
"""
from __future__ import annotations

STRATEGY_LABELS: dict[str, str] = {}

SECTOR_LABELS: dict[str, str] = {}


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

    Falls back to the full name if no specific pattern matches.
    """
    if not strategy_name:
        return "(unknown)"
    return strategy_name
