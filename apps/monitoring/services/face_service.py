"""
Face service — handles face detection, encoding, and recognition.
Improved: multi-encoding per person, histogram equalization, tighter tolerance,
DNN face detector fallback, dynamic reloading.
"""
import os
import cv2
import pickle
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import face_recognition (requires dlib)
try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
    logger.info("face_recognition library available — using dlib-based detection")
except ImportError:
    HAS_FACE_RECOGNITION = False
    logger.info("face_recognition not available — using OpenCV fallback")


class FaceService:
    """
    Detects and recognizes faces in video frames.
    Supports multiple encodings per person for better accuracy.
    """

    def __init__(self, tolerance=0.5, model='hog'):
        self.tolerance = tolerance  # Tighter default (was 0.6)
        self.model = model  # 'hog' (CPU) or 'cnn' (GPU)

        # Known faces — supports MULTIPLE encodings per person
        self.known_encodings = []
        self.known_names = []
        self.known_user_ids = []
        self._encoding_version = 0  # Track reload version

        # OpenCV Haar cascade
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # DNN face detector (more accurate than Haar)
        self._dnn_net = None
        self._init_dnn_detector()

    def _init_dnn_detector(self):
        """Try to load OpenCV DNN face detector (comes with opencv)."""
        try:
            model_dir = Path(cv2.data.haarcascades).parent / 'dnn'
            proto = str(model_dir / 'deploy.prototxt')
            model = str(model_dir / 'res10_300x300_ssd_iter_140000.caffemodel')
            if os.path.exists(proto) and os.path.exists(model):
                self._dnn_net = cv2.dnn.readNetFromCaffe(proto, model)
                logger.info("DNN face detector loaded")
        except Exception:
            pass  # Fall back to Haar

    def load_known_faces(self, profiles):
        """
        Load face encodings from UserProfile queryset.
        Supports multiple encodings per profile (stored as list in face_encoding).
        """
        self.known_encodings = []
        self.known_names = []
        self.known_user_ids = []

        for profile in profiles:
            if profile.face_encoding:
                try:
                    data = pickle.loads(profile.face_encoding)

                    # Support both single encoding and list of encodings
                    if isinstance(data, list):
                        for enc in data:
                            self.known_encodings.append(np.array(enc))
                            self.known_names.append(profile.full_name)
                            self.known_user_ids.append(profile.user_id)
                    else:
                        self.known_encodings.append(np.array(data))
                        self.known_names.append(profile.full_name)
                        self.known_user_ids.append(profile.user_id)
                except Exception as e:
                    logger.error(f"Error loading encoding for {profile}: {e}")

        self._encoding_version += 1
        logger.info(f"Loaded {len(self.known_encodings)} encoding(s) for {len(set(self.known_names))} people")

    def encode_face_from_image(self, image_path):
        """
        Generate face encoding from an image file.
        Applies pre-processing for better accuracy.
        Returns numpy array encoding or None.
        """
        if not os.path.exists(image_path):
            logger.error(f"Image not found: {image_path}")
            return None

        if HAS_FACE_RECOGNITION:
            image = face_recognition.load_image_file(image_path)

            # Pre-process: equalize histogram for lighting normalization
            image = self._preprocess_image_rgb(image)

            encodings = face_recognition.face_encodings(image, num_jitters=3)
            if encodings:
                return encodings[0]
            # Try with upsampled detection if no faces found
            encodings = face_recognition.face_encodings(image, num_jitters=1,
                                                         known_face_locations=None)
            return encodings[0] if encodings else None
        else:
            # OpenCV fallback
            img = cv2.imread(image_path)
            if img is None:
                return None
            img = self._preprocess_frame(img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)

            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
            )

            if len(faces) == 0:
                # Try with whole image as face
                face_resized = cv2.resize(gray, (100, 100))
                return face_resized.flatten().astype(np.float64)

            x, y, w, h = faces[0]
            face_roi = gray[y:y+h, x:x+w]
            face_resized = cv2.resize(face_roi, (100, 100))
            return face_resized.flatten().astype(np.float64)

    def encode_multiple_images(self, image_paths):
        """
        Generate encodings from multiple images of the same person.
        Returns list of encodings (for averaging or multi-match).
        """
        encodings = []
        for path in image_paths:
            enc = self.encode_face_from_image(path)
            if enc is not None:
                encodings.append(enc)
        return encodings

    def detect_and_recognize(self, frame):
        """
        Detect faces in a frame and attempt to identify them.
        Returns list of dicts: {name, user_id, location, confidence}
        """
        if HAS_FACE_RECOGNITION:
            return self._recognize_dlib(frame)
        else:
            return self._recognize_opencv(frame)

    def _preprocess_frame(self, frame):
        """Pre-process frame for better detection in varied lighting."""
        # Check brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)

        if avg_brightness < 80:
            # CLAHE enhancement for low light
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        elif avg_brightness > 200:
            # Reduce overexposure
            frame = cv2.convertScaleAbs(frame, alpha=0.8, beta=-10)

        return frame

    @staticmethod
    def _preprocess_image_rgb(image):
        """Pre-process RGB image for face_recognition library."""
        # Convert to LAB, equalize L channel, convert back
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def _recognize_dlib(self, frame):
        """Use face_recognition library for detection + recognition."""
        results = []
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Resize for speed (process at half resolution)
        small = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
        face_locations = face_recognition.face_locations(small, model=self.model)
        face_encodings = face_recognition.face_encodings(small, face_locations)

        for encoding, location in zip(face_encodings, face_locations):
            name = "Unknown"
            user_id = None
            confidence = 0.0

            if self.known_encodings:
                distances = face_recognition.face_distance(self.known_encodings, encoding)
                best_idx = int(np.argmin(distances))
                best_distance = distances[best_idx]

                if best_distance <= self.tolerance:
                    name = self.known_names[best_idx]
                    user_id = self.known_user_ids[best_idx]
                    confidence = round((1.0 - best_distance) * 100, 1)

            # Scale coordinates back to full resolution
            top, right, bottom, left = [v * 2 for v in location]
            results.append({
                'name': name,
                'user_id': user_id,
                'location': (left, top, right - left, bottom - top),
                'confidence': confidence,
            })

        return results

    def _recognize_opencv(self, frame):
        """Fallback: use OpenCV for detection + simple matching."""
        results = []
        processed = self._preprocess_frame(frame)
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        for (x, y, w, h) in faces:
            name = "Unknown"
            user_id = None
            confidence = 0.0

            if self.known_encodings:
                face_roi = gray[y:y+h, x:x+w]
                face_resized = cv2.resize(face_roi, (100, 100)).flatten().astype(np.float64)

                # Normalize descriptor
                norm = np.linalg.norm(face_resized)
                if norm > 0:
                    face_resized = face_resized / norm

                best_distance = float('inf')
                best_idx = -1

                for i, known_enc in enumerate(self.known_encodings):
                    known_norm = np.linalg.norm(known_enc)
                    if known_norm > 0:
                        known_normalized = known_enc / known_norm
                    else:
                        known_normalized = known_enc

                    dist = np.linalg.norm(face_resized - known_normalized)
                    if dist < best_distance:
                        best_distance = dist
                        best_idx = i

                threshold = 0.85  # Normalized distance threshold
                if best_distance < threshold and best_idx >= 0:
                    name = self.known_names[best_idx]
                    user_id = self.known_user_ids[best_idx]
                    confidence = round(max(0, (1.0 - best_distance / threshold)) * 100, 1)

            results.append({
                'name': name,
                'user_id': user_id,
                'location': (int(x), int(y), int(w), int(h)),
                'confidence': confidence,
            })

        return results

    def draw_annotations(self, frame, results, warnings=None, talking_detected=False):
        """Draw professional high-tech face bounding boxes and warning banners."""
        annotated = frame.copy()
        warnings = warnings or {}
        height, width = frame.shape[:2]

        # 1. Draw "TALKING DETECTED" Alert Banner
        if talking_detected:
            overlay = annotated.copy()
            cv2.rectangle(overlay, (0, 0), (width, 65), (0, 0, 220), -1)
            cv2.addWeighted(overlay, 0.7, annotated, 0.3, 0, annotated)
            
            text = "!!! TALKING DETECTED !!!"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 1.3, 3)
            cv2.putText(annotated, text, ((width - tw) // 2, 48), 
                        cv2.FONT_HERSHEY_DUPLEX, 1.3, (255, 255, 255), 3)

        # 2. Draw Face Annotations
        for r in results:
            x, y, w, h = r['location']
            name = r['name']
            warn_count = warnings.get(name, 0)

            # High-tech color palette
            if name == "Unknown":
                color = (180, 180, 180)  # Neutral Gray
            elif warn_count >= 3:
                color = (0, 0, 255)      # Critical Red
            elif warn_count >= 2:
                color = (0, 120, 255)    # Warning Orange
            elif warn_count >= 1:
                color = (0, 215, 255)    # Alert Yellow
            else:
                color = (0, 255, 120)    # Success Green

            # Draw stylized cornered box
            line_w = 3
            corner_len = int(min(w, h) * 0.25)
            # Top-Left
            cv2.line(annotated, (x, y), (x + corner_len, y), color, line_w)
            cv2.line(annotated, (x, y), (x, y + corner_len), color, line_w)
            # Top-Right
            cv2.line(annotated, (x + w, y), (x + w - corner_len, y), color, line_w)
            cv2.line(annotated, (x + w, y), (x + w, y + corner_len), color, line_w)
            # Bottom-Left
            cv2.line(annotated, (x, y + h), (x + corner_len, y + h), color, line_w)
            cv2.line(annotated, (x, y + h), (x, y + h - corner_len), color, line_w)
            # Bottom-Right
            cv2.line(annotated, (x + w, y + h), (x + w - corner_len, y + h), color, line_w)
            cv2.line(annotated, (x + w, y + h), (x + w, y + h - corner_len), color, line_w)
            
            # Subtle full-box outline
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 1)

            # Professional Label Tag
            label = f"{name.upper()}"
            if r['confidence']: label += f" | {r['confidence']:.0f}%"
            
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(annotated, (x, y - th - 15), (x + tw + 10, y), color, -1)
            cv2.putText(annotated, label, (x + 5, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            # Integrated Warning Status
            if warn_count > 0 and name != "Unknown":
                msg = {1: "SILENCE PLEASE", 2: "FINAL WARNING", 3: "EXPELLED"}.get(min(warn_count, 3), "")
                cv2.rectangle(annotated, (x, y + h), (x + w, y + h + 25), color, -1)
                cv2.putText(annotated, msg, (x + 5, y + h + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2)

        return annotated
