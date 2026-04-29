"""
PythonAnywhere WSGI Configuration
──────────────────────────────────
⚠️ IMPORTANT: Replace YOUR_USERNAME with your actual PythonAnywhere username.

This file is pasted into the PythonAnywhere WSGI configuration editor
(Web tab → WSGI configuration file → click to edit).
"""
import os
import sys

# ─── CHANGE THESE ───────────────────────────────────────
PYTHONANYWHERE_USERNAME = 'YOUR_USERNAME'  # ← Change this!
PROJECT_NAME = 'LSOYS-AI-Project'
# ────────────────────────────────────────────────────────

project_home = f'/home/{PYTHONANYWHERE_USERNAME}/{PROJECT_NAME}'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.pythonanywhere'
os.environ['PYTHONANYWHERE_USERNAME'] = PYTHONANYWHERE_USERNAME

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
