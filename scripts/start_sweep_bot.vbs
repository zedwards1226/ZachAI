Set WshShell = CreateObject("WScript.Shell")
' Silent launcher for sweep-bot. Runs alongside ORB in a separate process.
WshShell.Run "cmd /c cd /d C:\ZachAI\sweep-bot && python main.py >> logs\sweep_bot.log 2>&1", 0, False
