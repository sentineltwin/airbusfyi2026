@echo off
setlocal EnableDelayedExpansion
title SENTINELTWIN LAUNCHER

::  ============================================================
::  SENTINELTWIN  -  ONE-CLICK LAUNCHER
::  Double-click this file to start everything.
::
::    Frontend : http://localhost:5173
::    Backend  : http://localhost:8000
::    API Docs : http://localhost:8000/api/docs
::  ============================================================

SET "ROOT=%~dp0"
SET "BACKEND=%ROOT%backend"
SET "FRONTEND=%ROOT%frontend"

cls
echo.
echo  ============================================================
echo    S E N T I N E L T W I N  v4.4.0
echo    Aerospace Airworthiness Assurance Platform
echo    8192 Sensors  *  AI Anomaly Detection  *  SHA-256 Audit
echo  ============================================================
echo.

:: ---------------------------------------------------------------
:: STEP 1 — Kill anything on ports 8000 / 5173
:: ---------------------------------------------------------------
echo  [1/5] Stopping any previous instances...
powershell -NoProfile -Command ^
  "Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -EA 0 | %%{ Stop-Process -Id $_.OwningProcess -Force -EA 0 }"
ping -n 3 127.0.0.1 >nul
echo  [OK] Ports 8000 and 5173 cleared.

:: ---------------------------------------------------------------
:: STEP 2 — Locate Python
:: ---------------------------------------------------------------
echo.
echo  [2/5] Checking Python...
SET "PY=python"
python --version >nul 2>&1
if errorlevel 1 (
    SET "PY=py -3"
    py -3 --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  [ERROR] Python 3.9+ is required but was not found.
        echo  Download at: https://www.python.org/downloads/
        echo  Tip: tick "Add Python to PATH" during install.
        echo.
        pause
        exit /b 1
    )
)
%PY% --version

:: ---------------------------------------------------------------
:: STEP 3 — Locate Node / npm
:: ---------------------------------------------------------------
echo.
echo  [3/5] Checking Node.js / npm...
npm --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] npm / Node.js not found.
    echo  Download at: https://nodejs.org/
    echo.
    pause
    exit /b 1
)
node --version
npm  --version

:: ---------------------------------------------------------------
:: Install npm packages on first run
:: ---------------------------------------------------------------
if not exist "%FRONTEND%\node_modules\vite" (
    echo.
    echo  [..] First run: installing npm packages (~2 min)...
    cd /d "%FRONTEND%"
    npm install --no-audit --no-fund
    if errorlevel 1 (
        echo.
        echo  [ERROR] npm install failed. Check your internet connection.
        pause
        exit /b 1
    )
    cd /d "%ROOT%"
    echo  [OK] npm packages installed.
)

:: ---------------------------------------------------------------
:: STEP 4 — Start Backend in a new console window
:: ---------------------------------------------------------------
echo.
echo  [4/5] Starting Backend API on port 8000...
if not exist "%ROOT%logs" mkdir "%ROOT%logs"
start "SENTINELTWIN BACKEND" /D "%BACKEND%" cmd /k "%PY% -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level info"
echo  [OK] Backend window opened.

:: ---------------------------------------------------------------
:: STEP 5 — Start Frontend in a new console window
:: ---------------------------------------------------------------
echo.
echo  [5/5] Starting Frontend on port 5173...
start "SENTINELTWIN FRONTEND" /D "%FRONTEND%" cmd /k "npm run dev"
echo  [OK] Frontend window opened.

:: ---------------------------------------------------------------
:: Wait for both services to respond
:: ---------------------------------------------------------------
echo.
echo  [>>] Waiting for services (up to 90 seconds)...
echo.

SET "BE=0"
SET "FE=0"
SET "N=0"

:loop
    SET /A N+=1
    if !N! GTR 45 goto :timeout

    :: Check backend
    if "!BE!"=="0" (
        curl -s --max-time 2 -o NUL http://localhost:8000/health
        if not errorlevel 1 (
            SET "BE=1"
            echo  [OK] Backend  LIVE  --  http://localhost:8000
        )
    )

    :: Check frontend
    if "!FE!"=="0" (
        curl -s --max-time 2 -o NUL http://localhost:5173
        if not errorlevel 1 (
            SET "FE=1"
            echo  [OK] Frontend LIVE  --  http://localhost:5173
        )
    )

    if "!BE!"=="1" if "!FE!"=="1" goto :all_ready

    echo  [...] Check !N!/45 - services still starting...
    ping -n 3 127.0.0.1 >nul
goto :loop

:timeout
echo.
echo  [WARN] Services are taking longer than expected.
echo  Look at the BACKEND / FRONTEND console windows for errors.
goto :open_browser

:all_ready
echo.
echo  ============================================================
echo    ALL SYSTEMS ONLINE
echo  ============================================================
echo.
echo    Frontend  :  http://localhost:5173
echo    Backend   :  http://localhost:8000
echo    API Docs  :  http://localhost:8000/api/docs
echo.
echo    ----- LOGIN CREDENTIALS -----
echo    admin      /  sentinel2026
echo    pilot      /  pilot2026
echo    engineer   /  engineer2026
echo    dispatcher /  dispatch2026
echo  ============================================================
echo.

:open_browser
ping -n 2 127.0.0.1 >nul
start "" http://localhost:5173
echo  Browser launched: http://localhost:5173
echo.
echo  Keep the BACKEND and FRONTEND console windows open.
echo  To stop everything, run STOP.bat or close those windows.
echo.
pause
