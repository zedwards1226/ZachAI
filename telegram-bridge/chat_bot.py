"""
ZachAI Chat Bot — Claude CLI + TradingView on Telegram
Uses your Max subscription via the claude CLI (no API key needed).
Claude has full access: TradingView MCP, Bash, web search, GitHub, file system.
"""

import os, json, asyncio, logging, sys
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

BASE_DIR    = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE    = BASE_DIR / "chat_bot.log"
CLAUDE_CMD  = r"C:\Users\zedwa\AppData\Roaming\npm\claude.cmd"
WORK_DIR    = r"C:\Users\zedwa"
MAX_HISTORY = 10  # message pairs to keep in context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# conversation history per chat_id
conversations: dict[int, list] = {}

# global lock — only one claude task at a time
_task_lock = asyncio.Lock()
_current_task = {"text": None}

SYSTEM = """You are Claude, Zach's AI assistant running on his Windows machine in Memphis TN.
You have full tool access: TradingView Desktop MCP, Bash, Read/Write/Edit files, web search via Bash.

Web search: python -c "from ddgs import DDGS; results=list(DDGS().text('QUERY', max_results=5)); [print(r['title'], r['href'], r['body'][:200]) for r in results]"
GitHub search: curl -s "https://api.github.com/search/repositories?q=QUERY&sort=stars&per_page=5" | python -c "import json,sys; [print(r['full_name'], r['stargazers_count'], r['html_url']) for r in json.load(sys.stdin)['items']]"

=== STRATEGY WORKFLOW (when Zach says find/backtest/demo trade) ===
1. SEARCH — web search + GitHub for top Pine Script strategies for the market/style requested
2. PICK — choose the most promising one (good stars, active repo, clear logic)
3. LOAD — fetch the Pine Script source, adapt it if needed, inject into TradingView via pine_set_source
4. COMPILE — pine_smart_compile, fix any errors
5. BACKTEST — data_get_strategy_results, report: net profit, win rate, max drawdown, total trades, profit factor
6. DECIDE — if win rate >50% AND profit factor >1.5: activate demo trading. Otherwise tell Zach results and ask if he wants to try another
7. DEMO TRADE — create TradingView alert for entry/exit signals pointing to http://localhost:8766/alert with JSON payload {"action": "buy/sell/close", "symbol": "SYMBOL", "price": {{close}}, "strategy": "NAME"}. Start paper_trader.py if not running: cd C:\\ZachAI\\trading && start pythonw paper_trader.py
8. CONFIRM — tell Zach: strategy name, backtest results, demo trading is live

Paper trader status: GET http://localhost:8766/status
Reset paper trades: POST http://localhost:8766/reset

Rules:
- Be conversational and concise — Zach is on his phone
- No task IDs or "task complete" headers — natural responses only
- Always screenshot after TradingView changes
- Paper mode ON for WeatherAlpha. Never change that
- Demo trading is paper only — no real money ever"""


def build_prompt(history: list, user_text: str) -> str:
    parts = [
        "CRITICAL: Do NOT invoke any skills. Do NOT run resume-session, save-session, or any other skill. Do NOT output session headers or task lists. Just respond directly.",
        "",
        SYSTEM,
        "",
    ]
    if history:
        parts.append("Previous messages:")
        for msg in history:
            label = "Zach" if msg["role"] == "user" else "Claude"
            parts.append(f"{label}: {msg['text']}")
        parts.append("")
    parts.append(f"Zach says: {user_text}")
    parts.append("")
    parts.append("Respond directly and concisely. No preamble. No session output. Just do the task.")
    return "\n".join(parts)


def strip_session_preamble(text: str) -> str:
    """Remove session-resume skill output that appears before the real response."""
    markers = ["SESSION LOADED", "═══", "PROJECT:", "WHAT WE'RE BUILDING", "ACTIVE TASKS", "CONTEXT TO LOAD"]
    lines = text.splitlines()
    # Find where the real response starts — after the last marker block
    last_marker_line = -1
    in_code_block = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
        if any(m in line for m in markers):
            last_marker_line = i
    if last_marker_line >= 0:
        # Skip past the closing ``` of the session block
        for i in range(last_marker_line, len(lines)):
            if lines[i].strip() == "```" or (i > last_marker_line and not lines[i].strip().startswith("```") and lines[i].strip()):
                return "\n".join(lines[i:]).strip()
    return text.strip()


