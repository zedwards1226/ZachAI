Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\ZachAI\telegram-bridge && pythonw bot.py", 0, False
