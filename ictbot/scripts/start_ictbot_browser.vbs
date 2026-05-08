' Launch a dedicated Chromium for ICTBot on CDP :9223 pointed at TradingView Web.
'
' First-run setup (one-time, manual):
'   1. Run this VBS — Chromium opens with a fresh profile in C:\ZachAI\ictbot\state\chrome_profile\
'   2. Log into TradingView
'   3. Open chart, set symbol to MES1!, timeframe 5m, save layout
'   4. Close Chromium
' From then on this VBS auto-relaunches with the saved profile.
'
' This file launches the system Chrome (not the TradingView Desktop app — that
' belongs to ORB on :9222).

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

profileDir = "C:\ZachAI\ictbot\state\chrome_profile"
If Not fso.FolderExists(profileDir) Then
    fso.CreateFolder(profileDir)
End If

' Find Chrome executable. Try standard locations.
chromeCandidates = Array( _
    "C:\Program Files\Google\Chrome\Application\chrome.exe", _
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" _
)
chromeExe = ""
For Each c In chromeCandidates
    If fso.FileExists(c) Then
        chromeExe = c
        Exit For
    End If
Next

If chromeExe = "" Then
    WScript.Echo "Chrome not found. Install Google Chrome or set chromeExe manually."
    WScript.Quit 1
End If

' Compose the command.
' --remote-debugging-port    → expose CDP for ICTBot's ict_tv_client
' --user-data-dir            → isolate from any system Chrome profile
' --no-first-run             → skip welcome flow
' --new-window               → ensure a window opens
cmd = """" & chromeExe & """" & _
      " --remote-debugging-port=9223" & _
      " --user-data-dir=""" & profileDir & """" & _
      " --no-first-run --no-default-browser-check" & _
      " --new-window https://www.tradingview.com/chart/?symbol=CME_MINI%3AMES1!"

WshShell.Run cmd, 1, False

Set WshShell = Nothing
Set fso = Nothing
