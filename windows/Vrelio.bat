@echo off
title Vrelio Media Hub
cd /d "%~dp0.."
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" /B pyw desktop\vrelio_desktop.py
    exit /b 0
)
pythonw desktop\vrelio_desktop.py 2>nul
if %ERRORLEVEL% NEQ 0 (
    python desktop\vrelio_desktop.py
)
