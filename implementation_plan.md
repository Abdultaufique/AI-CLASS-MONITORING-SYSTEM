# AI-Based Classroom Attention Monitoring System — v1 Upgrade Plan

## Existing Codebase Summary

Before proposing changes, here's what's already in place:

| Component | What exists |
|---|---|
| `ai_engine/face_detector.py` | OpenCV Haar + `face_recognition` (dlib) dual-backend face detection |
| `ai_engine/person_detector.py` | YOLOv8 via `ultralytics` (optional/graceful fallback), counts people per frame |
| `ai_engine/audio_analyzer.py` | PyAudio RMS-based talking detection |
| `ai_engine/processor.py` | `MonitoringProcessor` — per-camera processing thread, marks attendance |
| `ai_engine/workers.py` | `WorkerManager` — ThreadPoolExecutor wrapper for multiple processors |
| `apps/monitoring/models.py` | `Camera`, `Attendance` models |
| `apps/monitoring/consumers.py` | `CameraConsumer` — WebSocket, streams MJPEG frames + accepts browser frames |
| `apps/monitoring/services/face_service.py` | Full `FaceService` (multi-encoding, CLAHE, dlib+OpenCV, annotation drawing) |
| `apps/monitoring/services/camera_service.py` | `CameraService` + `CameraManager` with reconnection, CLAHE, MJPEG |
| `apps/monitoring/views.py` | Camera CRUD + attendance API + CSV export |
| `apps/dashboard/views.py` | Dashboard, live demo (MJPEG), start/stop endpoints, polling stats API |
| `templates/dashboard/live_demo.html` | Live video feed UI + system status sidebar |
| `templates/base.html` | Sidebar nav, Chart.js loaded, WebSocket notifications, toast system |
| `config/settings/base.py` | Django Channels (in-memory), face recognition + audio config flags |

**What's missing for the attention monitoring upgrade:**
- No head-pose estimation (yaw/pitch/roll) 
- No gaze direction / eye-closure (EAR) detection
- No attention classification logic (per-frame + rolling score)
- No session concept (start/end) with timestamps
- No attention dashboard with class-wide % and per-student status
- No session report generation (graph + CSV/PDF export)
- No alert system for sustained low-attention
- No privacy/consent config flags or UI notice

---

## Proposed Changes

### Component 1 — `ai_engine/` — Attention Analysis Modules

#### [NEW] `ai_engine/attention_analyzer.py`
Core CV module — pure Python/OpenCV, no Django. Provides:
- **Head pose estimation** via solvePnP using MediaPipe Face Mesh landmarks (68-point model). Outputs yaw, pitch, roll in degrees.
- **Gaze / eye-closure (EAR)** — Eye Aspect Ratio from landmark coordinates; threshold-based blink/drowsiness detection.
- **Per-face attention classification** — heuristic combinator: `ATTENTIVE` if (|yaw| < 30° AND |pitch| < 20° AND EAR > 0.21), else `DISTRACTED`.
- **Graceful fallback** — if MediaPipe unavailable, falls back to yaw-only estimate using face bbox aspect ratio heuristic.

#### [MODIFY] `ai_engine/__init__.py`
Export `AttentionAnalyzer`.

#### [NEW] `ai_engine/attention_scorer.py`
Session-level state machine:
- `AttentionScorer` — accepts per-frame face attention states, maintains a sliding window (default 30 frames) per tracked face slot (anonymous slot ID, not identity).
- Computes rolling per-face attention score and **class-wide attention %** (attentive faces / total faces).
- Emits **alert events** when class-wide % stays below configurable threshold for configurable duration.
- Thread-safe (used from camera thread, read from WebSocket consumer).
- Stores time-series data in-memory: `[(timestamp, class_pct, per_slot_states)]` for session report.

---

### Component 2 — `apps/attention/` — New Django App

> New app to keep attention logic cleanly separated from existing monitoring app.

