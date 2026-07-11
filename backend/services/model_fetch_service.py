import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MODEL_FETCH_TIMEOUT = 15
MODEL_FETCH_USER_AGENT = "AI-skill/1.0"


class ModelFetchError(Exception):
    def __init__(self, message, *, client_error=False, status_code=None, endpoint=None):
        super().__init__(message)
        self.client_error = client_error
        self.status_code = status_code
        self.endpoint = endpoint


def fetch_model_list(
    *,
    base_url,
    api_key,
    is_full_url=False,
    models_url_override=None,
    custom_user_agent=None,
    timeout=MODEL_FETCH_TIMEOUT,
):
    candidates = build_model_endpoint_candidates(
        base_url=base_url,
        is_full_url=is_full_url,
        models_url_override=models_url_override,
    )
    if not api_key:
        raise ModelFetchError("API key is required to fetch model list.", client_error=True)

    last_not_found = None
    last_endpoint = None
    for url in candidates:
        try:
            models = _request_models(url, api_key, custom_user_agent=custom_user_agent, timeout=timeout)
            return {
                "endpoint": url,
                "models": models,
            }
        except ModelFetchError as exc:
            if exc.status_code in (404, 405):
                last_not_found = str(exc)
                last_endpoint = exc.endpoint or url
                continue
            raise

    message = last_not_found or "Unable to fetch models from the configured endpoint."
    raise ModelFetchError(message, endpoint=last_endpoint)


def build_model_endpoint_candidates(*, base_url, is_full_url=False, models_url_override=None):
    override = (models_url_override or "").strip()
    if override:
        _validate_http_url(override)
        return [override]

    trimmed = (base_url or "").strip().rstrip("/")
    if not trimmed:
        raise ModelFetchError("Base URL is required to derive the models endpoint.", client_error=True)

    candidates = []
    if is_full_url:
        marker_index = trimmed.find("/v1/")
        if marker_index >= 0:
            candidates.append(f"{trimmed[:marker_index]}/v1/models")
        else:
            slash_index = trimmed.rfind("/")
            if slash_index >= 0:
                root = trimmed[:slash_index]
                scheme_index = root.find("://")
                if scheme_index >= 0 and len(root) > scheme_index + 3:
                    candidates.append(f"{root}/v1/models")
        if not candidates:
            raise ModelFetchError("Cannot derive models endpoint from the full URL.", client_error=True)
    else:
        if _ends_with_version_segment(trimmed):
            candidates.append(f"{trimmed}/models")
            if not trimmed.endswith("/v1"):
                candidates.append(f"{trimmed}/v1/models")
        else:
            candidates.append(f"{trimmed}/v1/models")

        compat_root = _strip_compat_suffix(trimmed)
        if compat_root and compat_root != trimmed and "://" in compat_root:
            candidates.append(f"{compat_root}/v1/models")
            candidates.append(f"{compat_root}/models")

    unique_candidates = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            _validate_http_url(candidate)
            unique_candidates.append(candidate)

    return unique_candidates


def normalize_openai_base_url(base_url):
    trimmed = (base_url or "").strip().rstrip("/")
    if not trimmed:
        return trimmed

    marker_index = trimmed.find("/v1/")
    if marker_index >= 0:
        return f"{trimmed[:marker_index]}/v1"

    if _ends_with_version_segment(trimmed):
        return trimmed

    return f"{trimmed}/v1"


def _request_models(url, api_key, *, custom_user_agent=None, timeout=MODEL_FETCH_TIMEOUT):
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": custom_user_agent or MODEL_FETCH_USER_AGENT,
    }
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body = _read_error_body(exc)
        message = f"Model endpoint returned HTTP {exc.code}"
        if body:
            message = f"{message}: {body}"
        raise ModelFetchError(message, status_code=exc.code, endpoint=url) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ModelFetchError(f"Failed to fetch models: {exc}", endpoint=url) from exc

    try:
        payload = json.loads(raw_payload) if raw_payload else {}
    except json.JSONDecodeError as exc:
        raise ModelFetchError("Model endpoint returned invalid JSON.", endpoint=url) from exc

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ModelFetchError("Model endpoint response does not contain a data list.", endpoint=url)

    models = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        model = {"id": model_id}
        owned_by = entry.get("owned_by")
        if isinstance(owned_by, str) and owned_by:
            model["owned_by"] = owned_by
        models.append(model)

    models.sort(key=lambda model: model["id"])
    return models


def _ends_with_version_segment(url):
    last_segment = url.rsplit("/", 1)[-1]
    return len(last_segment) >= 2 and last_segment.startswith("v") and last_segment[1:].isdigit()


def _strip_compat_suffix(url):
    suffixes = [
        "/compatible-mode/v1",
        "/openai/deployments",
        "/api/v1",
        "/api",
        "/v1",
    ]
    for suffix in suffixes:
        if url.endswith(suffix):
            return url[: -len(suffix)].rstrip("/")
    return None


def _validate_http_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelFetchError("Model endpoint must be a valid HTTP or HTTPS URL.", client_error=True)


def _read_error_body(exc):
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(body) > 500:
        return f"{body[:500]}..."
    return body
