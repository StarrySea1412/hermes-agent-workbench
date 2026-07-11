#!/usr/bin/env python3
"""
Hermes Agent 配置同步脚本

从 Django AIConfig 读取配置，生成 Hermes Agent 所需的 ~/.hermes/config.yaml
支持手动同步或在 Django 启动时自动同步
"""

import os
import sys
import yaml
from pathlib import Path

# 添加 Django 项目路径
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# 配置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_skill_project.settings')

import django
django.setup()

from apps.ai_config.models import AIConfig
from services.encryption_service import get_encryption


def get_hermes_config_path():
    """获取 Hermes 配置文件路径"""
    home = Path.home()
    hermes_dir = home / ".hermes"
    hermes_dir.mkdir(exist_ok=True)
    return hermes_dir / "config.yaml"


def map_provider_to_hermes(provider):
    """映射项目 provider 到 Hermes 支持的格式"""
    provider_map = {
        'openai': 'openai',
        'anthropic': 'anthropic',
        'azure': 'openai',  # Azure 使用 OpenAI 兼容接口
        'deepseek': 'openai',
        'gemini': 'openai',
        'kimi': 'openai',
        'zhipu': 'openai',
        'minimax': 'openai',
        'qwen': 'openai',
        'openrouter': 'openrouter',
        'ollama': 'ollama',
        'custom': 'openai',
    }
    return provider_map.get(provider.lower(), 'openai')


def load_existing_config(config_path):
    """加载现有 Hermes 配置（如果存在）"""
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"警告: 无法读取现有配置: {e}")
    return {}


def sync_config(user_id=None, dry_run=False):
    """
    同步配置到 Hermes

    Args:
        user_id: 指定用户 ID，如果为 None 则使用第一个活跃配置
        dry_run: 是否只预览不实际写入
    """
    # 获取 AI 配置
    if user_id:
        ai_configs = AIConfig.objects.filter(user_id=user_id, is_active=True)
    else:
        ai_configs = AIConfig.objects.filter(is_active=True)

    if not ai_configs.exists():
        print("错误: 未找到活跃的 AI 配置")
        print("请先在项目 Settings 页面配置 AI 模型")
        return False

    config = ai_configs.first()
    print(f"✓ 找到配置: {config.user.username} - {config.provider}")

    # 解密 API Key
    encryption = get_encryption()
    try:
        api_key = encryption.decrypt(config.api_key_encrypted)
    except Exception as e:
        print(f"错误: 无法解密 API Key: {e}")
        return False

    # 映射 provider
    hermes_provider = map_provider_to_hermes(config.provider)

    # 获取配置路径
    config_path = get_hermes_config_path()

    # 加载现有配置（保留其他设置）
    existing_config = load_existing_config(config_path)

    # 构建 Hermes 配置
    hermes_config = existing_config.copy()

    # 更新模型配置
    hermes_config['model'] = {
        'provider': hermes_provider,
        'name': config.model_name,
        'api_key': api_key,
        'temperature': config.temperature,
        'max_tokens': max(config.max_tokens, 64000),  # Hermes 最低要求
    }

    # 如果有自定义 base_url，添加到配置
    if config.base_url and config.base_url != 'https://api.openai.com/v1':
        hermes_config['model']['base_url'] = config.base_url

    # 确保技能路径配置存在
    if 'skills' not in hermes_config:
        hermes_config['skills'] = {}

    if 'paths' not in hermes_config['skills']:
        # 添加项目技能目录
        project_root = Path(__file__).parent.parent
        hermes_config['skills']['paths'] = [
            str(project_root / "hermes_skills" / "auto"),
            str(project_root / "hermes_skills" / "manual"),
        ]

    # 预览配置
    print("\n" + "="*50)
    print("Hermes 配置预览:")
    print("="*50)

    # 隐藏敏感信息
    preview_config = hermes_config.copy()
    if 'model' in preview_config and 'api_key' in preview_config['model']:
        preview_config['model']['api_key'] = '***' + api_key[-8:] if len(api_key) > 8 else '***'

    print(yaml.dump(preview_config, default_flow_style=False, allow_unicode=True))
    print("="*50)

    if dry_run:
        print("\n[DRY RUN] 未写入实际配置")
        return True

    # 写入配置
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(hermes_config, f, default_flow_style=False, allow_unicode=True)
        print(f"\n✓ 配置已写入: {config_path}")
        return True
    except Exception as e:
        print(f"\n错误: 无法写入配置文件: {e}")
        return False


def verify_hermes_installation():
    """验证 Hermes 是否已安装"""
    import shutil
    if shutil.which('hermes'):
        print("✓ Hermes 命令已安装")
        return True
    else:
        print("✗ 未找到 Hermes 命令")
        print("请先运行安装脚本:")
        print("  ./scripts/install_hermes.sh  (Linux/macOS/WSL)")
        print("  .\\scripts\\install_hermes.ps1  (Windows PowerShell)")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description='同步 AI 配置到 Hermes Agent')
    parser.add_argument('--user-id', type=int, help='指定用户 ID')
    parser.add_argument('--dry-run', action='store_true', help='预览配置但不写入')
    parser.add_argument('--skip-verify', action='store_true', help='跳过 Hermes 安装验证')

    args = parser.parse_args()

    print("="*50)
    print("  Hermes Agent 配置同步")
    print("="*50)
    print()

    # 验证 Hermes 安装
    if not args.skip_verify:
        if not verify_hermes_installation():
            sys.exit(1)
        print()

    # 同步配置
    success = sync_config(user_id=args.user_id, dry_run=args.dry_run)

    if success and not args.dry_run:
        print("\n" + "="*50)
        print("  后续步骤:")
        print("="*50)
        print("\n1. 测试 Hermes 连接:")
        print("   hermes")
        print("\n2. 在项目中使用 Hermes 生成章节内容")
        print("   (前端选择 'Hermes 深度生成' 模式)")
        print()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
