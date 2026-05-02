Set WshShell = CreateObject("WScript.Shell")
' Pull latest code from GitHub before starting, then launch main.py
' Schema init + paper-mode guard live in main.py
WshShell.Run "cmd /c cd /d C:\ZachAI && git pull origin master 2>>omnialpha\logs\git_pull.log && cd omnialpha && python main.py >> logs\stdout.log 2>&1", 0, False
