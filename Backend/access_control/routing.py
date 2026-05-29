from django.urls import path
from .consumers import AccessLogConsumer

websocket_urlpatterns = [
    path('ws/access-log/', AccessLogConsumer.as_asgi()),
]