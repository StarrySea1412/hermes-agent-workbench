import json
import logging
import os
import socket
import time
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from openai import OpenAI

from services.text_utils import normalize_messages

logger = logging.getLogger(__name__)

DEFAULT_HERMES_SYSTEM_PROMPT = """You are Hermes Workbench, a practical AI agent runtime.
Help engineers plan tasks, call tools, inspect results, and produce clear final outputs from structured multi-step execution."""


def _iter_hermes_stream_events(lines):
    """解析网关 /v1/chat/completions 的 SSE 行流。

    网关把运行时整轮(含它自己的工具执行)聚合成一个 completion 流：
    思考/正文以普通 delta 出现，工具生命周期以
    ``event: hermes.tool.progress``（running/completed）出现——OpenAI SDK
    会吞掉这种自定义事件，所以必须手工解析。

    产出 ("reasoning"|"answer"|"tool_call"|"tool_result"|"final", payload)。
    同一次工具调用的两个事件共用同一个 dict：completed 时就地改写状态，
    上层（chat_service 的 tool_events 列表）持有的引用同步更新。
    """
    answer_parts = []
    records: Dict[str, Dict[str, Any]] = {}
    current_event = None
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        line = line.rstrip("\r\n")
        if not line or line.startswith(":"):
            current_event = None
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
            continue
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        event_name = current_event
        current_event = None
        if data == "[DONE]":
            break
        if event_name == "hermes.tool.progress":
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            call_id = str(payload.get("toolCallId") or "")
            name = payload.get("tool") or ""
            if payload.get("status") == "running":
                record = {"id": call_id or name or "tool", "name": name, "args": {}, "thought": "", "status": "running"}
                if payload.get("label"):
                    # label 是运行时对工具参数的摘要,completed 事件不再携带,先存上
                    record["result_preview"] = payload["label"]
                if call_id:
                    records[call_id] = record
                yield ("tool_call", record)
            else:
                record = records.get(call_id) or {"id": call_id or name or "tool", "name": name, "args": {}, "thought": ""}
                record["status"] = "ok"
                record["result"] = {"ok": True}
                yield ("tool_result", record)
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") if isinstance(chunk, dict) else None
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            yield ("reasoning", reasoning)
        content = delta.get("content")
        if isinstance(content, str) and content:
            answer_parts.append(content)
            yield ("answer", content)
    yield ("final", SimpleNamespace(content="".join(answer_parts)))


class HermesService:
    def __init__(self, config=None, session_id: Optional[str] = None, request_timeout: float = 180.0):
        self.gateway_url = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8642/v1").rstrip("/")
        if not self.gateway_url.endswith("/v1"):
            self.gateway_url += "/v1"
        self.gateway_key = os.getenv("HERMES_GATEWAY_KEY", "")
        self.session_id = session_id
        self.request_timeout = request_timeout
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

    def stream_chat_with_tools(
        self,
        messages,
        tools=None,
        system_prompt=None,
        tool_choice="auto",
        temperature=0.3,
        max_tokens=4000,
        extra_headers=None,
    ):
        """流式调用网关并解析 SSE 事件。

        tools 参数有意不转发：工具由运行时用它自己的工具集在网关内部执行，
        后端只需要从流里读出生命周期事件。产出序列见 _iter_hermes_stream_events。
        """
        request_messages = [{"role": "system", "content": system_prompt or DEFAULT_HERMES_SYSTEM_PROMPT}]
        request_messages.extend(normalize_messages(messages))
        headers = {
            "Authorization": f"Bearer {self.gateway_key or 'hermes'}",
            "Accept": "text/event-stream",
        }
        headers.update(self._extra_headers())
        if extra_headers:
            headers.update(extra_headers)
        body = {
            "model": "hermes-agent",
            "messages": request_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        import httpx

        # 思考型模型分片间隔可达 180s（运行时 stale-stream 阈值），read 超时放宽
        read_timeout = max(self.request_timeout, 600.0)
        with httpx.Client(timeout=httpx.Timeout(self.request_timeout, read=read_timeout)) as http_client:
            with http_client.stream("POST", f"{self.gateway_url}/chat/completions", json=body, headers=headers) as response:
                response.raise_for_status()
                yield from _iter_hermes_stream_events(response.iter_lines())

    def fetch_session_tool_trace(self, limit: int = 400) -> Dict[str, Dict[str, Any]]:
        """从网关会话历史取证：call_id → {name, args, result_content}。

        生命周期 SSE 事件只有工具名和状态，参数与真实执行结果只存在
        运行时会话里（/api/sessions/{id}/messages）。回合结束后查一次，
        失败静默返回空表——取证是锦上添花，不能影响主流程。
        """
        if not self.session_id:
            return {}
        try:
            import httpx

            headers = {"Authorization": f"Bearer {self.gateway_key or 'hermes'}"}
            url = f"{self.gateway_url.replace('/v1', '')}/api/sessions/{self.session_id}/messages"
            with httpx.Client(timeout=8.0) as http_client:
                response = http_client.get(url, params={"limit": limit}, headers=headers)
                response.raise_for_status()
                messages = response.json().get("data") or []
        except Exception as exc:
            logger.warning("Session tool trace fetch failed (session=%s): %s", self.session_id, exc)
            return {}

        trace: Dict[str, Dict[str, Any]] = {}
        for message in messages:
            role = message.get("role")
            if role == "assistant":
                for tool_call in message.get("tool_calls") or []:
                    fn = tool_call.get("function") or {}
                    call_id = tool_call.get("id") or tool_call.get("call_id") or ""
                    if not call_id:
                        continue
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {"raw": fn.get("arguments") or ""}
                    record = trace.setdefault(call_id, {})
                    record["name"] = fn.get("name") or record.get("name") or ""
                    record["args"] = args if isinstance(args, dict) else {"raw": args}
            elif role == "tool":
                call_id = message.get("tool_call_id") or ""
                if not call_id:
                    continue
                record = trace.setdefault(call_id, {})
                record["result_content"] = message.get("content") or ""
        return trace

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

    # 网关当前的上游模型与渠道（读 config.yaml），供前端标注"模型 · 渠道"
    try:
        from services.hermes_config_sync import get_hermes_config_path, load_existing_config

        gateway_cfg = load_existing_config(get_hermes_config_path()) or {}
        model_cfg = gateway_cfg.get("model") or {}
        result["upstream_model"] = model_cfg.get("default") or model_cfg.get("name") or ""
        result["upstream_base_url"] = model_cfg.get("base_url") or ""
    except Exception:
        result["upstream_model"] = ""
        result["upstream_base_url"] = ""

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
