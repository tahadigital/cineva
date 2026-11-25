@echo off
setlocal
title Mavie Media Hub
cd /d "%~dp0.."

rem Usage:
rem   Mavie.bat            -> Launch native Mavie desktop application window
rem   Mavie.bat --web      -> Start local server and open Mavie in default web browser
rem   Mavie.bat --serve    -> Run headless Mavie web server in this console (LAN / Smart TV)

set "MAVIE_USE_CONSOLE=0"
for %%A in (%*) do (
    if /I "%%~A"=="--serve" set "MAVIE_USE_CONSOLE=1"
)

if "%MAVIE_USE_CONSOLE%"=="1" (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" desktop\mavie_desktop.py %*
        exit /b %ERRORLEVEL%
    )
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        py desktop\mavie_desktop.py %*
        exit /b %ERRORLEVEL%
    )
    python desktop\mavie_desktop.py %*
    exit /b %ERRORLEVEL%
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" /B ".venv\Scripts\pythonw.exe" desktop\mavie_desktop.py %*
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" desktop\mavie_desktop.py %*
    exit /b %ERRORLEVEL%
)
where pyw >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" /B pyw desktop\mavie_desktop.py %*
    exit /b 0
)
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py desktop\mavie_desktop.py %*
    exit /b %ERRORLEVEL%
)
pythonw desktop\mavie_desktop.py %* 2>nul
if %ERRORLEVEL% NEQ 0 (
    python desktop\mavie_desktop.py %*
)
