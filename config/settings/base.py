"""
Base Django settings — shared across all environments.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key-change-me-in-production!')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'corsheaders',
    'channels',
    # Local apps
    'apps.accounts',
    'apps.monitoring',
    'apps.violations',
    'apps.notifications',
    'apps.dashboard',
    'apps.attention',   # Attention Monitoring (v1 upgrade)
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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
ASGI_APPLICATION = 'config.asgi.application'

# Channel layers (in-memory for development)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

# CORS
CORS_ALLOW_ALL_ORIGINS = DEBUG

# Login URL
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Face Recognition Settings
FACE_RECOGNITION_TOLERANCE = float(os.getenv('FACE_RECOGNITION_TOLERANCE', '0.6'))
FACE_RECOGNITION_MODEL = os.getenv('FACE_RECOGNITION_MODEL', 'hog')

# Audio Detection Settings
AUDIO_SILENCE_THRESHOLD = int(os.getenv('AUDIO_SILENCE_THRESHOLD', '500'))
AUDIO_SAMPLE_RATE = int(os.getenv('AUDIO_SAMPLE_RATE', '44100'))

# Camera Settings
DEFAULT_CAMERA_SOURCE = os.getenv('DEFAULT_CAMERA_SOURCE', '0')
CAMERA_FRAME_WIDTH = int(os.getenv('CAMERA_FRAME_WIDTH', '640'))
CAMERA_FRAME_HEIGHT = int(os.getenv('CAMERA_FRAME_HEIGHT', '480'))

# ── Attention Monitoring Settings ──────────────────────────────────────────────
#
# Privacy default: ATTENTION_PRIVACY_MODE=True means only class-wide attention %
# is exposed in the dashboard and reports. No per-slot (anonymous) face cards
# are shown. Set to False to enable per-slot display (still anonymous, no names).
#
# Alert: triggers an in-dashboard notification when class attention stays below
# ATTENTION_ALERT_THRESHOLD for ATTENTION_ALERT_DURATION_SECS seconds.
#
# Rolling window: number of frames used for each slot's attention score smoothing.
# Higher = smoother, lower = more reactive to momentary changes.
#
# Yaw/Pitch thresholds: head rotation angles beyond which a face is classified
# as 'distracted'. These are HEURISTIC APPROXIMATIONS — not validated baselines.
# Adjust conservatively to reduce false positives for students at wide camera angles.

ATTENTION_PRIVACY_MODE = os.getenv('ATTENTION_PRIVACY_MODE', 'True').lower() in ('true', '1', 'yes')
ATTENTION_ALERT_THRESHOLD = float(os.getenv('ATTENTION_ALERT_THRESHOLD', '0.50'))
ATTENTION_ALERT_DURATION_SECS = int(os.getenv('ATTENTION_ALERT_DURATION_SECS', '30'))
ATTENTION_ROLLING_WINDOW_FRAMES = int(os.getenv('ATTENTION_ROLLING_WINDOW_FRAMES', '30'))
ATTENTION_SNAPSHOT_INTERVAL_SECS = int(os.getenv('ATTENTION_SNAPSHOT_INTERVAL_SECS', '5'))
ATTENTION_YAW_THRESHOLD = float(os.getenv('ATTENTION_YAW_THRESHOLD', '30.0'))
ATTENTION_PITCH_THRESHOLD = float(os.getenv('ATTENTION_PITCH_THRESHOLD', '25.0'))
