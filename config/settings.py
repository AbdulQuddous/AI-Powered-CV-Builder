from pathlib import Path
from datetime import timedelta
import environ
import os
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environment variables
env = environ.Env(
    DJANGO_DEBUG=(bool, False)
)

# Read the .env file
environ.Env.read_env(BASE_DIR / '.env')

# Core Settings
SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env('DJANGO_DEBUG')
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# Application definition
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    "django.contrib.staticfiles",
    'accounts',
    'cvs',
    "templates_app",
    "cv_imports",
    "chatbot",  
    "ai",
    "m7_editor",
    "m8_renderer",
    "m9_dashboard",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# Database Configuration (Parsed from .env)
# Force connection directly to the active 5433 port
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'cv_maker',
        'USER': 'cv_user',
        'PASSWORD': 'cvmaker123',
        'HOST': '127.0.0.1',
        'PORT': '5433',
    }
}


# Custom User Model
AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Internationalization
USE_TZ = True
TIME_ZONE = 'Asia/Karachi'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
STATIC_URL = "/static/"

# Additional project-level static files
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Directory for collected static files in production
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django Rest Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication'
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated'
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'auth': '20/min'
    },
    'EXCEPTION_HANDLER': 'accounts.exceptions.exception_handler',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer'
    ],
}

# JWT Authentication Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=50),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
}

# Security Cookies (Enforced when DEBUG=False in production)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b",
)

GROQ_BASE_URL = os.getenv(
    "GROQ_BASE_URL",
    "https://api.groq.com/openai/v1",
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "",
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL",
    (
        "https://generativelanguage."
        "googleapis.com/v1beta/openai/"
    ),
)

# Separate model configuration without separate credentials.
M6_GEMINI_MODEL = os.getenv(
    "M6_GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

# Successful AI results are reusable for one hour.
M6_CACHE_SECONDS = 3600

# Bound AI request duration.
M6_TIMEOUT_MS = 30000

# Limit consumption through authenticated endpoints.
REST_FRAMEWORK.setdefault("DEFAULT_THROTTLE_RATES", {})
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["m6_ai"] = "20/hour"
# Bound chat requests and authenticated conversation consumption.
M5_TIMEOUT_SECONDS = 30
CHAT_LLM_PROVIDER = env('CHAT_LLM_PROVIDER', default='qwen_local')
# Dedicated Ollama settings preserve older OpenAI-compatible QWEN_* configuration.
CHAT_QWEN_BASE_URL = env('CHAT_QWEN_BASE_URL', default='http://127.0.0.1:11434')
CHAT_QWEN_MODEL = env('CHAT_QWEN_MODEL', default='qwen3.5:4b')
QWEN_TIMEOUT = env.int('QWEN_TIMEOUT', default=60)
FINAL_REVIEW_PROVIDER = env('FINAL_REVIEW_PROVIDER', default='gemini')
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["m5_chat"] = "30/min"
