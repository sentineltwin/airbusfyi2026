@echo off
chcp 65001 >nul 2>&1
title SENTINELTWIN — STOP

echo.
echo   [>>] Stopping SentinelTwin...
echo.

REM Kill processes on port 8000 (backend)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /T /F >nul 2>&1
    echo   [OK] Stopped backend (PID %%a)
)

REM Kill processes on port 5173 (frontend)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /T /F >nul 2>&1
    echo   [OK] Stopped frontend (PID %%a)
)

REM Also kill by window title
taskkill /FI "WINDOWTITLE eq SENTINELTWIN BACKEND" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SENTINELTWIN FRONTEND" /T /F >nul 2>&1

echo.
echo   [OK] SentinelTwin stopped.
echo.
pause
