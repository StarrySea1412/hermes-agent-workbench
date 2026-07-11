#!/bin/bash
set -e

echo "========================================="
echo "  Hermes Agent 安装脚本"
echo "========================================="

# 检查 Python 版本
check_python() {
    if command -v python3.11 &> /dev/null; then
        PYTHON_CMD="python3.11"
    elif command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ]; then
            PYTHON_CMD="python3"
        else
            echo "错误: Hermes Agent 需要 Python 3.11 或更高版本"
            echo "当前版本: $PYTHON_VERSION"
            echo "请访问 https://www.python.org/downloads/ 安装 Python 3.11+"
            exit 1
        fi
    else
        echo "错误: 未找到 Python 3"
        echo "请访问 https://www.python.org/downloads/ 安装 Python 3.11+"
        exit 1
    fi

    echo "✓ 检测到 Python: $($PYTHON_CMD --version)"
}

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="wsl"
    else
        echo "警告: 未识别的操作系统 $OSTYPE，尝试以 Linux 模式继续..."
        OS="linux"
    fi
    echo "✓ 操作系统: $OS"
}

# 安装 Hermes Agent
install_hermes() {
    echo ""
    echo "开始安装 Hermes Agent..."
    echo "这可能需要几分钟时间，请耐心等待..."
    echo ""

    # 使用官方安装脚本
    if curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash; then
        echo ""
        echo "✓ Hermes Agent 安装成功！"
    else
        echo ""
        echo "✗ Hermes Agent 安装失败"
        echo "请检查网络连接或手动访问 https://github.com/NousResearch/hermes-agent"
        exit 1
    fi
}

# 验证安装
verify_installation() {
    echo ""
    echo "验证安装..."

    # 重新加载环境变量
    if [ -f "$HOME/.bashrc" ]; then
        source "$HOME/.bashrc"
    fi

    if command -v hermes &> /dev/null; then
        HERMES_VERSION=$(hermes --version 2>&1 || echo "unknown")
        echo "✓ Hermes 命令可用"
        echo "  版本: $HERMES_VERSION"
    else
        echo "✗ Hermes 命令不可用"
        echo "请执行以下命令重新加载 shell 环境："
        echo "  source ~/.bashrc"
        echo "然后运行: hermes --version"
        exit 1
    fi
}

# 创建集成配置提示
show_next_steps() {
    echo ""
    echo "========================================="
    echo "  安装完成！后续步骤："
    echo "========================================="
    echo ""
    echo "1. 重新加载 shell 环境（如果 hermes 命令不可用）："
    echo "   source ~/.bashrc"
    echo ""
    echo "2. 运行配置同步脚本（在 Django 后端目录）："
    echo "   cd backend"
    echo "   python scripts/sync_hermes_config.py"
    echo ""
    echo "3. 验证 Hermes 连接："
    echo "   hermes"
    echo ""
    echo "详细文档: https://hermes-agent.nousresearch.com/docs/"
    echo ""
}

# 主流程
main() {
    check_python
    detect_os
    install_hermes
    verify_installation
    show_next_steps
}

main
