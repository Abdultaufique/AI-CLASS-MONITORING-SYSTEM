"""
Camera service — handles OpenCV video capture, frame processing, and MJPEG streaming.
Improved: buffer flushing, auto-reconnection, FPS control, brightness enhancement.
"""
import cv2
import time
import threading
import logging
import numpy as np

logger = logging.getLogger(__name__)


class CameraService:
    """Manages a single camera stream with thread-safe frame access."""

    def __init__(self, source=0, width=640, height=480):
        self.source = source
        self.width = width
        self.height = height
        self.capture = None
        self.current_frame = None
        self.is_running = False
        self._lock = threading.Lock()
        self._thread = None
        self._fps = 0
        self._frame_count = 0
        self._reconnect_attempts = 0
        self._max_reconnects = 5

    def start(self):
        """Start capturing frames in a background thread."""
        if self.is_running:
            return True

        if self._open_camera():
            self.is_running = True
            self._reconnect_attempts = 0
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            logger.info(f"Camera started: {self.source}")
            return True
        return False

    def _open_camera(self):
        """Open the camera with optimized settings and multiple fallback attempts."""
        # Try integer source (webcam index)
        try:
            src = int(self.source)
        except (ValueError, TypeError):
            src = self.source  # URL string

        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, None]
        
        for backend in backends:
            if backend is not None:
                self.capture = cv2.VideoCapture(src, backend)
            else:
                self.capture = cv2.VideoCapture(src)
                
            if self.capture.isOpened():
                break
        
        # If still not opened and it's a webcam, try index 1 or 2
        if not self.capture or not self.capture.isOpened():
            if isinstance(src, int) and src == 0:
                for alt_src in [1, 2]:
                    self.capture = cv2.VideoCapture(alt_src, cv2.CAP_DSHOW)
                    if self.capture.isOpened():
                        self.source = alt_src
                        break

        if not self.capture or not self.capture.isOpened():
            logger.error(f"Cannot open camera source: {self.source}")
            return False

        # Optimized settings for smooth streaming
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.capture.set(cv2.CAP_PROP_FPS, 30)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer lag
        return True

    def stop(self):
        """Stop capturing frames."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self.capture:
            self.capture.release()
        self.capture = None
        self.current_frame = None
        logger.info(f"Camera stopped: {self.source}")

    def _capture_loop(self):
        """Continuously capture frames with reconnection logic."""
        consecutive_failures = 0
        fps_timer = time.time()

        while self.is_running:
            if self.capture is None or not self.capture.isOpened():
                if not self._try_reconnect():
                    break
                continue

            ret, frame = self.capture.read()

            if ret and frame is not None and frame.size > 0:
                consecutive_failures = 0
                self._frame_count += 1

                # Enhance frame for low-light conditions
                frame = self._enhance_frame(frame)

                with self._lock:
                    self.current_frame = frame

                # Calculate FPS every second
                elapsed = time.time() - fps_timer
                if elapsed >= 1.0:
                    self._fps = self._frame_count / elapsed
                    self._frame_count = 0
                    fps_timer = time.time()
            else:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    logger.warning(f"Too many frame failures, reconnecting: {self.source}")
                    if not self._try_reconnect():
                        break
                    consecutive_failures = 0

            # Small sleep to prevent CPU hogging (~30 FPS target)
            time.sleep(0.01)

    def _try_reconnect(self):
        """Attempt to reconnect to the camera."""
        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnects:
            logger.error(f"Max reconnection attempts reached for {self.source}")
            self.is_running = False
            return False

        logger.info(f"Reconnecting camera {self.source} (attempt {self._reconnect_attempts})")
        if self.capture:
            self.capture.release()
        time.sleep(1)
        return self._open_camera()

    @staticmethod
    def _enhance_frame(frame):
        """Basic brightness/contrast enhancement for low-light conditions."""
        # Check average brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)

        if avg_brightness < 80:
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        return frame

    def get_frame(self):
        """Get the latest frame (thread-safe)."""
        with self._lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None

    def get_jpeg_frame(self, quality=75):
        """Get the latest frame encoded as JPEG bytes."""
        frame = self.get_frame()
        if frame is not None:
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
            if ret:
                return jpeg.tobytes()
        return None

    def generate_mjpeg(self):
        """Generator that yields MJPEG frames for HTTP streaming."""
        while self.is_running:
            jpeg = self.get_jpeg_frame()
            if jpeg:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
                )
            time.sleep(0.033)  # ~30 FPS

    @property
    def fps(self):
        return round(self._fps, 1)


class CameraManager:
    """Manages multiple camera streams."""

    _instance = None
    _cameras = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_or_create_camera(self, camera_id, source=0, width=640, height=480):
        """Get existing camera or create a new one."""
        if camera_id not in self._cameras:
            self._cameras[camera_id] = CameraService(source, width, height)
        return self._cameras[camera_id]

    def get_camera(self, camera_id):
        """Get a camera by ID."""
        return self._cameras.get(camera_id)

    def stop_camera(self, camera_id):
        """Stop and remove a camera."""
        camera = self._cameras.pop(camera_id, None)
        if camera:
            camera.stop()

    def stop_all(self):
        """Stop all cameras."""
        for cam_id in list(self._cameras.keys()):
            self.stop_camera(cam_id)
