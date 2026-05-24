@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title SENTINELTWIN — Aerospace Assurance Platform

REM ═══════════════════════════════════════════════════════════════════════
REM  SENTINELTWIN v4.4.0 — ONE-CLICK WINDOWS LAUNCHER
REM  EASA DO-326A / ED-202A / ARINC 664 Compliant
REM
REM  Usage:
REM    start_sentineltwin.bat              (auto-detect mode)
REM    start_sentineltwin.bat --local      (force local dev mode)
REM    start_sentineltwin.bat --docker     (force Docker mode)
REM    start_sentineltwin.bat --stop       (stop all services)
REM    start_sentineltwin.bat --check      (health check only)
REM ═══════════════════════════════════════════════════════════════════════

SET "ROOT=%~dp0"
SET "LOGDIR=%ROOT%logs"
SET "LAUNCH_PY=%ROOT%launch.py"

REM ── Create log directory ─────────────────────────────────────────────
IF NOT EXIST "%LOGDIR%" mkdir "%LOGDIR%"

REM ── Banner ───────────────────────────────────────────────────────────
echo.
echo   ╔══════════════════════════════════════════════════════════╗
echo   ║                                                          ║
echo   ║       S E N T I N E L T W I N  v4.4.0                  ║
echo   ║                                                          ║
echo   ║  Airworthiness Assurance Platform                       ║
echo   ║  EASA DO-326A / ED-202A / ARINC 664 Compliant          ║
echo   ║  8,192 Sensors · AI Anomaly Detection · SHA-256 Audit   ║
echo   ║                                                          ║
echo   ╚══════════════════════════════════════════════════════════╝
echo.

REM ── Handle --stop flag ───────────────────────────────────────────────
IF "%1"=="--stop" GOTO :stop_services
IF "%1"=="/stop"  GOTO :stop_services

REM ── Handle --check flag ──────────────────────────────────────────────
IF "%1"=="--check" GOTO :health_check
IF "%1"=="/check"  GOTO :health_check

REM ── Resolve Python ──────────────────────────────────────────────────
SET "PYTHON_CMD="
where python >nul 2>&1
IF NOT ERRORLEVEL 1 (
    python --version >nul 2>&1
    IF NOT ERRORLEVEL 1 (
        SET "PYTHON_CMD=python"
    )
)
IF NOT DEFINED PYTHON_CMD (
    where py >nul 2>&1
    IF NOT ERRORLEVEL 1 (
        FOR /F "delims=" %%P IN ('py -3 -c "import sys; print(sys.executable)" 2^>nul') DO (
            SET "PYTHON_CMD=%%P"
        )
    )
)
IF NOT DEFINED PYTHON_CMD (
    echo.
    echo   [ERROR] Python 3.9+ not found.
    echo   Install from: https://www.python.org/downloads/
    echo   Ensure "Add to PATH" is checked during install.
    echo.
    pause
    exit /b 1
)
echo   [OK] Python: !PYTHON_CMD!

REM ── Check if launch.py exists ────────────────────────────────────────
IF NOT EXIST "%LAUNCH_PY%" (
    echo   [ERROR] launch.py not found at: %LAUNCH_PY%
    echo   Ensure you are running from the SentinelTwin project root.
    pause
    exit /b 1
)

REM ── Parse mode argument ──────────────────────────────────────────────
SET "LAUNCH_ARGS="
IF "%1"=="--local"  SET "LAUNCH_ARGS=--mode local"
IF "%1"=="--docker" SET "LAUNCH_ARGS=--mode docker"
IF "%1"=="/local"   SET "LAUNCH_ARGS=--mode local"
IF "%1"=="/docker"  SET "LAUNCH_ARGS=--mode docker"

echo   [>>] Launching SentinelTwin orchestrator...
echo.

REM ── Execute launch.py (this manages everything) ──────────────────────
"!PYTHON_CMD!" "%LAUNCH_PY%" !LAUNCH_ARGS!
SET "EXIT_CODE=!ERRORLEVEL!"

IF !EXIT_CODE! NEQ 0 (
    echo.
    echo   [ERROR] Launch failed with exit code !EXIT_CODE!
    echo   Check logs\backend.log and logs\frontend.log for details.
    echo.
    pause
)
exit /b !EXIT_CODE!


REM ═══════════════════════════════════════════════════════════════════════
:stop_services
echo   [>>] Stopping SentinelTwin services...
SET "PYTHON_CMD="
where python >nul 2>&1
IF NOT ERRORLEVEL 1 SET "PYTHON_CMD=python"
IF NOT DEFINED PYTHON_CMD (
    where py >nul 2>&1
    IF NOT ERRORLEVEL 1 SET "PYTHON_CMD=py -3"
)
IF DEFINED PYTHON_CMD (
    IF EXIST "%LAUNCH_PY%" (
        "!PYTHON_CMD!" "%LAUNCH_PY%" --stop
        GOTO :stop_docker
    )
)
REM Fallback: kill by port
echo   [>>] Killing processes on ports 8000 and 5173...
FOR /F "tokens=5" %%a IN ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":8000 "') DO (
    taskkill /PID %%a /T /F >nul 2>&1
    echo   [OK] Killed PID %%a ^(port 8000^)
)
FOR /F "tokens=5" %%a IN ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":5173 "') DO (
    taskkill /PID %%a /T /F >nul 2>&1
    echo   [OK] Killed PID %%a ^(port 5173^)
)
:stop_docker
docker compose stop >nul 2>&1
echo   [OK] SentinelTwin stopped.
pause
exit /b 0


REM ═══════════════════════════════════════════════════════════════════════
:health_check
echo   [>>] Running system health check...
SET "PYTHON_CMD="
where python >nul 2>&1
IF NOT ERRORLEVEL 1 SET "PYTHON_CMD=python"
IF NOT DEFINED PYTHON_CMD (
    where py >nul 2>&1
    IF NOT ERRORLEVEL 1 SET "PYTHON_CMD=py -3"
)
IF DEFINED PYTHON_CMD (
    IF EXIST "%LAUNCH_PY%" (
        "!PYTHON_CMD!" "%LAUNCH_PY%" --check-only
        pause
        exit /b 0
    )
)
echo   [ERROR] Cannot run health check — Python or launch.py not found.
pause
exit /b 1
