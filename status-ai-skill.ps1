$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Services = @(
    @{ Name = "frontend"; Port = 5173; Url = "http://127.0.0.1:5173/" },
    @{ Name = "backend"; Port = 8000; Url = "http://127.0.0.1:8000/api/health" },
    @{ Name = "hermes"; Port = 8642; Url = "http://127.0.0.1:8642/v1/models"; Headers = @{ Authorization = "Bearer dev-test-key-for-local" } }
)

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

function Test-Service {
    param([hashtable]$Service)

    $listener = Get-PortListeners -Ports @($Service.Port) | Select-Object -First 1

    $httpStatus = ""
    $errorMessage = ""
    $headers = @{}
    if ($Service.ContainsKey("Headers")) {
        $headers = $Service.Headers
    }

    try {
        $response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri $Service.Url `
            -Headers $headers `
            -TimeoutSec 5
        $httpStatus = [string]$response.StatusCode
    } catch {
        $httpStatus = "FAILED"
        $errorMessage = $_.Exception.Message
    }

    [PSCustomObject]@{
        Service = $Service.Name
        Port = $Service.Port
        Listening = [bool]$listener
        ProcessId = if ($listener) { $listener.OwningProcess } else { "" }
        HttpStatus = $httpStatus
        Error = $errorMessage
    }
}

Write-Host "AI-skill service status"
Write-Host "Root: $Root"
Write-Host ""

$Services | ForEach-Object { Test-Service -Service $_ } | Format-Table -AutoSize

Write-Host ""
Write-Host "Recent logs"

$LogFiles = @(
    Join-Path $Root "backend\codex-backend-run.err.log"
    Join-Path $Root "ai-skill-app\codex-frontend-run.err.log"
    Join-Path $Root "hermes-gateway.err.log"
)

foreach ($logFile in $LogFiles) {
    Write-Host ""
    Write-Host "== $logFile =="
    if (Test-Path -LiteralPath $logFile) {
        Get-Content -LiteralPath $logFile -Tail 40 -ErrorAction SilentlyContinue |
            ForEach-Object { ($_ -replace "`0", "").TrimEnd() } |
            Where-Object { $_ -ne "" }
    } else {
        Write-Host "not found"
    }
}
