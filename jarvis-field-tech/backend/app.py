"""
Jarvis Field Tech backend.
Flask on :5050 serving /api/* + built React frontend from ./static/.
"""
import os
import sys
import socket
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory, Response
from flask_cors import CORS

BASE = Path(__file__).parent
load_dotenv(BASE.parent / ".env")

# Lazy imports so /api/health works even if OAuth / API keys not set yet
import drive_client
import claude_client
import pdf_extractor

STATIC_DIR = BASE / "static"
PORT = int(os.getenv("JARVIS_PORT", "5050"))

app = Flask(__name__, static_folder=None)
CORS(app)


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "service": "jarvis-field-tech"})


@app.route("/api/greet")
def greet():
    try:
        return jsonify({"text": claude_client.greeting()})
    except Exception as exc:
        return jsonify({"text": f"Systems online, Zach. What are we troubleshooting? ({exc})"})


@app.route("/api/machines")
def machines():
    refresh = request.args.get("refresh") == "1"
    try:
        tree = drive_client.refresh_cache() if refresh else drive_client.load_cache()
        return jsonify({"machines": tree})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/drawing/<file_id>")
def drawing(file_id):
    try:
        data = drive_client.download_file(file_id)
        mime = request.args.get("mime", "application/pdf")
        return Response(data, mimetype=mime, headers={
            "Content-Disposition": f'inline; filename="{file_id}.pdf"',
            "Cache-Control": "private, max-age=300",
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/ask", methods=["POST"])
def ask():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400

    machine = payload.get("machine") or ""
    doc_id = payload.get("doc_id") or ""
    history = payload.get("history") or []

    context = ""
    if doc_id:
        try:
            pdf_bytes = drive_client.download_file(doc_id)
            context = pdf_extractor.extract_text(pdf_bytes, max_chars=40_000)
        except Exception as exc:
            context = f"(Could not load doc: {exc})"

    try:
        result = claude_client.ask(question, context=context, machine=machine, history=history)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- Static frontend (built by `npm run build` into ./static/) -----------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    if not STATIC_DIR.exists():
        return (
            "<h1>Jarvis Field Tech</h1>"
            "<p>Frontend not built yet. Run <code>npm run build</code> in frontend/.</p>"
        ), 200
    if path and (STATIC_DIR / path).exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "?.?.?.?"
    print("\n" + "=" * 55)
    print("  Jarvis Field Tech")
    print(f"  Local  -> http://localhost:{PORT}")
    print(f"  Phone  -> http://{local_ip}:{PORT}")
    print("=" * 55 + "\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
