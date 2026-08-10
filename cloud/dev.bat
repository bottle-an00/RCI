@echo off
REM ===========================================================================
REM  RCI education platform - start all dev services (double-click me)
REM
REM  Starts broker (1883/8080) + mock RCI + FastAPI web (8123) in one window.
REM  A .ps1 opens in Notepad when double-clicked, so this wrapper calls
REM  PowerShell with -ExecutionPolicy Bypass instead.
REM
REM  Stop:  press Ctrl+C here.  If you closed the window with X, run stop.bat.
REM  Args:  dev.bat -Lan -NoMock       (passed straight through to dev.ps1)
REM
REM  KEEP THIS FILE ASCII-ONLY. cmd.exe parses batch files line by line in the
REM  console codepage; non-ASCII bytes get misread as commands and the script
REM  breaks. Korean user-facing text lives in scripts/dev.ps1 instead.
REM ===========================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

REM Prefer PowerShell 7 (pwsh); fall back to Windows PowerShell 5.1.
set "PS=pwsh"
where pwsh >nul 2>&1 || set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "scripts\dev.ps1" %*
set "CODE=%ERRORLEVEL%"

echo.
if not "%CODE%"=="0" echo [dev] exited with code %CODE% - see the messages above.
pause
endlocal
