@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-services.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Stopper exited with code: %errorlevel%
    pause
)
