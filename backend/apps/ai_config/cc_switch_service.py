import json
import logging
import os
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger("api")

CC_SWITCH_DB_FILENAME = "cc-switch.db"


def get_cc_switch_db_path():
    override = (os.getenv("CC_SWITCH_DB_PATH") or "").strip()
    if override:
        return Path(override)

    candidates = [
        Path.home() / ".cc-switch" / CC_SWITCH_DB_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _strip_model_suffix(model_name):
    text = str(model_name or "").strip()
    return re.sub(r"\[[^\]]*\]", "", text).strip()


def _parse_claude_config(settings_config):
    env = settings_config.get("env") or {}
    base_url = str(env.get("ANTHROPIC_BASE_URL") or "").strip().rstrip("/")
    api_key = str(env.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    candidates = [
        env.get("ANTHROPIC_MODEL"),
        env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"),
        env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
        env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
    ]
    model = ""
    for candidate in candidates:
        cleaned = _strip_model_suffix(candidate)
        if cleaned:
            model = cleaned
            break
    return {
        "provider": "anthropic",
        "base_url": base_url,
        "model_name": model,
        "api_key": api_key,
    }


_TOML_STRING_PATTERN = re.compile(r'^\s*([a-zA-Z_]+)\s*=\s*"([^"]*)"')


def _parse_codex_config(settings_config):
    api_key = str((settings_config.get("auth") or {}).get("OPENAI_API_KEY") or "").strip()
    toml_text = str(settings_config.get("config") or "")
    base_url = ""
    model = ""
    for line in toml_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            continue
        match = _TOML_STRING_PATTERN.match(line)
        if not match:
            continue
        key, value = match.group(1).lower(), match.group(2).strip()
        if not base_url and key == "base_url":
            base_url = value.rstrip("/")
        if not model and key == "model":
            model = _strip_model_suffix(value)
        if base_url and model:
            break
    return {
        "provider": "openai",
        "base_url": base_url,
        "model_name": model,
        "api_key": api_key,
    }


def _parse_settings_config(app_type, settings_config):
    try:
        parsed = json.loads(settings_config) if isinstance(settings_config, str) else settings_config
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    if app_type == "claude":
        parsed_provider = _parse_claude_config(parsed)
    elif app_type == "codex":
        parsed_provider = _parse_codex_config(parsed)
    else:
        return None
    if not parsed_provider["base_url"] or not parsed_provider["api_key"]:
        return None
    return parsed_provider


def _connect(db_path):
    path = Path(db_path) if not isinstance(db_path, Path) else db_path
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2.0)


def list_cc_switch_providers():
    db_path = get_cc_switch_db_path()
    if not db_path:
        return {"found": False, "path": "", "providers": []}

    providers = []
    try:
        with _connect(db_path) as connection:
            cursor = connection.execute(
                "SELECT id, app_type, name, settings_config, is_current "
                "FROM providers ORDER BY app_type, sort_index"
            )
            for row in cursor.fetchall():
                provider_id, app_type, name, settings_config, is_current = row
                parsed = _parse_settings_config(app_type, settings_config)
                if not parsed:
                    continue
                providers.append({
                    "id": str(provider_id),
                    "name": str(name or provider_id),
                    "app_type": app_type,
                    "is_current": bool(is_current),
                    "base_url": parsed["base_url"],
                    "model_name": parsed["model_name"],
                })
    except sqlite3.Error as exc:
        logger.warning("Unable to read CC Switch database %s: %s", db_path, exc)
        return {"found": True, "path": str(db_path), "providers": [], "error": str(exc)}

    return {"found": True, "path": str(db_path), "providers": providers}


def get_cc_switch_provider(provider_id):
    db_path = get_cc_switch_db_path()
    if not db_path:
        return None

    try:
        with _connect(db_path) as connection:
            cursor = connection.execute(
                "SELECT app_type, name, settings_config FROM providers WHERE id = ?",
                (str(provider_id),),
            )
            row = cursor.fetchone()
    except sqlite3.Error as exc:
        logger.warning("Unable to read CC Switch provider %s: %s", provider_id, exc)
        return None

    if not row:
        return None
    app_type, name, settings_config = row
    parsed = _parse_settings_config(app_type, settings_config)
    if not parsed:
        return None
    parsed.update({
        "id": str(provider_id),
        "name": str(name or provider_id),
        "app_type": app_type,
    })
    return parsed
