@echo off
REM Live tasks only. Removed 2026-04-29:
REM   - PaperTrader_Daily_Start  (legacy paper-trade pipeline retired 2026-04-17)
REM   - CloudflareTunnel_Daily_Start  (cloudflared.exe missing; running local-only)
schtasks /create /tn "ORB_Daily_Start" /tr "wscript.exe \"C:\Users\zedwa\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ORBAgents.vbs\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:00 /f
schtasks /create /tn "WeatherAlpha_6AM" /tr "wscript.exe \"C:\ZachAI\scripts\WeatherAlpha_Bot.vbs\"" /sc DAILY /st 06:00 /f
echo Done. Two tasks scheduled for 6:00 AM.
pause
