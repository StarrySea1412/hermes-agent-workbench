# Hermes Agent 安装脚本 (PowerShell for Windows)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Hermes Agent 安装脚本 (Windows)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# 检查是否在 WSL 环境中
function Test-WSL {
    if ($env:WSL_DISTRO_NAME) {
        return $true
    }
    return $false
}

# 检查 Python 版本
function Test-Python {
    Write-Host "检查 Python 版本..." -ForegroundColor Yellow

    $pythonCommands = @("python3.11", "python3", "python")
    $pythonCmd = $null

    foreach ($cmd in $pythonCommands) {
        try {
            $version = & $cmd --version 2>&1
            if ($version -match "Python (\d+)\.(\d+)") {
                $major = [int]$matches[1]
                $minor = [int]$matches[2]

                if ($major -eq 3 -and $minor -ge 11) {
                    $pythonCmd = $cmd
                    Write-Host "✓ 检测到 $cmd : $version" -ForegroundColor Green
                    return $pythonCmd
                }
            }
        } catch {
            continue
        }
    }

    Write-Host "✗ 错误: 未找到 Python 3.11 或更高版本" -ForegroundColor Red
    Write-Host "请访问 https://www.python.org/downloads/ 安装 Python 3.11+" -ForegroundColor Yellow
    exit 1
}

# 检查 WSL 安装
function Test-WSLInstalled {
    try {
        $wslVersion = wsl --version 2>&1
        return $true
    } catch {
        return $false
    }
}

# 主安装流程
function Install-Hermes {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "  重要提示" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Hermes Agent 原生不支持 Windows，需要通过 WSL2 运行。" -ForegroundColor Yellow
    Write-Host ""

    # 检查是否已在 WSL 中
    if (Test-WSL) {
        Write-Host "检测到 WSL 环境，继续安装..." -ForegroundColor Green
        Test-Python
        Write-Host ""
        Write-Host "请在 WSL 终端中运行以下命令安装 Hermes:" -ForegroundColor Yellow
        Write-Host "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash" -ForegroundColor Cyan
        Write-Host ""
        exit 0
    }

    # 检查 WSL 是否安装
    if (-not (Test-WSLInstalled)) {
        Write-Host "✗ 未检测到 WSL2" -ForegroundColor Red
        Write-Host ""
        Write-Host "请按照以下步骤安装 WSL2:" -ForegroundColor Yellow
        Write-Host "1. 以管理员身份打开 PowerShell" -ForegroundColor White
        Write-Host "2. 运行命令: wsl --install" -ForegroundColor Cyan
        Write-Host "3. 重启计算机" -ForegroundColor White
        Write-Host "4. 重新运行此脚本" -ForegroundColor White
        Write-Host ""
        Write-Host "详细文档: https://learn.microsoft.com/zh-cn/windows/wsl/install" -ForegroundColor Yellow
        Write-Host ""

        $response = Read-Host "是否现在安装 WSL2? (Y/N)"
        if ($response -eq "Y" -or $response -eq "y") {
            Write-Host "正在安装 WSL2..." -ForegroundColor Yellow
            wsl --install
            Write-Host ""
            Write-Host "✓ WSL2 安装命令已执行" -ForegroundColor Green
            Write-Host "请重启计算机后，在 WSL 终端中运行:" -ForegroundColor Yellow
            Write-Host "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash" -ForegroundColor Cyan
        }
        exit 0
    }

    # WSL 已安装，提示用户在 WSL 中运行
    Write-Host "✓ 检测到 WSL2 已安装" -ForegroundColor Green
    Write-Host ""
    Write-Host "请打开 WSL 终端并运行以下命令:" -ForegroundColor Yellow
    Write-Host "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "或者，从 PowerShell 直接运行:" -ForegroundColor Yellow
    Write-Host "  wsl curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash" -ForegroundColor Cyan
    Write-Host ""
}

# 执行安装
Install-Hermes

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  后续步骤" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "安装完成后，请运行配置同步脚本:" -ForegroundColor Yellow
Write-Host "  cd backend" -ForegroundColor Cyan
Write-Host "  python scripts/sync_hermes_config.py" -ForegroundColor Cyan
Write-Host ""
