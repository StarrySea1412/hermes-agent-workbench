$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "ai-skill-app"
$HermesHome = Join-Path $Root ".hermes-runtime"
$BackendPython = Join-Path $Backend "venv\Scripts\python.exe"

function Stop-PortProcess {
    param([int]$Port)
    $connections = Get-PortListeners -Ports @($Port)
    foreach ($connection in $connections) {
        Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

function Get-PortListeners {
    param([int[]]$Ports)

    $listeners = @()
    $seen = @{}

    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $Ports -contains $_.LocalPort } |
        ForEach-Object {
            $key = "$($_.LocalPort)-$($_.OwningProcess)"
            if (!$seen.ContainsKey($key)) {
                $seen[$key] = $true
                $listeners += [PSCustomObject]@{
                    LocalAddress = $_.LocalAddress
                    LocalPort = $_.LocalPort
                    OwningProcess = $_.OwningProcess
                }
            }
        }

    try {
        $netstatLines = & netstat.exe -ano -p tcp 2>$null
        foreach ($line in $netstatLines) {
            if ($line -match '^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$') {
                $port = [int]$Matches[2]
                $processId = [int]$Matches[3]
                $key = "$port-$processId"
                if (($Ports -contains $port) -and !$seen.ContainsKey($key)) {
                    $seen[$key] = $true
                    $listeners += [PSCustomObject]@{
                        LocalAddress = $Matches[1]
                        LocalPort = $port
                        OwningProcess = $processId
                    }
                }
            }
        }
    } catch {
        return $listeners
    }

    return $listeners
}

function Test-Http {
    param(
        [string]$Name,
        [string]$Url,
        [hashtable]$Headers = @{}
    )
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -TimeoutSec 8
        [PSCustomObject]@{ Service = $Name; Status = $response.StatusCode; Url = $Url }
    } catch {
        [PSCustomObject]@{ Service = $Name; Status = "FAILED"; Url = $Url; Error = $_.Exception.Message }
    }
}

function Get-HermesModelName {
    param([string]$ConfigPath)
    if (!(Test-Path -LiteralPath $ConfigPath)) {
        return ""
    }
    $lines = Get-Content -LiteralPath $ConfigPath -ErrorAction SilentlyContinue
    foreach ($line in $lines) {
        if ($line -match '^\s*(default|name):\s*(.+?)\s*$') {
            return $Matches[2].Trim(" `"'")
        }
    }
    return ""
}

function Resolve-HermesExecutable {
    $command = Get-Command hermes -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $searchRoots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        (Join-Path $env:APPDATA "Python")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($searchRoot in $searchRoots) {
        $candidate = Get-ChildItem -LiteralPath $searchRoot -Directory -Filter "Python*" -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "Scripts\hermes.exe" } |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if ($candidate) {
            return $candidate
        }
    }

    return ""
}

foreach ($port in @(5173, 8000, 8642)) {
    Stop-PortProcess -Port $port
}
Start-Sleep -Seconds 2

$env:HERMES_HOME = $HermesHome
$env:API_SERVER_ENABLED = "true"
$env:API_SERVER_HOST = "127.0.0.1"
$env:API_SERVER_PORT = "8642"
$env:API_SERVER_KEY = "dev-test-key-for-local"
if (!$env:API_SERVER_MODEL_NAME) {
    $modelFromConfig = Get-HermesModelName -ConfigPath (Join-Path $HermesHome "config.yaml")
    if ($modelFromConfig) {
        $env:API_SERVER_MODEL_NAME = $modelFromConfig
    }
}
$env:API_SERVER_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
$env:HERMES_ACCEPT_HOOKS = "1"

$HermesExe = Resolve-HermesExecutable
if (!$HermesExe) {
    throw "Hermes executable not found. Install Hermes or add the 'hermes' command to PATH."
}
if (!(Test-Path -LiteralPath $BackendPython)) {
    throw "Backend Python not found: $BackendPython"
}

Start-Process -FilePath $HermesExe `
    -ArgumentList @("gateway", "run", "--accept-hooks") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Root "hermes-gateway.out.log") `
    -RedirectStandardError (Join-Path $Root "hermes-gateway.err.log")

Start-Process -FilePath $BackendPython `
    -ArgumentList @("manage.py", "runserver", "127.0.0.1:8000") `
    -WorkingDirectory $Backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Backend "codex-backend-run.out.log") `
    -RedirectStandardError (Join-Path $Backend "codex-backend-run.err.log")

Start-Process -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
    -WorkingDirectory $Frontend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Frontend "codex-frontend-run.out.log") `
    -RedirectStandardError (Join-Path $Frontend "codex-frontend-run.err.log")

Start-Sleep -Seconds 8

Get-PortListeners -Ports @(5173, 8000, 8642) |
    Select-Object LocalAddress, LocalPort, OwningProcess

Test-Http -Name "frontend" -Url "http://127.0.0.1:5173/"
Test-Http -Name "backend" -Url "http://127.0.0.1:8000/api/health"
Test-Http -Name "hermes" -Url "http://127.0.0.1:8642/v1/models" -Headers @{ Authorization = "Bearer dev-test-key-for-local" }

Write-Host "AI-skill started: http://127.0.0.1:5173/"
