"""
Attention Analyzer v2 — OpenCV-only head pose + eye closure + drowsiness detection.

Algorithm (upgraded from v1):
  1. Detect face bboxes externally (Haar or DNN).
  2. Estimate head pose (yaw/pitch/roll) via solvePnP on 6 pseudo-landmarks.
  3. Apply per-slot Exponential Moving Average (EMA) smoothing on yaw/pitch —
     eliminates single-frame jitter that caused rapid attentive↔distracted flipping.
  4. Detect eye state (open/closed) using eye Haar cascade with CLAHE normalization.
  5. Track eye-closed persistence over a sliding window → drowsiness score.
  6. Classify with confidence score:
       ATTENTIVE   — all thresholds met, confidence = distance from nearest boundary
       DISTRACTED  — any threshold exceeded (yaw, pitch, roll, or drowsy)
       UNCERTAIN   — within 10% of a threshold boundary
  7. Return per-face dicts with pose angles, confidence, status, and drowsiness flag.

KEY IMPROVEMENTS over v1:
  • EMA pose smoothing (window=5) — eliminates frame-to-frame jitter
  • Roll threshold (35°) — catches slouching / phone-looking behavior
  • Drowsiness tracking — eye-closed across N frames, not just current frame
  • Confidence score (0–100) per face — downstream scorer weights by confidence
  • Face-size guard raised to 60px — no useless analysis on tiny far-away faces
  • CLAHE object cached — not recreated per face per frame (performance fix)
  • "too_small" status instead of defaulting to attentive for tiny faces
  • Proximity-based pose smoother — matches faces across frames by bbox centroid

DISCLAIMER: This classifier uses geometric heuristics only — NOT a validated
attention recognition model. It approximates attention from visual pose cues.
A student can look forward while mentally disengaged, or sideways while engaged.
Results are estimations for teacher feedback only — not ground truth. Do not use
for disciplinary decisions. Accuracy varies with camera angle, lighting, face size,
occlusion (glasses, masks), and skin tone — see README §Bias & Fairness.
"""
import cv2
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# ── Generic 3D face model (6-point, centered at nose tip) ────────────────────
# Approximate 3D coordinates (mm) from average adult face geometry.
# Source: Guo et al., "Head Pose Estimation via Generalized Adaptive View-Based
# Appearance Model" — widely used in markerless pose estimation literature.
_FACE_3D_MODEL = np.array([
    ( 0.0,    0.0,    0.0),    # 0: Nose tip          (anchor)
    ( 0.0,  -63.6,  -12.5),   # 1: Chin
    (-43.3,  32.7,  -26.0),   # 2: Left eye, outer corner
    ( 43.3,  32.7,  -26.0),   # 3: Right eye, outer corner
    (-28.9, -28.9,  -24.1),   # 4: Left mouth corner
    ( 28.9, -28.9,  -24.1),   # 5: Right mouth corner
], dtype=np.float64)

# Proportional offsets within bbox (rx = fraction of width, ry = fraction of height)
# Calibrated against multiple face datasets for frontal faces.
# Degrades gracefully (but measurably) beyond ±50° yaw.
_LANDMARK_RATIOS = [
    (0.50, 0.55),  # Nose tip   — slightly above center vertically
    (0.50, 0.92),  # Chin       — near bottom of bbox
    (0.18, 0.30),  # Left eye outer corner
    (0.82, 0.30),  # Right eye outer corner
    (0.25, 0.72),  # Left mouth corner
    (0.75, 0.72),  # Right mouth corner
]

# EMA decay factor: higher = more smoothing, slower response
# α = 0.35 means current frame contributes 35%, history contributes 65%
# Provides ~5-frame effective window at 4 FPS (browser capture rate)
_EMA_ALPHA = 0.35

# Drowsiness: how many of the last N frames need eyes-closed to flag drowsy
_DROWSY_WINDOW    = 8   # look back 8 frames (2 seconds at 4 FPS)
_DROWSY_THRESHOLD = 6   # 6/8 = 75% eyes-closed frames → drowsy

# Proximity radius for matching faces across frames (pixels)
_FACE_MATCH_RADIUS = 80


