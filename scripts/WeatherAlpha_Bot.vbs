Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

' Check if app.py is already running
Dim isRunning
isRunning = False

Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "app.py") > 0 Then
        isRunning = True
    End If
Next

' Only launch if not already running — preserves healthy state
If Not isRunning Then
    WshShell.Run "pythonw.exe C:\ZachAI\kalshi\bots\app.py", 0, False
End If
