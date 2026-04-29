"""
Dashboard views — renders the admin dashboard pages.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse

import cv2
from apps.monitoring.models import Camera, Attendance
from apps.violations.models import Warning, Violation
from apps.notifications.models import Notification
from apps.accounts.models import UserProfile


@login_required
def index(request):
    """Main dashboard page with stats and live feed."""
    org = request.organization
    today = timezone.now().date()

    context = {
        'page_title': 'Dashboard',
        'today_attendance': Attendance.objects.filter(organization=org, date=today).count() if org else 0,
        'total_students': UserProfile.objects.filter(organization=org, role='student').count() if org else 0,
        'today_warnings': Warning.objects.filter(organization=org, created_at__date=today).count() if org else 0,
        'today_violations': Violation.objects.filter(organization=org, date=today).count() if org else 0,
        'active_cameras': Camera.objects.filter(organization=org, is_monitoring=True).count() if org else 0,
        'cameras': Camera.objects.filter(organization=org, is_active=True) if org else [],
        'recent_notifications': Notification.objects.filter(organization=org)[:10] if org else [],
        'recent_attendance': Attendance.objects.filter(organization=org, date=today).select_related('user')[:10] if org else [],
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def attendance_view(request):
    """Attendance logs page."""
    org = request.organization
    date_filter = request.GET.get('date', timezone.now().date().isoformat())

    attendance = Attendance.objects.filter(
        organization=org, date=date_filter
    ).select_related('user', 'camera') if org else []

    context = {
        'page_title': 'Attendance',
        'attendance_records': attendance,
        'filter_date': date_filter,
    }
    return render(request, 'dashboard/attendance.html', context)


@login_required
def violations_view(request):
    """Violations and warnings log page."""
    org = request.organization
    today = timezone.now().date()

    context = {
        'page_title': 'Violations',
        'warnings': Warning.objects.filter(organization=org).select_related('user')[:50] if org else [],
        'violations': Violation.objects.filter(organization=org).select_related('user')[:50] if org else [],
    }
    return render(request, 'dashboard/violations.html', context)


@login_required
def students_view(request):
    """Student management page."""
    org = request.organization

    context = {
        'page_title': 'Students',
        'students': UserProfile.objects.filter(
            organization=org, role='student'
        ).select_related('user') if org else [],
    }
    return render(request, 'dashboard/students.html', context)


@login_required
def cameras_view(request):
    """Camera management page."""
    org = request.organization

    context = {
        'page_title': 'Cameras',
        'cameras': Camera.objects.filter(organization=org) if org else [],
    }
    return render(request, 'dashboard/cameras.html', context)


@login_required
def settings_view(request):
    """Organization settings page."""
    org = request.organization

    rule_config = None
    if org:
        from apps.violations.models import RuleConfig
        rule_config, _ = RuleConfig.objects.get_or_create(organization=org)

    context = {
        'page_title': 'Settings',
        'organization': org,
        'rule_config': rule_config,
    }
    return render(request, 'dashboard/settings.html', context)


@login_required
def dashboard_stats_api(request):
    """API endpoint for real-time dashboard stats (AJAX polling)."""
    org = request.organization
    today = timezone.now().date()

    if not org:
        return JsonResponse({'error': 'No organization'}, status=400)

    return JsonResponse({
        'today_attendance': Attendance.objects.filter(organization=org, date=today).count(),
        'total_students': UserProfile.objects.filter(organization=org, role='student').count(),
        'today_warnings': Warning.objects.filter(organization=org, created_at__date=today).count(),
        'today_violations': Violation.objects.filter(organization=org, date=today).count(),
        'active_cameras': Camera.objects.filter(organization=org, is_monitoring=True).count(),
        'unread_notifications': Notification.objects.filter(organization=org, is_read=False).count(),
    })


@login_required
def live_demo_view(request):
    """Live demo page — start camera, detect and recognize faces in real-time."""
    org = request.organization
    students = UserProfile.objects.filter(
        organization=org, role='student'
    ).select_related('user') if org else []

    # Count students with face encodings
    enrolled = sum(1 for s in students if s.face_encoding)

    context = {
        'page_title': 'Live Demo',
        'students': students,
        'enrolled_count': enrolled,
        'total_students': len(students) if hasattr(students, '__len__') else students.count(),
        'cameras': Camera.objects.filter(organization=org, is_active=True) if org else [],
    }
    return render(request, 'dashboard/live_demo.html', context)


@login_required
def live_demo_feed(request):
    """MJPEG feed with face recognition annotations overlaid."""
    from django.http import StreamingHttpResponse
    from apps.monitoring.services.camera_service import CameraManager, CameraService
    from apps.monitoring.services.face_service import FaceService
    import pickle
    import time

    org = request.organization
    camera_id = request.GET.get('camera_id', 'demo_cam')

    manager = CameraManager.get_instance()
    cam = manager.get_camera(camera_id)

    if not cam or not cam.is_running:
        # Auto-start default webcam for demo
        source = request.GET.get('source', '0')
        cam = manager.get_or_create_camera(camera_id, source)
        if not cam.start():
            return JsonResponse({'error': 'Cannot open webcam'}, status=500)

    # Load face encodings
    face_svc = FaceService()
    profiles = UserProfile.objects.filter(
        organization=org, role='student', face_encoding__isnull=False
    ).exclude(face_encoding=b'')
    face_svc.load_known_faces(profiles)

    # Initialize talking detector for this feed
    from apps.violations.services.talking_detector import TalkingDetector
    audio_detector = TalkingDetector(threshold=600)
    audio_detector.start_local() # Try to start local mic for demo

    def generate():
        frame_count = 0
        last_results = []
        while cam.is_running:
            frame = cam.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            frame_count += 1
            # Run recognition every 3rd frame for performance
            if frame_count % 3 == 0:
                last_results = face_svc.detect_and_recognize(frame)

            # Check for talking (audio level)
            talking = False
            if audio_detector.is_running:
                level = audio_detector.get_audio_level()
                talking = audio_detector.is_talking(level)

            # Draw annotations with talking alert
            annotated = face_svc.draw_annotations(frame, last_results, talking_detected=talking)

            # Encode to JPEG
            ret, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
                )
            time.sleep(0.033)
        
        audio_detector.stop()

    return StreamingHttpResponse(
        generate(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


@login_required
def live_demo_start(request):
    """Start the demo camera."""
    from apps.monitoring.services.camera_service import CameraManager
    import json

    body = json.loads(request.body) if request.body else {}
    source = body.get('source', '0')
    camera_id = body.get('camera_id', 'demo_cam')

    manager = CameraManager.get_instance()
    cam = manager.get_or_create_camera(camera_id, source)

    if cam.start():
        return JsonResponse({'status': 'Camera started', 'camera_id': camera_id})
    return JsonResponse({'error': 'Cannot open webcam'}, status=500)


@login_required
def live_demo_stop(request):
    """Stop the demo camera."""
    from apps.monitoring.services.camera_service import CameraManager
    import json

    body = json.loads(request.body) if request.body else {}
    camera_id = body.get('camera_id', 'demo_cam')

    manager = CameraManager.get_instance()
    manager.stop_camera(camera_id)
    return JsonResponse({'status': 'Camera stopped'})

