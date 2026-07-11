import json
import logging
import os
import socket
import time
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from openai import OpenAI

from services.text_utils import normalize_messages

logger = logging.getLogger(__name__)

DEFAULT_HERMES_SYSTEM_PROMPT = """You are Hermes Workbench, a practical AI agent runtime.
Help engineers plan tasks, call tools, inspect results, and produce clear final outputs from structured multi-step execution."""


class HermesService:
    def __init__(self, config=None, session_id: Optional[str] = None, request_timeout: float = 180.0):
        self.gateway_url = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8642/v1").rstrip("/")
        if not self.gateway_url.endswith("/v1"):
            self.gateway_url += "/v1"
        self.gateway_key = os.getenv("HERMES_GATEWAY_KEY", "")
        self.session_id = session_id
        self.client = OpenAI(
            api_key=self.gateway_key or "hermes",
            base_url=self.gateway_url,
            timeout=request_timeout,
            max_retries=2,
        )
        logger.info("Hermes Gateway initialized: %s session=%s", self.gateway_url, self.session_id)

    def _extra_headers(self) -> dict:
        if not self.session_id:
            return {}
        return {"X-Hermes-Session-Id": self.session_id}

    def chat(self, messages: Iterable[dict], system_prompt: Optional[str] = None, stream: bool = False):
        request_messages = [{"role": "system", "content": system_prompt or DEFAULT_HERMES_SYSTEM_PROMPT}]
        request_messages.extend(normalize_messages(messages))
        response = self.client.chat.completions.create(
            model="hermes-agent",
            messages=request_messages,
            temperature=0.7,
            max_tokens=4000,
            stream=stream,
            extra_headers=self._extra_headers(),
        )
        if stream:
            return response
        return response.choices[0].message.content or ""

    def chat_with_tools(
        self,
        messages,
        tools=None,
        system_prompt=None,
        tool_choice="auto",
        temperature=0.3,
        max_tokens=4000,
        extra_headers=None,
    ):
        request_messages = [{"role": "system", "content": system_prompt or DEFAULT_HERMES_SYSTEM_PROMPT}]
        request_messages.extend(normalize_messages(messages))
        headers = self._extra_headers()
        if extra_headers:
            headers.update(extra_headers)
        kwargs = {
            "model": "hermes-agent",
            "messages": request_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_headers": headers,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**kwargs)

    def stream_chat(self, messages: Iterable[dict], system_prompt: Optional[str] = None):
        stream = self.chat(messages, system_prompt=system_prompt, stream=True)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def generate_chapter(
        self,
        chapter_title: str,
        prompt: Optional[str] = None,
        context: Optional[str] = None,
        timeout: int = 120,
        system_prompt: Optional[str] = None,
    ) -> str:
        del timeout
        user_prompt = f"Write content for this chapter: {chapter_title}"
        if prompt:
            user_prompt += f"\n\nExtra requirements:\n{prompt}"
        if context:
            user_prompt += f"\n\nReference context:\n{context}"
        return self.chat([{"role": "user", "content": user_prompt}], system_prompt=system_prompt)

    def analyze_document(self, file_content: str, timeout: int = 180) -> Dict[str, Any]:
        del timeout
        prompt = f"""Analyze the following source material for an engineering agent project.
Return JSON with keys: title, summary, audience, key_points, suggested_outline, risks.

Source:
{file_content}"""
        result_text = self.chat([{"role": "user", "content": prompt}], system_prompt=DEFAULT_HERMES_SYSTEM_PROMPT)
        return _parse_json_or_raw(result_text)

    def health_check(self) -> Dict[str, Any]:
        try:
            start = time.perf_counter()
            content = self.chat([{"role": "user", "content": "Reply OK only."}])
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {"available": True, "connected": bool(content), "error": None, "latency_ms": latency_ms}
        except Exception as exc:
            return {"available": False, "connected": False, "error": str(exc)}

    def to_canvas_format(self, text: str) -> list:
        from services.text_utils import text_to_canvas_format

        return text_to_canvas_format(text)


def create_hermes_service(config=None, session_id: Optional[str] = None):
    try:
        return HermesService(config, session_id=session_id)
    except Exception as exc:
        logger.warning("Hermes Service unavailable: %s", exc)
        return None


def get_hermes_monitor(timeout: float = 3.0, run_chat_probe: bool = False) -> Dict[str, Any]:
    raw_url = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8642/v1").rstrip("/")
    gateway_url = raw_url if raw_url.endswith("/v1") else f"{raw_url}/v1"
    probe_url = gateway_url.replace("://localhost", "://127.0.0.1", 1)
    gateway_key = os.getenv("HERMES_GATEWAY_KEY", "")
    parsed = urlparse(probe_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    result = {
        "configured": bool(gateway_url),
        "gateway_url": gateway_url,
        "host": host,
        "port": port,
        "has_key": bool(gateway_key),
        "tcp_connected": False,
        "models_connected": False,
        "chat_connected": False,
        "connected": False,
        "latency_ms": None,
        "models_count": 0,
        "models": [],
        "error": None,
        "checks": [],
        "checked_at": checked_at,
    }

    tcp_start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            result["tcp_connected"] = True
            result["checks"].append({
                "name": "tcp",
                "ok": True,
                "latency_ms": round((time.perf_counter() - tcp_start) * 1000, 2),
            })
    except OSError as exc:
        result["error"] = f"TCP connect failed: {exc}"
        result["checks"].append({"name": "tcp", "ok": False, "error": str(exc)})
        return result

    models_start = time.perf_counter()
    try:
        headers = {}
        if gateway_key:
            headers["Authorization"] = f"Bearer {gateway_key}"
        request = Request(f"{probe_url}/models", headers=headers)
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload) if payload else {}
        models = data.get("data", []) if isinstance(data, dict) else []
        result["models_connected"] = True
        result["models_count"] = len(models)
        result["models"] = [
            model.get("id") for model in models[:8]
            if isinstance(model, dict) and model.get("id")
        ]
        result["checks"].append({
            "name": "models",
            "ok": True,
            "latency_ms": round((time.perf_counter() - models_start) * 1000, 2),
        })
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        result["error"] = f"Models probe failed: {exc}"
        result["checks"].append({"name": "models", "ok": False, "error": str(exc)})
        return result

    result["connected"] = result["tcp_connected"] and result["models_connected"]

    if run_chat_probe:
        chat = HermesService(request_timeout=timeout).health_check()
        result["chat_connected"] = bool(chat.get("connected"))
        result["latency_ms"] = chat.get("latency_ms")
        if result["chat_connected"]:
            result["checks"].append({"name": "chat", "ok": True, "latency_ms": chat.get("latency_ms")})
        else:
            result["error"] = chat.get("error") or "Chat probe failed"
            result["checks"].append({"name": "chat", "ok": False, "error": result["error"]})
            result["chat_degraded"] = True
            return result

    result["connected"] = result["tcp_connected"] and result["models_connected"]
    return result


def build_session_id(user_id, project_id) -> Optional[str]:
    if not user_id or not project_id:
        return None
    return f"u{user_id}-p{project_id}"


def _parse_json_or_raw(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_output": text}
