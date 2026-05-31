import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.urls import re_path
from urllib.parse import parse_qs

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faceguard.settings')

django_asgi_app = get_asgi_application()

from zones.consumers import AccessFeedConsumer

websocket_urlpatterns = [
    re_path(r'^ws/access-feed/$', AccessFeedConsumer.as_asgi()),
]


class JwtQueryAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get('query_string', b'').decode())
        token = (query.get('token') or [''])[0]
        if token:
            user = await self.get_user(token)
            if user is not None:
                scope['user'] = user
        return await self.app(scope, receive, send)

    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            authenticator = JWTAuthentication()
            validated = authenticator.get_validated_token(token)
            return authenticator.get_user(validated)
        except Exception:
            return None

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        JwtQueryAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
