Set WshShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

' Anti-double-launch: match the full main_longshot.py path so we never
' spawn a second bot instance (mirrors the WeatherAlpha_Bot.vbs pattern).
Dim isRunning
isRunning = False

Set colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each proc In colProcs
    If InStr(LCase(proc.CommandLine), "longshot\main_longshot.py") > 0 Then
        isRunning = True
    End If
Next

' Explicit Python314 path — avoids the Windows Store Python shim spawning
' a duplicate (per feedback_vbs_python_path.md). pythonw = no console window.
If Not isRunning Then
    WshShell.Run """C:\Python314\pythonw.exe"" C:\ZachAI\longshot\main_longshot.py", 0, False
End If
