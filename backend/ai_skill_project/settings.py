import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# ──────────────────────────────────────────────
# 核心安全配置 — 从环境变量读取
# ──────────────────────────────────────────────

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-this-in-production')

DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', '*').split(',') if h.strip()]

# ──────────────────────────────────────────────
# 代理信任（nginx 反向代理）
# ──────────────────────────────────────────────

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# 生产环境额外安全
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

if not DEBUG and SECRET_KEY.startswith('django-insecure-'):
    warnings.warn(
        'DJANGO_SECRET_KEY is still the insecure default. Set a real secret in production.',
        RuntimeWarning,
        stacklevel=1,
    )

# ──────────────────────────────────────────────
# 应用配置
# ──────────────────────────────────────────────

INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'corsheaders',
    'apps.users',
    'apps.projects',
    'apps.bids',
    'apps.ai_config',
    'apps.logs',
    'apps.files',
    'apps.tools',
    'apps.agents',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'ai_skill_project.middleware.RequestLogMiddleware',
]

ROOT_URLCONF = 'ai_skill_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ai_skill_project.wsgi.application'

# ──────────────────────────────────────────────
# 数据库
# ──────────────────────────────────────────────

_db_engine = os.getenv('DB_ENGINE', 'sqlite').lower()
if _db_engine in ('postgres', 'postgresql'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'ai_skill'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv('SQLITE_PATH', 'db.sqlite3'),
        }
    }

# ──────────────────────────────────────────────
# 认证
# ──────────────────────────────────────────────

AUTH_USER_MODEL = 'users.User'
if DEBUG:
    AUTH_PASSWORD_VALIDATORS = []
else:
    AUTH_PASSWORD_VALIDATORS = [
        {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
        {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
        {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
        {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    ]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────
# 静态文件 — 生产环境 collectstatic
# ──────────────────────────────────────────────

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ──────────────────────────────────────────────
# CORS — 从环境变量读取，支持生产域名
# ──────────────────────────────────────────────

_cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    # 开发环境默认值
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]

CORS_ALLOW_CREDENTIALS = True

# ──────────────────────────────────────────────
# Django REST Framework
# ──────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.users.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'EXCEPTION_HANDLER': 'apps.users.exception_handler.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/minute',
        'user': '100/minute',
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Hermes Agent Workbench API',
    'DESCRIPTION': 'API surface for the Hermes Agent Workbench runtime and compatibility layers.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'COMPONENT_SPLIT_REQUEST': True,
}

# ──────────────────────────────────────────────
# JWT
# ──────────────────────────────────────────────

JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-please-change-in-production')
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '240'))
# LOCAL_SINGLE_USER_MODE 仅用于本地单机调试（绕过鉴权），默认关闭以防误带入生产。
LOCAL_SINGLE_USER_MODE = os.getenv('LOCAL_SINGLE_USER_MODE', 'False').lower() in ('true', '1', 'yes')

if not DEBUG and JWT_SECRET_KEY == 'dev-secret-key-please-change-in-production':
    warnings.warn(
        'JWT_SECRET_KEY is still the development default. Set a real secret in production.',
        RuntimeWarning,
        stacklevel=1,
    )

# Bids / multi-agent workflows are legacy and off by default.
ENABLE_LEGACY_BIDS = os.getenv('ENABLE_LEGACY_BIDS', 'False').lower() in ('true', '1', 'yes')

# ──────────────────────────────────────────────
# AI 配置
# ──────────────────────────────────────────────

AI_CONFIG_ENCRYPTION_KEY = os.environ.get('AI_CONFIG_ENCRYPTION_KEY', 'change-this-to-a-fernet-key-in-production')

AI_DEFAULT_TIMEOUT = int(os.environ.get('AI_DEFAULT_TIMEOUT', '60'))
AI_MAX_RETRIES = int(os.environ.get('AI_MAX_RETRIES', '3'))
AI_DEFAULT_PROVIDER = os.environ.get('AI_DEFAULT_PROVIDER', 'openai')
AI_DEFAULT_BASE_URL = os.environ.get('AI_DEFAULT_BASE_URL', '')
AI_DEFAULT_MODEL = os.environ.get('AI_DEFAULT_MODEL', '')

# ──────────────────────────────────────────────
# Hermes Agent Gateway 配置
# ──────────────────────────────────────────────

HERMES_GATEWAY_URL = os.getenv('HERMES_GATEWAY_URL', 'http://localhost:8642/v1')
HERMES_GATEWAY_KEY = os.getenv('HERMES_GATEWAY_KEY', '')

# ──────────────────────────────────────────────
# Celery / Redis 配置（异步生成任务）
# ──────────────────────────────────────────────

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
CELERY_TIMEZONE = TIME_ZONE

# 任务序列化统一用 json
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# 单个生成任务的超时与重试
CELERY_TASK_TIME_LIMIT = 300       # 硬超时 5 分钟（含 Hermes reasoning + LLM 往返）
CELERY_TASK_SOFT_TIME_LIMIT = 270  # 软超时 4.5 分钟，触发前抛 SoftTimeLimitExceeded
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # worker 崩溃时任务重新入队，不丢失

# 稳妥的可见性超时（避免长任务被重复分发）
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_TASK_ALWAYS_EAGER = os.getenv(
    'CELERY_TASK_ALWAYS_EAGER',
    'true' if DEBUG else 'false',
).lower() in ('true', '1', 'yes')
CELERY_TASK_EAGER_PROPAGATES = True
if CELERY_TASK_ALWAYS_EAGER and not os.getenv('CELERY_BROKER_URL'):
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'

# ──────────────────────────────────────────────
# 日志
# ──────────────────────────────────────────────

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'api.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'api': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ──────────────────────────────────────────────
# Unfold Admin Theme
# ──────────────────────────────────────────────

UNFOLD = {
    'SITE_TITLE': 'Hermes Workbench',
    'SITE_HEADER': 'Hermes Workbench Admin',
    'SITE_SYMBOL': 'hub',
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': False,
    'COLORS': {
        'primary': {
            '50': '239 246 255',
            '100': '219 234 254',
            '200': '191 219 254',
            '300': '147 197 253',
            '400': '96 165 250',
            '500': '59 130 246',
            '600': '37 99 235',
            '700': '29 78 216',
            '800': '30 64 175',
            '900': '30 58 138',
        },
    },
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': True,
    },
    'TABS': [],
}
