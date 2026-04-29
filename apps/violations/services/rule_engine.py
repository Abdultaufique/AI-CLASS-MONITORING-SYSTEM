"""
Rule Engine — enforces talking rules with tiered warnings and violations.

Warning levels:
  1 → Soft notification
  2 → Strong alert
  3 → Violation marked

After max_violations_before_expel violations → "Please leave" alert.
Warnings reset daily.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from apps.violations.models import Warning, Violation, RuleConfig
from apps.accounts.models import Organization

logger = logging.getLogger(__name__)


class RuleEngine:
    """Processes talking detections and enforces the warning/violation pipeline."""

    def __init__(self, organization: Organization):
        self.organization = organization
        self._load_config()

    def _load_config(self):
        """Load organization rule configuration."""
        try:
            self.config = RuleConfig.objects.get(organization=self.organization)
        except RuleConfig.DoesNotExist:
            self.config = RuleConfig.objects.create(organization=self.organization)

    def process_talking_detection(self, user: User, camera_location: str = ''):
        """
        Called when talking is detected for an identified user.
        Returns dict with action taken and details.
        """
        today = timezone.now().date()

        # Get or create today's violation record
        violation, _ = Violation.objects.get_or_create(
            user=user,
            date=today,
            organization=self.organization,
            defaults={'warning_count': 0}
        )

        # If already expelled today, just log
        if violation.is_expelled:
            return {
                'action': 'already_expelled',
                'message': f'{user.get_full_name()} has already been asked to leave today.',
                'severity': 'critical',
            }

        # Check cooldown
        cooldown = timezone.now() - timedelta(seconds=self.config.cooldown_seconds)
        recent_warning = Warning.objects.filter(
            user=user, organization=self.organization,
            created_at__gte=cooldown,
        ).exists()

        if recent_warning:
            return {
                'action': 'cooldown',
                'message': 'Warning cooldown active.',
                'severity': 'info',
            }

        # Count today's warnings
        today_count = Warning.objects.filter(
            user=user, organization=self.organization,
            created_at__date=today,
        ).count()

        warning_level = min(today_count + 1, self.config.max_warnings_per_day)

        # Create warning
        warning = Warning.objects.create(
            user=user,
            organization=self.organization,
            level=warning_level,
            reason='Talking detected in quiet zone',
            camera_location=camera_location,
        )

        # Update violation count
        violation.warning_count = today_count + 1
        violation.save()

        # Determine action
        if warning_level == 1:
            result = {
                'action': 'warning_1',
                'warning_id': str(warning.id),
                'message': f'⚠️ {user.get_full_name()}: Please be quiet. (Warning 1/{self.config.max_warnings_per_day})',
                'severity': 'warning',
            }
        elif warning_level == 2:
            result = {
                'action': 'warning_2',
                'warning_id': str(warning.id),
                'message': f'🔶 {user.get_full_name()}: Second warning! Please stop talking. (Warning 2/{self.config.max_warnings_per_day})',
                'severity': 'high',
            }
        elif warning_level >= self.config.max_warnings_per_day:
            # Check total violations
            total_violations = Violation.objects.filter(
                user=user, organization=self.organization,
                warning_count__gte=self.config.max_warnings_per_day,
            ).count()

            if total_violations >= self.config.max_violations_before_expel:
                violation.is_expelled = True
                violation.save()
                result = {
                    'action': 'expelled',
                    'warning_id': str(warning.id),
                    'message': f'🚫 {user.get_full_name()}: Maximum violations reached. Please leave the class/library.',
                    'severity': 'critical',
                }
            else:
                result = {
                    'action': 'violation',
                    'warning_id': str(warning.id),
                    'message': f'🔴 {user.get_full_name()}: Violation marked! ({total_violations + 1}/{self.config.max_violations_before_expel} violations)',
                    'severity': 'critical',
                }
        else:
            result = {
                'action': f'warning_{warning_level}',
                'warning_id': str(warning.id),
                'message': f'Warning {warning_level} for {user.get_full_name()}',
                'severity': 'warning',
            }

        logger.info(f"Rule engine: {result['action']} for {user.get_full_name()}")
        return result

    @staticmethod
    def reset_daily_warnings(organization=None):
        """Reset daily tracking — called by scheduled task."""
        logger.info("Daily warning reset — violations are preserved in history.")
