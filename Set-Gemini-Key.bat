@echo off
setlocal
cd /d "%~dp0"
title Save your Gemini API key
if not exist ".venv\Scripts\python.exe" (
    echo Run Start-DineX.bat once to prepare this folder, then open this file again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m dinex set-gemini
set "dinex_result=%errorlevel%"
pause
exit /b %dinex_result%

