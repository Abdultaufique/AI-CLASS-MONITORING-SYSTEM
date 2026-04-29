"""
Models for violations: Warning, Violation, RuleConfig.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from apps.accounts.models import Organization


class RuleConfig(models.Model):
    """Per-organization configurable rules."""
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='rule_config'
    )
    max_warnings_per_day = models.IntegerField(default=3)
    max_violations_before_expel = models.IntegerField(default=3)
    audio_threshold = models.IntegerField(
        default=500, help_text='RMS audio level threshold for talking detection'
    )
    cooldown_seconds = models.IntegerField(
        default=30, help_text='Minimum seconds between warnings for the same person'
    )
    auto_reset_daily = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Rules for {self.organization.name}"


class Warning(models.Model):
    """A warning issued when talking is detected."""
    LEVEL_CHOICES = [
        (1, 'Warning 1 — Notification'),
        (2, 'Warning 2 — Strong Alert'),
        (3, 'Warning 3 — Violation Marked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='warnings')
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='warnings'
    )
    level = models.IntegerField(choices=LEVEL_CHOICES)
    reason = models.CharField(max_length=300, default='Talking detected')
    camera_location = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Warning L{self.level} — {self.user.get_full_name()} ({self.created_at.strftime('%H:%M')})"


class Violation(models.Model):
    """Tracks accumulated violations per student per day."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='violations')
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='violations'
    )
    date = models.DateField(auto_now_add=True, db_index=True)
    warning_count = models.IntegerField(default=0)
    is_expelled = models.BooleanField(default=False,
                                       help_text='Student asked to leave for the day')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['user', 'date']
        indexes = [
            models.Index(fields=['organization', 'date']),
        ]

    def __str__(self):
        status = "EXPELLED" if self.is_expelled else f"{self.warning_count} warnings"
        return f"{self.user.get_full_name()} — {self.date} — {status}"
