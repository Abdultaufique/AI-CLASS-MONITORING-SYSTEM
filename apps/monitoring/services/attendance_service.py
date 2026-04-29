"""
Attendance service — marks attendance when faces are recognized.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from apps.monitoring.models import Attendance

logger = logging.getLogger(__name__)

# Minimum interval between attendance marks for the same person (prevents duplicates)
ATTENDANCE_COOLDOWN_MINUTES = 30


class AttendanceService:
    """Handles automatic attendance marking based on face recognition results."""

    @staticmethod
    def mark_attendance(user, organization, camera=None, confidence=0.0, snapshot=None):
        """
        Mark attendance for a recognized user.
        Returns the Attendance record or None if already marked recently.
        """
        now = timezone.now()
        cooldown_threshold = now - timedelta(minutes=ATTENDANCE_COOLDOWN_MINUTES)

        # Check if already marked recently
        recent = Attendance.objects.filter(
            user=user,
            organization=organization,
            timestamp__gte=cooldown_threshold,
        ).exists()

        if recent:
            return None

        record = Attendance.objects.create(
            user=user,
            organization=organization,
            camera=camera,
            face_confidence=confidence,
            snapshot=snapshot,
        )
        logger.info(f"Attendance marked: {user.get_full_name()} at {now}")
        return record

    @staticmethod
    def get_today_attendance(organization):
        """Get all attendance records for today."""
        today = timezone.now().date()
        return Attendance.objects.filter(
            organization=organization,
            date=today,
        ).select_related('user', 'camera')

    @staticmethod
    def get_attendance_by_date_range(organization, start_date, end_date):
        """Get attendance records within a date range."""
        return Attendance.objects.filter(
            organization=organization,
            date__gte=start_date,
            date__lte=end_date,
        ).select_related('user', 'camera')

    @staticmethod
    def get_student_attendance(user, organization, days=30):
        """Get attendance history for a specific student."""
        start_date = timezone.now().date() - timedelta(days=days)
        return Attendance.objects.filter(
            user=user,
            organization=organization,
            date__gte=start_date,
        ).order_by('-timestamp')
