# Start the Worker service (development environment)
# Usage: .\start_worker.ps1 [-Port 8001]

param(
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TradingAgents-CN Pro - Worker start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Detect Python environment
$root = $PSScriptRoot
$pythonExe = $null
$pythonCandidates = @()

if ($env:TRADINGAGENTS_PYTHON_EXE -and (Test-Path $env:TRADINGAGENTS_PYTHON_EXE)) {
    $pythonCandidates += $env:TRADINGAGENTS_PYTHON_EXE
}

$pythonCandidates += @(
    (Join-Path $root "release\TradingAgentsCN-portable\vendors\python\python.exe"),
    (Join-Path $root "env\Scripts\python.exe"),
    (Join-Path $root "venv\Scripts\python.exe"),
    (Join-Path $root "vendors\python\python.exe")
)

foreach ($path in $pythonCandidates) {
    if (Test-Path $path) {
        $pythonExe = $path
        Write-Host "✅ found Python: $path" -ForegroundColor Green
        break
    }
}

if (-not $pythonExe) {
    Write-Host "❌ Python environment not found" -ForegroundColor Red
    exit 1
}

# Set environment variables
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"

Write-Host ""
Write-Host "🚀 Start the Worker service..." -ForegroundColor Cyan
Write-Host "   port: $Port" -ForegroundColor Gray
Write-Host "   Log: logs/worker.log" -ForegroundColor Gray
Write-Host ""

# start Worker
& $pythonExe -m uvicorn app.worker.worker_app:app --host 127.0.0.1 --port $Port --log-level info

