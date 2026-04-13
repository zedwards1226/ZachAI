Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\ZachAI\telegram-bridge && pythonw bot.py >> bot.log 2>&1", 0, False
