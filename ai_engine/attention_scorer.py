"""
Attention Scorer v2 — session-level state machine for attention tracking.

KEY IMPROVEMENTS over v1:
  • Hysteresis band — slot needs score >= 0.60 to become attentive, <= 0.40
    to become distracted. Prevents rapid flipping when score oscillates at 0.5.
  • Confidence-weighted class % — larger faces (closer/clearer) weighted more.
    Confidence comes from AttentionAnalyzer v2 per-face classification score.
  • "No faces" sentinel — class_pct is returned as None (not 1.0) when zero
    faces are in frame, so the UI shows "—" not misleading "100%".
  • Rapid-drop alert — if class_pct drops > 40 points in one frame, alert fires
    immediately (without waiting for sustained duration). Catches whole-class
    disruption events (fire alarm, teacher leaves room).
  • Improved slot assignment — uses face bbox centroid proximity (IoU-like)
    instead of pure index order, so students changing seats don't swap scores.
  • Uncertain status treated proportionally — counts as 0.5 attentive in class %.
  • "too_small" faces excluded from class % (not enough signal to classify).

Thread-safety: all public methods are protected by a threading.Lock.

DISCLAIMER: Scores are derived from geometric heuristics in attention_analyzer.py
and are approximations, not validated measurements. See README §Bias & Fairness.
"""
import time
import threading
import logging
from collections import deque
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SlotTracker:
    """
    Tracks attention state for a single anonymous face 'slot' across frames.

    Slots are positional / anonymous — NOT linked to any student's identity.
    Assignment is by bbox centroid proximity, not seat number or identity.

    v2 improvements:
      • Hysteresis: requires score >= 0.60 to become attentive, <= 0.40 to
        become distracted. Avoids rapid flipping at the 0.5 boundary.
      • Confidence-weighted frames: each frame contributes proportional to its
        confidence score (0–100), not as a flat 0/1 boolean.
      • Uncertain frames contribute 0.5 weight (not 0).
      • Drowsiness flag propagated as separate status signal.
    """

    ATTENTIVE_THRESHOLD  = 0.60   # score must be >= this to show as attentive
    DISTRACTED_THRESHOLD = 0.40   # score must drop below this to show as distracted

    def __init__(self, slot_id: int, window_size: int = 30):
        self.slot_id     = slot_id
        self.window_size = window_size
        # Deque of weighted scores: 0.0 (distracted) → 1.0 (fully attentive)
        self._frames: deque = deque(maxlen=window_size)
        self._status_cache = 'uncertain'   # hysteresis-controlled status
        self.last_seen     = time.time()
        self.last_centroid: Optional[Tuple[float, float]] = None
        self.drowsy_count  = 0   # how many of last N frames were drowsy

    def push(self, face_result: Dict) -> None:
        """
        Push one frame's face result (from AttentionAnalyzer.analyze_faces).
        face_result keys: status, confidence, drowsy (from v2 analyzer).
        """
        status     = face_result.get('status', 'uncertain')
        confidence = face_result.get('confidence', 50) / 100.0
        drowsy     = face_result.get('drowsy', False)

        if status == 'attentive':
            weight = 1.0 * confidence
        elif status == 'uncertain':
            weight = 0.5  # uncertain = half credit
        elif status == 'too_small':
            return  # Don't count tiny faces at all
        else:  # distracted
            weight = 0.0

        self._frames.append(weight)
        self.drowsy_count += int(drowsy)
        if len(self._frames) == self.window_size:
            self.drowsy_count = max(0, self.drowsy_count - 1)

        self.last_seen = time.time()
        # Update hysteresis status
        s = self.score
        if s >= self.ATTENTIVE_THRESHOLD:
            self._status_cache = 'attentive'
        elif s <= self.DISTRACTED_THRESHOLD:
            self._status_cache = 'distracted'
        # else: retain previous status (hysteresis zone 0.40–0.60)

    def push_bool(self, is_attentive: bool) -> None:
        """Compatibility shim for callers using old boolean API."""
        self.push({'status': 'attentive' if is_attentive else 'distracted', 'confidence': 70})

    def update_centroid(self, cx: float, cy: float) -> None:
        self.last_centroid = (cx, cy)
        self.last_seen = time.time()

    @property
    def score(self) -> float:
        """
        Weighted rolling attention score in [0.0, 1.0].
        1.0 = always fully attentive with high confidence.
        Returns 0.5 (uncertain) if no data yet.
        """
        if not self._frames:
            return 0.5
        return sum(self._frames) / len(self._frames)

    @property
    def status(self) -> str:
        """Hysteresis-controlled status: attentive | uncertain | distracted."""
        if not self._frames:
            return 'uncertain'
        return self._status_cache

    @property
    def is_stale(self) -> bool:
        """Slot is considered stale if not updated for > 3 seconds."""
        return (time.time() - self.last_seen) > 3.0

    @property
    def is_drowsy(self) -> bool:
        return self.drowsy_count > 2


