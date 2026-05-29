"""
WebSocket consumer — pushes access events to connected clients in real time.

Channel group: "access_feed"

Frontend connects to: ws://<host>/ws/access-feed/

Every time an AccessEvent is saved, the post_save signal calls
broadcast_access_event() which sends to this group.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger('recognition')

ACCESS_FEED_GROUP = 'access_feed'


class AccessFeedConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        # Authenticate — only admin/guard may receive live feed
        user = self.scope.get('user')
        if not user or not user.is_authenticated or user.role not in ('admin', 'guard'):
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(ACCESS_FEED_GROUP, self.channel_name)
        await self.accept()
        logger.info('WS connected: %s', user.email)

        # Send last 20 events on connect
        events = await self._get_recent_events()
        await self.send(text_data=json.dumps({'type': 'history', 'events': events}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(ACCESS_FEED_GROUP, self.channel_name)

    # Receive push from channel layer (sent by broadcast_access_event signal)
    async def access_event(self, event):
        await self.send(text_data=json.dumps({'type': 'event', 'data': event['data']}))

    @database_sync_to_async
    def _get_recent_events(self):
        from zones.models import AccessEvent
        from zones.serializers import AccessEventSerializer
        qs = AccessEvent.objects.select_related('zone', 'person').order_by('-created_at')[:20]
        return AccessEventSerializer(qs, many=True).data