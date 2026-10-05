from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase

from .consumers import BusinessRealtimeConsumer
from .events import business_group_name


class BusinessRealtimeConsumerTests(SimpleTestCase):
    def setUp(self):
        self.business_id = uuid4()
        self.user = SimpleNamespace(
            is_authenticated=True,
            business_id=self.business_id,
            role="OWNER",
        )

    def test_authenticated_user_receives_business_change_events(self):
        async_to_sync(self._assert_business_event_delivery)()

    async def _assert_business_event_delivery(self):
        communicator = WebsocketCommunicator(
            BusinessRealtimeConsumer.as_asgi(),
            "/ws/v1/business/",
        )
        communicator.scope["user"] = self.user

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        ready = await communicator.receive_json_from()
        self.assertEqual(ready["type"], "connection.ready")
        self.assertEqual(ready["business_id"], str(self.business_id))

        await get_channel_layer().group_send(
            business_group_name(self.business_id),
            {
                "type": "business.data.changed",
                "event_id": "event-1",
                "occurred_at": "2026-10-05T10:00:00+00:00",
                "resource": "sales",
                "operation": "created",
                "object_id": "sale-1",
            },
        )
        event = await communicator.receive_json_from()
        self.assertEqual(event["type"], "business.data.changed")
        self.assertEqual(event["resource"], "sales")
        self.assertEqual(event["operation"], "created")
        await communicator.disconnect()

    def test_business_events_are_isolated_between_tenants(self):
        async_to_sync(self._assert_tenant_isolation)()

    async def _assert_tenant_isolation(self):
        communicator = WebsocketCommunicator(
            BusinessRealtimeConsumer.as_asgi(),
            "/ws/v1/business/",
        )
        communicator.scope["user"] = self.user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()

        await get_channel_layer().group_send(
            business_group_name(uuid4()),
            {
                "type": "business.data.changed",
                "event_id": "event-other",
                "occurred_at": "2026-10-05T10:00:00+00:00",
                "resource": "sales",
                "operation": "created",
                "object_id": "other-sale",
            },
        )
        self.assertTrue(await communicator.receive_nothing(timeout=0.01))
        await communicator.disconnect()

    def test_assistant_question_returns_correlated_answer(self):
        async_to_sync(self._assert_assistant_answer)()

    async def _assert_assistant_answer(self):
        communicator = WebsocketCommunicator(
            BusinessRealtimeConsumer.as_asgi(),
            "/ws/v1/business/",
        )
        communicator.scope["user"] = self.user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()

        with patch(
            "realtime.consumers._answer_business_question",
            new_callable=AsyncMock,
            return_value="Your recorded sales are steady.",
        ):
            await communicator.send_json_to({
                "type": "assistant.ask",
                "request_id": "lovable-42",
                "question": "How are sales doing?",
            })
            answer = await communicator.receive_json_from()

        self.assertEqual(answer["type"], "assistant.answer")
        self.assertEqual(answer["request_id"], "lovable-42")
        self.assertEqual(answer["answer"], "Your recorded sales are steady.")
        await communicator.disconnect()

    def test_users_without_business_cannot_connect(self):
        async_to_sync(self._assert_no_business_rejected)()

    async def _assert_no_business_rejected(self):
        communicator = WebsocketCommunicator(
            BusinessRealtimeConsumer.as_asgi(),
            "/ws/v1/business/",
        )
        communicator.scope["user"] = SimpleNamespace(
            is_authenticated=True,
            business_id=None,
            role="OWNER",
        )
        connected, response = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(response["code"], 4403)
