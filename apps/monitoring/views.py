"""
Views for monitoring: camera management, live feed, attendance APIs.
"""
import csv
from django.http import StreamingHttpResponse, HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .models import Camera, Attendance
from .serializers import CameraSerializer, AttendanceSerializer
from .services.camera_service import CameraManager


class CameraViewSet(viewsets.ModelViewSet):
    """CRUD + streaming for cameras."""
    serializer_class = CameraSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org = self.request.organization
        if org:
            return Camera.objects.filter(organization=org)
        return Camera.objects.none()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

    @action(detail=True, methods=['post'], url_path='start')
    def start_monitoring(self, request, pk=None):
        """Start monitoring a camera."""
        camera = self.get_object()
        manager = CameraManager.get_instance()

        source = camera.source_url or '0'
        cam = manager.get_or_create_camera(str(camera.id), source)

        if cam.start():
            camera.is_monitoring = True
            camera.save()
            return Response({'status': 'Monitoring started'})
        return Response(
            {'error': 'Failed to open camera'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    @action(detail=True, methods=['post'], url_path='stop')
    def stop_monitoring(self, request, pk=None):
        """Stop monitoring a camera."""
        camera = self.get_object()
        manager = CameraManager.get_instance()
        manager.stop_camera(str(camera.id))
        camera.is_monitoring = False
        camera.save()
        return Response({'status': 'Monitoring stopped'})

    @action(detail=True, methods=['get'], url_path='feed')
    def live_feed(self, request, pk=None):
        """MJPEG live feed endpoint."""
        camera = self.get_object()
        manager = CameraManager.get_instance()
        cam = manager.get_camera(str(camera.id))

        if not cam or not cam.is_running:
            return Response(
                {'error': 'Camera is not currently monitoring'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return StreamingHttpResponse(
            cam.generate_mjpeg(),
            content_type='multipart/x-mixed-replace; boundary=frame'
        )


class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only attendance records."""
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org = self.request.organization
        if not org:
            return Attendance.objects.none()

        qs = Attendance.objects.filter(organization=org).select_related('user', 'camera')

        # Date filters
        date = self.request.query_params.get('date')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        user_id = self.request.query_params.get('user_id')

        if date:
            qs = qs.filter(date=date)
        elif start_date and end_date:
            qs = qs.filter(date__gte=start_date, date__lte=end_date)

        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        """Get today's attendance."""
        today = timezone.now().date()
        qs = self.get_queryset().filter(date=today)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """Export attendance as CSV."""
        qs = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="attendance.csv"'

        writer = csv.writer(response)
        writer.writerow(['Student Name', 'Student ID', 'Date', 'Time', 'Camera', 'Confidence'])

        for record in qs:
            writer.writerow([
                record.user.get_full_name(),
                getattr(record.user, 'profile', None) and record.user.profile.student_id or '',
                record.date,
                record.timestamp.strftime('%H:%M:%S'),
                record.camera.name if record.camera else '',
                f"{record.face_confidence:.2%}",
            ])

        return response
