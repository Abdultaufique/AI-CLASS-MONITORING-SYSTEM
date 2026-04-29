"""
WebSocket consumer for real-time notifications.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    """Pushes notifications to connected dashboard clients."""

    async def connect(self):
        user = self.scope.get('user')
        if user and hasattr(user, 'is_authenticated') and user.is_authenticated:
            try:
                from apps.accounts.models import UserProfile
                profile = await self._get_profile(user)
                if profile:
                    self.group_name = f'notifications_{profile.organization_id}'
                    await self.channel_layer.group_add(self.group_name, self.channel_name)
            except Exception:
                pass
        await self.accept()

    @staticmethod
    async def _get_profile(user):
        from channels.db import database_sync_to_async
        from apps.accounts.models import UserProfile
        @database_sync_to_async
        def get_prof(u):
            try:
                return u.profile
            except UserProfile.DoesNotExist:
                return None
        return await get_prof(user)

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'mark_read':
            notification_id = data.get('id')
            from .services.notification_service import NotificationService
            NotificationService.mark_read(notification_id)

    async def notification_message(self, event):
        """Send notification to WebSocket client."""
        await self.send(text_data=json.dumps(event['data']))
