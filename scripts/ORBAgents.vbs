Set WshShell = CreateObject("WScript.Shell")
' Pull latest code from GitHub before starting, then launch main.py
' PID lock in main.py ensures only one instance runs at a time
' Use full Python314 path to avoid Microsoft Store Python shim and silent failures
' under SYSTEM/cmd.exe spawn contexts (per memory feedback_vbs_python_path.md).
WshShell.Run "cmd /c cd /d C:\ZachAI && git pull origin master 2>>trading\logs\git_pull.log && cd trading && C:\Python314\python.exe main.py >> logs\agents.log 2>&1", 0, False
