@echo off
REM ─── LongshotFade dashboard launcher (manual, foreground) ───
REM
REM Open this window alongside the bot. Then visit http://localhost:8503
REM in any browser to see the mission-control view.
REM
REM The dashboard is read-only against the bot's SQLite journal — running
REM it without the bot is safe (you'll just see empty panels).

cd /d C:\ZachAI\longshot\dashboard

C:\Python314\python.exe serve.py
