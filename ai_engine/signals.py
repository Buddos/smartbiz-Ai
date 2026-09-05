import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from expenses.models import Expense
from inventory.models import InventoryTransaction
from sales.models import SaleItem

logger = logging.getLogger(__name__)


def _queue_pipeline(business):
    if not business or not getattr(settings, "AI_ENGINE_EVENT_PIPELINE", True):
        return

    def run():
        try:
            from .services import run_intelligence_pipeline
            run_intelligence_pipeline(business)
        except Exception:
            logger.exception("SmartBiz AI event pipeline failed for business %s", business.pk)

    transaction.on_commit(run)


@receiver(post_save, sender=SaleItem)
def sale_item_saved(sender, instance, **kwargs):
    _queue_pipeline(instance.sale.business)


@receiver(post_save, sender=Expense)
def expense_saved(sender, instance, **kwargs):
    _queue_pipeline(instance.business)


@receiver(post_save, sender=InventoryTransaction)
def inventory_transaction_saved(sender, instance, **kwargs):
    _queue_pipeline(instance.business)
