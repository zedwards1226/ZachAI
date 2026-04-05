"""
ZachAI Dashboard Backend
FastAPI server — REST + WebSocket, serves built React frontend.
Bind 0.0.0.0:3000 so phones on the same network can connect.
"""

import asyncio
import json
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATE_FILE  = Path("C:/ZachAI/data/state.json")
STATIC_DIR  = Path(__file__).parent / "static"

# ── Connected WebSocket clients ───────────────────────────────────────────────
_clients: set[WebSocket] = set()
_last_hash: int | None   = None


async def _watch_and_broadcast():
    """Poll state.json every 2 s; broadcast to all WS clients on change."""
    global _last_hash
    while True:
        await asyncio.sleep(2)
        try:
            text = STATE_FILE.read_text(encoding="utf-8") if STATE_FILE.exists() else "{}"
            h    = hash(text)
            if h != _last_hash:
                _last_hash = h
                dead = set()
                for ws in list(_clients):
                    try:
                        await ws.send_text(text)
                    except Exception:
                        dead.add(ws)
                _clients -= dead
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_watch_and_broadcast())
    yield


app = FastAPI(title="ZachAI Dashboard", lifespan=lifespan)


# ── REST ──────────────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"tasks": [], "messages": [], "approvals": []}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)

    # Push current state immediately on connect
    try:
        text = STATE_FILE.read_text(encoding="utf-8") if STATE_FILE.exists() else "{}"
        await ws.send_text(text)
    except Exception:
        pass

    try:
        while True:
            await ws.receive_text()   # keep-alive; client may send pings
    except WebSocketDisconnect:
        _clients.discard(ws)
    except Exception:
        _clients.discard(ws)


# ── Static React build ────────────────────────────────────────────────────────

if STATIC_DIR.exists():
    # SPA fallback: serve index.html for any unmatched route
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = STATIC_DIR / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(STATIC_DIR / "index.html"))

    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "?.?.?.?"

    print("\n" + "=" * 50)
    print("  ZachAI Dashboard")
    print(f"  Local  -> http://localhost:3000")
    print(f"  Phone  -> http://{local_ip}:3000")
    print("=" * 50 + "\n")

    uvicorn.run("server:app", host="0.0.0.0", port=3000, reload=False)