async def run_claude(prompt: str, progress_msg=None) -> str:
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(prompt)
            tmp_path = f.name

        # Strip API key so claude uses Max account, not the low-credit API key
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        proc = await asyncio.create_subprocess_exec(
            CLAUDE_CMD, "-p", f"@{tmp_path}",
            "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=WORK_DIR,
            env=env,
        )

        output_lines = []
        last_update = asyncio.get_event_loop().time()
        deadline = last_update + 600  # 10 minute hard limit

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                proc.kill()
                return strip_session_preamble("\n".join(output_lines)) or "Timed out after 10 minutes."
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=min(remaining, 30))
            except asyncio.TimeoutError:
                # Still running — send heartbeat every 15s
                if progress_msg and asyncio.get_event_loop().time() - last_update > 15:
                    try:
                        await progress_msg.edit_text("still working...")
                        last_update = asyncio.get_event_loop().time()
                    except Exception:
                        pass
                continue

            if not line:
                break

            decoded = line.decode(errors="replace")
            output_lines.append(decoded)

            # Send live progress chunks every ~30s
            if progress_msg and asyncio.get_event_loop().time() - last_update > 30:
                snippet = "".join(output_lines[-20:]).strip()[-800:]
                if snippet:
                    try:
                        await progress_msg.edit_text(f"working...\n\n{snippet}")
                        last_update = asyncio.get_event_loop().time()
                    except Exception:
                        pass

        await proc.wait()
        Path(tmp_path).unlink(missing_ok=True)
        raw = "".join(output_lines)
        return strip_session_preamble(raw) or "Done."

    except Exception as e:
        log.exception("Claude CLI error")
        return f"Error: {e}"


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    text = (update.message.text or "").strip()
    if not text:
        return

    chat_id = update.effective_chat.id

    # If a task is already running, tell user instead of spawning another
    if _task_lock.locked():
        await update.message.reply_text(f"Still working on: \"{_current_task['text']}\"\nWait for it to finish or send /cancel to stop it.")
        return

    # Immediately show typing indicator in chat header
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    history = conversations.setdefault(chat_id, [])
    msg = await update.message.reply_text("thinking...")
    prompt = build_prompt(history, text)
    log.info("[%s] User: %s", chat_id, text[:100])

    async with _task_lock:
        _current_task["text"] = text[:60]
        reply = await run_claude(prompt, progress_msg=msg)
    log.info("[%s] Claude: %s", chat_id, reply[:200])

    # Update history
    history.append({"role": "user", "text": text})
    history.append({"role": "assistant", "text": reply[:800]})  # truncate stored history
    if len(history) > MAX_HISTORY * 2:
        conversations[chat_id] = history[-(MAX_HISTORY * 2):]

    # Send — split if over 4000 chars
    if len(reply) <= 4000:
        await msg.edit_text(reply)
    else:
        await msg.edit_text(reply[:4000])
        for i in range(4000, len(reply), 4000):
            await update.message.reply_text(reply[i:i+4000])


# ── config / auth ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}

def save_config(c: dict):
    CONFIG_FILE.write_text(json.dumps(c, indent=2))

def is_authorized(update: Update) -> bool:
    auth = load_config().get("chat_id")
    return True if auth is None else update.effective_chat.id == auth


# ── commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    if "chat_id" not in cfg:
        cfg["chat_id"] = update.effective_chat.id
        save_config(cfg)
    await update.message.reply_text("Hey Zach. What do you need?")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    conversations.pop(update.effective_chat.id, None)
    await update.message.reply_text("Cleared.")

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    status = f"busy: \"{_current_task['text']}\"" if _task_lock.locked() else "idle"
    await update.message.reply_text(f"Online. Max/CLI. Status: {status}")

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    taskkill = await asyncio.create_subprocess_exec(
        "taskkill", "/F", "/IM", "claude.exe",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await taskkill.wait()
    await update.message.reply_text("Cancelled. Ready for next task.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("clear",  cmd_clear))
    app.add_handler(CommandHandler("ping",   cmd_ping))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("ZachAI Chat Bot (Max/CLI) starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    import asyncio as _asyncio
    _asyncio.set_event_loop(_asyncio.new_event_loop())
    main()
