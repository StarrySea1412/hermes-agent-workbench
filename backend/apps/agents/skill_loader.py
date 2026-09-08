"""Helpers for loading project-local Hermes skill files."""

from pathlib import Path
import logging
import re
from typing import Any, Optional

import yaml

logger = logging.getLogger("api")

_SKILLS_ROOT = (Path(__file__).resolve().parents[3] / "hermes_skills").resolve()
_FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", re.DOTALL)


def get_skills_root() -> Path:
    return _SKILLS_ROOT


def _normalize_skill_path(skill_path: str) -> str:
    raw = (skill_path or "").strip().replace("\\", "/")
    if raw.endswith(".md"):
        raw = raw[:-3]

    parts = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError("parent traversal is not allowed")
        parts.append(part)
    return "/".join(parts)


def resolve_skill_file(skill_path: str) -> Optional[Path]:
    try:
        normalized = _normalize_skill_path(skill_path)
    except ValueError:
        logger.warning("Illegal skill path: %s", skill_path)
        return None

    if not normalized:
        return None

    candidate = (_SKILLS_ROOT / Path(*normalized.split("/"))).with_suffix(".md")
    try:
        candidate.resolve(strict=False).relative_to(_SKILLS_ROOT)
    except ValueError:
        logger.warning("Out-of-root skill path: %s", skill_path)
        return None
    return candidate


def skill_exists(skill_path: str) -> bool:
    skill_file = resolve_skill_file(skill_path)
    return bool(skill_file and skill_file.is_file())


def load_skill_text(skill_path: str) -> Optional[str]:
    """Resolve a skill path such as ``agent-engineering/general-operator``."""
    skill_file = resolve_skill_file(skill_path)
    if not skill_file:
        return None

    try:
        return skill_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Skill file not found: %s", skill_file)
        return None
    except OSError as exc:
        logger.warning("Failed to read skill %s: %s", skill_file, exc)
        return None


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, (text or "").strip()

    metadata: dict[str, Any] = {}
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
        if isinstance(parsed, dict):
            metadata = parsed
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse skill frontmatter: %s", exc)

    return metadata, text[match.end():].strip()


def _extract_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def get_skill_details(skill_path: str) -> Optional[dict[str, Any]]:
    normalized = _normalize_skill_path(skill_path)
    skill_file = resolve_skill_file(normalized)
    if not skill_file or not skill_file.is_file():
        return None

    text = load_skill_text(normalized)
    if text is None:
        return None

    metadata, body = _parse_frontmatter(text)
    group = Path(normalized).parent.as_posix()
    source = normalized.split("/", 1)[0] if "/" in normalized else "project"
    if source not in {"auto", "manual"}:
        source = "project"

    fallback_name = Path(normalized).name
    tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []

    return {
        "path": normalized,
        "name": metadata.get("name") or fallback_name,
        "title": _extract_title(body, fallback_name),
        "description": metadata.get("description") or "",
        "tags": tags,
        "group": group,
        "source": source,
    }


def get_skill_document(skill_path: str) -> Optional[dict[str, Any]]:
    details = get_skill_details(skill_path)
    if not details:
        return None

    text = load_skill_text(skill_path)
    if text is None:
        return None

    metadata, body = _parse_frontmatter(text)
    return {
        **details,
        "metadata": metadata,
        "body": body,
        "raw_text": text,
    }


def list_skills() -> list[dict[str, Any]]:
    if not _SKILLS_ROOT.is_dir():
        logger.warning("Skill directory not found: %s", _SKILLS_ROOT)
        return []

    skills = []
    for skill_file in sorted(_SKILLS_ROOT.rglob("*.md")):
        if skill_file.name.lower() == "readme.md":
            continue
        relative_path = skill_file.relative_to(_SKILLS_ROOT).with_suffix("").as_posix()
        details = get_skill_details(relative_path)
        if details:
            skills.append(details)
    return skills


def build_system_prompt(skill_path: str, extra: str = "", tools_prompt: str = "") -> str:
    """Combine skill body, tool prompt, and extra prompt text."""
    parts = []
    skill = load_skill_text(skill_path)
    if skill:
        parts.append(skill.strip())
    if tools_prompt:
        parts.append(tools_prompt)
    if extra:
        parts.append(extra.strip())
    return "\n\n".join(parts) if parts else ""
