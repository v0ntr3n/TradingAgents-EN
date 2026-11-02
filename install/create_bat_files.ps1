# ============================================================================
# Create BAT files for installer
# ============================================================================
# Create a .bat startup file for the installer
# ============================================================================

# UTF-8 encoding settings
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
$portableDir = Join-Path $root "release\TradingAgentsCN-portable"

Write-Host "Creating BAT files for installer..." -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# start_all.bat
# ============================================================================

$startBat = @'
@echo off
chcp 65001 >nul
title TradingAgents-CN - Starting...

echo ============================================================================
echo   TradingAgents-CN Pro - Portable launcher
echo ============================================================================
echo.

cd /d "%~dp0"

echo Starting all services...
echo.
echo Tips: This script will call the PowerShell script to start the service
echo.

REM Call the PowerShell startup script
powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"

if errorlevel 1 (
    echo.
    echo ============================================================================
    echo   Startup failed
    echo ============================================================================
    echo.
    echo Please check the error message or try running directly start_all.ps1
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo   All services have been started!
echo ============================================================================
echo.
echo   Access address: http://localhost
echo   Default account: admin / admin123
echo.
pause

exit
'@

$startBatPath = Join-Path $portableDir "start_all.bat"
$startBat | Out-File -FilePath $startBatPath -Encoding ASCII
Write-Host "  ✅ Created: start_all.bat" -ForegroundColor Green

# ============================================================================
# stop_all.bat
# ============================================================================

$stopBat = @'
@echo off
chcp 65001 >nul
title TradingAgents-CN - Stopping...

echo ============================================================================
echo   TradingAgents-CN Pro - Stop all services
echo ============================================================================
echo.

cd /d "%~dp0"

echo [1/2] Stop application service...
taskkill /FI "WINDOWTITLE eq TradingAgents*" /F >nul 2>&1

echo.
echo [2/2] Stop database service...
call scripts\stop_databases.bat

echo.
echo ============================================================================
echo   All services have been stopped!
echo ============================================================================
echo.
pause
'@

$stopBatPath = Join-Path $portableDir "stop_all.bat"
$stopBat | Out-File -FilePath $stopBatPath -Encoding ASCII
Write-Host "  ✅ Created: stop_all.bat" -ForegroundColor Green

Write-Host ""
Write-Host "BAT files created successfully!" -ForegroundColor Green

