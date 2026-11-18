@echo off
setlocal
cd /d "%~dp0"
title Add Saffron Courtyard to this workspace
if not exist ".venv\Scripts\python.exe" (
    echo Run Start-DineX.bat once to prepare this folder, then open this file again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m dinex demo
set "dinex_result=%errorlevel%"
pause
exit /b %dinex_result%

