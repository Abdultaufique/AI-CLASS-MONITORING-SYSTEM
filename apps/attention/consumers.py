"""
WebSocket consumer for live attention data streaming.

Connects to: ws/attention/<camera_id>/

Pushes live attention state to the dashboard every second while the session
is active. Accepts 'start_session' / 'end_session' control messages.

Extends the existing WebSocket pattern from apps/monitoring/consumers.py.
"""
import json
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class AttentionConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer: streams live attention stats for a single camera session.
    One instance per connected dashboard client.
    """

    PUSH_INTERVAL = 1.0  # seconds between state pushes

    async def connect(self):
        self.camera_id  = self.scope['url_route']['kwargs']['camera_id']
        self.group_name = f'attention_{self.camera_id}'
        self._streaming = False

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.debug("AttentionConsumer connected for camera %s", self.camera_id)

        # Auto-start streaming if session is active
        asyncio.create_task(self._push_loop())

    async def disconnect(self, close_code):
        self._streaming = False
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug("AttentionConsumer disconnected for camera %s", self.camera_id)

    async def receive(self, text_data):
        """Handle control messages from the dashboard client."""
        try:
            data    = json.loads(text_data)
            command = data.get('command')
        except (json.JSONDecodeError, ValueError):
            return

        if command == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))
        elif command == 'get_state':
            state = await self._get_live_state()
            if state:
                await self.send(text_data=json.dumps({'type': 'state', **state}))

    # ── Push loop ──────────────────────────────────────────────────────────────

    async def _push_loop(self):
        """Continuously push live attention state to the connected client."""
        self._streaming = True
        while self._streaming:
            state = await self._get_live_state()
            if state:
                try:
                    await self.send(text_data=json.dumps({'type': 'state', **state}))
                except Exception:
                    break
            await asyncio.sleep(self.PUSH_INTERVAL)

    @database_sync_to_async
    def _get_live_state(self):
        """Fetch live attention state from SessionManager (sync ORM call)."""
        from apps.attention.services.session_manager import SessionManager
        manager = SessionManager.get_instance()
        state   = manager.get_live_state(self.camera_id)
        if state is None:
            return {'status': 'no_session', 'camera_id': self.camera_id}
        # Respect aggregate_only privacy setting: strip per-slot data
        if state.get('aggregate_only', True):
            state.pop('slots', None)
        state['type'] = 'state'
        return state

    # ── Group broadcast handler ────────────────────────────────────────────────

    async def attention_alert(self, event):
        """Handle alert broadcast sent to the group."""
        await self.send(text_data=json.dumps({
            'type':    'alert',
            'message': event.get('message', 'Low attention alert'),
            'camera_id': self.camera_id,
        }))
