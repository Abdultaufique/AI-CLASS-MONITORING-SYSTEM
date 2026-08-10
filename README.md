# LSOYS AI — Classroom Attention Monitoring System

> **This is a teacher feedback tool, not a surveillance system.**
> It estimates class-wide visual engagement to help educators adapt pacing.
> It must not be used for individual disciplinary or academic decisions.

---

## Overview

LSOYS AI is a Django-based platform that uses computer vision on a classroom
camera feed to:

1. Detect and track student faces in real time.
2. Estimate head orientation (yaw/pitch) and eye openness per detected face.
3. Classify each face as *attentive* or *distracted* using lightweight heuristics.
4. Aggregate into a live **class-wide attention percentage** for the teacher.
5. Generate a **session engagement report** (attention over time, dip timestamps, CSV export).
6. Alert the teacher when attention stays below a configurable threshold for a
   sustained period.

---

## ⚠️ Accuracy Limitation — Read Before Deploying

The attention classifier uses **geometric heuristics only**:
- Head yaw/pitch estimated via `cv2.solvePnP` (no validated face model)
- Eye closure detected via OpenCV Haar cascade

**These are approximations, not ground truth.** A student can look forward while
mentally disengaged, or look sideways while fully engaged. Results are directional
signals only. **Do not use as the sole basis for any academic, disciplinary, or
welfare decision.**

Accuracy varies with:
- Camera angle and distance
- Lighting conditions (low light, backlighting)
- Glasses, masks, heavy eye shadow
- Skin tone (see Bias & Fairness section below)

---

## Feature Scope

### ✅ In Scope (v1)
| Feature | Status |
|---|---|
| Real-time face detection (OpenCV Haar + DNN fallback) | ✅ |
| Head pose estimation (solvePnP, 6-point landmark proxy) | ✅ |
| Eye closure detection (Haar cascade) | ✅ |
| Per-face ATTENTIVE / DISTRACTED classification | ✅ |
| Rolling attention score (debounced, 30-frame window) | ✅ |
| Class-wide live attention percentage | ✅ |
| Live dashboard with animated gauge + Chart.js timeline | ✅ |
| WebSocket live push (fallback: HTTP polling) | ✅ |
| Session reports: attention-over-time, dip timestamps | ✅ |
| CSV export | ✅ |
| Sustained low-attention alert | ✅ |
| Privacy / consent framework (aggregate-only default) | ✅ |
| Existing: face recognition / attendance | ✅ |
| Existing: violation / warning system | ✅ |

### ❌ Out of Scope (v1)
- Emotion / sentiment classification
- Academic performance correlation
- Facial recognition for identity / attendance in the attention pipeline
- Audio-based engagement analysis
- Per-student disciplinary reporting

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | Django 4.2, Django REST Framework |
| Real-time | Django Channels 4 + Daphne (ASGI), WebSocket |
| Computer vision | OpenCV (headless), NumPy |
| AI / ML | solvePnP head pose, Haar cascade eye detection |
| Optional | YOLOv8 (ultralytics) for person counting |
| Frontend | Vanilla JS, Chart.js 4, Font Awesome |
| Database | SQLite (dev), PostgreSQL (production) |
| Deployment | Render (free tier), Whitenoise static |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Camera Feed (webcam / MJPEG / browser WebRTC)                       │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ frames
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ai_engine/                                                          │
│  processor.py          ← main thread per camera                     │
│  ├── face_service.py   ← detect faces (Haar/dlib fallback)         │
│  ├── attention_analyzer.py  ← head pose + eye closure per face     │
│  └── attention_scorer.py   ← rolling score + alert events          │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ every ~5s
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ apps/attention/                                                      │
│  services/session_manager.py  ← singleton, bridges thread ↔ ORM   │
│  models.py            ← AttentionSession, AttentionSnapshot         │
│  consumers.py         ← WebSocket → live state push (1s interval)  │
│  services/report_generator.py ← CSV export + stats                 │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ HTTP / WebSocket
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Teacher Dashboard (browser)                                         │
│  /dashboard/attention/ — live gauge, chart, alert banner           │
│  /dashboard/settings/  — privacy config, thresholds               │
│  /dashboard/attention/consent/ — privacy/consent notice            │
│  /dashboard/attention/session/<id>/export/ — CSV download          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Setup & Run

