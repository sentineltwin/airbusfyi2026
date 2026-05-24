@echo off
REM ═══════════════════════════════════════════════════════════════
REM SENTINELTWIN — Windows Shutdown Script
REM Stops all SentinelTwin services (Docker + Local processes)
REM ═══════════════════════════════════════════════════════════════

setlocal EnableDelayedExpansion
title SENTINELTWIN — Shutdown

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                                                              ║
echo  ║    SENTINELTWIN — Graceful Shutdown                         ║
echo  ║                                                              ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_ROOT=%~dp0"
set "STOPPED_SOMETHING=0"

REM ── 1. Stop Docker containers (if Docker is available) ──────
echo  [1/3] Checking for Docker containers...
where docker >nul 2>&1
if not errorlevel 1 (
    docker info >nul 2>&1
    if not errorlevel 1 (
        REM Check if any sentineltwin containers are running
        docker compose -f "%PROJECT_ROOT%docker-compose.yml" ps -q 2>nul | findstr /r "." >nul 2>&1
        if not errorlevel 1 (
            echo         Stopping Docker containers...
            docker compose -f "%PROJECT_ROOT%docker-compose.yml" down
            if not errorlevel 1 (
                echo         OK: All Docker containers stopped
                set "STOPPED_SOMETHING=1"
            ) else (
                echo         WARNING: Some containers may not have stopped cleanly
            )
        ) else (
            echo         No Docker containers running
        )
    ) else (
        echo         Docker Desktop not running — skipping
    )
) else (
    echo         Docker not installed — skipping
)

REM ── 2. Stop local backend process (Python/Uvicorn) ──────────
echo.
echo  [2/3] Checking for local backend process...

REM Kill any Python processes running main.py (SentinelTwin backend)
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq SENTINELTWIN Backend" /FO LIST 2^>nul ^| findstr "PID:"') do (
    echo         Stopping backend (PID: %%a)...
    taskkill /PID %%a /T /F >nul 2>&1
    set "STOPPED_SOMETHING=1"
)

REM Also check for any uvicorn process bound to port 8000
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":8000 "') do (
    echo         Stopping process on port 8000 (PID: %%a)...
    taskkill /PID %%a /T /F >nul 2>&1
    set "STOPPED_SOMETHING=1"
)
echo         OK: Backend stopped

REM ── 3. Stop local frontend process (Vite/Node) ─────────────
echo.
echo  [3/3] Checking for local frontend process...

REM Kill any Node processes running the SentinelTwin frontend
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq SENTINELTWIN Frontend" /FO LIST 2^>nul ^| findstr "PID:"') do (
    echo         Stopping frontend (PID: %%a)...
    taskkill /PID %%a /T /F >nul 2>&1
    set "STOPPED_SOMETHING=1"
)

REM Also check for any process bound to port 5173 (Vite dev)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":5173 "') do (
    echo         Stopping process on port 5173 (PID: %%a)...
    taskkill /PID %%a /T /F >nul 2>&1
    set "STOPPED_SOMETHING=1"
)
echo         OK: Frontend stopped

REM ── Summary ─────────────────────────────────────────────────
echo.
if "!STOPPED_SOMETHING!"=="1" (
    echo  ╔══════════════════════════════════════════════════════════════╗
    echo  ║                                                              ║
    echo  ║    SENTINELTWIN — All services stopped successfully         ║
    echo  ║                                                              ║
    echo  ║    To restart: start.bat                                    ║
    echo  ║    To restart Docker only: start.bat --docker               ║
    echo  ║    To restart local only:  start.bat --local                ║
    echo  ║                                                              ║
    echo  ╚══════════════════════════════════════════════════════════════╝
) else (
    echo  ╔══════════════════════════════════════════════════════════════╗
    echo  ║                                                              ║
    echo  ║    SENTINELTWIN — No running services found                 ║
    echo  ║                                                              ║
    echo  ║    The platform does not appear to be running.              ║
    echo  ║    To start: start.bat                                      ║
    echo  ║                                                              ║
    echo  ╚══════════════════════════════════════════════════════════════╝
)
echo.
pause
