"""
ASGI config for the monitoring platform — supports WebSocket via Channels.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

django_asgi_app = get_asgi_application()

from apps.notifications.routing import websocket_urlpatterns as notification_ws
from apps.monitoring.routing import websocket_urlpatterns as monitoring_ws

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            notification_ws + monitoring_ws
        )
    ),
})
