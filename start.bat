@echo off
title LSOYS AI Monitoring Platform

echo.
echo ============================================================
echo   LSOYS AI Classroom Monitoring System
echo ============================================================
echo.

REM Kill any existing process using port 8000
echo [1/4] Clearing port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM Activate virtual environment
echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

REM Apply any pending migrations
echo [3/4] Applying migrations...
venv\Scripts\python manage.py migrate --settings=config.settings.development --run-syncdb 2>&1

echo.
echo [4/4] Starting server...
echo.
echo  Choose server mode:
echo    1) Standard runserver (no WebSockets - simpler)
echo    2) Daphne ASGI      (full WebSockets - recommended)
echo.
set /p choice="Enter 1 or 2 (default=2): "

if "%choice%"=="1" (
    echo.
    echo Starting Django development server on http://127.0.0.1:8000
    echo Press Ctrl+C to stop.
    echo.
    venv\Scripts\python manage.py runserver 8000 --settings=config.settings.development
) else (
    echo.
    echo Starting Daphne ASGI server on http://127.0.0.1:8000
    echo WebSockets: ENABLED ^(Attention Monitor live updates, Notification feed^)
    echo Press Ctrl+C to stop.
    echo.
    venv\Scripts\daphne -b 127.0.0.1 -p 8000 config.asgi:application
)
