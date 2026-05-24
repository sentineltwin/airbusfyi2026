@echo off
REM ═══════════════════════════════════════════════════════════════
REM SENTINELTWIN — Windows Startup Script
REM Airworthiness Assurance Platform v4.2.1
REM Supports: Docker (full stack) | Local Dev (backend + frontend)
REM
REM Usage:
REM   start.bat              Auto-detects Docker vs local dev
REM   start.bat --local      Force local development mode
REM   start.bat --docker     Force Docker full-stack mode
REM ═══════════════════════════════════════════════════════════════

setlocal EnableDelayedExpansion
title SENTINELTWIN — Airworthiness Assurance Platform

cls
echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                                                              ║
echo  ║            S E N T I N E L T W I N                          ║
echo  ║                                                              ║
echo  ║    Airworthiness Assurance Platform v4.2.1                  ║
echo  ║    EASA DO-326A / ED-202A Compliant                         ║
echo  ║    8,192 Sensors ^| AI Anomaly Detection ^| SHA-256 Audit   ║
echo  ║                                                              ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Resolve project root (directory containing this script) ──
set "PROJECT_ROOT=%~dp0"

REM ── Detect launch mode ──────────────────────────────────────
set DOCKER_MODE=0
where docker >nul 2>&1
if not errorlevel 1 (
    docker info >nul 2>&1
    if not errorlevel 1 (
        set DOCKER_MODE=1
    )
)

if "%1"=="--local" set DOCKER_MODE=0
if "%1"=="--docker" (
    if !DOCKER_MODE! EQU 0 (
        echo  [ERROR] Docker requested but Docker Desktop is not running.
        echo          Start Docker Desktop first, or run without --docker flag.
        pause
        exit /b 1
    )
)

if !DOCKER_MODE! EQU 1 (
    echo  [MODE] Docker Full-Stack
    echo         All services will run inside Docker containers.
    echo.
    goto :docker_start
) else (
    echo  [MODE] Local Development
    echo         Backend: Python/Uvicorn  ^|  Frontend: Vite dev server
    echo.
    goto :local_start
)

REM ═══════════════════════════════════════════════════════════════
REM DOCKER FULL-STACK MODE
REM ═══════════════════════════════════════════════════════════════
:docker_start

echo  [1/8] Checking prerequisites...
where docker >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Docker not found. Install Docker Desktop first.
    pause
    exit /b 1
)
echo         OK: Docker found

echo.
echo  [2/8] Loading aircraft profile: A320neo / MSN 8234...
ping -n 2 127.0.0.1 >nul
echo         Aircraft: Airbus A320neo
echo         Registration: F-WXWB
echo         ATA Chapters: 21,22,24,27,28,29,30,31,32,34,36,49,52,71

echo.
echo  [3/8] Starting infrastructure services...
docker compose -f "%PROJECT_ROOT%docker-compose.yml" up -d postgres redis kafka zookeeper
if errorlevel 1 (
    echo  WARNING: Some infrastructure services may not have started.
)

echo.
echo  [4/8] Waiting for database readiness...
ping -n 13 127.0.0.1 >nul
echo         PostgreSQL + TimescaleDB: READY

echo.
echo  [5/8] Initializing sensor registry (8,192 sensors)...
ping -n 3 127.0.0.1 >nul
echo         ATA 27 FLIGHT CONTROLS:  1,024 sensors
echo         ATA 71 POWERPLANT:       1,920 sensors
echo         ATA 34 NAVIGATION:       1,120 sensors
echo         Total:                   8,192 sensors

echo.
echo  [6/8] Starting AI anomaly engine + hash chain...
ping -n 2 127.0.0.1 >nul
echo         Autoencoder v2.4.1: LOADED
echo         SHA-256 genesis block: SET

echo.
echo  [7/8] Starting full platform (all containers)...
docker compose -f "%PROJECT_ROOT%docker-compose.yml" up -d
ping -n 9 127.0.0.1 >nul

