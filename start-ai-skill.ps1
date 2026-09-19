$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "ai-skill-app"
$HermesHome = Join-Path $Root ".hermes-runtime"
$BackendPython = Join-Path $Backend "venv\Scripts\python.exe"

# Ensure local SQLite schema is current (no-op if already applied)
try {
    & $BackendPython (Join-Path $Backend "manage.py") migrate --noinput | Out-Null
} catch {
    Write-Host "Warning: migrate failed: $($_.Exception.Message)"
}


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
# 后端调用网关用的是同一个服务密钥，必须保持一致，否则网关返回 401
$env:HERMES_GATEWAY_KEY = "dev-test-key-for-local"
if (!$env:API_SERVER_MODEL_NAME) {
    $modelFromConfig = Get-HermesModelName -ConfigPath (Join-Path $HermesHome "config.yaml")
    if ($modelFromConfig) {
        $env:API_SERVER_MODEL_NAME = $modelFromConfig
    }
}
$env:API_SERVER_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
$env:HERMES_ACCEPT_HOOKS = "1"

# Anthropic 协议的网关运行时需要 ANTHROPIC_API_KEY 环境变量（hermes 入口强制校验），
# 从 config.yaml 取同一家密钥注入，避免设置页切换供应商后网关起不来。
# provider=zai 时 hermes 改从 GLM_API_KEY 取密钥，同样从 config.yaml 注入。
# provider 必须保持 zai（而非 anthropic）：hermes 的 anthropic 适配层会把模型名里的
# 点号改写成横杠（grok-4.6 -> grok-4-6），中转站按原始名提供渠道，改写后一律 503
# "No available channel"。zai 供应商保留点号，是点号模型名的既定用法。
$gatewayConfigPath = Join-Path $HermesHome "config.yaml"
if ((Test-Path -LiteralPath $gatewayConfigPath) -and -not $env:ANTHROPIC_API_KEY) {
    $configText = Get-Content -LiteralPath $gatewayConfigPath -Raw -ErrorAction SilentlyContinue
    $keyMatch = [regex]::Match($configText, '(?m)^\s*api_key:\s*(\S+)')
    if ($keyMatch.Success) {
        $resolvedKey = $keyMatch.Groups[1].Value.Trim()
        if (-not $env:ANTHROPIC_API_KEY) {
            $env:ANTHROPIC_API_KEY = $resolvedKey
        }
        if ($configText -match '(?m)^\s*provider:\s*zai\s*$' -and -not $env:GLM_API_KEY) {
            $env:GLM_API_KEY = $resolvedKey
        }
    }
}

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