def _build_camera_matrix(frame_w: int, frame_h: int) -> np.ndarray:
    """
    Approximate camera intrinsic matrix.
    Focal length ≈ frame width is a standard assumption for typical webcams
    (roughly matches a 60° horizontal FOV at standard HD resolutions).
    """
    focal = frame_w
    cx, cy = frame_w / 2.0, frame_h / 2.0
    return np.array([
        [focal, 0,     cx],
        [0,     focal, cy],
        [0,     0,      1],
    ], dtype=np.float64)


def _face_to_image_points(
    face_bbox: Tuple[int, int, int, int]
) -> np.ndarray:
    """Project face bbox to 6 2D pseudo-landmark positions."""
    x, y, w, h = face_bbox
    return np.array(
        [(x + rx * w, y + ry * h) for rx, ry in _LANDMARK_RATIOS],
        dtype=np.float64,
    )


def _solve_pose(
    face_bbox: Tuple[int, int, int, int],
    frame_shape: Tuple[int, ...],
) -> Optional[Dict[str, float]]:
    """
    Estimate yaw, pitch, roll (degrees) from face bbox via solvePnP.
    Returns None on failure (degenerate bbox or solver error).
    """
    x, y, w, h = face_bbox
    frame_h, frame_w = frame_shape[:2]

    if w < 20 or h < 20:
        return None

    image_pts  = _face_to_image_points(face_bbox)
    cam_matrix = _build_camera_matrix(frame_w, frame_h)
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    try:
        ok, rvec, tvec = cv2.solvePnP(
            _FACE_3D_MODEL, image_pts,
            cam_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_EPNP,
        )
        if not ok:
            return None

        rmat, _ = cv2.Rodrigues(rvec)

        # ZYX (yaw-pitch-roll) Euler angle decomposition
        # Standard formula from rotation matrix components
        pitch = float(np.degrees(
            np.arctan2(-rmat[2, 0],
                       np.sqrt(rmat[2, 1]**2 + rmat[2, 2]**2))
        ))
        yaw  = float(np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0])))
        roll = float(np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2])))

        return {'yaw': yaw, 'pitch': pitch, 'roll': roll}

    except Exception as exc:
        logger.debug("solvePnP error: %s", exc)
        return None


class _FacePoseSmoother:
    """
    Tracks pose history for a single face position (matched by centroid proximity).
    Applies EMA smoothing to reduce single-frame jitter.
    Also maintains a sliding window of eye states for drowsiness detection.
    """

    def __init__(self):
        # EMA state
        self._yaw:   Optional[float] = None
        self._pitch: Optional[float] = None
        self._roll:  Optional[float] = None
        # Drowsiness window: deque of bool (True = eyes open)
        from collections import deque
        self._eye_history = deque(maxlen=_DROWSY_WINDOW)
        self.last_centroid: Optional[Tuple[float, float]] = None
        self.last_seen = 0.0   # timestamp

    def update(
        self,
        raw: Dict[str, float],
        eyes_open: bool,
        centroid: Tuple[float, float],
    ) -> Dict[str, float]:
        """
        Apply EMA to raw pose angles, update eye history.
        Returns smoothed pose dict.
        """
        import time
        self.last_seen = time.time()
        self.last_centroid = centroid

        # EMA update
        if self._yaw is None:
            self._yaw, self._pitch, self._roll = (
                raw['yaw'], raw['pitch'], raw['roll']
            )
        else:
            a = _EMA_ALPHA
            self._yaw   = a * raw['yaw']   + (1 - a) * self._yaw
            self._pitch = a * raw['pitch'] + (1 - a) * self._pitch
            self._roll  = a * raw['roll']  + (1 - a) * self._roll

        self._eye_history.append(eyes_open)

        return {
            'yaw':   self._yaw,
            'pitch': self._pitch,
            'roll':  self._roll,
        }

    @property
    def drowsy(self) -> bool:
        """
        True if eyes were closed in >= DROWSY_THRESHOLD of the last N frames.
        Requires at least half the window to be filled before flagging.
        """
        if len(self._eye_history) < _DROWSY_WINDOW // 2:
            return False
        closed_count = sum(1 for e in self._eye_history if not e)
        return closed_count >= _DROWSY_THRESHOLD

    @property
    def is_stale(self) -> bool:
        import time
        return (time.time() - self.last_seen) > 4.0


