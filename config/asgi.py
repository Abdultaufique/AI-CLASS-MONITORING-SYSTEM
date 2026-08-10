"""
ASGI config for the monitoring platform — supports WebSocket via Channels.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Strip any accidental whitespace/newlines from the env var (Render dashboard bug)
_settings = os.environ.get('DJANGO_SETTINGS_MODULE', '').strip()
# Auto-detect Render environment (RENDER is always set on Render)
if os.environ.get('RENDER') or _settings == 'config.settings.render':
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render'
elif _settings:
    os.environ['DJANGO_SETTINGS_MODULE'] = _settings
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

django_asgi_app = get_asgi_application()

from apps.notifications.routing import websocket_urlpatterns as notification_ws
from apps.monitoring.routing   import websocket_urlpatterns as monitoring_ws
from apps.attention.routing    import websocket_urlpatterns as attention_ws

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            notification_ws + monitoring_ws + attention_ws
        )
    ),
})

