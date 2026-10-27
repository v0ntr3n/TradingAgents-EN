# TradingAgents-CN Services Diagnostic Script
# Diagnose the startup status and error information of MongoDB and Redis services

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("mongodb", "redis", "all")]
    [string]$Service = "all",
    
    [Parameter(Mandatory=$false)]
    [switch]$Start,
    
    [Parameter(Mandatory=$false)]
    [switch]$ShowLogs,
    
    [Parameter(Mandatory=$false)]
    [switch]$TestConnection
)

$ErrorActionPreference = "Continue"
# Script is at project root directory
# Project root is the same as script directory
$root = $PSScriptRoot
$envPath = Join-Path $root '.env'

# ============================================================================
# Helper Functions
# ============================================================================

function Load-Env($path) {
    $map = @{}
    if (Test-Path -LiteralPath $path) {
        foreach ($line in Get-Content -LiteralPath $path) {
            if ($line -match '^\s*#') { continue }
            if ($line -match '^\s*$') { continue }
            $idx = $line.IndexOf('=')
            if ($idx -gt 0) {
                $key = $line.Substring(0, $idx).Trim()
                $val = $line.Substring($idx + 1).Trim()
                $map[$key] = $val
            }
        }
    }
    return $map
}

function Ensure-Dir($path) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

function Test-TcpConnection($hostname, $port, $timeoutSeconds = 3) {
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connect = $tcpClient.BeginConnect($hostname, $port, $null, $null)
        $wait = $connect.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($timeoutSeconds), $false)
        if ($wait) {
            $tcpClient.EndConnect($connect)
            $tcpClient.Close()
            return $true
        } else {
            $tcpClient.Close()
            return $false
        }
    } catch {
        return $false
    }
}

function Get-ProcessInfo($processName) {
    $processes = Get-Process -Name $processName -ErrorAction SilentlyContinue
    if ($processes) {
        return $processes | Select-Object -First 1 | ForEach-Object {
            @{
                Exists = $true
                PID = $_.Id
                Name = $_.ProcessName
                Path = $_.Path
                StartTime = $_.StartTime
            }
        }
    }
    return @{ Exists = $false }
}

function Get-PortInfo($port) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($connections) {
        $conn = $connections | Select-Object -First 1
        $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        return @{
            InUse = $true
            PID = $conn.OwningProcess
            ProcessName = if ($process) { $process.ProcessName } else { "Unknown" }
            State = $conn.State
        }
    }
    return @{ InUse = $false }
}

# ============================================================================
# MongoDB Diagnostic Functions
# ============================================================================

