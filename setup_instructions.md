# LSOYS AI Monitoring Platform — Setup Instructions

## Prerequisites

- **Python 3.10+** (3.10 or 3.11 recommended)
- **pip** (Python package manager)
- **Git** (optional, for version control)

## Quick Start (Local Development)

### 1. Create Virtual Environment

```bash
cd LSOYS-AI-Project
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
copy .env.example .env
# Edit .env with your settings (the defaults work for development)
```

### 4. Run Database Migrations

```bash
python manage.py makemigrations accounts monitoring violations notifications
python manage.py migrate
```

### 5. Load Sample Data

```bash
python sample_data/create_sample_data.py
```

This creates:
- **Admin user**: `admin` / `admin123`
- **8 sample students**: `alice`, `bob`, `charlie`, etc. / `student123`
- **2 cameras**, sample attendance, warnings, and notifications

### 6. Run Development Server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000** in your browser.

---

## Optional: Enhanced Face Recognition

If you want better face recognition accuracy (requires C++ build tools):

```bash
# Install CMake first
pip install cmake

# Install dlib (requires Visual Studio Build Tools on Windows)
pip install dlib

# Install face_recognition
pip install face-recognition
```

## Optional: YOLO Person Detection

```bash
pip install ultralytics
```

## Optional: Local Audio Detection

```bash
pip install pyaudio
```

---

## Project Structure Overview

```
LSOYS-AI-Project/
├── config/          → Django settings (dev/prod)
├── apps/
│   ├── accounts/    → Auth, organizations, user profiles
│   ├── monitoring/  → Cameras, face recognition, attendance
│   ├── violations/  → Warnings, violations, rule engine
│   ├── notifications/ → Real-time alerts
│   └── dashboard/   → Web dashboard views
├── ai_engine/       → AI/CV processing pipeline
├── templates/       → HTML templates
├── static/          → CSS, JS, images
├── media/           → Uploaded files (face images)
└── sample_data/     → Test data scripts
```

## Default Login Credentials

| Username | Password    | Role  |
|----------|-------------|-------|
| admin    | admin123    | Admin |
| alice    | student123  | Student |
| bob      | student123  | Student |
