"""
Person Detector — optional YOLOv8 integration for person counting.
Degrades gracefully if ultralytics is not installed.
"""
import logging
import cv2

logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False
    logger.info("ultralytics not installed — YOLO person detection unavailable")


class PersonDetector:
    """Detects and counts people in video frames using YOLOv8."""

    def __init__(self, model_path='yolov8n.pt', confidence=0.5):
        self.confidence = confidence
        self.model = None
        if HAS_YOLO:
            try:
                self.model = YOLO(model_path)
                logger.info(f"YOLO model loaded: {model_path}")
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}")

    def detect_persons(self, frame):
        """
        Detect persons in a frame.
        Returns list of dicts: {bbox: (x, y, w, h), confidence: float}
        """
        if not self.model:
            return []

        results = self.model(frame, conf=self.confidence, classes=[0], verbose=False)
        persons = []

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0])
                persons.append({
                    'bbox': (int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                    'confidence': conf,
                })

        return persons

    def count_persons(self, frame):
        """Count the number of people in a frame."""
        return len(self.detect_persons(frame))

    def draw_detections(self, frame, detections):
        """Draw bounding boxes on frame."""
        annotated = frame.copy()
        for det in detections:
            x, y, w, h = det['bbox']
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (255, 200, 0), 2)
            label = f"Person {det['confidence']:.0%}"
            cv2.putText(annotated, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)
        return annotated