function Test-MongoDBConnection($hostname, $port, $username, $password) {
    Write-Host "  📡 Test MongoDB connection..." -ForegroundColor Gray
    
    # First test TCP connection
    if (-not (Test-TcpConnection -hostname $hostname -port $port -timeoutSeconds 5)) {
        Write-Host "    ❌ TCP Connection failed: Unable to connect to $hostname`:$port" -ForegroundColor Red
        return $false
    }
    Write-Host "    ✅ TCP Connection successful" -ForegroundColor Green
    
    # Try Python connection test if available
    $pythonExe = Join-Path $root 'vendors\python\python.exe'
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $root 'venv\Scripts\python.exe'
    }
    
    if (Test-Path $pythonExe) {
        try {
            $testScript = @"
import sys
import json
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure
    
    client = MongoClient(
        host='$hostname',
        port=$port,
        username='$username',
        password='$password',
        authSource='admin',
        serverSelectionTimeoutMS=10000
    )
    
    # Test connection with ping
    result = client.admin.command('ping')
    print('PING_SUCCESS')
    
    # Get server info
    server_info = client.server_info()
    print(f'SERVER_VERSION: {server_info.get("version", "unknown")}')
    
    # List databases
    db_list = client.list_database_names()
    print(f'DATABASES: {", ".join(db_list) if db_list else "(empty)"}')
    
    # Try to get database stats
    try:
        admin_db = client.admin
        db_stats = admin_db.command('dbStats')
        data_size = db_stats.get("dataSize", 0)
        print(f'ADMIN_DB_SIZE: {data_size}')
    except Exception as e:
        print(f'ADMIN_DB_SIZE: 0')
    
    # Test write/read if possible
    try:
        from datetime import datetime
        test_db = client.get_database('test')
        test_collection = test_db.get_collection('connection_test')
        test_collection.insert_one({'test': 'connection', 'timestamp': datetime.now().isoformat()})
        count = test_collection.count_documents({})
        test_collection.delete_one({'test': 'connection'})
        print(f'WRITE_READ_TEST: SUCCESS (count={count})')
    except Exception as e:
        print(f'WRITE_READ_TEST: SKIPPED ({str(e)[:50]})')
    
    print('ALL_TESTS_PASSED')
    sys.exit(0)
except ConnectionFailure as e:
    print(f'CONNECTION_ERROR: {e}')
    sys.exit(1)
except OperationFailure as e:
    print(f'AUTH_ERROR: {e}')
    sys.exit(2)
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(3)
"@
            $scriptFile = Join-Path $env:TEMP "test_mongo_$(Get-Random).py"
            Set-Content -Path $scriptFile -Value $testScript -Encoding UTF8
            
            $output = & $pythonExe $scriptFile 2>&1 | Out-String
            Remove-Item $scriptFile -ErrorAction SilentlyContinue
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "    ✅ MongoDB Authentication connection successful" -ForegroundColor Green
                
                # Parse and display test results
                try {
                    $outputLines = $output -split "`n" | Where-Object { $_.Trim() }
                    foreach ($line in $outputLines) {
                        $line = $line.Trim()
                        if ([string]::IsNullOrWhiteSpace($line)) { continue }
                        
                        try {
                            if ($line -match '^SERVER_VERSION:') {
                                $version = $line -replace '^SERVER_VERSION:\s*', ''
                                Write-Host "      📌 MongoDB version: $version" -ForegroundColor Gray
                            } elseif ($line -match '^DATABASES:') {
                                $dbs = $line -replace '^DATABASES:\s*', ''
                                Write-Host "      📌 Database list: $dbs" -ForegroundColor Gray
                            } elseif ($line -match '^ADMIN_DB_SIZE:') {
                                $sizeStr = $line -replace '^ADMIN_DB_SIZE:\s*', ''
                                # Try to extract numeric value (handle formats like "0", "0.0", "1234", etc.)
                                if ($sizeStr -match '^(\d+(?:\.\d+)?)$') {
                                    try {
                                        $sizeBytes = [double]$matches[1]
                                        $sizeMB = [math]::Round($sizeBytes / 1MB, 2)
                                        Write-Host "      📌 Admin Database size: $sizeMB MB" -ForegroundColor Gray
                                    } catch {
                                        Write-Host "      📌 Admin Database size: $sizeStr" -ForegroundColor Gray
                                    }
                                } else {
                                    Write-Host "      📌 Admin Database size: $sizeStr" -ForegroundColor Gray
                                }
                            } elseif ($line -match '^WRITE_READ_TEST:') {
                                $testResult = $line -replace '^WRITE_READ_TEST:\s*', ''
                                if ($testResult -match 'SUCCESS') {
                                    Write-Host "      ✅ Reading and writing test successful: $testResult" -ForegroundColor Green
                                } else {
                                    Write-Host "      ⚠️ Read and write test skipped: $testResult" -ForegroundColor Yellow
                                }
                            }
                        } catch {
                            # Ignore parsing errors for individual lines
                            # Don't display error to avoid cluttering output
                        }
                    }
                } catch {
                    # If parsing fails completely, still consider connection successful
                    Write-Host "      ⚠️ Having trouble parsing test results, but connection test succeeds" -ForegroundColor Yellow
                }
                
                return $true
            } else {
                Write-Host "    ❌ MongoDB Connection test failed" -ForegroundColor Red
                $outputLines = $output -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 3
                foreach ($line in $outputLines) {
                    Write-Host "      $($line.Trim())" -ForegroundColor Red
                }
                return $false
            }
        } catch {
            # Check if Python script actually ran successfully
            # If it did, connection test passed even if parsing failed
            if ($LASTEXITCODE -eq 0) {
                Write-Host "    ⚠️ Having trouble parsing test results: $_" -ForegroundColor Yellow
                Write-Host "    ✅ But the MongoDB connection test itself succeeds" -ForegroundColor Green
                return $true
            } else {
                Write-Host "    ⚠️ Python Connection test failed: $_" -ForegroundColor Yellow
                return $false
            }
        }
    } else {
        Write-Host "    ⚠️ Python executable not found, skipping detailed connection test" -ForegroundColor Yellow
        Write-Host "    💡 Tips: TCP Connection successful, but authentication and database access cannot be verified" -ForegroundColor Gray
    }
    
    return $true  # TCP connection succeeded
}

