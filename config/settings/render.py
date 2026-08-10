"""
Render deployment settings — Fully free tier, SQLite database.
"""
import os
from .base import *  # noqa: F401,F403

DEBUG = False

# Allow all onrender.com subdomains (handles any service name)
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.onrender.com',  # covers any *.onrender.com hostname
]

# Render automatically sets RENDER_EXTERNAL_HOSTNAME for the web service
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS = [f'https://{RENDER_EXTERNAL_HOSTNAME}']
else:
    # Fallback: trust all onrender.com origins
    CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']

# Keep the base SQLite database. It will reset when the free instance sleeps,
# but the build.sh script will populate it with dummy data.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Add WhiteNoise to the middleware list for serving static files efficiently
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# WhiteNoise settings — use non-manifest version to avoid strict missing-file errors
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Security Settings for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Allowing all origins for demo/free tier purposes to ensure the UI works correctly
CORS_ALLOW_ALL_ORIGINS = True
