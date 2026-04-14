@echo off
schtasks /create /tn "ORB_Daily_Start" /tr "wscript.exe \"C:\Users\zedwa\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ORBAgents.vbs\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:00 /f
schtasks /create /tn "PaperTrader_Daily_Start" /tr "wscript.exe \"C:\Users\zedwa\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\PaperTrader.vbs\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:00 /f
schtasks /create /tn "CloudflareTunnel_Daily_Start" /tr "wscript.exe \"C:\Users\zedwa\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\CloudflareTunnel.vbs\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:00 /f
schtasks /create /tn "WeatherAlpha_6AM" /tr "wscript.exe \"C:\ZachAI\scripts\WeatherAlpha_Bot.vbs\"" /sc DAILY /st 06:00 /f
echo Done. All four tasks scheduled for 6:00 AM.
pause
