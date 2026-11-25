@echo off
title Mavie Media Hub
cd /d "%~dp0.."
if exist ".venv\Scripts\pythonw.exe" (
    start "" /B ".venv\Scripts\pythonw.exe" desktop\mavie_desktop.py
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" desktop\mavie_desktop.py
    exit /b %ERRORLEVEL%
)
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" /B pyw desktop\mavie_desktop.py
    exit /b 0
)
pythonw desktop\mavie_desktop.py 2>nul
if %ERRORLEVEL% NEQ 0 (
    python desktop\mavie_desktop.py
)
