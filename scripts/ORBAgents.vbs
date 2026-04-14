Set WshShell = CreateObject("WScript.Shell")
' Pull latest code from GitHub before starting, then launch main.py
' PID lock in main.py ensures only one instance runs at a time
WshShell.Run "cmd /c cd /d C:\ZachAI && git pull origin master 2>>trading\logs\git_pull.log && cd trading && python main.py >> logs\agents.log 2>&1", 0, False
