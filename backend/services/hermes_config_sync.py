import logging
import os
from pathlib import Path

import yaml

from apps.ai_config.models import AIConfig
from services.encryption_service import get_encryption
from services.model_fetch_service import MODEL_FETCH_USER_AGENT, normalize_openai_base_url

logger = logging.getLogger("api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_HERMES_BASE_URL = "https://api.openai.com/v1"
DEFAULT_SKILL_PATHS = [
    PROJECT_ROOT / "hermes_skills" / "auto",
    PROJECT_ROOT / "hermes_skills" / "manual",
]
ANTHROPIC_PROVIDERS = {"anthropic"}

PROVIDER_MAP = {
    "openai": "openai-api",
    "anthropic": "anthropic",
    "azure": "custom",
    "deepseek": "custom",
    "gemini": "custom",
    "kimi": "custom",
    "minimax": "custom",
    "ollama": "custom",
    "openrouter": "openrouter",
    "qwen": "custom",
    "zhipu": "custom",
    "custom": "custom",
}


def map_provider_to_hermes(provider, base_url=""):
    provider_key = (provider or "openai").lower()
    normalized_base_url = (base_url or "").rstrip("/")
    if provider_key == "openai" and normalized_base_url and normalized_base_url != DEFAULT_HERMES_BASE_URL:
        return "custom"
    return PROVIDER_MAP.get(provider_key, "custom")


def get_hermes_config_path():
    override = (os.getenv("HERMES_CONFIG_PATH") or "").strip()
    if override:
        path = Path(override).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    hermes_home = (os.getenv("HERMES_HOME") or "").strip()
    if hermes_home:
        home_path = Path(hermes_home).expanduser()
        home_path.mkdir(parents=True, exist_ok=True)
        return home_path / "config.yaml"

    hermes_dir = Path.home() / ".hermes"
    hermes_dir.mkdir(exist_ok=True)
    return hermes_dir / "config.yaml"


def load_existing_config(config_path):
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except Exception as exc:
        logger.warning("Unable to read existing Hermes config %s: %s", config_path, exc)
        return {}


def sync_hermes_config_for_user(user):
    config = AIConfig.objects.filter(user=user, is_active=True).first()
    if not config:
        return {"ok": False, "reason": "no_active_config"}

    encryption = get_encryption()
    api_key = encryption.decrypt(config.api_key_encrypted)
    config_path = get_hermes_config_path()
    existing = load_existing_config(config_path)
    hermes_config = existing.copy()

    raw_base_url = (config.base_url or "").rstrip("/")
    base_url = raw_base_url
    if (config.provider or "").lower() not in ANTHROPIC_PROVIDERS:
        base_url = normalize_openai_base_url(raw_base_url)
    hermes_config["model"] = {
        "provider": map_provider_to_hermes(config.provider, base_url),
        "default": config.model_name,
        "name": config.model_name,
        "api_key": api_key,
        "temperature": config.temperature,
        "max_tokens": max(config.max_tokens, 4000),
    }

    if base_url and base_url != DEFAULT_HERMES_BASE_URL:
        hermes_config["model"]["base_url"] = base_url
        hermes_config["model"]["default_headers"] = {
            "Accept": "application/json",
            "User-Agent": MODEL_FETCH_USER_AGENT,
        }
    elif "base_url" in hermes_config["model"]:
        hermes_config["model"].pop("base_url", None)
        hermes_config["model"].pop("default_headers", None)

    skills = hermes_config.setdefault("skills", {})
    if not skills.get("paths"):
        skills["paths"] = [str(path) for path in DEFAULT_SKILL_PATHS]

    with open(config_path, "w", encoding="utf-8") as handle:
        yaml.dump(hermes_config, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(
        "Synced Hermes config for user_id=%s model=%s path=%s",
        user.id,
        config.model_name,
        config_path,
    )
    return {
        "ok": True,
        "path": str(config_path),
        "model_name": config.model_name,
    }
