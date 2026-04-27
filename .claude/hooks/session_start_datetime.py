"""SessionStart hook: inject current date/day/time + market status.

Claude sees this as additionalContext at the start of every session so it never
has to guess "is the market open tomorrow" — the answer is already in context.
"""
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# 2026 US equity + futures market holidays (NYSE schedule; CME futures follow similar).
# Add as needed — simpler to hardcode than pull a calendar API.
MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day observed
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}


def market_status_for(d: date, t: time) -> str:
    dow = d.weekday()  # Mon=0..Sun=6
    if dow >= 5:
        return "CLOSED (weekend)"
    if d in MARKET_HOLIDAYS_2026:
        return "CLOSED (holiday)"
    open_t = time(9, 30)
    close_t = time(16, 0)
    if open_t <= t < close_t:
        return "OPEN (regular hours 09:30-16:00 ET)"
    if t < open_t:
        return f"PRE-MARKET (opens 09:30 ET, now {t.strftime('%H:%M')})"
    return f"AFTER-HOURS (closed 16:00 ET, now {t.strftime('%H:%M')})"


def next_trading_day(from_d: date) -> date:
    d = from_d + timedelta(days=1)
    while d.weekday() >= 5 or d in MARKET_HOLIDAYS_2026:
        d += timedelta(days=1)
    return d


def main():
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    next_td = next_trading_day(today)

    zach_off_today = today.weekday() == 4  # Friday per CLAUDE.md

    context = (
        f"DATETIME: {now.strftime('%A, %Y-%m-%d %H:%M')} ET\n"
        f"TODAY: {today.strftime('%A %Y-%m-%d')} | "
        f"MARKET: {market_status_for(today, now.time())}\n"
        f"TOMORROW: {tomorrow.strftime('%A %Y-%m-%d')} | "
        f"MARKET: {market_status_for(tomorrow, time(10, 0))}\n"
        f"NEXT TRADING DAY: {next_td.strftime('%A %Y-%m-%d')}\n"
        f"ZACH OFF TODAY: {'YES (Friday)' if zach_off_today else 'no'}\n"
        "Use this instead of guessing. When user says \"tomorrow\" or asks if "
        "the market is ready, cross-reference the above."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
