"""
PythonAnywhere deployment settings — SQLite, DEBUG=False, WSGI only.
────────────────────────────────────────────────────────────────────
Update YOUR_USERNAME below with your actual PythonAnywhere username.
"""
import os
from .base import *  # noqa: F401,F403

DEBUG = False

# ⚠️ CHANGE THIS to your PythonAnywhere username
PYTHONANYWHERE_USERNAME = os.getenv('PYTHONANYWHERE_USERNAME', 'YOUR_USERNAME')

ALLOWED_HOSTS = [
    f'{PYTHONANYWHERE_USERNAME}.pythonanywhere.com',
    'localhost',
    '127.0.0.1',
]

# SQLite database (PythonAnywhere free tier doesn't support PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Static files — collected by `python manage.py collectstatic`
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Security — PythonAnywhere free tier uses HTTP (not HTTPS)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = False   # Free tier = HTTP only
CSRF_COOKIE_SECURE = False      # Free tier = HTTP only
X_FRAME_OPTIONS = 'DENY'
CSRF_TRUSTED_ORIGINS = [
    f'https://{PYTHONANYWHERE_USERNAME}.pythonanywhere.com',
    f'http://{PYTHONANYWHERE_USERNAME}.pythonanywhere.com',
]

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    f'https://{PYTHONANYWHERE_USERNAME}.pythonanywhere.com',
    f'http://{PYTHONANYWHERE_USERNAME}.pythonanywhere.com',
]

# Disable Daphne/Channels on PythonAnywhere (WSGI only, no WebSocket)
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ('daphne', 'channels')]

# Channel layers — dummy backend (WebSocket not available)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# WhiteNoise for serving static files efficiently
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
