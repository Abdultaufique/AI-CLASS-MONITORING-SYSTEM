#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Convert static files
python manage.py collectstatic --no-input

# Run migrations (uses SQLite)
python manage.py migrate

# Generate sample data so the app looks populated even after sleep/restart
python sample_data/create_sample_data.py
