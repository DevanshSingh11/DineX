@echo off
setlocal
cd /d "%~dp0"

echo.
echo  DineX Universal
echo  Finding this PC's local network address...
echo.

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Find-DineX-IP.ps1"`) do set "DINEX_LAN_IP=%%I"

if not defined DINEX_LAN_IP (
    echo Could not find an active Wi-Fi or Ethernet IPv4 address.
    echo Connect this PC to your network and try again.
    echo You can see its IPv4 address by running ipconfig in PowerShell.
    echo.
    pause
    exit /b 1
)

set "DINEX_PUBLIC_URL=http://%DINEX_LAN_IP%:8000"
echo This address will be used for the browser and table QR codes:
echo %DINEX_PUBLIC_URL%
echo.

py -3.14 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.14 was not found by the Windows launcher.
    echo Install Python 3.14, reopen this window, then start DineX again.
    echo Download: https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the private DineX Python environment...
    py -3.14 -m venv .venv
    if errorlevel 1 goto failed
)

echo Checking DineX dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Preparing the DineX database...
".venv\Scripts\python.exe" -m dinex init
if errorlevel 1 goto failed

echo.
echo If this is your first run, create the platform administrator below.
".venv\Scripts\python.exe" -m dinex bootstrap
if errorlevel 1 goto failed

".venv\Scripts\python.exe" -m dinex demo --if-empty
if errorlevel 1 goto failed

echo.
echo DineX is available to this network at:
echo %DINEX_PUBLIC_URL%
echo Keep this window open while using DineX.
echo Windows Firewall may ask to allow Python on private networks.
echo Press Ctrl+C to stop the server.
echo.
start "" "%DINEX_PUBLIC_URL%"
".venv\Scripts\python.exe" -m dinex serve --host 0.0.0.0 --port 8000
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo DineX could not start. Read the error above and check README.md.
pause
exit /b 1