#### [NEW] `apps/attention/__init__.py`
#### [NEW] `apps/attention/apps.py`
#### [NEW] `apps/attention/models.py`
Two models:
- **`AttentionSession`** — records session start/end, camera FK, org FK, privacy_mode (aggregate_only boolean), status (active/ended).
- **`AttentionSnapshot`** — one row per ~5s interval: session FK, timestamp, class_attention_pct, total_faces, attentive_count, distracted_count. No per-student identity stored.

#### [NEW] `apps/attention/services/session_manager.py`
- `SessionManager` singleton — maps `camera_id → (AttentionScorer, AttentionSession)`.
- `start_session(camera_id, org, privacy_mode)` — creates DB record, starts scorer.
- `end_session(camera_id)` — closes DB record, persists final snapshots.
- `push_frame_result(camera_id, face_attention_list)` — forwards data into scorer, periodically flushes snapshots to DB.

#### [NEW] `apps/attention/services/report_generator.py`
- `generate_session_report(session_id)` — queries snapshots, builds:
  - Attention-over-time time-series (list of `{timestamp, pct}`)
  - Low-attention dip timestamps (consecutive snapshots below threshold)
  - Summary stats: avg %, min %, max %, total dip duration
- Returns dict usable for both JSON API and CSV export.
- CSV export: uses Python's `csv` module (consistent with existing `export_csv` in monitoring views).

#### [NEW] `apps/attention/views.py`
- `attention_dashboard` — renders the attention dashboard page.
- `start_session_view` — POST, starts a session for a camera.
- `end_session_view` — POST, ends session, returns session ID for report.
- `session_report_view` — GET, returns JSON report data for a session.
- `export_report_csv` — GET, returns downloadable CSV.
- `live_attention_api` — GET, returns current live attention stats (polling fallback).
- `consent_notice_view` — GET, renders the privacy/consent notice page.

#### [NEW] `apps/attention/urls.py`
URL patterns under `/dashboard/attention/`.

#### [NEW] `apps/attention/consumers.py`
`AttentionConsumer` — WebSocket that pushes live attention data (`class_pct`, per-slot statuses, alert events) to the dashboard every ~1s.

#### [NEW] `apps/attention/routing.py`
WebSocket URL pattern: `ws/attention/<session_id>/`.

#### [NEW] `apps/attention/migrations/0001_initial.py`
Initial migration for `AttentionSession` and `AttentionSnapshot`.

---

### Component 3 — Integrate into existing pipeline

#### [MODIFY] `ai_engine/processor.py`
- In `_process_frame`, after calling `face_service.detect_and_recognize`, also call `AttentionAnalyzer.analyze_faces(frame, face_locations)` and pass results to `SessionManager.push_frame_result`.
- Import is guarded: if `apps.attention` session manager has no active session for this camera, skip attention scoring (zero overhead on existing flows).

#### [MODIFY] `apps/monitoring/consumers.py`
- No structural changes needed — attention data flows through a separate `AttentionConsumer`.

---

### Component 4 — Dashboard & Templates

#### [NEW] `templates/dashboard/attention_dashboard.html`
Full-page attention monitoring view:
- **Live class attention gauge** — big circular progress ring showing current class attention %, color-coded (green ≥ 70%, amber 50-70%, red < 50%).
- **Attention-over-time mini chart** — Chart.js line chart, last 60 seconds.
- **Per-slot status grid** — anonymous face slot cards (Slot 1, Slot 2, …) showing attentive/distracted status + head pose indicators (yaw badge). Only shown when `privacy_mode=False`.
- **Alert banner** — shown when alert is triggered.
- **Session controls** — Start Session / End Session + Camera selector.
- **Export Report button**.
- WebSocket connection to `AttentionConsumer`.

#### [NEW] `templates/dashboard/consent_notice.html`
Simple one-page privacy/consent notice — explains: tool purpose (teacher feedback, not surveillance), data minimization policy (no raw video stored), aggregate-only option.

#### [MODIFY] `templates/base.html`
- Add "Attention" nav item linking to `attention:dashboard`.

#### [MODIFY] `templates/dashboard/settings.html`
- Add "Attention Monitoring" settings section with:
  - Privacy Mode toggle (aggregate-only vs per-slot)
  - Alert threshold (default 50%)
  - Alert duration (default 30s)