function Start-MongoDBWithLogs($mongoExe, $mongoData, $mongoPort, $showLogs) {
    Write-Host "  🚀 start MongoDB..." -ForegroundColor Cyan
    
    Ensure-Dir $mongoData
    
    # Check if initialized
    $initMarker = Join-Path $mongoData '.mongo_initialized'
    $needsAuth = Test-Path $initMarker
    
    $mongoArgs = "--dbpath `"$mongoData`" --bind_ip 127.0.0.1 --port $mongoPort"
    if ($needsAuth) {
        $mongoArgs += " --auth"
    }
    
    try {
        # Start process without redirecting streams to avoid blocking
        # Use ProcessStartInfo to have better control
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $mongoExe
        $psi.Arguments = $mongoArgs
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        # Don't redirect output to avoid blocking on ReadLine()
        $psi.RedirectStandardOutput = $false
        $psi.RedirectStandardError = $false
        
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.Start() | Out-Null
        
        Write-Host "    MongoDB Process started (PID: $($process.Id))" -ForegroundColor Gray
        
        if ($showLogs) {
            Write-Host "    📋 MongoDB Startup information:" -ForegroundColor Cyan
            Write-Host "      ⚠️ Note: To avoid blocking, log output is disabled" -ForegroundColor Yellow
            Write-Host "      💡 Tips: To view detailed logs, please check the log files in the MongoDB data directory" -ForegroundColor Gray
            Write-Host "      💡 Tips: Or run it manually to see the output: $mongoExe $mongoArgs" -ForegroundColor Gray
        }
        
        # Give MongoDB a moment to start
        Start-Sleep -Seconds 2
        
        if ($process.HasExited) {
            Write-Host "    ❌ MongoDB Process has exited (exit code: $($process.ExitCode))" -ForegroundColor Red
            Write-Host "    💡 Tips: Please check MongoDB data directory permissions and log files" -ForegroundColor Yellow
            Write-Host "    💡 Tips: Or run it manually to view errors: $mongoExe $mongoArgs" -ForegroundColor Gray
            return $null
        } else {
            Write-Host "    ✅ MongoDB Process is running" -ForegroundColor Green
            Write-Host "    ⏳ Wait for MongoDB to fully start (check port listening)..." -ForegroundColor Gray
            
            # Wait for port to be listening (max 30 seconds)
            $portReady = $false
            $waitStartTime = Get-Date
            $maxWaitSeconds = 30
            
            while (-not $portReady -and (Get-Date).Subtract($waitStartTime).TotalSeconds -lt $maxWaitSeconds) {
                if ($process.HasExited) {
                    Write-Host "    ❌ MongoDB Process exited unexpectedly" -ForegroundColor Red
                    return $null
                }
                
                $portInfo = Get-PortInfo -port $mongoPort
                if ($portInfo.InUse -and $portInfo.ProcessName -eq "mongod") {
                    $portReady = $true
                    break
                }
                Start-Sleep -Seconds 1
            }
            
            if ($portReady) {
                Write-Host "    ✅ MongoDB port $mongoPort Started listening" -ForegroundColor Green
            } else {
                Write-Host "    ⚠️ MongoDB The process is running, but the port $mongoPort Not listening yet (may still be starting)" -ForegroundColor Yellow
            }
            
            return $process
        }
    } catch {
        Write-Host "    ❌ Failed to start MongoDB: $_" -ForegroundColor Red
        return $null
    }
}

function Diagnose-MongoDB($envMap, $root, $start, $showLogs, $testConnection) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "MongoDB Diagnosis" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    $mongoPort = if ($envMap.ContainsKey('MONGODB_PORT')) { [int]$envMap['MONGODB_PORT'] } else { 27017 }
    $mongoHost = if ($envMap.ContainsKey('MONGODB_HOST')) { $envMap['MONGODB_HOST'] } else { "localhost" }
    $mongoUsername = if ($envMap.ContainsKey('MONGODB_USERNAME')) { $envMap['MONGODB_USERNAME'] } else { "admin" }
    $mongoPassword = if ($envMap.ContainsKey('MONGODB_PASSWORD')) { $envMap['MONGODB_PASSWORD'] } else { "tradingagents123" }
    
    Write-Host "📋 Configuration information:" -ForegroundColor Cyan
    Write-Host "  Host: $mongoHost" -ForegroundColor Gray
    Write-Host "  port: $mongoPort" -ForegroundColor Gray
    Write-Host "  Username: $mongoUsername" -ForegroundColor Gray
    Write-Host ""
    
    # Check executable
    $mongoExe = Join-Path $root 'vendors\mongodb\mongodb-win32-x86_64-windows-8.0.13\bin\mongod.exe'
    Write-Host "🔍 Check the MongoDB executable file..." -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $mongoExe)) {
        Write-Host "  ❌ MongoDB Executable file does not exist: $mongoExe" -ForegroundColor Red
        Write-Host "  💡 Suggestions: Check whether the installation directory is correct" -ForegroundColor Yellow
        return
    }
    Write-Host "  ✅ MongoDB Executable file exists" -ForegroundColor Green
    Write-Host ""
    
    # Check data directory
    $mongoData = Join-Path $root 'data\mongodb\db'
    Write-Host "🔍 Check data directory..." -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $mongoData)) {
        Write-Host "  ⚠️ The data directory does not exist and will be created automatically.: $mongoData" -ForegroundColor Yellow
        Ensure-Dir $mongoData
    } else {
        Write-Host "  ✅ data directory exists: $mongoData" -ForegroundColor Green
    }
    Write-Host ""
    
    # Check process
    Write-Host "🔍 Check MongoDB process..." -ForegroundColor Cyan
    $procInfo = Get-ProcessInfo -processName "mongod"
    if ($procInfo.Exists) {
        Write-Host "  ✅ MongoDB Process is running" -ForegroundColor Green
        Write-Host "    PID: $($procInfo.PID)" -ForegroundColor Gray
        Write-Host "    path: $($procInfo.Path)" -ForegroundColor Gray
        Write-Host "    Start time: $($procInfo.StartTime)" -ForegroundColor Gray
    } else {
        Write-Host "  ❌ MongoDB Process is not running" -ForegroundColor Red
    }
    Write-Host ""
    
    # Check port
    Write-Host "🔍 Check port $mongoPort..." -ForegroundColor Cyan
    $portInfo = Get-PortInfo -port $mongoPort
    if ($portInfo.InUse) {
        Write-Host "  ✅ port $mongoPort Listening" -ForegroundColor Green
        Write-Host "    process: $($portInfo.ProcessName) (PID: $($portInfo.PID))" -ForegroundColor Gray
        if ($portInfo.ProcessName -ne "mongod") {
            Write-Host "    ⚠️ warning: The port is occupied by other processes!" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ❌ port $mongoPort Not listening" -ForegroundColor Red
    }
    Write-Host ""
    
    # Test connection
    if ($testConnection) {
        Test-MongoDBConnection -hostname $mongoHost -port $mongoPort -username $mongoUsername -password $mongoPassword | Out-Null
        Write-Host ""
    }
    
    # Start if requested and not running
    if ($start -and -not $procInfo.Exists) {
        Write-Host "🔧 Try to start MongoDB..." -ForegroundColor Cyan
        $process = Start-MongoDBWithLogs -mongoExe $mongoExe -mongoData $mongoData -mongoPort $mongoPort -showLogs $showLogs
        
        if ($process) {
            Write-Host ""
            Write-Host "  ⏳ Wait for MongoDB to fully start..." -ForegroundColor Yellow
            # Wait a bit more for MongoDB to be fully ready
            Start-Sleep -Seconds 3
            
            # Re-check process and port
            $procInfo = Get-ProcessInfo -processName "mongod"
            $portInfo = Get-PortInfo -port $mongoPort
            
            if ($procInfo.Exists -and $portInfo.InUse -and $portInfo.ProcessName -eq "mongod") {
                Write-Host "  ✅ MongoDB Started successfully!" -ForegroundColor Green
                Write-Host ""
                
                # Automatically test connection after startup
                Write-Host "🔍 Automatically test MongoDB connections..." -ForegroundColor Cyan
                $connectionOk = Test-MongoDBConnection -hostname $mongoHost -port $mongoPort -username $mongoUsername -password $mongoPassword
                Write-Host ""
                
                if ($connectionOk) {
                    Write-Host "  ✅ MongoDB The connection test is successful and the service is ready" -ForegroundColor Green
                } else {
                    Write-Host "  ⚠️ MongoDB The process is running, but the connection test failed" -ForegroundColor Yellow
                    Write-Host "  💡 Tips: MongoDB May still be initializing, please try again later" -ForegroundColor Gray
                }
            } else {
                Write-Host "  ❌ MongoDB Startup failed, the process has exited or the port is not listening" -ForegroundColor Red
            }
        } else {
            Write-Host "  ❌ MongoDB Startup failed" -ForegroundColor Red
        }
        Write-Host ""
    } elseif ($start -and $procInfo.Exists) {
        Write-Host "  ℹ️ MongoDB Already running, no need to start" -ForegroundColor Cyan
        Write-Host ""
        
        # Test connection if already running
        if ($testConnection) {
            Write-Host "🔍 Test MongoDB connection..." -ForegroundColor Cyan
            $connectionOk = Test-MongoDBConnection -hostname $mongoHost -port $mongoPort -username $mongoUsername -password $mongoPassword
            Write-Host ""
        }
    }
    
    # Summary and Error Diagnostics
    Write-Host "📊 diagnostic summary:" -ForegroundColor Cyan
    $procInfo = Get-ProcessInfo -processName "mongod"
    $portInfo = Get-PortInfo -port $mongoPort
    
    if ($procInfo.Exists -and $portInfo.InUse -and $portInfo.ProcessName -eq "mongod") {
        Write-Host "  ✅ MongoDB Running normally" -ForegroundColor Green
    } else {
        Write-Host "  ❌ MongoDB There is a problem" -ForegroundColor Red
        Write-Host ""
        Write-Host "🔧 Error diagnosis and repair suggestions:" -ForegroundColor Yellow
        
        if (-not $procInfo.Exists) {
            Write-Host "  ❌ question: MongoDB Process is not running" -ForegroundColor Red
            Write-Host "    Possible reasons:" -ForegroundColor Gray
            Write-Host "      1. MongoDB Not started" -ForegroundColor Gray
            Write-Host "      2. MongoDB Crash immediately after startup" -ForegroundColor Gray
            Write-Host "      3. Data directory permissions issue" -ForegroundColor Gray
            Write-Host "      4. Data file corruption" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Use the -Start parameter to try to start: .\debug_services.ps1 -Service mongodb -Start -ShowLogs" -ForegroundColor Gray
            Write-Host "      - Check data directory permissions: $mongoData" -ForegroundColor Gray
            Write-Host "      - View the MongoDB log file (if it exists)" -ForegroundColor Gray
            Write-Host ""
        }
        
        if (-not $portInfo.InUse) {
            Write-Host "  ❌ question: port $mongoPort Not listening" -ForegroundColor Red
            Write-Host "    Possible reasons:" -ForegroundColor Gray
            Write-Host "      1. MongoDB Process not started" -ForegroundColor Gray
            Write-Host "      2. MongoDB Startup failed" -ForegroundColor Gray
            Write-Host "      3. Port configuration error" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Check the MONGODB_PORT configuration in the .env file" -ForegroundColor Gray
            Write-Host "      - Start using the -Start parameter MongoDB: .\debug_services.ps1 -Service mongodb -Start" -ForegroundColor Gray
            Write-Host "      - Check if the firewall blocks the port" -ForegroundColor Gray
            Write-Host ""
        }
        
        if ($portInfo.InUse -and $portInfo.ProcessName -ne "mongod") {
            Write-Host "  ⚠️ question: port $mongoPort occupied by other processes" -ForegroundColor Yellow
            Write-Host "    occupy process: $($portInfo.ProcessName) (PID: $($portInfo.PID))" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Stop the process occupying the port: Stop-Process -Id $($portInfo.PID) -Force" -ForegroundColor Gray
            Write-Host "      - Or modify MONGODB_PORT in the .env file to use other ports" -ForegroundColor Gray
            Write-Host ""
        }
        
        # Check data directory permissions
        if (Test-Path -LiteralPath $mongoData) {
            try {
                $testFile = Join-Path $mongoData "test_write_$(Get-Random).tmp"
                [System.IO.File]::WriteAllText($testFile, "test")
                Remove-Item $testFile -ErrorAction SilentlyContinue
            } catch {
                Write-Host "  ⚠️ question: Insufficient permissions on the data directory" -ForegroundColor Yellow
                Write-Host "    Directory: $mongoData" -ForegroundColor Gray
                Write-Host "    Repair suggestions:" -ForegroundColor Cyan
                Write-Host "      - Run as administrator PowerShell" -ForegroundColor Gray
                Write-Host "      - Check directory permissions: icacls `"$mongoData`"" -ForegroundColor Gray
                Write-Host "      - Grant the current user full control permissions" -ForegroundColor Gray
                Write-Host ""
            }
        }
    }
    Write-Host ""
}

