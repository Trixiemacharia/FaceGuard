import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faceguard.settings')

django_asgi_app = get_asgi_application()

from zones.consumers import AccessFeedConsumer

websocket_urlpatterns = [
    re_path(r'^ws/access-feed/$', AccessFeedConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})