---

### Component 5 — Settings & Config

#### [MODIFY] `config/settings/base.py`
Add new config block:
```python
# Attention Monitoring Settings
ATTENTION_PRIVACY_MODE = os.getenv('ATTENTION_PRIVACY_MODE', 'False').lower() in ('true', '1')
ATTENTION_ALERT_THRESHOLD = float(os.getenv('ATTENTION_ALERT_THRESHOLD', '0.50'))
ATTENTION_ALERT_DURATION_SECS = int(os.getenv('ATTENTION_ALERT_DURATION_SECS', '30'))
ATTENTION_ROLLING_WINDOW_FRAMES = int(os.getenv('ATTENTION_ROLLING_WINDOW_FRAMES', '30'))
ATTENTION_SNAPSHOT_INTERVAL_SECS = int(os.getenv('ATTENTION_SNAPSHOT_INTERVAL_SECS', '5'))
```

#### [MODIFY] `.env.example`
Document the new env vars.

---

### Component 6 — Requirements & Registration

#### [MODIFY] `requirements.txt`
Add:
- `mediapipe` (head pose + landmark detection; CPU-friendly)
- `scipy` (optional smoothing utils; lightweight)

> **Note**: `mediapipe` is the key new dependency. It bundles its own face mesh model; no separate model download needed. It runs at 10-15 FPS on CPU for a single face, slower for large groups — the fallback heuristic (bbox aspect ratio) handles degraded conditions.

#### [MODIFY] `config/settings/base.py`
Add `apps.attention` to `INSTALLED_APPS`.

#### [MODIFY] `config/asgi.py`
Add `attention` WebSocket routes to the routing table.

---

### Component 7 — Documentation

#### [MODIFY] `README.md`
Complete rewrite from the 28-byte stub with:
- System overview and purpose statement (teacher feedback tool, not surveillance)
- In-scope / out-of-scope features
- Privacy/consent stance
- Setup and run instructions
- Architecture diagram (text-based)
- Configuration flags reference

---

## Open Questions

> [!IMPORTANT]
> **MediaPipe dependency on Render**: MediaPipe installs a large binary (~50MB). Render's free tier has limited build time and slug size. Do you want to use MediaPipe (most accurate), or should I implement a lighter OpenCV-only head pose estimator using the existing DNN detector + solvePnZ with a 6-point landmark model? The lighter approach avoids the heavy dependency but is slightly less accurate.

> [!IMPORTANT]
> **Per-student vs aggregate privacy default**: The spec says aggregate-only should be a fallback. Should the system default to **aggregate-only** (no per-slot cards shown) and require explicit opt-in for per-slot view? Or default to per-slot (anonymous, no names) with opt-out to aggregate? This affects the default value of `ATTENTION_PRIVACY_MODE`.

> [!IMPORTANT]
> **Session report export format**: The spec says "PDF or CSV — pick whichever fits the current tech stack." The existing stack has `csv` module already in use (`monitoring/views.py` export). I'll use **CSV** unless you prefer PDF (which would require `reportlab` or `weasyprint` — extra dependencies).

> [!NOTE]
> **Attention in live_demo.html vs separate page**: The existing Live Demo page shows MJPEG feed + face recognition. Should attention monitoring be integrated into this existing page (adding panels), or live on a new separate "Attention" page? I've proposed a separate page to avoid cluttering the existing demo, but can merge them.

---

## Verification Plan

### Automated / Code-level
- Smoke-test `AttentionAnalyzer` standalone with a test frame.
- Verify migrations apply cleanly (`python manage.py migrate`).
- Verify Django starts without import errors.

### Manual Browser Verification
- Navigate to Attention Dashboard, start a session, verify WebSocket connects and gauge updates.
- Simulate low attention (cover camera), verify alert fires after threshold duration.
- End session, click "Export CSV", verify file downloads with correct columns.
- Toggle Privacy Mode in Settings, verify per-slot cards hide/show accordingly.
- Visit Consent Notice page, verify content is clear and accurate.