### Prerequisites
- Python 3.10+
- (Optional) GPU for faster OpenCV; CPU-only is fully supported at 10–15 FPS

### Install
```bash
cd LSOYS-AI-Project
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Configure
```bash
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY
```

### Database
```bash
python manage.py migrate
python manage.py createsuperuser
```

### Run (development)
```bash
python manage.py runserver
# Or with ASGI (for WebSockets):
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Navigate to `http://localhost:8000/dashboard/attention/` to open the attention dashboard.

---

## Configuration Reference

All settings have sane defaults and are overridable via environment variables.

| Env Var | Default | Description |
|---|---|---|
| `ATTENTION_PRIVACY_MODE` | `True` | Aggregate-only mode. No per-slot cards. |
| `ATTENTION_ALERT_THRESHOLD` | `0.50` | Alert when class attention < 50% |
| `ATTENTION_ALERT_DURATION_SECS` | `30` | Sustained seconds before alert fires |
| `ATTENTION_ROLLING_WINDOW_FRAMES` | `30` | Frames in per-slot smoothing window |
| `ATTENTION_SNAPSHOT_INTERVAL_SECS` | `5` | DB snapshot interval |
| `ATTENTION_YAW_THRESHOLD` | `30.0` | Horizontal rotation threshold (°) |
| `ATTENTION_PITCH_THRESHOLD` | `25.0` | Vertical rotation threshold (°) |

---

## Privacy & Consent Framework

### Default behaviour (aggregate-only, `ATTENTION_PRIVACY_MODE=True`)
- **No raw video is stored.** Frames are processed in memory and discarded.
- **No biometric data is retained** by the attention module.
- **No per-student identification** — attention analysis operates on anonymous face slots.
- Only class-wide aggregate metrics are stored: attention %, face counts, timestamps.
- Per-slot anonymous cards are hidden in the UI.

### Per-slot mode (`ATTENTION_PRIVACY_MODE=False`)
- Anonymous face-slot cards are displayed (Slot 1, Slot 2, …).
- Slots are positional/ephemeral — they are **not linked to any student identity**.
- Still no biometric data stored.

### Before deployment
1. Display the consent notice (`/dashboard/attention/consent/`) to all stakeholders.
2. Obtain explicit consent from students and parents/guardians as required.
3. Confirm institutional compliance with DPDP Act 2023 (India), GDPR, FERPA, or equivalent.
4. Brief teachers on accuracy limitations and intended use.

---

## Bias & Fairness Notice

Eye-detection and head-pose algorithms can perform unevenly across:
- Different skin tones
- Camera angles and distances
- Glasses, masks, heavy eye shadow
- Low-light or backlit conditions

**Test with diverse faces and lighting before any classroom deployment.** The
Verification section below includes explicit testing checklist items for this.
Classification errors are not uniform and should not be interpreted as reflecting
anything about individual students.

---

## Deployment (Render)

```bash
# No new heavy dependencies (MediaPipe excluded — Render free-tier safe)
# scipy (~10MB) is the only new addition
git push origin main
# Render auto-deploys via render.yaml
```

Environment variables must be set in the Render dashboard under Environment.

---

## Verification Checklist

### Automated
- [ ] `python manage.py migrate` — applies cleanly with no errors
- [ ] `python manage.py runserver` — starts without import errors

### Manual (browser)
- [ ] `/dashboard/attention/` loads; WebSocket connects
- [ ] Start session → gauge updates, timer runs
- [ ] End session → appears in Past Sessions list; CSV downloads correctly
- [ ] Alert: cover camera for 30s → alert banner appears
- [ ] Settings → toggle Privacy Mode → per-slot cards show/hide
- [ ] `/dashboard/attention/consent/` renders without errors

### Bias & Fairness (pre-deployment)
- [ ] Test in bright, dim, and backlit lighting — confirm no systematic misclassification
- [ ] Test with at least 2–3 different users of different skin tones
- [ ] Test with glasses worn — confirm eye cascade doesn't false-positive "distracted"
- [ ] Test with user turned >45° from camera — confirm system classifies as distracted (expected)
- [ ] Document any consistent failure modes and inform teachers before deployment