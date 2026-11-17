@echo off
title Cineva Media Hub
cd /d "%~dp0.."
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" /B pyw desktop\cineva_desktop.py
    exit /b 0
)
pythonw desktop\cineva_desktop.py 2>nul
if %ERRORLEVEL% NEQ 0 (
    python desktop\cineva_desktop.py
)
