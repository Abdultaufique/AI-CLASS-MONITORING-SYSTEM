"""
Face Detector — wraps face detection and recognition functionality.
Provides a clean interface used by the processing pipeline.
"""
import os
import cv2
import pickle
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False


class FaceDetector:
    """High-level face detection and recognition interface."""

    def __init__(self, tolerance=0.6, model='hog'):
        self.tolerance = tolerance
        self.model = model
        self.cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )

    def detect_faces(self, frame):
        """Detect face locations in a frame. Returns list of (x, y, w, h)."""
        if HAS_FACE_RECOGNITION:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb, model=self.model)
            return [(l, t, r - l, b - t) for t, r, b, l in locations]
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]

    def encode_face_from_image(self, image_path):
        """Generate face encoding from an image file."""
        if not os.path.exists(image_path):
            return None

        if HAS_FACE_RECOGNITION:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            return encodings[0] if encodings else None
        else:
            img = cv2.imread(image_path)
            if img is None:
                return None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) > 0:
                x, y, w, h = faces[0]
                roi = gray[y:y+h, x:x+w]
                return cv2.resize(roi, (100, 100)).flatten().astype(np.float64)
            return None

    def encode_face_from_frame(self, frame, face_location):
        """Generate encoding from a detected face in a frame."""
        x, y, w, h = face_location
        if HAS_FACE_RECOGNITION:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            top, right, bottom, left = y, x + w, y + h, x
            encodings = face_recognition.face_encodings(rgb, [(top, right, bottom, left)])
            return encodings[0] if encodings else None
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi = gray[y:y+h, x:x+w]
            return cv2.resize(roi, (100, 100)).flatten().astype(np.float64)
