Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\ZachAI\telegram-bridge && pythonw chat_bot.py >> chat_bot.log 2>&1", 0, False
