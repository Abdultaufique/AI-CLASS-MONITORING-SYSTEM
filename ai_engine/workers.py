"""
Background Workers — manages processing threads for multiple cameras.
Uses ThreadPoolExecutor instead of Celery for PythonAnywhere compatibility.
"""
import os
import sys
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages background processing workers for camera streams."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.processors = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.is_running = False

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start_processor(self, camera_id, processor):
        """Start a processing worker for a camera."""
        if camera_id in self.processors:
            logger.warning(f"Processor already running for camera: {camera_id}")
            return

        self.processors[camera_id] = processor
        self.executor.submit(processor.start)
        logger.info(f"Worker started for camera: {camera_id}")

    def stop_processor(self, camera_id):
        """Stop a processing worker."""
        processor = self.processors.pop(camera_id, None)
        if processor:
            processor.stop()
            logger.info(f"Worker stopped for camera: {camera_id}")

    def stop_all(self):
        """Stop all workers."""
        for cam_id in list(self.processors.keys()):
            self.stop_processor(cam_id)
        self.executor.shutdown(wait=False)
        logger.info("All workers stopped")

    def get_active_count(self):
        """Get count of active workers."""
        return len(self.processors)

    def list_active(self):
        """List active camera IDs."""
        return list(self.processors.keys())
