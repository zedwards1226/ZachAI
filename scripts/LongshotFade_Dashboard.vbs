Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

' Anti-double-launch: match the full dashboard serve.py path. longshot's
' serve.py is distinct from the ORB/WA dashboards' serve.py, so match the
' full path (same class of bug WeatherAlpha_Dashboard.vbs hit on 2026-05-13).
Dim isRunning
isRunning = False

Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "longshot\dashboard\serve.py") > 0 Then
        isRunning = True
    End If
Next

If Not isRunning Then
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\longshot\dashboard\serve.py", 0, False
End If
