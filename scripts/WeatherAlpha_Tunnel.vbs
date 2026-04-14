Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "C:\ZachAI\cloudflared.exe tunnel --url http://localhost:3001", 0, False
