@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Faire.ps1"
echo.
echo Faire exit code: %errorlevel%
pause
