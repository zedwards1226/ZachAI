"""
Telegram Bridge Bot - Enhanced
  /claude <prompt>  — run Claude Code, stream output, route approvals
  /run <cmd>        — shell command
  /tasks            — list active claude tasks
  /status /ping     — health
Approval requests from Claude Code hooks come in over HTTP on port 8765,
are forwarded as inline-keyboard Telegram messages, and block until answered.
"""

import os, json, logging, subprocess, sys, asyncio, threading, uuid
from pathlib import Path
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DATA_DIR    = Path("C:/ZachAI/data")
STATE_FILE  = DATA_DIR / "state.json"
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE    = BASE_DIR / "bot.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")
BOT_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN")
APPROVAL_PORT    = 8765
PROGRESS_SECS    = 90   # send a progress chunk every N seconds

# ── Globals (set during startup) ──────────────────────────────────────────────
_bot_loop: asyncio.AbstractEventLoop | None = None
_bot_app  = None

# approval_id → {event: threading.Event, approved: bool|None, data: dict}
pending_approvals: dict[str, dict] = {}

# task_id → {prompt, status, output}
active_tasks: dict[str, dict] = {}

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

# ── State helpers ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tasks": [], "messages": [], "approvals": []}

def save_state(s: dict) -> None:
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")

def log_message(direction: str, text: str) -> None:
    s = load_state()
    s.setdefault("messages", []).append({
        "id": str(uuid.uuid4())[:8],
        "direction": direction,
        "text": text[:500],
        "timestamp": _now(),
    })
    s["messages"] = s["messages"][-100:]
    save_state(s)

def upsert_task(task_id: str, **fields) -> None:
    s = load_state()
    tasks = s.setdefault("tasks", [])
    for t in tasks:
        if t["id"] == task_id:
            t.update(fields)
            t["updated_at"] = _now()
            save_state(s)
            return
    tasks.append({"id": task_id, "updated_at": _now(), **fields})
    s["tasks"] = tasks[-50:]
    save_state(s)

def log_approval_state(aid: str, **fields) -> None:
    s = load_state()
    appr = s.setdefault("approvals", [])
    for a in appr:
        if a["id"] == aid:
            a.update(fields)
            save_state(s)
            return
    appr.append({"id": aid, **fields})
    s["approvals"] = appr[-50:]
    save_state(s)

# ── Config helpers ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_config(c: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(c, indent=2), encoding="utf-8")

def get_authorized_id() -> int | None:
    return load_config().get("chat_id")

def register_chat_id(chat_id: int) -> None:
    c = load_config()
    c["chat_id"] = chat_id
    save_config(c)
    log.info("Registered chat ID: %s", chat_id)

def is_authorized(update: Update) -> bool:
    auth = get_authorized_id()
    return True if auth is None else update.effective_chat.id == auth

# ── Approval HTTP server (runs in background thread) ──────────────────────────

class _ApprovalHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):   # silence HTTP logs
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length))

        aid   = str(uuid.uuid4())[:8]
        event = threading.Event()
        pending_approvals[aid] = {"event": event, "approved": None, "data": body}

        log_approval_state(aid,
            tool_name  = body.get("tool_name", "unknown"),
            tool_input = body.get("tool_input", {}),
            status     = "pending",
            timestamp  = _now(),
        )

        # Dispatch Telegram message on the running async loop
        if _bot_loop and _bot_app:
            asyncio.run_coroutine_threadsafe(
                _send_approval_telegram(aid, body), _bot_loop
            )

        # Block this thread until user replies or timeout
        event.wait(timeout=300)

        entry    = pending_approvals.pop(aid, {})
        approved = entry.get("approved") or False
        log_approval_state(aid, status="approved" if approved else "denied")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"approved": approved}).encode())


def _start_approval_server():
    server = HTTPServer(("127.0.0.1", APPROVAL_PORT), _ApprovalHandler)
    log.info("Approval HTTP server on 127.0.0.1:%s", APPROVAL_PORT)
    server.serve_forever()

