# Jarvis Field Tech — Active Files

Files NOT in this list should not exist. Follow ZachAI file hygiene rules.

## Root
- `README.md` — project docs
- `ACTIVE_FILES.md` — this manifest
- `.env.example` — env var template (checked in)
- `.env` — real secrets (gitignored)
- `.gitignore`
- `requirements.txt` — Python deps

## backend/
- `app.py` — Flask server, port 5050, serves /api/* + static build
- `drive_client.py` — Google Drive OAuth + folder listing + file download
- `ai_client.py` — Gemini API wrapper (free tier — 2.0 Flash model)
- `pdf_extractor.py` — PDF text extraction for Claude context
- `machines.json` — auto-generated folder cache (gitignored)
- `token.json` — OAuth token cache (gitignored)
- `static/` — built frontend output (gitignored, created by `npm run build`)

## frontend/
- `package.json`, `vite.config.js`, `index.html`, `postcss.config.js`, `tailwind.config.js`
- `public/manifest.json` — PWA manifest
- `public/service-worker.js` — PWA installability
- `public/icon-192.png`, `public/icon-512.png` — PWA icons (placeholder)
- `src/main.jsx` — React entry
- `src/App.jsx` — top-level app
- `src/styles/hud.css` — arc reactor animations
- `src/styles/index.css` — tailwind + base
- `src/components/JarvisHUD.jsx` — arc reactor HUD
- `src/components/VoiceInput.jsx` — mic button + transcript
- `src/components/ChatLog.jsx` — Q&A scrollback
- `src/components/PDFViewer.jsx` — PDF.js drawing viewer
- `src/components/MachineList.jsx` — machine picker
- `src/hooks/useSpeech.js` — Web Speech API TTS + STT
- `src/hooks/useApi.js` — fetch wrapper
- `src/lib/docMatch.js` — fuzzy-match voice/text → Drive doc for "open X" intent

## Startup scripts (live in C:\ZachAI\scripts\, referenced here)
- `JarvisFieldTech.vbs` — starts `pythonw backend/app.py`
- `JarvisFieldTechTunnel.vbs` — starts `cloudflared` tunnel to :5050
