param(
    [switch]$SkipBuild,
    [switch]$SkipBackendTests,
    [switch]$CheckServices
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "ai-skill-app"
$Backend = Join-Path $Root "backend"
$BackendPython = Join-Path $Backend "venv\Scripts\python.exe"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    & $Command
}

function Assert-File {
    param(
        [string]$Path,
        [string]$Label
    )

    if (!(Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory = ""
    )

    $previousLocation = Get-Location
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        if ($WorkingDirectory) {
            Push-Location $WorkingDirectory
        }
        $ErrorActionPreference = "Continue"
        & $FilePath @ArgumentList 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $message = $_.Exception.Message
            } else {
                $message = [string]$_
            }
            if ($message -and $message -ne "System.Management.Automation.RemoteException") {
                Write-Host $message
            }
        }
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "Command failed with exit code ${exitCode}: $FilePath $($ArgumentList -join ' ')"
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        while ((Get-Location).Path -ne $previousLocation.Path) {
            Pop-Location
        }
    }
}

Write-Host "AI-skill verification"
Write-Host "Root: $Root"

Assert-File -Path (Join-Path $Frontend "package.json") -Label "Frontend package"
Assert-File -Path (Join-Path $Backend "manage.py") -Label "Backend manage.py"
Assert-File -Path $BackendPython -Label "Backend Python"

Invoke-Step -Name "PowerShell script syntax" -Command {
    $scripts = @(
        "start-ai-skill.ps1",
        "stop-ai-skill.ps1",
        "status-ai-skill.ps1",
        "verify-ai-skill.ps1"
    )

    foreach ($script in $scripts) {
        $path = Join-Path $Root $script
        Assert-File -Path $path -Label $script
        $null = [scriptblock]::Create((Get-Content -LiteralPath $path -Raw -Encoding UTF8))
        Write-Host "OK $script"
    }
}

Invoke-Step -Name "Frontend UI quality" -Command {
    Invoke-Native -FilePath "npm.cmd" -ArgumentList @("run", "check:ui") -WorkingDirectory $Frontend
}

Invoke-Step -Name "Frontend lint" -Command {
    Invoke-Native -FilePath "npm.cmd" -ArgumentList @("run", "lint") -WorkingDirectory $Frontend
}

if (!$SkipBuild) {
    Invoke-Step -Name "Frontend build" -Command {
        Invoke-Native -FilePath "npm.cmd" -ArgumentList @("run", "build") -WorkingDirectory $Frontend
    }
} else {
    Write-Host ""
    Write-Host "== Frontend build skipped =="
}

if (!$SkipBackendTests) {
    Invoke-Step -Name "Backend delivery tests" -Command {
        Invoke-Native `
            -FilePath $BackendPython `
            -ArgumentList @(
                "manage.py",
                "test",
                "apps.projects.tests.ConversationHermesStreamTests",
                "apps.ai_config.tests.AIModelListApiTests",
                "apps.agents.tests.AgentRunApiTests.test_doc_export_persists_generated_markdown_file",
                "apps.agents.tests.AgentRunApiTests.test_doc_export_persists_generated_xlsx_file",
                "--keepdb"
            ) `
            -WorkingDirectory $Backend
    }
} else {
    Write-Host ""
    Write-Host "== Backend delivery tests skipped =="
}

if ($CheckServices) {
    Invoke-Step -Name "Service status" -Command {
        & (Join-Path $Root "status-ai-skill.ps1")
    }
}

Write-Host ""
Write-Host "AI-skill verification completed."
