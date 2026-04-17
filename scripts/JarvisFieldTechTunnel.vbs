Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "C:\ZachAI\cloudflared.exe tunnel --url http://localhost:5050", 0, False