# ============================================================================
# Redis Diagnostic Functions
# ============================================================================

function Test-RedisConnection($hostname, $port, $password) {
    Write-Host "  📡 Test Redis connection..." -ForegroundColor Gray
    
    # First test TCP connection
    if (-not (Test-TcpConnection -hostname $hostname -port $port -timeoutSeconds 5)) {
        Write-Host "    ❌ TCP Connection failed: Unable to connect to $hostname`:$port" -ForegroundColor Red
        return $false
    }
    Write-Host "    ✅ TCP Connection successful" -ForegroundColor Green
    
    # Try Python connection test if available
    $pythonExe = Join-Path $root 'vendors\python\python.exe'
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $root 'venv\Scripts\python.exe'
    }
    
    if (Test-Path $pythonExe) {
        try {
            $testScript = @"
import sys
try:
    import redis
    
    r = redis.Redis(
        host='$hostname',
        port=$port,
        password='$password',
        socket_connect_timeout=5,
        decode_responses=True
    )
    
    # Test connection
    r.ping()
    print('SUCCESS')
    sys.exit(0)
except redis.ConnectionError as e:
    print(f'CONNECTION_ERROR: {e}')
    sys.exit(1)
except redis.AuthenticationError as e:
    print(f'AUTH_ERROR: {e}')
    sys.exit(2)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(3)
"@
            $scriptFile = Join-Path $env:TEMP "test_redis_$(Get-Random).py"
            Set-Content -Path $scriptFile -Value $testScript -Encoding UTF8
            
            $output = & $pythonExe $scriptFile 2>&1
            Remove-Item $scriptFile -ErrorAction SilentlyContinue
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "    ✅ Redis Authentication connection successful" -ForegroundColor Green
                return $true
            } else {
                Write-Host "    ⚠️ Redis Connection test: $output" -ForegroundColor Yellow
                return $false
            }
        } catch {
            Write-Host "    ⚠️ Python Connection test failed: $_" -ForegroundColor Yellow
        }
    }
    
    return $true  # TCP connection succeeded
}

