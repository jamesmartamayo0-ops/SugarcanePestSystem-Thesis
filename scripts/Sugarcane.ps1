[CmdletBinding()]
param(
    [switch]$Open,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$flaskPath = Join-Path $backendRoot '.venv\Scripts\flask.exe'
$npmPath = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
$backendUrl = 'http://127.0.0.1:5002'
$frontendUrl = 'http://localhost:3002'
$databaseHost = '127.0.0.1'
$databasePort = 5434
$databaseName = 'sugarcane_pest_test'
$backendPort = 5002
$frontendPort = 3002
$serviceName = 'postgresql-x64-17'
$backendProcess = $null
$frontendProcess = $null
$logRoot = Join-Path $env:TEMP ("sugarcane-demo-{0}" -f $PID)
$backendLog = Join-Path $logRoot 'backend.log'
$frontendLog = Join-Path $logRoot 'frontend.log'

function Fail([string]$Message) { throw $Message }

function Write-Ok([string]$Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }

function Test-PortFree([int]$Port) {
    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($connections.Count -eq 0) { return }
    $details = $connections | ForEach-Object {
        $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        "PID $($_.OwningProcess) $($process.ProcessName) at $($_.LocalAddress):$Port"
    }
    Fail "Port $Port is already occupied. $($details -join '; '). No process was stopped."
}

function Invoke-BackendPython([string]$Code) {
    Push-Location $backendRoot
    try {
        return @(& $pythonPath -c $Code 2>&1)
    }
    finally {
        Pop-Location
    }
}

function Test-Database {
    $pgReadyPath = (Get-Command pg_isready.exe -ErrorAction SilentlyContinue).Source
    if ([string]::IsNullOrWhiteSpace($pgReadyPath)) {
        $pgReadyPath = (Get-ChildItem (Join-Path $env:ProgramFiles 'PostgreSQL\*\bin\pg_isready.exe') -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
    }
    if ([string]::IsNullOrWhiteSpace($pgReadyPath)) { Fail 'pg_isready.exe was not found on PATH or under Program Files\PostgreSQL.' }
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($null -eq $service -or $service.Status -ne 'Running') { Fail "PostgreSQL service '$serviceName' is not running." }
    & $pgReadyPath -h $databaseHost -p $databasePort *> $null
    if ($LASTEXITCODE -ne 0) { Fail "PostgreSQL is not accepting connections on ${databaseHost}:$databasePort." }
    $probe = Invoke-BackendPython 'from app import create_app; from app.extensions import db; app=create_app(); c=app.app_context(); c.push(); print(db.engine.url.database); c.pop()'
    if ($LASTEXITCODE -ne 0 -or ($probe | Select-Object -Last 1) -ne 'sugarcane_pest_test') { Fail 'Application database verification failed.' }
    Write-Ok "PostgreSQL verified at ${databaseHost}:$databasePort"
    Write-Ok "Database verified: $databaseName"
}

function Test-Administrator {
    $probe = Invoke-BackendPython 'from app import create_app; from app.extensions import db; from app.models import User; from sqlalchemy import select; app=create_app(); c=app.app_context(); c.push(); [print(u.username, u.role, u.is_active) for u in db.session.scalars(select(User))]; c.pop()'
    if ($LASTEXITCODE -ne 0 -or -not ($probe | Where-Object { $_.ToString().Trim() -eq 'sugarcane2026 ADMIN True' })) { Fail 'Administrator sugarcane2026 is missing, inactive, or not ADMIN.' }
    Write-Ok 'Demo Administrator verified: sugarcane2026 (ADMIN)'
}

function Test-Preflight {
    if (-not (Test-Path -LiteralPath $projectRoot -PathType Container)) { Fail "Repository missing: $projectRoot" }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { Fail "Backend virtual environment missing: $pythonPath" }
    if (-not (Test-Path -LiteralPath $flaskPath -PathType Leaf)) { Fail "Flask executable missing: $flaskPath" }
    if ([string]::IsNullOrWhiteSpace($npmPath)) { Fail 'npm.cmd is not available on PATH.' }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules') -PathType Container)) { Fail 'Frontend dependencies are missing: frontend/node_modules' }
    if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.env') -PathType Leaf)) { Fail 'backend/.env is missing.' }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot '.env.local') -PathType Leaf)) { Fail 'frontend/.env.local is missing.' }
    Write-Ok 'Repository verified'
    Write-Ok 'Backend virtual environment verified'
    Write-Ok 'Frontend dependencies verified'
    Test-Database
    Test-Administrator
    Test-PortFree $backendPort
    Test-PortFree $frontendPort
    Write-Ok 'Ports 5002 and 3002 available'
}

function Stop-Tree($Process) {
    if ($null -eq $Process) { return }
    if ($Process.HasExited) { return }
    & taskkill.exe /PID $Process.Id /T /F *> $null
}

function Write-NewLogLines([string]$Path, [string]$Label, [ref]$Offset) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $lines = @(Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue)
    while ($Offset.Value -lt $lines.Count) {
        Write-Host ("[{0}] {1}" -f $Label, $lines[$Offset.Value])
        $Offset.Value++
    }
}

Write-Host '========================================' -ForegroundColor DarkCyan
Write-Host ' SUGARCANE PEST MANAGEMENT SYSTEM' -ForegroundColor DarkCyan
Write-Host '========================================' -ForegroundColor DarkCyan
Write-Host "Project: $projectRoot"
Write-Host 'Environment: Local Client Demo'
Write-Host 'Database: PostgreSQL 17 @ 127.0.0.1:5434 / sugarcane_pest_test'
Write-Host 'Frontend: http://localhost:3002'
Write-Host 'Backend:  http://127.0.0.1:5002'

Test-Preflight
if ($CheckOnly) { Write-Ok 'Preflight check complete'; exit 0 }

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
Remove-Item -LiteralPath $backendLog,$frontendLog -Force -ErrorAction SilentlyContinue
Write-Info 'Starting backend...'
$backendCommand = "`$env:HOST='127.0.0.1'; `$env:PORT='5002'; & '$pythonPath' 'run.py' 2>&1"
$backendProcess = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$backendCommand) -WorkingDirectory $backendRoot -RedirectStandardOutput $backendLog -PassThru
Write-Info 'Starting frontend...'
$frontendCommand = "& '$npmPath' run dev -- -p 3002 2>&1"
$frontendProcess = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$frontendCommand) -WorkingDirectory $frontendRoot -RedirectStandardOutput $frontendLog -PassThru

