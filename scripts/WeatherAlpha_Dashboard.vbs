Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

Dim isRunning
isRunning = False
Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    ' Match the FULL kalshi path so we don't collide with OmniAlpha's
    ' serve.py (same filename, different bot). Bug surfaced post-reboot
    ' on 2026-05-13: OA dashboard came up first, this VBS saw "serve.py"
    ' anywhere and skipped, leaving :3001 down until manual relaunch.
    If InStr(LCase(proc.CommandLine), "kalshi\dashboard\backend\serve.py") > 0 Then
        isRunning = True
    End If
Next

If Not isRunning Then
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\kalshi\dashboard\backend\serve.py", 0, False
End If
