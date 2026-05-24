# SentinelTwin - PowerShell One-Click Launcher
# Right-click -> "Run with PowerShell" OR: powershell -ExecutionPolicy Bypass -File LAUNCH.ps1

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend  = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Clear-Host
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "    S E N T I N E L T W I N  v4.4.0" -ForegroundColor Cyan
Write-Host "    Aerospace Airworthiness Assurance Platform" -ForegroundColor Cyan
Write-Host "    8192 Sensors  *  AI Anomaly Detection  *  SHA-256 Audit" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------
# STEP 1 - Kill old processes on ports 8000 and 5173
# ---------------------------------------------------------------
Write-Host "  [1/5] Stopping previous instances..." -ForegroundColor Yellow
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -EA SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
Start-Sleep -Seconds 2
Write-Host "  [OK]  Ports cleared." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 2 - Check Python
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  [2/5] Checking Python..." -ForegroundColor Yellow
$py = $null
foreach ($cmd in @("python", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python 3\.([9-9]|1\d)") { $py = $cmd; break }
    } catch {}
}
if (-not $py) {
    Write-Host "  [ERROR] Python 3.9+ not found." -ForegroundColor Red
    Write-Host "  Download: https://www.python.org/downloads/" -ForegroundColor Red
    try { Read-Host "Press Enter to exit" } catch {}
    exit 1
}
Write-Host "  [OK]  $(& $py --version 2>&1)" -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 3 - Check Node / npm
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  [3/5] Checking Node.js..." -ForegroundColor Yellow
if (-not (Get-Command npm -EA SilentlyContinue)) {
    Write-Host "  [ERROR] npm not found. Download: https://nodejs.org/" -ForegroundColor Red
    try { Read-Host "Press Enter to exit" } catch {}
    exit 1
}
Write-Host "  [OK]  Node $(node --version)  /  npm $(npm --version)" -ForegroundColor Green

# Install npm packages if missing
$viteBin = Join-Path $Frontend "node_modules\vite"
if (-not (Test-Path $viteBin)) {
    Write-Host ""
    Write-Host "  [..] First run: installing npm packages (~2 min)..." -ForegroundColor Yellow
    Push-Location $Frontend
    npm install --no-audit --no-fund
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] npm install failed." -ForegroundColor Red
        try { Read-Host "Press Enter to exit" } catch {}
        exit 1
    }
    Write-Host "  [OK]  npm packages installed." -ForegroundColor Green
}

# ---------------------------------------------------------------
# STEP 4 - Start Backend
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  [4/5] Starting Backend on port 8000..." -ForegroundColor Yellow
$null = New-Item -ItemType Directory -Path (Join-Path $Root "logs") -Force
Start-Process "cmd.exe" -ArgumentList "/k title SENTINELTWIN BACKEND && $py -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level info" -WorkingDirectory $Backend -WindowStyle Normal
Write-Host "  [OK]  Backend window opened." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 5 - Start Frontend
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  [5/5] Starting Frontend on port 5173..." -ForegroundColor Yellow
Start-Process "cmd.exe" -ArgumentList "/k title SENTINELTWIN FRONTEND && npm run dev" -WorkingDirectory $Frontend -WindowStyle Normal
Write-Host "  [OK]  Frontend window opened." -ForegroundColor Green

# ---------------------------------------------------------------
# Wait for both services
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  [>>] Waiting for services to come online (up to 90s)..." -ForegroundColor Cyan
Write-Host ""

$beReady = $false
$feReady = $false
$tries   = 0

while ($tries -lt 45) {
    $tries++

    if (-not $beReady) {
        $exitCode = (Start-Process "curl.exe" -ArgumentList "-s --max-time 2 -o NUL http://localhost:8000/health" -Wait -PassThru -WindowStyle Hidden).ExitCode
        if ($exitCode -eq 0) {
            $beReady = $true
            Write-Host "  [OK]  Backend  LIVE  --  http://localhost:8000" -ForegroundColor Green
        }
    }

    if (-not $feReady) {
        $exitCode = (Start-Process "curl.exe" -ArgumentList "-s --max-time 2 -o NUL http://localhost:5173" -Wait -PassThru -WindowStyle Hidden).ExitCode
        if ($exitCode -eq 0) {
            $feReady = $true
            Write-Host "  [OK]  Frontend LIVE  --  http://localhost:5173" -ForegroundColor Green
        }
    }

    if ($beReady -and $feReady) { break }

    Write-Host "  [...] Check $tries/45 - services still starting..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 2
}

if (-not $beReady -or -not $feReady) {
    Write-Host ""
    Write-Host "  [WARN] Services slow to start. Check the console windows for errors." -ForegroundColor Yellow
}

# ---------------------------------------------------------------
# Summary & open browser
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "    ALL SYSTEMS ONLINE" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "    Frontend  :  http://localhost:5173"
Write-Host "    Backend   :  http://localhost:8000"
Write-Host "    API Docs  :  http://localhost:8000/api/docs"
Write-Host ""
Write-Host "    LOGIN CREDENTIALS"
Write-Host "    admin      /  sentinel2026"
Write-Host "    pilot      /  pilot2026"
Write-Host "    engineer   /  engineer2026"
Write-Host "    dispatcher /  dispatch2026"
Write-Host ""
Write-Host "  Keep the BACKEND and FRONTEND windows open."
Write-Host "  Run STOP.bat to shut everything down."
Write-Host "  ============================================================" -ForegroundColor Cyan

Start-Sleep -Seconds 1
Start-Process "http://localhost:5173"
Write-Host ""
Write-Host "  Browser opened at http://localhost:5173" -ForegroundColor Green
Write-Host ""
$nonInteractive = [Environment]::GetCommandLineArgs() -contains '-NonInteractive'
if (-not $nonInteractive) {
    try { Read-Host "Press Enter to exit this launcher" } catch {}
}
