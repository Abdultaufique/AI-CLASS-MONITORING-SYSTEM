"""
Models for monitoring: Camera, Attendance.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from apps.accounts.models import Organization


class Camera(models.Model):
    """A camera feed source linked to an organization."""
    SOURCE_TYPE_CHOICES = [
        ('webcam', 'Local Webcam'),
        ('ip', 'IP Camera (RTSP/MJPEG)'),
        ('browser', 'Browser Webcam'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='cameras'
    )
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default='webcam')
    source_url = models.CharField(
        max_length=500, blank=True,
        help_text='For webcam: device index (0, 1...). For IP: RTSP/MJPEG URL.'
    )
    is_active = models.BooleanField(default=True)
    is_monitoring = models.BooleanField(default=False, help_text='Currently being monitored')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['organization', 'name']

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class Attendance(models.Model):
    """Automatic attendance record created when a face is recognized."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='attendance_records'
    )
    camera = models.ForeignKey(
        Camera, on_delete=models.SET_NULL, null=True, related_name='attendance_records'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    face_confidence = models.FloatField(default=0.0)
    snapshot = models.ImageField(upload_to='attendance_snapshots/', blank=True, null=True)
    date = models.DateField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['organization', 'date']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