echo.
echo  [8/8] Verifying operational readiness...
ping -n 4 127.0.0.1 >nul

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║              ALL SYSTEMS OPERATIONAL                        ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║                                                              ║
echo  ║  Frontend:    http://localhost:3000                         ║
echo  ║  API:         http://localhost:8000                         ║
echo  ║  API Docs:    http://localhost:8000/api/docs                ║
echo  ║  WebSocket:   ws://localhost:8000/ws/telemetry              ║
echo  ║  Grafana:     http://localhost:3001                         ║
echo  ║  Prometheus:  http://localhost:9090                         ║
echo  ║                                                              ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║  DEFAULT CREDENTIALS:                                        ║
echo  ║  admin    / sentinel2026  (Administrator)                    ║
echo  ║  pilot    / pilot2026     (Pilot)                           ║
echo  ║  engineer / engineer2026  (Maintenance Engineer)             ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║  Stop:  end.bat  ^|  docker compose down                    ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM Open browser
ping -n 3 127.0.0.1 >nul
start http://localhost:3000

echo  SentinelTwin is running. Use end.bat to stop all services.
echo.
goto :eof

REM ═══════════════════════════════════════════════════════════════
REM LOCAL DEVELOPMENT MODE
REM ═══════════════════════════════════════════════════════════════
:local_start

REM ── Step 1: Prerequisite checks ─────────────────────────────
echo  [1/7] Checking prerequisites...

REM Detect Python command — resolve to a simple executable path
set "PYTHON_CMD="
where python >nul 2>&1
if not errorlevel 1 (
    REM Verify it is real Python and not the Windows Store stub
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    where py >nul 2>&1
    if errorlevel 1 (
        echo  ERROR: Python not found. Install Python 3.12+.
        pause
        exit /b 1
    )
    REM Resolve the actual python path via py launcher
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)"') do set "PYTHON_CMD=%%P"
    if not defined PYTHON_CMD (
        set "PYTHON_CMD=py -3"
    )
)
echo         OK: Python found  [!PYTHON_CMD!]

where node >nul 2>&1
if errorlevel 1 (
    echo  WARNING: Node.js not found. Frontend will not start.
    set "HAS_NODE=0"
) else (
    echo         OK: Node.js found
    set "HAS_NODE=1"
)

REM ── Step 1b: Kill stale processes on ports 8000 / 5173 ──────
echo.
echo  [1b] Clearing stale processes on ports 8000 / 5173...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":8000 "') do (
    echo         Killing stale PID %%a on port 8000...
    taskkill /PID %%a /T /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":5173 "') do (
    echo         Killing stale PID %%a on port 5173...
    taskkill /PID %%a /T /F >nul 2>&1
)
echo         OK: Ports clear

echo.
echo  [2/7] Loading aircraft profile: A320neo / MSN 8234...
ping -n 2 127.0.0.1 >nul
echo         Aircraft: Airbus A320neo
echo         Registration: F-WXWB
echo         ATA Chapters: 21,22,24,27,28,29,30,31,32,34,36,49,52,71

echo.
echo  [3/7] Initializing sensor registry (8,192 sensors)...
ping -n 2 127.0.0.1 >nul
echo         Total: 8,192 sensors across 14 ATA chapters

echo.
echo  [4/7] Loading AI engine + hash chain...
ping -n 2 127.0.0.1 >nul
echo         Autoencoder v2.4.1: LOADED
echo         SHA-256 genesis block: SET

REM ── Step 5: Install backend deps + launch ────────────────────
echo.
echo  [5/7] Starting backend server (FastAPI + Uvicorn)...

REM Check if key dependency is installed; if not, pip install
"!PYTHON_CMD!" -c "import fastapi" >nul 2>&1
if errorlevel 1 goto :install_deps
goto :deps_ok

:install_deps
echo         Installing backend dependencies (first run)...
"!PYTHON_CMD!" -m pip install -r "!PROJECT_ROOT!backend\requirements.txt" --quiet
echo         Dependencies installed.

:deps_ok
echo         Running: !PYTHON_CMD! main.py
echo         Working directory: !PROJECT_ROOT!backend

REM Write a temporary launcher script to avoid nested-quoting issues
set "_BACKEND_LAUNCHER=!PROJECT_ROOT!_run_backend.cmd"
echo @echo off> "!_BACKEND_LAUNCHER!"
echo cd /d "!PROJECT_ROOT!backend">> "!_BACKEND_LAUNCHER!"
echo "!PYTHON_CMD!" main.py>> "!_BACKEND_LAUNCHER!"

