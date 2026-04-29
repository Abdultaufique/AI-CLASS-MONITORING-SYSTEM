"""
Notification service — creates notifications and broadcasts via WebSocket.
"""
import json
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Creates notification records and pushes them via WebSocket."""

    @staticmethod
    def create_and_send(organization, title, message, severity='info',
                        notification_type='system', recipient=None):
        """Create a notification and broadcast it."""
        notification = Notification.objects.create(
            organization=organization,
            recipient=recipient,
            notification_type=notification_type,
            severity=severity,
            title=title,
            message=message,
        )

        # Broadcast via WebSocket
        try:
            channel_layer = get_channel_layer()
            group_name = f'notifications_{organization.id}'
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'notification.message',
                    'data': {
                        'id': str(notification.id),
                        'type': notification_type,
                        'severity': severity,
                        'title': title,
                        'message': message,
                        'created_at': notification.created_at.isoformat(),
                    }
                }
            )
        except Exception as e:
            logger.error(f"WebSocket broadcast failed: {e}")

        return notification

    @staticmethod
    def send_warning_notification(organization, user, warning_result):
        """Send a notification based on rule engine result."""
        return NotificationService.create_and_send(
            organization=organization,
            title=f"Talking Alert — {user.get_full_name()}",
            message=warning_result['message'],
            severity=warning_result['severity'],
            notification_type='warning' if 'warning' in warning_result['action'] else 'violation',
        )

    @staticmethod
    def get_unread(organization, limit=20):
        """Get unread notifications for an organization."""
        return Notification.objects.filter(
            organization=organization, is_read=False
        )[:limit]

    @staticmethod
    def mark_read(notification_id):
        """Mark a notification as read."""
        Notification.objects.filter(id=notification_id).update(is_read=True)

    @staticmethod
    def mark_all_read(organization):
        """Mark all notifications as read for an organization."""
        Notification.objects.filter(
            organization=organization, is_read=False
        ).update(is_read=True)
