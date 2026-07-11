$ErrorActionPreference = "SilentlyContinue"

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

    return $listeners
}

foreach ($port in @(5173, 8000, 8642)) {
    $connections = Get-PortListeners -Ports @($port)
    foreach ($connection in $connections) {
        Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

Get-PortListeners -Ports @(5173, 8000, 8642) |
    Select-Object LocalAddress, LocalPort, OwningProcess

Write-Host "AI-skill services stopped."
