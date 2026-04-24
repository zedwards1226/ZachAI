"""
Telegram Bridge Bot - Enhanced
  /claude <prompt>  — run Claude Code, stream output, route approvals
  /run <cmd>        — shell command
  /tasks            — list active claude tasks
  /status /ping     — health
Approval requests from Claude Code hooks come in over HTTP on port 8765,
are forwarded as inline-keyboard Telegram messages, and block until answered.
"""

import os, json, logging, subprocess, sys, asyncio, threading, uuid, time
from pathlib import Path
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
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

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024   # Telegram bot API cap

# Jarvis persona — injected into every Claude Code run so replies feel
# like Zach's operator, not generic Claude.
JARVIS_SYSTEM_PROMPT = (
    "You are Jarvis, Zach Edwards's personal AI operator running on his "
    "Windows PC at C:\\ZachAI. You talk directly to Zach over Telegram. "
    "Keep replies SHORT and conversational (1-4 sentences unless he asks "
    "for detail or code). No markdown headers, no bullet lists for simple "
    "answers. Do not announce what you're about to do — just do it. "
    "You manage his trading bots (ORB futures, Kalshi weather), his "
    "Telegram bridge, and his company projects. If Zach sends a photo, "
    "read it and describe what you see. If he sends a file, read it and "
    "summarize. Never say you can't do something — try first."
)

# Zach explicitly says "opus" anywhere in the message → switch to Opus 4.7.
# No other magic words. Default stays fast (haiku).
def _wants_opus(text: str) -> bool:
    return "opus" in text.lower()

# ── Globals (set during startup) ──────────────────────────────────────────────
_bot_loop: asyncio.AbstractEventLoop | None = None
_bot_app  = None

# approval_id → {event: threading.Event, approved: bool|None, data: dict}
pending_approvals: dict[str, dict] = {}

# task_id → {prompt, status, output}
active_tasks: dict[str, dict] = {}

# chat_id → Claude Code session_id (enables multi-turn memory within a bot session)
chat_sessions: dict[int, str] = {}

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

async def _download_telegram_file(file_obj, suggested_name: str) -> Path | None:
    """Download a Telegram File to UPLOAD_DIR. Returns path or None on failure."""
    try:
        if file_obj.file_size and file_obj.file_size > MAX_UPLOAD_BYTES:
            return None
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe = "".join(c for c in suggested_name if c.isalnum() or c in "._-") or "file"
        path = UPLOAD_DIR / f"{ts}_{safe}"
        await file_obj.download_to_drive(custom_path=str(path))
        return path
    except Exception as exc:
        log.exception("download failed: %s", exc)
        return None

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

async def _stream_claude(cmd: list[str], chat_id: int,
                         edit_cb, on_session_id) -> tuple[int, str]:
    """Spawn claude CLI, stream stream-json events, return (rc, final_text)."""
    log.info("claude cmd: %s", " ".join(cmd[:-1]) + " <prompt>")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="C:\\ZachAI",
        limit=10 * 1024 * 1024,  # 10 MB — stream-json lines can be huge
    )
    final_text = ""
    last_result_text = ""
    async for line in proc.stdout:
        try:
            ev = json.loads(line.decode(errors="replace"))
        except Exception:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            sid = ev.get("session_id")
            if sid:
                on_session_id(sid)
        elif t == "assistant":
            for part in ev.get("message", {}).get("content", []):
                if part.get("type") == "text":
                    final_text += part.get("text", "")
                    await edit_cb(final_text)
        elif t == "result":
            last_result_text = ev.get("result", "") or ""
            if ev.get("is_error"):
                log.warning("claude result is_error=true: %s", last_result_text[:300])
    await proc.wait()
    rc = proc.returncode
    if not final_text:
        final_text = last_result_text
    if rc != 0 or not final_text:
        err = (await proc.stderr.read()).decode(errors="replace")[-2000:]
        log.warning("claude rc=%s stderr=%s final_len=%d result=%s",
                    rc, err, len(final_text), last_result_text[:300])
    return rc, final_text


