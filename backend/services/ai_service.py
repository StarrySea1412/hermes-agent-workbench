from openai import OpenAI

from django.conf import settings

from services.encryption_service import get_encryption
from services.model_fetch_service import MODEL_FETCH_USER_AGENT, normalize_openai_base_url
from services.text_utils import normalize_messages, text_to_canvas_format

ANTHROPIC_PROVIDERS = {"anthropic"}

DEFAULT_CONTENT_SYSTEM_PROMPT = """You are Hermes Workbench, an AI delivery assistant for structured engineering and knowledge work.
Help the user turn rough notes, files, and goals into clear outlines, plans, reports, specs, speaker notes, and export-ready content.
Prefer structured Markdown. When useful, include a section named "Suggested outline" with concise bullets.
Ask at most one focused question only when required; otherwise make a reasonable assumption and continue."""

BID_COMPAT_SYSTEM_PROMPT = """You are a professional document writing assistant.
Generate structured, specific, polished content for the requested chapter.
Use clear headings and avoid empty boilerplate."""


class _CompatMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _CompatChoice:
    def __init__(self, message):
        self.message = message


class _CompatResponse:
    def __init__(self, content=""):
        self.choices = [_CompatChoice(_CompatMessage(content=content))]


class AIService:
    def __init__(self, config):
        self.config = config
        self.provider = config.provider or "openai"
        encryption = get_encryption()
        self.api_key = encryption.decrypt(config.api_key_encrypted)
        self.model = config.model_name
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens

        if self.provider in ANTHROPIC_PROVIDERS:
            self._init_anthropic()
        else:
            self._init_openai()

    def _init_openai(self):
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=normalize_openai_base_url(self.config.base_url),
            timeout=settings.AI_DEFAULT_TIMEOUT,
            max_retries=settings.AI_MAX_RETRIES,
            default_headers={
                "Accept": "application/json",
                "User-Agent": MODEL_FETCH_USER_AGENT,
            },
        )
        self._use_openai = True

    def _init_anthropic(self):
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError("anthropic package not installed. Run: pip install anthropic") from exc

        self.client = Anthropic(
            api_key=self.api_key,
            base_url=self.config.base_url,
            timeout=settings.AI_DEFAULT_TIMEOUT,
            max_retries=settings.AI_MAX_RETRIES,
        )
        self._use_openai = False

    def generate_chapter_content(self, chapter_title, prompt=None, context=None):
        user_prompt = f"Write content for this chapter: {chapter_title}"
        if prompt:
            user_prompt += f"\n\nExtra requirements:\n{prompt}"
        if context:
            user_prompt += f"\n\nReference context:\n{context}"

        generated_text = self.generate_content(
            [{"role": "user", "content": user_prompt}],
            system_prompt=BID_COMPAT_SYSTEM_PROMPT,
        )
        return generated_text, text_to_canvas_format(generated_text)

    def generate_content(self, messages, system_prompt=None, context=None):
        system_prompt = system_prompt or DEFAULT_CONTENT_SYSTEM_PROMPT
        normalized_messages = normalize_messages(messages)
        if context:
            normalized_messages.insert(0, {"role": "user", "content": f"Reference context:\n{context}"})

        if self._use_openai:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, *normalized_messages],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content or ""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=normalized_messages,
            temperature=self.temperature,
        )
        return response.content[0].text or ""

    def stream_content(self, messages, system_prompt=None, context=None):
        system_prompt = system_prompt or DEFAULT_CONTENT_SYSTEM_PROMPT
        normalized_messages = normalize_messages(messages)
        if context:
            normalized_messages.insert(0, {"role": "user", "content": f"Reference context:\n{context}"})

        if not self._use_openai:
            yield self.generate_content(normalized_messages, system_prompt=system_prompt)
            return

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, *normalized_messages],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def chat_with_tools(
        self,
        messages,
        tools=None,
        system_prompt=None,
        tool_choice="auto",
        temperature=None,
        max_tokens=None,
        extra_headers=None,
    ):
        system_prompt = system_prompt or DEFAULT_CONTENT_SYSTEM_PROMPT
        request_messages = [{"role": "system", "content": system_prompt}]
        request_messages.extend(normalize_messages(messages))

        if self._use_openai:
            kwargs = {
                "model": self.model,
                "messages": request_messages,
                "temperature": self.temperature if temperature is None else temperature,
                "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            }
            if extra_headers:
                kwargs["extra_headers"] = extra_headers
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice
            return self.client.chat.completions.create(**kwargs)

        if tools:
            raise ValueError("Native tool calling is not supported for the current provider.")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
            system=system_prompt,
            messages=normalize_messages(messages),
            temperature=self.temperature if temperature is None else temperature,
        )
        text = response.content[0].text if response.content else ""
        return _CompatResponse(text)

    def test_connection(self):
        return self.test_connection_details()["success"]

    def test_connection_details(self):
        base_url = self._connection_base_url()
        endpoint = self._connection_endpoint(base_url)
        try:
            if self._use_openai:
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10,
                )
            else:
                self.client.messages.create(
                    model=self.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
            return {
                "success": True,
                "message": "Connection successful.",
                "provider": self.provider,
                "base_url": base_url,
                "endpoint": endpoint,
                "model": self.model,
            }
        except Exception as exc:
            error_info = describe_ai_exception(exc)
            return {
                "success": False,
                "message": error_info["message"],
                "provider": self.provider,
                "base_url": base_url,
                "endpoint": endpoint,
                "model": self.model,
                **error_info,
            }

    def _connection_base_url(self):
        if self._use_openai:
            return str(normalize_openai_base_url(self.config.base_url)).rstrip("/")
        return (self.config.base_url or "").rstrip("/")

    def _connection_endpoint(self, base_url):
        if not base_url:
            return ""
        if self._use_openai:
            return f"{base_url}/chat/completions"
        return f"{base_url}/messages"


def describe_ai_exception(exc):
    chain_text = _exception_chain_text(exc)
    error_type = exc.__class__.__name__
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_text = _extract_response_text(response)

    message = str(exc) or error_type
    if status_code:
        message = f"Upstream returned HTTP {status_code}."
    elif "CERTIFICATE_VERIFY_FAILED" in chain_text:
        message = "TLS certificate verification failed."
    elif "timed out" in chain_text.lower() or "timeout" in error_type.lower():
        message = "Upstream request timed out."
    elif "Connection error" in message or "ConnectError" in chain_text:
        message = "Could not connect to the upstream chat endpoint."

    hint = _build_error_hint(status_code, error_type, chain_text, response_text)
    return {
        "error_type": error_type,
        "status_code": status_code,
        "error": _truncate(response_text or chain_text or str(exc), 1200),
        "message": message,
        "hint": hint,
    }


def _build_error_hint(status_code, error_type, chain_text, response_text):
    text = f"{chain_text}\n{response_text}".lower()
    if status_code == 401:
        return "API key is missing, invalid, or not accepted by this provider."
    if status_code == 403:
        return "The provider blocked the request. Check key permissions, account access, IP/Cloudflare rules, or required headers."
    if status_code == 404:
        return "The base URL or chat endpoint is not OpenAI-compatible, or the selected model name is not available for chat."
    if status_code == 429:
        return "The provider rate limited the request. Wait, reduce concurrency, or switch key/model."
    if status_code and status_code >= 500:
        return "The upstream provider returned a server error. Retry later or switch provider."
    if "hostname mismatch" in text or "certificate_verify_failed" in text:
        return "The TLS certificate does not match the configured host. Use the provider's correct HTTPS domain or fix the reverse proxy certificate."
    if "cloudflare" in text or "attention required" in text:
        return "The request was blocked by Cloudflare before reaching the model API."
    if "connecterror" in text or "connection error" in text:
        return "The server can reach the local app, but cannot establish a working connection to the upstream chat endpoint."
    if "timeout" in text:
        return "The upstream endpoint did not respond before the timeout."
    if error_type:
        return "Check base URL, model name, API key permissions, and whether the provider supports OpenAI chat completions."
    return ""


def _exception_chain_text(exc):
    parts = []
    seen = set()
    current = exc
    while current and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{current.__class__.__name__}: {current}")
        next_exc = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        current = next_exc
    return " | ".join(parts)


def _extract_response_text(response):
    if not response:
        return ""
    try:
        return response.text
    except Exception:
        return ""


def _truncate(value, limit):
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit]}..."
