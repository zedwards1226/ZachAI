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

' Launch the bot (hidden, do not wait)
WshShell.Run "cmd /c python -m main >> logs\ictbot.log 2>&1", 0, False

Set WshShell = Nothing
