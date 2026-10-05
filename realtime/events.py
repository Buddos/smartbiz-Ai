import logging
import uuid
from functools import partial

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def business_group_name(business_id):
    return f"business_{business_id}"


def queue_business_event(business_id, resource, operation, object_id):
    if not business_id:
        return

    event = {
        "type": "business.data.changed",
        "event_id": str(uuid.uuid4()),
        "occurred_at": timezone.now().isoformat(),
        "resource": resource,
        "operation": operation,
        "object_id": str(object_id),
    }

    def publish():
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.error("Realtime event not published: no channel layer is configured.")
            return
        async_to_sync(channel_layer.group_send)(
            business_group_name(business_id),
            event,
        )

    transaction.on_commit(publish, robust=True)
