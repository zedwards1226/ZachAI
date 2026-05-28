@echo off
REM ─── LongshotFade bot launcher (manual, foreground) ───
REM
REM Two terminals required during paper testing:
REM   1) This window — the bot itself (scans Kalshi every 60s)
REM   2) `run_dashboard.bat` — the Flask dashboard on :8503
REM
REM Why no VBS auto-start: per Phase 3 plan, paper window is manual-launch
REM only. We add auto-start (`scripts/LongshotFade.vbs`) AFTER Zach approves
REM the live promotion gate at Day 18.

cd /d C:\ZachAI\omnialpha

REM Ensure DB schema exists before scheduler boots
C:\Python314\python.exe -c "from data_layer.database import init_db; init_db(); print('DB initialized')"

REM Launch the bot
C:\Python314\python.exe main_longshot.py