function Start-RedisWithLogs($redisExe, $root, $redisPort, $showLogs) {
    Write-Host "  🚀 start Redis..." -ForegroundColor Cyan
    
    # Ensure directories
    $redisData = Join-Path $root 'data\redis\data'
    Ensure-Dir $redisData
    Ensure-Dir (Join-Path $root 'runtime')
    
    # Create Redis config
    $redisConf = Join-Path $root 'runtime\redis.conf'
    $redisDataUnix = $redisData -replace '\\', '/'
    $conf = @(
        "bind 127.0.0.1",
        "port $redisPort",
        "dir $redisDataUnix",
        "requirepass tradingagents123",
        "appendonly yes",
        "save 900 1",
        "save 300 10",
        "save 60 10000"
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($redisConf, ($conf -join "`n"), $utf8NoBom)
    
    $redisConfRelative = "runtime\redis.conf"
    
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $redisExe
        $psi.Arguments = "`"$redisConfRelative`""
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.WorkingDirectory = $root
        
        $process = [System.Diagnostics.Process]::Start($psi)
        Write-Host "    Redis Process started (PID: $($process.Id))" -ForegroundColor Gray
        
        # Wait and capture output
        Start-Sleep -Seconds 5
        
        if ($showLogs) {
            Write-Host "    📋 Redis Startup log:" -ForegroundColor Cyan
            try {
                $stdout = ""
                $stderr = ""
                while ($process.StandardOutput.Peek() -gt -1) {
                    $line = $process.StandardOutput.ReadLine()
                    $stdout += $line + "`n"
                    Write-Host "      $line" -ForegroundColor Gray
                }
                while ($process.StandardError.Peek() -gt -1) {
                    $line = $process.StandardError.ReadLine()
                    $stderr += $line + "`n"
                    Write-Host "      $line" -ForegroundColor Yellow
                }
            } catch {
                # Ignore read errors
            }
        }
        
        if ($process.HasExited) {
            Write-Host "    ❌ Redis Process has exited (exit code: $($process.ExitCode))" -ForegroundColor Red
            
            # Try to read error output for diagnostics
            try {
                $errorOutput = ""
                while ($process.StandardError.Peek() -gt -1) {
                    $errorOutput += $process.StandardError.ReadLine() + "`n"
                }
                if ($errorOutput) {
                    Write-Host "    📋 error output:" -ForegroundColor Yellow
                    $errorOutput -split "`n" | ForEach-Object {
                        if ($_.Trim()) {
                            Write-Host "      $_" -ForegroundColor Yellow
                        }
                    }
                    
                    # Common error patterns
                    if ($errorOutput -match "Address already in use|bind.*failed") {
                        Write-Host "    💡 Diagnosis: The port may be occupied" -ForegroundColor Cyan
                    }
                    if ($errorOutput -match "Permission denied|access denied") {
                        Write-Host "    💡 Diagnosis: Insufficient permissions, please run as administrator" -ForegroundColor Cyan
                    }
                    if ($errorOutput -match "config.*error|parse.*error") {
                        Write-Host "    💡 Diagnosis: There may be errors in the configuration file, check runtime\redis.conf" -ForegroundColor Cyan
                    }
                }
            } catch {
                # Ignore read errors
            }
            
            return $null
        } else {
            Write-Host "    ✅ Redis Process is running" -ForegroundColor Green
            return $process
        }
    } catch {
        Write-Host "    ❌ Failed to start Redis: $_" -ForegroundColor Red
        return $null
    }
}

