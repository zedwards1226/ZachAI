Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

' Check if app.py is already running (any Python variant)
Dim isRunning
isRunning = False

Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "app.py") > 0 Then
        isRunning = True
    End If
Next

' Only launch if not already running — use explicit Python314 path to avoid
' Windows Store Python shim spawning a duplicate process.
If Not isRunning Then
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\kalshi\bots\app.py", 0, False
End If