async def run_claude(task_id: str, prompt: str, chat_id: int,
                     attachments: list[Path] | None = None,
                     fast: bool = False) -> None:
    upsert_task(task_id, prompt=prompt[:300], status="running",
                start_time=_now(), output="")
    active_tasks[task_id] = {"prompt": prompt, "status": "running", "output": ""}

    # Prepend attachment paths so Claude knows to read them
    if attachments:
        paths_block = "\n".join(f"- {p}" for p in attachments)
        prompt = (
            f"[User sent attachment(s). Read them before responding.]\n"
            f"{paths_block}\n\n{prompt}"
        )

    status_msg = await _bot_app.bot.send_message(chat_id=chat_id, text="🧠 Thinking…")
    msg_id = status_msg.message_id

    typing_active = True
    async def _keep_typing():
        while typing_active:
            try:
                await _bot_app.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(4)
    typing_task = asyncio.create_task(_keep_typing())

    last_edit = 0.0
    last_shown = ""
    async def _maybe_edit(text: str, *, force: bool = False):
        nonlocal last_edit, last_shown
        now = time.time()
        if not force and now - last_edit < 2.5:
            return
        body = text[-3800:] if text else "🧠 Thinking…"
        if body == last_shown:
            return
        last_edit = now
        last_shown = body
        try:
            await _bot_app.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=body,
            )
        except Exception:
            pass

    def _set_session(sid: str):
        chat_sessions[chat_id] = sid

    try:
        # Default: Sonnet 4.6 (reliable vision + fast enough for chat).
        # Opus 4.7 only when Zach explicitly says "opus" in his message.
        model = "claude-opus-4-7" if not fast else "claude-sonnet-4-6"
        cmd = [r"C:\Users\zedwa\AppData\Roaming\npm\claude.cmd",
               "-p", "--output-format", "stream-json", "--verbose",
               "--append-system-prompt", JARVIS_SYSTEM_PROMPT,
               "--model", model,
               "--add-dir", str(UPLOAD_DIR)]
        # Skip session resume when attachments are present — fresh context
        # prevents Claude from replying to stale conversation state and
        # makes sure he reads the new file.
        prior = None if (attachments or fast) else chat_sessions.get(chat_id)
        if prior:
            cmd += ["--resume", prior]
        # "--" terminates variadic flags (--tools, --add-dir) so the
        # prompt isn't swallowed as extra tool/dir args.
        cmd += ["--", prompt]

        rc, final_text = await _stream_claude(cmd, chat_id, _maybe_edit, _set_session)

        # Resume failed? retry fresh once.
        if rc != 0 and prior and not final_text:
            log.warning("resume failed (rc=%d), retrying fresh", rc)
            chat_sessions.pop(chat_id, None)
            cmd2 = [r"C:\Users\zedwa\AppData\Roaming\npm\claude.cmd",
                    "-p", "--output-format", "stream-json", "--verbose", prompt]
            rc, final_text = await _stream_claude(cmd2, chat_id, _maybe_edit, _set_session)

        typing_active = False
        typing_task.cancel()

        final_text = (final_text or "(no output)")[-3800:]
        status = "completed" if rc == 0 else "failed"
        upsert_task(task_id, status=status, output=final_text)
        active_tasks.pop(task_id, None)
        await _maybe_edit(final_text, force=True)

    except Exception as exc:
        typing_active = False
        typing_task.cancel()
        log.exception("Claude task error: %s", exc)
        upsert_task(task_id, status="failed")
        active_tasks.pop(task_id, None)
        try:
            await _bot_app.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=f"Error: {exc}")
        except Exception:
            pass

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
        "/new — Reset conversation (start fresh context)\n"
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

async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation session — next message starts a fresh context."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    removed = chat_sessions.pop(chat_id, None)
    if removed:
        await update.message.reply_text("Conversation reset. Next message starts fresh.")
    else:
        await update.message.reply_text("No active session to reset.")

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
    if not text.strip():
        return
    log_message("in", text)
    task_id = str(uuid.uuid4())[:8]
    # Default: fast haiku. Switch to Opus only when Zach says "opus".
    use_fast = not _wants_opus(text)
    asyncio.create_task(run_claude(task_id, text, update.effective_chat.id,
                                   fast=use_fast))

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    photos = update.message.photo
    if not photos:
        return
    biggest = photos[-1]
    tg_file = await biggest.get_file()
    path = await _download_telegram_file(tg_file, f"photo_{biggest.file_unique_id}.jpg")
    if not path:
        await update.message.reply_text("Couldn't save photo (too big or download failed).")
        return
    caption = (update.message.caption or "").strip()
    if caption:
        prompt = caption
    else:
        prompt = (
            "Use the Read tool ONLY on the image path above, then describe "
            "what you see in 2-3 short sentences. Do not run git, do not "
            "explore the repo, do not open any other files. Just read the "
            "image and reply."
        )
    log_message("in", f"[photo] {path.name} caption={caption!r}")
    task_id = str(uuid.uuid4())[:8]
    asyncio.create_task(run_claude(task_id, prompt, update.effective_chat.id,
                                   attachments=[path], fast=True))

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    doc = update.message.document
    if not doc:
        return
    if doc.file_size and doc.file_size > MAX_UPLOAD_BYTES:
        await update.message.reply_text(
            f"File too big ({doc.file_size // 1024 // 1024} MB > 20 MB). "
            f"Trim it or drop it in C:\\ZachAI\\ directly."
        )
        return
    tg_file = await doc.get_file()
    path = await _download_telegram_file(tg_file, doc.file_name or "file")
    if not path:
        await update.message.reply_text("Download failed.")
        return
    caption = (update.message.caption or "").strip()
    if caption:
        prompt = caption
    else:
        prompt = (
            f"Use the Read tool ONLY on the file path above ({path.name}), "
            f"then summarize it briefly. Do not run git, do not explore the "
            f"repo, do not open any other files."
        )
    log_message("in", f"[document] {path.name} caption={caption!r}")
    task_id = str(uuid.uuid4())[:8]
    asyncio.create_task(run_claude(task_id, prompt, update.effective_chat.id,
                                   attachments=[path], fast=True))

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
    app.add_handler(CommandHandler("new",    cmd_new))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    import asyncio as _asyncio
    _asyncio.set_event_loop(_asyncio.new_event_loop())
    log.info("Telegram bridge starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
