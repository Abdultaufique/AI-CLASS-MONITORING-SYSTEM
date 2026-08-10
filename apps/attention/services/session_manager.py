"""
SessionManager — singleton that manages active AttentionScorer instances
and bridges between the camera processing thread and the Django ORM.

Lifecycle:
    start_session(camera_id, org, camera_obj, aggregate_only)
        → creates AttentionSession DB record
        → creates AttentionScorer in memory
    push_frame_result(camera_id, face_attention_list)
        → pushes into AttentionScorer
        → periodically flushes AttentionSnapshot rows to DB
    end_session(camera_id)
        → closes AttentionSession DB record
        → flushes any remaining snapshots
        → returns session_id for report generation

Thread-safety: the manager dict is protected by a Lock. Each AttentionScorer
has its own lock internally.
"""
import time
import threading
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# Delay Django ORM imports until runtime (processor.py pattern)
_orm_ready = False


def _ensure_orm():
    global _orm_ready
    if not _orm_ready:
        import django
        django.setup()
        _orm_ready = True


class SessionManager:
    """
    Singleton managing active attention sessions per camera.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        # Maps camera_id (str) → dict with 'scorer', 'session_id', 'last_flush'
        self._sessions: Dict[str, dict] = {}
        self._mgr_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'SessionManager':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def start_session(
        self,
        camera_id: str,
        org,
        camera_obj,
        aggregate_only: bool = True,
        alert_threshold: float = 0.50,
        alert_duration_secs: int = 30,
        rolling_window_frames: int = 30,
    ) -> Optional[str]:
        """
        Start a new attention monitoring session for a camera.
        Returns the session UUID string, or None on failure.
        """
        from apps.attention.models import AttentionSession
        from ai_engine.attention_scorer import AttentionScorer

        with self._mgr_lock:
            if camera_id in self._sessions:
                logger.warning("Session already active for camera %s — ending it first", camera_id)
                self._end_session_locked(camera_id)

            try:
                session = AttentionSession.objects.create(
                    organization=org,
                    camera=camera_obj,
                    aggregate_only=aggregate_only,
                    alert_threshold=alert_threshold,
                    alert_duration_secs=alert_duration_secs,
                    status='active',
                )
                scorer = AttentionScorer(
                    alert_threshold=alert_threshold,
                    alert_duration_secs=float(alert_duration_secs),
                    rolling_window_frames=rolling_window_frames,
                )
                self._sessions[camera_id] = {
                    'session_id':   str(session.id),
                    'scorer':       scorer,
                    'last_flush':   time.time(),
                    'aggregate_only': aggregate_only,
                    'org':          org,           # stored for notification calls
                    'last_alert_notif': False,     # debounce alert notifications
                }
                logger.info("Attention session %s started for camera %s", session.id, camera_id)
                return str(session.id)
            except Exception as exc:
                logger.error("Failed to start attention session: %s", exc)
                return None

    def end_session(self, camera_id: str) -> Optional[str]:
        """
        End the active session for a camera. Returns the session_id string.
        """
        with self._mgr_lock:
            return self._end_session_locked(camera_id)

    def _end_session_locked(self, camera_id: str) -> Optional[str]:
        """Must be called while holding _mgr_lock."""
        from apps.attention.models import AttentionSession
        from django.utils import timezone

        entry = self._sessions.pop(camera_id, None)
        if not entry:
            return None

        session_id = entry['session_id']
        scorer     = entry['scorer']

        # Flush remaining snapshots
        self._flush_snapshots(session_id, scorer, force=True)

        try:
            session = AttentionSession.objects.get(id=session_id)
            session.status   = 'ended'
            session.ended_at = timezone.now()
            session.save()
            logger.info("Attention session %s ended", session_id)
        except Exception as exc:
            logger.error("Failed to close session %s: %s", session_id, exc)

        return session_id

    # ── Frame data ingestion ───────────────────────────────────────────────────

    def push_frame_result(
        self,
        camera_id: str,
        face_attention_list: List[dict],
    ) -> None:
        """
        Ingest attention analysis results for one frame.
        Called from the camera processing thread (ai_engine/processor.py).

        Transparently no-ops if no session is active for this camera
        — zero overhead on existing camera processing flows.
        """
        entry = self._sessions.get(camera_id)
        if not entry:
            return  # No active session — safe no-op

        scorer = entry['scorer']
        scorer.push_frame(face_attention_list)

        # Flush snapshots to DB if interval elapsed
        now = time.time()
        if (now - entry['last_flush']) >= 5.0:
            self._flush_snapshots(entry['session_id'], scorer)
            entry['last_flush'] = now

    def _flush_snapshots(
        self,
        session_id: str,
        scorer,
        force: bool = False,
    ) -> None:
        """Write a single AttentionSnapshot row to DB from current scorer state."""
        from apps.attention.models import AttentionSession, AttentionSnapshot
        from django.utils import timezone

        state = scorer.get_live_state()
        try:
            session = AttentionSession.objects.get(id=session_id)
            AttentionSnapshot.objects.create(
                session=session,
                timestamp=timezone.now(),
                class_attention_pct=state['class_pct'],
                total_faces=state['total_slots'],
                attentive_count=state['attentive'],
                distracted_count=state['distracted'],
                alert_active=state['alert_active'],
            )

            # P6: Fire notification when attention alert activates
            # Debounced — only fires once per alert edge (False→True)
            entry = None
            for cam_id, e in self._sessions.items():
                if e.get('session_id') == session_id:
                    entry = e
                    break
            if entry is not None and state['alert_active'] and not entry.get('last_alert_notif', False):
                org = entry.get('org')
                if org:
                    try:
                        from apps.notifications.services.notification_service import NotificationService
                        pct = round(state['class_pct'] * 100)
                        NotificationService.create_and_send(
                            organization=org,
                            title=f'⚠ Low Attention Alert — {pct}% attentive',
                            message=(
                                f'Class attention has dropped to {pct}% and stayed below '
                                f'the threshold. Consider adjusting teaching pace.'
                            ),
                            severity='warning',
                            notification_type='system',
                        )
                    except Exception:
                        pass
                entry['last_alert_notif'] = True
            elif entry is not None and not state['alert_active']:
                entry['last_alert_notif'] = False  # reset so next alert fires again

        except Exception as exc:
            logger.debug("Snapshot flush error (non-fatal): %s", exc)

    # ── Read access (WebSocket consumer) ──────────────────────────────────────

    def get_live_state(self, camera_id: str) -> Optional[dict]:
        """
        Get current live state for a camera's active session.
        Returns None if no session is active.
        """
        entry = self._sessions.get(camera_id)
        if not entry:
            return None
        state = entry['scorer'].get_live_state()
        state['session_id']    = entry['session_id']
        state['aggregate_only'] = entry['aggregate_only']
        return state

    def get_active_session_id(self, camera_id: str) -> Optional[str]:
        """Return active session ID for a camera, or None."""
        entry = self._sessions.get(camera_id)
        return entry['session_id'] if entry else None

    def has_active_session(self, camera_id: str) -> bool:
        return camera_id in self._sessions

    def list_active_cameras(self) -> List[str]:
        return list(self._sessions.keys())