function Diagnose-Redis($envMap, $root, $start, $showLogs, $testConnection) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Redis Diagnosis" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    $redisPort = if ($envMap.ContainsKey('REDIS_PORT')) { [int]$envMap['REDIS_PORT'] } else { 6379 }
    $redisHost = if ($envMap.ContainsKey('REDIS_HOST')) { $envMap['REDIS_HOST'] } else { "localhost" }
    $redisPassword = if ($envMap.ContainsKey('REDIS_PASSWORD')) { $envMap['REDIS_PASSWORD'] } else { "tradingagents123" }
    
    Write-Host "📋 Configuration information:" -ForegroundColor Cyan
    Write-Host "  Host: $redisHost" -ForegroundColor Gray
    Write-Host "  port: $redisPort" -ForegroundColor Gray
    Write-Host ""
    
    # Check executable
    $redisExe = Join-Path $root 'vendors\redis\Redis-8.2.2-Windows-x64-msys2\redis-server.exe'
    Write-Host "🔍 Check the Redis executable file..." -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $redisExe)) {
        Write-Host "  ❌ Redis Executable file does not exist: $redisExe" -ForegroundColor Red
        Write-Host "  💡 Suggestions: Check whether the installation directory is correct" -ForegroundColor Yellow
        return
    }
    Write-Host "  ✅ Redis Executable file exists" -ForegroundColor Green
    Write-Host ""
    
    # Check data directory
    $redisData = Join-Path $root 'data\redis\data'
    Write-Host "🔍 Check data directory..." -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $redisData)) {
        Write-Host "  ⚠️ The data directory does not exist and will be created automatically.: $redisData" -ForegroundColor Yellow
        Ensure-Dir $redisData
    } else {
        Write-Host "  ✅ data directory exists: $redisData" -ForegroundColor Green
    }
    Write-Host ""
    
    # Check process
    Write-Host "🔍 Check the Redis process..." -ForegroundColor Cyan
    $procInfo = Get-ProcessInfo -processName "redis-server"
    if ($procInfo.Exists) {
        Write-Host "  ✅ Redis Process is running" -ForegroundColor Green
        Write-Host "    PID: $($procInfo.PID)" -ForegroundColor Gray
        Write-Host "    path: $($procInfo.Path)" -ForegroundColor Gray
        Write-Host "    Start time: $($procInfo.StartTime)" -ForegroundColor Gray
    } else {
        Write-Host "  ❌ Redis Process is not running" -ForegroundColor Red
    }
    Write-Host ""
    
    # Check port
    Write-Host "🔍 Check port $redisPort..." -ForegroundColor Cyan
    $portInfo = Get-PortInfo -port $redisPort
    if ($portInfo.InUse) {
        Write-Host "  ✅ port $redisPort Listening" -ForegroundColor Green
        Write-Host "    process: $($portInfo.ProcessName) (PID: $($portInfo.PID))" -ForegroundColor Gray
        if ($portInfo.ProcessName -ne "redis-server") {
            Write-Host "    ⚠️ warning: The port is occupied by other processes!" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ❌ port $redisPort Not listening" -ForegroundColor Red
    }
    Write-Host ""
    
    # Test connection
    if ($testConnection) {
        Test-RedisConnection -hostname $redisHost -port $redisPort -password $redisPassword | Out-Null
        Write-Host ""
    }
    
    # Start if requested and not running
    if ($start -and -not $procInfo.Exists) {
        Write-Host "🔧 Try to start Redis..." -ForegroundColor Cyan
        $process = Start-RedisWithLogs -redisExe $redisExe -root $root -redisPort $redisPort -showLogs $showLogs
        
        if ($process) {
            Write-Host ""
            Write-Host "  ⏳ Wait for Redis startup to complete..." -ForegroundColor Yellow
            Start-Sleep -Seconds 3
            
            # Re-check
            $procInfo = Get-ProcessInfo -processName "redis-server"
            if ($procInfo.Exists) {
                Write-Host "  ✅ Redis Started successfully!" -ForegroundColor Green
            } else {
                Write-Host "  ❌ Redis Startup failed, process has exited" -ForegroundColor Red
            }
        } else {
            Write-Host "  ❌ Redis Startup failed" -ForegroundColor Red
        }
        Write-Host ""
    } elseif ($start -and $procInfo.Exists) {
        Write-Host "  ℹ️ Redis Already running, no need to start" -ForegroundColor Cyan
        Write-Host ""
    }
    
    # Summary and Error Diagnostics
    Write-Host "📊 diagnostic summary:" -ForegroundColor Cyan
    $procInfo = Get-ProcessInfo -processName "redis-server"
    $portInfo = Get-PortInfo -port $redisPort
    
    if ($procInfo.Exists -and $portInfo.InUse -and $portInfo.ProcessName -eq "redis-server") {
        Write-Host "  ✅ Redis Running normally" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Redis There is a problem" -ForegroundColor Red
        Write-Host ""
        Write-Host "🔧 Error diagnosis and repair suggestions:" -ForegroundColor Yellow
        
        if (-not $procInfo.Exists) {
            Write-Host "  ❌ question: Redis Process is not running" -ForegroundColor Red
            Write-Host "    Possible reasons:" -ForegroundColor Gray
            Write-Host "      1. Redis Not started" -ForegroundColor Gray
            Write-Host "      2. Redis Crash immediately after startup" -ForegroundColor Gray
            Write-Host "      3. Configuration file error" -ForegroundColor Gray
            Write-Host "      4. Data directory permissions issue" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Use the -Start parameter to try to start: .\debug_services.ps1 -Service redis -Start -ShowLogs" -ForegroundColor Gray
            Write-Host "      - Check configuration file: $root\runtime\redis.conf" -ForegroundColor Gray
            Write-Host "      - Check data directory permissions: $redisData" -ForegroundColor Gray
            Write-Host ""
        }
        
        if (-not $portInfo.InUse) {
            Write-Host "  ❌ question: port $redisPort Not listening" -ForegroundColor Red
            Write-Host "    Possible reasons:" -ForegroundColor Gray
            Write-Host "      1. Redis Process not started" -ForegroundColor Gray
            Write-Host "      2. Redis Startup failed" -ForegroundColor Gray
            Write-Host "      3. Port configuration error" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Check the REDIS_PORT configuration in the .env file" -ForegroundColor Gray
            Write-Host "      - Start using the -Start parameter Redis: .\debug_services.ps1 -Service redis -Start" -ForegroundColor Gray
            Write-Host "      - Check if the firewall blocks the port" -ForegroundColor Gray
            Write-Host ""
        }
        
        if ($portInfo.InUse -and $portInfo.ProcessName -ne "redis-server") {
            Write-Host "  ⚠️ question: port $redisPort occupied by other processes" -ForegroundColor Yellow
            Write-Host "    occupy process: $($portInfo.ProcessName) (PID: $($portInfo.PID))" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Stop the process occupying the port: Stop-Process -Id $($portInfo.PID) -Force" -ForegroundColor Gray
            Write-Host "      - Or modify REDIS_PORT in the .env file to use other ports" -ForegroundColor Gray
            Write-Host ""
        }
        
        # Check Redis config file
        $redisConf = Join-Path $root 'runtime\redis.conf'
        if (-not (Test-Path -LiteralPath $redisConf)) {
            Write-Host "  ⚠️ question: Redis Configuration file does not exist" -ForegroundColor Yellow
            Write-Host "    File: $redisConf" -ForegroundColor Gray
            Write-Host "    Repair suggestions:" -ForegroundColor Cyan
            Write-Host "      - Configuration files are automatically created at startup" -ForegroundColor Gray
            Write-Host "      - Start using the -Start parameter Redis: .\debug_services.ps1 -Service redis -Start" -ForegroundColor Gray
            Write-Host ""
        }
        
        # Check data directory permissions
        if (Test-Path -LiteralPath $redisData) {
            try {
                $testFile = Join-Path $redisData "test_write_$(Get-Random).tmp"
                [System.IO.File]::WriteAllText($testFile, "test")
                Remove-Item $testFile -ErrorAction SilentlyContinue
            } catch {
                Write-Host "  ⚠️ question: Insufficient permissions on the data directory" -ForegroundColor Yellow
                Write-Host "    Directory: $redisData" -ForegroundColor Gray
                Write-Host "    Repair suggestions:" -ForegroundColor Cyan
                Write-Host "      - Run as administrator PowerShell" -ForegroundColor Gray
                Write-Host "      - Check directory permissions: icacls `"$redisData`"" -ForegroundColor Gray
                Write-Host "      - Grant the current user full control permissions" -ForegroundColor Gray
                Write-Host ""
            }
        }
    }
    Write-Host ""
}

# ============================================================================
# Main Script
# ============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TradingAgents-CN Service Diagnostic Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Load environment variables
Write-Host "📋 Load configuration file..." -ForegroundColor Cyan
Write-Host "  Project root directory: $root" -ForegroundColor Gray
if (Test-Path $envPath) {
    Write-Host "  ✅ Find the .env file: $envPath" -ForegroundColor Green
} else {
    Write-Host "  ⚠️ .env file not found: $envPath" -ForegroundColor Yellow
    Write-Host "  Default configuration will be used" -ForegroundColor Gray
}
Write-Host ""

$envMap = Load-Env $envPath

# Run diagnostics
if ($Service -eq "mongodb" -or $Service -eq "all") {
    Diagnose-MongoDB -envMap $envMap -root $root -start $Start -showLogs $ShowLogs -testConnection $TestConnection
}

if ($Service -eq "redis" -or $Service -eq "all") {
    Diagnose-Redis -envMap $envMap -root $root -start $Start -showLogs $ShowLogs -testConnection $TestConnection
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Diagnosis completed" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
