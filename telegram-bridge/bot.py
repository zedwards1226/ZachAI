"""
Telegram Bridge Bot
-------------------
Sends commands from Telegram and returns responses.
Chat ID is auto-registered on first message received.
Only the registered chat ID can execute commands (security).
"""

import os
import json
import logging
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = BASE_DIR / "bot.log"

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Persistence ───────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_authorized_id() -> int | None:
    return load_config().get("chat_id")


def register_chat_id(chat_id: int) -> None:
    config = load_config()
    config["chat_id"] = chat_id
    save_config(config)
    log.info("Registered authorized chat ID: %s", chat_id)

# ── Auth guard ────────────────────────────────────────────────────────────────

def is_authorized(update: Update) -> bool:
    authorized = get_authorized_id()
    if authorized is None:
        return True  # not configured yet — allow first /start or message
    return update.effective_chat.id == authorized

# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    config = load_config()

    if "chat_id" not in config:
        register_chat_id(chat_id)
        await update.message.reply_text(
            f"*Bot initialized!*\n\n"
            f"Your chat ID `{chat_id}` has been saved.\n"
            f"Only this chat can issue commands.\n\n"
            f"Use /help to see what's available.",
            parse_mode="Markdown",
        )
    else:
        if not is_authorized(update):
            await update.message.reply_text("Unauthorized.")
            return
        await update.message.reply_text(
            "Bot is already running. Use /help to see available commands."
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    await update.message.reply_text(
        "*Available commands*\n\n"
        "/start — Initialize bot & register your chat ID\n"
        "/help — Show this message\n"
        "/run `<command>` — Execute a shell command\n"
        "/ping — Check responsiveness\n"
        "/status — Show bot info\n"
        "/chatid — Show your current chat ID\n\n"
        "_Tip: /run supports any shell command, e.g. `/run dir C:\\`_",
        parse_mode="Markdown",
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/run <shell command>`", parse_mode="Markdown")
        return

    command = " ".join(context.args)
    log.info("Running command: %s", command)
    await update.message.reply_text(f"Running: `{command}`", parse_mode="Markdown")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home()),
        )
        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip() or "(no output)"

        if len(output) > 3900:
            output = output[:3900] + "\n…(truncated)"

        await update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("Timed out after 30 seconds.")
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text("Pong!")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    config = load_config()
    chat_id = config.get("chat_id", "not registered")
    python_ver = sys.version.split()[0]
    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"Status: running\n"
        f"Registered chat ID: `{chat_id}`\n"
        f"Python: {python_ver}\n"
        f"Log: `{LOG_FILE}`",
        parse_mode="Markdown",
    )


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Your chat ID: `{update.effective_chat.id}`", parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = load_config()

    # Auto-register on first message
    if "chat_id" not in config:
        register_chat_id(update.effective_chat.id)
        await update.message.reply_text(
            f"*Chat ID auto-registered:* `{update.effective_chat.id}`\n"
            "Use /help to see available commands.",
            parse_mode="Markdown",
        )
        return

    if not is_authorized(update):
        return  # silently ignore unauthorized users

    await update.message.reply_text(
        "Use /help to see available commands, or `/run <cmd>` to execute shell commands.",
        parse_mode="Markdown",
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    log.info("Starting Telegram bridge bot…")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Bot is polling. Press Ctrl+C to stop.")
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
