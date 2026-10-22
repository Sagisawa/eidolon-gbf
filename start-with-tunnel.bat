@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-with-tunnel.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Launcher exited with code: %errorlevel%
    pause
)
