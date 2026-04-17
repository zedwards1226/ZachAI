# Jarvis Field Tech

Mobile PWA that greets Zach with a Jarvis HUD + voice, pulls machine drawings/manuals from Google Drive, and helps troubleshoot industrial toilet paper converting machines.

## Quickstart

```bash
# Backend
cd backend
pip install -r ../requirements.txt
cp ../.env.example ../.env        # fill in keys
python app.py                     # serves on :5050

# Frontend (dev)
cd frontend
npm install
npm run dev                       # Vite dev server :5173, proxies /api -> :5050

# Frontend (prod) — build into backend/static/ and serve from Flask
cd frontend
npm run build                     # outputs to ../backend/static/
```

## Phone install (PWA)

1. Start backend: `pythonw backend/app.py` (or use `JarvisFieldTech.vbs` startup)
2. Start Cloudflare tunnel: `JarvisFieldTechTunnel.vbs`
3. Open tunnel URL on phone in Chrome → menu → "Add to Home Screen"
4. Tap the new app icon — Jarvis greets you

## Architecture

- **Backend** (`backend/app.py`): Flask on :5050 serving `/api/*` + static build
- **Frontend** (`frontend/`): React + Vite PWA with arc-reactor HUD + Web Speech API
- **Google Drive**: read-only OAuth, token cached in `backend/token.json`
- **Claude**: Opus 4.7 for troubleshooting, Haiku 4.5 for doc-name lookups

## Google Drive folder layout

Expected structure in your Drive:
```
Work/
└── Machine Docs/
    ├── Rewinder_Perini/
    │   ├── electrical/*.pdf
    │   └── manuals/*.pdf
    ├── LogSaw/
    │   ├── electrical/*.pdf
    │   └── manuals/*.pdf
    └── TailSealer/
        └── ...
```

Configure root folder ID in `.env` as `DRIVE_ROOT_FOLDER_ID`.

## Environment variables

See `.env.example`. Required:
- `ANTHROPIC_API_KEY` — Claude API key
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — OAuth creds (from Google Cloud Console)
- `DRIVE_ROOT_FOLDER_ID` — ID of your `Machine Docs` folder (from Drive URL)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — optional, for error notifications

## First-time Google Drive auth

Run once on desktop (browser opens):
```bash
python backend/drive_client.py --auth
```
Token saved to `backend/token.json` (gitignored). Auto-refreshes after.
