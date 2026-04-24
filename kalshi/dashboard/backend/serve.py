"""
Lightweight static file server for WeatherAlpha dashboard.
Proxies /api/* to the Flask bot backend on port 5000.
Serves React build from ./static/.
Phone-accessible on port 3001.
"""
import socket
import sys
import os
from pathlib import Path
import urllib.request
import urllib.error

# Pull INTERNAL_API_SECRET from the bot's config so proxy + API share one value.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bots"))
from config import INTERNAL_API_SECRET  # noqa: E402

from flask import Flask, send_from_directory, request, Response
from flask_cors import CORS

STATIC_DIR  = Path(__file__).parent / "static"
BOT_API_URL = "http://127.0.0.1:5000"
SERVE_PORT  = 3001

app = Flask(__name__, static_folder=None)
CORS(app, origins=["http://localhost:3001", "http://127.0.0.1:3001"])


@app.route("/api/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy_api(subpath):
    """Proxy all /api/* requests to the bot Flask server."""
    url  = f"{BOT_API_URL}/api/{subpath}"
    qs   = request.query_string.decode()
    if qs:
        url += f"?{qs}"
    try:
        body    = request.get_data() or None
        headers = {k: v for k, v in request.headers if k != "Host"}
        # Inject shared secret server-side so the browser never sees it.
        # Strip any client-supplied value first — clients can't grant themselves access.
        headers.pop("X-Internal-Secret", None)
        headers.pop("x-internal-secret", None)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            headers["X-Internal-Secret"] = INTERNAL_API_SECRET
        req     = urllib.request.Request(url, data=body, headers=headers, method=request.method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return Response(resp.read(), status=resp.status,
                            content_type=resp.headers.get("Content-Type", "application/json"))
    except urllib.error.HTTPError as e:
        return Response(e.read(), status=e.code, content_type="application/json")
    except Exception as exc:
        return Response(f'{{"error": "{exc}"}}', status=502, content_type="application/json")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    if path and (STATIC_DIR / path).exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


if __name__ == "__main__":
    if not STATIC_DIR.exists():
        print(f"ERROR: {STATIC_DIR} not found. Run 'npm run build' in frontend/ first.")
        sys.exit(1)

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "?.?.?.?"

    print("\n" + "=" * 55)
    print("  WeatherAlpha Dashboard")
    print(f"  Local  -> http://localhost:{SERVE_PORT}")
    print(f"  Phone  -> http://{local_ip}:{SERVE_PORT}")
    print(f"  Bot API-> http://localhost:5000")
    print("=" * 55 + "\n")
    app.run(host="0.0.0.0", port=SERVE_PORT, debug=False)
