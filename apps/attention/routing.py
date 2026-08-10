"""
WebSocket routing for attention monitoring app.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/attention/(?P<camera_id>[^/]+)/$', consumers.AttentionConsumer.as_asgi()),
]
