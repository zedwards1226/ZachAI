Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /k cd /d C:\ZachAI && claude --channels plugin:telegram@claude-plugins-official --dangerously-skip-permissions", 1, False