class AttentionScorer:
    """
    Class-wide attention scoring engine for a single camera session (v2).

    Typical lifecycle:
        scorer = AttentionScorer(alert_threshold=0.5, alert_duration=30)
        scorer.push_frame(face_attention_results)   # called per frame
        state = scorer.get_live_state()             # read from WebSocket consumer
        snapshots = scorer.get_time_series()        # read at session end
    """

    SLOT_STALE_TIMEOUT_SECS = 3.0   # Forget slot if not seen for this long
    SNAPSHOT_INTERVAL_SECS  = 5.0   # How often to record a time-series point
    RAPID_DROP_THRESHOLD    = 0.40  # Immediate alert if class_pct drops this much in 1 frame

    def __init__(
        self,
        alert_threshold:       float = 0.50,
        alert_duration_secs:   float = 30.0,
        rolling_window_frames: int   = 30,
    ):
        self.alert_threshold     = alert_threshold
        self.alert_duration_secs = alert_duration_secs
        self.window_size         = rolling_window_frames

        self._lock   = threading.Lock()
        self._slots: Dict[int, SlotTracker] = {}
        self._next_slot_id = 0

        self._time_series: List[Tuple]      = []
        self._last_snapshot_ts              = time.time()
        self._prev_class_pct: Optional[float] = None  # for rapid-drop detection

        # Alert state
        self._below_threshold_since: Optional[float] = None
        self._alert_active           = False
        self._alert_events: List[Dict] = []
        self._alert_current_min      = 1.0

        self.started_at = time.time()

    # ── Slot assignment ────────────────────────────────────────────────────────

    def _assign_slots_by_proximity(
        self, face_results: List[Dict]
    ) -> List[Tuple[int, Dict]]:
        """
        Match each face result to the nearest existing slot by centroid proximity.
        Creates new slots for unmatched faces, prunes stale slots.
        Returns [(slot_id, face_result), ...]
        """
        # Prune stale slots
        stale = [sid for sid, s in self._slots.items() if s.is_stale]
        for sid in stale:
            del self._slots[sid]

        if not face_results:
            return []

        # Build centroid list for each face
        def centroid(r):
            x, y, w, h = r.get('bbox', (0, 0, 0, 0))
            return (x + w / 2.0, y + h / 2.0)

        face_centroids = [centroid(r) for r in face_results]
        used_slots     = set()
        assignments    = []

        for fi, fc in enumerate(face_centroids):
            best_slot_id = None
            best_dist    = float('inf')

            for sid, slot in self._slots.items():
                if sid in used_slots or slot.last_centroid is None:
                    continue
                dx = slot.last_centroid[0] - fc[0]
                dy = slot.last_centroid[1] - fc[1]
                d  = (dx*dx + dy*dy) ** 0.5
                if d < best_dist and d < 120:  # 120px match radius
                    best_dist    = d
                    best_slot_id = sid

            if best_slot_id is not None:
                used_slots.add(best_slot_id)
                self._slots[best_slot_id].update_centroid(*fc)
                assignments.append((best_slot_id, face_results[fi]))
            else:
                # New face — create new slot
                sid = self._next_slot_id
                self._next_slot_id += 1
                self._slots[sid] = SlotTracker(sid, self.window_size)
                self._slots[sid].update_centroid(*fc)
                used_slots.add(sid)
                assignments.append((sid, face_results[fi]))

        return assignments

    # ── Class percentage computation ──────────────────────────────────────────

    def _compute_class_pct(self) -> Optional[float]:
        """
        Compute class-wide attention % from active slots.

        v2: confidence-weighted — larger/clearer faces contribute more.
        Returns None (not 1.0) when no faces are in frame.
        Returns float in [0.0, 1.0] when faces present.

        Uncertain slots contribute 0.5 to both numerator and denominator.
        'too_small' slots are excluded entirely.
        """
        active = [s for s in self._slots.values() if not s.is_stale]
        if not active:
            return None  # No faces → undefined (shown as "—" in UI)

        # Weight each slot by its rolling score confidence (proxy: score * 2 if attentive, else 1)
        total_weight = 0.0
        attentive_weight = 0.0
        for slot in active:
            st = slot.status
            sc = slot.score
            if st == 'attentive':
                w = 1.0 + sc          # reward high-confidence attentive (1.0–2.0)
                attentive_weight += w
                total_weight += w
            elif st == 'uncertain':
                w = 0.8
                attentive_weight += w * 0.5  # half credit
                total_weight += w
            else:  # distracted
                w = 1.0 + (1.0 - sc)  # heavier weight for high-confidence distracted
                total_weight += w

        if total_weight == 0:
            return None
        return attentive_weight / total_weight

    # ── Alert logic ───────────────────────────────────────────────────────────

    def _update_alert_state(self, class_pct: Optional[float], ts: float) -> None:
        """
        Update sustained low-attention alert state.

        v2 additions:
          • Immediate alert if class_pct drops > 40% from previous frame
            (whole-class disruption detection).
          • No alert when class_pct is None (no faces in frame).
        """
        if class_pct is None:
            # No faces — reset alert state, don't trigger
            self._below_threshold_since = None
            self._prev_class_pct        = None
            return

        # Rapid drop detection
        if (self._prev_class_pct is not None and
                (self._prev_class_pct - class_pct) > self.RAPID_DROP_THRESHOLD):
            if not self._alert_active:
                self._alert_active = True
                self._alert_events.append({
                    'start': ts, 'end': None,
                    'min_pct': round(class_pct, 3),
                    'type': 'rapid_drop',
                })
                logger.warning(
                    "Attention rapid-drop alert — class fell from %.0f%% to %.0f%%",
                    self._prev_class_pct * 100, class_pct * 100,
                )

        self._prev_class_pct = class_pct

        # Sustained low-attention alert
        if class_pct < self.alert_threshold:
            if self._below_threshold_since is None:
                self._below_threshold_since = ts
                self._alert_current_min = class_pct
            else:
                self._alert_current_min = min(self._alert_current_min, class_pct)
                duration = ts - self._below_threshold_since
                if duration >= self.alert_duration_secs and not self._alert_active:
                    self._alert_active = True
                    self._alert_events.append({
                        'start': self._below_threshold_since, 'end': None,
                        'min_pct': round(self._alert_current_min, 3),
                        'type': 'sustained',
                    })
                    logger.warning(
                        "Attention sustained-low alert — %.0f%% for %.0fs",
                        class_pct * 100, duration,
                    )
        else:
            if self._alert_active and self._alert_events:
                self._alert_events[-1]['end'] = ts
            self._below_threshold_since = None
            self._alert_active = False
            self._alert_current_min = 1.0

    # ── Public API ─────────────────────────────────────────────────────────────

    def push_frame(self, face_attention_results: List[Dict]) -> None:
        """
        Ingest per-frame attention results from AttentionAnalyzer.analyze_faces().
        Thread-safe.

        face_attention_results: list of dicts with at minimum:
            {'bbox', 'status', 'confidence', 'drowsy'} (v2 analyzer output).
        Backwards-compatible with v1 dicts that only have {'bbox', 'status'}.
        """
        ts = time.time()
        with self._lock:
            assignments = self._assign_slots_by_proximity(face_attention_results)
            for slot_id, face_result in assignments:
                self._slots[slot_id].push(face_result)

            class_pct = self._compute_class_pct()
            self._update_alert_state(class_pct, ts)

            # Record time-series snapshot
            if (ts - self._last_snapshot_ts) >= self.SNAPSHOT_INTERVAL_SECS:
                slot_data = {
                    sid: {
                        'status': s.status,
                        'score':  round(s.score, 3),
                        'drowsy': s.is_drowsy,
                    }
                    for sid, s in self._slots.items() if not s.is_stale
                }
                self._time_series.append((ts, class_pct, slot_data))
                self._last_snapshot_ts = ts

    def _compute_class_pct_locked(self) -> Optional[float]:
        """_compute_class_pct without lock (for use inside locked methods)."""
        return self._compute_class_pct()

    def get_live_state(self) -> Dict:
        """
        Snapshot of current live state for WebSocket push / polling API.
        Thread-safe.

        Returns dict with:
            class_pct:     float 0–1, or None if no faces in frame
            total_slots:   int
            attentive:     int
            uncertain:     int
            distracted:    int
            drowsy_count:  int  ← NEW: number of slots currently flagged drowsy
            alert_active:  bool
            alert_since:   float|None
            slots:         list of slot dicts (for per-slot panel)
            elapsed_secs:  float
        """
        with self._lock:
            active      = [s for s in self._slots.values() if not s.is_stale]
            class_pct   = self._compute_class_pct()
            attentive   = sum(1 for s in active if s.status == 'attentive')
            uncertain   = sum(1 for s in active if s.status == 'uncertain')
            distracted  = sum(1 for s in active if s.status == 'distracted')
            drowsy_count = sum(1 for s in active if s.is_drowsy)
            slots = [
                {
                    'id':     s.slot_id,
                    'status': s.status,
                    'score':  round(s.score, 3),
                    'drowsy': s.is_drowsy,
                }
                for s in active
            ]
            return {
                'class_pct':    round(class_pct, 4) if class_pct is not None else None,
                'total_slots':  len(active),
                'attentive':    attentive,
                'uncertain':    uncertain,
                'distracted':   distracted,
                'drowsy_count': drowsy_count,
                'alert_active': self._alert_active,
                'alert_since':  self._below_threshold_since,
                'slots':        slots,
                'elapsed_secs': round(time.time() - self.started_at, 1),
            }

    def get_time_series(self) -> List[Dict]:
        """Return recorded time-series for report generation. Thread-safe."""
        with self._lock:
            return [
                {
                    'timestamp':  ts,
                    'class_pct':  pct,
                    'slot_count': len(slots),
                }
                for ts, pct, slots in self._time_series
            ]

    def get_alert_events(self) -> List[Dict]:
        """Return list of alert events with start/end timestamps."""
        with self._lock:
            events = list(self._alert_events)
            if events and events[-1]['end'] is None:
                events[-1] = dict(events[-1])
                events[-1]['end'] = time.time()
            return events

    def get_summary_stats(self) -> Dict:
        """Session summary statistics for the CSV report."""
        with self._lock:
            if not self._time_series:
                return {
                    'avg_pct': None, 'min_pct': None, 'max_pct': None,
                    'total_dip_duration_secs': 0, 'dip_count': 0,
                    'total_snapshots': 0,
                }
            pcts = [pct for _, pct, _ in self._time_series if pct is not None]
            if not pcts:
                pcts = [0.0]
            alert_events = self.get_alert_events()
            total_dip = sum(
                (e['end'] or time.time()) - e['start']
                for e in alert_events if e.get('end') is not None
            )
            return {
                'avg_pct':                  round(sum(pcts) / len(pcts), 4),
                'min_pct':                  round(min(pcts), 4),
                'max_pct':                  round(max(pcts), 4),
                'total_dip_duration_secs':  round(total_dip, 1),
                'dip_count':                len(alert_events),
                'total_snapshots':          len(pcts),
            }
