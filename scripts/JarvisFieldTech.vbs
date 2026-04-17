Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\ZachAI\jarvis-field-tech\backend && pythonw app.py", 0, False
