Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

Dim isRunning
isRunning = False
Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    ' Match C:\ZachAI\scripts\watchdog.py but NOT orb_watchdog.py
    If InStr(LCase(proc.CommandLine), "scripts\watchdog.py") > 0 Then
        isRunning = True
    End If
Next

If Not isRunning Then
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\scripts\watchdog.py", 0, False
End If
