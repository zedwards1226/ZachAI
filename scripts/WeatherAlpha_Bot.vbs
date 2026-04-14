Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

' Kill any existing app.py instance before launching fresh
Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "app.py") > 0 Then
        proc.Terminate()
    End If
Next

' Short pause to let old process die
WScript.Sleep 2000

' Launch fresh instance silently
WshShell.Run "pythonw.exe C:\ZachAI\kalshi\bots\app.py", 0, False
