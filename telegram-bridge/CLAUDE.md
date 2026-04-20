# TELEGRAM BRIDGE — Project Brain

## OVERVIEW
Jarvis Telegram bot — primary command/control surface. Routes commands to Claude Code, ORB system, and WeatherAlpha. Sends heartbeats, trade alerts, digests.

- Active file: `C:\ZachAI\telegram-bridge\bot.py`
- Auto-start: `scripts/Jarvis_Bot.vbs`
- Retired: `chat_bot.py` (replaced by bot.py — do not revive)

## PROTECTION RULE
**Never modify `bot.py` without explicit approval.** Show the diff first and wait for confirmation. This is load-bearing: the bot is the only command surface when Zach is away from the PC.

## COMMANDS
- `/claude` — forward prompt to Claude Code
- `/run` — execute shell command
- `/tasks` — list/manage scheduled tasks
- Approval flows — inline confirm/deny buttons for builds and risky actions

## HOOKS
`hooks/` dir contains Telegram hook handlers. Check before creating a new one — follow the grep-before-create rule.

## ENV
- Bot token + chat ID stored in `.env` (gitignored)
- Never commit the token

## AUTO-MERGE EXCEPTION
Changes to `bot.py` follow the standard approval-first flow. After approval is granted and change is merged, the auto-merge policy applies normally.
