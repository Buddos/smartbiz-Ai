from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .events import business_group_name

class BusinessRealtimeConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user", AnonymousUser())
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        if not user.business_id:
            await self.close(code=4403)
            return

        self.business_id = str(user.business_id)
        self.group_name = business_group_name(self.business_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "connection.ready",
            "business_id": self.business_id,
            "capabilities": {
                "business_events": True,
                "assistant_chat": False,
            },
        })

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.send_json({
                "type": "error",
                "code": "invalid_message",
                "message": "Send a JSON object.",
            })
            return

        message_type = content.get("type")
        if message_type == "ping":
            await self.send_json({"type": "pong"})
            return
        if message_type != "ping":
            await self.send_json({
                "type": "error",
                "code": "unsupported_message",
                "message": "Supported client message type: ping.",
            })
            return
        await self.send_json({"type": "pong"})

    async def business_data_changed(self, event):
        await self.send_json({
            "type": "business.data.changed",
            "event_id": event["event_id"],
            "occurred_at": event["occurred_at"],
            "resource": event["resource"],
            "operation": event["operation"],
            "object_id": event["object_id"],
        })
