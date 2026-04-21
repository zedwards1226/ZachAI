' Auto-start ORB Trading Watchdog on Windows boot.
' Drop a shortcut to this file in:
'   %AppData%\Microsoft\Windows\Start Menu\Programs\Startup\
' Dedupes: if orb_watchdog.py is already running, do nothing.
Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

Dim isRunning
isRunning = False
Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "orb_watchdog.py") > 0 Then
        isRunning = True
    End If
Next

If Not isRunning Then
    WshShell.CurrentDirectory = "C:\ZachAI\scripts"
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\scripts\orb_watchdog.py", 0, False
End If
