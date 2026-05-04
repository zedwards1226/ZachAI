Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

' Avoid double-launch: only start if no python is already running serve.py
' for the omnialpha dashboard.
Dim isRunning
isRunning = False
Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "omnialpha\dashboard\backend\serve.py") > 0 Then
        isRunning = True
    End If
Next

If Not isRunning Then
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\omnialpha\dashboard\backend\serve.py", 0, False
End If
