# Deployment Guide — PythonAnywhere

## Step 1: Upload Code

1. Log in to [PythonAnywhere](https://www.pythonanywhere.com)
2. Open a **Bash console**
3. Clone or upload your project:

```bash
git clone <your-repo-url> ~/LSOYS-AI-Project
# OR upload as a zip and extract
```

## Step 2: Create Virtual Environment

```bash
cd ~/LSOYS-AI-Project
mkvirtualenv --python=/usr/bin/python3.10 lsoys-env
pip install -r requirements.txt
```

## Step 3: Configure Environment

```bash
cp .env.example .env
nano .env
```

Set:
```
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
SECRET_KEY=<generate-a-strong-key>
ALLOWED_HOSTS=yourusername.pythonanywhere.com
```

## Step 4: Database Setup

```bash
python manage.py migrate
python sample_data/create_sample_data.py
python manage.py collectstatic --noinput
```

## Step 5: Configure Web App

1. Go to **Web** tab in PythonAnywhere
2. Click **Add a new web app**
3. Choose **Manual configuration** → **Python 3.10**
4. Set:
   - **Source code**: `/home/YOUR_USERNAME/LSOYS-AI-Project`
   - **Virtualenv**: `/home/YOUR_USERNAME/.virtualenvs/lsoys-env`
5. Edit the **WSGI configuration file** and replace contents with:

```python
import os
import sys

path = '/home/YOUR_USERNAME/LSOYS-AI-Project'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

## Step 6: Static Files

In the **Web** tab, add static file mapping:

| URL            | Directory                                        |
|----------------|--------------------------------------------------|
| `/static/`     | `/home/YOUR_USERNAME/LSOYS-AI-Project/staticfiles` |
| `/media/`      | `/home/YOUR_USERNAME/LSOYS-AI-Project/media`       |

## Step 7: Reload

Click **Reload** on the Web tab. Visit `https://yourusername.pythonanywhere.com`.

---

## Important Notes for PythonAnywhere

- **No webcam access**: Use browser webcam (getUserMedia) or IP cameras
- **No Redis/Celery**: Background processing uses threading (already configured)
- **Free tier limitations**: Limited CPU seconds and outbound network access
- **Always-on tasks**: Available on paid plans for background workers
