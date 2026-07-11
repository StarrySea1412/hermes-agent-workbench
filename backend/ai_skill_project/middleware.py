import json
import logging
import time

from apps.logs.models import RequestLog

logger = logging.getLogger('api')

SKIP_PATHS = {'/admin/', '/api/health', '/static/', '/favicon.ico'}
SENSITIVE_KEYS = {'password', 'api_key', 'token', 'access_token', 'refresh_token', 'secret', 'authorization'}


def _is_sensitive_key(key):
    normalized = key.lower()
    return (
        normalized in SENSITIVE_KEYS
        or normalized.endswith('_token')
        or normalized.endswith('_secret')
        or normalized.endswith('_api_key')
    )


def _mask_sensitive(data):
    if isinstance(data, dict):
        return {
            key: '******' if _is_sensitive_key(key) else _mask_sensitive(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive(item) for item in data]
    return data


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _read_body(request):
    try:
        body = request.body
        if not body:
            return None
        return _mask_sensitive(json.loads(body))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return '<binary>'


def _read_response(response):
    if getattr(response, 'streaming', False):
        return '<streaming>'

    try:
        content = response.content
        if not content:
            return None
        data = json.loads(content)
        masked = _mask_sensitive(data)
        if len(str(masked)) > 5000:
            return {'_truncated': True, 'preview': str(masked)[:500]}
        return masked
    except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        return '<binary>'


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(path) for path in SKIP_PATHS):
            return self.get_response(request)

        start = time.time()
        request_body = _read_body(request)
        response = self.get_response(request)
        duration = round((time.time() - start) * 1000, 2)
        response_body = _read_response(response)

        user = getattr(request, 'user', None)
        username = user.username if user and user.is_authenticated else 'anonymous'

        try:
            RequestLog.objects.create(
                method=request.method,
                path=request.path,
                query_string=request.META.get('QUERY_STRING', ''),
                status_code=response.status_code,
                duration_ms=duration,
                user=username,
                ip=_get_client_ip(request),
                request_body=request_body,
                response_body=response_body,
            )
        except Exception:
            pass

        log_data = {
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'duration_ms': duration,
            'user': username,
            'request': request_body,
            'response': response_body,
        }
        log_message = json.dumps(log_data, ensure_ascii=False, default=str)
        if response.status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        return response
