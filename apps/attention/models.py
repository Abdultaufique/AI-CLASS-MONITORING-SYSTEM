"""
Models for Attention Monitoring.

Two models store the session-level results:
  AttentionSession  — one per monitoring session (start/end time, config).
  AttentionSnapshot — periodic class-wide attention snapshots within a session.

Design principles:
  • Raw video is NEVER stored. Only derived numeric metrics are persisted.
  • Per-student identification is never stored in v1. All data is aggregate
    (class-wide %) or per-anonymous-slot (not linked to any individual identity).
  • Snapshots are written every ~5 seconds; fine-grained frame data lives only
    in memory in AttentionScorer during a live session.
"""
import uuid
from django.db import models
from apps.accounts.models import Organization
from apps.monitoring.models import Camera


class AttentionSession(models.Model):
    """
    One monitoring session — represents a contiguous period of attention tracking
    for a single camera feed.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('ended',  'Ended'),
        ('error',  'Error'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='attention_sessions'
    )
    camera       = models.ForeignKey(
        Camera, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attention_sessions'
    )
    started_at   = models.DateTimeField(auto_now_add=True)
    ended_at     = models.DateTimeField(null=True, blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')

    # Privacy configuration — aggregate_only=True means per-slot data is not
    # exposed in the dashboard or reports; only class-wide % is shown.
    aggregate_only = models.BooleanField(
        default=True,
        help_text=(
            'When True (default), only class-wide attention % is displayed. '
            'No per-slot (anonymous) cards are shown. Recommended for all deployments.'
        ),
    )

    # Alert thresholds stored at session creation (in case settings change mid-run)
    alert_threshold    = models.FloatField(default=0.50)
    alert_duration_secs = models.IntegerField(default=30)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        status_str = self.status.upper()
        cam_str    = self.camera.name if self.camera else 'No Camera'
        return f"Session {str(self.id)[:8]} [{status_str}] — {cam_str}"

    @property
    def duration_secs(self):
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None


class AttentionSnapshot(models.Model):
    """
    A periodic (every ~5s) aggregate snapshot of class attention during a session.

    No individual student data is ever stored here. All values are class-wide
    aggregates or counts of anonymous face slots.

    These snapshots are the basis for session reports and the attention-over-time
    graph. They are lightweight and safe to retain post-session.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session     = models.ForeignKey(
        AttentionSession, on_delete=models.CASCADE, related_name='snapshots'
    )
    timestamp   = models.DateTimeField()            # Exact moment of snapshot

    # Class-wide metrics
    class_attention_pct = models.FloatField()       # 0.0 – 1.0
    total_faces         = models.IntegerField(default=0)
    attentive_count     = models.IntegerField(default=0)
    distracted_count    = models.IntegerField(default=0)

    # Alert state at this moment
    alert_active = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']
        indexes  = [models.Index(fields=['session', 'timestamp'])]

    def __str__(self):
        return (
            f"Snapshot @{self.timestamp.strftime('%H:%M:%S')} "
            f"— {self.class_attention_pct:.0%} attentive"
        )