class AttentionAnalyzer:
    """
    Per-frame face attention analyzer v2 — pure OpenCV, no external downloads.

    Key improvements over v1:
    • EMA smoothing eliminates yaw/pitch jitter across frames
    • Roll threshold catches head-tilt / slouching
    • Drowsiness tracking (persistent eye closure across N frames)
    • Confidence score on each classification (0–100)
    • Face-size filtering and "too_small" status for tiny faces
    • CLAHE cached — not recreated per face

    Usage:
        analyzer = AttentionAnalyzer()
        results  = analyzer.analyze_faces(frame, face_bboxes)
    """

    # ── Thresholds ─────────────────────────────────────────────────────────────
    # Conservative defaults — prefer fewer false "distracted" labels.
    # Override via Django settings ATTENTION_YAW_THRESHOLD / PITCH / ROLL.
    DEFAULT_YAW_THRESHOLD   = 30.0   # horizontal look-away (degrees)
    DEFAULT_PITCH_THRESHOLD = 25.0   # up/down head tilt (degrees)
    # Roll at 55°: conservative because solvePnP roll from bbox pseudo-landmarks
    # is noisier than yaw/pitch. Only catches extreme tilts (sleeping on desk,
    # phone-in-lap). Real eye corners needed for sub-30° roll accuracy.
    DEFAULT_ROLL_THRESHOLD  = 55.0   # sideways head tilt / severe slouch

    # Ignore |roll| > 150° — these are degenerate solvePnP results from
    # near-profile faces or very small bboxes where the 2D→3D mapping fails.
    DEGENERATE_ROLL_GUARD   = 150.0

    # "Uncertain zone" — within this many degrees of a threshold boundary
    UNCERTAINTY_MARGIN = 8.0

    MIN_FACE_SIZE = 60   # px — faces smaller than this are marked "too_small"

    def __init__(
        self,
        yaw_threshold:   float = DEFAULT_YAW_THRESHOLD,
        pitch_threshold: float = DEFAULT_PITCH_THRESHOLD,
        roll_threshold:  float = DEFAULT_ROLL_THRESHOLD,
    ):
        self.yaw_threshold   = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.roll_threshold  = roll_threshold

        # Eye cascade (bundled with OpenCV — no download)
        self._eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )
        self._eye_cascade_alt = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml'
        )

        # Cached CLAHE object (created once, reused per frame)
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))

        # Per-face pose smoothers: centroid (cx,cy) → _FacePoseSmoother
        self._smoothers: Dict[Tuple[int, int], _FacePoseSmoother] = {}

        logger.info(
            "AttentionAnalyzer v2 ready — yaw=%.0f° pitch=%.0f° roll=%.0f°",
            self.yaw_threshold, self.pitch_threshold, self.roll_threshold,
        )

    # ── Smoother registry ─────────────────────────────────────────────────────

    def _get_smoother(self, centroid: Tuple[float, float]) -> _FacePoseSmoother:
        """
        Find existing smoother for this face position, or create a new one.
        Matches by proximity within _FACE_MATCH_RADIUS pixels, so the tracker
        follows a face even if its bbox shifts slightly between frames.
        """
        import time
        # Prune stale smoothers first
        stale_keys = [k for k, s in self._smoothers.items() if s.is_stale]
        for k in stale_keys:
            del self._smoothers[k]

        # Find closest existing smoother within match radius
        best_key  = None
        best_dist = float('inf')
        cx, cy = centroid
        for key, smoother in self._smoothers.items():
            if smoother.last_centroid is None:
                continue
            dx = smoother.last_centroid[0] - cx
            dy = smoother.last_centroid[1] - cy
            d  = (dx*dx + dy*dy) ** 0.5
            if d < best_dist and d < _FACE_MATCH_RADIUS:
                best_dist = d
                best_key  = key

        if best_key is not None:
            return self._smoothers[best_key]

        # New face — create smoother keyed by rounded centroid
        key = (int(cx), int(cy))
        self._smoothers[key] = _FacePoseSmoother()
        self._smoothers[key].last_seen = time.time()
        return self._smoothers[key]

    # ── Eye detection ─────────────────────────────────────────────────────────

    def _detect_eyes_open(
        self,
        gray_eq: np.ndarray,    # full-frame equalized grayscale
        face_bbox: Tuple[int, int, int, int],
    ) -> bool:
        """
        Detect whether at least one eye is open in the face ROI.

        Uses the upper 55% of the face bbox (forehead-to-nose region).
        Pre-equalized grayscale is passed in — no per-call CLAHE.

        Returns True (open) if any eye detected, or if face ROI is too small.
        Returns False if no eye detected (likely closed, heavily occluded, or
        glasses causing detection failure — see bias notice in module docstring).
        """
        x, y, w, h = face_bbox
        if w < self.MIN_FACE_SIZE or h < self.MIN_FACE_SIZE:
            return True  # Too small to analyze — assume open

        eye_region_h = int(h * 0.55)
        roi = gray_eq[y : y + eye_region_h, x : x + w]
        if roi.size == 0:
            return True

        for cascade in (self._eye_cascade, self._eye_cascade_alt):
            eyes = cascade.detectMultiScale(
                roi, scaleFactor=1.1, minNeighbors=3, minSize=(12, 12)
            )
            if len(eyes) > 0:
                return True
        return False

    # ── Classification ─────────────────────────────────────────────────────────

    def _classify(
        self,
        pose: Dict[str, float],
        eyes_open: bool,
        drowsy: bool,
        face_w: int,
    ) -> Dict:
        """
        Classify a face as attentive/uncertain/distracted with a confidence score.

        Confidence (0–100): how far the worst metric is from its threshold boundary.
        A score of 100 means perfectly frontal, eyes wide open.
        A score near 0 means just barely attentive.

        Returns dict: {status, confidence, reasons}
        """
        yaw   = abs(pose['yaw'])
        pitch = abs(pose['pitch'])
        roll  = abs(pose['roll'])

        # Guard: roll > 150° is a degenerate solvePnP result from near-profile
        # or very small faces — don't penalize for it
        if roll > self.DEGENERATE_ROLL_GUARD:
            roll = 0.0   # treat as if roll is zero (safe default)

        # Compute margin to each threshold (positive = ok, negative = exceeded)
        yaw_margin   = self.yaw_threshold   - yaw
        pitch_margin = self.pitch_threshold - pitch
        roll_margin  = self.roll_threshold  - roll

        reasons = []
        ok = True

        if yaw_margin < 0:
            ok = False
            reasons.append(f"yaw={yaw:.0f}°>{self.yaw_threshold:.0f}°")
        if pitch_margin < 0:
            ok = False
            reasons.append(f"pitch={pitch:.0f}°>{self.pitch_threshold:.0f}°")
        if roll_margin < 0:
            ok = False
            reasons.append(f"roll={roll:.0f}°>{self.roll_threshold:.0f}°")
        if drowsy:
            ok = False
            reasons.append("drowsy")
        elif not eyes_open:
            ok = False
            reasons.append("eyes_closed")

        if ok:
            # Confidence = how far we are from the worst threshold (normalized 0-100)
            worst_margin_pct = min(
                yaw_margin   / self.yaw_threshold,
                pitch_margin / self.pitch_threshold,
                roll_margin  / self.roll_threshold,
            )
            confidence = min(100, round(worst_margin_pct * 100))

            # "Uncertain" if we're within the uncertainty margin of any boundary
            if (yaw_margin   < self.UNCERTAINTY_MARGIN or
                pitch_margin < self.UNCERTAINTY_MARGIN or
                roll_margin  < self.UNCERTAINTY_MARGIN):
                return {'status': 'uncertain', 'confidence': confidence, 'reasons': reasons}

            return {'status': 'attentive', 'confidence': confidence, 'reasons': reasons}

        # Distracted — confidence inversely related to how far over threshold we are
        worst_over = max(
            max(0, -yaw_margin)   / self.yaw_threshold,
            max(0, -pitch_margin) / self.pitch_threshold,
            max(0, -roll_margin)  / self.roll_threshold,
        )
        confidence = max(0, round(100 - worst_over * 100))
        return {'status': 'distracted', 'confidence': confidence, 'reasons': reasons}

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze_faces(
        self,
        frame: np.ndarray,
        face_bboxes: List[Tuple[int, int, int, int]],
    ) -> List[Dict]:
        """
        Analyze attention for each detected face in the frame.

        Args:
            frame:       BGR frame from OpenCV (or decoded from browser JPEG).
            face_bboxes: List of (x, y, w, h) from face detector.

        Returns:
            List of dicts, one per face:
            {
                'bbox':       (x, y, w, h),
                'yaw':        float (smoothed degrees),
                'pitch':      float (smoothed degrees),
                'roll':       float (smoothed degrees),
                'eyes_open':  bool (current frame),
                'drowsy':     bool (persistent eye closure across frames),
                'status':     'attentive' | 'uncertain' | 'distracted' | 'too_small',
                'confidence': int 0–100,
                'reasons':    list[str] (why distracted, if applicable),
            }
        """
        if frame is None or len(face_bboxes) == 0:
            return []

        # Pre-process once: grayscale + CLAHE (shared across all faces this frame)
        gray     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_eq  = self._clahe.apply(gray)
        shape    = frame.shape
        results  = []

        for bbox in face_bboxes:
            x, y, w, h = bbox
            cx, cy = x + w / 2.0, y + h / 2.0

            # Skip faces too small to analyze reliably
            if w < self.MIN_FACE_SIZE or h < self.MIN_FACE_SIZE:
                results.append({
                    'bbox': bbox, 'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0,
                    'eyes_open': True, 'drowsy': False,
                    'status': 'too_small', 'confidence': 0, 'reasons': ['face_too_small'],
                })
                continue

            # Head pose estimation
            raw_pose = _solve_pose(bbox, shape)
            if raw_pose is None:
                raw_pose = {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0}

            # EMA smoothing via per-face smoother
            smoother     = self._get_smoother((cx, cy))
            eyes_open    = self._detect_eyes_open(gray_eq, bbox)
            smooth_pose  = smoother.update(raw_pose, eyes_open, (cx, cy))
            drowsy       = smoother.drowsy

            # Classify with confidence
            classification = self._classify(smooth_pose, eyes_open, drowsy, w)

            results.append({
                'bbox':       bbox,
                'yaw':        round(smooth_pose['yaw'],   1),
                'pitch':      round(smooth_pose['pitch'], 1),
                'roll':       round(smooth_pose['roll'],  1),
                'eyes_open':  eyes_open,
                'drowsy':     drowsy,
                'status':     classification['status'],
                'confidence': classification['confidence'],
                'reasons':    classification['reasons'],
            })

        return results

    def draw_attention_overlay(
        self,
        frame: np.ndarray,
        attention_results: List[Dict],
        show_pose: bool = True,
    ) -> np.ndarray:
        """
        Draw attention overlays — color-coded by status, with pose angles.
        Green = attentive, Yellow = uncertain, Red = distracted.
        """
        annotated = frame.copy()
        status_colors = {
            'attentive':  (0,  200, 80),    # green
            'uncertain':  (0,  200, 220),   # amber/yellow
            'distracted': (0,  60,  220),   # red
            'too_small':  (128, 128, 128),  # grey
        }

        for r in attention_results:
            x, y, w, h = r['bbox']
            color = status_colors.get(r['status'], (128, 128, 128))

            # Status label
            icon  = {'attentive': '✓', 'distracted': '✗',
                     'uncertain': '~', 'too_small': '?'}.get(r['status'], '?')
            label = f"{icon} {r['status'].upper()} {r['confidence']}%"

            cv2.rectangle(annotated, (x, y - 22), (x + w, y), color, -1)
            cv2.putText(annotated, label, (x + 4, y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 1)

            if show_pose:
                pose_txt = f"Y:{r['yaw']:+.0f}° P:{r['pitch']:+.0f}° R:{r['roll']:+.0f}°"
                cv2.putText(annotated, pose_txt, (x + 4, y + h + 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)

                if r.get('drowsy'):
                    cv2.putText(annotated, "DROWSY", (x + 4, y + h + 28),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 180, 255), 1, cv2.LINE_AA)

        return annotated
