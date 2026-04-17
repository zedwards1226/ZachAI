' Auto-start ORB Trading Watchdog on Windows boot.
' Drop a shortcut to this file in:
'   %AppData%\Microsoft\Windows\Start Menu\Programs\Startup\
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\ZachAI\scripts"
WshShell.Run "pythonw C:\ZachAI\scripts\orb_watchdog.py", 0, False
