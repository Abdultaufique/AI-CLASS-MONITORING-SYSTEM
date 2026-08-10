"""
Views for Attention Monitoring app.

Endpoints:
  GET  /dashboard/attention/              → attention dashboard page
  GET  /dashboard/attention/consent/      → privacy/consent notice page
  POST /dashboard/attention/session/start/  → start monitoring session
  POST /dashboard/attention/session/end/    → end session, return session_id
  GET  /dashboard/attention/session/<id>/report/   → JSON report
  GET  /dashboard/attention/session/<id>/export/   → CSV download
  GET  /dashboard/attention/live/         → polling fallback for live state
  POST /dashboard/attention/settings/save/  → save attention settings for org

All views require login (existing @login_required pattern).
"""
import json
import logging
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AttentionSession, AttentionSnapshot
from .services.session_manager import SessionManager
from .services.report_generator import generate_session_report, generate_csv

logger = logging.getLogger(__name__)


# ── Pages ─────────────────────────────────────────────────────────────────────

@login_required
def attention_dashboard(request):
    """Live attention monitoring dashboard page."""
    org     = request.organization
    from apps.monitoring.models import Camera
    cameras = Camera.objects.filter(organization=org, is_active=True) if org else []

    # Attention config from settings (with per-org override later)
    context = {
        'page_title':     'Attention Monitor',
        'cameras':        cameras,
        'alert_threshold': int(getattr(settings, 'ATTENTION_ALERT_THRESHOLD', 0.50) * 100),
        'alert_duration':  getattr(settings, 'ATTENTION_ALERT_DURATION_SECS', 30),
        'privacy_mode':    getattr(settings, 'ATTENTION_PRIVACY_MODE', True),
        # Recent sessions for session history panel
        'recent_sessions': AttentionSession.objects.filter(
            organization=org, status='ended'
        ).order_by('-started_at')[:10] if org else [],
    }
    return render(request, 'dashboard/attention_dashboard.html', context)


@login_required
def consent_notice(request):
    """Privacy and consent notice page."""
    return render(request, 'dashboard/consent_notice.html', {
        'page_title': 'Privacy & Consent Notice',
    })


# ── Session management API ────────────────────────────────────────────────────

@login_required
@require_POST
def start_session(request):
    """Start an attention monitoring session for a camera."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    org       = request.organization
    camera_id = data.get('camera_id', 'demo_cam')

    # Resolve Camera object (optional — None is OK for demo)
    camera_obj = None
    if org:
        from apps.monitoring.models import Camera
        try:
            camera_obj = Camera.objects.get(id=camera_id, organization=org)
        except (Camera.DoesNotExist, Exception):
            pass  # Use None (e.g. demo_cam is not a real DB Camera)

    # Privacy config: prefer explicit request body, then settings default
    aggregate_only = data.get(
        'aggregate_only',
        getattr(settings, 'ATTENTION_PRIVACY_MODE', True),
    )
    alert_threshold     = float(data.get(
        'alert_threshold',
        getattr(settings, 'ATTENTION_ALERT_THRESHOLD', 0.50),
    ))
    alert_duration_secs = int(data.get(
        'alert_duration_secs',
        getattr(settings, 'ATTENTION_ALERT_DURATION_SECS', 30),
    ))
    window_frames = int(getattr(settings, 'ATTENTION_ROLLING_WINDOW_FRAMES', 30))

    if not org:
        return JsonResponse({'error': 'No organization'}, status=400)

    manager    = SessionManager.get_instance()
    session_id = manager.start_session(
        camera_id=camera_id,
        org=org,
        camera_obj=camera_obj,
        aggregate_only=aggregate_only,
        alert_threshold=alert_threshold,
        alert_duration_secs=alert_duration_secs,
        rolling_window_frames=window_frames,
    )

    if not session_id:
        return JsonResponse({'error': 'Failed to start session'}, status=500)

    return JsonResponse({
        'status':     'started',
        'session_id': session_id,
        'camera_id':  camera_id,
        'aggregate_only': aggregate_only,
        'alert_threshold': alert_threshold,
    })


@login_required
@require_POST
def end_session(request):
    """End the active attention monitoring session for a camera."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    camera_id = data.get('camera_id', 'demo_cam')
    manager   = SessionManager.get_instance()
    session_id = manager.end_session(camera_id)

    if not session_id:
        return JsonResponse({'error': 'No active session for that camera'}, status=404)

    return JsonResponse({'status': 'ended', 'session_id': session_id})


# ── Live state polling fallback ───────────────────────────────────────────────

@login_required
def live_attention_api(request):
    """
    Polling fallback for live attention state.
    Returns current class attention % and slot data for the given camera.
    Used when WebSocket is unavailable.
    """
    camera_id = request.GET.get('camera_id', 'demo_cam')
    manager   = SessionManager.get_instance()
    state     = manager.get_live_state(camera_id)

    if state is None:
        return JsonResponse({'status': 'no_session', 'camera_id': camera_id})

    # Respect aggregate_only: strip per-slot data if configured
    if state.get('aggregate_only', True):
        state.pop('slots', None)

    return JsonResponse(state)


# ── Report & Export ──────────────────────────────────────────────────────────

@login_required
def session_report_json(request, session_id):
    """Return full session report as JSON."""
    org     = request.organization
    # Security: verify session belongs to this org
    session = get_object_or_404(AttentionSession, id=session_id, organization=org)
    report  = generate_session_report(str(session.id))
    if report is None:
        return JsonResponse({'error': 'Report unavailable'}, status=404)
    return JsonResponse(report)


@login_required
def export_report_csv(request, session_id):
    """Download session engagement report as CSV."""
    org     = request.organization
    session = get_object_or_404(AttentionSession, id=session_id, organization=org)
    report  = generate_session_report(str(session.id))
    if report is None:
        return HttpResponse('Report unavailable', status=404)

    csv_text  = generate_csv(report)
    filename  = f"attention_report_{str(session.id)[:8]}_{timezone.now().strftime('%Y%m%d')}.csv"
    response  = HttpResponse(csv_text, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Settings save ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def save_attention_settings(request):
    """
    Save per-session attention settings (stored in Django settings for now;
    a future version could store these per-organization in the DB).
    For now returns OK with the received values echoed back.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    # In a production system you'd persist these to the Organization model.
    # For v1 they are env-var driven; this endpoint validates and echoes them.
    threshold = float(data.get('alert_threshold', 50)) / 100.0
    duration  = int(data.get('alert_duration', 30))
    privacy   = bool(data.get('aggregate_only', True))

    return JsonResponse({
        'status':           'ok',
        'alert_threshold':  threshold,
        'alert_duration':   duration,
        'aggregate_only':   privacy,
        'note': (
            'Settings acknowledged. Restart session to apply new thresholds. '
            'To persist across server restarts, set env vars: '
            'ATTENTION_ALERT_THRESHOLD, ATTENTION_ALERT_DURATION_SECS, ATTENTION_PRIVACY_MODE'
        ),
    })
