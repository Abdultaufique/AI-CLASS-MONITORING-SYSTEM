"""
WebSocket consumer for live camera feed streaming.
"""
import json
import asyncio
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from .services.camera_service import CameraManager


class CameraConsumer(AsyncWebsocketConsumer):
    """Streams camera frames over WebSocket to the dashboard."""

    async def connect(self):
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        self.group_name = f'camera_{self.camera_id}'
        self.streaming = False

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        self.streaming = False
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        command = data.get('command')

        if command == 'start_stream':
            self.streaming = True
            asyncio.create_task(self._stream_frames())
        elif command == 'stop_stream':
            self.streaming = False
        elif command == 'browser_frame':
            # Handle frame from browser webcam
            frame_data = data.get('frame')
            if frame_data:
                await self.channel_layer.group_send(
                    self.group_name,
                    {'type': 'camera.frame', 'frame': frame_data}
                )

    async def _stream_frames(self):
        """Stream frames from the camera to the WebSocket."""
        manager = CameraManager.get_instance()
        cam = manager.get_camera(self.camera_id)

        while self.streaming and cam and cam.is_running:
            jpeg = cam.get_jpeg_frame()
            if jpeg:
                frame_b64 = base64.b64encode(jpeg).decode('utf-8')
                await self.send(text_data=json.dumps({
                    'type': 'frame',
                    'data': frame_b64,
                }))
            await asyncio.sleep(0.066)  # ~15 FPS over WebSocket

    async def camera_frame(self, event):
        """Handle camera frame from group broadcast."""
        await self.send(text_data=json.dumps({
            'type': 'frame',
            'data': event['frame'],
        }))
