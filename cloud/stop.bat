@echo off
REM ===========================================================================
REM  RCI education platform - stop all dev services (double-click me)
REM
REM  If you stopped dev.bat with Ctrl+C it already cleaned up. Use this when
REM  the window was closed with X and python.exe processes were orphaned, or
REM  when a port is still taken and dev.bat refuses to start.
REM
REM  Covers the broker ports (1883 / 8080) plus every web port declared in
REM  .claude/launch.json (8123 / 8129 / 8130). Also sweeps uvicorn --reload
REM  workers, which have no recognizable command line and used to pile up as
REM  orphans holding a port open.
REM
REM  Only this project's services are killed (matched by command line/lineage).
REM  Args:  stop.bat -WhatIf       show what would be killed, kill nothing
REM         stop.bat -Force        also kill non-matching port holders (careful)
REM         stop.bat -KeepOrphans  leave abandoned spawn workers alone
REM
REM  KEEP THIS FILE ASCII-ONLY - see the note in dev.bat.
REM ===========================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PS=pwsh"
where pwsh >nul 2>&1 || set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "scripts\stop.ps1" %*

echo.
pause
endlocal