# ── Telegram approval message ─────────────────────────────────────────────────

async def _send_approval_telegram(aid: str, data: dict) -> None:
    chat_id = get_authorized_id()
    if not chat_id or not _bot_app:
        return

    tool = data.get("tool_name", "unknown")
    inp  = data.get("tool_input", {})
    inp_str = (
        "\n".join(f"  {k}: {str(v)[:200]}" for k, v in inp.items())
        if isinstance(inp, dict) else str(inp)[:400]
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅  YES", callback_data=f"approve:{aid}"),
        InlineKeyboardButton("❌  NO",  callback_data=f"deny:{aid}"),
    ]])

    await _bot_app.bot.send_message(
        chat_id    = chat_id,
        text       = (
            f"*Claude wants to use:* `{tool}`\n\n"
            f"```\n{inp_str}\n```\n\n"
            f"ID: `{aid}` — reply within 5 min"
        ),
        parse_mode = "Markdown",
        reply_markup = keyboard,
    )

# ── Callback: inline YES/NO buttons ──────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_authorized(update):
        return

    action, aid = q.data.split(":", 1)
    approved = action == "approve"

    if aid in pending_approvals:
        pending_approvals[aid]["approved"] = approved
        pending_approvals[aid]["event"].set()
        label = "✅ Approved" if approved else "❌ Denied"
        await q.edit_message_text(
            q.message.text + f"\n\n*{label}*",
            parse_mode="Markdown",
        )
    else:
        await q.edit_message_text(
            q.message.text + "\n\n_(expired or already handled)_",
            parse_mode="Markdown",
        )

# ── Claude runner ─────────────────────────────────────────────────────────────

async def run_claude(task_id: str, prompt: str, chat_id: int) -> None:
    upsert_task(task_id, prompt=prompt, status="running",
                start_time=_now(), output="")
    active_tasks[task_id] = {"prompt": prompt, "status": "running", "output": ""}

    await _bot_app.bot.send_message(
        chat_id    = chat_id,
        text       = f"*Task started* `[{task_id}]`\n\n_{prompt}_",
        parse_mode = "Markdown",
    )

    output_lines: list[str] = []
    last_sent_at  = asyncio.get_event_loop().time()
    last_sent_idx = 0

    async def send_progress():
        nonlocal last_sent_idx, last_sent_at
        chunk = output_lines[last_sent_idx:]
        if not chunk:
            return
        text = "".join(chunk)[-3500:]
        await _bot_app.bot.send_message(
            chat_id    = chat_id,
            text       = f"*Progress* `[{task_id}]`\n```\n{text}\n```",
            parse_mode = "Markdown",
        )
        last_sent_idx = len(output_lines)
        last_sent_at  = asyncio.get_event_loop().time()

    try:
        proc = await asyncio.create_subprocess_exec(
            r"C:\Users\zedwa\AppData\Roaming\npm\claude.cmd",
            "-p", prompt,
            stdout = asyncio.subprocess.PIPE,
            stderr = asyncio.subprocess.STDOUT,
            cwd    = "C:\\ZachAI",
        )
        active_tasks[task_id]["process"] = proc

        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
            except (asyncio.TimeoutError, TimeoutError):
                if asyncio.get_event_loop().time() - last_sent_at >= PROGRESS_SECS:
                    await send_progress()
                continue

            if not raw:
                break

            line = raw.decode(errors="replace")
            output_lines.append(line)
            tail = "".join(output_lines[-50:])
            active_tasks[task_id]["output"] = tail
            upsert_task(task_id, output=tail, status="running")

            if asyncio.get_event_loop().time() - last_sent_at >= PROGRESS_SECS:
                await send_progress()

        await proc.wait()
        rc = proc.returncode

        final = "".join(output_lines).strip()
        if len(final) > 3800:
            final = "…" + final[-3800:]

        status = "completed" if rc == 0 else "failed"
        upsert_task(task_id, status=status, output=final)
        active_tasks.pop(task_id, None)

        await _bot_app.bot.send_message(
            chat_id    = chat_id,
            text       = (
                f"*Task {status}* `[{task_id}]`  exit={rc}\n\n"
                f"```\n{final[-3500:] or '(no output)'}\n```"
            ),
            parse_mode = "Markdown",
        )

    except Exception as exc:
        log.exception("Claude task error: %s", exc)
        upsert_task(task_id, status="failed")
        active_tasks.pop(task_id, None)
        await _bot_app.bot.send_message(
            chat_id    = chat_id,
            text       = f"*Task failed* `[{task_id}]`\nError: {exc}",
            parse_mode = "Markdown",
        )

# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    config  = load_config()
    if "chat_id" not in config:
        register_chat_id(chat_id)
        await update.message.reply_text(
            f"*Bot initialized!*\nChat ID `{chat_id}` saved.\nUse /help for commands.",
            parse_mode="Markdown",
        )
    else:
        if not is_authorized(update):
            await update.message.reply_text("Unauthorized.")
            return
        await update.message.reply_text("Bot running. Use /help.")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "*Commands*\n\n"
        "/claude `<prompt>` — Run Claude Code task\n"
        "/tasks — List running tasks\n"
        "/run `<cmd>` — Shell command\n"
        "/status — Bot info\n"
        "/ping — Ping\n"
        "/chatid — Your chat ID\n\n"
        "_Approval requests appear as YES/NO buttons when Claude needs to use a tool._",
        parse_mode="Markdown",
    )

async def cmd_claude(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    if not ctx.args:
        await update.message.reply_text(
            "Usage: `/claude <prompt>`",
            parse_mode="Markdown",
        )
        return
    prompt  = " ".join(ctx.args)
    task_id = str(uuid.uuid4())[:8]
    log_message("in", f"/claude {prompt}")
    asyncio.create_task(run_claude(task_id, prompt, update.effective_chat.id))

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    if not active_tasks:
        await update.message.reply_text("No active tasks.")
        return
    lines = [f"`{tid}` {t['status']}: _{t['prompt'][:60]}_"
             for tid, t in active_tasks.items()]
    await update.message.reply_text(
        "*Active tasks*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )

async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/run <command>`", parse_mode="Markdown")
        return
    command = " ".join(ctx.args)
    log_message("in", f"/run {command}")
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip() or "(no output)"
        if len(out) > 3900:
            out = out[:3900] + "\n…(truncated)"
        await update.message.reply_text(f"```\n{out}\n```", parse_mode="Markdown")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("Timed out after 30s.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    cfg = load_config()
    await update.message.reply_text(
        f"*Status*\n"
        f"Chat ID: `{cfg.get('chat_id', 'unset')}`\n"
        f"Active tasks: {len(active_tasks)}\n"
        f"Pending approvals: {len(pending_approvals)}",
        parse_mode="Markdown",
    )

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    await update.message.reply_text("Pong!")

async def cmd_chatid(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    config = load_config()
    if "chat_id" not in config:
        register_chat_id(update.effective_chat.id)
        await update.message.reply_text(
            f"Chat ID `{update.effective_chat.id}` registered. Use /help.",
            parse_mode="Markdown",
        )
        return
    if not is_authorized(update):
        return
    text = update.message.text or ""
    log_message("in", text)
    await update.message.reply_text(
        "Use /help or `/claude <prompt>` to run Claude Code.",
        parse_mode="Markdown",
    )

# ── Startup / main ────────────────────────────────────────────────────────────

async def _post_init(application: Application) -> None:
    global _bot_loop
    _bot_loop = asyncio.get_running_loop()
    log.info("Async loop captured")

def main() -> None:
    global _bot_app

    if not BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    threading.Thread(target=_start_approval_server, daemon=True).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    _bot_app = app

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("claude", cmd_claude))
    app.add_handler(CommandHandler("tasks",  cmd_tasks))
    app.add_handler(CommandHandler("run",    cmd_run))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ping",   cmd_ping))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    import asyncio as _asyncio
    _asyncio.set_event_loop(_asyncio.new_event_loop())
    log.info("Telegram bridge starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