$backendOffset = 0
$frontendOffset = 0
$readyDeadline = [DateTime]::UtcNow.AddSeconds(60)
$backendReady = $false
$frontendReady = $false
try {
    while (-not ($backendReady -and $frontendReady)) {
        Write-NewLogLines $backendLog 'BACKEND' ([ref]$backendOffset)
        Write-NewLogLines $frontendLog 'FRONTEND' ([ref]$frontendOffset)
        if ($backendProcess.HasExited) { Fail "Backend exited during startup (code $($backendProcess.ExitCode))." }
        if ($frontendProcess.HasExited) { Fail "Frontend exited during startup (code $($frontendProcess.ExitCode))." }
        if (-not $backendReady) {
            try { $health = Invoke-WebRequest -UseBasicParsing -Uri "$backendUrl/api/v1/health" -TimeoutSec 2; if ($health.StatusCode -eq 200) { $backendReady = $true; Write-Ok "Backend ready at $backendUrl" } } catch {}
        }
        if (-not $frontendReady) {
            try { $page = Invoke-WebRequest -UseBasicParsing -Uri $frontendUrl -TimeoutSec 2; if ($page.StatusCode -eq 200) { $frontendReady = $true; Write-Ok "Frontend ready at $frontendUrl" } } catch {}
        }
        if ([DateTime]::UtcNow -ge $readyDeadline) { Fail "Timed out waiting for backend/frontend readiness." }
        Start-Sleep -Milliseconds 500
    }
    if ($Open) { Start-Process $frontendUrl | Out-Null; Write-Ok 'Browser opened at http://localhost:3002' }
    Write-Info 'Both services are supervised in this terminal. Press Ctrl+C to stop them.'
    while ($true) {
        Write-NewLogLines $backendLog 'BACKEND' ([ref]$backendOffset)
        Write-NewLogLines $frontendLog 'FRONTEND' ([ref]$frontendOffset)
        if ($backendProcess.HasExited) { Fail "Backend exited (code $($backendProcess.ExitCode))." }
        if ($frontendProcess.HasExited) { Fail "Frontend exited (code $($frontendProcess.ExitCode))." }
        Start-Sleep -Milliseconds 250
    }
}
finally {
    Write-Info 'Stopping Sugarcane child processes...'
    Stop-Tree $backendProcess
    Stop-Tree $frontendProcess
    Start-Sleep -Milliseconds 750
    Remove-Item -LiteralPath $logRoot -Recurse -Force -ErrorAction SilentlyContinue
}
