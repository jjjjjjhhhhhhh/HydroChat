"""
Base settings for the wound scanning application.
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.authentication',
    'apps.patients',
    'apps.scans',
    'apps.ai_processing',
    'apps.common',  # Common utilities and middleware
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://172.28.96.144:8081",
    "http://172.29.104.185:8081",  # Added IP from .env file
    "http://172.29.104.185:8082",  # Alternative port for Expo
    "http://172.29.104.185:19000", # Default Expo port
    "http://172.29.104.185:19001", # Alternative Expo port
    # Add other origins as needed, e.g., your frontend's production URL
]
CORS_ALLOW_CREDENTIALS = True

# Gemini LLM Configuration (Phase 14 & 17)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', None)
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp')
GEMINI_MAX_INPUT_LENGTH = int(os.getenv('GEMINI_MAX_INPUT_LENGTH', '1000'))
LLM_REQUEST_TIMEOUT = float(os.getenv('LLM_REQUEST_TIMEOUT', '30.0'))
LLM_MAX_RETRIES = int(os.getenv('LLM_MAX_RETRIES', '3'))

# Redis Configuration (Phase 18)
# Optional Redis-backed conversation state management
# Requires Redis server running (Docker, WSL, or Windows binary)
REDIS_ENABLED = os.getenv('USE_REDIS_STATE', 'false').lower() == 'true'
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
REDIS_STATE_TTL = int(os.getenv('REDIS_STATE_TTL', '7200'))  # 2 hours
REDIS_MAX_CONNECTIONS = int(os.getenv('REDIS_MAX_CONNECTIONS', '50'))
REDIS_SOCKET_TIMEOUT = int(os.getenv('REDIS_SOCKET_TIMEOUT', '5'))