Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\ZachAI\trading && python main.py >> logs\agents.log 2>&1", 0, False
