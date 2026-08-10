"""
Frame processing endpoint for browser-sent webcam frames.

Accepts a base64 JPEG frame, decodes it, runs face recognition + attention
analysis, and returns results as JSON. Called from JS every ~300ms when
the browser webcam is active.

This is the key missing link in the pipeline: previously the server tried
cv2.VideoCapture(0) which fails in most web deployments. Now the browser
sends frames from getUserMedia(), the server does AI processing, and sends
results back — no server-side camera hardware needed.
"""
import base64
import json
import logging
import time
import numpy as np
import cv2

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# ── Per-org FaceService singleton cache ───────────────────────────────────────
# Key: org_id (int|None), Value: {'svc': FaceService, 'loaded_at': float}
# Re-loads face encodings from DB every 60 seconds (not every frame).
# This reduces DB load from ~3 queries/sec to ~1 query/minute per org.
_FACE_SVC_CACHE: dict = {}
_FACE_SVC_TTL   = 60.0   # seconds before re-querying DB for new enrollments


@login_required
@require_POST
def process_browser_frame(request):
    """
    Receive a base64 JPEG frame from the browser, run face recognition,
    return detected faces and recognition results as JSON.

    Used by Live Demo (face recognition pipeline).
    Called every ~300ms from the browser JS capture loop.
    """
    try:
        body = json.loads(request.body)
        frame_b64 = body.get('frame', '')
        if not frame_b64:
            return JsonResponse({'faces': [], 'status': 'no_frame'})

        # Strip data URL prefix if present
        if ',' in frame_b64:
            frame_b64 = frame_b64.split(',', 1)[1]

        # Decode base64 → numpy BGR frame
        frame_bytes = base64.b64decode(frame_b64)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({'faces': [], 'status': 'decode_error'})

        # Get or refresh cached FaceService for this org
        org = request.organization
        org_id = org.id if org else None
        cache_entry = _FACE_SVC_CACHE.get(org_id)
        now = time.time()

        if cache_entry is None or (now - cache_entry['loaded_at']) > _FACE_SVC_TTL:
            from apps.monitoring.services.face_service import FaceService
            from apps.accounts.models import UserProfile
            face_svc = FaceService()
            if org:
                profiles = UserProfile.objects.filter(
                    organization=org, role='student',
                    face_encoding__isnull=False,
                ).exclude(face_encoding=b'').select_related('user')
                face_svc.load_known_faces(profiles)
            _FACE_SVC_CACHE[org_id] = {'svc': face_svc, 'loaded_at': now}
            logger.debug("FaceService reloaded for org %s (%d profiles)",
                         org_id, len(profiles) if org else 0)
        else:
            face_svc = cache_entry['svc']

        results = face_svc.detect_and_recognize(frame)

        # Auto-create attendance record for recognized students
        if org and results:
            from apps.monitoring.models import Attendance
            from django.contrib.auth.models import User
            from django.utils import timezone

            for r in results:
                if r.get('user_id'):
                    try:
                        user = User.objects.get(id=r['user_id'])
                        Attendance.objects.get_or_create(
                            user=user,
                            organization=org,
                            date=timezone.now().date(),
                            defaults={
                                'face_confidence': r.get('confidence', 0.0),  # already 0-100
                                'camera': None,
                            },
                        )
                        # Fire a notification for the first recognition today
                        from apps.notifications.services.notification_service import NotificationService
                        today_count = Attendance.objects.filter(
                            user=user, organization=org, date=timezone.now().date()
                        ).count()
                        if today_count == 1:
                            NotificationService.create_and_send(
                                organization=org,
                                title=f"✓ Attendance — {user.get_full_name()}",
                                message=f"{user.get_full_name()} recognized and marked present.",
                                severity='info',
                                notification_type='attendance',
                            )
                    except Exception:
                        pass

        face_data = []
        for r in results:
            x, y, w, h = r.get('location', (0, 0, 0, 0))
            face_data.append({
                'bbox':       [x, y, w, h],
                'name':       r.get('name', 'Unknown'),
                'user_id':    str(r['user_id']) if r.get('user_id') else None,
                'confidence': round(float(r.get('confidence', 0.0)), 1),  # already 0-100
                'recognized': r.get('user_id') is not None,
            })

        return JsonResponse({
            'faces':       face_data,
            'face_count':  len(face_data),
            'recognized':  sum(1 for f in face_data if f['recognized']),
            'status':      'ok',
        })

    except Exception as exc:
        logger.error("process_browser_frame error: %s", exc, exc_info=True)
        return JsonResponse({'faces': [], 'status': 'error', 'detail': str(exc)}, status=500)


@login_required
@require_POST
def process_attention_frame(request):
    """
    Receive a base64 JPEG frame, run AttentionAnalyzer, push into SessionManager.
    Returns the current live attention state.

    Used by Attention Monitor browser webcam capture loop.
    Called every ~200ms when a session is active.
    """
    try:
        body = json.loads(request.body)
        frame_b64 = body.get('frame', '')
        camera_id = body.get('camera_id', 'demo_cam')

        if not frame_b64:
            return JsonResponse({'status': 'no_frame'})

        if ',' in frame_b64:
            frame_b64 = frame_b64.split(',', 1)[1]

        frame_bytes = base64.b64decode(frame_b64)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({'status': 'decode_error'})

        from apps.attention.services.session_manager import SessionManager
        from ai_engine.attention_analyzer import AttentionAnalyzer

        manager = SessionManager.get_instance()
        if not manager.has_active_session(camera_id):
            return JsonResponse({'status': 'no_session'})

        # Run attention analysis — reuse singleton analyzer from session entry
        analyzer = getattr(process_attention_frame, '_analyzer', None)
        if analyzer is None:
            from django.conf import settings
            analyzer = AttentionAnalyzer(
                yaw_threshold=float(getattr(settings, 'ATTENTION_YAW_THRESHOLD', 30.0)),
                pitch_threshold=float(getattr(settings, 'ATTENTION_PITCH_THRESHOLD', 25.0)),
            )
            process_attention_frame._analyzer = analyzer

        # Detect face bboxes — cache cascade to avoid reload overhead per frame
        face_cascade = getattr(process_attention_frame, '_cascade', None)
        if face_cascade is None:
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            process_attention_frame._cascade = face_cascade
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        raw_faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
        )
        face_bboxes = [tuple(f) for f in raw_faces] if len(raw_faces) else []

        attention_results = analyzer.analyze_faces(frame, face_bboxes)
        manager.push_frame_result(camera_id, attention_results)

        state = manager.get_live_state(camera_id)
        if state:
            # Strip per-slot data in aggregate-only (privacy) mode
            if state.get('aggregate_only', True):
                state.pop('slots', None)

            # Handle None class_pct (no faces in frame) gracefully
            # UI should show "—" not "0%" when the room is empty
            if state.get('class_pct') is None:
                state['class_pct_display'] = None
            else:
                state['class_pct_display'] = round(state['class_pct'] * 100)

        return JsonResponse({'status': 'ok', 'state': state or {}})

    except Exception as exc:
        logger.error("process_attention_frame error: %s", exc, exc_info=True)
        return JsonResponse({'status': 'error', 'detail': str(exc)}, status=500)
