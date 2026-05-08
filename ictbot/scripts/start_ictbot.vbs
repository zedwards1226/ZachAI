' ICTBot auto-start launcher.
' - cd to ictbot/
' - git pull (best-effort, non-fatal)
' - python -m main
' - run hidden (no console window)

Set WshShell = CreateObject("WScript.Shell")
projectDir = "C:\ZachAI\ictbot"
WshShell.CurrentDirectory = projectDir

' Best-effort git pull (silent, ignore errors)
WshShell.Run "cmd /c git pull --rebase --autostash 2> logs\git_pull_err.log", 0, True

' Launch the bot (hidden, do not wait).
' Do NOT redirect to logs\ictbot.log — main.py's FileHandler owns that file
' and Windows can't share the handle. Send stdout/stderr to stdout.log instead.
WshShell.Run "cmd /c python -m main >> logs\stdout.log 2>&1", 0, False

Set WshShell = Nothing
