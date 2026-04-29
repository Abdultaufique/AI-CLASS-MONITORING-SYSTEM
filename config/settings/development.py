"""
Development settings — SQLite, DEBUG=True
"""
from .base import *  # noqa: F401,F403

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# More permissive CORS in development
CORS_ALLOW_ALL_ORIGINS = True
