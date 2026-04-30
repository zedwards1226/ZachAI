@echo off
REM Live tasks only. PaperTrader_Daily_Start removed 2026-04-29 — legacy
REM paper-trade pipeline retired 2026-04-17 (PaperTrader.vbs is gone).
schtasks /create /tn "ORB_Daily_Start" /tr "wscript.exe \"C:\Users\zedwa\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ORBAgents.vbs\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:00 /f
schtasks /create /tn "CloudflareTunnel_Daily_Start" /tr "wscript.exe \"C:\Users\zedwa\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\CloudflareTunnel.vbs\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:00 /f
schtasks /create /tn "WeatherAlpha_6AM" /tr "wscript.exe \"C:\ZachAI\scripts\WeatherAlpha_Bot.vbs\"" /sc DAILY /st 06:00 /f
echo Done. Three tasks scheduled for 6:00 AM.
pause
