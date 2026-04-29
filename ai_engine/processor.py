"""
Main AI Processing Pipeline — coordinates face detection, recognition,
talking detection, rule engine, and notifications.
"""
import os
import sys
import time
import pickle
import logging
import threading

import cv2
import django

# Setup Django before importing models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User
from apps.accounts.models import UserProfile
from apps.monitoring.models import Camera, Attendance
from apps.monitoring.services.camera_service import CameraManager
from apps.monitoring.services.face_service import FaceService
from apps.monitoring.services.attendance_service import AttendanceService
from apps.violations.services.rule_engine import RuleEngine
from apps.notifications.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class MonitoringProcessor:
    """
    Main processing pipeline for a single camera.
    Runs in a background thread: captures frames, detects faces,
    recognizes students, marks attendance, and enforces rules.
    """

    def __init__(self, camera_db_obj, organization):
        self.camera = camera_db_obj
        self.organization = organization
        self.face_service = FaceService()
        self.rule_engine = RuleEngine(organization)
        self.is_running = False
        self._thread = None

        # Load known faces
        profiles = UserProfile.objects.filter(
            organization=organization, role='student',
            face_encoding__isnull=False,
        )
        self.face_service.load_known_faces(profiles)

    def start(self):
        """Start the processing pipeline in a background thread."""
        if self.is_running:
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        logger.info(f"Processor started for camera: {self.camera.name}")

    def stop(self):
        """Stop the processing pipeline."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info(f"Processor stopped for camera: {self.camera.name}")

    def _process_loop(self):
        """Main processing loop — runs continuously."""
        manager = CameraManager.get_instance()
        cam = manager.get_camera(str(self.camera.id))

        if not cam:
            logger.error(f"Camera not found in manager: {self.camera.id}")
            return

        frame_count = 0
        process_every_n = 5  # Process every 5th frame for performance

        while self.is_running:
            frame = cam.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            frame_count += 1
            if frame_count % process_every_n != 0:
                time.sleep(0.033)
                continue

            try:
                self._process_frame(frame)
            except Exception as e:
                logger.error(f"Frame processing error: {e}")

            time.sleep(0.1)  # Limit processing rate

    def _process_frame(self, frame):
        """Process a single frame: detect, recognize, enforce rules."""
        results = self.face_service.detect_and_recognize(frame)

        for result in results:
            if result['user_id']:
                # Mark attendance
                try:
                    user = User.objects.get(id=result['user_id'])
                    AttendanceService.mark_attendance(
                        user=user,
                        organization=self.organization,
                        camera=self.camera,
                        confidence=result['confidence'],
                    )
                except User.DoesNotExist:
                    pass

    def process_talking_event(self, user_id):
        """Called when talking is detected for a user."""
        try:
            user = User.objects.get(id=user_id)
            result = self.rule_engine.process_talking_detection(
                user=user,
                camera_location=self.camera.location or self.camera.name,
            )

            # Send notification
            NotificationService.send_warning_notification(
                organization=self.organization,
                user=user,
                warning_result=result,
            )

            return result
        except User.DoesNotExist:
            logger.error(f"User not found: {user_id}")
            return None
