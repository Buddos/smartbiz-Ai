from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .events import business_group_name

ASSISTANT_ROLES = {"OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"}


@database_sync_to_async
def _answer_business_question(business_id, question):
    from businesses.models import Business
    from ai_engine.gemini import answer_business_question

    business = Business.objects.get(pk=business_id)
    return answer_business_question(business, question)


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
        self.can_use_assistant = user.role in ASSISTANT_ROLES
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "connection.ready",
            "business_id": self.business_id,
            "capabilities": {
                "business_events": True,
                "assistant_chat": self.can_use_assistant,
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
        if message_type != "assistant.ask":
            await self.send_json({
                "type": "error",
                "code": "unsupported_message",
                "message": "Supported client message types: ping, assistant.ask.",
            })
            return
        if not self.can_use_assistant:
            await self.send_json({
                "type": "assistant.error",
                "code": "forbidden",
                "message": "Your role cannot use the AI assistant.",
                "request_id": content.get("request_id"),
            })
            return

        request_id = content.get("request_id")
        if not isinstance(request_id, str):
            request_id = None
        else:
            request_id = request_id[:100]

        question = content.get("question")
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            await self.send_json({
                "type": "assistant.error",
                "code": "invalid_question",
                "message": "Provide a question containing 1 to 1,000 characters.",
                "request_id": request_id,
            })
            return

        from ai_engine.gemini import GeminiError

        try:
            answer = await _answer_business_question(
                self.business_id,
                question.strip(),
            )
        except GeminiError as exc:
            await self.send_json({
                "type": "assistant.error",
                "code": "assistant_unavailable",
                "message": str(exc),
                "request_id": request_id,
            })
            return

        await self.send_json({
            "type": "assistant.answer",
            "request_id": request_id,
            "answer": answer,
        })

    async def business_data_changed(self, event):
        await self.send_json({
            "type": "business.data.changed",
            "event_id": event["event_id"],
            "occurred_at": event["occurred_at"],
            "resource": event["resource"],
            "operation": event["operation"],
            "object_id": event["object_id"],
        })