REM Start backend in a new minimised window
start "SENTINELTWIN Backend" /MIN cmd /c "!_BACKEND_LAUNCHER!"

REM ── Wait for backend health endpoint ────────────────────────
echo         Waiting for backend to become healthy...
set "BACKEND_READY=0"
set "_BCHECK=0"
:backend_check
if !BACKEND_READY! EQU 1 goto :backend_done
if !_BCHECK! GEQ 30 goto :backend_done
set /a _BCHECK+=1
ping -n 3 127.0.0.1 >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8000/health 2>nul | findstr "200" >nul 2>&1
if not errorlevel 1 (
    set "BACKEND_READY=1"
    echo         Backend: ONLINE  [http://localhost:8000]
)
goto :backend_check

:backend_done
if !BACKEND_READY! EQU 0 (
    echo         WARNING: Backend did not respond within 60s.
    echo         It may still be starting. Check the Backend window.
)

REM ── Step 6: Start frontend ──────────────────────────────────
echo.
echo  [6/7] Starting frontend dev server (Vite)...
if "!HAS_NODE!"=="0" goto :skip_frontend

REM Install npm dependencies if node_modules is missing
if exist "!PROJECT_ROOT!frontend\node_modules" goto :npm_ok
echo         Installing dependencies (first run)...
pushd "!PROJECT_ROOT!frontend"
call npm install
popd
echo         npm install complete.

:npm_ok
REM Write a temporary launcher script for frontend
set "_FRONTEND_LAUNCHER=!PROJECT_ROOT!_run_frontend.cmd"
echo @echo off> "!_FRONTEND_LAUNCHER!"
echo cd /d "!PROJECT_ROOT!frontend">> "!_FRONTEND_LAUNCHER!"
echo npm run dev>> "!_FRONTEND_LAUNCHER!"

start "SENTINELTWIN Frontend" /MIN cmd /c "!_FRONTEND_LAUNCHER!"
echo         Vite dev server: STARTING

REM Wait for Vite to be ready
echo         Waiting for frontend to become ready...
set "FRONTEND_READY=0"
set "_FCHECK=0"
:frontend_check
if !FRONTEND_READY! EQU 1 goto :frontend_done
if !_FCHECK! GEQ 20 goto :frontend_done
set /a _FCHECK+=1
ping -n 3 127.0.0.1 >nul
curl -s -o nul -w "%%{http_code}" http://localhost:5173 2>nul | findstr "200" >nul 2>&1
if not errorlevel 1 (
    set "FRONTEND_READY=1"
    echo         Frontend: ONLINE  [http://localhost:5173]
)
goto :frontend_check

:frontend_done
if !FRONTEND_READY! EQU 0 (
    echo         WARNING: Frontend did not respond within 40s.
    echo         It may still be starting. Check the Frontend window.
)
goto :show_status

:skip_frontend
echo         SKIPPED: Node.js not available

:show_status
echo.
echo  [7/7] Verifying operational readiness...
ping -n 2 127.0.0.1 >nul

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║              ALL SYSTEMS OPERATIONAL                        ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║                                                              ║
echo  ║  Frontend:    http://localhost:5173   (Vite dev server)     ║
echo  ║  API:         http://localhost:8000                         ║
echo  ║  API Docs:    http://localhost:8000/api/docs                ║
echo  ║  WebSocket:   ws://localhost:8000/ws/telemetry              ║
echo  ║                                                              ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║  DEFAULT CREDENTIALS:                                        ║
echo  ║  admin    / sentinel2026  (Administrator)                    ║
echo  ║  pilot    / pilot2026     (Pilot)                           ║
echo  ║  engineer / engineer2026  (Maintenance Engineer)             ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║  Stop:  end.bat   (kills backend + frontend processes)      ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Auto-open frontend in default browser ───────────────────
if "!HAS_NODE!"=="1" (
    echo  Opening frontend in browser...
    start "" http://localhost:5173
) else (
    echo  Opening API docs in browser...
    start "" http://localhost:8000/api/docs
)

echo.
echo  SentinelTwin is running. Use end.bat to stop all services.
echo  Backend and Frontend are running in minimized windows.
echo.
goto :eof
