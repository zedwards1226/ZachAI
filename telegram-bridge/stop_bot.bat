@echo off
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq telegram-bridge*" >nul 2>&1
wmic process where "commandline like '%%telegram-bridge%%bot.py%%'" delete >nul 2>&1
echo Bot stopped.
